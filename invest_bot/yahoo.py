"""Daily price history from Yahoo Finance (unofficial chart API).

One request per symbol returns the whole history with dividends and splits.
`close` is adjusted for splits only, `adj_close` for splits and dividends.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import requests

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {"User-Agent": "Mozilla/5.0"}

log = logging.getLogger(__name__)


class YahooError(RuntimeError):
    pass


@dataclass
class History:
    symbol: str
    currency: str
    timezone: str
    bars: list[tuple]       # (date, open, high, low, close, adj_close, volume)
    dividends: list[tuple]  # (date, amount)
    splits: list[tuple]     # (date, numerator, denominator)
    skipped: int            # rows without prices, or today's unfinished bar


def fetch(symbol: str, start: date, retries: int = 3) -> History:
    params = {
        "period1": int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp()),
        "period2": int(time.time()),
        "interval": "1d",
        "events": "div,split",
        "includeAdjustedClose": "true",
    }
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(URL.format(symbol=symbol), params=params, headers=HEADERS, timeout=30)
            if r.status_code == 404:
                raise YahooError(f"{symbol}: unknown symbol")
            r.raise_for_status()
            chart = r.json()["chart"]
            if chart["error"]:
                raise YahooError(f"{symbol}: {chart['error']}")
            return _parse(symbol, chart["result"][0])
        except (requests.RequestException, ValueError) as e:
            if attempt == retries:
                raise YahooError(f"{symbol}: {e}") from None
            log.warning("%s: %s, retry in %d s", symbol, e, 2 ** attempt)
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def _parse(symbol: str, res: dict) -> History:
    meta = res["meta"]
    tz = ZoneInfo(meta["exchangeTimezoneName"])
    day = lambda ts: datetime.fromtimestamp(int(ts), tz).date()  # noqa: E731
    today = datetime.now(tz)

    q = res["indicators"]["quote"][0]
    adj = res["indicators"]["adjclose"][0]["adjclose"]
    bars, skipped = [], 0
    for i, ts in enumerate(res.get("timestamp", [])):
        row = (q["open"][i], q["high"][i], q["low"][i], q["close"][i], adj[i], q["volume"][i])
        d = day(ts)
        # Today's bar is unfinished until well after the close (16:00 New York)
        if None in row[:5] or (d == today.date() and today.hour < 18):
            skipped += 1
            continue
        bars.append((d.isoformat(), *(round(x, 6) for x in row[:5]), row[5] or 0))
    # Currencies trade around the clock and sometimes come with two bars for one
    # date; keep the later one
    bars = list({b[0]: b for b in bars}.values())

    ev = res.get("events", {})
    divs = sorted((day(v["date"]).isoformat(), v["amount"]) for v in ev.get("dividends", {}).values())
    splits = sorted(
        (day(v["date"]).isoformat(), v["numerator"], v["denominator"])
        for v in ev.get("splits", {}).values()
    )
    return History(symbol, meta.get("currency", ""), meta["exchangeTimezoneName"], bars, divs, splits, skipped)
