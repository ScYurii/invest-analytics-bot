"""How would the candidate rules have done since 2010?

Every STEP months (quarterly): pick the top 10 by the rules among S&P 500 members (only
from the date each joined the index), hold them equally for a month. Compared
with the equal-weight basket of all members that day (same survivorship bias:
today's list has no companies that left the index) and with SPY.

Fees are estimated for a 4000 EUR account: every name that leaves or enters
the top 10 is one order of 2 + 0.02 per share.

Usage: test_candidates.py
"""
import json
import statistics
import sys
from bisect import bisect_right
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from invest_bot import store, universe  # noqa: E402
from invest_bot.candidates import TOP, metrics, passes  # noqa: E402
from invest_bot.portfolio import Prices  # noqa: E402

START = "2010-01-01"
ACCOUNT = 4000.0   # an example account size
STEP = 3          # months between reviews of the list


def month_ends(dates: list[str]) -> list[str]:
    return [d for k, d in enumerate(dates[:-1]) if d[:7] != dates[k + 1][:7]]


def stats(label: str, r: list[float], months: list[str], base: list[float] | None = None) -> float:
    eq, peak, dd = 1.0, 1.0, 0.0
    for x in r:
        eq *= 1 + x
        peak = max(peak, eq)
        dd = min(dd, eq / peak - 1)
    years = len(r) * STEP / 12
    cagr = eq ** (1 / years) - 1
    beat = f"{sum(a > b for a, b in zip(r, base)) / len(r):5.0%}" if base else "    —"
    half = len(r) // 2
    h1 = statistics.fmean(r[:half]) * 12 / STEP
    h2 = statistics.fmean(r[half:]) * 12 / STEP
    print(f"{label:44} {cagr:+7.1%} {dd:+7.1%} {beat:>8} {h1:+8.1%} {h2:+8.1%}")
    return cagr


def stats_cagr(r: list[float]) -> float:
    eq = 1.0
    for x in r:
        eq *= 1 + x
    return eq ** (12 / STEP / len(r)) - 1


def main() -> int:
    px = Prices(store.connect())
    members = universe.load(ROOT / "data")
    sd, sa = px.series("SPY")
    ends = [d for d in month_ends(sd) if d >= START]
    series = {}
    for m in members:
        sym = universe.yahoo(m["symbol"])
        d, c = px.series(sym, "close")
        if d:
            series[sym] = (d, c, px.series(sym)[1], m["added"] or "1900-01-01")

    top_r, mom_r, all_r, spy_r, turnover = [], [], [], [], []
    prev: set[str] = set()
    for t, t1 in zip(ends[::STEP], ends[STEP::STEP]):
        j = bisect_right(sd, t) - 1
        spy_mom = sa[j - 21] / sa[j - 252] - 1
        rows = []
        for sym, (d, c, a, added) in series.items():
            if added > t:
                continue                       # not in the index yet
            i, i1 = bisect_right(d, t) - 1, bisect_right(d, t1) - 1
            if i < 252 or d[i] != t or d[i1] != t1:
                continue
            x = metrics(d, c, a, i, sym)
            rows.append((x, a[i1] / a[i] - 1))
        if not rows:
            continue
        picked = sorted((r for r in rows if passes(r[0], spy_mom)), key=lambda r: -r[0].mom)[:TOP]
        pure = sorted(rows, key=lambda r: -r[0].mom)[:TOP]
        top_r.append(statistics.fmean(r[1] for r in picked) if picked else 0.0)
        mom_r.append(statistics.fmean(r[1] for r in pure))
        all_r.append(statistics.fmean(r[1] for r in rows))
        spy_r.append(sa[bisect_right(sd, t1) - 1] / sa[j] - 1)
        names = {r[0].symbol for r in picked}
        turnover.append(len(names ^ prev))     # orders: sells + buys
        prev = names

    months = ends[::STEP][:len(top_r)]
    print(f"Periods of {STEP} months: {len(top_r)} ({months[0]}..), companies: {len(series)}\n")
    print(f"{'':44} {'CAGR':>7} {'maxDD':>7} {'>basket':>8} {'1st half':>8} {'2nd half':>8}")
    stats("Candidates: rules + top 10", top_r, months, all_r)
    per_year = 12 / STEP
    fee = [n * (2 + 0.02 * 5) / ACCOUNT for n in turnover]   # ~5 shares per 400 EUR position
    stats(f"  ... minus fees on {ACCOUNT:.0f} EUR", [r - f for r, f in zip(top_r, fee)], months, all_r)
    stats("Momentum only, top 10", mom_r, months, all_r)
    stats("Basket: all members, equal weight", all_r, months)
    stats("SPY", spy_r, months)
    per_year = 12 / STEP
    print(f"\nOrders per review on average: {statistics.fmean(turnover):.1f} "
          f"(fees ≈ {statistics.fmean(fee) * per_year:.1%} of {ACCOUNT:.0f} EUR a year)")
    yearly = {}
    for t, a, b in zip(months, top_r, spy_r):
        y = yearly.setdefault(t[:4], [1.0, 1.0])
        y[0] *= 1 + a
        y[1] *= 1 + b
    (ROOT / "data" / "candidates_stats.json").write_text(json.dumps({
        "since": months[0], "cagr": stats_cagr(top_r), "basket": stats_cagr(all_r), "spy": stats_cagr(spy_r),
        "fees": statistics.fmean(fee) * per_year, "account": ACCOUNT,
        "worse_years": sum(v[0] < v[1] for v in yearly.values()), "years": len(yearly),
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
