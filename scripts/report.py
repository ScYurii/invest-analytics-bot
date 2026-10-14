"""Build the weekly report: refresh prices for the holdings and indices, print the text.

Usage: report.py [--no-update] [--telegram] [--no-summary]
"""
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from invest_bot import store  # noqa: E402
from invest_bot.broker import ReadOnlyBroker  # noqa: E402
from invest_bot import universe  # noqa: E402
from invest_bot.candidates import screen  # noqa: E402
from invest_bot.ideas import this_week, track_record  # noqa: E402
from invest_bot.summary import for_report  # noqa: E402
from invest_bot.portfolio import Prices, load, yahoo_symbol  # noqa: E402
from invest_bot.report import INDICES, snapshot, text as report_text  # noqa: E402
from invest_bot.telegram import Telegram  # noqa: E402
from invest_bot.yahoo import YahooError, fetch  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")


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
        symbols = [s for s, _ in INDICES] + ["EURUSD=X"] + sorted({yahoo_symbol(p.instr) for p in positions})
        for i, sym in enumerate(symbols):
            if i:
                time.sleep(1)
            try:
                store.save(con, fetch(sym, date(2005, 1, 1)))
            except YahooError as e:
                print(f"WARNING: {e}", file=sys.stderr)
    ideas = this_week(broker)
    track = track_record(ROOT / "data" / "ideas" / "results.csv")
    res = ROOT / "data" / "ideas" / "results.csv"
    trend = {up: track_record(res, up) for up in (True, False)}
    rule_f = res.with_name("rule_stats.json")
    rule = json.loads(rule_f.read_text())["lag"] if rule_f.exists() else None
    bk = ROOT / "data" / "backup.json"
    backup = json.loads(bk.read_text()) if bk.exists() else None
    px = Prices(con)
    cands, cstats = candidates(px)
    snap = snapshot(px, positions, cash, lots, ideas, track, trend, rule, backup, cands, cstats)
    text = report_text(snap)
    reports = ROOT / "data" / "reports"
    reports.mkdir(exist_ok=True)
    summary = for_report(reports, snap.today, text) if "--no-summary" not in sys.argv else None
    if "--telegram" in sys.argv:
        tg = Telegram()
        if summary:
            tg.send_plain(f"🧠 Кратко за неделю (написано Claude по цифрам отчёта):\n\n{summary}")
        tg.send_text(text)
        print("sent to Telegram" + (" with a summary" if summary else ""))
    else:
        print(("🧠 Кратко:\n" + summary + "\n\n") if summary else "", text, sep="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
