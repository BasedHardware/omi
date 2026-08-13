from datetime import datetime, timezone

import pytest

from utils.memory.v3.account_generation_source import (
    V3AccountGenerationFailureReason,
    V3TrustedAccountGenerationReadError,
    read_memory_v3_trusted_account_generation,
)
from tests.unit.fake_firestore import FakeFirestore as _FakeDb


def _head_doc(**overrides):
    data = {
        "schema_version": 1,
        "uid": "u1",
        "source": "memory_state_head",
        "account_generation": 7,
        "head_commit_id": "head7",
        "commit_sequence": 11,
        "updated_at": datetime.now(timezone.utc),
    }
    data.update(overrides)
    return data


def test_trusted_account_generation_reads_independent_memory_state_head_path():
    db = _FakeDb({"users/u1/memory_state/head": _head_doc(account_generation=8)})

    result = read_memory_v3_trusted_account_generation(uid="u1", db_client=db)

    assert result.account_generation == 8
    assert result.source_path == "users/u1/memory_state/head"
    assert result.head_commit_id == "head7"
    assert result.source == "memory_state_head"
    assert result.read_error_reason is None
    assert db.document_reads == ["users/u1/memory_state/head"]


def test_trusted_account_generation_can_join_the_callers_firestore_transaction():
    db = _FakeDb({"users/u1/memory_state/head": _head_doc(account_generation=8)})
    transaction = object()

    result = read_memory_v3_trusted_account_generation(uid="u1", db_client=db, transaction=transaction)

    assert result.account_generation == 8


@pytest.mark.parametrize(
    "docs, reason",
    [
        ({}, V3AccountGenerationFailureReason.MISSING_STATE_HEAD),
        (
            {"users/u1/memory_state/head": ["not", "a", "dict"]},
            V3AccountGenerationFailureReason.MALFORMED_STATE_HEAD,
        ),
        ({"users/u1/memory_state/head": _head_doc(uid="other")}, V3AccountGenerationFailureReason.UID_MISMATCH),
        (
            {"users/u1/memory_state/head": _head_doc(source="memory_control_state")},
            V3AccountGenerationFailureReason.SOURCE_MISMATCH,
        ),
        (
            {"users/u1/memory_state/head": _head_doc(schema_version=0)},
            V3AccountGenerationFailureReason.UNSUPPORTED_SCHEMA,
        ),
        (
            {"users/u1/memory_state/head": _head_doc(account_generation="7")},
            V3AccountGenerationFailureReason.MALFORMED_ACCOUNT_GENERATION,
        ),
        (
            {"users/u1/memory_state/head": _head_doc(account_generation=-1)},
            V3AccountGenerationFailureReason.MALFORMED_ACCOUNT_GENERATION,
        ),
        (
            {"users/u1/memory_state/head": _head_doc(head_commit_id="")},
            V3AccountGenerationFailureReason.MALFORMED_STATE_HEAD,
        ),
        ({"users/u1/memory_state/head": RuntimeError("boom")}, V3AccountGenerationFailureReason.READ_FAILED),
    ],
)
def test_trusted_account_generation_fails_closed_for_missing_malformed_or_untrusted_head(docs, reason):
    result = read_memory_v3_trusted_account_generation(uid="u1", db_client=_FakeDb(docs))

    assert result.account_generation is None
    assert result.read_error_reason == reason
    with pytest.raises(V3TrustedAccountGenerationReadError) as exc:
        result.require_account_generation()
    assert exc.value.reason == reason
