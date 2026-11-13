"""Targeted joins: the bare batch-pipeline lanes ride the shared storm damper.

Each test drives one real production lane — the privacy fence
(``advance_privacy_generation`` / ``finish_privacy_purge``), the lease
revocations (``quarantine_fenced`` / ``cancel_fenced_recovery``) and the
voice-evidence receipts (``load_reference`` / ``publish``) — with the
contention switches on and a spied process-shared damper, and freezes the
damper conversation the lane must hold. On the bare parent the lanes hand
their body to ``client.transaction()`` directly: no damper is resolved, no
consult ever fires and the SDK still owns the commit loop, so every join
assertion here is red on the parent and green on the joined lanes. The
dormancy tests pin the opposite edge: with a switch off the resolver answers
``None`` and the lane stays byte-for-byte the bare bounded ladder (the
transaction is still one bounded engine chain, never the bare SDK loop).

Failure-Class: FC-bare-batch-pipeline-lanes-collide-inside-armed-storm-window
"""

import re
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from config import batch_pipeline as config
from database import batch_pipeline_privacy as privacy
from database import batch_pipeline_quarantine_recovery as quarantine_recovery
from database import batch_pipeline_recovery as recovery
from database import batch_pipeline_store as storage
from database import batch_voice_evidence as voice
from database.firestore_transaction_retry import FirestoreContentionExhausted
from tests.unit.batch_lane_storm_gate_grid_harness import ChainSleepRecorder, silence_and_pin_chain
from utils.batch_pipeline.contracts import Priority, WorkItem

ARM_WINDOW_SECONDS = 1.25
DEFAULT_GENERATION = 4
NAMESPACE = 'batch_pipeline_dev'


class ScriptedStormDamper(storage._ContentionStormDamper):
    """The real damper class with every boundary answer scripted and recorded."""

    def __init__(self, *, entry_wait=0.0, residual_schedule=(0.0,), wave_wait=0.5, arm_window=ARM_WINDOW_SECONDS):
        self.slept = []
        super().__init__(sleeper=self._record_sleep)
        self.residual_schedule = list(residual_schedule)
        self.wave_wait = wave_wait
        self.entry_wait = entry_wait
        self.arm_wait = arm_window
        self.events = []
        self.consult_clients = []
        self.arm_clients = []
        self.note_success_args = []
        self.peeks = 0

    def _record_sleep(self, seconds):
        self.slept.append(round(seconds, 9))

    def consult(self, label, *, client=None):
        self.events.append(['consult', label, self.entry_wait])
        self.consult_clients.append(client)
        if self.entry_wait > 0.0:
            self._sleeper(self.entry_wait)
        return self.entry_wait, DEFAULT_GENERATION

    def peek(self, label, *, client=None):
        rung = self.peeks + 1
        self.peeks = rung
        residual = self.residual_schedule[min(rung, len(self.residual_schedule)) - 1]
        self.events.append(['peek', label, residual])
        return residual, DEFAULT_GENERATION

    def wave_rung_wait(self, failed_attempt):
        self.events.append(['wave', failed_attempt, self.wave_wait])
        return self.wave_wait

    def arm(self, label, *, client=None):
        self.events.append(['arm', label, self.arm_wait])
        self.arm_clients.append(client)
        return self.arm_wait

    def note_success(self, label, generation):
        self.events.append(['note_success', label, generation])
        self.note_success_args.append([label, generation])


class AbortThenCommitTx:
    """A transaction that commits on the first try, recording its construction."""

    _max_attempts = 1
    _read_only = False
    _id = None

    def __init__(self):
        self.commits = 0

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = b'synthetic'

    def _commit(self):
        self.commits += 1
        self._id = None

    def _rollback(self):
        self._id = None

    def set(self, *args, **kwargs):
        self.writes = getattr(self, 'writes', 0) + 1

    def update(self, *args, **kwargs):
        self.writes = getattr(self, 'writes', 0) + 1

    def delete(self, *args, **kwargs):
        self.writes = getattr(self, 'writes', 0) + 1


def make_client(transaction_calls=None):
    client = Mock()

    def _transaction(*args, **kwargs):
        if transaction_calls is not None:
            transaction_calls.append(kwargs)
        return AbortThenCommitTx()

    client.transaction.side_effect = _transaction
    return client


def pin_engine(monkeypatch):
    """Pin the retry engine's wall-clock edges: sleeps recorded, never slept."""
    silence_and_pin_chain(monkeypatch, ChainSleepRecorder())


def stub_doc(client, doc):
    client.collection.return_value.document.return_value.get.return_value = Mock(to_dict=lambda: doc)


def switches_on(monkeypatch):
    # Both names matter: storage resolved the switches at import time, the
    # purge resolver reads them lazily from config.
    for module in (config, storage):
        monkeypatch.setattr(module, 'contention_retry_enabled', lambda: True)
        monkeypatch.setattr(module, 'contention_storm_damper_enabled', lambda: True)


def switches_off(monkeypatch):
    for module in (config, storage):
        monkeypatch.setattr(module, 'contention_retry_enabled', lambda: False)
        monkeypatch.setattr(module, 'contention_storm_damper_enabled', lambda: False)


def spy_shared_damper(monkeypatch, scripted):
    """Bind the process-shared resolver to one scripted damper, recording keys."""
    keys = []

    def factory(key):
        keys.append(key)
        return scripted

    monkeypatch.setattr(storage, 'shared_storm_damper', factory)
    return keys


def aborting_body(aborts):
    calls = []

    def body(transaction):
        calls.append(len(calls) + 1)
        if len(calls) <= aborts:
            raise Aborted('synthetic read contention')
        return 'committed'

    return body, calls


def test_advance_consults_the_privacy_partition_damper(monkeypatch):
    switches_on(monkeypatch)
    scripted = ScriptedStormDamper(entry_wait=0.4)
    keys = spy_shared_damper(monkeypatch, scripted)
    client = make_client()
    stub_doc(client, {})

    generation = privacy.advance_privacy_generation(client, 'uid-a', blocked=True)

    assert generation == 1
    assert keys == ['batch_pipeline_privacy']
    assert scripted.events == [
        ['consult', 'batch_privacy_generation_advance', 0.4],
        ['note_success', 'batch_privacy_generation_advance', DEFAULT_GENERATION],
    ]
    assert scripted.consult_clients == [client]
    assert scripted.slept == [0.4]


def test_advance_arms_the_partition_window_on_exhaustion(monkeypatch):
    switches_on(monkeypatch)
    scripted = ScriptedStormDamper(residual_schedule=(0.0,), wave_wait=1.25)
    spy_shared_damper(monkeypatch, scripted)
    client = make_client()
    reads = []

    def aborting_get(*args, **kwargs):
        reads.append(len(reads) + 1)
        raise Aborted('synthetic read contention')

    client.collection.return_value.document.return_value.get.side_effect = aborting_get

    with pytest.raises(FirestoreContentionExhausted) as error:
        pin_engine(monkeypatch)
        privacy.advance_privacy_generation(client, 'uid-a', blocked=True)
    assert error.value.retry_after == ARM_WINDOW_SECONDS
    # One body execution per outer attempt: the bounded engine owns every
    # retry, never the SDK's same-id commit loop.
    assert reads == [1, 2, 3, 4, 5]
    assert scripted.events[-1] == ['arm', 'batch_privacy_generation_advance', ARM_WINDOW_SECONDS]


def test_finish_consults_and_clears_the_ladder_on_commit(monkeypatch):
    switches_on(monkeypatch)
    scripted = ScriptedStormDamper()
    spy_shared_damper(monkeypatch, scripted)
    client = make_client()
    stub_doc(client, {'generation': 4})

    privacy.finish_privacy_purge(client, 'uid-a', 4)

    assert scripted.events == [
        ['consult', 'batch_privacy_purge_finish', 0.0],
        ['note_success', 'batch_privacy_purge_finish', DEFAULT_GENERATION],
    ]


def test_recovery_revoke_consults_the_namespace_damper(monkeypatch):
    switches_on(monkeypatch)
    scripted = ScriptedStormDamper()
    keys = spy_shared_damper(monkeypatch, scripted)
    client = make_client()
    fenced = []

    def assert_allowed(*args, **kwargs):
        fenced.append(args[2:])
        raise privacy.BatchPrivacyBlocked('fenced')

    monkeypatch.setattr(recovery, 'assert_batch_write_allowed', assert_allowed)
    job = {'state': 'leased', 'owner_id': 'uid-a', 'conversation_id': 'conv-1', 'privacy_generation': 2}
    stub_doc(client, job)

    revoked = recovery.quarantine_fenced(client, NAMESPACE, 'seg-1', 1000.0)

    assert revoked is True
    assert keys == [NAMESPACE]
    assert scripted.events == [
        ['consult', 'batch_recovery_fenced_revoke', 0.0],
        ['note_success', 'batch_recovery_fenced_revoke', DEFAULT_GENERATION],
    ]
    assert fenced == [('uid-a',)]


def test_cancel_consults_the_namespace_damper_and_mirrors(monkeypatch):
    switches_on(monkeypatch)
    scripted = ScriptedStormDamper()
    keys = spy_shared_damper(monkeypatch, scripted)
    store = Mock()
    store.client = make_client()
    store.namespace = NAMESPACE

    def assert_allowed(*args, **kwargs):
        raise privacy.BatchPrivacyBlocked('fenced')

    monkeypatch.setattr(privacy, 'assert_batch_write_allowed', assert_allowed)
    job = {
        'recovery': {'attempt': 1},
        'projection_binding': {
            'owner_id': 'uid-a',
            'job_id': 'job-1',
            'content_id': 'content-1',
            'segment_ids': ['seg-1'],
        },
        'conversation_id': 'conv-1',
    }
    stub_doc(store.client, job)
    mirrors = []
    import database.batch_pipeline_shadow_hook as shadow_hook

    monkeypatch.setattr(shadow_hook, 'mirror_refresh', lambda ns, rows: mirrors.append((ns, rows)))

    cancelled = quarantine_recovery.cancel_fenced_recovery(store, 'seg-1')

    assert cancelled is True
    assert keys == [NAMESPACE]
    assert scripted.events[0] == ['consult', 'batch_quarantine_recovery_cancel', 0.0]
    assert scripted.note_success_args == [['batch_quarantine_recovery_cancel', DEFAULT_GENERATION]]
    assert mirrors == [(NAMESPACE, [('jobs', 'seg-1')])]


def test_voice_receipt_read_consults_the_namespace_damper(monkeypatch):
    switches_on(monkeypatch)
    scripted = ScriptedStormDamper()
    keys = spy_shared_damper(monkeypatch, scripted)
    store = Mock()
    store.client = make_client()
    store.namespace = NAMESPACE
    job = {'owner_id': 'uid-a', 'projection_binding': {}}
    stub_doc(store.client, job)

    receipt = voice.load_reference(store, 'uid-a', 'seg-1', 'conv-1')

    assert receipt is None  # unbound job: the read still rode the runner
    assert keys == [NAMESPACE]
    assert scripted.events == [
        ['consult', 'batch_voice_evidence_receipt_read', 0.0],
        ['note_success', 'batch_voice_evidence_receipt_read', DEFAULT_GENERATION],
    ]


def test_voice_publish_consults_before_the_binding_refusal(monkeypatch):
    switches_on(monkeypatch)
    scripted = ScriptedStormDamper()
    spy_shared_damper(monkeypatch, scripted)
    store = Mock()
    store.client = make_client()
    store.namespace = NAMESPACE
    job = {'owner_id': 'uid-a', 'projection_binding': {}}
    stub_doc(store.client, job)
    fenced = []

    def assert_allowed(*args, **kwargs):
        fenced.append(args[2:])

    monkeypatch.setattr(voice, 'assert_batch_write_allowed', assert_allowed)
    item = WorkItem(
        segment_id='seg-1',
        owner_id='uid-a',
        capture_at=1000.0,
        audio_uri='gs://bucket/a.enc#1',
        duration_seconds=12.0,
        priority=Priority.FRESH,
    )

    with pytest.raises(PermissionError):
        voice.publish(store, item, 'gs://bucket/a.enc#1', 'conv-1')

    # A binding refusal is neither a contention exhaustion nor a commit: the
    # ladder is consulted at entry, the privacy fence is still asserted, and
    # nothing clears or arms the window.
    assert scripted.events == [['consult', 'batch_voice_evidence_publish_write', 0.0]]
    assert fenced == [('uid-a',)]


def test_dormant_switches_leave_the_bare_bounded_ladder(monkeypatch):
    switches_off(monkeypatch)
    scripted = ScriptedStormDamper(entry_wait=9.9)
    keys = spy_shared_damper(monkeypatch, scripted)
    calls = []
    client = make_client(transaction_calls=calls)
    stub_doc(client, {})

    generation = privacy.advance_privacy_generation(client, 'uid-a', blocked=False)

    assert generation == 1
    assert keys == []
    assert scripted.events == []
    # The join keeps the bounded engine chain (one fresh transaction per
    # outer attempt) even while the damper is dormant: never the bare
    # SDK same-id commit loop.
    assert calls == [{'max_attempts': 1}]


def test_resolver_is_gated_by_both_kill_switches(monkeypatch):
    scripted = ScriptedStormDamper()
    monkeypatch.setattr(storage, 'shared_storm_damper', lambda key: scripted)
    switches_on(monkeypatch)
    assert storage.batch_lane_storm_damper(NAMESPACE) is scripted
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: False)
    assert storage.batch_lane_storm_damper(NAMESPACE) is None
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: True)
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: False)
    assert storage.batch_lane_storm_damper(NAMESPACE) is None


def test_transaction_is_one_bounded_chain_per_attempt(monkeypatch):
    switches_on(monkeypatch)
    pin_engine(monkeypatch)
    scripted = ScriptedStormDamper(residual_schedule=(0.3,))
    spy_shared_damper(monkeypatch, scripted)
    calls = []
    client = make_client(transaction_calls=calls)
    body, body_calls = aborting_body(2)

    result = storage.run_batch_pipeline_transaction(
        client, body, operation_name='batch_privacy_generation_advance', storm_damper=scripted
    )

    assert result == 'committed'
    assert body_calls == [1, 2, 3]
    assert calls == [{'max_attempts': 1}] * 3
    assert scripted.events == [
        ['consult', 'batch_privacy_generation_advance', 0.0],
        ['peek', 'batch_privacy_generation_advance', 0.3],
        ['peek', 'batch_privacy_generation_advance', 0.3],
        ['note_success', 'batch_privacy_generation_advance', DEFAULT_GENERATION],
    ]


def test_mid_ladder_wave_engages_from_the_third_failed_rung(monkeypatch):
    pin_engine(monkeypatch)
    scripted = ScriptedStormDamper(residual_schedule=(0.9, 0.6, 0.2, 0.0), wave_wait=1.25)
    client = make_client()
    body, body_calls = aborting_body(4)

    result = storage.run_batch_pipeline_transaction(
        client, body, operation_name='batch_recovery_fenced_revoke', storm_damper=scripted
    )

    assert result == 'committed'
    assert body_calls == [1, 2, 3, 4, 5]
    wave_events = [event for event in scripted.events if event[0] == 'wave']
    assert [event[1] for event in wave_events] == [3, 4]


def test_exhaustion_raises_typed_and_never_notes_success(monkeypatch):
    pin_engine(monkeypatch)
    scripted = ScriptedStormDamper(residual_schedule=(0.0,), wave_wait=1.25)
    client = make_client()
    body, body_calls = aborting_body(5)

    with pytest.raises(FirestoreContentionExhausted):
        storage.run_batch_pipeline_transaction(
            client, body, operation_name='batch_voice_evidence_publish_write', storm_damper=scripted
        )

    assert body_calls == [1, 2, 3, 4, 5]
    assert scripted.events[-1] == ['arm', 'batch_voice_evidence_publish_write', ARM_WINDOW_SECONDS]
    assert scripted.note_success_args == []


def test_purge_runner_delegates_to_the_shared_doctrine(monkeypatch):
    seen = {}

    def spy(client, operation, *, operation_name, storm_damper=None, logger=None):
        seen['name'] = operation_name
        seen['logger'] = logger
        seen['damper'] = storm_damper
        return 'erased'

    monkeypatch.setattr(storage, 'run_batch_pipeline_transaction', spy)
    import database.batch_pipeline_purge as purge

    scripted = ScriptedStormDamper()
    outcome = purge.run_purge_transaction(
        make_client(),
        lambda transaction: 'erased',
        operation_name=purge.PURGE_RESULT_ERASE_LABEL,
        storm_damper=scripted,
    )

    assert outcome == 'erased'
    assert seen['name'] == 'batch_purge_result_erase'
    assert seen['damper'] is scripted
    assert seen['logger'] is purge.logger


def test_purge_storm_damper_resolver_shares_the_doctrine(monkeypatch):
    switches_on(monkeypatch)
    scripted = ScriptedStormDamper()
    keys = spy_shared_damper(monkeypatch, scripted)

    from database.batch_pipeline_purge import _purge_storm_damper

    assert _purge_storm_damper(NAMESPACE) is scripted
    assert keys == [NAMESPACE]
    switches_off(monkeypatch)
    assert _purge_storm_damper(NAMESPACE) is None


def test_lane_labels_hold_the_store_label_grammar():
    labels = (
        privacy.BATCH_PRIVACY_GENERATION_ADVANCE_LABEL,
        privacy.BATCH_PRIVACY_PURGE_FINISH_LABEL,
        recovery.BATCH_RECOVERY_FENCED_REVOKE_LABEL,
        quarantine_recovery.BATCH_QUARANTINE_RECOVERY_CANCEL_LABEL,
        voice.BATCH_VOICE_EVIDENCE_RECEIPT_READ_LABEL,
        voice.BATCH_VOICE_EVIDENCE_PUBLISH_WRITE_LABEL,
    )
    pattern = re.compile(r'^[a-z][a-z0-9_]{0,63}$')
    assert len(set(labels)) == 6
    for label in labels:
        assert pattern.fullmatch(label)
