"""Send one plain message to the owner's chat (used by deploy/update.sh).

Usage: python -m invest_bot.notify "text"
"""
import sys

from .telegram import Telegram, TelegramError

if __name__ == "__main__":
    try:
        Telegram().send_plain(" ".join(sys.argv[1:]))
    except (OSError, KeyError, TelegramError) as e:
        sys.exit(f"notify: {e}")
