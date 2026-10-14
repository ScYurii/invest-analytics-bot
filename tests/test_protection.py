from invest_bot.protection import check, status_line

DAYS = 252 * 4


def test_calm_market_gives_no_signal(make_prices):
    spy = [100 * 1.0004 ** i for i in range(DAYS)]
    p = check(make_prices({"SPY": spy, "BIL": [100.0] * DAYS}))
    assert not p.fired and p.level == "ok" and p.signals == []
    assert p.gap > 0.02
    assert status_line(p).startswith("🟢")


def test_crash_fires_at_month_end_and_the_rule_helps(make_prices):
    up = [100 * 1.0004 ** i for i in range(DAYS - 150)]
    down = [up[-1] * 0.997 ** i for i in range(1, 151)]        # about −36 %, still falling
    p = check(make_prices({"SPY": up + down, "BIL": [100 + i * 0.01 for i in range(DAYS)]}))
    assert p.fired and p.level == "fired" and p.month_gap < 0
    last = p.signals[-1]
    assert last.back is None                                    # still out of the market
    assert last.verdict == "helped" and last.spy < last.bil
    assert p.worst[1] > p.worst[0]                              # the rule fell less than holding
    assert status_line(p).startswith("🔴")
