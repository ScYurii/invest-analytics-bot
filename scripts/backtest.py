"""Stage 2: compare simple strategies against buy-and-hold with real fees.

Usage: backtest.py            prints the comparison table
"""
import sqlite3
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from invest_bot.backtest import CASH, Data, cagr, max_drawdown, period, run  # noqa: E402

START = "2007-01-03"         # includes the 2008 crash; needs one year of history before
HALVES = [("2007-01-03", "2016-12-31"), ("2017-01-01", "9999-12-31")]
BUDGETS_EUR = [100, 500, 1000]
EURUSD = 1.15                # assumed constant rate for the budget
RISKY = ["SPY", "QQQ", "GLD", "IEF"]


def cash_asset(d: Data, i: int) -> str:
    return "BIL" if d.px["BIL"][i] is not None else CASH


def buy_hold(symbol):
    return lambda d, i: symbol


def sma_timing(symbol, days=200):
    def strategy(d: Data, i: int) -> str:
        window = d.px[symbol][i - days + 1:i + 1]
        return symbol if d.px[symbol][i] > statistics.fmean(window) else cash_asset(d, i)
    return strategy


def momentum(lookback):
    """Hold the asset with the best total return over `lookback` days, if it beats cash."""
    def strategy(d: Data, i: int) -> str:
        best = max(RISKY, key=lambda s: d.ret(s, i, lookback))
        cash_ret = d.ret("BIL", i, lookback) or 0.0
        return best if d.ret(best, i, lookback) > cash_ret else cash_asset(d, i)
    return strategy


STRATEGIES = [
    ("Buy & hold S&P 500", buy_hold("SPY"), ["monthly"]),
    ("Buy & hold Nasdaq-100", buy_hold("QQQ"), ["monthly"]),
    ("S&P 500 above 200-day avg", sma_timing("SPY"), ["weekly", "monthly"]),
    ("Momentum 6 months", momentum(126), ["weekly", "monthly"]),
    ("Momentum 12 months", momentum(252), ["weekly", "monthly"]),
]


def main() -> None:
    con = sqlite3.connect(ROOT / "data" / "prices.db")
    data = Data(con, ["SPY", "QQQ", "GLD", "IEF", "BIL"])
    print(f"Period {START}..{data.dates[-1]}, fee 2 + 0.02/share per order, "
          f"budget in USD at EURUSD {EURUSD}")
    for budget_eur in BUDGETS_EUR:
        budget = budget_eur * EURUSD
        print(f"\n=== Budget {budget_eur} EUR (${budget:.0f}) ===")
        print(f"{'strategy':27} {'freq':7} {'final $':>8} {'CAGR':>6} {'07-16':>6} {'17-26':>6} "
              f"{'maxDD':>6} {'orders':>6} {'fees $':>7} {'busy':>6} {'no $':>5}")
        for name, strat, freqs in STRATEGIES:
            for freq in freqs:
                r = run(data, strat, freq, budget, START)
                halves = [cagr(*period(r, a, b)) for a, b in HALVES]
                full = (r.equity[-1] / budget) ** (
                    1 / ((len(r.dates) - 1) / 252)) - 1
                print(f"{name:27} {freq:7} {r.equity[-1]:8.0f} {full:6.1%} {halves[0]:6.1%} "
                      f"{halves[1]:6.1%} {max_drawdown(r.equity):6.1%} {r.orders:6d} "
                      f"{r.fees:7.0f} {r.days_invested / len(r.dates):6.0%} {r.unaffordable:5d}")


if __name__ == "__main__":
    main()
