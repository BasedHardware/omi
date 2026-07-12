from datetime import datetime, timezone

import pytest

from database.memory_compatibility_projection import read_v3_compatibility_projection_page
from utils.memory.v3.account_generation_source import (
    V3AccountGenerationFailureReason,
    V3TrustedAccountGenerationReadError,
    read_memory_v3_trusted_account_generation,
)
from utils.memory.v3.projection_reader_contract import (
    V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
    V3_COMPATIBILITY_PROJECTION_SOURCE,
    V3_COMPATIBILITY_PROJECTION_VERSION,
    V3ProjectionFailureReason,
    V3ProjectionReadError,
    V3ProjectionReadRequest,
)


from tests.unit.fake_firestore import FakeDocumentReference as _FakeDocumentRef
from tests.unit.fake_firestore import FakeFirestore as _FakeDb
from tests.unit.fake_firestore import FakeSnapshot as _FakeSnapshot


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


def _projection_state(**overrides):
    data = {
        "schema_version": V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
        "ready": True,
        "uid": "u1",
        "source": V3_COMPATIBILITY_PROJECTION_SOURCE,
        "account_generation": 7,
        "projection_generation": 7,
        "freshness_fence_generation": 7,
        "tombstone_fence_generation": 7,
        "vector_cleanup_fence_generation": 7,
        "source_commit_id": "source-7",
        "source_version": "memory",
        "projection_commit_id": "commit-7",
        "projection_version": V3_COMPATIBILITY_PROJECTION_VERSION,
        "source_evidence_fence": "evidence-7",
        "projection_evidence_fence": "evidence-7",
        "write_convergence_complete": True,
        "delete_convergence_complete": True,
        "tombstone_convergence_complete": True,
        "empty_projection": True,
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


def test_projection_expected_generation_must_come_from_trusted_head_not_control_or_projection_self_compare():
    db = _FakeDb(
        {
            "users/u1/memory_state/head": _head_doc(account_generation=9),
            "users/u1/memory_control/state": {"uid": "u1", "account_generation": 3},
            "users/u1/v3_compatibility_projection/state": _projection_state(
                account_generation=3, projection_generation=9
            ),
        }
    )

    trusted = read_memory_v3_trusted_account_generation(uid="u1", db_client=db)
    assert trusted.account_generation == 9

    with pytest.raises(V3ProjectionReadError) as exc:
        read_v3_compatibility_projection_page(
            db_client=db,
            request=V3ProjectionReadRequest(
                uid="u1",
                limit=10,
                expected_account_generation=trusted.require_account_generation(),
            ),
        )

    assert exc.value.reason == V3ProjectionFailureReason.ACCOUNT_GENERATION_MISMATCH


def test_trusted_head_control_projection_and_cursor_generations_can_be_compared_as_distinct_sources():
    db = _FakeDb(
        {
            "users/u1/memory_state/head": _head_doc(account_generation=7),
            "users/u1/memory_control/state": {"uid": "u1", "account_generation": 7},
            "users/u1/v3_compatibility_projection/state": _projection_state(
                account_generation=7, projection_generation=7
            ),
        }
    )

    trusted = read_memory_v3_trusted_account_generation(uid="u1", db_client=db)
    page = read_v3_compatibility_projection_page(
        db_client=db,
        request=V3ProjectionReadRequest(
            uid="u1",
            limit=10,
            expected_account_generation=trusted.require_account_generation(),
        ),
    )

    assert page.items == []
    assert trusted.account_generation == 7
    assert page.account_generation == 7
    assert "users/u1/memory_control/state" not in db.document_reads[:1]
