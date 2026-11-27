"""First-week summary guarantee (SCA-4790): stamp, deadline, lane and counter.

Hermetic: no Firestore, no task client, no LLM.
"""

from __future__ import annotations

import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import enrichment as enrichment_config  # noqa: E402
from config import summary_guarantee as guarantee  # noqa: E402
from database import batch_summary_debt, conversations as conversations_db, users as users_db  # noqa: E402
from services import first_week_summary_closeout as closeout  # noqa: E402
from utils.conversations import summary_delivery  # noqa: E402
from utils.enrichment import age_gate, fresh_demotion, outbox  # noqa: E402

PAID = 1_790_000_000
HOUR = 3600


def _clear(monkeypatch):
    for name in (
        guarantee.FIRST_WEEK_ENABLED_ENV,
        guarantee.FIRST_WEEK_WINDOW_ENV,
        'ENRICHMENT_FIRST_WEEK_TASKS_QUEUE',
        'ENRICHMENT_FRESH_TASKS_QUEUE',
        'ENRICHMENT_TASKS_QUEUE',
        'ENRICHMENT_TASKS_HANDLER_URL',
        'ENRICHMENT_TASKS_OIDC_AUDIENCE',
        'ENRICHMENT_TASKS_INVOKER_SA',
        'ENRICHMENT_ROUTE',
        'ENRICHMENT_FRESH_DEMOTE_AFTER_MIN',
        'ENRICHMENT_MAX_AGE_HOURS',
    ):
        monkeypatch.delenv(name, raising=False)


# --- the window stamp ------------------------------------------------------


def test_stamp_is_absent_without_a_paid_start_or_outside_the_window(monkeypatch):
    _clear(monkeypatch)
    assert guarantee.first_week_stamp(None, PAID) is None
    assert guarantee.first_week_stamp(PAID, PAID - 1) is None
    assert guarantee.first_week_stamp(PAID, PAID + 7 * 24 * HOUR) is None


def test_stamp_covers_a_conversation_created_inside_the_paid_week(monkeypatch):
    _clear(monkeypatch)
    stamp = guarantee.first_week_stamp(PAID, PAID + 3 * 24 * HOUR, interval='monthly')
    assert stamp == {
        'policy_id': guarantee.FIRST_WEEK_POLICY_ID,
        'paid_since': PAID,
        'window_end_at': PAID + 7 * 24 * HOUR,
        'interval': 'monthly',
    }


def test_stamp_epoch_accepts_firestore_datetimes():
    naive = datetime.fromtimestamp(PAID, timezone.utc).replace(tzinfo=None)
    aware = datetime.fromtimestamp(PAID, timezone.utc)
    assert guarantee.first_week_stamp(PAID, naive)['paid_since'] == PAID
    assert guarantee.first_week_stamp(PAID, aware)['paid_since'] == PAID


def test_kill_switch_off_and_zero_hours_disable_the_stamp(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'false')
    assert guarantee.first_week_stamp(PAID, PAID + HOUR) is None
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'true')
    monkeypatch.setenv(guarantee.FIRST_WEEK_WINDOW_ENV, '0')
    assert guarantee.first_week_stamp(PAID, PAID + HOUR) is None


def test_window_is_stored_not_recomputed_from_age(monkeypatch):
    _clear(monkeypatch)
    row = {'first_week_summary': guarantee.first_week_stamp(PAID, PAID + HOUR)}
    assert guarantee.first_week_open(row, now=PAID + 6 * 24 * HOUR) is True
    assert guarantee.first_week_open(row, now=PAID + 7 * 24 * HOUR) is False
    # A config change after stamping does not move an in-flight window.
    monkeypatch.setenv(guarantee.FIRST_WEEK_WINDOW_ENV, '24')
    assert guarantee.first_week_open(row, now=PAID + 6 * 24 * HOUR) is True


def test_interval_comes_from_the_period_length_not_a_catalog():
    assert guarantee.first_week_interval(PAID, PAID + 30 * 24 * HOUR) == 'monthly'
    assert guarantee.first_week_interval(PAID, PAID + 365 * 24 * HOUR) == 'yearly'
    assert guarantee.first_week_interval(None, PAID) == 'unknown'


# --- the paid-start epoch --------------------------------------------------


def test_paid_since_is_set_once_on_a_free_to_paid_transition():
    stored = {'plan': 'basic', 'status': 'active'}
    incoming = {
        'plan': 'unlimited',
        'status': 'active',
        'current_period_start': PAID,
        '_first_week_payment_status': 'active',
        '_first_week_paid_since': PAID,
    }
    patch = users_db.paid_since_patch(stored, incoming, now=PAID)
    assert patch == {'paid_since': PAID}
    # The user-level epoch is authoritative and a renewal never moves it.
    assert users_db.paid_since_patch(stored, incoming, stored_user_paid_since=PAID, now=PAID + 99) == {
        'paid_since': PAID
    }
    # A legacy paid row without the epoch is never covered.
    assert users_db.paid_since_patch({'plan': 'unlimited', 'status': 'active'}, incoming, now=PAID) == {}
    assert (
        users_db.paid_since_patch(stored, {'plan': 'operator', 'status': 'active', 'current_period_start': PAID}) == {}
    )
    assert (
        users_db.paid_since_patch(
            stored, {'plan': 'unlimited', 'status': 'active', 'prepaid': True, 'current_period_start': PAID}
        )
        == {}
    )
    assert users_db.paid_since_patch(stored, {'plan': 'unlimited', 'status': 'active'}, now=PAID) == {}


def test_paid_since_ignores_a_trial_that_was_never_charged():
    stored = {'plan': 'basic', 'status': 'active'}
    assert users_db.paid_since_patch(stored, {'plan': 'unlimited', 'status': 'trialing'}, now=PAID) == {}
    # A carried epoch from the caller is authoritative and never moved.
    assert users_db.paid_since_patch(
        stored,
        {
            'plan': 'unlimited',
            'status': 'active',
            'paid_since': 5,
            'current_period_start': PAID,
            '_first_week_payment_status': 'active',
        },
        now=PAID,
    ) == {'paid_since': 5}
    trial = {'plan': 'unlimited', 'status': 'active'}
    converted = {
        'plan': 'unlimited',
        'status': 'active',
        '_first_week_payment_status': 'active',
        '_first_week_trial_conversion': True,
        '_first_week_paid_since': PAID + 24 * HOUR,
    }
    assert users_db.paid_since_patch(trial, converted, stored_user_first_week_trialing=True) == {
        'paid_since': PAID + 24 * HOUR
    }
    # An active entitlement projection alone is not provider evidence of payment.
    assert (
        users_db.paid_since_patch(
            stored,
            {'plan': 'unlimited', 'status': 'active', 'current_period_start': PAID},
        )
        == {}
    )


# --- the deadline readers --------------------------------------------------


def _stamped_row(now=PAID + 30 * HOUR):
    return {'first_pending_at': PAID + 20 * HOUR, 'first_week_summary': guarantee.first_week_stamp(PAID, PAID)}


def test_age_gate_does_not_park_a_row_inside_its_stored_window(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    row = _stamped_row()
    assert age_gate.expired(row, row['first_pending_at'], now=PAID + 96 * HOUR) is False
    assert age_gate.expired(row, row['first_pending_at'], now=PAID + 7 * 24 * HOUR + 1) is True
    # Kill switch off restores today's gate exactly.
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'false')
    assert age_gate.expired(row, row['first_pending_at'], now=PAID + 96 * HOUR) is True


def test_demotion_skips_an_open_first_week_row_with_no_first_week_queue(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv('ENRICHMENT_ROUTE', 'enrichment_queue')
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setenv('ENRICHMENT_FRESH_DEMOTE_AFTER_MIN', '30')
    dispatch = {
        'queue': 'enrichment-fresh',
        'handler': 'https://worker/v2/enrichment/run',
        'audience': 'https://worker/v2/enrichment/run',
        'invoker_sa': 'sa@example.iam',
    }
    row = {
        'first_pending_at': PAID,
        'first_summary_policy': {'first_summary_enabled': True, 'first_summary_deadline_seconds': 60},
        'first_week_summary': guarantee.first_week_stamp(PAID, PAID),
        'dispatch': dispatch,
    }
    assert fresh_demotion.stale_fresh(row, now=PAID + HOUR) is False
    assert fresh_demotion.stale_fresh(row, now=PAID + 7 * 24 * HOUR) is True


def test_first_week_does_not_replace_the_first_summary_deadline(monkeypatch):
    _clear(monkeypatch)
    row = _stamped_row()
    assert summary_delivery.summary_deadline_seconds(row) == guarantee.deadline_seconds()
    unstated = {'first_summary_policy': {'first_summary_enabled': True, 'first_summary_deadline_seconds': 60}}
    assert summary_delivery.summary_deadline_seconds(unstated) == 60


# --- the lane --------------------------------------------------------------


def test_first_week_binding_uses_its_reserved_queue_and_falls_back(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv('ENRICHMENT_ROUTE', 'enrichment_queue')
    monkeypatch.setenv('ENRICHMENT_TASKS_QUEUE', 'enrichment')
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setenv('ENRICHMENT_FIRST_WEEK_TASKS_QUEUE', 'enrichment-first-week')
    monkeypatch.setenv('ENRICHMENT_TASKS_HANDLER_URL', 'https://worker/v2/enrichment/run')
    assert enrichment_config.dispatch_binding(recent=False, first_week=True)['queue'] == 'enrichment-first-week'
    # Priority is its own admission gate: no 30-minute freshness clock needed.
    assert enrichment_config.dispatch_binding(recent=False, first_week=False)['queue'] == 'enrichment'
    monkeypatch.delenv('ENRICHMENT_FIRST_WEEK_TASKS_QUEUE')
    assert enrichment_config.dispatch_binding(recent=True, first_week=True)['queue'] == 'enrichment-fresh'
    assert enrichment_config.dispatch_binding(recent=False, first_week=True)['queue'] == 'enrichment-fresh'
    # Backfill keeps its own routing.
    monkeypatch.setenv('SYNC_BACKFILL_TASKS_QUEUE', 'sync-backfill')
    assert enrichment_config.dispatch_binding(backfill=True, first_week=True)['queue'] == 'sync-backfill'


def test_production_overlay_keeps_every_first_week_service_disabled_until_census():
    key = guarantee.FIRST_WEEK_ENABLED_ENV
    overlay = yaml.safe_load((BACKEND_DIR / 'deploy/runtime_env/prod.overlay.yaml').read_text())['overlay']
    prod = yaml.safe_load((BACKEND_DIR / 'deploy/runtime_env.yaml').read_text())['environments']['prod']

    def value(env, name=key):
        entry = env.get(name)
        return entry.get('value') if isinstance(entry, dict) else entry

    # Both GKE writers have direct overrides and the shared envFrom ConfigMap
    # carries the same explicit off value for workload replicas without one.
    for service in ('backend-listen', 'pusher'):
        assert value(overlay['gke'][service]['env']) == 'false'
        assert value(prod['gke'][service]['env']) == 'false'
    assert overlay['gke']['config_map']['entries'][key] == {'source': 'literal', 'value': 'false'}
    assert prod['gke']['config_map']['entries'][key] == {'source': 'literal', 'value': 'false'}
    assert value(overlay['desktop_backend']['env']) == 'false'
    assert value(prod['desktop_backend']['env']) == 'false'

    cloud_run = prod['cloud_run']
    services = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration', 'backend-projection-pump')
    for service in services:
        assert value(cloud_run['services'][service]['env']) == 'false'
    jobs = ('notifications-job', 'x-connector-sync-job', 'frame-request-retention-job', 'day3-reengagement-email-job')
    for job in jobs:
        assert value(cloud_run['jobs'][job]['env']) == 'false'

    assert 'enrichment-first-week:' in (BACKEND_DIR / 'deploy/ops/prod.yaml').read_text()
    assert "'first_week_summary_closeout'" in (BACKEND_DIR / 'database/firestore_index_registry.py').read_text()


# --- the counter -----------------------------------------------------------


def test_closeout_classifies_summarized_failed_and_no_attempt():
    stamp = guarantee.first_week_stamp(PAID, PAID)
    base = {'first_week_summary': stamp, 'first_week_outcome': None}
    assert closeout.classify({**base, 'summary_output_present': True, 'summary_completed_at': PAID + HOUR}) == (
        'summarized',
        'unknown',
    )
    assert closeout.classify({**base, 'summary_empty_failures': 1})[0] == 'no_attempt'
    assert closeout.classify({**base, 'summary_blocked_reason': 'blocked_byok'})[0] == 'no_attempt'
    assert closeout.classify({**base, 'first_week_attempts': 1, 'first_week_last_class': 'attempt_failed'})[0] == (
        'attempt_failed'
    )
    assert closeout.classify(base)[0] == 'no_attempt'


def test_closeout_counts_only_an_uncounted_row():
    stamp = guarantee.first_week_stamp(PAID, PAID)
    row = {'first_week_summary': stamp, 'first_week_outcome': None, 'summary_output_present': True}
    assert closeout.outcome_patch(row, now=PAID + 8 * 24 * HOUR) == {
        'first_week_outcome': 'summarized',
        'first_week_outcome_at': PAID + 8 * 24 * HOUR,
    }
    counted = {**row, 'first_week_outcome': 'no_attempt'}
    assert closeout.outcome_patch(counted, now=PAID + 9 * 24 * HOUR) is None


def test_closeout_is_a_no_op_when_the_guarantee_is_off(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'false')
    assert closeout.tick(now=PAID, client=None) == {'scanned': 0, 'closed': 0, 'errors': 0, 'lease_busy': 0}


def test_a_summary_that_lands_after_the_close_is_not_backdated():
    stamp = guarantee.first_week_stamp(PAID, PAID)
    row = {
        'first_week_summary': stamp,
        'summary_output_present': True,
        'summary_completed_at': stamp['window_end_at'] + HOUR,
    }
    assert closeout.classify(row)[0] == 'no_attempt'


def test_campaign_off_subscription_writer_round_trips_paid_since_at_user_level(monkeypatch):
    class Snapshot:
        exists = True

        def __init__(self, data):
            self.data = data

        def to_dict(self):
            return dict(self.data)

    class UserRef:
        def __init__(self):
            self.data = {'subscription': {'plan': 'basic', 'status': 'active'}}
            self.writes = []
            self.reads = []

        def get(self, fields=None, transaction=None, field_paths=None):
            fields = field_paths or fields
            self.reads.append(tuple(fields or ()))
            selected = self.data if fields is None else {key: self.data[key] for key in fields if key in self.data}
            return Snapshot(selected)

        def update(self, patch):
            self.writes.append(dict(patch))
            self.data.update(patch)

    ref = UserRef()

    class Collection:
        def document(self, _uid):
            return ref

    class Client:
        def collection(self, name):
            assert name == 'users'
            return Collection()

    class Transaction:
        def update(self, reference, patch):
            reference.update(patch)

    monkeypatch.setattr(users_db, 'transactional', lambda function: function)
    monkeypatch.setattr(users_db, 'run_transactional', lambda _client, function, **_kwargs: function(Transaction()))

    monkeypatch.setattr(users_db, 'db', Client())
    monkeypatch.setattr(users_db, 'invalidate_subscription', lambda _uid: None)
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'true')
    monkeypatch.setattr('config.referral_campaign.campaign_enabled', lambda: False)

    users_db.update_user_subscription.__wrapped__(
        'uid',
        {
            'plan': 'unlimited',
            'status': 'active',
            'current_period_start': PAID,
            'current_period_end': PAID + 30 * 24 * HOUR,
            '_first_week_payment_status': 'active',
            '_first_week_paid_since': PAID,
        },
    )

    assert len(ref.writes) == 1
    assert 'paid_since' in ref.data and type(ref.data['paid_since']) is int
    assert ref.data[users_db.FIRST_WEEK_TRIALING_FIELD] is False
    assert 'paid_since' not in ref.data['subscription']
    assert '_first_week_trialing' not in ref.data['subscription']

    cache = {}
    reads = []

    def cached_read(family, uid, variant, fetch, **kwargs):
        assert family == 'subscription_cache'
        assert kwargs['seconds'] == 60
        reads.append(variant)
        if variant not in cache:
            cache[variant] = fetch()
        return cache[variant]

    def existing(uid, fields, *, firestore_client=None):
        data = ref.get(['subscription', *fields]).to_dict()
        subscription = users_db.Subscription.model_validate(data['subscription'])
        return subscription, {field: data.get(field) for field in fields}

    monkeypatch.setattr(users_db, 'cached_read', cached_read)
    monkeypatch.setattr(users_db, 'memo', lambda _uid, _key, fetch: fetch())
    monkeypatch.setattr(users_db, 'get_existing_user_subscription_and_fields', existing)
    paid_since = ref.data['paid_since']
    stamp = users_db.first_week_stamp_for('uid', paid_since + HOUR)
    again = users_db.first_week_stamp_for('uid', paid_since + HOUR)
    assert stamp == again
    assert stamp['paid_since'] == paid_since
    assert stamp['window_end_at'] == paid_since + 168 * HOUR
    assert len(reads) == 2 and reads[0] == reads[1]

    ref.reads.clear()
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'false')
    users_db.update_user_subscription.__wrapped__('uid', {'plan': 'unlimited', 'status': 'active'})
    assert ref.reads == []
    assert ref.data['paid_since'] == paid_since


def test_campaign_off_flag_off_writer_keeps_subscription_payload_unchanged(monkeypatch):
    class UserRef:
        def __init__(self):
            self.data = {'subscription': {'plan': 'basic', 'status': 'active'}}
            self.writes = []

        def update(self, patch):
            self.writes.append(dict(patch))
            self.data.update(patch)

    ref = UserRef()

    class Collection:
        def document(self, _uid):
            return ref

    class Client:
        def collection(self, name):
            assert name == 'users'
            return Collection()

    monkeypatch.setattr(users_db, 'db', Client())
    monkeypatch.setattr(users_db, 'invalidate_subscription', lambda _uid: None)
    monkeypatch.setattr('config.referral_campaign.campaign_enabled', lambda: False)
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'false')
    incoming = {
        'plan': 'unlimited',
        'status': 'active',
        'current_period_start': PAID,
        'current_period_end': PAID + 30 * 24 * HOUR,
        '_first_week_payment_status': 'active',
        '_first_week_paid_since': PAID,
        '_first_week_trial_conversion': True,
        '_first_week_trialing': True,
    }
    expected = {key: value for key, value in incoming.items() if not key.startswith('_first_week_')}

    users_db.update_user_subscription.__wrapped__('uid', incoming)

    assert ref.writes == [{'subscription': expected}]
    assert ref.data == {'subscription': expected}
    assert 'paid_since' not in ref.data
    assert users_db.FIRST_WEEK_TRIALING_FIELD not in ref.data


def test_conversation_codec_uses_stored_creation_time_for_the_window(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'true')
    monkeypatch.setattr(conversations_db, 'first_week_open', lambda _row, now=None: True)
    monkeypatch.setattr(
        users_db,
        'first_week_stamp_for',
        lambda _uid, created_at, **kwargs: guarantee.first_week_stamp(PAID, created_at, interval='monthly'),
    )

    valid = conversations_db.encode_conversation_for_write(
        'uid', {'id': 'new', 'structured': {}, 'created_at': PAID + HOUR}
    )
    old_delta = conversations_db.encode_conversation_for_write(
        'uid',
        {'id': 'old', 'structured': {}, 'created_at': PAID + HOUR},
        conversation_state={'created_at': PAID - 1},
    )
    missing_time = conversations_db.encode_conversation_for_write('uid', {'id': 'partial', 'structured': {}})
    historical = conversations_db.encode_conversation_for_write(
        'uid',
        {'id': 'historical', 'structured': {}},
        conversation_state={'created_at': PAID + HOUR, 'processing_tier': 'historical'},
    )
    closed_stamp = guarantee.first_week_stamp(PAID, PAID + HOUR, interval='monthly')
    closed = conversations_db.encode_conversation_for_write(
        'uid',
        {'id': 'closed', 'structured': {}},
        conversation_state={
            'created_at': PAID + HOUR,
            'first_week_summary': closed_stamp,
            'first_week_outcome': 'no_attempt',
            'first_week_outcome_at': PAID + 8 * 24 * HOUR,
        },
    )

    assert valid['first_week_summary']['paid_since'] == PAID
    assert 'first_week_summary' not in old_delta
    assert 'first_week_summary' not in missing_time
    assert 'first_week_summary' not in historical
    assert closed['first_week_summary'] == closed_stamp
    assert closed['first_week_outcome'] == 'no_attempt'
    assert closed['first_week_outcome_at'] == PAID + 8 * 24 * HOUR
    assert conversations_db._first_week_created_epoch({}) is None


def test_conversation_codec_does_not_create_a_closed_window_stamp(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'true')
    monkeypatch.setattr(
        users_db,
        'first_week_stamp_for',
        lambda _uid, created_at, **kwargs: guarantee.first_week_stamp(PAID, created_at, interval='monthly'),
    )
    write = conversations_db.encode_conversation_for_write(
        'uid', {'id': 'closed-window', 'structured': {}, 'created_at': PAID + HOUR}
    )
    assert 'first_week_summary' not in write


def test_processing_merge_preserves_closed_first_week_receipts():
    stamp = guarantee.first_week_stamp(PAID, PAID + HOUR)
    existing = {
        'first_week_summary': stamp,
        'first_week_outcome': 'no_attempt',
        'first_week_outcome_at': PAID + 8 * 24 * HOUR,
        'first_week_attempts': 0,
        'first_week_last_class': 'no_attempt',
    }
    write = {'summary_output_present': True, 'structured': {'overview': 'usable'}}
    summary_delivery.merge_result(existing, write, 'uid', now=PAID + 9 * 24 * HOUR)
    assert write['first_week_summary'] == stamp
    assert write['first_week_outcome'] == 'no_attempt'
    assert write['first_week_outcome_at'] == PAID + 8 * 24 * HOUR


def test_outbox_mark_uses_the_stored_stamp_or_original_creation_time(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'true')
    monkeypatch.setenv('ENRICHMENT_ROUTE', 'enrichment_queue')
    monkeypatch.setenv('ENRICHMENT_TASKS_QUEUE', 'enrichment')
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setenv('ENRICHMENT_FIRST_WEEK_TASKS_QUEUE', 'enrichment-first-week')
    monkeypatch.setenv('ENRICHMENT_TASKS_HANDLER_URL', 'https://worker.example/v2/enrichment/run')
    monkeypatch.setenv('ENRICHMENT_TASKS_OIDC_AUDIENCE', 'https://worker.example/v2/enrichment/run')
    monkeypatch.setenv('ENRICHMENT_TASKS_INVOKER_SA', 'worker@example.iam.gserviceaccount.com')
    monkeypatch.setattr(
        users_db,
        'first_week_stamp_for',
        lambda _uid, created_at, **kwargs: guarantee.first_week_stamp(PAID, created_at, interval='monthly'),
    )
    metadata = {
        'new': {'created_at': PAID + HOUR},
        'old': {'created_at': PAID - 1},
        'historical': {'created_at': PAID + HOUR, 'processing_tier': 'historical'},
    }
    monkeypatch.setattr(outbox, '_conversation_scheduling_metadata', lambda _uid, cid: metadata[cid])
    rows = {}

    def mutate(document_id, update):
        _persisted, (result, coalesced) = update(None)
        rows[document_id] = result
        return result, coalesced

    monkeypatch.setattr(outbox, '_mutate', mutate)
    monkeypatch.setattr(outbox, '_enqueue', lambda _row: None)
    outbox.mark('uid', 'new', 'en', now=PAID + HOUR)
    outbox.mark('uid', 'old', 'en', now=PAID + HOUR)
    outbox.mark('uid', 'historical', 'en', now=PAID + HOUR)

    assert rows[outbox.key('uid', 'new')]['first_week_summary']['paid_since'] == PAID
    assert 'first_week_summary' not in rows[outbox.key('uid', 'old')]
    assert 'first_week_summary' not in rows[outbox.key('uid', 'historical')]


def test_outbox_mark_retries_when_required_metadata_is_unavailable(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'true')
    monkeypatch.setattr(outbox, '_conversation_scheduling_metadata', Mock(side_effect=OSError('offline')))
    fallback = Mock()
    monkeypatch.setattr(outbox, 'record_fallback', fallback)
    with pytest.raises(RuntimeError, match='retry the outbox mark'):
        outbox.mark('uid', 'conversation', 'en', now=PAID)
    fallback.assert_called_once()


def test_subscription_stamp_read_errors_fail_open_and_are_observable(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'true')
    monkeypatch.setattr(
        users_db,
        'get_existing_user_subscription_and_fields_cached',
        Mock(side_effect=OSError('offline')),
    )
    fallback = Mock()
    monkeypatch.setattr(users_db, 'record_fallback', fallback)
    assert users_db.first_week_stamp_for('uid', PAID) is None
    fallback.assert_called_once()


def test_open_first_week_sweep_skips_the_conversation_point_read(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'true')
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    now = PAID + 4 * 24 * HOUR
    row = {
        'uid': 'uid',
        'conversation_id': 'conversation',
        'first_pending_at': PAID + HOUR,
        'first_week_summary': guarantee.first_week_stamp(PAID, PAID + HOUR),
    }
    monkeypatch.setattr(outbox, 'mutate_row', lambda _row_id, operation, client=None: operation(row)[1])
    created_read = Mock(side_effect=AssertionError('open first-week rows need no conversation read'))
    monkeypatch.setattr(age_gate, 'conversation_created_at', created_read)
    assert not age_gate.park_if_expired('row', 'token', now=now, client=object())
    created_read.assert_not_called()


def test_first_week_keeps_existing_dispatch_and_repair_deadlines(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_SECONDS', '120')
    monkeypatch.setenv('SYNC_REPROCESS_SETTLE_SECONDS', '600')
    monkeypatch.setenv('ENRICHMENT_ROUTE', 'enrichment_queue')
    monkeypatch.setenv('ENRICHMENT_TASKS_QUEUE', 'enrichment')
    monkeypatch.setenv('ENRICHMENT_FIRST_WEEK_TASKS_QUEUE', 'enrichment-first-week')
    monkeypatch.setenv('ENRICHMENT_TASKS_HANDLER_URL', 'https://worker.example/v2/enrichment/run')
    monkeypatch.setenv('ENRICHMENT_TASKS_OIDC_AUDIENCE', 'https://worker.example/v2/enrichment/run')
    monkeypatch.setenv('ENRICHMENT_TASKS_INVOKER_SA', 'worker@example.iam.gserviceaccount.com')
    stamp = guarantee.first_week_stamp(PAID, PAID + HOUR, interval='monthly')
    assert outbox._deadline_seconds({'first_week_summary': stamp, 'first_pending_at': PAID}) == 120
    assert summary_delivery.summary_deadline_seconds({'first_week_summary': stamp}) == 120

    row, _ = outbox.mark_update(
        'uid',
        'conversation',
        'en',
        current=PAID,
        settle_at=PAID + 600,
        coalesce='max',
        effects_only=False,
        batch=False,
        first_week=stamp,
        initial_recent=False,
    )(None)
    appended, _ = outbox.mark_update(
        'uid',
        'conversation',
        'en',
        current=PAID + 60,
        settle_at=PAID + 660,
        coalesce='max',
        effects_only=False,
        batch=False,
        first_week=stamp,
        initial_recent=False,
    )(row)

    assert row['dispatch']['queue'] == 'enrichment-first-week'
    assert row['due_at'] == PAID + 120
    assert appended['due_at'] == PAID + 120


def test_projection_repair_deadline_is_not_extended_to_week_end(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'true')
    monkeypatch.setattr(summary_delivery, 'projection_debt_enabled', lambda: True)
    accepted = PAID + HOUR
    write = {
        'status': 'completed',
        'created_at': accepted,
        'summary_first_pending_at': accepted,
        'summary_due_at': None,
        'data_protection_level': 'standard',
        'structured': {},
        'first_week_summary': guarantee.first_week_stamp(PAID, accepted, interval='monthly'),
    }

    assert summary_delivery.stamp_projection_debt(write, now=accepted + HOUR)
    assert write['summary_due_at'] == accepted + guarantee.deadline_seconds()


def test_projection_debt_survives_the_72_hour_gate_inside_an_open_week(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(guarantee.FIRST_WEEK_ENABLED_ENV, 'true')
    monkeypatch.setattr(summary_delivery, 'projection_debt_enabled', lambda: True)
    accepted = PAID + HOUR
    stamp = guarantee.first_week_stamp(PAID, accepted)
    write = {
        'status': 'completed',
        'created_at': accepted,
        'summary_first_pending_at': accepted,
        'summary_due_at': None,
        'data_protection_level': 'standard',
        'structured': {},
        'first_week_summary': stamp,
    }
    now = PAID + 4 * 24 * HOUR
    assert now - accepted > 72 * HOUR
    assert summary_delivery.stamp_projection_debt(write, now=now)
    assert write['summary_due_at'] == accepted + guarantee.deadline_seconds()


def test_batch_projection_debt_inherits_the_stored_first_week_stamp(monkeypatch):
    _clear(monkeypatch)
    stamp = guarantee.first_week_stamp(PAID, PAID + HOUR, interval='monthly')
    current = {
        'first_week_summary': stamp,
        'first_week_outcome': 'no_attempt',
        'first_week_outcome_at': PAID + 8 * 24 * HOUR,
        'created_at': PAID + HOUR,
    }
    payload = {
        'id': 'conversation',
        'record_lane_owner': 'batch_live_v1',
        'status': 'completed',
        'record_projection_revision': 2,
        'transcript_segments': [{'text': 'ok'}],
    }
    seen = {}
    monkeypatch.setattr(batch_summary_debt.delivery, 'projection_debt_enabled', lambda: True)
    monkeypatch.setattr(batch_summary_debt, 'verify_projection_finalization', lambda *args: (True, None))

    def stamp_debt(candidate):
        seen.update(candidate)
        candidate['summary_first_pending_at'] = PAID + HOUR

    monkeypatch.setattr(batch_summary_debt.delivery, 'stamp_projection_debt', stamp_debt)
    batch_summary_debt.arm_projection_summary('uid', object(), object(), payload, current)

    assert seen['first_week_summary'] == stamp
    assert seen['created_at'] == PAID + HOUR
    assert seen['first_week_outcome'] == 'no_attempt'
    assert payload['summary_first_pending_at'] == PAID + HOUR
    assert payload['first_week_summary'] == stamp
    assert payload['first_week_outcome'] == 'no_attempt'


def test_closeout_writes_the_durable_aggregate_with_the_outcome(monkeypatch):
    class Snapshot:
        exists = True

        def __init__(self, data):
            self.data = data

        def to_dict(self):
            return dict(self.data)

    class Ref:
        def __init__(self, path, data=None):
            self.path = path
            self.data = dict(data or {})

        def get(self, transaction=None):
            return Snapshot(self.data)

    class Transaction:
        def update(self, ref, patch):
            ref.data.update(patch)

        def set(self, ref, value, merge=False):
            ref.data.update(value)

    class Collection:
        def __init__(self, client, path):
            self.client = client
            self.path = path

        def document(self, doc_id):
            path = f'{self.path}/{doc_id}'
            return self.client.refs.setdefault(path, Ref(path))

        def stream(self):
            prefix = f'{self.path}/'
            return [Snapshot(ref.data) for path, ref in self.client.refs.items() if path.startswith(prefix)]

    class Client:
        def __init__(self):
            self.refs = {}
            self.tx = Transaction()

        def collection(self, path):
            return Collection(self, path)

        def transaction(self):
            return self.tx

    monkeypatch.setattr(closeout.firestore, 'transactional', lambda fn: fn)
    client = Client()
    conversation = Ref(
        'users/uid/conversations/c',
        {
            'first_week_summary': guarantee.first_week_stamp(PAID, PAID, interval='monthly'),
            'first_week_outcome': None,
            'summary_output_present': True,
        },
    )

    result = closeout.close_one(conversation, now=PAID + 8 * 24 * HOUR, client=client)

    assert result == ('summarized', 'monthly')
    assert conversation.data['first_week_outcome'] == 'summarized'
    assert closeout.durable_outcome_counts(client=client) == {('summarized', 'monthly'): 1}


def test_closeout_classifies_from_the_outbox_attempt_receipt(monkeypatch):
    class Snapshot:
        exists = True

        def __init__(self, data):
            self.data = data

        def to_dict(self):
            return dict(self.data)

    class Ref:
        def __init__(self, path, data=None):
            self.path = path
            self.data = dict(data or {})

        def get(self, transaction=None):
            return Snapshot(self.data)

    class Transaction:
        def update(self, ref, patch):
            ref.data.update(patch)

        def set(self, ref, value, merge=False):
            ref.data.update(value)

    class Collection:
        def __init__(self, client, path):
            self.client = client
            self.path = path

        def document(self, doc_id):
            path = f'{self.path}/{doc_id}'
            return self.client.refs.setdefault(path, Ref(path))

    class Client:
        def __init__(self):
            self.refs = {}
            self.tx = Transaction()

        def collection(self, path):
            return Collection(self, path)

        def transaction(self):
            return self.tx

    monkeypatch.setattr(closeout.firestore, 'transactional', lambda fn: fn)
    client = Client()
    conversation = Ref(
        'users/uid/conversations/c',
        {
            'uid': 'uid',
            'first_week_summary': guarantee.first_week_stamp(PAID, PAID, interval='monthly'),
            'first_week_outcome': None,
        },
    )
    outbox_id = hashlib.sha256(b'uid\0c').hexdigest()
    client.collection('sync_reprocess_outbox').document(outbox_id).data.update(
        first_week_attempts=1,
        first_week_last_class='attempt_failed',
    )

    result = closeout.close_one(conversation, now=PAID + 8 * 24 * HOUR, client=client)

    assert result == ('attempt_failed', 'monthly')
    assert conversation.data['first_week_outcome'] == 'attempt_failed'


def test_closeout_clears_callback_results_on_transaction_retry(monkeypatch):
    class Snapshot:
        exists = True

        def __init__(self, data):
            self.data = data

        def to_dict(self):
            return dict(self.data)

    class SequenceRef:
        def __init__(self, rows):
            self.rows = iter(rows)

        def get(self, transaction=None):
            return Snapshot(next(self.rows))

    class Transaction:
        def get(self, ref):
            return ref.get(transaction=self)

        def update(self, _ref, _patch):
            pass

        def set(self, _ref, _value, merge=False):
            pass

    class CountRef:
        def get(self, transaction=None):
            return Snapshot({})

    class Collection:
        def document(self, _doc_id):
            return CountRef()

    class Client:
        def __init__(self):
            self.tx = Transaction()

        def collection(self, _path):
            return Collection()

        def transaction(self):
            return self.tx

    def retry_twice(callback):
        def wrapped(transaction):
            callback(transaction)
            callback(transaction)

        return wrapped

    monkeypatch.setattr(closeout.firestore, 'transactional', retry_twice)
    stamp = guarantee.first_week_stamp(PAID, PAID, interval='monthly')
    ref = SequenceRef(
        [
            {'first_week_summary': stamp, 'first_week_outcome': None},
            {'first_week_summary': stamp, 'first_week_outcome': 'no_attempt'},
        ]
    )

    assert closeout.close_one(ref, now=PAID + 8 * 24 * HOUR, client=Client()) is None


def test_closeout_release_does_not_clear_a_successor_lease(monkeypatch):
    class Snapshot:
        exists = True

        def to_dict(self):
            return {'owner': 'successor', 'lease_until': PAID + 500}

    class Ref:
        def get(self, transaction=None):
            return Snapshot()

    class Transaction:
        def __init__(self):
            self.updated = False

        def update(self, _ref, _patch):
            self.updated = True

    class Client:
        def __init__(self):
            self.tx = Transaction()

        def transaction(self):
            return self.tx

    monkeypatch.setattr(closeout.firestore, 'transactional', lambda fn: fn)
    client = Client()

    closeout._release(Ref(), 'expired-owner', client)

    assert client.tx.updated is False


def test_closeout_lease_contention_is_not_reported_as_an_error(monkeypatch):
    monkeypatch.setattr(closeout, 'first_week_enabled', lambda: True)
    monkeypatch.setattr(closeout, '_lease', lambda *_args: None)

    result = closeout.tick(now=PAID, client=object())

    assert result == {'scanned': 0, 'closed': 0, 'errors': 0, 'lease_busy': 1}
