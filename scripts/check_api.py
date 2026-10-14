"""Check that the API keys work. Prints no personal data, only flags and counts."""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from invest_bot.broker import BrokerError, ReadOnlyBroker  # noqa: E402

logging.basicConfig(level=logging.WARNING)

try:
    b = ReadOnlyBroker()
    u = b.user_info()["data"]
    ps = b.positions()["result"]["ps"]
    q = b.quotes(["SPY.US"])["result"]["q"][0]
except (BrokerError, KeyError, OSError) as e:
    sys.exit(f"FAIL: {e}")

print(f"keys OK, demo={u.get('f_demo')}, active={u.get('f_active')}")
print(f"accounts: {len(ps['acc'])}, positions: {len(ps['pos'])}")
print(f"SPY.US last {q.get('ltp')} at {q.get('ltt')}")
