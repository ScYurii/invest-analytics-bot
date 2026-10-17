from invest_bot.candidates import metrics, passes, screen


def test_metrics_skip_the_last_month():
    n = 300
    adj = [100.0] * (n - 21) + [200.0] * 21          # the jump is in the last month only
    m = metrics([str(i) for i in range(n)], adj, adj, n - 1, "X")
    assert m.mom == 0                               # 12-1 momentum ignores it
    assert m.above and m.r1m == 1.0                 # but the last month shows it


def test_too_short_history():
    assert metrics(["d"] * 100, [1.0] * 100, [1.0] * 100, 99, "X") is None


def test_passes_needs_trend_and_strength():
    adj = [100 * 1.001 ** i for i in range(300)]
    m = metrics([str(i) for i in range(300)], adj, adj, 299, "X")
    assert passes(m, spy_mom=0.1) and not passes(m, spy_mom=0.5)


def test_screen_uses_the_day_members_share(make_prices):
    """SPY refreshed daily, members weekly: the screen must not call them all stale."""
    n = 300
    up = [100 * 1.002 ** i for i in range(n)]
    px = make_prices({"SPY": [100 * 1.0005 ** i for i in range(n + 3)],   # 3 days newer
                      "AAA": up, "BBB": up})
    members = [{"symbol": "AAA"}, {"symbol": "BBB"}]
    picks, _ = screen(px, members)
    assert [m.symbol for m in picks] == ["AAA", "BBB"]
    assert picks[0].date == px.series("AAA")[0][-1]      # the members' day, not SPY's
