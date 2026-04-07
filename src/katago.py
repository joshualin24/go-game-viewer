"""
KataGo GTP interface for live position analysis.

KataGo must be installed separately. Set the KATAGO_PATH env var to the
katago binary, and KATAGO_MODEL to the .bin.gz model file path.
KATAGO_CONFIG may point to a GTP config file (optional).

If KataGo is not configured, analysis requests return a "not available" response.
"""

import os
import re
import select
import subprocess
import threading
import time
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
            # Verify startup with a simple command
            resp = self._gtp("name", timeout=15.0)
            self._available = "KataGo" in resp or len(resp) > 0
        except FileNotFoundError:
            self._proc = None
            self._available = False
        except Exception:
            self._proc = None
            self._available = False

    @property
    def available(self) -> bool:
        return self._available and self._proc is not None and self._proc.poll() is None

    def _gtp(self, cmd: str, timeout: float = 10.0) -> str:
        """Send a standard GTP command (expects a response ending with blank line)."""
        if not self._proc:
            return ""
        self._proc.stdin.write(cmd + "\n")
        self._proc.stdin.flush()
        lines = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            ready, _, _ = select.select([self._proc.stdout], [], [], 0.2)
            if not ready:
                continue
            line = self._proc.stdout.readline()
            if not line:
                break
            line = line.rstrip("\n")
            if line == "":
                break
            lines.append(line)
        return "\n".join(lines)

    def _stream_analyze(self, color: str, duration: float = 3.0, max_moves: int = 5) -> str:
        """
        Send kata-analyze and collect streaming output for `duration` seconds,
        then interrupt with a no-op GTP command and drain.
        Returns the collected info lines as a single string.
        """
        cmd = f"kata-analyze {color} 10 maxmoves {max_moves}\n"
        self._proc.stdin.write(cmd)
        self._proc.stdin.flush()

        lines = []
        deadline = time.time() + duration
        while time.time() < deadline:
            ready, _, _ = select.select([self._proc.stdout], [], [], 0.1)
            if not ready:
                continue
            line = self._proc.stdout.readline()
            if not line:
                break
            lines.append(line.rstrip("\n"))

        # Interrupt the streaming analysis with a new GTP command
        self._proc.stdin.write("name\n")
        self._proc.stdin.flush()

        # Drain until we see the "name" response
        drain_deadline = time.time() + 3.0
        while time.time() < drain_deadline:
            ready, _, _ = select.select([self._proc.stdout], [], [], 0.2)
            if not ready:
                break
            line = self._proc.stdout.readline().rstrip("\n")
            if line == "":
                break
            # Once we see the name response, we're done draining
            if "KataGo" in line:
                break

        return "\n".join(lines)

    def analyze(self, board_size: int, moves: list[dict], move_index: int) -> dict:
        """
        Analyze the position after move_index moves.
        Returns: { "available": bool, "win_rate": float, "top_moves": [...], ... }
        """
        if not self.available:
            return {"available": False, "error": "KataGo not configured. See README."}

        with self._lock:
            try:
                return self._do_analyze(board_size, moves, move_index)
            except Exception as e:
                return {"available": False, "error": str(e)}

    def _col_letter(self, col: int) -> str:
        return "ABCDEFGHJKLMNOPQRST"[col]

    def _to_gtp(self, row: int, col: int, board_size: int) -> str:
        return f"{self._col_letter(col)}{board_size - row}"

    def _do_analyze(self, board_size: int, moves: list[dict], move_index: int) -> dict:
        self._gtp(f"boardsize {board_size}")
        self._gtp("clear_board")
        self._gtp("komi 6.5")

        plays = [m for m in moves[:move_index] if "row" in m or m.get("move") == "pass"]
        for m in plays:
            color = "black" if m["color"] == "b" else "white"
            if m.get("move") == "pass":
                self._gtp(f"play {color} pass")
            else:
                coord = self._to_gtp(m["row"], m["col"], board_size)
                self._gtp(f"play {color} {coord}")

        color_to_play = "black" if (len(plays) % 2 == 0) else "white"

        raw = self._stream_analyze(color_to_play, duration=3.0, max_moves=5)
        return self._parse_analysis(raw, color_to_play, board_size)

    def _parse_analysis(self, raw: str, color: str, board_size: int) -> dict:
        result = {
            "available": True,
            "color_to_play": color,
            "win_rate": None,
            "score_lead": None,
            "top_moves": [],
        }

        # Each streaming output line contains all moves concatenated:
        # "info move Q16 ... order 0 pv ... info move Q4 ... order 1 pv ..."
        # Split each line on "info move" to get individual move tokens.
        # Keep highest-visits entry per move across all updates.
        best: dict[str, dict] = {}
        letters = "ABCDEFGHJKLMNOPQRST"

        for line in raw.split("\n"):
            line = re.sub(r"^[=\s]+", "", line)
            if "info" not in line:
                continue

            # Split into per-move chunks
            chunks = re.split(r"(?=\binfo\b)", line)
            for chunk in chunks:
                chunk = chunk.strip()
                if not chunk.startswith("info"):
                    continue

                move_m   = re.search(r"\bmove (\w+)", chunk)
                wr_m     = re.search(r"\bwinrate ([\d.]+)", chunk)
                score_m  = re.search(r"\bscoreMean ([-\d.]+)", chunk)
                visits_m = re.search(r"\bvisits (\d+)", chunk)
                order_m  = re.search(r"\border (\d+)", chunk)

                if not (move_m and wr_m):
                    continue

                move_str = move_m.group(1)
                win_rate = float(wr_m.group(1))
                score    = float(score_m.group(1)) if score_m  else 0.0
                visits   = int(visits_m.group(1))  if visits_m else 0
                order    = int(order_m.group(1))   if order_m  else 99

                row, col = -1, -1
                if move_str.upper() != "PASS" and len(move_str) >= 2:
                    col_letter = move_str[0].upper()
                    if col_letter in letters:
                        col = letters.index(col_letter)
                        row = board_size - int(move_str[1:])

                entry = {
                    "move": move_str, "row": row, "col": col,
                    "win_rate": win_rate, "score": score,
                    "visits": visits, "order": order,
                }

                if move_str not in best or visits > best[move_str]["visits"]:
                    best[move_str] = entry

        moves = sorted(best.values(), key=lambda m: m["order"])[:5]
        if moves:
            result["win_rate"]   = moves[0]["win_rate"]
            result["score_lead"] = moves[0]["score"]

        result["top_moves"] = [{k: v for k, v in m.items() if k != "order"} for m in moves]
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


_engine: Optional[KataGoEngine] = None


def get_engine() -> KataGoEngine:
    global _engine
    if _engine is None:
        _engine = KataGoEngine()
    return _engine
