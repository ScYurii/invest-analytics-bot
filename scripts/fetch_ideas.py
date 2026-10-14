"""Download Freedom24 investment ideas, their details and price history.

Everything is cached under data/ideas/, so an interrupted run continues where
it stopped; prices are fetched again when a ticker has an idea that needs newer
prices than the cache has. Prices come from Tradernet: it keeps the history of delisted
stocks up to their last trading day (acquisitions, bankruptcies).

Usage: fetch_ideas.py
"""
import json
import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from invest_bot.broker import BrokerError, ReadOnlyBroker  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
DIR = ROOT / "data" / "ideas"


def idea_ticker(idea: dict, details: dict) -> str | None:
    """Delisted stocks lose `ticker`; it survives in the tags."""
    if idea.get("ticker"):
        return idea["ticker"]
    idea_d = details.get("idea")
    tags = (idea_d.get("tags") if isinstance(idea_d, dict) else None) or []
    return tags[0] if tags else None


def horizon_months(raw) -> int:
    try:
        return int(str(raw).split("-")[-1])
    except ValueError:
        return 12


def add_months(d: date, m: int) -> date:
    y, mo = divmod(d.month - 1 + m, 12)
    return date(d.year + y, mo + 1, min(d.day, 28))


def last_bar(f: Path) -> str:
    """Date of the last bar in a cached price file ('' if none). Delisted stocks
    stay behind forever and are fetched again each run, which is cheap."""
    c = json.loads(f.read_text())
    if not c.get("hloc"):
        return ""
    ts = c["xSeries"][next(iter(c["hloc"]))]
    return datetime.fromtimestamp(ts[-1], timezone(timedelta(hours=3))).date().isoformat() if ts else ""


def fetch_details(b: ReadOnlyBroker, idea_id: int, tries: int = 4) -> dict | None:
    """The server sometimes answers {"idea": [], "details": []}; ask again."""
    for attempt in range(tries):
        try:
            d = b._call("getInvestIdeaDetails", {"id": idea_id})
        except BrokerError as e:
            print(f"details {idea_id}: {e}", flush=True)
            d = None
        if d and isinstance(d.get("idea"), dict):
            return d
        time.sleep(5 * (attempt + 1))
    return None


def main() -> None:
    (DIR / "details").mkdir(parents=True, exist_ok=True)
    (DIR / "prices").mkdir(exist_ok=True)
    b = ReadOnlyBroker()

    ideas = b._call("getInvestIdeas", {})["list"]
    (DIR / "list.json").write_text(json.dumps(ideas, ensure_ascii=False))
    stocks = [i for i in ideas if i["investIdeaType"] == 1 and i["instr_type_c"] == 1]
    print(f"{len(ideas)} ideas, {len(stocks)} stock ideas", flush=True)

    # ticker -> the last date its ideas need prices for (the end of the latest horizon)
    tickers: dict[str, str] = {"SPY.US": date.today().isoformat()}
    for n, idea in enumerate(stocks, 1):
        f = DIR / "details" / f"{idea['id']}.json"
        if not f.exists():
            d = fetch_details(b, idea["id"])
            if d is None:
                print(f"details {idea['id']}: empty after retries", flush=True)
                continue
            f.write_text(json.dumps(d, ensure_ascii=False))
        det = json.loads(f.read_text())
        t = idea_ticker(idea, det)
        if t:
            months = horizon_months(det["details"].get("investmentTermRaw") or idea.get("investmentTermRaw"))
            until = min(date.today(), add_months(date.fromisoformat(idea["rawDate"][:10]), months)).isoformat()
            tickers[t] = max(tickers.get(t, ""), until)
        if n % 100 == 0:
            print(f"details {n}/{len(stocks)}", flush=True)

    for n, t in enumerate(sorted(tickers), 1):
        f = DIR / "prices" / f"{t}.json"
        if f.exists() and last_bar(f) >= (date.fromisoformat(tickers[t]) - timedelta(days=4)).isoformat():
            continue                       # has prices up to where its ideas need them
        try:
            c = b.candles(t, datetime(2019, 6, 1), datetime.now())
        except BrokerError as e:
            print(f"prices {t}: {e}", flush=True)
            c = {}
        f.write_text(json.dumps(c))
        if n % 100 == 0:
            print(f"prices {n}/{len(tickers)}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
