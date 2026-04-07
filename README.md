# Go Game Viewer

An interactive Go game viewer with KGS download support and live KataGo analysis.

## Features

- Download SGF games directly from KGS by username
- Interactive board — click intersections or use arrow keys to step through moves
- Move list with clickable chips
- Live analysis via KataGo: win rate bar, score lead, top-move heatmap
- 19×19 / 13×13 / 9×9 board support

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run
bash run.sh
```

Open http://localhost:8000 in your browser.

## KataGo (optional — enables live analysis)

Install KataGo and a model, then set env vars before running:

```bash
export KATAGO_PATH="/usr/local/bin/katago"
export KATAGO_MODEL="/path/to/kata1-b28c512nbt-s6386034176-d3130251843.bin.gz"
export KATAGO_CONFIG="/path/to/gtp.cfg"   # optional
bash run.sh
```

KataGo binaries and models: https://github.com/lightvector/KataGo/releases

## Usage

1. **Download games** — enter a KGS username, click Download. Games land in `data/games/`.
2. **Select a game** from the left panel.
3. **Navigate** with arrow keys (←/→), PageUp/Down, or click the move chips.
4. **Click an intersection** to jump to the move played there.
5. **Analyze** — click "Analyze now" or enable auto-analyze (requires KataGo).

## Project Structure

```
go-game-viewer/
├── src/
│   ├── app.py          # FastAPI backend
│   ├── kgs.py          # KGS downloader
│   ├── sgf_parser.py   # SGF → JSON parser
│   ├── katago.py       # KataGo GTP interface
│   └── static/
│       ├── index.html
│       ├── style.css
│       └── app.js      # Board rendering + UI
├── data/games/         # Downloaded SGF files (git-ignored)
├── requirements.txt
└── run.sh
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `KATAGO_PATH` | `katago` | Path to katago binary |
| `KATAGO_MODEL` | _(empty)_ | Path to KataGo model file |
| `KATAGO_CONFIG` | _(empty)_ | Path to KataGo GTP config |
| `GAMES_DIR` | `./data/games` | Directory for SGF files |
