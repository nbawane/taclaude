import pandas as pd
import pytest

from niftyta.analysis.monthly import (by_calendar_month, expected_by_chance, month_outlook, monthly_moves, movers,
                                      overall)


def daily(rows):
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close"])
    return df.assign(date=pd.to_datetime(df.date)).set_index("date")


DATA = daily([("2024-01-31", 100, 101, 99, 100), ("2024-02-01", 101, 112, 95, 104), ("2024-02-29", 105, 111, 104, 110),
              ("2024-03-28", 110, 111, 98, 99), ("2024-05-31", 99, 100, 98, 99), ("2024-06-10", 99, 105, 99, 104)])


def test_moves_are_measured_from_the_previous_month_close():
    m = monthly_moves(DATA, pd.Timestamp("2024-06-11")).set_index("month")
    feb = m.loc[2]
    assert feb.return_pct == pytest.approx(10) and feb.up_pct == pytest.approx(12)
    assert feb.down_pct == pytest.approx(-5) and feb.range_pct == pytest.approx(17) and feb.days == 2
    assert m.loc[3].return_pct == pytest.approx(-10)


def test_first_month_and_months_after_a_gap_are_left_out():
    assert list(monthly_moves(DATA, pd.Timestamp("2024-06-11")).month) == [2, 3, 6]   # no April before May


def test_unfinished_month_is_marked_and_not_summarised():
    m = monthly_moves(DATA, pd.Timestamp("2024-06-11"))
    assert list(m.complete) == [True, True, False]
    s = by_calendar_month(m).set_index("month_name")
    assert s.loc["Feb", "avg_return"] == pytest.approx(10) and s.loc["Feb", "times_up"] == 100
    assert pd.isna(s.loc["Jun", "avg_return"]) and len(s) == 12
    assert overall(m)["months"] == 2 and overall(m)["times_up"] == 50


def test_month_cut_short_by_old_data_is_not_complete():
    m = monthly_moves(DATA.iloc[:3].iloc[:2], pd.Timestamp("2024-06-11"))   # data stops on 1 February
    assert not m.complete.any()


def seasonal(symbol, returns, rng=5.0):
    return pd.DataFrame({"symbol": symbol, "year": range(2016, 2016 + len(returns)), "month": 12,
                         "return_pct": returns, "up_pct": 3.0, "down_pct": -2.0, "range_pct": rng, "complete": True})


def test_outlook_ranks_by_how_often_and_ignores_short_or_unfinished_history():
    unfinished = seasonal("A", [50.0]).assign(year=2030, complete=False)
    moves = pd.concat([seasonal("A", [1.0] * 9 + [-1]), seasonal("B", [-2.0] * 8 + [1, 1], rng=9),
                       seasonal("C", [1.0, -1] * 5), seasonal("D", [1.0] * 3), unfinished])
    o = month_outlook(moves, 12, min_years=8)
    assert sorted(o.symbol) == ["A", "B", "C"] and o.set_index("symbol").loc["A", "years"] == 10
    lists = movers(o, often=70)
    assert list(lists["rise"].symbol) == ["A"] and list(lists["fall"].symbol) == ["B"]
    assert lists["swing"].symbol.iloc[0] == "B"


def test_expected_by_chance_for_a_fair_coin():
    rise, fall = expected_by_chance(pd.DataFrame({"years": [10] * 1024}), 0.5, often=80)
    assert rise == pytest.approx(56) and fall == pytest.approx(56)   # C(10, 8) + C(10, 9) + C(10, 10) = 56
