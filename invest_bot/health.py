"""Docker healthcheck: the main loop touched data/heartbeat recently, or a job
is running (data/busy; the loop does not turn while a job runs).

Usage: python -m invest_bot.health   (exit 0: healthy)
"""
import sys
import time

from .daemon import BUSY, HEARTBEAT

MAX_AGE = 600      # seconds; the loop turns every ~70 s, after an error it sleeps 300 s


def healthy(now: float | None = None) -> bool:
    if BUSY.exists():
        return True
    try:
        return (now or time.time()) - HEARTBEAT.stat().st_mtime < MAX_AGE
    except OSError:
        return False


if __name__ == "__main__":
    sys.exit(0 if healthy() else 1)
