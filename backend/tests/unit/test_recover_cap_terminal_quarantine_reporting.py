"""The recover sweep's lease-expiry cap terminal books the shared report.

The cap terminal used to book every cap-reached unit on the bare anonymous
``event=batch_quarantined reason=lease_expired recovery=held`` ERROR line
while the same transition wrote ``quarantine_reason='worker_failed'`` and
dropped the diagnosis the ladder had preserved. Both scheduler-side
terminals -- the worker-verdict terminal in ``Scheduler.fail`` and this
cap terminal in ``observe_recovery`` -- now book the shared
``report_terminal_quarantine``: designed handoffs demote to their INFO
transition events, a real fault keeps the attributed ERROR naming
stage/worker_reason, and the awaiting-fenced-recovery warning follows every
booking. Durable state, evidence, correctness meters and queue metrics are
unchanged.

The first section fails on the parent commit: the attributed and demoted
bookings below do not exist there. The second section pins the unchanged
surface the fix must not move.

Failure-Class: FC-lease-expiry-cap-quarantine-misbooked-as-anonymous-worker-fault
"""

import logging

import utils.batch_pipeline.retry_policy as retry_policy_module
import utils.batch_pipeline.scheduler as scheduler_module
from utils.batch_pipeline.errors import report_terminal_quarantine
from utils.batch_pipeline.retry_policy import expire_lease, observe_recovery

LOGGER_NAME = 'utils.batch_pipeline.retry_policy'
GATE = 'BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED'
GUARD_FORMAT = 'event=batch_language_guard outcome=held_for_redrive attempt=%d recovery=held stage=%s worker_reason=%s'
LADDER_FORMAT = 'event=batch_empty_ladder outcome=held_for_recovery attempt=%d recovery=held stage=%s worker_reason=%s'
DISPOSITION_FORMAT = (
    'event=batch_validation_disposition outcome=held_for_disposition attempt=%d recovery=held stage=%s worker_reason=%s'
)
FAULT_FORMAT = 'event=batch_quarantined reason=worker_failed attempt=%d recovery=held stage=%s worker_reason=%s'
AWAITING_FORMAT = 'event=batch_recovery outcome=held reason=awaiting_fenced_recovery'


class _Tx:
    """Minimal transaction double: quarantine_job reads the owner, puts the job."""

    def __init__(self):
        self.puts = []

    def get(self, kind, key):
        if kind == 'owners':
            return {'revision': 1}
        return None

    def put(self, kind, key, value):
        self.puts.append((kind, key, value))


class _Policy:
    def __init__(self, max_attempts):
        self.max_attempts = max_attempts


class _Metrics:
    def __init__(self):
        self.recorded = []

    def record(self, name):
        self.recorded.append(name)


def _stage_policy(tx, job, lane, *, candidates, observations):
    return _Policy(3)


def _defer(job, now, reason):
    job['state'] = 'retry'
    job['last_defer_reason'] = reason


def _drive(
    monkeypatch,
    caplog,
    *,
    attempt,
    evidence=None,
    max_attempts=3,
    gate='true',
    serving=True,
):
    """Run the real cap terminal once and return (job, outcome, records)."""
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve' if serving else 'shadow')
    monkeypatch.setenv(GATE, gate)
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    job = {
        'owner_id': 'owner-1',
        'owner_key': 'owner-1',
        'attempt': attempt,
        'duration_seconds': 12.5,
        'state': 'leased',
        'lease_until': 1.0,
    }
    if evidence is not None:
        job['worker_failure_evidence'] = evidence
    tx = _Tx()
    outcome = expire_lease(
        tx,
        job,
        100.0,
        stage_policy=_stage_policy,
        candidates={},
        observations=[],
        defer=_defer,
    )
    observe_recovery(outcome, None)
    records = [(r.levelno, r.getMessage()) for r in caplog.records if r.name == LOGGER_NAME]
    return job, outcome, records


def _quarantine_records(records):
    return [(level, message) for level, message in records if 'event=batch_quarantined' in message]


# ---------------------------------------------------------------------------
# Fails on parent: the attributed and demoted bookings.
# ---------------------------------------------------------------------------


def test_cap_expiry_books_the_attributed_worker_failed_line(monkeypatch, caplog):
    """A fault carries the same attributed shape the verdict terminal books."""
    _, _, records = _drive(monkeypatch, caplog, attempt=99)
    assert (logging.ERROR, FAULT_FORMAT % (99, 'unknown', 'unclassified')) in records


def test_cap_expiry_never_books_the_lease_expired_label(monkeypatch, caplog):
    """The log stops contradicting the quarantine_reason the transition wrote."""
    _, _, records = _drive(monkeypatch, caplog, attempt=99)
    assert all('reason=lease_expired' not in message for _, message in records)


def test_cap_expiry_demotes_the_language_guard_handoff(monkeypatch, caplog):
    """A preserved guard diagnosis rides the expiry terminal to its INFO event."""
    evidence = {'stage': 'vad_windows', 'reason': 'unsupported_language'}
    _, _, records = _drive(monkeypatch, caplog, attempt=7, evidence=evidence)
    assert (logging.INFO, GUARD_FORMAT % (7, 'vad_windows', 'unsupported_language')) in records
    assert _quarantine_records(records) == []


def test_cap_expiry_demotes_the_empty_ladder_handoff(monkeypatch, caplog):
    """A preserved empty-ladder diagnosis rides the expiry terminal to its INFO event."""
    evidence = {'stage': 'assemble_words', 'reason': 'empty_asr'}
    _, _, records = _drive(monkeypatch, caplog, attempt=7, evidence=evidence)
    assert (logging.INFO, LADDER_FORMAT % (7, 'assemble_words', 'empty_asr')) in records
    assert _quarantine_records(records) == []


def test_cap_expiry_demotes_the_disposition_handoff_when_the_switch_is_on(monkeypatch, caplog):
    """The flagged verdicts demote under the same switch as the verdict terminal."""
    evidence = {'stage': 'word_clocks', 'reason': 'word_sequence'}
    _, _, records = _drive(monkeypatch, caplog, attempt=7, evidence=evidence, gate='true')
    assert (logging.INFO, DISPOSITION_FORMAT % (7, 'word_clocks', 'word_sequence')) in records
    assert _quarantine_records(records) == []


def test_cap_expiry_keeps_the_disposition_handoff_loud_when_the_switch_is_off(monkeypatch, caplog):
    """With the switch off, the flagged verdict keeps the attributed ERROR."""
    evidence = {'stage': 'word_clocks', 'reason': 'word_sequence'}
    _, _, records = _drive(monkeypatch, caplog, attempt=7, evidence=evidence, gate='false')
    assert (logging.ERROR, FAULT_FORMAT % (7, 'word_clocks', 'word_sequence')) in records


def test_cap_expiry_demotes_the_unconditional_disposition_regardless_of_switch(monkeypatch, caplog):
    """The fetch_decode trio's chain end is unconditional, so its demotion is too."""
    evidence = {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}
    _, _, records = _drive(monkeypatch, caplog, attempt=7, evidence=evidence, gate='false')
    assert (logging.INFO, DISPOSITION_FORMAT % (7, 'fetch_decode', 'staged_audio_invalid')) in records


def test_cap_expiry_demotes_the_persist_refusal_regardless_of_switch(monkeypatch, caplog):
    """The persist sibling demotes at the persist stage under either switch."""
    evidence = {'stage': 'persist', 'reason': 'persist_payload_invalid'}
    _, _, records = _drive(monkeypatch, caplog, attempt=7, evidence=evidence, gate='false')
    assert (logging.INFO, DISPOSITION_FORMAT % (7, 'persist', 'persist_payload_invalid')) in records


def test_cap_expiry_keeps_the_deliberately_retryable_evidence_loud(monkeypatch, caplog):
    """outside_admitted_source keeps the attributed ERROR at the expiry terminal."""
    evidence = {'stage': 'assemble_words', 'reason': 'outside_admitted_source'}
    _, _, records = _drive(monkeypatch, caplog, attempt=7, evidence=evidence)
    assert (logging.ERROR, FAULT_FORMAT % (7, 'assemble_words', 'outside_admitted_source')) in records


def test_cap_expiry_report_names_the_preserved_diagnosis(monkeypatch, caplog):
    """The terminal record names the stage/reason the ladder actually collected."""
    evidence = {'stage': 'vad_windows', 'reason': 'vad_bounds'}
    _, _, records = _drive(monkeypatch, caplog, attempt=13, evidence=evidence, gate='false')
    assert (logging.ERROR, FAULT_FORMAT % (13, 'vad_windows', 'vad_bounds')) in records


def test_cap_expiry_unknown_vocabulary_keeps_the_carried_tokens(monkeypatch, caplog):
    """An off-vocabulary closed shape prints its carried tokens, not a demotion."""
    evidence = {'stage': 'weird_stage', 'reason': 'weird_reason'}
    _, _, records = _drive(monkeypatch, caplog, attempt=5, evidence=evidence)
    assert (logging.ERROR, FAULT_FORMAT % (5, 'weird_stage', 'weird_reason')) in records


def test_cap_expiry_hostile_evidence_falls_back_to_the_anonymous_attribution(monkeypatch, caplog):
    """A non-dict evidence payload never raises and books the anonymous shape."""
    for evidence in (None, ['staged'], 7, 'staged_audio_invalid'):
        _, _, records = _drive(monkeypatch, caplog, attempt=9, evidence=evidence)
        assert (logging.ERROR, FAULT_FORMAT % (9, 'unknown', 'unclassified')) in records


def test_cap_expiry_hostile_closed_shapes_keep_the_fault_line(monkeypatch, caplog):
    """Extra keys and off-vocabulary case keep the attributed fault line."""
    for evidence in (
        {'stage': 'word_clocks', 'reason': 'word_sequence', 'extra': 1},
        {'stage': 'ASSEMBLE_WORDS', 'reason': 'empty_asr'},
        {'stage': 'assemble_words'},
        {'reason': 'empty_asr'},
    ):
        _, _, records = _drive(monkeypatch, caplog, attempt=4, evidence=evidence, gate='true')
        assert _quarantine_records(records) != []


def test_both_scheduler_terminals_share_one_report(monkeypatch, caplog):
    """One booking function, two terminals -- the verdict and cap terminals agree."""
    assert scheduler_module.report_terminal_quarantine is report_terminal_quarantine
    assert retry_policy_module.report_terminal_quarantine is report_terminal_quarantine
    evidence = {'stage': 'word_clocks', 'reason': 'word_sequence'}
    _, _, records = _drive(monkeypatch, caplog, attempt=7, evidence=evidence, gate='false')
    assert (logging.ERROR, FAULT_FORMAT % (7, 'word_clocks', 'word_sequence')) in records


# ---------------------------------------------------------------------------
# Unchanged surface the fix must not move.
# ---------------------------------------------------------------------------


def test_cap_expiry_defer_branch_never_books_a_quarantine(monkeypatch, caplog):
    """A below-cap lease expiry keeps deferring with no terminal report."""
    job, outcome, records = _drive(monkeypatch, caplog, attempt=1)
    assert job['state'] == 'retry'
    assert outcome[0] == 'lease_expired'
    assert outcome[3] is None
    assert records == []


def test_cap_expiry_outcome_carries_the_terminal_payload(monkeypatch, caplog):
    """The quarantined outcome carries the attempt and the preserved diagnosis."""
    evidence = {'stage': 'vad_windows', 'reason': 'unsupported_language'}
    _, outcome, _ = _drive(monkeypatch, caplog, attempt=7, evidence=evidence)
    assert outcome[0] == 'quarantined'
    assert outcome[3] == (7, evidence)


def test_cap_expiry_quarantine_writes_the_durable_worker_failed_reason(monkeypatch, caplog):
    """Durable custody is untouched: the job quarantines as worker_failed."""
    job, _, _ = _drive(monkeypatch, caplog, attempt=99)
    assert job['state'] == 'quarantined'
    assert job['quarantine_reason'] == 'worker_failed'
    assert job['recovery_state'] == 'held'
    assert 'worker_failure_evidence' not in job


def test_cap_expiry_records_correctness_failed(monkeypatch, caplog):
    """The correctness meter still counts the cap-reached unit as failed."""
    recorded = []
    monkeypatch.setattr(
        retry_policy_module, 'record_correctness', lambda name, seconds=None: recorded.append((name, seconds))
    )
    _drive(monkeypatch, caplog, attempt=99)
    assert recorded == [('failed', 12.5)]


def test_cap_expiry_records_the_queue_metrics(monkeypatch, caplog):
    """The queue metrics still count quarantined and recovery_held."""
    metrics = _Metrics()
    job = {
        'owner_id': 'owner-1',
        'owner_key': 'owner-1',
        'attempt': 99,
        'duration_seconds': 12.5,
        'state': 'leased',
        'lease_until': 1.0,
    }
    tx = _Tx()
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.setenv(GATE, 'true')
    outcome = expire_lease(tx, job, 100.0, stage_policy=_stage_policy, candidates={}, observations=[], defer=_defer)
    observe_recovery(outcome, metrics)
    assert metrics.recorded == ['quarantined', 'recovery_held']


def test_cap_expiry_books_the_awaiting_recovery_warning_last(monkeypatch, caplog):
    """The awaiting-fenced-recovery warning follows the booking on every shape."""
    for evidence in (None, {'stage': 'vad_windows', 'reason': 'unsupported_language'}):
        _, _, records = _drive(monkeypatch, caplog, attempt=99, evidence=evidence)
        assert records[-1] == (logging.WARNING, AWAITING_FORMAT)


def test_cap_expiry_evidence_preserved_through_the_demotion(monkeypatch, caplog):
    """The demotion rechannels the report only: the evidence stays on the job."""
    evidence = {'stage': 'assemble_words', 'reason': 'no_owned_words'}
    job, _, records = _drive(monkeypatch, caplog, attempt=7, evidence=evidence)
    assert job['worker_failure_evidence'] == evidence
    assert (logging.INFO, LADDER_FORMAT % (7, 'assemble_words', 'no_owned_words')) in records


def test_cap_expiry_non_serving_expiry_still_defers(monkeypatch, caplog):
    """A shadow-mode expiry keeps the legacy defer with no decision consumption."""
    job, outcome, records = _drive(monkeypatch, caplog, attempt=99, serving=False)
    assert job['state'] == 'retry'
    assert outcome[0] == 'lease_expired'
    assert outcome[2] is not None
    assert outcome[2].serving is False
    assert records == []


def test_cap_expiry_empty_diagnosis_books_the_anonymous_attribution(monkeypatch, caplog):
    """An empty dict diagnosis books the anonymous shape like a missing one."""
    _, _, records = _drive(monkeypatch, caplog, attempt=6, evidence={})
    assert (logging.ERROR, FAULT_FORMAT % (6, 'unknown', 'unclassified')) in records
