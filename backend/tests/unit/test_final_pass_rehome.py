"""Re-homing a conversation stranded on ``legacy_final_pass_v1`` (M3 review; lead ruling b209a5).

The loop being closed: in ``draining``/``dark`` a conversation whose
``record_lane_owner`` is ``legacy_final_pass_v1`` routes LEGACY, no legacy job may
be created, and every later upload is acknowledged with the in-progress 409, so
the phone keeps that audio for good. ``utils.sync.final_pass_rehome`` moves the
owner to ``batch_sync_v1`` with the revision-fenced CAS and the upload is
admitted to batch intake instead.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import conversations as conversations_db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreSnapshot
from utils.batch_pipeline import live_upload
from utils.batch_pipeline.live_upload import RecordUploadRoute
from utils.conversations import transcription_shadow as shadow
from utils.sync import final_pass_rehome, legacy_dark
from utils.sync.final_pass_rehome import RehomeOutcome, rehome_final_pass_owner, upload_rehome
from utils.sync.legacy_dark import LegacySyncMode

UID, CID = 'synthetic-user', 'synthetic-conversation'
PATH = ('users', UID, 'conversations', CID)
R1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
R2 = datetime(2026, 1, 2, tzinfo=timezone.utc)


def forbidden(*args, **kwargs):
    raise AssertionError('this path must not run')


@pytest.fixture(autouse=True)
def revision_from_row(monkeypatch):
    # Pin the original re-home/owner policy; new language admission ordering
    # is covered through the real router in test_batch_admission_language_router.
    monkeypatch.setenv('BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED', 'false')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(
        StrictFirestoreSnapshot,
        'update_time',
        property(lambda self: (self._data or {}).get('_test_revision')),
        raising=False,
    )


def _client(owner='legacy_final_pass_v1', **fields):
    row = {'record_lane_owner': owner, '_test_revision': R1, **fields}
    if owner is None:
        row.pop('record_lane_owner')
    return StrictFirestore({PATH: row})


def _cas(client, *, winner='batch_sync_v1', outcome=R2):
    """A claim_record_lane_owner double: on success it writes the owner like the real CAS."""

    def claim(uid, conversation_id, owner, expected_updated_at, *, firestore_client=None):
        assert (uid, conversation_id, owner) == (UID, CID, 'batch_sync_v1')
        assert expected_updated_at == R1 and firestore_client is client
        if outcome is None:
            if winner is not None:
                client.rows[PATH] = {**client.rows[PATH], 'record_lane_owner': winner, '_test_revision': R2}
            return None
        client.rows[PATH] = {**client.rows[PATH], 'record_lane_owner': owner, '_test_revision': outcome}
        return outcome

    return Mock(side_effect=claim)


def _acks():
    return legacy_dark.OMI_LEGACY_DARK_ACK_TOTAL.labels(reason='legacy_final_pass_rehomed')._value.get()


# --- the helper ----------------------------------------------------------------------------------


def test_stranded_owner_moves_to_batch_sync_by_the_revision_fenced_cas(monkeypatch):
    client = _client()
    claim = _cas(client)
    monkeypatch.setattr(conversations_db, 'claim_record_lane_owner', claim)
    before = _acks()
    assert rehome_final_pass_owner(UID, CID, firestore_client=client, live_jobs=lambda uid: 0) is RehomeOutcome.REHOMED
    assert claim.call_count == 1
    assert client.rows[PATH]['record_lane_owner'] == 'batch_sync_v1'
    assert _acks() == before + 1


@pytest.mark.parametrize('pending', [1, 3, None])
def test_a_live_legacy_job_for_the_uid_holds_the_owner(monkeypatch, pending):
    """Legacy jobs record no conversation id, so any live job (or an unavailable probe) holds."""
    client = _client()
    monkeypatch.setattr(conversations_db, 'claim_record_lane_owner', forbidden)
    probed = []

    def probe(uid):
        probed.append(uid)
        return pending

    assert rehome_final_pass_owner(UID, CID, firestore_client=client, live_jobs=probe) is RehomeOutcome.HELD
    assert probed == [UID]
    assert client.rows[PATH]['record_lane_owner'] == 'legacy_final_pass_v1'


@pytest.mark.parametrize('owner', ['batch_sync_v1', 'batch_live_v1'])
def test_a_batch_owner_is_idempotent_without_a_probe_or_write(monkeypatch, owner):
    client = _client(owner)
    monkeypatch.setattr(conversations_db, 'claim_record_lane_owner', forbidden)
    outcome = rehome_final_pass_owner(UID, CID, firestore_client=client, live_jobs=forbidden)
    assert outcome is RehomeOutcome.ALREADY_BATCH
    assert client.rows[PATH]['record_lane_owner'] == owner


@pytest.mark.parametrize('case', ['unowned', 'missing', 'deleted', 'account_deleting'])
def test_unowned_missing_deleted_and_deleting_accounts_are_left_alone(monkeypatch, case):
    """Privacy: a tombstone or a deleting account gets no new processing route; an unowned
    row is admission's to claim, never this helper's."""
    client = _client(None if case == 'unowned' else 'legacy_final_pass_v1')
    if case == 'missing':
        client.rows.pop(PATH)
    if case == 'deleted':
        client.rows[PATH]['deleted'] = True
    if case == 'account_deleting':
        client.rows[('account_deletions', UID)] = {'status': 'deleting'}
    monkeypatch.setattr(conversations_db, 'claim_record_lane_owner', forbidden)
    outcome = rehome_final_pass_owner(UID, CID, firestore_client=client, live_jobs=forbidden)
    assert outcome is RehomeOutcome.NOT_APPLICABLE


@pytest.mark.parametrize('winner,expected', [('legacy_final_pass_v1', 'held'), ('batch_sync_v1', 'already_batch')])
def test_a_lost_cas_is_one_attempt_then_held_or_follows_the_batch_winner(monkeypatch, winner, expected):
    """Race with a concurrent claim (a final pass starting, an edit): never a second CAS in the
    same call. A legacy winner is held, so the client retries; a batch winner is ours to follow."""
    client = _client()
    claim = _cas(client, winner=winner, outcome=None)
    monkeypatch.setattr(conversations_db, 'claim_record_lane_owner', claim)
    before = _acks()
    outcome = rehome_final_pass_owner(UID, CID, firestore_client=client, live_jobs=lambda uid: 0)
    assert outcome is RehomeOutcome(expected)
    assert claim.call_count == 1
    assert _acks() == before


def test_dry_run_passes_every_fence_and_stops_before_the_cas(monkeypatch):
    client = _client()
    monkeypatch.setattr(conversations_db, 'claim_record_lane_owner', forbidden)
    outcome = rehome_final_pass_owner(UID, CID, firestore_client=client, live_jobs=lambda uid: 0, apply=False)
    assert outcome is RehomeOutcome.ELIGIBLE
    assert client.rows[PATH]['record_lane_owner'] == 'legacy_final_pass_v1'


def test_upload_rehome_is_inert_at_legacy_sync_on():
    """``on`` is today's path byte for byte: no read, no probe, no write."""
    assert upload_rehome(LegacySyncMode.ON, UID, CID, firestore_client=forbidden) is RehomeOutcome.NOT_APPLICABLE


@pytest.mark.parametrize('mode', [LegacySyncMode.DRAINING, LegacySyncMode.DARK])
def test_upload_rehome_runs_the_helper_outside_on_after_the_flip_grace(monkeypatch, mode):
    client = _client()
    monkeypatch.setattr(conversations_db, 'claim_record_lane_owner', _cas(client))
    monkeypatch.setattr(final_pass_rehome, 'live_legacy_jobs', lambda uid: 0)
    monkeypatch.setattr(legacy_dark, 'mode_age_seconds', lambda now=None: final_pass_rehome.FLIP_GRACE_SECONDS)
    assert upload_rehome(mode, UID, CID, firestore_client=client) is RehomeOutcome.REHOMED


@pytest.mark.parametrize('age', [0, 299.0, None])
def test_upload_rehome_holds_inside_the_flip_grace_without_any_read(monkeypatch, age):
    """Review P1: a request that read ``on`` just before the flip can still create a legacy job
    after it, invisible to the probe until created. No re-home until every such request is over;
    an unknown ramp age holds too."""
    monkeypatch.setattr(legacy_dark, 'mode_age_seconds', lambda now=None: age)
    outcome = upload_rehome(LegacySyncMode.DRAINING, UID, CID, firestore_client=forbidden)
    assert outcome is RehomeOutcome.HELD
    assert upload_rehome(LegacySyncMode.DARK, UID, CID, firestore_client=forbidden, mode_age=age) is RehomeOutcome.HELD


def test_the_flip_grace_bounds_the_stale_admission_window():
    """The router re-reads a mode older than ADMISSION_REVALIDATE_SECONDS before a legacy job and the
    ramp cache refreshes within TTL_SECONDS, so no stale 'on' creates a legacy job later than their
    sum after a flip; the grace that holds re-homes must exceed it."""
    from utils.rollout.runtime_percent import TTL_SECONDS

    assert final_pass_rehome.FLIP_GRACE_SECONDS > legacy_dark.ADMISSION_REVALIDATE_SECONDS + TTL_SECONDS


def test_mode_age_reads_the_ramp_write_time_and_fails_closed(monkeypatch):
    from utils.rollout import runtime_percent

    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(runtime_percent, 'ramp_snapshot', lambda: SimpleNamespace(updated_at='2026-01-01T11:50:00Z'))
    assert legacy_dark.mode_age_seconds(now) == 600.0
    monkeypatch.setattr(runtime_percent, 'ramp_snapshot', lambda: SimpleNamespace(updated_at=None))
    assert legacy_dark.mode_age_seconds(now) is None
    monkeypatch.setattr(runtime_percent, 'ramp_snapshot', lambda: SimpleNamespace(updated_at='not-a-time'))
    assert legacy_dark.mode_age_seconds(now) is None
    monkeypatch.setattr(runtime_percent, 'ramp_snapshot', Mock(side_effect=RuntimeError('cold')))
    assert legacy_dark.mode_age_seconds(now) is None


def test_live_legacy_jobs_reads_the_pending_index_and_fails_closed(monkeypatch):
    from database import sync_jobs

    monkeypatch.setattr(sync_jobs, 'pending_sync_jobs', lambda uid: [{'id': 'sync:a'}, {'id': 'sync:b'}])
    assert final_pass_rehome.live_legacy_jobs(UID) == 2
    monkeypatch.setattr(sync_jobs, 'pending_sync_jobs', Mock(side_effect=ConnectionError('redis')))
    assert final_pass_rehome.live_legacy_jobs(UID) is None


# --- the route (registered_record_response) --------------------------------------------------------


def _route(loaded, **kwargs):
    return live_upload.registered_record_response(
        uid=UID,
        conversation_id=CID,
        content_id='wal',
        paths=[],
        source='omi',
        client_device_id=None,
        loaded_conversation=loaded,
        **kwargs,
    )


@pytest.mark.parametrize('mode', [LegacySyncMode.DRAINING, LegacySyncMode.DARK])
async def test_dark_upload_for_a_stranded_final_pass_owner_no_longer_loops(monkeypatch, mode):
    """The 409 loop: before the re-home both uploads route LEGACY and the owner never changes.
    Now the first upload re-homes and routes BATCH; the second follows the batch owner directly.
    (With live admission off the route does no owner read and batch intake re-homes instead.)"""
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'true')
    client = _client()
    claim = _cas(client)
    monkeypatch.setattr(conversations_db, 'claim_record_lane_owner', claim)
    monkeypatch.setattr(final_pass_rehome, 'live_legacy_jobs', lambda uid: 0)
    monkeypatch.setattr(legacy_dark, 'mode_age_seconds', lambda now=None: final_pass_rehome.FLIP_GRACE_SECONDS)
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: SimpleNamespace(client=client))
    assert await _route(None, legacy_mode=mode) is RecordUploadRoute.BATCH
    assert client.rows[PATH]['record_lane_owner'] == 'batch_sync_v1'
    assert await _route(None, legacy_mode=mode) is RecordUploadRoute.BATCH
    assert claim.call_count == 1


@pytest.mark.parametrize('outcome', [RehomeOutcome.HELD, RehomeOutcome.NOT_APPLICABLE])
async def test_a_held_rehome_keeps_the_legacy_route_so_the_fence_acks(monkeypatch, outcome):
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: SimpleNamespace(client=object()))
    monkeypatch.setattr(final_pass_rehome, 'upload_rehome', lambda *a, **k: outcome)
    loaded = {'record_lane_owner': 'legacy_final_pass_v1'}
    assert await _route(loaded, legacy_mode=LegacySyncMode.DARK) is RecordUploadRoute.LEGACY


async def test_the_route_is_unchanged_at_legacy_sync_on(monkeypatch):
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: SimpleNamespace(client=object()))
    monkeypatch.setattr(final_pass_rehome, 'rehome_final_pass_owner', forbidden)
    monkeypatch.setattr(legacy_dark, 'mode_age_seconds', forbidden)
    loaded = {'record_lane_owner': 'legacy_final_pass_v1'}
    assert await _route(loaded, legacy_mode=LegacySyncMode.ON) is RecordUploadRoute.LEGACY


async def test_the_route_reads_the_mode_off_the_loop_when_the_caller_has_none(monkeypatch):
    """Batch intake's record_router call passes no mode: read it as the router does."""
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: SimpleNamespace(client=object()))
    monkeypatch.setattr(legacy_dark, 'current_mode', lambda: LegacySyncMode.DARK)
    seen = []
    monkeypatch.setattr(
        final_pass_rehome, 'upload_rehome', lambda mode, *a, **k: seen.append(mode) or RehomeOutcome.REHOMED
    )
    loaded = {'record_lane_owner': 'legacy_final_pass_v1'}
    assert await _route(loaded) is RecordUploadRoute.BATCH
    assert seen == [LegacySyncMode.DARK]


# --- no new legacy final-pass owner outside on (M3 re-review scope add) ----------------------------


def _narrowed_policy():
    from dataclasses import replace

    from config.policy import resolve_batch_policy

    return replace(resolve_batch_policy(UID), batch_enabled=False, live_admission_enabled=True)


@pytest.mark.parametrize('mode', [LegacySyncMode.DRAINING, LegacySyncMode.DARK])
async def test_an_ownerless_upload_for_a_narrowed_uid_takes_batch_outside_on(monkeypatch, mode):
    """The ownerless-upload claim picked legacy_final_pass_v1 whenever the uid's batch policy
    was off (owner-load narrowing), minting new stranded owners after the gate. Outside ``on``
    it claims batch_sync_v1: intake widens a narrowed upload onto batch anyway."""
    client = _client(None, status='completed')
    claimed = []
    monkeypatch.setattr(
        live_upload, 'claim_record_lane_owner', lambda uid, cid, owner, expected, **kw: claimed.append(owner) or R2
    )
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: SimpleNamespace(client=client))
    monkeypatch.setattr(live_upload, 'record_capture_eligible', lambda *a, **k: False)
    assert await _route(None, legacy_mode=mode, policy=_narrowed_policy()) is RecordUploadRoute.BATCH
    assert claimed == ['batch_sync_v1']


async def test_an_ownerless_upload_for_a_narrowed_uid_still_takes_legacy_at_on(monkeypatch):
    client = _client(None, status='completed')
    claimed = []
    monkeypatch.setattr(
        live_upload, 'claim_record_lane_owner', lambda uid, cid, owner, expected, **kw: claimed.append(owner) or R2
    )
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: SimpleNamespace(client=client))
    monkeypatch.setattr(live_upload, 'record_capture_eligible', lambda *a, **k: False)
    monkeypatch.setattr(legacy_dark, 'current_mode', forbidden)  # the caller's mode is used, never a read
    assert await _route(None, legacy_mode=LegacySyncMode.ON, policy=_narrowed_policy()) is RecordUploadRoute.LEGACY
    assert claimed == ['legacy_final_pass_v1']


@pytest.mark.parametrize('mode', [LegacySyncMode.DRAINING, LegacySyncMode.DARK])
@pytest.mark.parametrize('live_admission', ['true', 'false'])
def test_the_shadow_final_pass_takes_no_new_owner_outside_on(monkeypatch, mode, live_admission):
    """transcription_shadow._claim_shadow_owner claimed legacy_final_pass_v1 without reading the
    mode. Outside ``on`` an unowned conversation gets no claim and no pass (it stays unowned for
    batch admission); an owner that already exists keeps its pass until the next upload re-homes it."""
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', live_admission)
    monkeypatch.setattr(legacy_dark, 'current_mode', lambda: mode)
    monkeypatch.setattr(shadow.conversations_db, 'claim_record_lane_owner', forbidden)
    monkeypatch.setattr(shadow.conversations_db, 'get_conversation', forbidden)
    assert shadow._claim_shadow_owner(UID, CID, {'id': CID, 'updated_at': 1}) is None
    owned = {'id': CID, 'record_lane_owner': 'legacy_final_pass_v1', 'updated_at': 1}
    assert shadow._claim_shadow_owner(UID, CID, owned) is owned


def test_the_shadow_final_pass_claims_as_before_at_on(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'true')
    monkeypatch.setattr(legacy_dark, 'current_mode', lambda: LegacySyncMode.ON)
    claim = Mock(return_value=2)
    monkeypatch.setattr(shadow.conversations_db, 'claim_record_lane_owner', claim)
    result = shadow._claim_shadow_owner(UID, CID, {'id': CID, 'updated_at': 1})
    assert result['record_lane_owner'] == 'legacy_final_pass_v1' and claim.call_count == 1


# --- the operator sweep --------------------------------------------------------------------------


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def where(self, *, filter):
        field, op, value = filter.field_path, filter.op_string, filter.value

        def matches(row):
            stored = row['data'].get(field)
            if op == '==':
                return stored == value
            if op == '>=':
                return stored is not None and stored >= value
            raise AssertionError(f'unsupported filter {op}')

        return _Query([row for row in self._rows if matches(row)])

    def limit(self, count):
        return _Query(self._rows[:count])

    def stream(self):
        for row in self._rows:
            snapshot = SimpleNamespace(
                exists=True,
                to_dict=lambda data=row['data']: dict(data),
                reference=SimpleNamespace(path=row['path']),
            )
            yield snapshot


class _SweepClient:
    """collection_group('conversations') plus each user's ledger, enough for the sweep."""

    def __init__(self, conversations, ledgers):
        self._conversations = conversations
        self._ledgers = ledgers

    def collection_group(self, name):
        assert name == 'conversations'
        return _Query(self._conversations)

    def collection(self, name):
        assert name == 'users'
        client = self

        class _Users:
            def document(self, uid):
                class _User:
                    def collection(self, ledger):
                        assert ledger == 'sync_content_ledger'
                        return _Query([{'path': '', 'data': row} for row in client._ledgers.get(uid, [])])

                return _User()

        return _Users()


def _conversation(uid, cid, owner='legacy_final_pass_v1'):
    return {'path': f'users/{uid}/conversations/{cid}', 'data': {'record_lane_owner': owner}}


def test_sweep_counts_each_outcome_and_is_clear_only_when_nothing_remains(monkeypatch):
    from scripts.legacy_dark import final_pass_rehome as sweep_module

    client = _SweepClient(
        [
            _conversation('u1', 'a'),
            _conversation('u1', 'b'),
            _conversation('u2', 'c'),
            {'path': 'users/u3/folders/f/conversations/d', 'data': {'record_lane_owner': 'legacy_final_pass_v1'}},
        ],
        {},
    )
    outcomes = {('u1', 'a'): RehomeOutcome.REHOMED, ('u1', 'b'): RehomeOutcome.ALREADY_BATCH}
    seen = []

    def rehome(uid, conversation_id, *, firestore_client, live_jobs, apply):
        seen.append((uid, conversation_id, apply))
        assert firestore_client is client and live_jobs is probe
        return outcomes.get((uid, conversation_id), RehomeOutcome.HELD)

    probe = lambda uid: 0  # noqa: E731
    monkeypatch.setattr(sweep_module, 'rehome_final_pass_owner', rehome)
    result = sweep_module.sweep(client, apply=True, probe=probe)
    assert seen == [('u1', 'a', True), ('u1', 'b', True), ('u2', 'c', True)]
    assert result['scanned'] == 4 and result['verdict'] == 'REMAINING'
    assert result['counts'] == {'already_batch': 1, 'held': 1, 'rehomed': 1, 'skipped_shape': 1}
    assert result['remaining_stranded'] == 1

    outcomes[('u2', 'c')] = RehomeOutcome.REHOMED
    assert sweep_module.sweep(client, apply=True, probe=probe)['verdict'] == 'CLEAR'


def test_sweep_dry_run_never_writes_and_counts_eligible_as_remaining(monkeypatch):
    from scripts.legacy_dark import final_pass_rehome as sweep_module

    client = _SweepClient([_conversation('u1', 'a')], {})
    applied = []
    monkeypatch.setattr(
        sweep_module,
        'rehome_final_pass_owner',
        lambda uid, cid, **kwargs: applied.append(kwargs['apply']) or RehomeOutcome.ELIGIBLE,
    )
    result = sweep_module.sweep(client, apply=False, probe=lambda uid: 0, limit=5)
    assert applied == [False]
    assert result['counts'] == {'eligible': 1} and result['verdict'] == 'REMAINING'
    assert result['truncated'] is False


def test_a_capped_sweep_is_partial_never_clear(monkeypatch):
    """Review P2: ``--apply --limit 1`` over 20 owners re-homed one and said CLEAR."""
    from scripts.legacy_dark import final_pass_rehome as sweep_module

    client = _SweepClient([_conversation('u1', 'a'), _conversation('u1', 'b')], {})
    monkeypatch.setattr(sweep_module, 'rehome_final_pass_owner', lambda *a, **k: RehomeOutcome.REHOMED)
    result = sweep_module.sweep(client, apply=True, probe=lambda uid: 0, limit=1)
    assert result['scanned'] == 1 and result['counts'] == {'rehomed': 1}
    assert result['truncated'] is True and result['verdict'] == 'PARTIAL'


def test_ledger_probe_counts_active_retryable_and_recent_legacy_rows_fresh_each_call():
    """The operator shell has no Redis: an ACTIVE legacy processing claim, a retryable legacy
    row, or any row created inside the quiet window holds the uid; batch and cap-hold rows,
    stale claims and completions do not. Review P1: nothing is cached, the sweep runs beside
    live legacy admission."""
    from scripts.legacy_dark import final_pass_rehome as sweep_module

    now = datetime(2026, 1, 10, tzinfo=timezone.utc)
    old = datetime(2025, 1, 1, tzinfo=timezone.utc)
    fresh = {'status': 'processing', 'job_id': 'legacy-1', 'updated_at': now, 'created_at': old}
    stale = {'status': 'processing', 'job_id': 'legacy-2', 'updated_at': old, 'created_at': old}
    batch = {'status': 'processing', 'job_id': 'bp_1', 'dispatch_protocol': 'batch_v1', 'updated_at': now}
    held = {'status': 'held', 'job_id': 'hold', 'dispatch_protocol': 'stt_cap_hold_v1'}
    retryable = {'status': 'retryable', 'job_id': 'legacy-3', 'created_at': old}
    just_admitted = {'status': 'completed', 'job_id': 'legacy-4', 'created_at': now - timedelta(seconds=30)}
    recent_batch = {'status': 'completed', 'dispatch_protocol': 'batch_v1', 'created_at': now - timedelta(seconds=30)}
    recent_hold = {'status': 'held', 'dispatch_protocol': 'stt_cap_hold_v1', 'created_at': now - timedelta(seconds=5)}
    ledgers = {
        'u1': [fresh, stale, batch, held, retryable],
        'u2': [stale, batch],
        'u3': [just_admitted],
        'u4': [recent_batch, recent_hold],  # review P2: batch traffic alone never holds a uid
    }
    client = _SweepClient([], ledgers)
    probe = sweep_module.ledger_live_jobs(client, now=now)
    assert probe('u1') == 2
    assert probe('u2') == 0
    assert probe('u3') == 1
    assert probe('u4') == 0
    ledgers['u2'].append(dict(fresh))  # a job started while the sweep was running
    assert probe('u2') == 1


@pytest.mark.parametrize(
    'mode,age,refused',
    [
        ('on', 10_000, True),
        (None, None, True),
        ('draining', None, True),
        ('draining', 299, True),
        ('draining', 300, False),
        ('dark', 86_400, False),
    ],
)
def test_apply_runs_only_in_draining_or_dark_past_the_flip_grace(mode, age, refused):
    """Review P1: at ``on`` the sweep cannot serialize with live legacy admission; applied only
    once admission is quiesced (the router re-validates its mode read before any legacy job)."""
    from scripts.legacy_dark import final_pass_rehome as sweep_module

    assert (sweep_module.apply_refusal(mode, age) is not None) is refused


def test_served_ramp_reads_the_env_entry_and_its_age(monkeypatch):
    from database import rollout_cohorts as store
    from scripts.legacy_dark import final_pass_rehome as sweep_module

    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    document = {'envs': {'prod': {'legacy_sync': 'draining', 'updated_at': '2026-01-01T11:55:00Z'}}}
    monkeypatch.setattr(store, 'read_ramp', lambda **kwargs: document)
    assert sweep_module.served_ramp(object(), 'prod', now=now) == ('draining', 300.0)
    assert sweep_module.served_ramp(object(), 'staging', now=now) == (None, None)
    monkeypatch.setattr(store, 'read_ramp', lambda **kwargs: None)
    assert sweep_module.served_ramp(object(), 'prod', now=now) == (None, None)


def test_main_refuses_apply_at_on_before_touching_a_conversation(monkeypatch, capsys):
    from google.cloud import firestore
    from scripts.legacy_dark import final_pass_rehome as sweep_module

    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.setattr(firestore, 'Client', lambda **kwargs: object())
    monkeypatch.setattr(sweep_module, 'served_ramp', lambda client, env, now=None: ('on', 10_000.0))
    monkeypatch.setattr(sweep_module, 'sweep', forbidden)
    assert sweep_module.main(['--env', 'prod', '--apply']) == 2
    assert 'runs in draining or dark' in capsys.readouterr().err


def test_ledger_probe_fails_closed_on_a_read_error():
    from scripts.legacy_dark import final_pass_rehome as sweep_module

    broken = SimpleNamespace(collection=Mock(side_effect=RuntimeError('unavailable')))
    assert sweep_module.ledger_live_jobs(broken)('u1') is None


def test_sweep_apply_refuses_a_read_only_tier(monkeypatch, capsys):
    from scripts.legacy_dark import final_pass_rehome as sweep_module

    monkeypatch.setenv('GCP_AGENT_TIER', 'ro-prod')
    assert sweep_module.main(['--env', 'prod', '--apply']) == 2
    assert 'operator tier' in capsys.readouterr().err


# --- batch language eligibility at the ownerless-upload claim (lead 41e13b, scope 304254) ---------


def _batch_policy():
    from dataclasses import replace

    from config.policy import resolve_batch_policy

    return replace(resolve_batch_policy(UID), batch_enabled=True, live_admission_enabled=True)


async def _claim_owner(monkeypatch, language, mode):
    client = _client(None, status='completed', language=language)
    claimed = []
    monkeypatch.setattr(
        live_upload, 'claim_record_lane_owner', lambda uid, cid, owner, expected, **kw: claimed.append(owner) or R2
    )
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: SimpleNamespace(client=client))
    monkeypatch.setattr(live_upload, 'record_capture_eligible', lambda *a, **k: False)
    route = await _route(None, legacy_mode=mode, policy=_batch_policy())
    return route, claimed


async def test_a_known_unsupported_conversation_language_takes_legacy_at_on(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_LANGUAGE_ELIGIBILITY_ENABLED', raising=False)
    route, claimed = await _claim_owner(monkeypatch, 'ja', LegacySyncMode.ON)
    assert route is RecordUploadRoute.LEGACY and claimed == ['legacy_final_pass_v1']


@pytest.mark.parametrize('language', [None, '', 'multi', 'auto', 'und', 'en', 'es'])
async def test_unknown_or_supported_conversation_language_keeps_the_batch_owner_at_on(monkeypatch, language):
    monkeypatch.delenv('BATCH_PIPELINE_LANGUAGE_ELIGIBILITY_ENABLED', raising=False)
    route, claimed = await _claim_owner(monkeypatch, language, LegacySyncMode.ON)
    assert route is RecordUploadRoute.BATCH and claimed == ['batch_sync_v1']


@pytest.mark.parametrize('mode', [LegacySyncMode.DRAINING, LegacySyncMode.DARK])
async def test_a_known_unsupported_language_keeps_the_batch_owner_outside_on(monkeypatch, mode):
    monkeypatch.delenv('BATCH_PIPELINE_LANGUAGE_ELIGIBILITY_ENABLED', raising=False)
    route, claimed = await _claim_owner(monkeypatch, 'ja', mode)
    assert route is RecordUploadRoute.BATCH and claimed == ['batch_sync_v1']


async def test_eligibility_kill_switch_off_restores_the_batch_owner_at_on(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_ELIGIBILITY_ENABLED', 'false')
    route, claimed = await _claim_owner(monkeypatch, 'ja', LegacySyncMode.ON)
    assert route is RecordUploadRoute.BATCH and claimed == ['batch_sync_v1']
