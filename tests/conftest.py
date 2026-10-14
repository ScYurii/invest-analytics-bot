"""Synthetic price data: no network, no keys, no broker."""
from datetime import date, timedelta

import pytest

from invest_bot import store
from invest_bot.portfolio import Prices


def weekdays(start: date, n: int) -> list[str]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


@pytest.fixture
def make_prices(tmp_path):
    """make_prices({"SPY": [close, ...]}, start=date) -> Prices; close = adj_close."""
    def make(series: dict[str, list[float]], start: date = date(2006, 1, 2)) -> Prices:
        con = store.connect(tmp_path / "prices.db")
        for sym, closes in series.items():
            con.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?)",
                            [(sym, d, c, c, c, c, c, 0) for d, c in zip(weekdays(start, len(closes)), closes)])
        con.commit()
        return Prices(con)
    return make
