"""Download or refresh daily history for all S&P 500 companies into data/prices.db.

Symbols refreshed within MAX_AGE_DAYS are skipped, so an interrupted run
continues and the weekly run only fetches what is old.

Usage: update_universe.py
"""
import logging
import sys
import time
from datetime import date, datetime, timedelta, UTC
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from invest_bot import store, universe  # noqa: E402
from invest_bot.yahoo import YahooError, fetch  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
START = date(2005, 1, 1)
MAX_AGE_DAYS = 5


def main() -> int:
    con = store.connect()
    members = universe.load(ROOT / "data")
    fresh_after = (datetime.now(UTC) - timedelta(days=MAX_AGE_DAYS)).isoformat()
    fresh = {s for (s,) in con.execute("SELECT symbol FROM symbols WHERE updated_at > ?", (fresh_after,))}
    todo = [universe.yahoo(m["symbol"]) for m in members if universe.yahoo(m["symbol"]) not in fresh]
    print(f"{len(members)} companies, {len(todo)} to fetch", flush=True)
    failed = []
    for n, sym in enumerate(todo, 1):
        try:
            store.save(con, fetch(sym, START))
        except YahooError as e:
            failed.append(f"{sym} ({e})")
        if n % 50 == 0:
            print(f"{n}/{len(todo)}", flush=True)
        time.sleep(1)
    print(f"done, failed: {len(failed)} {'; '.join(failed[:10])}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
