from utils.retrieval.tools.result_bounds import cap_items_for_llm, bounded_result, MAX_RESULT_CHARS


def test_cap_items_normal():
    items = [1, 2, 3, 4, 5]
    capped, total, truncated = cap_items_for_llm(items, 3)
    assert capped == [1, 2, 3]
    assert total == 5
    assert truncated is True


def test_cap_items_not_truncated():
    items = [1, 2]
    capped, total, truncated = cap_items_for_llm(items, 5)
    assert capped == [1, 2]
    assert total == 2
    assert truncated is False


def test_cap_items_none_items():
    capped, total, truncated = cap_items_for_llm(None, 5)
    assert capped == []
    assert total == 0
    assert truncated is False


def test_cap_items_negative_limit():
    items = [1, 2, 3]
    capped, total, truncated = cap_items_for_llm(items, -1)
    assert capped == []
    assert total == 3
    assert truncated is True


def test_cap_items_string_limit_coercion():
    items = [1, 2, 3, 4]
    capped, total, truncated = cap_items_for_llm(items, "2")
    assert capped == [1, 2]
    assert total == 4
    assert truncated is True


def test_cap_items_invalid_limit():
    items = [1, 2, 3]
    capped, total, truncated = cap_items_for_llm(items, "invalid")
    assert capped == []
    assert total == 3
    assert truncated is True


def test_bounded_result_none_input():
    res = bounded_result(None, False)
    assert res == ""


def test_bounded_result_none_input_with_truncation():
    res = bounded_result(None, True, noun="records", shown=0)
    assert "records" in res
    assert "omitted data is not evidence of absence" in res


def test_bounded_result_exceeds_max_chars():
    huge_str = "A" * (MAX_RESULT_CHARS + 500)
    res = bounded_result(huge_str, False)
    assert len(res) > MAX_RESULT_CHARS
    assert "more were omitted" in res or "more may exist" in res


def test_bounded_result_custom_order_and_shown():
    res = bounded_result("Line 1\nLine 2", True, noun="items", order="newest first", shown=2)
    assert "Rows are ordered newest first" in res
    assert "2 items" in res
