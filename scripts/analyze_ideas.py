"""How did Freedom24 stock ideas do against SPY?

For every long stock idea: the price at the end of its horizon (or the last
trading day of a delisted stock) against the price on the day before the
idea, and the same for SPY. Both from Tradernet, without dividends. A target
counts as reached if the daily high touched it within the horizon.

Returns use the Tradernet series only (split-adjusted); the entry price and the
target are scaled by the ratio of the series price to the idea's entry price,
so splits do not distort them. Ideas whose entry price is far from the series
are left out as unreliable.

Usage: analyze_ideas.py        (after fetch_ideas.py)
"""
import csv
import json
import statistics
import sys
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "data" / "ideas"
MSK = timezone(timedelta(hours=3))  # Tradernet bar timestamps are midnight Moscow time
MISMATCH = 0.30                      # entry price vs series: beyond this, report the idea as adjusted
STALE = 10                           # days without bars before "today" = delisted


def load_series(ticker: str):
    f = DIR / "prices" / f"{ticker}.json"
    if not f.exists():
        return None
    c = json.loads(f.read_text())
    if not c.get("hloc"):
        return None
    k = next(iter(c["hloc"]))
    dates = [datetime.fromtimestamp(t, MSK).date().isoformat() for t in c["xSeries"][k]]
    return dates, [x[3] for x in c["hloc"][k]], [x[0] for x in c["hloc"][k]]  # close, high


def add_months(d: date, m: int) -> date:
    y, mo = divmod(d.month - 1 + m, 12)
    return date(d.year + y, mo + 1, min(d.day, 28))


def horizon(raw: str | None) -> int:
    """'12' -> 12, '3-6' -> 6 (the idea is meant to work within the longer bound)."""
    try:
        return int(str(raw).split("-")[-1])
    except ValueError:
        return 12


def main() -> int:
    ideas = json.loads((DIR / "list.json").read_text())
    stocks = [i for i in ideas if i["investIdeaType"] == 1 and i["instr_type_c"] == 1]
    spy = load_series("SPY.US")
    today = spy[0][-1]
    rows, skipped, adjusted = [], defaultdict(list), []

    for idea in stocks:
        f = DIR / "details" / f"{idea['id']}.json"
        # The server never returned details for a few ideas: take the entry price
        # from the series ("indicative closing price") and the horizon from the list
        det = json.loads(f.read_text()) if f.exists() else {"idea": {}, "details": {}}
        no_details = not f.exists()
        ticker = idea.get("ticker") or (det["idea"].get("tags") or [None])[0]
        s = load_series(ticker) if ticker else None
        if s is None:
            skipped["no prices"].append(ticker or idea["title"][:40])
            continue
        dates, close, high = s
        d0 = idea["rawDate"][:10]
        i0 = bisect_left(dates, d0) - 1          # the last close before the idea
        if i0 < 0:
            skipped["no price before the idea"].append(ticker)
            continue
        try:
            entry = close[i0] if no_details else float(det["details"]["entryPrice"])
            target = float(idea["targetPrice"])
        except (TypeError, ValueError):
            skipped["no entry or target price"].append(ticker)
            continue
        # Splits, reverse splits and spin-offs after the idea rescale the series; the
        # ratio to the entry price carries them into the target, so keep every idea
        scale = close[i0] / entry
        if abs(scale - 1) > MISMATCH:
            adjusted.append(ticker)

        months = horizon(det["details"].get("investmentTermRaw") or idea.get("investmentTermRaw"))
        end = add_months(date.fromisoformat(d0), months).isoformat()
        last = dates[-1]
        delisted = (date.fromisoformat(today) - date.fromisoformat(last)).days > STALE
        if end <= today:
            status = "closed"
        else:
            status = "open"
            end = today
        if delisted and last < end:
            end, status = last, f"{status}, delisted"
        i1 = bisect_right(dates, end) - 1
        j0, j1 = bisect_left(spy[0], d0) - 1, bisect_right(spy[0], end) - 1

        ret = close[i1] / close[i0] - 1
        spy_ret = spy[1][j1] / spy[1][j0] - 1
        hit = max(high[i0 + 1:i1 + 1], default=0) >= target * scale
        trend_up = close[i0] > statistics.fmean(close[max(0, i0 - 199):i0 + 1]) if i0 >= 199 else None
        rows.append({
            "id": idea["id"], "date": d0, "ticker": ticker, "author": idea["author"],
            "risk": det["details"].get("risk"), "months": months, "status": status,
            "entry_from": "series" if no_details else "idea",
            "end": end, "ret": ret, "spy": spy_ret, "excess": ret - spy_ret,
            "target_pct": target / entry - 1, "hit": hit, "title": idea["title"],
            "trend_up": trend_up,
        })

    with open(DIR / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    def summary(label: str, rs: list[dict]) -> None:
        if not rs:
            return
        r = [x["ret"] for x in rs]
        e = [x["excess"] for x in rs]
        print(f"{label:28} {len(rs):5} {statistics.fmean(r):+7.1%} {statistics.median(r):+7.1%} "
              f"{statistics.fmean(x['spy'] for x in rs):+7.1%} {statistics.fmean(e):+7.1%} "
              f"{sum(x > 0 for x in e) / len(rs):6.0%} {sum(x['hit'] for x in rs) / len(rs):6.0%} "
              f"{sum(x < 0 for x in r) / len(rs):6.0%}")

    print(f"Stock ideas: {len(stocks)}, analysed: {len(rows)}, SPY data until {today}")
    print(f"  entry price differs from the series by >{MISMATCH:.0%} (splits, spin-offs), kept: {len(adjusted)}")
    for k, v in skipped.items():
        print(f"  skipped, {k}: {len(v)}  e.g. {', '.join(map(str, v[:5]))}")
    print(f"\n{'group':28} {'n':>5} {'mean':>7} {'median':>7} {'SPY':>7} {'excess':>7} {'>SPY':>6} {'target':>6} {'loss':>6}")
    closed = [x for x in rows if x["status"].startswith("closed")]
    opened = [x for x in rows if x["status"].startswith("open")]
    summary("All closed ideas", closed)
    summary("  of them delisted", [x for x in closed if "delisted" in x["status"]])
    summary("Open ideas (so far)", opened)
    print()
    for y in sorted({x["date"][:4] for x in closed}):
        summary(f"Closed, published {y}", [x for x in closed if x["date"][:4] == y])
    print()
    summary("Closed, stock in uptrend", [x for x in closed if x["trend_up"] is True])
    summary("Closed, stock in downtrend", [x for x in closed if x["trend_up"] is False])
    print()
    for risk in sorted({str(x["risk"]) for x in closed}):
        summary(f"Closed, risk {risk}", [x for x in closed if str(x["risk"]) == risk])
    print()
    by_author = defaultdict(list)
    for x in closed:
        by_author[x["author"]].append(x)
    for a, rs in sorted(by_author.items(), key=lambda kv: -len(kv[1]))[:8]:
        summary(f"Closed, {a[:20]}", rs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
