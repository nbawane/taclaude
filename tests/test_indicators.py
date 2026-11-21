import numpy as np
import pandas as pd
import pytest

from niftyta.indicators.core import compute_indicators, load_params

PARAMS = load_params()


# --- independent reference implementations (plain numpy loops, no TA-Lib) ---
def ref_sma(x, n):
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        out[i] = x[i - n + 1:i + 1].mean()
    return out


def ref_ema(x, n):  # seeded with the first SMA, as TA-Lib and most charting tools do
    out = np.full(len(x), np.nan)
    k = 2 / (n + 1)
    out[n - 1] = x[:n].mean()
    for i in range(n, len(x)):
        out[i] = x[i] * k + out[i - 1] * (1 - k)
    return out


def ref_rsi(x, n):  # Wilder smoothing
    out = np.full(len(x), np.nan)
    d = np.diff(x)
    gain, loss = np.clip(d, 0, None), np.clip(-d, 0, None)
    ag, al = gain[:n].mean(), loss[:n].mean()
    out[n] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n, len(d)):
        ag = (ag * (n - 1) + gain[i]) / n
        al = (al * (n - 1) + loss[i]) / n
        out[i + 1] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def ref_bb(x, n, k):  # population standard deviation, as TA-Lib uses
    mid = ref_sma(x, n)
    sd = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        sd[i] = x[i - n + 1:i + 1].std()
    return mid + k * sd, mid, mid - k * sd


@pytest.fixture
def series():
    rng = np.random.default_rng(42)
    close = 1000 * np.exp(np.cumsum(rng.normal(0, 0.02, 400)))
    return pd.DataFrame({"close": close}, index=pd.bdate_range("2020-01-01", periods=400))


def test_matches_independent_implementations(series):
    x = series["close"].to_numpy()
    ind = compute_indicators(series, PARAMS)
    np.testing.assert_allclose(ind["rsi_14"], ref_rsi(x, 14), rtol=1e-9, equal_nan=True)
    np.testing.assert_allclose(ind["ema_9"], ref_ema(x, 9), rtol=1e-9, equal_nan=True)
    np.testing.assert_allclose(ind["ema_21"], ref_ema(x, 21), rtol=1e-9, equal_nan=True)
    np.testing.assert_allclose(ind["sma_20"], ref_sma(x, 20), rtol=1e-9, equal_nan=True)
    np.testing.assert_allclose(ind["sma_50"], ref_sma(x, 50), rtol=1e-9, equal_nan=True)
    up, mid, lo = ref_bb(x, 20, 2)
    np.testing.assert_allclose(ind["bb_upper_20_2"], up, rtol=1e-9, equal_nan=True)
    np.testing.assert_allclose(ind["bb_middle_20_2"], mid, rtol=1e-9, equal_nan=True)
    np.testing.assert_allclose(ind["bb_lower_20_2"], lo, rtol=1e-9, equal_nan=True)


def test_warmup_is_nan_not_filled(series):
    ind = compute_indicators(series, PARAMS)
    assert ind["rsi_14"].iloc[:14].isna().all() and ind["rsi_14"].notna().iloc[14]
    assert ind["sma_50"].iloc[:49].isna().all() and ind["sma_50"].notna().iloc[49]


def test_known_values():
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0, 5.0]}, index=pd.bdate_range("2020-01-01", periods=5))
    p = {"rsi": {"period": 2}, "ema_fast": {"period": 2}, "ema_slow": {"period": 3},
         "sma_short": {"period": 5}, "sma_long": {"period": 5}, "bbands": {"period": 5, "std": 2}}
    ind = compute_indicators(df, p)
    assert ind["sma_5"].iloc[-1] == pytest.approx(3.0)
    assert ind["rsi_2"].iloc[-1] == pytest.approx(100.0)  # only gains
    assert ind["bb_middle_5_2"].iloc[-1] == pytest.approx(3.0)
