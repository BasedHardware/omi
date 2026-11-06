"""Retained projection expiry and nightly target-only release contracts."""

from copy import deepcopy
from unittest.mock import Mock

import pytest

from config.batch_pipeline import HELD_DEAD_LETTER_SECONDS
from utils.batch_pipeline import held_dead_letter as held_sweep
from database.batch_pipeline_projection_release import ProjectionReleaseStore, expired_page_ids
from tests.unit.test_batch_pipeline_projection_release import rows, store_for, OWNER, TARGET

RESULT = ('batch_pipeline_prod_results', 'held')
JOB = ('batch_pipeline_prod_jobs', 'held')
CONVERSATION = ('users', OWNER, 'conversations', TARGET)


@pytest.fixture(autouse=True)
def runtime(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'true')


def test_expiry_preserves_payload_receipt_job_and_watermark_and_is_idempotent():
    seeded = rows(discarded=True, held_deadline_at=100, payload={'words': [{'word': 'retained'}]})
    before = deepcopy(seeded)
    client, store = store_for(seeded)
    release = ProjectionReleaseStore(store)
    assert not release.release('held', 101)
    assert release.expired
    expected = {
        **before[RESULT],
        'held_expired_reason': 'held_expired',
        'held_expired_at': 101,
    }
    assert client.rows == {**before, RESULT: expected}
    assert not release.release('held', 102)
    assert not release.expired
    assert client.rows[RESULT] == expected


def test_old_rows_receive_a_full_window_and_malformed_deadlines_never_expire():
    client, store = store_for(rows(discarded=True))
    assert not ProjectionReleaseStore(store).release('held', 100)
    assert client.rows[RESULT]['held_deadline_at'] == 100 + HELD_DEAD_LETTER_SECONDS
    for value in (True, '1', float('nan'), float('inf')):
        client, store = store_for(rows(discarded=True, held_deadline_at=value))
        assert not ProjectionReleaseStore(store).release('held', 100)
        assert client.rows[RESULT]['projection_state'] == 'quarantine_held'
        assert not client.transactions[-1].updates


@pytest.mark.parametrize('blocked', ['privacy', 'operator', 'persisted', 'wrong-reason', 'wrong-owner'])
def test_expiry_never_bypasses_original_eligibility(blocked):
    seeded = rows(discarded=True, held_deadline_at=1)
    if blocked == 'privacy':
        seeded[RESULT]['projection_privacy_refusal'] = True
    elif blocked == 'operator':
        seeded[JOB]['speech_redrive'] = {'state': 'pending'}
    elif blocked == 'persisted':
        seeded[RESULT]['projection_state'] = 'persisted'
    elif blocked == 'wrong-reason':
        seeded[RESULT]['projection']['disposition'] = 'privacy_blocked'
    elif blocked == 'wrong-owner':
        seeded[RESULT]['owner_key'] = 'someone-else'
    client, store = store_for(seeded)
    assert not ProjectionReleaseStore(store).release('held', 100)
    assert client.rows == seeded


def test_flag_off_old_held_behavior_is_byte_identical(monkeypatch):
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')
    for extra in ({}, {'held_deadline_at': 1}):
        seeded = rows(discarded=True, **extra)
        client, store = store_for(seeded)
        assert not ProjectionReleaseStore(store).release('held', 100)
        assert client.rows == seeded
        assert not client.transactions[-1].updates


@pytest.mark.parametrize('target', ['missing', 'discarded', 'deleted', 'processing', 'byok', 'custody', 'restored'])
def test_expired_redrive_requires_restorable_target_even_with_flag_off(monkeypatch, target):
    seeded = rows(held_deadline_at=1)
    client, store = store_for(seeded)
    client.rows[CONVERSATION]['discarded'] = True
    assert not ProjectionReleaseStore(store).release('held', 2)
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')
    client.rows[CONVERSATION].pop('discarded')
    if target == 'missing':
        client.rows.pop(CONVERSATION)
    elif target in ('discarded', 'deleted'):
        client.rows[CONVERSATION][target] = True
    elif target == 'processing':
        client.rows[CONVERSATION]['status'] = 'processing'
    elif target == 'byok':
        client.rows[CONVERSATION]['uses_custom_stt'] = True
    elif target == 'custody':
        client.rows[CONVERSATION]['data_protection_level'] = 'e2ee'
    before = deepcopy(client.rows)
    release = ProjectionReleaseStore(store)
    assert release.release('held', 86401, dead_before=86400) is (target == 'restored')
    if target != 'restored':
        assert client.rows == before
    else:
        assert client.rows[RESULT]['projection_state'] == 'pending'
        assert client.rows[RESULT]['projection_release_attempts'] == 1
        assert client.rows[JOB]['audio_uri'] == seeded[JOB]['audio_uri']
        assert not release.release('held', 86402, dead_before=86400)


def test_restorable_held_releases_instead_of_expiring():
    client, store = store_for(rows(held_deadline_at=1))
    release = ProjectionReleaseStore(store)
    assert release.release('held', 100)
    assert not release.expired
    assert client.rows[RESULT]['projection_state'] == 'pending'


def test_expired_rechecks_previous_day_cutoff_and_does_not_hot_loop():
    client, store = store_for(rows(held_expired_at=100, held_deadline_at=1, held_expired_reason='held_expired'))
    release = ProjectionReleaseStore(store)
    assert not release.release('held', 101, dead_before=100)
    assert not client.transactions[-1].updates
    assert release.release('held', 101, dead_before=101)


def test_expired_page_is_bounded_and_keyset():
    query = Mock()
    for method in ('where', 'order_by', 'start_after', 'limit'):
        getattr(query, method).return_value = query
    query.stream.return_value = []
    client = Mock()
    client.collection.return_value = query
    assert expired_page_ids(client, 'ns', 10000, 'after') == []
    assert [call.args for call in query.where.call_args_list] == [
        ('projection_state', '==', 'quarantine_held'),
        ('held_expired_reason', '==', 'held_expired'),
    ]
    query.limit.assert_called_once_with(128)
    query.order_by.assert_called_once_with('__name__')
    query.start_after.assert_called_once_with({'__name__': query.document.return_value})


def test_nightly_cursor_survives_restart_continues_full_pages_and_sleeps(monkeypatch):
    from database import batch_pipeline_projection_release as release_module
    from utils.batch_pipeline.held_dead_letter import ProjectionHeldDeadLetter, INTERVAL_SECONDS

    client, projection = store_for(rows())
    store = projection.store
    seen = []
    order = [f'row-{i:02}' for i in range(35)]

    def page(_client, _namespace, limit, after):
        start = order.index(after) + 1 if after else 0
        return order[start : start + limit]

    monkeypatch.setattr(held_sweep, 'expired_page_ids', page)

    def redrive(_self, sid, now, *, dead_before):
        seen.append((sid, dead_before))
        if sid == 'row-00':
            raise ValueError('synthetic poison')
        return True

    monkeypatch.setattr(release_module.ProjectionReleaseStore, 'release', redrive)
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')
    assert ProjectionHeldDeadLetter(store).tick(86401) == 31
    assert ProjectionHeldDeadLetter(store).tick(86402) == 0
    assert ProjectionHeldDeadLetter(store).tick(86401 + INTERVAL_SECONDS) == 3
    assert ProjectionHeldDeadLetter(store).tick(86401 + 2 * INTERVAL_SECONDS) == 0
    assert [sid for sid, _ in seen] == order
    assert {cutoff for _, cutoff in seen} == {86400}
    assert ProjectionHeldDeadLetter(store).tick(172801) == 31


def test_nightly_time_budget_checkpoints_last_examined_row(monkeypatch):
    from database import batch_pipeline_projection_release as release_module
    from utils.batch_pipeline import held_dead_letter as sweep

    _, projection = store_for(rows())
    store = projection.store
    clock = [0.0]
    monkeypatch.setattr(sweep.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(held_sweep, 'expired_page_ids', lambda *args: ['one', 'two', 'three'])

    def slow_release(*args, **kwargs):
        clock[0] += 3
        return True

    monkeypatch.setattr(release_module.ProjectionReleaseStore, 'release', slow_release)
    assert sweep.ProjectionHeldDeadLetter(store).tick(86401) == 2
    cursor = store.run(lambda tx: tx.get('leases', sweep.ProjectionHeldDeadLetter.CURSOR))
    assert cursor['after_id'] == 'two' and not cursor['redrive_done']


def test_flag_off_restored_hold_preserves_legacy_metadata(monkeypatch):
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')
    client, store = store_for(rows(held_deadline_at=1))
    assert ProjectionReleaseStore(store).release('held', 100)
    assert client.rows[RESULT]['held_deadline_at'] == 1


def test_expired_stock_is_visible_but_not_a_runnable_projection():
    from tests.unit.test_batch_pipeline_timeliness import _sample, EPOCH, NOW
    from database.batch_pipeline_store import PROJECTION_OBLIGATION_STATES

    sample = _sample(
        results=[
            {'projection_state': 'quarantine_held', 'held_expired_reason': 'held_expired', 'committed_at': EPOCH + 100}
        ]
    )
    assert sample['new_over_sla']['held_expired_rows'] == 1
    assert sample['held_oldest']['held_expired'] == EPOCH + 100
    assert sample['new_oldest']['held_expired_rows'] == EPOCH + 100
    assert sample['drain_oldest'] is None
    assert 'quarantine_held' in PROJECTION_OBLIGATION_STATES
    assert 'held_expired' not in PROJECTION_OBLIGATION_STATES


def test_unfinished_nightly_pass_keeps_cursor_across_midnight(monkeypatch):
    from database import batch_pipeline_projection_release as release_module
    from utils.batch_pipeline.held_dead_letter import ProjectionHeldDeadLetter

    _, projection = store_for(rows())
    seen = []

    def page(_client, _namespace, limit, after):
        seen.append(after)
        return [f'blocked-{i}' for i in range(32)] if after is None else ['restored-tail']

    monkeypatch.setattr(held_sweep, 'expired_page_ids', page)
    monkeypatch.setattr(release_module.ProjectionReleaseStore, 'release', lambda *a, **kw: a[1] == 'restored-tail')
    assert ProjectionHeldDeadLetter(projection.store).tick(172790) == 0
    assert ProjectionHeldDeadLetter(projection.store).tick(173090) == 1
    assert seen == [None, 'blocked-31']


@pytest.mark.parametrize('attempts', [0, 2, 3])
def test_expired_row_remains_releasable_by_unchanged_pre_change_code(monkeypatch, attempts):
    from tests.unit.fixtures.legacy_projection_release import ProjectionReleaseStore as LegacyReleaseStore

    seeded = rows(
        discarded=True, held_deadline_at=1, projection_release_attempts=attempts, payload={'transcript': 'retained'}
    )
    client, store = store_for(seeded)
    assert not ProjectionReleaseStore(store).release('held', 2)
    expired = deepcopy(client.rows[RESULT])
    assert expired['projection_state'] == 'quarantine_held'
    assert expired['held_expired_reason'] == 'held_expired'
    if attempts == 3:
        assert expired['held_expired_release_attempts'] == 3
        assert expired['projection_release_attempts'] == 0
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')
    assert not LegacyReleaseStore(store).release('held', 3)
    assert client.rows[RESULT] == expired
    client.rows[CONVERSATION]['discarded'] = False
    assert LegacyReleaseStore(store).release('held', 4)
    assert client.rows[RESULT]['projection_state'] == 'pending'
    assert client.rows[RESULT]['payload'] == seeded[RESULT]['payload']
    assert not LegacyReleaseStore(store).release('held', 5)
