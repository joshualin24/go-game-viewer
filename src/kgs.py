"""
KGS Go Server game downloader.
Downloads SGF files from a KGS user's game archive.
"""

import os
import time
import requests
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup


KGS_BASE = "https://www.gokgs.com"
KGS_ARCHIVE = f"{KGS_BASE}/gameArchives.jsp"
HEADERS = {"User-Agent": "go-game-viewer/1.0 (educational)"}


def fetch_game_list(username: str, max_games: int = 50) -> list[dict]:
    """
    Fetch list of games for a KGS user.
    Returns list of dicts with keys: url, white, black, date, result, board_size.
    """
    params = {"user": username, "size": 19}
    resp = requests.get(KGS_ARCHIVE, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    games = []

    for row in soup.select("table tr"):
        cells = row.find_all("td")
        if len(cells) < 5:
            continue

        link = cells[0].find("a", href=True)
        if not link or not link["href"].endswith(".sgf"):
            continue

        sgf_url = urljoin(KGS_BASE, link["href"])
        games.append({
            "url": sgf_url,
            "white": cells[1].get_text(strip=True),
            "black": cells[2].get_text(strip=True),
            "date": cells[3].get_text(strip=True),
            "result": cells[4].get_text(strip=True),
            "filename": os.path.basename(link["href"]),
        })

        if len(games) >= max_games:
            break

    return games


def download_games(username: str, output_dir: str, max_games: int = 50) -> list[str]:
    """
    Download SGF files for a KGS user into output_dir.
    Returns list of downloaded file paths.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    game_list = fetch_game_list(username, max_games)
    downloaded = []

    for game in game_list:
        dest = out / game["filename"]
        if dest.exists():
            downloaded.append(str(dest))
            continue

        try:
            resp = requests.get(game["url"], headers=HEADERS, timeout=15)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            downloaded.append(str(dest))
            time.sleep(0.3)  # be polite to KGS
        except Exception as e:
            print(f"Failed to download {game['url']}: {e}")

    return downloaded
