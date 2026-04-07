"""
KGS Go Server game downloader.
Downloads SGF files from a KGS user's game archive.
"""

import io
import os
import re
import time
import zipfile
import requests
from pathlib import Path
from urllib.parse import urljoin

KGS_BASE    = "https://www.gokgs.com"
KGS_ARCHIVE = f"{KGS_BASE}/gameArchives.jsp"
HEADERS     = {"User-Agent": "Mozilla/5.0 (go-game-viewer/1.0; educational)"}


def _get(url, params=None) -> requests.Response:
    resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp


def _month_links(html: str) -> list[dict]:
    """Extract year/month archive links from the index page HTML."""
    months = []
    for m in re.finditer(
        r'href="gameArchives\.jsp\?user=([^&"]+)&amp;year=(\d+)&amp;month=(\d+)"',
        html,
    ):
        months.append({"user": m.group(1), "year": int(m.group(2)), "month": int(m.group(3))})
    return months


def _sgf_links_from_month_page(html: str) -> list[dict]:
    """Extract direct SGF download links from a month's archive page."""
    games = []
    # Game rows: <td><a href="https://files.gokgs.com/games/...sgf">Yes</a></td>
    # Then white, black, setup, date, type, result in subsequent <td>s
    rows = re.findall(
        r'<tr>\s*<td><a href="(https://files\.gokgs\.com/games/[^"]+\.sgf)">[^<]+</a></td>'
        r'\s*<td[^>]*>(?:<a[^>]*>)?([^<]+)(?:</a>)?</td>'   # white
        r'\s*<td[^>]*>(?:<a[^>]*>)?([^<]+)(?:</a>)?</td>'   # black
        r'\s*<td[^>]*>([^<]*)</td>'                          # setup
        r'\s*<td[^>]*>([^<]*)</td>'                          # date
        r'\s*<td[^>]*>([^<]*)</td>'                          # type
        r'\s*<td[^>]*>([^<]*)</td>',                         # result
        html,
    )
    for url, white, black, setup, date, gtype, result in rows:
        games.append({
            "url":      url,
            "filename": os.path.basename(url),
            "white":    white.strip(),
            "black":    black.strip(),
            "setup":    setup.strip(),
            "date":     date.strip(),
            "type":     gtype.strip(),
            "result":   result.strip(),
        })
    return games


def _zip_url(username: str, year: int, month: int) -> str:
    return f"{KGS_BASE}/servlet/archives/en_US/{username}-{year}-{month:02d}.zip"


def fetch_game_list(username: str, max_games: int = 50) -> list[dict]:
    """
    Fetch a flat list of games for a KGS user across all available months.
    Returns list of game dicts with keys: url, filename, white, black, date, result.
    """
    index_html = _get(KGS_ARCHIVE, params={"user": username}).text
    months = _month_links(index_html)

    games = []
    for entry in reversed(months):          # most recent first
        if len(games) >= max_games:
            break
        try:
            month_html = _get(
                KGS_ARCHIVE,
                params={"user": entry["user"], "year": entry["year"], "month": entry["month"]},
            ).text
            month_games = _sgf_links_from_month_page(month_html)
            games.extend(month_games)
            time.sleep(0.3)
        except Exception as e:
            print(f"  Warning: could not fetch {entry}: {e}")

    return games[:max_games]


def download_games(username: str, output_dir: str, max_games: int = 50) -> list[str]:
    """
    Download SGF files for a KGS user into output_dir.
    Prefers bulk zip download per month; falls back to individual SGF download.
    Returns list of downloaded file paths.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    index_html = _get(KGS_ARCHIVE, params={"user": username}).text
    months = _month_links(index_html)

    downloaded: list[str] = []

    for entry in reversed(months):          # most recent first
        if len(downloaded) >= max_games:
            break

        year, month = entry["year"], entry["month"]

        # Try bulk zip first
        try:
            zip_resp = _get(_zip_url(username, year, month))
            with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as zf:
                for name in zf.namelist():
                    if name.endswith(".sgf"):
                        dest = out / Path(name).name
                        if not dest.exists():
                            dest.write_bytes(zf.read(name))
                        downloaded.append(str(dest))
                        if len(downloaded) >= max_games:
                            break
            time.sleep(0.5)
            continue
        except Exception:
            pass  # fall through to individual download

        # Fallback: parse month page and download individually
        try:
            month_html = _get(
                KGS_ARCHIVE,
                params={"user": entry["user"], "year": year, "month": month},
            ).text
            for game in _sgf_links_from_month_page(month_html):
                if len(downloaded) >= max_games:
                    break
                dest = out / game["filename"]
                if not dest.exists():
                    try:
                        resp = _get(game["url"])
                        dest.write_bytes(resp.content)
                        time.sleep(0.3)
                    except Exception as e:
                        print(f"  Failed to download {game['url']}: {e}")
                        continue
                downloaded.append(str(dest))
        except Exception as e:
            print(f"  Warning: month {year}-{month:02d} fallback failed: {e}")

    return downloaded
