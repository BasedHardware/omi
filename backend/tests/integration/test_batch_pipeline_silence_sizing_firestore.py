"""Synthetic projection sizing and mixed-completion transaction guards on loopback Firestore."""

from collections import Counter
import json

import pytest

from database.firestore_document_probe import FIRESTORE_BILLED_READS_BY_CALLER
from tests.integration.test_batch_pipeline_projection_firestore import lane

pytestmark = pytest.mark.integration


def read_counts():
    counts = Counter()
    for family in FIRESTORE_BILLED_READS_BY_CALLER.collect():
        for sample in family.samples:
            if sample.name.endswith('_total'):
                counts[sample.labels['caller']] += sample.value
    return counts


@pytest.mark.parametrize('enabled', ['false', 'true'])
@pytest.mark.parametrize(
    'case,outcomes',
    [
        ('all_silent', ('silence', 'silence')),
        ('mixed_silent_last', ('success', 'silence')),
        ('mixed_speech_last', ('silence', 'success')),
    ],
)
def test_completed_unit_read_sizing_and_no_speculative_mixed_commit(lane, monkeypatch, enabled, case, outcomes):
    monkeypatch.setenv('BATCH_PIPELINE_SILENCE_READ_SKIP_ENABLED', enabled)
    monkeypatch.setenv('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED', 'false')
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    batch = lane.seed(('first', 'last'))
    for index, outcome in enumerate(outcomes):
        lane.finish(batch, index, outcome=outcome)
    upload_before = read_counts()
    assert lane.projector.project(batch.ids[0]) is None
    complete = lane.projector.store.complete
    attempts = []

    def counted(segment, binding, now, accounting, **kwargs):
        attempts.append(accounting is None)
        return complete(segment, binding, now, accounting, **kwargs)

    monkeypatch.setattr(lane.projector.store, 'complete', counted)
    before = read_counts()
    result = lane.projector.project(batch.ids[-1])
    measured = read_counts() - before
    upload_reads = sum((read_counts() - upload_before).values())
    assert result is not None
    assert batch.ledger.get().to_dict()['status'] == 'completed'
    if case.startswith('mixed'):
        assert attempts == [False]
    assert bool(lane.tasks) == case.startswith('mixed')
    print(
        'SILENCE_SIZING '
        + json.dumps(
            {
                'case': case,
                'enabled': enabled,
                'reads': sum(measured.values()),
                'upload_reads': upload_reads,
                'reads_per_unit': upload_reads / len(batch.ids),
                'callers': dict(sorted(measured.items())),
                'zero_speech_attempts': attempts.count(True),
            },
            sort_keys=True,
        )
    )
    attempts.clear()
    before = read_counts()
    assert lane.projector.project(batch.ids[-1]) == result
    measured = read_counts() - before
    if case.startswith('mixed'):
        assert not any(attempts)
    print(
        'SILENCE_REPLAY_SIZING '
        + json.dumps(
            {
                'case': case,
                'enabled': enabled,
                'reads': sum(measured.values()),
                'callers': dict(sorted(measured.items())),
                'zero_speech_attempts': attempts.count(True),
            },
            sort_keys=True,
        )
    )
