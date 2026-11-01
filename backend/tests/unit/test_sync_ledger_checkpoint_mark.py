"""One ledger commit per processed segment must keep the outcomes of checkpoint-then-mark."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

pytest.importorskip('google.cloud.firestore')

from database import sync_ledger  # noqa: E402

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
OWNED = {'status': 'processing', 'job_id': 'job', 'ledger_run_token': 'tok', 'ledger_run_epoch': 3}


class _Transaction:
    def __init__(self):
        self.sets = []

    def set(self, ref, data, merge=False):
        self.sets.append((data, merge))


def _ref(existing):
    snapshot = SimpleNamespace(exists=existing is not None, to_dict=lambda: dict(existing or {}))
    return SimpleNamespace(get=lambda transaction=None: snapshot)


def _run(existing, segment='seg-2'):
    transaction = _Transaction()
    outcome = sync_ledger._checkpoint_and_mark_transaction.to_wrap(
        transaction, _ref(existing), 'job', {'conversation_ids': ['c']}, segment, NOW, 'tok', 3
    )
    return outcome, transaction.sets


def test_owned_new_segment_checkpoints_and_marks_in_one_write():
    outcome, sets = _run({**OWNED, 'processed_segment_ids': ['seg-1']})
    assert outcome == sync_ledger.SEGMENT_MARKED
    assert len(sets) == 1
    data, merge = sets[0]
    assert merge and data['partial_result'] == {'conversation_ids': ['c']} and 'processed_segment_ids' in data


def test_already_processed_segment_still_checkpoints_like_the_separate_calls():
    outcome, sets = _run({**OWNED, 'processed_segment_ids': ['seg-2']})
    assert outcome == sync_ledger.SEGMENT_ALREADY_PROCESSED
    assert [data for data, _ in sets] == [{'partial_result': {'conversation_ids': ['c']}, 'updated_at': NOW}]


@pytest.mark.parametrize(
    'existing',
    [None, {**OWNED, 'job_id': 'other'}, {**OWNED, 'ledger_run_token': 'stale'}, {**OWNED, 'status': 'completed'}],
)
def test_foreign_owner_writes_nothing(existing):
    outcome, sets = _run(existing)
    assert outcome == sync_ledger.SEGMENT_FOREIGN_OWNER
    assert sets == []
