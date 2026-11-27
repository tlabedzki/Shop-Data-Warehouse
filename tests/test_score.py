import pandas as pd

from shop_warehouse import score


def truth(rows):
    return pd.DataFrame(rows, columns=["issue_id", "table_name", "record_key", "column_name", "issue_type",
                                       "dirty_value", "clean_value"])


def dq(rows):
    return pd.DataFrame(rows, columns=["table_name", "record_key", "column_name", "rule", "raw_value", "kept_value",
                                       "action"])


def test_phone_numbers_compare_by_digits():
    assert score.normalize("phone_number", "720 731 397") == score.normalize("phone_number", "+48720731397")
    assert score.normalize("net_purchase_price", "164.20") == score.normalize("net_purchase_price", "164.2")
    assert score.normalize("city", "") is None


def test_every_issue_gets_one_outcome():
    key = truth([
        (1, "customers", "1", "phone_number", "format", "600-100-200", "600 100 200"),
        (2, "customers", "2", "phone_number", "missing", "", "600 100 300"),
        (3, "customers", "3", "city", "typo", "KRAKOW", "Kraków"),
        (4, "order_lines", "9", "order_line_id", "duplicate_row", "9", ""),
        (5, "customers", "5", "age", "outlier", "150", "40"),
    ])
    found = dq([
        ("customers", "1", "phone_number", "format", "600-100-200", "+48600100200", "fixed"),
        ("customers", "2", "phone_number", "missing", None, None, "set to unknown"),
        ("customers", "3", "city", "typo", "KRAKOW", "Krakow", "fixed"),
        ("order_lines", "9", "order_line_id", "duplicate_row", "9", None, "removed copy"),
    ])
    outcomes = score.issue_outcomes(found, key).set_index("issue_id")["outcome"].to_dict()
    assert outcomes == {1: "fixed", 2: "caught", 3: "wrong", 4: "fixed", 5: "missed"}


def test_issue_copied_to_a_second_account_is_not_a_false_alarm():
    key = truth([
        (1, "customers", "200", "customer_id", "duplicate_customer", "200", "100"),
        (2, "customers", "100", "city", "typo", "krakow", "Kraków"),
    ])
    found = dq([
        ("customers", "200", "customer_id", "duplicate_customer", "200", "100", "merged"),
        ("customers", "100", "city", "typo", "krakow", "Kraków", "fixed"),
        ("customers", "200", "city", "typo", "krakow", "Kraków", "fixed"),
        ("customers", "300", "email", "format", "X@example.com", "x@example.com", "fixed"),
    ])
    extra = score.false_alarms(found, key)
    assert extra.set_index("record_key")["is_copy"].to_dict() == {"200": True, "300": False}
