"""Zero-lost-recordings census (contract (h), soak check 5)."""

from datetime import datetime, timedelta, timezone

import google.cloud.firestore  # noqa: F401  (paid at collection, not inside the CPU-guarded call)
import pytest

from database import sync_ledger  # noqa: F401
from scripts.legacy_dark import drain_census  # noqa: F401
from scripts.legacy_dark import lost_recordings as census
from scripts.parity import soak_check

COMPLETED = {'kind': 'completed'}
HELD = {'kind': 'held'}
SINCE = datetime(2026, 10, 20, 7, 25, 25, tzinfo=timezone.utc)


def _classify(rows, states=None):
    states = states or {}
    return census.classify(
        rows,
        lambda namespace, ids: {s: states.get((namespace, s)) for s in ids},
        valid_completed=lambda result: result == COMPLETED,
        valid_held=lambda result: result == HELD,
    )


def _batch(status, segments, **extra):
    return {
        'status': status,
        'dispatch_protocol': 'batch_v1',
        'batch_pipeline': {'namespace': 'bp', 'segment_ids': list(segments)},
        **extra,
    }


def test_every_accepted_row_is_accounted_by_receipt_hold_or_terminal_units():
    rows = [
        _batch('completed', ['a'], result=COMPLETED),
        {'status': 'held', 'dispatch_protocol': 'stt_cap_hold_v1', 'result': HELD},
        _batch('processing', ['b1', 'b2']),
        _batch('processing', ['c']),
    ]
    states = {('bp', 'b1'): 'committed', ('bp', 'b2'): 'privacy_blocked', ('bp', 'c'): 'quarantined'}
    counts = _classify(rows, states)
    assert counts['accepted_content_ids'] == 4
    assert counts['receipted_or_terminal_content_ids'] == 4
    assert counts['lost_content_ids'] == 0
    assert counts['in_custody'] == 1
    assert counts['legacy_and_batch_content_ids'] == 0


def test_a_unit_still_running_after_the_grace_is_lost_and_named_by_state_only():
    rows = [_batch('processing', ['x1', 'x2']), _batch('completed', ['y'], result={'bad': True})]
    counts = _classify(rows, {('bp', 'x1'): 'committed', ('bp', 'x2'): 'retry'})
    assert counts['lost_content_ids'] == 2
    assert counts['unaccounted_states'] == {'absent': 1, 'retry': 1}


def test_a_legacy_writer_field_on_a_batch_row_is_double_processing():
    rows = [
        _batch('completed', ['a'], result=COMPLETED, ledger_run_token='legacy-run'),
        _batch('completed', ['b'], result=COMPLETED, adopted_legacy_job_id='legacy-1'),
        # Batch projection writes processed_segment_ids itself; it is not legacy evidence.
        _batch('completed', ['c'], result=COMPLETED, processed_segment_ids=['c']),
    ]
    counts = _classify(rows)
    assert counts['legacy_and_batch_content_ids'] == 1
    assert counts['adopted'] == 1


def test_evidence_passes_soak_check_5_when_clean_and_fails_when_lost(monkeypatch):
    clean = {'since': '2026-10-20T07:25:25Z', **_classify([_batch('completed', ['a'], result=COMPLETED)])}
    draining = SINCE.timestamp()
    assert soak_check.check_lost_recordings({'lost_recordings': clean}, draining)['status'] == soak_check.PASS
    lost = {'since': '2026-10-20T07:25:25Z', **_classify([_batch('processing', ['z'])])}
    result = soak_check.check_lost_recordings({'lost_recordings': lost}, draining)
    assert result['status'] == soak_check.FAIL and result['reason'] == 'lost_recordings'


@pytest.mark.parametrize('error', [RuntimeError('index not ready'), ValueError('window_not_yet_closed')])
def test_any_read_failure_fails_closed_to_pending(monkeypatch, error):
    def boom(*args, **kwargs):
        raise error

    monkeypatch.setattr(census, 'take_census', boom)
    evidence = census.build_evidence('staging', SINCE, None, datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc))
    assert 'lost_recordings' not in evidence
    assert evidence['lost_recordings_error'] == type(error).__name__
    result = soak_check.check_lost_recordings(evidence, SINCE.timestamp())
    assert result['status'] == soak_check.PENDING


def test_window_closes_one_grace_before_now(monkeypatch):
    seen = {}

    class Query:
        def __init__(self, filters=()):
            self.filters = filters

        def where(self, filter):
            return Query(self.filters + ((filter.field_path, filter.op_string, filter.value),))

        def stream(self):
            seen['filters'] = self.filters
            return []

    class Client:
        def __init__(self, project, database):
            seen['target'] = (project, database)

        def collection_group(self, name):
            seen['collection'] = name
            return Query()

    import google.cloud.firestore as firestore_module

    monkeypatch.setattr(firestore_module, 'Client', Client)
    now = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)
    result = census.take_census('staging', SINCE, None, now)
    assert seen['target'] == ('based-hardware-dev', 'staging')
    assert seen['collection'] == 'sync_content_ledger'
    assert seen['filters'] == (('created_at', '>=', SINCE), ('created_at', '<=', now - timedelta(hours=1)))
    assert result['accepted_content_ids'] == 0 and result['until'] == '2026-10-20T09:00:00Z'
    with pytest.raises(ValueError):
        census.take_census('staging', now - timedelta(minutes=10), None, now)


def test_the_census_query_has_a_declared_collection_group_index():
    from database.firestore_index_registry import FIELD_INDEX_REQUIREMENTS

    assert any(
        r.collection_group == 'sync_content_ledger'
        and r.field_path == 'created_at'
        and 'ASCENDING' in r.collection_group_modes
        for r in FIELD_INDEX_REQUIREMENTS
    )
