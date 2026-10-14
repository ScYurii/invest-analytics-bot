from invest_bot.candidates import metrics, passes


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
