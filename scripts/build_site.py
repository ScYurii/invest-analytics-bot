"""Build the dashboard into site/ and save this week's report into the archive.

Usage: build_site.py [--no-update]
"""
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from invest_bot import site, store  # noqa: E402
from invest_bot.broker import ReadOnlyBroker  # noqa: E402
from invest_bot import universe  # noqa: E402
from invest_bot.candidates import screen  # noqa: E402
from invest_bot.ideas import this_week, track_record  # noqa: E402
from invest_bot.summary import for_report  # noqa: E402
from invest_bot.history import series  # noqa: E402
from invest_bot.portfolio import Prices, load, yahoo_symbol  # noqa: E402
from invest_bot.report import INDICES, snapshot, text  # noqa: E402
from invest_bot.yahoo import YahooError, fetch  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
DATA = ROOT / "data"


def candidates(px: Prices) -> tuple[list, dict | None]:
    """Today's screen with the member data, and the screen's track record."""
    data = Path(__file__).resolve().parent.parent / "data"
    if not (data / "sp500.csv").exists():
        return [], None
    members = universe.load(data)
    by_symbol = {universe.yahoo(m["symbol"]): m for m in members}
    picks, _ = screen(px, members)
    f = data / "candidates_stats.json"
    return [(m, by_symbol[m.symbol]) for m in picks], json.loads(f.read_text()) if f.exists() else None


def main() -> int:
    broker = ReadOnlyBroker()
    positions, cash, lots, _ = load(broker)
    con = store.connect()
    if "--no-update" not in sys.argv:
        symbols = ([s for s, _ in INDICES] + ["EURUSD=X"]
                   + sorted({yahoo_symbol(lot.instr) for lot in lots}))
        for i, sym in enumerate(symbols):
            if i:
                time.sleep(1)
            try:
                store.save(con, fetch(sym, date(2005, 1, 1)))
            except YahooError as e:
                print(f"WARNING: {e}", file=sys.stderr)
    px = Prices(con)
    res = DATA / "ideas" / "results.csv"
    snap = snapshot(px, positions, cash, lots, this_week(broker), track_record(res),
                    {up: track_record(res, up) for up in (True, False)},
                    json.loads(res.with_name("rule_stats.json").read_text())["lag"]
                    if res.with_name("rule_stats.json").exists() else None,
                    json.loads((DATA / "backup.json").read_text()) if (DATA / "backup.json").exists() else None,
                    *candidates(px))
    reports = DATA / "reports"
    reports.mkdir(exist_ok=True)
    report = text(snap)
    (reports / f"{snap.today}.txt").write_text(report)
    summary = for_report(reports, snap.today, report)
    (ROOT / "public").mkdir(exist_ok=True)
    site.build(ROOT / "public" / "site", snap, series(px, lots), px.series("SPY", "close"), DATA / "ideas", reports, summary)
    print(f"site built: {ROOT / 'public' / 'site'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
