"""The list of S&P 500 companies (from Wikipedia), cached in data/sp500.csv."""
from __future__ import annotations

import csv
import html
import re
import time
from pathlib import Path

import requests

URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
MAX_AGE = 30 * 86400  # refresh the cache once a month


def _cell(c: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", c)).split())


def fetch() -> list[dict]:
    r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0 (invest-analytics-bot; personal use)"}, timeout=30)
    r.raise_for_status()
    s = r.text
    table = s[s.index('id="constituents"'):]
    table = table[:table.index("</table>")]
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)[1:]:
        cells = [_cell(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) >= 6:
            out.append({"symbol": cells[0], "name": cells[1], "sector": cells[2],
                        "industry": cells[3], "added": cells[5]})
    if len(out) < 450:
        raise RuntimeError(f"S&P 500 list looks wrong: {len(out)} rows")
    return out


def load(data: Path) -> list[dict]:
    f = data / "sp500.csv"
    if not f.exists() or time.time() - f.stat().st_mtime > MAX_AGE:
        rows = fetch()
        with f.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
    return list(csv.DictReader(f.open()))


def yahoo(symbol: str) -> str:
    """BRK.B -> BRK-B on Yahoo."""
    return symbol.replace(".", "-")
