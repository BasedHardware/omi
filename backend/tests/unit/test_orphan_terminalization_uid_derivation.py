"""Orphan terminalization must derive the uid from the conversation path.

Live defect (PR #24592 review, 2026-11-04, verified at the task tip): the
finalization-jobs copy of the orphan-terminalization transaction called
``_uid_from_conversation_path`` — an underscore-prefixed name that exists
nowhere in the tree — while the shared parser lives in
``database.conversation_finalization_values.uid_from_conversation_path`` and
the recovery copy (``conversation_processing_recovery``) already imports it
correctly. Any recovery-admission call that reaches this terminalization
without an explicit uid — exactly the path the ``uid: str | None = None``
parameter exists for — crashed with ``NameError`` inside the transaction, so
the crash orphan stayed ``processing`` forever and the sweep family burned on
it every window.

Fix: call the shared parser. Pinned here from the transaction outward: the
uid-less derivation, the terminal's fencing, and the deterministic-title
terminal the derived uid feeds (``kept_row_terminal_update``).

Failure-Class: FC-terminal-leaves-kept-row-untitled — a server terminal that
keeps a still-processing row as a visible completed conversation must leave it
titled; the NameError aborted the whole terminal write instead of stamping it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

from database import conversation_finalization_jobs as jobs
from database import conversation_processing_recovery as processing_recovery
from database.conversation_finalization_values import uid_from_conversation_path
from database.conversation_terminal_title import fit_document_limit, kept_row_terminal_update
from utils.firestore_document_size import FIRESTORE_MAX_DOCUMENT_BYTES

_UID = 'uid-1'
_ADMITTED_AT = datetime(2026, 9, 30, 22, 0, 0, tzinfo=timezone.utc)
_FIRST_SENTENCE = 'We picked the venue for Friday.'


class _FakeSnapshot:
    def __init__(self, data: dict[str, Any] | None):
        self.exists = data is not None
        self._data = data or {}

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


class _FakeRef:
    def __init__(self, data: dict[str, Any] | None, *, path: str | None = f'users/{_UID}/conversations/c1'):
        self._data = data
        if path is not None:
            self.path = path

    def get(self, transaction: Any = None) -> _FakeSnapshot:
        return _FakeSnapshot(self._data)


class _FakeTransaction:
    def __init__(self) -> None:
        self.updates: list[tuple[Any, dict[str, Any]]] = []

    def update(self, ref: Any, data: dict[str, Any]) -> None:
        self.updates.append((ref, data))


def _segments(*texts: str) -> list[dict]:
    return [{'text': text, 'speaker': 'SPEAKER_00', 'is_user': False, 'start': 0, 'end': 1} for text in texts]


def _orphan_row(**extra: Any) -> dict[str, Any]:
    return {
        'status': 'processing',
        'processing_admitted_at': _ADMITTED_AT,
        'structured': {'title': '', 'overview': '', 'category': 'other'},
        **extra,
    }


def _run_txn(
    row: dict[str, Any],
    *,
    uid: str | None = None,
    ref: _FakeRef | None = None,
    time_zone_for_uid: Any = None,
) -> tuple[bool, _FakeTransaction, _FakeRef]:
    txn = _FakeTransaction()
    ref = ref if ref is not None else _FakeRef(row)
    completed = jobs._complete_orphan_conversation_txn(
        txn, ref, _ADMITTED_AT, datetime.now(timezone.utc), uid, time_zone_for_uid
    )
    return completed, txn, ref


# ---------------------------------------------------------------------------
# The shared parser's contract (the function the broken call must resolve to).
# ---------------------------------------------------------------------------


def test_relative_conversation_path_yields_the_uid():
    assert uid_from_conversation_path('users/uid-1/conversations/c1') == 'uid-1'


def test_uid_is_returned_verbatim_with_punctuation():
    assert uid_from_conversation_path('users/a.B-c_d:e/conversations/c1') == 'a.B-c_d:e'


def test_project_prefixed_path_is_not_parsed():
    # Firestore DocumentReference.path is always the relative form; the parser
    # deliberately refuses the full resource name rather than guess.
    assert uid_from_conversation_path('projects/p/databases/(default)/documents/users/u/c1/x') is None


def test_empty_path_yields_none():
    assert uid_from_conversation_path('') is None


def test_single_segment_yields_none():
    assert uid_from_conversation_path('users') is None


def test_two_segments_yield_none():
    assert uid_from_conversation_path('users/uid-1') is None


def test_three_segments_yield_none():
    assert uid_from_conversation_path('users/uid-1/conversations') is None


def test_five_segments_yield_none():
    assert uid_from_conversation_path('users/uid-1/conversations/c1/extra') is None


def test_wrong_top_collection_yields_none():
    assert uid_from_conversation_path('chats/uid-1/conversations/c1') is None


def test_wrong_leaf_collection_yields_none():
    assert uid_from_conversation_path('users/uid-1/chats/c1') is None


def test_uppercase_collections_yield_none():
    assert uid_from_conversation_path('USERS/uid-1/conversations/c1') is None


def test_blank_uid_segment_yields_a_falsy_uid():
    # '' is falsy: the terminal's ``if uid:`` treats it exactly like an absent
    # uid, so a blank uid segment stamps no title.
    assert not uid_from_conversation_path('users//conversations/c1')


def test_leading_slash_yields_none():
    assert uid_from_conversation_path('/users/uid-1/conversations/c1') is None


def test_trailing_slash_yields_none():
    assert uid_from_conversation_path('users/uid-1/conversations/c1/') is None


def test_unstripped_whitespace_yields_none():
    assert uid_from_conversation_path(' users/uid-1/conversations/c1') is None


# ---------------------------------------------------------------------------
# The uid-less terminalization: the path that crashed with NameError.
# ---------------------------------------------------------------------------


def test_uidless_txn_derives_the_uid_from_the_ref_path():
    row = _orphan_row(transcript_segments=_segments('', _FIRST_SENTENCE, 'More talk.'))
    completed, txn, ref = _run_txn(row)
    assert completed is True
    assert len(txn.updates) == 1
    payload = txn.updates[0][1]
    assert payload['status'] == 'completed'
    assert payload['structured']['title'] == _FIRST_SENTENCE


def test_uidless_txn_terminal_write_carries_completed_status():
    completed, txn, _ref = _run_txn(_orphan_row())
    assert completed is True
    assert txn.updates[0][1]['status'] == 'completed'


def test_uidless_txn_garbage_path_still_terminalizes_without_title():
    row = _orphan_row()
    ref = _FakeRef(row, path='not/a/conversation-path')
    completed, txn, _ref2 = _run_txn(row, ref=ref)
    assert completed is True
    assert txn.updates[0][1] == {'status': 'completed'}


def test_uidless_txn_project_prefixed_path_terminalizes_status_only():
    ref = _FakeRef(
        _orphan_row(),
        path=f'projects/p/databases/(default)/documents/users/{_UID}/conversations/c1',
    )
    completed, txn, _ref2 = _run_txn(_orphan_row(), ref=ref)
    assert completed is True
    assert txn.updates[0][1] == {'status': 'completed'}


def test_uidless_txn_missing_path_attr_still_terminalizes():
    row = _orphan_row()
    ref = _FakeRef(row)
    del ref.path  # the terminal must tolerate a ref that carries no path at all
    completed, txn, _ref2 = _run_txn(row, ref=ref)
    assert completed is True
    assert txn.updates[0][1]['status'] == 'completed'


def test_explicit_uid_wins_over_path_derivation():
    row = _orphan_row(transcript_segments=_segments(_FIRST_SENTENCE))
    completed, txn, _ref = _run_txn(row, uid=_UID)
    assert completed is True
    payload = txn.updates[0][1]
    assert payload['status'] == 'completed'
    assert payload['structured']['title'] == _FIRST_SENTENCE


# ---------------------------------------------------------------------------
# The terminal's generation/ownership fence (unchanged by the fix, pinned so
# the derivation can never widen what the transaction may close).
# ---------------------------------------------------------------------------


def test_missing_snapshot_is_not_terminalized():
    txn = _FakeTransaction()
    ref = _FakeRef(None)
    completed = jobs._complete_orphan_conversation_txn(txn, ref, _ADMITTED_AT, datetime.now(timezone.utc), None, None)
    assert completed is False
    assert txn.updates == []


def test_wrong_status_is_not_terminalized():
    completed, txn, _ref = _run_txn(_orphan_row(status='completed'))
    assert completed is False
    assert txn.updates == []


def test_discarded_row_is_not_terminalized():
    completed, txn, _ref = _run_txn(_orphan_row(discarded=True))
    assert completed is False
    assert txn.updates == []


def test_deferred_row_is_not_terminalized():
    completed, txn, _ref = _run_txn(_orphan_row(deferred=True))
    assert completed is False
    assert txn.updates == []


def test_durable_owned_row_is_not_terminalized():
    completed, txn, _ref = _run_txn(_orphan_row(finalization_job_id='job-9'))
    assert completed is False
    assert txn.updates == []


def test_generation_mismatch_is_not_terminalized():
    # The fence compares the scanned generation, so a stale expectation CASes out.
    stale_expectation = _ADMITTED_AT + timedelta(minutes=5)
    txn = _FakeTransaction()
    ref = _FakeRef(_orphan_row())
    completed = jobs._complete_orphan_conversation_txn(
        txn, ref, stale_expectation, datetime.now(timezone.utc), None, None
    )
    assert completed is False
    assert txn.updates == []


def test_string_admitted_at_is_not_terminalized():
    row = _orphan_row(processing_admitted_at=_ADMITTED_AT.isoformat())
    completed, txn, _ref = _run_txn(row)
    assert completed is False
    assert txn.updates == []


def test_jobs_and_recovery_txns_agree_on_uidless_derivation():
    row = _orphan_row(transcript_segments=_segments(_FIRST_SENTENCE))
    jobs_txn, recovery_txn = _FakeTransaction(), _FakeTransaction()
    ref = _FakeRef(row)
    now = datetime.now(timezone.utc)
    jobs_completed = jobs._complete_orphan_conversation_txn(jobs_txn, ref, _ADMITTED_AT, now, None, None)
    recovery_completed = processing_recovery._complete_orphan_conversation_txn(
        recovery_txn, ref, _ADMITTED_AT, now, None, None
    )
    assert jobs_completed is True
    assert recovery_completed is True
    assert jobs_txn.updates[0][1]['status'] == recovery_txn.updates[0][1]['status'] == 'completed'


# ---------------------------------------------------------------------------
# The deterministic-title terminal the derived uid feeds.
# ---------------------------------------------------------------------------


def _title_ref(row: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(path=f'users/{_UID}/conversations/c1')


def test_untitled_row_gets_first_sentence_title():
    row = _orphan_row(transcript_segments=_segments('', _FIRST_SENTENCE, 'More talk.'))
    update = kept_row_terminal_update(_UID, row, _title_ref(row), {'status': 'completed'}, None)
    assert update['status'] == 'completed'
    assert update['structured']['title'] == _FIRST_SENTENCE


def test_existing_generated_title_is_untouched():
    row = _orphan_row(
        transcript_segments=_segments(_FIRST_SENTENCE),
        structured={'title': 'Real generated title', 'overview': 'o', 'category': 'other'},
    )
    update = kept_row_terminal_update(_UID, row, _title_ref(row), {'status': 'completed'}, None)
    assert update == {'status': 'completed'}


def test_user_title_override_is_untouched():
    row = _orphan_row(transcript_segments=_segments(_FIRST_SENTENCE), user_title='My own title')
    update = kept_row_terminal_update(_UID, row, _title_ref(row), {'status': 'completed'}, None)
    assert update == {'status': 'completed'}


def test_stored_structured_map_survives_the_title_write():
    row = _orphan_row(
        transcript_segments=_segments(_FIRST_SENTENCE),
        structured={'title': '', 'overview': 'kept overview', 'category': 'meeting'},
    )
    update = kept_row_terminal_update(_UID, row, _title_ref(row), {'status': 'completed'}, None)
    assert update['structured']['overview'] == 'kept overview'
    assert update['structured']['category'] == 'meeting'
    assert update['structured']['title'] == _FIRST_SENTENCE


def test_time_title_for_transcript_free_row_with_zone():
    row = _orphan_row(started_at=_ADMITTED_AT)
    zones: list[str] = []

    def time_zone_for_uid(_uid: str) -> str | None:
        zones.append(_uid)
        return 'America/New_York'

    update = kept_row_terminal_update(_UID, row, _title_ref(row), {'status': 'completed'}, time_zone_for_uid)
    assert update['structured']['title'].startswith('Recording')
    assert zones == [_UID]


def test_undecodable_transcript_degrades_without_raising():
    row = _orphan_row(
        transcript_segments=[b'\x00\x01not-a-transcript'],
        transcript_segments_compressed=False,
        started_at=_ADMITTED_AT,
    )
    update = kept_row_terminal_update(
        _UID, row, _title_ref(row), {'status': 'completed'}, lambda _uid: 'America/New_York'
    )
    assert update['status'] == 'completed'


def test_small_row_merges_title_extras():
    row = _orphan_row(transcript_segments=_segments(_FIRST_SENTENCE))
    update = fit_document_limit(row, _title_ref(row), {'status': 'completed'}, {'structured': {'title': 'x'}})
    assert update == {'status': 'completed', 'structured': {'title': 'x'}}


def test_near_ceiling_row_drops_title_extras():
    row = _orphan_row(blob='x' * FIRESTORE_MAX_DOCUMENT_BYTES)
    update = fit_document_limit(row, _title_ref(row), {'status': 'completed'}, {'structured': {'title': 'x'}})
    assert update == {'status': 'completed'}
