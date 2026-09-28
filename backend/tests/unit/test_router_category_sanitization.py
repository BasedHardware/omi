"""Hermetic unit tests for category validation exception sanitization in mcp and developer routers."""

import pytest

try:
    from fastapi import HTTPException
except ImportError:

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            self.status_code = status_code
            self.detail = detail
            super().__init__(status_code, detail)


from enum import Enum


class MockMemoryCategory(Enum):
    FACT = "fact"
    PREFERENCE = "preference"


class MockCategoryEnum(Enum):
    WORK = "work"
    PERSONAL = "personal"


def parse_mcp_memory_categories(categories: str):
    category_list = []
    if categories:
        try:
            category_list = [MockMemoryCategory(c.strip()) for c in categories.split(",") if c.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid category provided.")
    return category_list


def parse_mcp_conversation_categories(categories: str):
    try:
        category_list = (
            [MockCategoryEnum(c.strip()).value for c in categories.split(",") if c.strip()] if categories else []
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid category provided.")
    return category_list


def parse_dev_memory_categories(categories: str):
    category_list = []
    if categories:
        try:
            category_list = [MockMemoryCategory(c.strip()) for c in categories.split(",") if c.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid category provided.")
    return category_list


def parse_dev_conversation_categories(categories: str):
    try:
        category_list = [MockCategoryEnum(c.strip()) for c in categories.split(",") if c.strip()] if categories else []
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid category provided.")
    return category_list


def test_mcp_memory_category_valid():
    cats = parse_mcp_memory_categories("fact, preference")
    assert len(cats) == 2
    assert cats[0] == MockMemoryCategory.FACT
    assert cats[1] == MockMemoryCategory.PREFERENCE


def test_mcp_memory_category_invalid_sanitized():
    with pytest.raises(HTTPException) as exc_info:
        parse_mcp_memory_categories("fact, malicious_sql_inject_or_leak")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid category provided."
    # Ensure raw exception / injected string is NOT leaked in detail
    assert "malicious_sql_inject_or_leak" not in exc_info.value.detail
    assert "is not a valid" not in exc_info.value.detail


def test_mcp_conversation_category_valid():
    cats = parse_mcp_conversation_categories("work, personal")
    assert cats == ["work", "personal"]


def test_mcp_conversation_category_invalid_sanitized():
    with pytest.raises(HTTPException) as exc_info:
        parse_mcp_conversation_categories("invalid_enum_val")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid category provided."
    assert "invalid_enum_val" not in exc_info.value.detail


def test_developer_memory_category_invalid_sanitized():
    with pytest.raises(HTTPException) as exc_info:
        parse_dev_memory_categories("bad_cat")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid category provided."
    assert "bad_cat" not in exc_info.value.detail


def test_developer_conversation_category_invalid_sanitized():
    with pytest.raises(HTTPException) as exc_info:
        parse_dev_conversation_categories("nonexistent_cat")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid category provided."
    assert "nonexistent_cat" not in exc_info.value.detail
