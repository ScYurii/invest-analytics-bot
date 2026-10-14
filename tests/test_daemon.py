from datetime import datetime

from invest_bot.daemon import TZ, last_slot


def test_last_slot_is_the_previous_saturday_morning():
    wed = datetime(2026, 10, 14, 12, 0, tzinfo=TZ)
    assert last_slot(wed) == datetime(2026, 10, 10, 9, 0, tzinfo=TZ)


def test_saturday_before_and_after_nine():
    assert last_slot(datetime(2026, 10, 17, 8, 59, tzinfo=TZ)).day == 10
    assert last_slot(datetime(2026, 10, 17, 9, 0, tzinfo=TZ)).day == 17
