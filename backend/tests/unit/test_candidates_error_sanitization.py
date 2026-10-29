"""Hermetic unit tests for error sanitization in the candidates router.

Verifies that:
1. WorkstreamCandidateResolverUnavailableError, generic CandidateStoreError, and
   internal TaskLinkResolverUnavailableError route through _sanitize_candidate_error.
2. Domain validation messages on TaskLinkValidationError remain client-facing for UX compatibility.
3. No store-error reflections remain in _raise_store_error or accept_candidate.
4. Behavioral executions for candidate error paths return sanitized responses.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "***")

import pytest
from fastapi import HTTPException

import database.candidates as candidates_db
from routers import candidates as candidates_router
from utils.task_intelligence.task_links import TaskLinkResolverUnavailableError, TaskLinkValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
CANDIDATES_ROUTER_FILE = BACKEND_DIR / "routers" / "candidates.py"


def test_sanitize_candidate_error_behavior():
    sanitize = getattr(candidates_router, "_sanitize_candidate_error", None)
    assert sanitize is not None, "_sanitize_candidate_error must be implemented in routers.candidates"

    fallback = "Candidate operation could not be completed"

    # 1. Store error returns fallback
    assert sanitize(candidates_db.CandidateStoreError("database query failed with internal schema"), fallback) == fallback

    # 2. Raw traceback filtered to fallback
    assert sanitize(ValueError("Traceback (most recent call last):\n  File 'x.py', line 1\nZeroDivisionError"), fallback) == fallback

    # 3. Empty exception detail falls back cleanly
    assert sanitize(candidates_db.CandidateStoreError(""), fallback) == fallback


def test_no_raw_store_error_leak_in_candidates():
    source = CANDIDATES_ROUTER_FILE.read_text(encoding="utf-8")
    assert "_sanitize_candidate_error" in source

    # Verify _raise_store_error does not contain raw detail=str(exc)
    start = source.index("def _raise_store_error")
    end = source.index("\n\ndef ", start)
    raise_store_error_source = source[start:end]
    assert "detail=str(exc)" not in raise_store_error_source
    assert "_sanitize_candidate_error" in raise_store_error_source


def test_raise_store_error_sanitization():
    _raise_store_error = getattr(candidates_router, "_raise_store_error", None)
    assert _raise_store_error is not None

    # 1. NotFound preserves 404
    with pytest.raises(HTTPException) as ctx:
        _raise_store_error(candidates_db.CandidateNotFoundError("not found"))
    assert ctx.value.status_code == 404
    assert ctx.value.detail == "Candidate or task not found"

    # 2. GenerationMismatch preserves 409
    with pytest.raises(HTTPException) as ctx:
        _raise_store_error(candidates_db.CandidateGenerationMismatchError("mismatch"))
    assert ctx.value.status_code == 409
    assert ctx.value.detail == "Account generation mismatch"

    # 3. Workstream resolver unavailable sanitizes to clean detail
    with pytest.raises(HTTPException) as ctx:
        _raise_store_error(
            candidates_db.WorkstreamCandidateResolverUnavailableError("resolver socket timeout: port 9000")
        )
    assert ctx.value.status_code == 409
    assert ctx.value.detail == "Workstream candidate resolver is temporarily unavailable"

    # 4. Generic CandidateStoreError sanitizes to clean detail
    with pytest.raises(HTTPException) as ctx:
        _raise_store_error(candidates_db.CandidateStoreError("unhandled internal postgres table lock"))
    assert ctx.value.status_code == 409
    assert ctx.value.detail == "Candidate operation could not be completed"


def test_accept_candidate_store_error_sanitization():
    accept_candidate = candidates_router.accept_candidate

    with patch.object(candidates_router, "_require_candidate_write_control"), patch.object(
        candidates_router.candidate_service,
        "accept_candidate",
        side_effect=candidates_db.CandidateStoreError("internal firestore index conflict"),
    ):
        with pytest.raises(HTTPException) as ctx:
            accept_candidate(candidate_id="c-1", account_generation=1, uid="u-1")
        assert ctx.value.status_code == 409
        assert ctx.value.detail == "Candidate operation could not be completed"


def test_accept_candidate_task_link_error_handling():
    accept_candidate = candidates_router.accept_candidate

    # 1. Internal resolver unavailable is sanitized
    with patch.object(candidates_router, "_require_candidate_write_control"), patch.object(
        candidates_router.candidate_service,
        "accept_candidate",
        side_effect=TaskLinkResolverUnavailableError("Ticket 04 workstream goal resolver is not registered"),
    ):
        with pytest.raises(HTTPException) as ctx:
            accept_candidate(candidate_id="c-1", account_generation=1, uid="u-1")
        assert ctx.value.status_code == 409
        assert ctx.value.detail == "Task link resolver is temporarily unavailable"

    # 2. Client-facing domain validation message is preserved
    with patch.object(candidates_router, "_require_candidate_write_control"), patch.object(
        candidates_router.candidate_service,
        "accept_candidate",
        side_effect=TaskLinkValidationError("workstream and goal do not match"),
    ):
        with pytest.raises(HTTPException) as ctx:
            accept_candidate(candidate_id="c-1", account_generation=1, uid="u-1")
        assert ctx.value.status_code == 409
        assert ctx.value.detail == "workstream and goal do not match"
