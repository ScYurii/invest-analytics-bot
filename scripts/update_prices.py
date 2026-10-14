"""Download or refresh daily history for the symbols in tickers.txt, then check it.

Usage: update_prices.py [SYMBOL ...]   (default: all symbols from tickers.txt)
"""
import logging
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from invest_bot import store  # noqa: E402
from invest_bot.checks import REFERENCE, check  # noqa: E402
from invest_bot.yahoo import YahooError, fetch  # noqa: E402

START = date(2005, 1, 1)
PAUSE = 1.0  # seconds between requests, Yahoo throttles bursts

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")


def read_tickers() -> list[str]:
    lines = (ROOT / "tickers.txt").read_text().splitlines()
    return [line.split("#")[0].strip() for line in lines if line.split("#")[0].strip()]


def main() -> int:
    symbols = sys.argv[1:] or read_tickers()
    # The reference calendar first, so the checks of the others can use it
    symbols = [REFERENCE] + [s for s in symbols if s != REFERENCE]
    con = store.connect()
    failed = 0
    for i, sym in enumerate(symbols):
        if i:
            time.sleep(PAUSE)
        try:
            h = fetch(sym, START)
        except YahooError as e:
            print(f"{sym:6} FAIL {e}")
            failed += 1
            continue
        store.save(con, h)
        first, last = (h.bars[0][0], h.bars[-1][0]) if h.bars else ("-", "-")
        print(f"{sym:6} {len(h.bars):5} bars {first}..{last}  div {len(h.dividends):3}  "
              f"splits {len(h.splits)}  skipped {h.skipped}")

    print("\nChecks:")
    for sym in symbols:
        problems = check(con, sym)
        print(f"{sym:6} " + ("OK" if not problems else "\n       ".join(problems)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
