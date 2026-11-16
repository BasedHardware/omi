"""Synthetic heartbeat fencing, compatibility, policy and projection regressions."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock
from types import SimpleNamespace
from testing.pipeline_sim.store import SimTransaction

import pytest
from google.api_core.exceptions import Aborted, ServiceUnavailable

from database.batch_pipeline_store import FirestoreStore
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_batch_backlog_release import METER, RELEASE, NOW, merge, put, ready, tokens
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline import backlog_release as gate, serving
from config.batch_pipeline_backlog_release import WriterConfig, PREFIX
from utils.batch_pipeline.backlog_heartbeat import HeartbeatAuthority, LEASE_KEY
from utils.batch_pipeline.scheduler import owner_key, _OwnWrites


@pytest.fixture(autouse=True)
def switches(monkeypatch):
    monkeypatch.delenv(METER, raising=False)
    monkeypatch.delenv(RELEASE, raising=False)


def authority(store, *, now=NOW, config=None):
    return HeartbeatAuthority(
        store, clock=lambda: now, config=lambda: config or WriterConfig(True, 'open', 2, 0, 'all')
    )


def row(store):
    return store.run(lambda tx: tx.get('backlog_release', 'gate'))


def test_disabled_default_does_not_even_read_store():
    store = Mock()
    assert not HeartbeatAuthority(store, config=WriterConfig).tick()
    store.run.assert_not_called()


def test_single_writer_even_when_ticks_race_and_advisory_lease_is_off(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_LEADER_LEASE_ENABLED', 'false')
    store = MemoryStore()
    writers = [authority(store), authority(store)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda writer: writer.tick(), writers)) == [False, True]
    assert row(store)['tokens_used'] == 0
    assert store.rows['leases', LEASE_KEY]['fence'] == 1


def test_takeover_waits_for_old_gate_to_expire_then_fences_old_writer():
    store = MemoryStore()
    first = authority(store)
    assert first.tick()
    second = authority(store, now=NOW + 121)
    assert not second.tick()  # Lease expired, but the previous clock's gate is still fresh.
    second.clock = lambda: NOW + 180
    assert second.tick()
    assert store.rows['leases', LEASE_KEY]['fence'] == 2
    first.clock = lambda: NOW + 181
    assert not first.tick()
    assert row(store)['updated_at'] == NOW + 180


def test_token_preservation_interleaves_commits_and_hour_roll():
    store = MemoryStore()
    writer = authority(store)
    for name in ('a', 'b', 'c'):
        ready(store, name)
    assert writer.tick()
    assert merge(store) and tokens(store) == 1
    writer.clock = lambda: NOW + 20
    assert writer.tick() and tokens(store) == 1
    assert merge(store, NOW + 20) and tokens(store) == 2
    writer.clock = lambda: NOW + 40
    assert writer.tick() and merge(store, NOW + 40) is None
    next_hour = (int(NOW // 3600) + 1) * 3600
    writer.clock = lambda: next_hour
    assert writer.tick() and tokens(store) == 2  # Heartbeat never resets the durable count.
    assert merge(store, next_hour) and tokens(store) == 1
    assert row(store)['window'] == int(next_hour // 3600)


def test_stopping_heartbeat_closes_at_exactly_180_seconds():
    store = MemoryStore()
    ready(store, 'a')
    assert authority(store).tick()
    assert merge(store, NOW + 180) is None
    assert tokens(store) == 0
    assert merge(store, NOW + 179)


@pytest.mark.parametrize('error', [ServiceUnavailable('synthetic'), Aborted('synthetic')])
def test_any_store_error_latches_writer_off_until_restart(error):
    store = MemoryStore()
    writer = authority(store)
    assert writer.tick()
    before = deepcopy(store.rows)
    run = store.run
    store.run = Mock(side_effect=error)
    with pytest.raises(type(error)):
        writer.tick()
    store.run = run
    assert not writer.tick() and store.rows == before


def test_ambiguous_commit_reply_never_retries_heartbeat():
    store = MemoryStore()
    run = store.run

    def lost_reply(body):
        run(body)
        raise ServiceUnavailable('synthetic lost acknowledgement')

    store.run = lost_reply
    writer = authority(store)
    with pytest.raises(ServiceUnavailable):
        writer.tick()
    store.run = run
    assert row(store)['updated_at'] == NOW
    assert not writer.tick()
    assert not authority(store, now=NOW + 121).tick()


def test_transaction_retry_reloads_tokens_instead_of_resetting_them():
    store = MemoryStore()
    writer = authority(store)
    assert writer.tick()
    run = store.run
    fired = False

    def retry(body):
        nonlocal fired
        if not fired:
            fired = True

            def abort(tx):
                body(tx)
                raise Aborted('synthetic')

            with pytest.raises(Aborted):
                run(abort)
            run(lambda tx: tx.patch('backlog_release', 'gate', {'tokens_used': 1}))
        return run(body)

    store.run = retry
    writer.clock = lambda: NOW + 20
    assert writer.tick()
    assert row(store)['tokens_used'] == 1


@pytest.mark.parametrize('reach', [-1, 1, 86400, 30 * 86400 - 1, True, 30.0 * 86400])
def test_invalid_reach_refuses_to_start(reach):
    store = Mock()
    writer = authority(store, config=WriterConfig(True, 'open', 2, reach, 'all'))
    with pytest.raises(ValueError):
        writer.tick()
    store.run.assert_not_called()
    assert writer.failed


@pytest.mark.parametrize('reach', [0, 30 * 86400, 31 * 86400])
def test_safe_reach(reach):
    assert WriterConfig(reach_seconds=reach).validate()


@pytest.mark.parametrize(
    'values',
    [
        {'state': 'unknown'},
        {'rate_per_hour': -1},
        {'rate_per_hour': True},
        {'mode': 'priority'},
        {'owner_keys': ('raw-identifier',)},
        {'owner_keys': ('a' * 64,) * 2},
        {'owner_keys': tuple(f'{i:064x}' for i in range(101))},
    ],
)
def test_invalid_policy_is_rejected_without_identifiers_in_error(values):
    with pytest.raises(ValueError, match='^invalid backlog heartbeat configuration$'):
        replace(WriterConfig(), **values).validate()


def test_env_config_is_disabled_closed_by_default_and_validates_reach(monkeypatch):
    for suffix in ('WRITER', 'STATE', 'RATE_PER_HOUR', 'REACH_SECONDS', 'MODE', 'OWNER_KEYS'):
        monkeypatch.delenv(PREFIX + suffix, raising=False)
    assert WriterConfig.from_env() == WriterConfig()
    monkeypatch.setenv(PREFIX + 'WRITER', 'enabled')
    monkeypatch.setenv(PREFIX + 'STATE', 'open')
    monkeypatch.setenv(PREFIX + 'REACH_SECONDS', '86400')
    with pytest.raises(ValueError):
        WriterConfig.from_env()


@pytest.mark.parametrize('mode,allowed', [('allowlist_only', False), ('all', True)])
def test_allowlist_exclusive_and_all_modes(mode, allowed, monkeypatch, caplog):
    store = MemoryStore()
    ready(store, 'support', owner='synthetic-support')
    ready(store, 'other', owner='synthetic-other')
    config = WriterConfig(True, 'open', 2, 0, mode, (owner_key('synthetic-support'),))
    assert authority(store, config=config).tick()
    hits, grants = Mock(), Mock()
    monkeypatch.setattr(gate, 'ALLOWLIST_HITS', hits)
    monkeypatch.setattr(gate, 'TOKENS_GRANTED', grants)
    assert bool(merge(store, owner='synthetic-other')) is allowed
    assert merge(store, owner='synthetic-support')
    hits.inc.assert_called_once()
    assert grants.inc.call_count == 1 + int(allowed)
    assert 'synthetic-support' not in caplog.text and config.owner_keys[0] not in caplog.text


def test_empty_exclusive_allowlist_releases_nothing():
    store = MemoryStore()
    ready(store, 'a')
    assert authority(store, config=WriterConfig(True, 'open', 2)).tick()
    assert merge(store) is None and tokens(store) == 0


@pytest.mark.parametrize('depth', [0, 1, 16])
def test_projection_headroom_even_with_catch_up_switch_off(depth, monkeypatch):
    store = MemoryStore()
    ready(store, 'a')
    assert authority(store).tick()
    limit = depth or 16
    put(store, 'owners', owner_key('synthetic'), {'log_sequence': limit})
    refused = Mock()
    monkeypatch.setattr(gate, 'REFUSED', refused)
    assert merge(store, depth=depth) is None and tokens(store) == 0
    refused.labels.assert_called_with('projection')
    put(
        store,
        'results',
        'projected',
        {
            'log_sequence': limit,
            'segment_id': 'projected',
            'owner_key': owner_key('synthetic'),
            'owner_id': 'synthetic',
        },
    )
    put(
        store,
        'owners',
        owner_key('synthetic'),
        {'log_sequence': limit, 'projection_watermark': 'projected', 'log_tail': 'projected'},
    )
    assert merge(store, depth=depth) and tokens(store) == 1


@pytest.mark.parametrize('sequence', [None, -1, '1', True, 10])
def test_unknown_or_invalid_projection_watermark_is_closed(sequence):
    store = MemoryStore()
    ready(store, 'a')
    assert authority(store).tick()
    put(
        store,
        'owners',
        owner_key('synthetic'),
        {'log_sequence': 2, 'projection_watermark': 'missing', 'log_tail': 'tail'},
    )
    if sequence is not None:
        put(
            store,
            'results',
            'missing',
            {
                'log_sequence': sequence,
                'segment_id': 'missing',
                'owner_key': owner_key('synthetic'),
                'owner_id': 'synthetic',
            },
        )
    assert merge(store) is None and tokens(store) == 0


@pytest.mark.parametrize('switch', [RELEASE, METER])
def test_writer_and_committer_kill_switches(switch, monkeypatch):
    store = MemoryStore()
    ready(store, 'a')
    monkeypatch.setenv(switch, 'false')
    assert authority(store).tick()
    assert row(store)['state'] == 'closed'
    assert merge(store) is None and tokens(store) == 0


def test_closed_config_preserves_used_tokens():
    store = MemoryStore()
    writer = authority(store)
    ready(store, 'a')
    ready(store, 'b')
    assert writer.tick() and merge(store)
    writer.config = lambda: WriterConfig(True, 'closed', 2, 0, 'all')
    assert writer.tick()
    assert tokens(store) == 1 and merge(store) is None


@pytest.mark.parametrize('value', ['true', '1', 'on', 'yes'])
def test_writer_refuses_legacy_true_instead_of_using_unmetered_path(value, monkeypatch):
    monkeypatch.setenv(RELEASE, value)
    store = Mock()
    with pytest.raises(ValueError, match='legacy unmetered'):
        authority(store).tick()
    store.run.assert_not_called()


@pytest.mark.parametrize('change', [{'tokens_used': 'bad'}, {'extra': 1}, {'updated_at': NOW + 1}])
def test_bad_existing_gate_or_regressing_clock_is_never_repaired_by_reset(change):
    store = MemoryStore()
    writer = authority(store)
    assert writer.tick()
    store.rows['backlog_release', 'gate'].update(change)
    before = deepcopy(store.rows)
    with pytest.raises(ValueError):
        writer.tick()
    assert store.rows == before


def test_real_firestore_adapter_reads_before_writes_and_preserves_gate(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    store = FirestoreStore('batch_pipeline_dev', firestore_client=StrictFirestore())
    writer = authority(store)
    assert writer.tick()
    store.run(lambda tx: tx.put('backlog_release', 'gate', {**tx.get('backlog_release', 'gate'), 'tokens_used': 1}))
    writer.clock = lambda: NOW + 20
    assert writer.tick() and row(store)['tokens_used'] == 1


def test_frozen_old_reader_rejects_versioned_gate_instead_of_releasing_unlisted_owner():
    from tests.unit.fixtures.backlog_gate_v1 import Gate as OldGate

    store = MemoryStore()
    assert authority(store).tick()
    versioned = row(store)
    assert gate.Gate.parse(versioned) is not None
    assert OldGate.parse(versioned) is None
    old = {name: versioned[name] for name in gate.FIELDS}
    assert OldGate.parse(old) is not None  # Discriminates old-reader refusal from a broken fixture.


@pytest.mark.parametrize(
    'fields',
    [
        {'schema_version': 1},
        {'schema_version': True},
        {'schema_version': 3},
        {'mode': 'priority'},
        {'owner_keys': ['raw-identifier']},
        {'extra': True},
        {'reach_seconds': 86400},
    ],
)
def test_malformed_versioned_document_closes(fields):
    store = MemoryStore()
    ready(store, 'a')
    assert authority(store).tick()
    store.rows['backlog_release', 'gate'].update(fields)
    assert merge(store) is None and tokens(store) == 0


async def test_supervisor_exits_on_error_and_never_retries(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    async def immediate(executor, fn, *args):
        return fn(*args)

    store = Mock(run=Mock(side_effect=ServiceUnavailable('synthetic')))
    monkeypatch.setattr(serving, 'run_blocking', immediate)
    monkeypatch.setattr(serving, 'current_stage', lambda: 'dev')
    monkeypatch.setattr(serving, 'serving_for_stage', lambda _: SimpleNamespace(store=store))
    monkeypatch.setenv(PREFIX + 'WRITER', 'enabled')
    await serving._supervise_backlog_heartbeat(asyncio.Event())
    store.run.assert_called_once()


def test_deleted_gate_cannot_reset_current_hour_tokens():
    store = MemoryStore()
    writer = authority(store)
    assert writer.tick()
    del store.rows['backlog_release', 'gate']
    with pytest.raises(ValueError, match='missing backlog gate'):
        writer.tick()
    assert ('backlog_release', 'gate') not in store.rows


@pytest.mark.parametrize('document', [{}, {'tokens_used': 1}])
def test_strict_firestore_existing_empty_or_partial_gate_latches_closed(document, monkeypatch):
    """Reviewer reproduction: an existing {} must never be initialized as an absent gate."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    store = FirestoreStore('batch_pipeline_dev', firestore_client=StrictFirestore())
    store.run(lambda tx: tx.put('backlog_release', 'gate', document))
    writer = authority(store)
    with pytest.raises(ValueError, match='invalid existing backlog gate'):
        writer.tick()
    assert writer.failed and not writer.tick()
    assert row(store) == document
    assert store.run(lambda tx: tx.get_existing('leases', LEASE_KEY)) is None


@pytest.mark.parametrize(
    'change',
    [
        {'owner_key': owner_key('different-owner'), 'owner_id': 'different-owner'},
        {'owner_key': None},
        {'owner_id': None},
        {'owner_id': 'different-owner'},
        {'segment_id': None},
        {'segment_id': 'different-segment'},
        {'log_sequence': 0},
        {'log_sequence': True},
        {'log_sequence': 3},
    ],
)
def test_projection_watermark_requires_matching_owner_and_segment(change, monkeypatch):
    store = MemoryStore()
    ready(store, 'a')
    assert authority(store).tick()
    put(
        store,
        'owners',
        owner_key('synthetic'),
        {
            'log_sequence': 2,
            'projection_watermark': 'projected',
            'log_tail': 'projected',
        },
    )
    result = {
        'log_sequence': 2,
        'segment_id': 'projected',
        'owner_key': owner_key('synthetic'),
        'owner_id': 'synthetic',
    }
    for field, value in change.items():
        if value is None:
            result.pop(field)
        else:
            result[field] = value
    put(store, 'results', 'projected', result)
    refused = Mock()
    monkeypatch.setattr(gate, 'REFUSED', refused)
    assert merge(store) is None and tokens(store) == 0
    refused.labels.assert_called_with('projection')


@pytest.mark.parametrize('tail,allowed', [('projected', True), ('other', False), (None, False)])
def test_projection_sequence_equal_requires_watermark_at_owner_log_tail(tail, allowed):
    store = MemoryStore()
    ready(store, 'a')
    assert authority(store).tick()
    put(
        store,
        'owners',
        owner_key('synthetic'),
        {
            'log_sequence': 2,
            'projection_watermark': 'projected',
            'log_tail': tail,
        },
    )
    put(
        store,
        'results',
        'projected',
        {
            'log_sequence': 2,
            'segment_id': 'projected',
            'owner_key': owner_key('synthetic'),
            'owner_id': 'synthetic',
        },
    )
    assert bool(merge(store)) is allowed
    assert tokens(store) == int(allowed)


@pytest.mark.parametrize('adapter', ['firestore', 'simulator', 'scheduler'])
def test_existence_read_preserves_legacy_get_cache_and_buffered_empty_write(adapter, monkeypatch):
    def body(tx):
        assert tx.get('backlog_release', 'gate') == {}
        assert tx.get_existing('backlog_release', 'gate') is None
        tx.put('backlog_release', 'gate', {})
        assert tx.get_existing('backlog_release', 'gate') == {}

    if adapter == 'firestore':
        monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
        store = FirestoreStore('batch_pipeline_dev', firestore_client=StrictFirestore())
        store.run(body)
        store.run(lambda tx: tx.get('backlog_release', 'gate'))
        assert store.run(lambda tx: tx.get_existing('backlog_release', 'gate')) == {}
    elif adapter == 'scheduler':
        MemoryStore().run(lambda tx: body(_OwnWrites(tx)))
    else:
        body(SimTransaction(SimpleNamespace(rows={})))
        tx = SimTransaction(SimpleNamespace(rows={('backlog_release', 'gate'): {}}))
        assert tx.get('backlog_release', 'gate') == {}
        assert tx.get_existing('backlog_release', 'gate') == {}


@pytest.mark.parametrize('tail,allowed', [('tail', True), ('projected', False), (None, False)])
def test_earlier_projection_sequence_requires_a_distinct_valid_log_tail(tail, allowed):
    store = MemoryStore()
    ready(store, 'a')
    assert authority(store).tick()
    put(
        store,
        'owners',
        owner_key('synthetic'),
        {
            'log_sequence': 2,
            'projection_watermark': 'projected',
            'log_tail': tail,
        },
    )
    put(
        store,
        'results',
        'projected',
        {
            'log_sequence': 1,
            'segment_id': 'projected',
            'owner_key': owner_key('synthetic'),
            'owner_id': 'synthetic',
        },
    )
    assert bool(merge(store)) is allowed
    assert tokens(store) == int(allowed)


@pytest.fixture(params=['memory', 'firestore'])
def authority_store(request, monkeypatch):
    if request.param == 'memory':
        return MemoryStore()
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    return FirestoreStore('batch_pipeline_dev', firestore_client=StrictFirestore())


def control_documents(store):
    return store.run(
        lambda tx: {
            'lease': tx.get_existing('leases', LEASE_KEY),
            'gate': tx.get_existing('backlog_release', 'gate'),
        }
    )


@pytest.mark.parametrize('gate_exists', [False, True], ids=['absent-gate', 'fresh-gate'])
def test_empty_existing_lease_latches_without_initialization_or_takeover(authority_store, gate_exists, monkeypatch):
    store = authority_store
    if gate_exists:
        assert authority(store).tick()
        store.run(lambda tx: tx.put('backlog_release', 'gate', {**tx.get('backlog_release', 'gate'), 'tokens_used': 1}))
    store.run(lambda tx: tx.put('leases', LEASE_KEY, {}))
    before = control_documents(store)
    run = store.run
    writes = Mock()

    def observed(body):
        def check(tx):
            monkeypatch.setattr(tx, 'put', writes)
            return body(tx)

        return run(check)

    monkeypatch.setattr(store, 'run', observed)
    writer = authority(store, now=NOW + 121)  # Fresh gate still forbids a new clock, even after lease TTL.
    with pytest.raises(ValueError, match='invalid heartbeat lease'):
        writer.tick()
    assert writer.failed and not writer.tick()
    writes.assert_not_called()  # No attempted fence=1 reset or open-gate write, even if rolled back.
    monkeypatch.setattr(store, 'run', run)
    assert control_documents(store) == before
    assert before['lease'] == {}
    if gate_exists:
        assert before['gate']['tokens_used'] == 1 and before['gate']['updated_at'] == NOW
    else:
        assert before['gate'] is None


def test_absent_lease_with_existing_gate_cannot_reinitialize_fence(authority_store):
    store = authority_store
    seed = MemoryStore()
    assert authority(seed).tick()
    store.run(lambda tx: tx.put('backlog_release', 'gate', row(seed)))
    before = control_documents(store)
    writer = authority(store, now=NOW + 121)
    with pytest.raises(ValueError, match='missing heartbeat lease'):
        writer.tick()
    assert writer.failed and not writer.tick()
    assert control_documents(store) == before
    assert before['lease'] is None
