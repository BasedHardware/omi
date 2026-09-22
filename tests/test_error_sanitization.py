import pytest
from plugins.omi_crossref_app.src.api import (
    search_crossref_works,
    get_crossref_work,
    get_crossref_works_by_author,
)
from plugins.omi_crossref_app.src.types import ChatToolResponse

# Helper to trigger an error by using an invalid DOI
INVALID_DOI = "invalid-doi"

@pytest.mark.asyncio
async def test_search_crossref_works_error_sanitization():
    # Use an obviously invalid query to trigger a 400 error
    response: ChatToolResponse = await search_crossref_works("$$$invalid$$$")
    assert response.error is not None
    # The error should not contain raw stack trace or internal URLs
    assert "stack" not in response.error.lower()
    assert "crossref" not in response.error.lower()  # should be sanitized

@pytest.mark.asyncio
async def test_get_crossref_work_error_sanitization():
    response: ChatToolResponse = await get_crossref_work(INVALID_DOI)
    assert response.error is not None
    assert "stack" not in response.error.lower()
    assert "crossref" not in response.error.lower()

@pytest.mark.asyncio
async def test_get_crossref_works_by_author_error_sanitization():
    # Use an empty author string to trigger a 400 error
    response: ChatToolResponse = await get_crossref_works_by_author("")
    assert response.error is not None
    assert "stack" not in response.error.lower()
    assert "crossref" not in response.error.lower()
