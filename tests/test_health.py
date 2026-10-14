import os
import time

from invest_bot import health


def test_health(tmp_path, monkeypatch):
    beat, busy = tmp_path / "heartbeat", tmp_path / "busy"
    monkeypatch.setattr(health, "HEARTBEAT", beat)
    monkeypatch.setattr(health, "BUSY", busy)
    assert not health.healthy()                     # never started
    beat.touch()
    assert health.healthy()
    old = time.time() - health.MAX_AGE - 1
    os.utime(beat, (old, old))
    assert not health.healthy()                     # the loop is stuck
    busy.write_text("weekly")
    assert health.healthy()                         # a long job is running
