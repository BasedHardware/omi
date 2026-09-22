import pytest
from omi_cli.commands.local import _normalize_sql_result

def test_normalize_sql_table_with_error_prefix_in_column():
    table = (
        "SQL Error: count | total\n"
        "----------------------------------------\n"
        "1 | 2\n\n"
        "1 row(s)"
    )
    result = _normalize_sql_result(table)
    assert result == {
        "columns": ["SQL Error: count", "total"],
        "rows": [{"SQL Error: count": "1", "total": "2"}],
        "row_count": 1,
    }

def test_normalize_sql_table_with_ok_prefix_in_column():
    table = (
        "OK: count | total\n"
        "----------------------------------------\n"
        "1 | 2\n\n"
        "1 row(s)"
    )
    result = _normalize_sql_result(table)
    assert result == {
        "columns": ["OK: count", "total"],
        "rows": [{"OK: count": "1", "total": "2"}],
        "row_count": 1,
    }

def test_normalize_sql_error_message():
    table = "SQL Error: Something went wrong"
    result = _normalize_sql_result(table)
    assert result == {"error": table}

def test_normalize_sql_ok_message():
    table = "OK: All good"
    result = _normalize_sql_result(table)
    assert result == {"ok": True, "message": table}
