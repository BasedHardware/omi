"""Unit tests for marketplace reviewer UID parsing and validation."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from utils.marketplace_reviewers import (
    is_marketplace_reviewer,
    parse_marketplace_reviewers,
)


def test_parse_marketplace_reviewers_empty_and_none() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert parse_marketplace_reviewers(None) == []
    assert parse_marketplace_reviewers("") == []
    assert parse_marketplace_reviewers("   ") == []


def test_parse_marketplace_reviewers_trims_whitespace_and_drops_empty() -> None:
    raw = "  reviewer-a , reviewer-b  ,  , reviewer-c\n"
    parsed = parse_marketplace_reviewers(raw)
    assert parsed == ["reviewer-a", "reviewer-b", "reviewer-c"]


def test_parse_marketplace_reviewers_preserves_order() -> None:
    raw = "first,second,third"
    assert parse_marketplace_reviewers(raw) == ["first", "second", "third"]


def test_is_marketplace_reviewer_matches_exact_and_padded_uids() -> None:
    raw = " reviewer-1 , reviewer-2 "
    assert is_marketplace_reviewer("reviewer-1", raw=raw) is True
    assert is_marketplace_reviewer(" reviewer-1 ", raw=raw) is True
    assert is_marketplace_reviewer("reviewer-2", raw=raw) is True
    assert is_marketplace_reviewer("reviewer-3", raw=raw) is False


def test_is_marketplace_reviewer_rejects_empty_and_blank() -> None:
    raw = "reviewer-1, reviewer-2"
    assert is_marketplace_reviewer("", raw=raw) is False
    assert is_marketplace_reviewer("   ", raw=raw) is False
    assert is_marketplace_reviewer(None, raw=raw) is False  # type: ignore[arg-type]
