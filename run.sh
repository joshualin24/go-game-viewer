#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

# Optional KataGo config — set these if you have KataGo installed
# export KATAGO_PATH="/usr/local/bin/katago"
# export KATAGO_MODEL="$HOME/katago/kata1-b28c512nbt-s6386034176-d3130251843.bin.gz"
# export KATAGO_CONFIG="$HOME/katago/gtp_custom.cfg"

# Games directory (default: ./data/games)
# export GAMES_DIR="/path/to/your/sgf/games"

mkdir -p data/games

echo "Starting Go Game Viewer at http://localhost:8000"
cd src
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
