"""Read-only access to the Freedom24 (Tradernet) API.

Wraps tradernet-sdk instead of subclassing it, so no order method of the SDK
is reachable from here. Stage 1 of the roadmap only reads data.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any

import requests
from tradernet import Tradernet

CONFIG = os.environ.get("INVBOT_TRADERNET_INI", os.path.expanduser("~/.config/tradernet/tradernet.ini"))

log = logging.getLogger(__name__)

# The SDK logs request headers (public key, signature) at DEBUG level under
# loggers named after its classes. Never let those through.
for _name in ("Tradernet", "Core", "TradernetSymbol", "TradernetWebsocket"):
    logging.getLogger(_name).setLevel(logging.WARNING)


class BrokerError(RuntimeError):
    """The API answered with an error (errMsg) or kept failing."""


class ReadOnlyBroker:
    # Rate limits are not published; stay well below anything reasonable
    MIN_INTERVAL = 1.0   # seconds between requests
    RETRIES = 3
    TIMEOUT = 30         # the SDK default is 300 s

    def __init__(self, config: str = CONFIG) -> None:
        mode = os.stat(config).st_mode & 0o777
        if mode & 0o077:
            raise BrokerError(f"{config} is readable by others ({mode:o}), chmod 600")
        self._api = Tradernet.from_config(config)
        self._api.timeout = self.TIMEOUT
        self._last = 0.0

    def _call(self, cmd: str, params: dict[str, Any] | None = None) -> Any:
        for attempt in range(1, self.RETRIES + 1):
            wait = self._last + self.MIN_INTERVAL - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                result = self._api.authorized_request(cmd, params)
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                if status != 429 and status < 500:
                    raise BrokerError(f"{cmd}: HTTP {status}") from None
                err = f"HTTP {status}"
            except (requests.ConnectionError, requests.Timeout) as e:
                err = type(e).__name__
            else:
                # Errors come back as HTTP 200 with errMsg; the SDK only logs them
                if isinstance(result, dict) and "errMsg" in result:
                    raise BrokerError(f"{cmd}: {result['errMsg']}")
                return result
            if attempt == self.RETRIES:
                raise BrokerError(f"{cmd}: {err}, gave up after {attempt} attempts")
            delay = 2 ** attempt
            log.warning("%s: %s, retry in %d s", cmd, err, delay)
            time.sleep(delay)

    def user_info(self) -> dict[str, Any]:
        return self._call("GetAllUserTexInfo")

    def positions(self) -> dict[str, Any]:
        return self._call("getPositionJson")

    def trades(self, start: str, end: str) -> dict[str, Any]:
        """Executed trades between two dates (YYYY-MM-DD)."""
        return self._call("getTradesHistory", {"beginDate": start, "endDate": end})

    def tariffs(self) -> dict[str, Any]:
        return self._call("GetListTariffs")

    def quotes(self, symbols: list[str]) -> dict[str, Any]:
        return self._call("getStockQuotesJson", {"tickers": ",".join(symbols)})

    def candles(
        self, symbol: str, start: datetime, end: datetime, timeframe: int = 86400
    ) -> dict[str, Any]:
        """Price history; timeframe in seconds (86400 = daily).

        `end` has no default on purpose: the SDK's get_candles defaults it to
        the time its module was imported.
        """
        return self._call(
            "getHloc",
            {
                "id": symbol,
                "count": -1,
                "timeframe": timeframe // 60,
                "date_from": start.strftime("%d.%m.%Y %H:%M"),
                "date_to": end.strftime("%d.%m.%Y %H:%M"),
                "intervalMode": "OpenRay",
            },
        )
