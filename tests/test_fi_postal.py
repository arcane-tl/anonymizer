"""Finnish postal code boundary tests."""

from anonymizer.anonymize.recognizers.fi_postal import find_fi_postals, is_plausible_fi_postal


def test_plausible_range():
    assert is_plausible_fi_postal("02330")
    assert is_plausible_fi_postal("00100")
    assert not is_plausible_fi_postal("00099")
    assert not is_plausible_fi_postal("1234")
    assert not is_plausible_fi_postal("123456")


def test_accept_leading_space_and_trailing_space():
    hits = find_fi_postals("Osoite Testikatu 1, 02330 Espoo.")
    assert [h[2] for h in hits] == ["02330"]


def test_accept_after_colon_no_space():
    hits = find_fi_postals("Postal code:02330")
    assert [h[2] for h in hits] == ["02330"]


def test_accept_after_colon_with_space():
    hits = find_fi_postals("Postinumero: 00100 Helsinki")
    assert [h[2] for h in hits] == ["00100"]


def test_accept_line_start():
    hits = find_fi_postals("02330 Espoo\n00100 Helsinki")
    assert [h[2] for h in hits] == ["02330", "00100"]


def test_accept_trailing_comma():
    assert [h[2] for h in find_fi_postals(" city, 02330, next")] == ["02330"]


def test_reject_mid_digit_run():
    assert find_fi_postals("order 10233099 done") == []
    assert find_fi_postals("id=023301234") == []
    assert find_fi_postals("x902330y") == []
    assert find_fi_postals("call 0401234567") == []


def test_reject_decimal_money_false_positive():
    """Was producing [POSTAL].00 when '.' was allowed as trailing punct."""
    assert find_fi_postals("Amount 12345.00 EUR") == []
    assert find_fi_postals("price=00100.50") == []
    assert find_fi_postals(" 99999.99 ") == []


def test_accept_sentence_period_not_decimal():
    assert [h[2] for h in find_fi_postals("kentässä: 02330.")] == ["02330"]


def test_reject_glued_to_letters():
    assert find_fi_postals("code 02330Espoo") == []


def test_reject_letter_prefix_without_colon():
    assert find_fi_postals("A02330 ") == []
    assert find_fi_postals("ref02330 ") == []
