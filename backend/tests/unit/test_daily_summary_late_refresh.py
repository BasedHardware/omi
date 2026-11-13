"""Late-input repair exercises the real legacy producer and strict transactional storage."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import partial
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from config.refactor_modes import daily_recap_late_input_refresh_enabled
from database import daily_summary_refresh as storage
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_daily_summary_race_condition import notification_harness  # noqa: F401
from utils.other import daily_summary_refresh as identity
from utils.llm.daily_recap_fingerprint import FINGERPRINT_FIELD, input_fingerprint
from utils.daily_summary_read_contract import summary_read_payload

UID = 'synthetic-owner'
DAY = '2026-11-10'
NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)
RECAP = ('users', UID, 'daily_summaries', 'stable-link')
MARKER = ('users', UID, 'daily_summary_generation', DAY)


@pytest.fixture
def refresh_harness(notification_harness, monkeypatch):
    h = notification_harness
    n = h.module
    monkeypatch.delenv('DAILY_RECAP_LATE_INPUT_REFRESH_ENABLED')
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'off')
    monkeypatch.setenv('CALLS_RECAP_MODE', 'off')
    monkeypatch.setattr(n, 'generated_compute_allowed', lambda *_a: True)
    monkeypatch.setattr(n, 'account_deletion_blocks_user_work', lambda *_a: False)
    from utils.other import daily_recap

    monkeypatch.setattr(daily_recap, 'account_deletion_blocks_user_work', lambda *_a: False)
    monkeypatch.setattr(n, 'try_acquire_daily_summary_lock', lambda *_a: True)
    monkeypatch.setattr(n, 'require_daily_summary', lambda *a, **k: a[0])
    monkeypatch.setattr(n.daily_summary_metrics, 'refresh', MagicMock(wraps=n.daily_summary_metrics.refresh))
    monkeypatch.setattr(n, 'bound_daily_summary_conversations', lambda _u, _d, rows: rows)
    monkeypatch.setattr(n, '_conversation_has_summary_content', lambda *_a: True)
    monkeypatch.setattr(n, 'exclude_from_derived', lambda _u, row, **_k: row.excluded)
    monkeypatch.setattr(
        n,
        'deserialize_conversations',
        lambda rows: [
            SimpleNamespace(
                id=r['id'],
                transcript_segments=r.get('transcript_segments', ['speech']),
                discarded=r.get('discarded', False),
                excluded=r.get('excluded', False),
            )
            for r in rows
        ],
    )
    h.rows = [
        {
            'id': 'a',
            'created_at': NOW - timedelta(days=1),
            'sync_content_revision': 1,
            'summary_completed_at': (NOW - timedelta(days=1)).timestamp(),
            'structured': {'overview': 'Original content'},
        }
    ]
    h.store = StrictFirestore(
        {
            RECAP: {
                'id': 'stable-link',
                'date': DAY,
                'headline': 'Before',
                'created_at': NOW,
                'generated_at': NOW,
                'visibility': 'private',
                identity.FIELD: identity.fingerprint(h.rows),
            }
        }
    )
    h.conversations_db.get_conversations.side_effect = lambda *_a, **_k: deepcopy(h.rows)
    h.daily_summaries_db.get_daily_summary_by_date.side_effect = lambda *_a: deepcopy(h.store.rows.get(RECAP))
    h.daily_summaries_db.get_daily_summary_generation_status = lambda *_a: deepcopy(h.store.rows.get(MARKER))
    # The real marker setter is independently checked with the E2E storage seam.
    h.daily_summaries_db.set_daily_summary_generation_status = lambda *_a: None
    monkeypatch.setattr(n.recap_refresh_db, 'get_firestore_client', lambda: h.store)
    monkeypatch.setattr(n.recap_refresh_db, 'reserve', partial(storage.reserve, now=NOW))
    h.generate_summary.return_value = {'id': 'model-id', 'headline': 'After', 'created_at': NOW + timedelta(days=1)}
    h.call = lambda: n._generate_and_store_daily_summary(UID, DAY, NOW - timedelta(days=1), NOW)
    return h


def change(h):
    h.rows[0]['sync_content_revision'] += 1


def test_default_on_and_explicit_kill_switch(monkeypatch):
    monkeypatch.delenv('DAILY_RECAP_LATE_INPUT_REFRESH_ENABLED', raising=False)
    assert daily_recap_late_input_refresh_enabled()
    monkeypatch.setenv('DAILY_RECAP_LATE_INPUT_REFRESH_ENABLED', 'false')
    assert not daily_recap_late_input_refresh_enabled()


def test_changed_inputs_refresh_same_id_creation_time_and_receipt(refresh_harness):
    h = refresh_harness
    h.store.rows[RECAP]['notification_delivery_completed'] = True
    change(h)
    result, created, reason = h.call()
    assert created and reason is None
    h.module.daily_summary_metrics.refresh.assert_called_with('refreshed')
    assert result['id'] == 'stable-link'
    assert result['created_at'] == NOW
    assert result['notification_delivery_completed'] is True
    assert h.store.rows[RECAP]['headline'] == 'After'
    assert 'late_refresh_verify_pending' not in h.store.rows[MARKER]
    assert not h.call()[1]
    h.module.daily_summary_metrics.refresh.assert_called_with('refresh_skipped_unchanged')
    h.generate_summary.assert_called_once()


def test_metadata_only_write_does_not_refresh(refresh_harness):
    h = refresh_harness
    h.rows[0]['structured']['action_items'] = [{'description': 'Plan', 'completed': False}]
    h.store.rows[RECAP][identity.FIELD] = identity.fingerprint(h.rows)
    h.rows[0].update(updated_at=NOW, revision=99, starred=True, folder_id='folder', geolocation={'address': 'resolved'})
    h.rows[0]['structured']['action_items'][0]['completed'] = True
    assert not h.call()[1]
    h.generate_summary.assert_not_called()


@pytest.mark.parametrize('prior_identity', [False, True])
@pytest.mark.parametrize(
    'late',
    [
        False,
        True,
        'unknown',
        'ordinal',
        'bad_stamp',
        'missing_generation',
        'late_row',
        'missing_created',
        'bad_generation',
        'nan_stamp',
    ],
)
def test_adoption_never_blesses_existing_stale_content(refresh_harness, late, prior_identity):
    h = refresh_harness
    del h.store.rows[RECAP][identity.FIELD]
    if late is True:
        h.rows[0]['summary_completed_at'] = (NOW + timedelta(seconds=1)).timestamp()
    elif late == 'unknown':
        del h.rows[0]['summary_completed_at']
    elif late == 'ordinal':
        change(h)
    elif late == 'bad_stamp':
        h.rows[0]['summary_completed_at'] = 'unparseable'
    elif late == 'missing_generation':
        del h.store.rows[RECAP]['generated_at']
    elif late == 'missing_created':
        del h.rows[0]['created_at']
    elif late == 'bad_generation':
        h.store.rows[RECAP]['generated_at'] = 'unknown'
    elif late == 'nan_stamp':
        h.rows[0]['summary_completed_at'] = float('nan')
    elif late == 'late_row':
        h.rows.append(dict(h.rows[0], id='late', created_at=NOW + timedelta(seconds=1)))
    # Keep the old identity matching even in stale cases, so only the age /
    # ordinal check can schedule debt. A separate test covers no old identity.
    if prior_identity:
        h.store.rows[RECAP][FINGERPRINT_FIELD] = input_fingerprint(h.rows)
    result, created, reason = h.call()
    assert not created and reason is None
    h.generate_summary.assert_not_called()
    stale = late is not False
    assert h.store.rows[MARKER]['late_refresh_required'] is stale
    h.module.daily_summary_metrics.refresh.assert_called_with('adopted_stale_scheduled' if stale else 'adopted_fresh')
    assert result[identity.FIELD] == identity.fingerprint(h.rows)
    assert h.call()[1] is stale
    assert h.generate_summary.call_count == int(stale)


def test_real_persisted_daily_cap_is_owner_wide_and_rolls_at_utc_midnight():
    store = StrictFirestore()
    reserve = partial(storage.reserve, UID, firestore_client=store)
    assert reserve('2026-11-01', now=NOW)
    assert reserve('2026-11-02', now=NOW)
    # A new call/worker, and a different recap date, still share the owner's budget.
    assert not storage.reserve(UID, '2026-11-03', firestore_client=store, now=NOW)
    assert reserve('2026-11-03', now=NOW + timedelta(days=1))
    assert storage.reserve('other-owner', DAY, firestore_client=store, now=NOW)
    assert store.rows[('users', UID, 'daily_summary_refresh_budget', '2026-11-11')]['refresh_count'] == 2


def test_cap_blocks_third_model_attempt_and_retains_debt(refresh_harness):
    h = refresh_harness
    for _ in range(2):
        change(h)
        assert h.call()[1]
    change(h)
    assert not h.call()[1]
    assert h.generate_summary.call_count == 2
    h.module.daily_summary_metrics.refresh.assert_called_with('refresh_skipped_cap')
    assert h.store.rows[MARKER]['late_refresh_required'] is True


def test_later_revision_during_generation_keeps_old_content_and_repair_debt(refresh_harness):
    h = refresh_harness
    change(h)

    def generate(*_a, **_k):
        change(h)
        return {'headline': 'Outdated candidate'}

    h.generate_summary.side_effect = generate
    assert not h.call()[1]
    assert h.store.rows[RECAP]['headline'] == 'Before'
    h.module.daily_summary_metrics.refresh.assert_called_with('refresh_conflict')
    assert h.store.rows[MARKER]['late_refresh_required'] is True
    h.generate_summary.side_effect = None
    assert h.call()[1]


def test_revision_between_last_input_read_and_write_retains_verification(refresh_harness, monkeypatch):
    h = refresh_harness
    change(h)
    commit = h.module.recap_refresh_db.commit

    def race(*a, **k):
        change(h)
        return commit(*a, **k)

    monkeypatch.setattr(h.module.recap_refresh_db, 'commit', race)
    assert h.call()[1]
    assert h.store.rows[RECAP][identity.FIELD] != identity.fingerprint(h.rows)
    assert 'late_refresh_verify_pending' not in h.store.rows[MARKER]
    monkeypatch.setattr(h.module.recap_refresh_db, 'commit', commit)
    assert h.call()[1]
    assert h.store.rows[RECAP][identity.FIELD] == identity.fingerprint(h.rows)


def test_concurrent_visibility_and_delivery_changes_survive_content_patch(refresh_harness):
    h = refresh_harness
    change(h)

    def generate(*_a, **_k):
        h.store.rows[RECAP].update(visibility='shared', notification_delivery_completed=True)
        return {'headline': 'After', 'visibility': 'private', 'notification_delivery_completed': False}

    h.generate_summary.side_effect = generate
    result, created, _ = h.call()
    assert created and result['visibility'] == 'shared'
    assert result['notification_delivery_completed'] is True
    assert h.store.rows[RECAP]['visibility'] == 'shared'
    assert h.store.transactions[-1].updates[-1][0] == RECAP
    assert 'visibility' not in h.store.transactions[-1].updates[-1][1]


def test_concurrent_recap_writer_is_not_overwritten(refresh_harness):
    h = refresh_harness
    change(h)
    h.generate_summary.side_effect = lambda *_a, **_k: (
        h.store.rows[RECAP].update({identity.FIELD: 'newer-writer'}) or {'headline': 'Lost race'}
    )
    assert not h.call()[1]
    assert h.store.rows[RECAP]['headline'] == 'Before'
    assert h.store.rows[MARKER]['late_refresh_required'] is True


@pytest.mark.parametrize('receipt', [False, True])
def test_refresh_is_silent_even_for_on_demand_day(refresh_harness, monkeypatch, receipt):
    h = refresh_harness
    n = h.module
    if receipt:
        h.store.rows[RECAP]['notification_delivery_completed'] = True
    change(h)
    monkeypatch.setattr(n, '_display_date_for_now', lambda *_a: NOW.date() - timedelta(days=1))
    monkeypatch.setattr(n, '_backfill_recent_daily_summaries', MagicMock())
    monkeypatch.setattr(n, '_deliver_day_summary_webhook', MagicMock())
    monkeypatch.setattr(n, '_deliver_current_day_summary', MagicMock())
    n._send_summary_notification((UID, ['token'], 'UTC'))
    assert 'late_refresh_silent' not in h.store.rows[RECAP]
    n._deliver_current_day_summary.assert_not_called()
    n._deliver_day_summary_webhook.assert_not_called()


def test_deleted_input_drops_out_of_generated_refresh(refresh_harness):
    h = refresh_harness
    h.rows.append(dict(h.rows[0], id='deleted-input'))
    h.store.rows[RECAP][identity.FIELD] = identity.fingerprint(h.rows)
    h.rows.pop()
    assert h.call()[1]
    assert [c.id for c in h.generate_summary.call_args.args[1]] == ['a']


def test_deleted_all_inputs_keeps_legacy_row_without_model(refresh_harness):
    h = refresh_harness
    h.rows.clear()
    assert h.call()[2] == 'no_conversations'
    assert h.store.rows[RECAP]['headline'] == 'Before'
    h.generate_summary.assert_not_called()


@pytest.mark.parametrize('fence', ['budget', 'locked', 'excluded', 'discarded', 'speech', 'account'])
def test_existing_fences_decline_refresh_before_model(refresh_harness, monkeypatch, fence):
    h = refresh_harness
    change(h)
    if fence == 'budget':
        monkeypatch.setattr(h.module, 'generated_compute_allowed', lambda *_a: False)
    elif fence == 'account':
        from utils.other import daily_recap

        monkeypatch.setattr(daily_recap, 'account_deletion_blocks_user_work', lambda *_a: True)
    elif fence == 'speech':
        h.rows[0]['transcript_segments'] = []
    else:
        h.rows[0][{'locked': 'is_locked', 'excluded': 'excluded', 'discarded': 'discarded'}[fence]] = True
    assert not h.call()[1]
    h.generate_summary.assert_not_called()


def test_invalid_candidate_never_overwrites_valid_recap(refresh_harness, monkeypatch):
    h = refresh_harness
    from utils.daily_summary_validation import require_daily_summary, DailySummaryUnavailable

    monkeypatch.setattr(h.module, 'require_daily_summary', require_daily_summary)
    change(h)
    h.generate_summary.return_value = {'memories_learned': [{'content': 'Missing canonical id'}]}
    with pytest.raises(DailySummaryUnavailable):
        h.call()
    assert h.store.rows[RECAP]['headline'] == 'Before'
    assert h.store.rows[MARKER]['late_refresh_required'] is True


def test_backfill_stays_seven_days_silent_and_refreshes_count_against_tick_cap(refresh_harness, monkeypatch):
    h = refresh_harness
    n = h.module
    generate = MagicMock(return_value=({'id': 'existing-refresh'}, True, None))
    monkeypatch.setattr(n, '_generate_and_store_daily_summary', generate)
    monkeypatch.setattr(n, '_deliver_current_day_summary', MagicMock())
    n._backfill_recent_daily_summaries(UID, NOW.date(), 'UTC')
    assert generate.call_count == 3
    n._deliver_current_day_summary.assert_not_called()
    generate.reset_mock()
    generate.return_value = ({'id': 'unchanged'}, False, None)
    n._backfill_recent_daily_summaries(UID, NOW.date(), 'UTC')
    assert generate.call_count == 7
    assert generate.call_args.args[1] == '2026-11-04'


def test_legacy_fresh_without_prior_fingerprint_adopts_without_model(refresh_harness):
    h = refresh_harness
    del h.store.rows[RECAP][identity.FIELD]
    assert FINGERPRINT_FIELD not in h.store.rows[RECAP]
    result, created, reason = h.call()
    assert not created and reason is None
    assert result[identity.FIELD] == identity.fingerprint(h.rows)
    assert not h.store.rows[MARKER]['late_refresh_required']
    assert not h.call()[1]
    h.generate_summary.assert_not_called()
    change(h)
    assert h.call()[1]


def test_refreshed_content_carries_its_read_contract_metadata(refresh_harness):
    h = refresh_harness
    change(h)
    h.generate_summary.return_value = {
        'headline': 'New format',
        'read_contract_version': 2,
        'action_items_coverage': 'created_in_window',
        'memories_learned_coverage': 'bounded_review_selection_max_3_from_600_newest_updated; not all stored memories',
        'stats': {'watching_minutes': 20, 'watching_minutes_basis': 'interval_union', 'watching_coverage': 'complete'},
    }
    result, created, reason = h.call()
    assert created and reason is None
    projected = summary_read_payload(h.store.rows[RECAP])
    assert result['read_contract_version'] == 2
    assert projected['action_items_coverage'] == 'created_in_window'
    assert projected['memories_learned_coverage'] == h.generate_summary.return_value['memories_learned_coverage']
    assert projected['stats']['watching_minutes_basis'] == 'interval_union'
    assert projected['stats']['watching_coverage'] == 'complete'


def test_refresh_metric_rejects_identity_and_free_text_labels(refresh_harness):
    metrics = refresh_harness.module.daily_summary_metrics
    before = set(metrics.REFRESH._metrics)
    with pytest.raises(ValueError, match='unknown daily recap refresh outcome'):
        metrics.refresh(UID)
    assert set(metrics.REFRESH._metrics) == before
    assert before == {(outcome,) for outcome in metrics.REFRESH_OUTCOMES}


def test_retry_delivery_after_refresh_pushes_once_without_receipt(refresh_harness, monkeypatch):
    h, n = refresh_harness, refresh_harness.module
    # A stale flag left by an earlier build must not suppress an owed delivery.
    h.store.rows[RECAP]['late_refresh_silent'] = True
    change(h)
    monkeypatch.setattr(n, '_display_date_for_now', lambda *_a: NOW.date() - timedelta(days=1))
    monkeypatch.setattr(n, '_backfill_recent_daily_summaries', MagicMock())
    monkeypatch.setattr(n, '_deliver_day_summary_webhook', MagicMock())
    monkeypatch.setattr(n, '_deliver_current_day_summary', MagicMock())
    monkeypatch.setattr(
        n.daily_summaries_db,
        'mark_daily_summary_delivery_completed',
        lambda *_a: h.store.rows[RECAP].update(notification_delivery_completed=True),
    )
    recipient = n.daily_summary_metrics.RECIPIENTS
    before = recipient.labels(outcome='generated')._value.get()
    refreshed_before = recipient.labels(outcome='refreshed')._value.get()
    user = (UID, ['token'], 'UTC', NOW, True)
    n._send_summary_notification(user)
    n._send_summary_notification(user)
    n._deliver_current_day_summary.assert_called_once()
    n._deliver_day_summary_webhook.assert_called_once()
    assert recipient.labels(outcome='generated')._value.get() == before
    assert recipient.labels(outcome='refreshed')._value.get() == refreshed_before + 1


def test_post_generation_account_deletion_blocks_pass_and_backfill(refresh_harness, monkeypatch):
    h, n = refresh_harness, refresh_harness.module
    change(h)
    h.generate_summary.side_effect = lambda *_a, **_k: (
        monkeypatch.setattr(n, 'account_deletion_blocks_user_work', lambda *_a: True) or {'headline': 'Must not commit'}
    )
    monkeypatch.setattr(n, '_backfill_recent_daily_summaries', MagicMock())
    monkeypatch.setattr(n, '_deliver_current_day_summary', MagicMock())
    assert n._send_summary_notification((UID, ['token'], 'UTC', NOW)) is None
    assert h.store.rows[RECAP]['headline'] == 'Before'
    n._backfill_recent_daily_summaries.assert_not_called()
    n._deliver_current_day_summary.assert_not_called()


@pytest.mark.parametrize('excluded', ['is_locked', 'excluded', 'discarded', 'bounded_out'])
def test_only_model_inputs_participate_in_fingerprint(refresh_harness, monkeypatch, excluded):
    h, n = refresh_harness, refresh_harness.module
    other = dict(h.rows[0], id='not-rendered')
    h.rows.append(other)
    if excluded == 'bounded_out':
        monkeypatch.setattr(n, 'bound_daily_summary_conversations', lambda _u, _d, rows: rows[:1])
    else:
        other[excluded] = True
    other['sync_content_revision'] = 20
    assert not h.call()[1]
    h.generate_summary.assert_not_called()
    change(h)
    assert h.call()[1]
    assert [c.id for c in h.generate_summary.call_args.args[1]] == ['a']


def test_full_window_records_truncation_without_claiming_complete_coverage(refresh_harness):
    h = refresh_harness
    h.rows[:] = [dict(h.rows[0], id=str(i)) for i in range(100)]
    h.store.rows[RECAP][identity.FIELD] = identity.fingerprint(h.rows)
    assert not h.call()[1]
    h.module.daily_summary_metrics.refresh.assert_any_call('window_truncated')
    h.generate_summary.assert_not_called()


def test_on_demand_existing_day_does_not_consume_scheduled_refresh_budget(refresh_harness, monkeypatch):
    h, n = refresh_harness, refresh_harness.module
    monkeypatch.setattr(n, 'require_generated_compute', lambda *_a: None)
    change(h)
    result, reason = n.generate_daily_summary_on_demand(UID, DAY, NOW - timedelta(days=1), NOW)
    assert result['headline'] == 'After' and reason is None
    h.generate_summary.assert_called_once()
    assert not any('daily_summary_refresh_budget' in key for key in h.store.rows)


def test_wave2_shadow_series_still_observes_inputs(refresh_harness, monkeypatch):
    h, n = refresh_harness, refresh_harness.module
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'serve')
    shadow = MagicMock()
    monkeypatch.setattr(n, 'record_notes_shadow', shadow)
    h.store.rows[RECAP][FINGERPRINT_FIELD] = input_fingerprint(h.rows)
    h.call()
    shadow.assert_called_once_with('daily_recap_inputs', 'agree')
    shadow.reset_mock()
    change(h)
    h.call()
    shadow.assert_called_once_with('daily_recap_inputs', 'disagree')


def test_verification_read_also_records_a_truncated_window(refresh_harness):
    h = refresh_harness
    change(h)

    def generate(*_a, **_k):
        h.rows.extend(dict(h.rows[0], id=str(i), is_locked=True) for i in range(99))
        return {'headline': 'Updated eligible input'}

    h.generate_summary.side_effect = generate
    assert h.call()[1]
    h.module.daily_summary_metrics.refresh.assert_any_call('window_truncated')
