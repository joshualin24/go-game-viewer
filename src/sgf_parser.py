"""
SGF file parser using sgfmill.
Converts SGF into a JSON-serialisable game dict.
"""

from pathlib import Path
from sgfmill import sgf, sgf_moves


def parse_sgf(path: str) -> dict:
    """
    Parse an SGF file and return a structured game dict:
    {
        "metadata": { player_white, player_black, result, komi, date, ... },
        "board_size": int,
        "moves": [ {"color": "b"|"w", "row": int, "col": int} | {"color": "b"|"w", "move": "pass"} ]
        "setup_stones": { "black": [(row, col), ...], "white": [(row, col), ...] }
    }
    Row/col are 0-indexed from the top-left of the board.
    """
    data = Path(path).read_bytes()
    game = sgf.Sgf_game.from_bytes(data)
    root = game.get_root()

    board_size = game.get_size()

    def prop(key):
        try:
            return root.get(key) or ""
        except KeyError:
            return ""

    metadata = {
        "player_white": prop("PW"),
        "player_black": prop("PB"),
        "white_rank":   prop("WR"),
        "black_rank":   prop("BR"),
        "result":       prop("RE"),
        "komi":         prop("KM"),
        "date":         prop("DT"),
        "event":        prop("EV"),
        "place":        prop("PC"),
        "rules":        prop("RU"),
        "time_limit":   prop("TM"),
        "overtime":     prop("OT"),
    }

    moves = []
    setup_stones = {"black": [], "white": []}

    try:
        board, plays = sgf_moves.get_setup_and_moves(game)
    except Exception:
        return {"metadata": metadata, "board_size": board_size, "moves": [], "setup_stones": setup_stones}

    # Capture any handicap/setup stones
    for color, point in board.list_occupied_points():
        row, col = point
        setup_stones["black" if color == "b" else "white"].append([row, col])

    for color, point in plays:
        if point is None:
            moves.append({"color": color, "move": "pass"})
        else:
            row, col = point
            # Convert from sgfmill coords (0=bottom) to display coords (0=top)
            moves.append({"color": color, "row": board_size - 1 - row, "col": col})

    return {
        "metadata": metadata,
        "board_size": board_size,
        "moves": moves,
        "setup_stones": setup_stones,
    }


def list_sgf_files(games_dir: str) -> list[dict]:
    """Return summary list of all SGF files in games_dir."""
    results = []
    for path in sorted(Path(games_dir).glob("*.sgf")):
        try:
            data = path.read_bytes()
            game = sgf.Sgf_game.from_bytes(data)
            root = game.get_root()
            def _p(k):
                try: return root.get(k) or "?"
                except KeyError: return "?"
            results.append({
                "filename": path.name,
                "player_white": _p("PW"),
                "player_black": _p("PB"),
                "result":       _p("RE"),
                "date":         _p("DT"),
                "board_size":   game.get_size(),
            })
        except Exception:
            results.append({"filename": path.name, "player_white": "?", "player_black": "?",
                            "result": "?", "date": "?", "board_size": 19})
    return results
