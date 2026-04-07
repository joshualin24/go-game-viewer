"""
KataGo GTP interface for live position analysis.

KataGo must be installed separately. Set the KATAGO_PATH env var to the
katago binary, and KATAGO_MODEL to the .bin.gz model file path.
KATAGO_CONFIG may point to a GTP config file (optional).

If KataGo is not configured, analysis requests return a "not available" response.
"""

import os
import re
import subprocess
import threading
from typing import Optional


class KataGoEngine:
    """Manages a KataGo subprocess and provides position analysis."""

    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._available = False
        self._start()

    def _start(self):
        katago_bin = os.environ.get("KATAGO_PATH", "katago")
        model = os.environ.get("KATAGO_MODEL", "")
        config = os.environ.get("KATAGO_CONFIG", "")

        cmd = [katago_bin, "gtp"]
        if model:
            cmd += ["-model", model]
        if config:
            cmd += ["-config", config]

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
            # Wait for startup
            self._send_cmd("name")
            self._available = True
        except FileNotFoundError:
            self._proc = None
            self._available = False
        except Exception:
            self._proc = None
            self._available = False

    @property
    def available(self) -> bool:
        return self._available and self._proc is not None and self._proc.poll() is None

    def _send_cmd(self, cmd: str) -> str:
        """Send a GTP command and return the response."""
        if not self._proc:
            return ""
        self._proc.stdin.write(cmd + "\n")
        self._proc.stdin.flush()
        lines = []
        while True:
            line = self._proc.stdout.readline()
            if not line:
                break
            line = line.rstrip("\n")
            if line == "":
                break
            lines.append(line)
        return "\n".join(lines)

    def analyze(self, board_size: int, moves: list[dict], move_index: int) -> dict:
        """
        Analyze the position after move_index moves.
        moves: list of {"color": "b"|"w", "row": int, "col": int} dicts (display coords).
        Returns: { "available": bool, "win_rate": float, "top_moves": [...], "error": str }
        """
        if not self.available:
            return {"available": False, "error": "KataGo not configured. See README."}

        with self._lock:
            try:
                return self._do_analyze(board_size, moves, move_index)
            except Exception as e:
                return {"available": False, "error": str(e)}

    def _col_to_letter(self, col: int) -> str:
        letters = "ABCDEFGHJKLMNOPQRST"
        return letters[col]

    def _to_gtp_coord(self, row: int, col: int, board_size: int) -> str:
        # GTP: row 1=bottom, col A=left. Display: row 0=top.
        gtp_row = board_size - row
        return f"{self._col_to_letter(col)}{gtp_row}"

    def _do_analyze(self, board_size: int, moves: list[dict], move_index: int) -> dict:
        self._send_cmd(f"boardsize {board_size}")
        self._send_cmd("clear_board")
        self._send_cmd(f"komi 6.5")

        plays = [m for m in moves[:move_index] if "row" in m or m.get("move") == "pass"]
        for m in plays:
            color = "black" if m["color"] == "b" else "white"
            if m.get("move") == "pass":
                self._send_cmd(f"play {color} pass")
            else:
                coord = self._to_gtp_coord(m["row"], m["col"], board_size)
                self._send_cmd(f"play {color} {coord}")

        # Determine color to play
        if len(plays) == 0:
            color_to_play = "black"
        else:
            last_color = plays[-1]["color"]
            color_to_play = "white" if last_color == "b" else "black"

        # Use kata-analyze for detailed output
        resp = self._send_cmd(f"kata-analyze {color_to_play} interval 0 maxmoves 5")

        return self._parse_analysis(resp, color_to_play, board_size)

    def _parse_analysis(self, resp: str, color: str, board_size: int) -> dict:
        """Parse kata-analyze output."""
        result = {
            "available": True,
            "color_to_play": color,
            "win_rate": None,
            "score_lead": None,
            "top_moves": [],
        }

        # kata-analyze returns lines like:
        # info move A1 visits 100 winrate 0.55 scoreMean 2.3 ...
        for line in resp.split("\n"):
            line = line.lstrip("= ")
            if line.startswith("info"):
                move_match = re.search(r"move (\w+)", line)
                wr_match = re.search(r"winrate ([\d.]+)", line)
                score_match = re.search(r"scoreMean ([-\d.]+)", line)
                visits_match = re.search(r"visits (\d+)", line)

                if move_match and wr_match:
                    move_str = move_match.group(1)
                    win_rate = float(wr_match.group(1))
                    score = float(score_match.group(1)) if score_match else 0.0
                    visits = int(visits_match.group(1)) if visits_match else 0

                    if result["win_rate"] is None:
                        result["win_rate"] = win_rate
                        result["score_lead"] = score

                    # Convert GTP coord back to row/col for heatmap
                    if move_str.upper() != "PASS":
                        letters = "ABCDEFGHJKLMNOPQRST"
                        col_letter = move_str[0].upper()
                        col = letters.index(col_letter) if col_letter in letters else -1
                        gtp_row = int(move_str[1:])
                        row = board_size - gtp_row  # convert to display coords
                        result["top_moves"].append({
                            "move": move_str,
                            "row": row, "col": col,
                            "win_rate": win_rate,
                            "score": score,
                            "visits": visits,
                        })

        return result

    def stop(self):
        if self._proc:
            try:
                self._proc.stdin.write("quit\n")
                self._proc.stdin.flush()
                self._proc.wait(timeout=3)
            except Exception:
                self._proc.kill()
            self._proc = None
            self._available = False


# Singleton instance
_engine: Optional[KataGoEngine] = None


def get_engine() -> KataGoEngine:
    global _engine
    if _engine is None:
        _engine = KataGoEngine()
    return _engine
