"""
FastAPI backend for the Go game viewer.
"""

import os
import threading
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from kgs import download_games, fetch_game_list
from sgf_parser import parse_sgf, list_sgf_files
from katago import get_engine

GAMES_DIR = os.environ.get("GAMES_DIR", str(Path(__file__).parent.parent / "data" / "games"))
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(GAMES_DIR).mkdir(parents=True, exist_ok=True)
    # Warm up KataGo in a background thread so it doesn't block the event loop
    threading.Thread(target=get_engine, daemon=True).start()
    yield
    get_engine().stop()


app = FastAPI(title="Go Game Viewer", lifespan=lifespan)


# ── REST API ──────────────────────────────────────────────────────────────────

@app.get("/api/games")
def list_games():
    """List all locally stored SGF games."""
    return list_sgf_files(GAMES_DIR)


@app.get("/api/game/{filename}")
def get_game(filename: str):
    """Return parsed game data for a given SGF filename."""
    if not filename.endswith(".sgf") or "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = Path(GAMES_DIR) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Game not found")
    return parse_sgf(str(path))


class DownloadRequest(BaseModel):
    username: str
    max_games: int = 20


@app.post("/api/download")
def download_kgs(req: DownloadRequest, background_tasks: BackgroundTasks):
    """Kick off a background download of games for a KGS username."""
    if not req.username.isalnum() or len(req.username) > 20:
        raise HTTPException(status_code=400, detail="Invalid username")

    def _dl():
        download_games(req.username, GAMES_DIR, req.max_games)

    background_tasks.add_task(_dl)
    return {"status": "started", "username": req.username, "max_games": req.max_games}


@app.get("/api/download/preview")
def preview_kgs(username: str, max_games: int = 20):
    """Fetch game list from KGS without downloading (preview)."""
    if not username.isalnum() or len(username) > 20:
        raise HTTPException(status_code=400, detail="Invalid username")
    try:
        games = fetch_game_list(username, max_games)
        return games
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


class AnalyzeRequest(BaseModel):
    board_size: int = 19
    moves: list[dict]
    move_index: int


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    """Analyze a position using KataGo (runs in thread pool to avoid blocking)."""
    import asyncio
    engine = get_engine()
    return await asyncio.get_event_loop().run_in_executor(
        None, engine.analyze, req.board_size, req.moves, req.move_index
    )


@app.get("/api/katago/status")
def katago_status():
    return {"available": get_engine().available}


# ── Static files ───────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
