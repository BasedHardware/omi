"""The in-flight ledger contract: table invariants, transitions, fail-open and privacy."""

from __future__ import annotations

from prometheus_client import generate_latest
from prometheus_client.parser import text_string_to_metric_families

from database import pipeline_ledger as ledger


def test_every_nonterminal_stage_has_a_deadline_and_an_exit():
    for stage, rule in ledger.STAGE_TABLE.items():
        assert rule.deadline_seconds > 0, stage
        assert rule.exit_stage in ledger.STAGE_TABLE or ledger.is_terminal(rule.exit_stage), stage
    for stage in ledger.TERMINAL_STAGES:
        assert stage not in ledger.STAGE_TABLE, stage
        assert ledger.is_terminal(stage)


def test_forward_transitions_are_legal_and_ranked():
    doc = ledger.plan_advance(None, ledger.CAPTURING, now=100).doc
    assert doc is not None and doc['stage'] == ledger.CAPTURING
    for stage, at in ((ledger.SEALED, 200), (ledger.TRANSCRIBED, 300), (ledger.NOTED, 400), (ledger.DONE, 500)):
        plan = ledger.plan_advance(doc, stage, now=at)
        assert plan.outcome == 'written', stage
        doc = plan.doc
    assert doc['stage'] == ledger.DONE
    assert doc['deadline_at'] is None
    assert ledger._epoch(doc['expires_at']) == 500 + ledger.terminal_ttl_seconds()


def test_forward_skip_is_legal_so_uninstrumented_stages_do_not_block():
    doc = ledger.plan_advance(None, ledger.CAPTURING, now=100).doc
    plan = ledger.plan_advance(doc, ledger.NOTED, now=200)
    assert plan.outcome == 'written'
    assert plan.doc['stage'] == ledger.NOTED


def test_backward_transition_is_illegal():
    doc = ledger.plan_advance(None, ledger.NOTED, now=100).doc
    assert ledger.plan_advance(doc, ledger.SEALED, now=200).outcome == 'illegal'


def test_duplicate_advance_is_idempotent():
    doc = ledger.plan_advance(None, ledger.SEALED, now=100).doc
    plan = ledger.plan_advance(doc, ledger.SEALED, now=200)
    assert plan.outcome == 'duplicate'
    assert plan.doc is None


def test_duplicate_same_revision_is_idempotent():
    doc = ledger.plan_advance(None, ledger.SEALED, now=100, revision=1).doc
    plan = ledger.plan_advance(doc, ledger.SEALED, now=200, revision=1)
    assert plan.outcome == 'duplicate'
    assert plan.doc is None


def test_stale_revision_loses():
    doc = ledger.plan_advance(None, ledger.SEALED, now=100, revision=2).doc
    plan = ledger.plan_advance(doc, ledger.NOTED, now=200, revision=1)
    assert plan.outcome == 'stale'
    assert plan.doc is None


def test_late_append_reopens_a_terminal_with_a_higher_revision():
    doc = ledger.plan_advance(None, ledger.DONE, now=100, revision=4).doc
    assert doc['terminal'] is True
    plan = ledger.plan_advance(doc, ledger.NOTED, now=200, revision=5, reopen=True)
    assert plan.outcome == 'written'
    assert plan.doc['stage'] == ledger.NOTED
    assert plan.doc['terminal'] is False
    assert plan.doc['revision'] == 5


def test_retry_reopens_a_failed_terminal_with_a_higher_revision():
    doc = ledger.plan_advance(None, ledger.failed_stage('provider'), now=100, revision=2).doc
    plan = ledger.plan_advance(doc, ledger.SEALED, now=200, revision=3, reopen=True)
    assert plan.outcome == 'written'
    assert plan.doc['stage'] == ledger.SEALED


def test_terminal_is_final_without_a_higher_revision():
    doc = ledger.plan_advance(None, ledger.NO_SPEECH, now=100).doc
    assert ledger.plan_advance(doc, ledger.SEALED, now=200).outcome == 'terminal'
    assert ledger.plan_advance(doc, ledger.NOTED, now=200, revision=2).outcome == 'terminal'


def test_unknown_stage_is_illegal():
    assert ledger.plan_advance(None, 'not_a_stage', now=100).outcome == 'illegal'


def test_transition_history_is_capped_at_sixteen():
    existing = {
        'stage': ledger.NOTED,
        'attempt': 20,
        'transitions': [{'stage': ledger.CAPTURING, 'at': i} for i in range(20)],
    }
    doc = ledger.plan_advance(existing, ledger.DONE, now=100).doc
    assert len(doc['transitions']) == ledger.MAX_TRANSITIONS
    assert doc['transitions'][-1]['stage'] == ledger.DONE


def test_attempt_reason_end_type_and_end_at_are_preserved():
    doc = ledger.plan_advance(
        None,
        ledger.CAPTURING,
        now=100,
        reason='capture_started',
        end_type='user_initiated',
        end_at=90,
    ).doc
    assert doc['attempt'] == 1
    assert doc['reason'] == 'capture_started'
    assert doc['end_type'] == 'user_initiated'
    assert doc['end_at'] == 90

    next_doc = ledger.plan_advance(doc, ledger.SEALED, now=200).doc
    assert next_doc['attempt'] == 2
    assert next_doc['reason'] == 'capture_started'
    assert next_doc['end_type'] == 'user_initiated'
    assert next_doc['end_at'] == 90


def test_unknown_end_type_is_never_labelled_observed():
    doc = ledger.plan_advance(None, ledger.CAPTURING, now=100, end_type='invented').doc
    assert doc['end_type'] == 'unknown'


def test_end_at_is_the_firing_clock_not_last_speech():
    doc = ledger.plan_advance(
        None,
        ledger.NO_SPEECH,
        now=1000,
        end_type='silence_backstop',
        end_at=1000,
        last_speech_at=400,
        quiet_due_at=900,
    ).doc
    assert doc['end_at'] == 1000
    assert doc['last_speech_at'] == 400
    assert doc['quiet_due_at'] == 900


def test_failure_reason_is_bounded():
    assert ledger.failed_stage('timeout') == 'failed:timeout'
    assert ledger.failed_stage('a-user-supplied-string') == 'failed:other'
    assert ledger.stage_label('failed:timeout') == 'failed'
    assert ledger.bounded_reason('a-user-supplied-string') == 'other'
    assert ledger.bounded_reason('timeout') == 'timeout'


def test_terminal_ttl_is_at_least_twenty_six_hours(monkeypatch):
    monkeypatch.delenv('PIPELINE_LEDGER_TERMINAL_TTL_SECONDS', raising=False)
    assert ledger.terminal_ttl_seconds() >= 26 * 3600
    monkeypatch.setenv('PIPELINE_LEDGER_TERMINAL_TTL_SECONDS', '60')
    assert ledger.terminal_ttl_seconds() >= 26 * 3600
    monkeypatch.setenv('PIPELINE_LEDGER_TERMINAL_TTL_SECONDS', str(30 * 86400))
    assert ledger.terminal_ttl_seconds() == ledger.MAX_TERMINAL_TTL_SECONDS


def test_terminal_ttl_and_no_deadline():
    doc = ledger.plan_advance(None, ledger.failed_stage('provider'), now=100).doc
    assert doc['deadline_at'] is None
    assert ledger._epoch(doc['expires_at']) == 100 + ledger.terminal_ttl_seconds()
    assert doc['terminal'] is True
    assert doc['terminal_reason'] == 'failed:provider'


def test_expires_at_is_a_utc_timestamp_not_an_epoch():
    from datetime import datetime, timezone

    doc = ledger.plan_advance(None, ledger.NO_SPEECH, now=100).doc
    assert isinstance(doc['expires_at'], datetime)
    assert doc['expires_at'].tzinfo == timezone.utc
    assert ledger.plan_advance(None, ledger.SEALED, now=100).doc['expires_at'] is None


def test_arbitrary_failed_reason_collapses_to_the_closed_enum():
    doc = ledger.plan_advance(None, 'failed:a-user-supplied-string', now=100).doc
    assert doc['stage'] == 'failed:other'
    assert doc['terminal_reason'] == 'failed:other'
    assert ledger.plan_advance(None, 'failed:upload_failed', now=100).doc['stage'] == 'failed:upload_failed'


def test_schema_fields_are_present_and_content_free():
    doc = ledger.plan_advance(
        None,
        ledger.NOTED,
        now=100,
        speech_seconds=12.5,
        has_speech=True,
        speech_basis='vad',
    ).doc
    for field in (
        'schema_version',
        'owner_key',
        'stage',
        'entered_at',
        'deadline_at',
        'attempt',
        'reason',
        'end_type',
        'end_at',
        'admitted_at',
        'created_at',
        'updated_at',
        'revision',
        'terminal',
        'terminal_reason',
        'speech_seconds',
        'has_speech',
        'speech_basis',
        'home_ready_at',
        'episode_done_at',
        'transitions',
        'expires_at',
    ):
        assert field in doc, field
    assert doc['schema_version'] == 1
    assert doc['speech_seconds'] == 12.5
    assert doc['speech_basis'] == 'vad'
    assert doc['home_ready_at'] == 100
    for forbidden in (
        'title',
        'overview',
        'transcript',
        'audio_path',
        'email',
        'device_id',
        'uid',
        'capture_id',
        'conversation_id',
    ):
        assert forbidden not in doc


def test_owner_key_is_a_truncated_hash_not_the_uid():
    key = ledger.owner_key('uid-secret')
    assert key != 'uid-secret'
    assert len(key) == 16


class _FakeSnapshot:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _FakeRef:
    def __init__(self, store, path):
        self.store = store
        self.path = path

    def collection(self, name):
        return _FakeRef(self.store, f'{self.path}/{name}')

    def document(self, name):
        return _FakeRef(self.store, f'{self.path}/{name}')

    def get(self, transaction=None):
        return _FakeSnapshot(self.store.get(self.path))

    def set(self, doc):
        self.store[self.path] = doc


class _FakeTransaction:
    _read_only = False
    _max_attempts = 1
    _id = 'fake-transaction'
    retry_id = None

    def __init__(self, store):
        self.store = store

    def _begin(self, retry_id=None):
        return None

    def set(self, ref, doc):
        self.store[ref.path] = doc

    def _commit(self):
        return None

    def _rollback(self):
        return None

    def _clean_up(self):
        return None


class _FakeClient:
    def __init__(self):
        self.store = {}

    def collection(self, name):
        return _FakeRef(self.store, name)

    def transaction(self):
        return _FakeTransaction(self.store)


class _BoomClient:
    def collection(self, *_args, **_kwargs):
        raise RuntimeError('synthetic ledger store failure')


def test_advance_is_fail_open_on_store_error(monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    assert ledger.advance('uid', 'capture', ledger.SEALED, firestore_client=_BoomClient()) is False


def test_advance_is_silent_when_disabled(monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'off')
    assert ledger.advance('uid', 'capture', ledger.SEALED, firestore_client=_BoomClient()) is False


def test_advance_writes_the_planned_document(monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    client = _FakeClient()
    assert ledger.advance('uid', 'capture', ledger.SEALED, now=100, firestore_client=client) is True
    doc = client.store['users/uid/pipeline_ledger/capture']
    assert doc['stage'] == ledger.SEALED
    assert doc['owner_key'] == ledger.owner_key('uid')
    assert 'capture_id' not in doc
    assert 'conversation_id' not in doc


def test_advance_duplicate_does_not_double_count(monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    client = _FakeClient()
    assert ledger.advance('uid', 'capture', ledger.SEALED, now=100, firestore_client=client) is True
    assert ledger.advance('uid', 'capture', ledger.SEALED, now=200, firestore_client=client) is False
    doc = client.store['users/uid/pipeline_ledger/capture']
    assert doc['attempt'] == 1
    assert len(doc['transitions']) == 1


def test_metrics_are_content_free(monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    ledger.advance('uid-secret', 'capture-secret', ledger.SEALED, now=100, firestore_client=_FakeClient())
    exported = generate_latest().decode()
    families = {family.name: family for family in text_string_to_metric_families(exported)}
    write = families['omi_pipeline_ledger_write']
    assert all(set(sample.labels) == {'outcome'} for sample in write.samples)
    transition = families['omi_pipeline_ledger_transition']
    assert all(set(sample.labels) == {'from', 'to'} for sample in transition.samples)
    stage_seconds = families['omi_pipeline_ledger_stage_seconds']
    assert all(set(sample.labels) <= {'stage', 'le'} for sample in stage_seconds.samples)
    assert 'uid-secret' not in exported
    assert 'capture-secret' not in exported


class _FakeFilter:
    def __init__(self, field_path, op_string, value):
        self.field_path = field_path
        self.op_string = op_string
        self.value = value


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []
        self.limit_value = None

    def where(self, filter=None, **_kwargs):
        self.filters.append(filter)
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def stream(self):
        rows = list(self.rows)
        for item in self.filters:
            if item.op_string == '>=':
                rows = [row for row in rows if row.get(item.field_path, 0) >= item.value]
            elif item.op_string == '<':
                rows = [row for row in rows if row.get(item.field_path, 0) < item.value]
        if self.limit_value is not None:
            rows = rows[: self.limit_value]
        return [_FakeSnapshot(row) for row in rows]


class _FakeWindowRef:
    def __init__(self, rows, path=()):
        self.rows = rows
        self.path = path

    def document(self, name):
        return _FakeWindowRef(self.rows, self.path + (name,))

    def collection(self, name):
        assert name == ledger.COLLECTION
        assert self.path[0] == 'users' and len(self.path) == 2, self.path
        return _FakeQuery(self.rows)


class _FakeWindowClient:
    def __init__(self, rows):
        self.rows = rows

    def collection(self, name):
        assert name == 'users'
        return _FakeWindowRef(self.rows, (name,))


def test_census_window_is_bounded_owner_scoped_and_read_only():
    rows = [
        {'admitted_at': 10, 'stage': ledger.SEALED, 'owner_key': 'owner-a'},
        {'admitted_at': 20, 'stage': ledger.NOTED, 'owner_key': 'owner-a'},
        {'admitted_at': 30, 'stage': ledger.DONE, 'owner_key': 'owner-a'},
    ]
    client = _FakeWindowClient(rows)
    assert [row['stage'] for row in ledger.census_window(15, 25, uid='u', firestore_client=client)] == [ledger.NOTED]
    assert [row['stage'] for row in ledger.iter_window(0, 100, uid='u', firestore_client=client)] == [
        ledger.SEALED,
        ledger.NOTED,
        ledger.DONE,
    ]
    assert 'capture_id' not in ledger.census_window(0, 100, uid='u', firestore_client=client)[0]


def test_census_window_fails_closed_when_truncated():
    rows = [{'admitted_at': 10}, {'admitted_at': 20}]
    client = _FakeWindowClient(rows)
    try:
        ledger.census_window(0, 100, uid='u', limit=1, firestore_client=client)
    except ledger.LedgerWindowTruncated:
        pass
    else:  # pragma: no cover - the assertion is the contract
        raise AssertionError('truncated window must fail closed')


def test_iter_window_yields_no_prefix_before_truncation():
    rows = [{'admitted_at': 10}, {'admitted_at': 20}]
    client = _FakeWindowClient(rows)
    seen = []
    try:
        for row in ledger.iter_window(0, 100, uid='u', limit=1, firestore_client=client):
            seen.append(row)
    except ledger.LedgerWindowTruncated:
        pass
    else:  # pragma: no cover - the assertion is the contract
        raise AssertionError('truncated window must fail closed')
    assert seen == []


def test_census_window_rejects_an_inverted_window():
    client = _FakeWindowClient([])
    try:
        ledger.census_window(20, 10, uid='u', firestore_client=client)
    except ValueError:
        pass
    else:  # pragma: no cover - the assertion is the contract
        raise AssertionError('inverted window must be rejected')
