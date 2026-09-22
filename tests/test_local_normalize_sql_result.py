import pytest
from omi_cli.commands.local import _normalize_sql_result

def test_table_with_sql_error_prefix_in_column():
    table = """SQL Error: count | total
----------------------------------------
1 | 2

1 row(s)"""
    result = _normalize_sql_result(table)
    assert result == {
        "columns": ["SQL Error: count", "total"],
        "rows": [{"SQL Error: count": "1", "total": "2"}],
        "row_count": 1,
    }

def test_table_with_ok_prefix_in_column():
    table = """OK: count | total
--------------------
1 | 2

1 row(s)"""
    result = _normalize_sql_result(table)
    assert result == {
        "columns": ["OK: count", "total"],
        "rows": [{"OK: count": "1", "total": "2"}],
        "row_count": 1,
    }

def test_error_status():
    table = "SQL Error: something went wrong\n\n1 row(s)"
    result = _normalize_sql_result(table)
    assert result == {"error": "SQL Error: something went wrong\n\n1 row(s)"}

def test_ok_status():
    table = "OK: operation succeeded\n\n1 row(s)"
    result = _normalize_sql_result(table)
    assert result == {"ok": True, "message": "OK: operation succeeded\n\n1 row(s)"}
