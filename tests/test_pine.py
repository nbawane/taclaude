from niftyta.indicators.core import load_params
from niftyta.pine.generator import generate

P = load_params()


def test_each_script_is_a_v6_strategy_not_an_indicator():
    for key in ("rsi", "ema_cross", "bbands"):
        src, _ = generate(key, "RELIANCE", "1D", P)
        assert src.startswith("//@version=6")
        assert "strategy(" in src and "indicator(" not in src
        assert "process_orders_on_close=false" in src
        assert 'strategy.entry("Long"' in src and 'strategy.close("Long"' in src


def test_parameters_match_config():
    src, _ = generate("rsi", "RELIANCE", "1D", P)
    assert 'input.int(14, "RSI length")' in src
    assert "input.float(30" in src and "input.float(70" in src
    src2, _ = generate("ema_cross", "RELIANCE", "1D", P)
    assert "input.int(9," in src2 and "input.int(21," in src2
    src3, _ = generate("bbands", "RELIANCE", "1D", P)
    assert "input.int(20," in src3 and "input.float(2," in src3


def test_notes_state_it_is_untested_and_list_differences():
    _, notes = generate("bbands", "RELIANCE", "1W", P)
    assert "NOT" in notes or "not" in notes
    assert "Commission" in notes and "Slippage" in notes
