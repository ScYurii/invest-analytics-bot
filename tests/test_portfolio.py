from invest_bot import portfolio


def test_symbols_file(tmp_path):
    f = tmp_path / "symbols.txt"
    f.write_text("# Tradernet  Yahoo\nABC.EU ABC.DE   # Xetra\n\nbad line here\n")
    assert portfolio._load_symbols(f) == {"ABC.EU": "ABC.DE"}
    assert portfolio._load_symbols(tmp_path / "missing.txt") == {}


def test_us_suffix_dropped():
    assert portfolio.yahoo_symbol("AAPL.US") == "AAPL"
