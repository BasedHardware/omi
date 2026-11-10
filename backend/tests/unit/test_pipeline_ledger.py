"""The in-flight ledger contract: table invariants, transitions and fail-open."""

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
    assert doc['expires_at'] == 500 + ledger.TERMINAL_TTL_SECONDS


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


def test_terminal_is_final():
    doc = ledger.plan_advance(None, ledger.NO_SPEECH, now=100).doc
    assert ledger.plan_advance(doc, ledger.SEALED, now=200).outcome == 'terminal'


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


def test_failure_reason_is_bounded():
    assert ledger.failed_stage('timeout') == 'failed:timeout'
    assert ledger.failed_stage('a-user-supplied-string') == 'failed:other'
    assert ledger.stage_label('failed:timeout') == 'failed'


def test_terminal_ttl_and_no_deadline():
    doc = ledger.plan_advance(None, ledger.failed_stage('provider'), now=100).doc
    assert doc['deadline_at'] is None
    assert doc['expires_at'] == 100 + ledger.TERMINAL_TTL_SECONDS


class _BoomClient:
    def collection(self, *_args, **_kwargs):
        raise RuntimeError('synthetic ledger store failure')


class _FakeSnapshot:
    exists = False

    def to_dict(self):
        return None


class _FakeClient:
    def __init__(self):
        self.written = None

    def collection(self, *_args, **_kwargs):
        return self

    def document(self, *_args, **_kwargs):
        return self

    def get(self):
        return _FakeSnapshot()

    def set(self, doc):
        self.written = doc


def test_prepare_is_fail_open_on_store_error(monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    assert ledger.prepare('uid', 'capture', ledger.SEALED, firestore_client=_BoomClient()) is None


def test_prepare_is_silent_when_disabled(monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'off')
    assert ledger.prepare('uid', 'capture', ledger.SEALED, firestore_client=_BoomClient()) is None


def test_advance_writes_the_planned_document(monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    client = _FakeClient()
    assert ledger.advance('uid', 'capture', ledger.SEALED, now=100, firestore_client=client) is True
    assert client.written['stage'] == ledger.SEALED
    assert client.written['capture_id'] == 'capture'


def test_metrics_are_content_free(monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    ledger.advance('uid-secret', 'capture-secret', ledger.SEALED, now=100, firestore_client=_FakeClient())
    exported = generate_latest().decode()
    families = {family.name: family for family in text_string_to_metric_families(exported)}
    advance = families['omi_pipeline_ledger_advance']
    assert all(set(sample.labels) == {'stage', 'outcome'} for sample in advance.samples)
    stage_seconds = families['omi_pipeline_ledger_stage_seconds']
    assert all(set(sample.labels) == {'stage'} for sample in stage_seconds.samples)
    assert 'uid-secret' not in exported
    assert 'capture-secret' not in exported
