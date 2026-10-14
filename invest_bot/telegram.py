"""Sending messages to the owner's Telegram chat, and nobody else."""
from __future__ import annotations

import configparser
import html
import os

import requests

CONFIG = os.environ.get("INVBOT_TELEGRAM_INI", os.path.expanduser("~/.config/invest-bot/telegram.ini"))
LIMIT = 4000  # Telegram allows 4096 characters per message


class TelegramError(RuntimeError):
    pass


class Telegram:
    def __init__(self, config: str = CONFIG) -> None:
        if os.stat(config).st_mode & 0o077:
            raise TelegramError(f"{config} is readable by others, chmod 600")
        c = configparser.ConfigParser()
        c.read(config)
        self._api = f"https://api.telegram.org/bot{c['telegram']['token'].strip()}"
        self.chat_id = int(c["telegram"]["chat_id"])

    def _post(self, method: str, http_timeout: int = 30, **data) -> dict:
        try:
            r = requests.post(f"{self._api}/{method}", data=data, timeout=http_timeout)
            result = r.json()
        except (requests.RequestException, ValueError) as e:
            # The URL contains the token: never show the exception text as is
            raise TelegramError(f"{method}: {type(e).__name__}") from None
        if not result.get("ok"):
            raise TelegramError(f"{method}: {result.get('description')}")
        return result["result"]

    def send_text(self, text: str) -> None:
        """Send plain text in a monospace block, split into messages by lines."""
        chunk: list[str] = []
        for line in text.splitlines():
            if sum(len(x) + 1 for x in chunk) + len(line) > LIMIT:
                self._send_pre("\n".join(chunk))
                chunk = []
            chunk.append(line)
        if chunk:
            self._send_pre("\n".join(chunk))

    def send_plain(self, text: str) -> None:
        """A normal message (no monospace), for text written for reading."""
        self._post("sendMessage", chat_id=self.chat_id, text=text[:LIMIT], disable_web_page_preview="true")

    def _send_pre(self, text: str) -> None:
        self._post("sendMessage", chat_id=self.chat_id, parse_mode="HTML",
                   text=f"<pre>{html.escape(text)}</pre>", disable_web_page_preview="true")
