import pytest

from niftyta.data.ca_parse import classify


def test_bonus_one_for_one_halves_the_price():
    kind, factor, _ = classify(" Bonus 1:1")
    assert kind == "bonus" and factor == pytest.approx(0.5)


def test_bonus_two_for_one_is_a_third():
    assert classify("Bonus 2:1")[1] == pytest.approx(1 / 3)


def test_face_value_split_uses_new_over_old():
    kind, factor, _ = classify("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share")
    assert kind == "split" and factor == pytest.approx(0.2)


@pytest.mark.parametrize("text,kind", [
    (" Dividend - Rs 6.50  Per Share", "dividend"),
    (" Rights 1:15 @ Premium Rs 1247", "rights"),
    ("Demerger", "demerger"),
    ("Annual General Meeting", "other"),
])
def test_events_without_a_defined_price_effect_are_not_applied(text, kind):
    k, factor, note = classify(text)
    assert k == kind and factor is None
    assert "not applied" in note
