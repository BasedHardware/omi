"""`probe_canonical_graph_state` answers three things, not two.

Callers that destroy the pre-canonical store need the difference between "this
account has no canonical state" and "we could not find out". The trusted head
read collapses every exception into `READ_FAILED`, so a Firestore timeout looks
identical to an absent document unless the reason is inspected by value.
"""

from __future__ import annotations

from typing import Any

import pytest

from utils.memory import canonical_graph as kg
from utils.memory.v3.account_generation_source import (
    V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION,
    V3_TRUSTED_ACCOUNT_GENERATION_SOURCE,
    V3AccountGenerationFailureReason as Reason,
    V3TrustedAccountGenerationResult as TrustedHead,
)

UID = "uid-probe"
HEAD_PATH = f"users/{UID}/memory_state/head"


def _head(monkeypatch, result: TrustedHead) -> None:
    monkeypatch.setattr(kg, "read_memory_v3_trusted_account_generation", lambda **_kw: result)


@pytest.fixture(autouse=True)
def _no_firestore(monkeypatch):
    monkeypatch.setattr(kg, "get_firestore_client", lambda: object())


def test_a_committed_head_is_established(monkeypatch):
    _head(
        monkeypatch,
        TrustedHead(
            uid=UID,
            source_path=HEAD_PATH,
            account_generation=2,
            head_commit_id="commit-1",
            commit_sequence=5,
            source=V3_TRUSTED_ACCOUNT_GENERATION_SOURCE,
            schema_version=V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION,
        ),
    )

    assert kg.probe_canonical_graph_state(UID) is kg.CanonicalGraphState.ESTABLISHED


def test_an_absent_head_is_the_only_unestablished_answer(monkeypatch):
    _head(monkeypatch, TrustedHead(uid=UID, source_path=HEAD_PATH, read_error_reason=Reason.MISSING_STATE_HEAD))

    assert kg.probe_canonical_graph_state(UID) is kg.CanonicalGraphState.UNESTABLISHED


@pytest.mark.parametrize(
    "reason",
    [
        Reason.READ_FAILED,
        Reason.MALFORMED_STATE_HEAD,
        Reason.UNSUPPORTED_SCHEMA,
        Reason.UID_MISMATCH,
        Reason.SOURCE_MISMATCH,
        Reason.MALFORMED_ACCOUNT_GENERATION,
    ],
    ids=lambda reason: reason.value,
)
def test_every_other_failure_reason_is_indeterminate(monkeypatch, reason):
    _head(monkeypatch, TrustedHead(uid=UID, source_path=HEAD_PATH, read_error_reason=reason))

    assert kg.probe_canonical_graph_state(UID) is kg.CanonicalGraphState.INDETERMINATE


def test_a_head_without_a_usable_revision_fence_is_indeterminate(monkeypatch):
    _head(
        monkeypatch,
        TrustedHead(uid=UID, source_path=HEAD_PATH, account_generation=2, head_commit_id="", commit_sequence=5),
    )

    assert kg.probe_canonical_graph_state(UID) is kg.CanonicalGraphState.INDETERMINATE


def test_a_thrown_head_read_is_classified_as_read_failed_not_absent(monkeypatch):
    """The probe's boundary is the real reader, not a hand-written enum value.

    `read_memory_v3_trusted_account_generation` swallows every head-get
    exception. Drive it with a client that raises so the probe is exercised
    against the classification production actually produces.
    """

    class _Exploding:
        def document(self, _path: str) -> Any:
            raise TimeoutError("firestore deadline exceeded")

    assert kg.probe_canonical_graph_state(UID, db_client=_Exploding()) is kg.CanonicalGraphState.INDETERMINATE


def test_the_probe_needs_no_cursor_secret_and_no_atlas_query(monkeypatch):
    """The probe reads one document; it must not depend on paging machinery.

    The previous implementation materialized a whole canonical page just to
    answer a boolean, which made the answer depend on `MEMORY_V3_CURSOR_SECRET`
    and on the atlas composite index being present.
    """
    monkeypatch.delenv("MEMORY_V3_CURSOR_SECRET", raising=False)

    def _must_not_page(*_args: Any, **_kwargs: Any):  # pragma: no cover - asserts absence
        raise AssertionError("the state probe paged the canonical atlas")

    monkeypatch.setattr(kg, "get_canonical_knowledge_graph", _must_not_page)
    monkeypatch.setattr(kg, "_read_canonical_graph_page_once", _must_not_page)

    reads: list[str] = []

    class _Head:
        exists = True

        def to_dict(self) -> dict[str, Any]:
            return {
                "schema_version": V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION,
                "uid": UID,
                "source": V3_TRUSTED_ACCOUNT_GENERATION_SOURCE,
                "account_generation": 2,
                "head_commit_id": "commit-1",
                "commit_sequence": 5,
            }

    class _Doc:
        def get(self, **_kw: Any) -> _Head:
            return _Head()

    class _Client:
        def document(self, path: str) -> _Doc:
            reads.append(path)
            return _Doc()

        def collection(self, *_args: Any, **_kwargs: Any):  # pragma: no cover - asserts absence
            raise AssertionError("the state probe ran a collection query")

    assert kg.probe_canonical_graph_state(UID, db_client=_Client()) is kg.CanonicalGraphState.ESTABLISHED
    assert reads == [HEAD_PATH]
