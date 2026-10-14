"""Would a "sell if it is not growing" rule have helped on Freedom24 ideas?

For every closed idea (see analyze_ideas.py): hold from the day before the idea
to the end of its horizon, or sell earlier when a rule fires. After a sale the
money either stays in cash or goes into SPY until the end of the horizon.
Prices from Tradernet, without dividends; fees and taxes are not counted.

Rules:
  trend   close below its 200-day average on two month-end checks in a row
  lag     12-month return trails SPY by more than LAG (checked at month ends)
  since   return since the purchase trails SPY since the purchase by more than LAG
          (month ends) -- "it stopped growing after I bought it"
  stop    close more than STOP below the entry price (checked daily)
  trail   close more than STOP below the highest close since entry (daily)

Usage: test_exit_rules.py
"""
import csv
import json
import statistics
import sys
from bisect import bisect_left, bisect_right
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_ideas import DIR, load_series  # noqa: E402

LAG = 0.15
STOP = 0.20


def month_ends(dates: list[str], a: int, b: int) -> list[int]:
    return [i for i in range(a + 1, b + 1) if i + 1 >= len(dates) or dates[i][:7] != dates[i + 1][:7]]


def exit_day(rule: str, dates, close, spy_at, i0: int, i1: int) -> int | None:
    """Index of the day the rule sells, or None if it never fires."""
    if rule in ("stop", "trail"):
        peak = close[i0]
        for i in range(i0 + 1, i1 + 1):
            peak = max(peak, close[i])
            ref = close[i0] if rule == "stop" else peak
            if close[i] < ref * (1 - STOP):
                return i
        return None
    below = 0
    for i in month_ends(dates, i0, i1):
        if rule == "trend":
            if i < 199:
                continue
            below = below + 1 if close[i] < statistics.fmean(close[i - 199:i + 1]) else 0
            if below >= 2:
                return i
        elif rule == "since":
            stock = close[i] / close[i0] - 1
            spy = spy_at(dates[i]) / spy_at(dates[i0]) - 1
            if stock - spy < -LAG:
                return i
        elif rule == "lag" and i >= 252:
            stock = close[i] / close[i - 252] - 1
            spy = spy_at(dates[i]) / spy_at(dates[i - 252]) - 1
            if stock - spy < -LAG:
                return i
    return None


def main() -> int:
    spy_d, spy_c, _ = load_series("SPY.US")
    spy_at = lambda d: spy_c[bisect_right(spy_d, d) - 1]  # noqa: E731
    rows = [r for r in csv.DictReader((DIR / "results.csv").open()) if r["status"].startswith("closed")]
    rules = ["trend", "lag", "since", "stop", "trail"]
    res = {r: {"cash": [], "spy": [], "fired": 0, "helped": 0, "switch": []} for r in rules}
    hold, bench, years = [], [], []

    for r in rows:
        s = load_series(r["ticker"])
        if s is None:
            continue
        dates, close, _ = s
        i0 = bisect_left(dates, r["date"]) - 1
        i1 = bisect_right(dates, r["end"]) - 1
        if i0 < 0 or i1 <= i0:
            continue
        held = close[i1] / close[i0] - 1
        spy_all = spy_at(dates[i1]) / spy_at(dates[i0]) - 1
        hold.append(held)
        years.append(r["date"][:4])
        bench.append(spy_all)
        for rule in rules:
            x = exit_day(rule, dates, close, spy_at, i0, i1)
            if x is None:
                res[rule]["cash"].append(held)
                res[rule]["spy"].append(held)
                continue
            sold = close[x] / close[i0] - 1
            then_spy = (1 + sold) * (spy_at(dates[i1]) / spy_at(dates[x])) - 1
            res[rule]["cash"].append(sold)
            res[rule]["spy"].append(then_spy)
            res[rule]["fired"] += 1
            res[rule]["helped"] += sold > held
            res[rule]["switch"].append(then_spy - held)   # gain of moving into SPY

    n = len(hold)
    print(f"Closed ideas: {n}; average horizon result, prices only, no fees or taxes\n")
    print(f"{'strategy':44} {'mean':>7} {'median':>7} {'vs SPY':>7} {'>SPY':>5} {'loss':>5} {'fired':>6} {'sale was right':>14}")

    def line(label, xs, fired="", right=""):
        print(f"{label:44} {statistics.fmean(xs):+7.1%} {statistics.median(xs):+7.1%} "
              f"{statistics.fmean(xs) - statistics.fmean(bench):+7.1%} "
              f"{sum(a > b for a, b in zip(xs, bench)) / n:5.0%} {sum(x < 0 for x in xs) / n:5.0%} {fired:>6} {right:>14}")

    line("Hold to the end of the horizon", hold)
    line("S&P 500 over the same dates", bench)
    names = {"trend": "trend: below 200-day avg 2 months in a row",
             "lag": f"lag: trails SPY by >{LAG:.0%} over 12 months",
             "since": f"since: trails SPY by >{LAG:.0%} since purchase",
             "stop": f"stop: {STOP:.0%} below the entry price",
             "trail": f"trail: {STOP:.0%} below the high since entry"}
    for rule in rules:
        d = res[rule]
        fired = f"{d['fired'] / n:.0%}"
        right = f"{d['helped'] / d['fired']:.0%}" if d["fired"] else "—"
        line(f"{names[rule]}, then cash", d["cash"], fired, right)
        line("   ... then S&P 500", d["spy"])

    stats = {rule: {"fired": res[rule]["fired"] / n,
                    "switch_better": sum(x > 0 for x in res[rule]["switch"]) / max(len(res[rule]["switch"]), 1),
                    "switch_gain": statistics.fmean(res[rule]["switch"]) if res[rule]["switch"] else 0.0,
                    "lag": LAG, "ideas": n}
             for rule in rules}
    (DIR / "rule_stats.json").write_text(json.dumps(stats, indent=1))
    s = stats["lag"]
    print(f"\nWhen 'lag' fired, moving into SPY beat holding in {s['switch_better']:.0%} of cases, "
          f"by {s['switch_gain']:+.1%} on average (saved to rule_stats.json)")

    print("\nBy year of the idea, mean result: hold / rule then S&P 500 / S&P 500")
    for y in sorted(set(years)):
        k = [j for j, yy in enumerate(years) if yy == y]
        cells = "  ".join(f"{rule} {statistics.fmean(res[rule]['spy'][j] for j in k):+6.1%}" for rule in rules)
        print(f"{y} n={len(k):3}  hold {statistics.fmean(hold[j] for j in k):+6.1%}  {cells}  "
              f"SPY {statistics.fmean(bench[j] for j in k):+6.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
