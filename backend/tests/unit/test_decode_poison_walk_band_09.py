"""Generated fetch-decode poison custody walk band 09.

Scenario slice 182 bounded ladder walks. Every cell drives the real
``utils.batch_pipeline.scheduler.Scheduler`` over ``MemoryStore`` through one
walk (interim custody sequence, terminal custody, quarantine flag) and
asserts one property of the resulting transcript against the independent
custody spec embedded below. The spec mirrors the documented contract (the
closed stage and reason vocabularies, the four terminal report arms in
precedence order with their exact messages, the evidence preservation
order, exhaustion at the policy cap of five attempts, the bounded retry
backoff), never the module under test. The emitter and its independent
model live outside the tree. Do not edit frozen literals by hand.

Failure-Class: FC-fetch-decode-valueerror-poison-walks-gpu-ladder-as-anonymous-per-attempt
"""

import logging
from functools import lru_cache

import pytest

from config.batch_pipeline import worker_validation_disposition_enabled
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item
from utils.batch_pipeline.scheduler import Scheduler
from utils.observability.reasons import WorkerValidationReason as _WVR

_POISON = _WVR.DECODE_PAYLOAD_INVALID.value

STAGES = ('fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery', 'persist')
UNCONDITIONAL_FETCH = (
    'staged_audio_invalid',
    'retained_audio_invalid',
    'decoded_duration_mismatch',
    'decode_payload_invalid',
)
UNCONDITIONAL_PERSIST = ('persist_payload_invalid',)
FLAGGED = ('vad_nonfinite', 'vad_order', 'vad_bounds', 'word_shape', 'word_clock', 'word_sequence')
EMPTY = ('empty_asr', 'no_owned_words')
GUARD = ('unsupported_language',)
LOGGER_NAMES = ('utils.batch_pipeline.scheduler', 'utils.batch_pipeline.retry_policy')

pytestmark = [pytest.mark.filterwarnings('ignore::DeprecationWarning')]


class _Sink(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _seq_last_evidence(seq, terminal_attempt, same, foreign):
    if terminal_attempt < 2:
        return None
    if seq in ('ev_same_all', 'ev_same_first'):
        return same
    if seq in ('ev_foreign_all', 'ev_foreign_first'):
        return foreign
    return None


def _interim_kwargs(seq, position, same, foreign):
    if seq == 'ev_same_all':
        return {'worker_failure_evidence': dict(same)}
    if seq == 'ev_foreign_all':
        return {'worker_failure_evidence': dict(foreign)}
    if seq == 'ev_same_first' and position == 1:
        return {'worker_failure_evidence': dict(same)}
    if seq == 'ev_foreign_first' and position == 1:
        return {'worker_failure_evidence': dict(foreign)}
    return {}


def _drive(variant, stage, reason, foreign_stage, foreign_reason, quarantine, terminal_attempt, seq):
    store = MemoryStore()
    queue = Scheduler(store)
    sink = _Sink()
    root = logging.getLogger()
    root.addHandler(sink)
    previous = root.level
    root.setLevel(logging.DEBUG)
    try:
        queue.enqueue(item('a'), 0.0)
        rets = []
        last_now = 0.0
        last_lease_token = ''
        for attempt in range(1, terminal_attempt + 1):
            now = attempt * 1000.0
            queue.recover(now)
            lease = queue.pull(now)[0]
            last_lease_token = lease.token
            last_now = now + 1.0
            kwargs = {}
            if attempt < terminal_attempt:
                kwargs = _interim_kwargs(
                    seq, attempt, {'stage': stage, 'reason': reason}, {'stage': foreign_stage, 'reason': foreign_reason}
                )
            else:
                if variant in ('wf', 'wfev'):
                    kwargs['worker_failure'] = {'stage': stage, 'reason': reason}
                if variant in ('ev', 'wfev'):
                    kwargs['worker_failure_evidence'] = {'stage': stage, 'reason': reason}
                if quarantine:
                    kwargs['quarantine'] = True
            rets.append(queue.fail('a', lease.token, now + 1.0, **kwargs))
        job = store.rows['jobs', 'a']
        state_before_dupe = job.get('state')
        dupe = queue.fail('a', last_lease_token, last_now + 1.0)
        state_after_dupe = store.rows['jobs', 'a'].get('state')
        records = [(record.levelname, record.getMessage()) for record in sink.records if record.name in LOGGER_NAMES]
        return {
            'rets': rets,
            'dupe': dupe,
            'state': state_before_dupe,
            'state_after_dupe': state_after_dupe,
            'attempt': job.get('attempt'),
            'failure': job.get('failure'),
            'quarantine_reason': job.get('quarantine_reason'),
            'recovery_state': job.get('recovery_state'),
            'worker_failure': job.get('worker_failure'),
            'worker_failure_evidence': job.get('worker_failure_evidence'),
            'empty_evidence': job.get('worker_empty_evidence'),
            'merge_pending': job.get('merge_pending'),
            'retry_started_at': job.get('retry_started_at'),
            'available_at': job.get('available_at'),
            'records': records,
            'last_now': last_now,
            'terminal_attempt': terminal_attempt,
        }
    finally:
        root.removeHandler(sink)
        root.setLevel(previous)


def _spec_channel_message(stage, reason, attempt, flag_on):
    if reason in GUARD:
        return (
            'INFO',
            'batch_language_guard',
            'event=batch_language_guard outcome=held_for_redrive attempt=%d recovery=held stage=%s worker_reason=%s'
            % (attempt, stage, reason),
        )
    if stage == 'assemble_words' and reason in EMPTY:
        return (
            'INFO',
            'batch_empty_ladder',
            'event=batch_empty_ladder outcome=held_for_recovery attempt=%d recovery=held stage=%s worker_reason=%s'
            % (attempt, stage, reason),
        )
    if stage == 'fetch_decode' and reason in UNCONDITIONAL_FETCH:
        return (
            'INFO',
            'batch_validation_disposition',
            'event=batch_validation_disposition outcome=held_for_disposition attempt=%d recovery=held stage=%s worker_reason=%s'
            % (attempt, stage, reason),
        )
    if stage == 'persist' and reason in UNCONDITIONAL_PERSIST:
        return (
            'INFO',
            'batch_validation_disposition',
            'event=batch_validation_disposition outcome=held_for_disposition attempt=%d recovery=held stage=%s worker_reason=%s'
            % (attempt, stage, reason),
        )
    if reason in FLAGGED and flag_on:
        return (
            'INFO',
            'batch_validation_disposition',
            'event=batch_validation_disposition outcome=held_for_disposition attempt=%d recovery=held stage=%s worker_reason=%s'
            % (attempt, stage, reason),
        )
    return (
        'ERROR',
        'batch_quarantined',
        'event=batch_quarantined reason=worker_failed attempt=%d recovery=held stage=%s worker_reason=%s'
        % (attempt, stage, reason),
    )


def _spec(variant, stage, reason, foreign_stage, foreign_reason, quarantine, terminal_attempt, seq):
    same = {'stage': stage, 'reason': reason}
    foreign = {'stage': foreign_stage, 'reason': foreign_reason}
    has_wf = variant in ('wf', 'wfev')
    has_ev = variant in ('ev', 'wfev')
    last_ev = _seq_last_evidence(seq, terminal_attempt, same, foreign)
    is_terminal = has_wf or quarantine or terminal_attempt >= 5
    diag_stage = (
        same['stage'] if has_wf else (same['stage'] if has_ev else (last_ev['stage'] if last_ev else 'unknown'))
    )
    diag_reason = (
        same['reason'] if has_wf else (same['reason'] if has_ev else (last_ev['reason'] if last_ev else 'unclassified'))
    )
    expected = {}
    expected['rets'] = [True] * terminal_attempt
    expected['dupe'] = False
    expected['empty_evidence'] = None
    defer_lines = [
        ('INFO', 'event=batch_retry reason=worker_failed outcome=deferred attempt=%d' % attempt)
        for attempt in range(1, terminal_attempt + (0 if is_terminal else 1))
    ]
    if is_terminal:
        expected['state'] = 'quarantined'
        expected['attempt'] = terminal_attempt
        expected['failure'] = 'worker_failed'
        expected['quarantine_reason'] = 'worker_failed'
        expected['recovery_state'] = 'held'
        expected['merge_pending'] = False
        expected['retry_started_at'] = None
        expected['worker_failure'] = same if has_wf else None
        expected['worker_failure_evidence'] = same if has_ev else (dict(last_ev) if last_ev else None)
        level, event, message = _spec_channel_message(
            diag_stage, diag_reason, terminal_attempt, worker_validation_disposition_enabled()
        )
        records = defer_lines + [
            (level, message),
            ('WARNING', 'event=batch_recovery outcome=held reason=awaiting_fenced_recovery'),
        ]
        expected['line_count'] = len(records)
        expected['line1_level'] = records[0][0]
        expected['line1_event'] = records[0][1].split()[0][len('event=') :]
        expected['line1_attempt'] = '1' if defer_lines else str(terminal_attempt)
        expected['line1_stage'] = None if defer_lines else diag_stage
        expected['line1_reason'] = None if defer_lines else diag_reason
        expected['line1_message'] = records[0][1]
        expected['terminal_level'] = level
        expected['terminal_event'] = event
        expected['terminal_attempt'] = str(terminal_attempt)
        expected['terminal_stage'] = diag_stage
        expected['terminal_reason'] = diag_reason
        expected['terminal_message'] = message
        expected['warning_present'] = True
        expected['warning_level'] = 'WARNING'
        expected['defer_lines'] = len(defer_lines)
    else:
        expected['state'] = 'retry'
        expected['attempt'] = terminal_attempt
        expected['failure'] = 'worker_failed'
        expected['quarantine_reason'] = None
        expected['recovery_state'] = None
        expected['merge_pending'] = True
        expected['retry_started_at'] = 1001.0
        expected['worker_failure'] = None
        expected['worker_failure_evidence'] = same if has_ev else (dict(last_ev) if last_ev else None)
        backoff = min(600, 5 * 2 ** min(7, max(0, terminal_attempt - 1)))
        expected['available_at'] = terminal_attempt * 1000.0 + 1.0 + backoff
        records = defer_lines
        expected['line_count'] = len(records)
        expected['line1_level'] = 'INFO'
        expected['line1_event'] = 'batch_retry'
        expected['line1_attempt'] = '1'
        expected['line1_stage'] = None
        expected['line1_reason'] = None
        expected['line1_message'] = records[0][1]
        expected['terminal_level'] = None
        expected['terminal_event'] = None
        expected['terminal_attempt'] = None
        expected['terminal_stage'] = None
        expected['terminal_reason'] = None
        expected['terminal_message'] = None
        expected['warning_present'] = False
        expected['warning_level'] = None
        expected['defer_lines'] = len(defer_lines)
    expected['records'] = records
    expected['no_message_text'] = True
    return expected


@lru_cache(maxsize=None)
def _case(index):
    scenario = SCENARIOS[index]
    return _drive(*scenario), _spec(*scenario)


def _transcript_lines(transcript):
    return transcript['records']


SCENARIOS = [
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 1, 'bare_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 2, 'bare_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 2, 'ev_same_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 2, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 2, 'ev_same_first'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 2, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 3, 'bare_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 3, 'ev_same_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 3, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 3, 'ev_same_first'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 3, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 4, 'bare_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 4, 'ev_same_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 4, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 4, 'ev_same_first'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 4, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 5, 'bare_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 5, 'ev_same_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 5, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 5, 'ev_same_first'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', False, 5, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 1, 'bare_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 2, 'bare_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 2, 'ev_same_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 2, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 2, 'ev_same_first'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 2, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 3, 'bare_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 3, 'ev_same_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 3, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 3, 'ev_same_first'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 3, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 4, 'bare_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 4, 'ev_same_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 4, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 4, 'ev_same_first'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 4, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 5, 'bare_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 5, 'ev_same_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 5, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 5, 'ev_same_first'),
    ('wf', 'word_clocks', 'vad_bounds', 'word_clocks', 'empty_asr', True, 5, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 1, 'bare_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 2, 'bare_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 2, 'ev_same_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 2, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 2, 'ev_same_first'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 2, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 3, 'bare_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 3, 'ev_same_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 3, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 3, 'ev_same_first'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 3, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 4, 'bare_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 4, 'ev_same_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 4, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 4, 'ev_same_first'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 4, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 5, 'bare_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 5, 'ev_same_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 5, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 5, 'ev_same_first'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', False, 5, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 1, 'bare_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 2, 'bare_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 2, 'ev_same_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 2, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 2, 'ev_same_first'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 2, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 3, 'bare_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 3, 'ev_same_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 3, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 3, 'ev_same_first'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 3, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 4, 'bare_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 4, 'ev_same_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 4, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 4, 'ev_same_first'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 4, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 5, 'bare_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 5, 'ev_same_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 5, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 5, 'ev_same_first'),
    ('wf', 'word_clocks', 'empty_asr', 'word_clocks', 'no_owned_words', True, 5, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 1, 'bare_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 2, 'bare_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 2, 'ev_same_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 2, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 2, 'ev_same_first'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 2, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 3, 'bare_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 3, 'ev_same_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 3, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 3, 'ev_same_first'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 3, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 4, 'bare_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 4, 'ev_same_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 4, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 4, 'ev_same_first'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 4, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 5, 'bare_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 5, 'ev_same_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 5, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 5, 'ev_same_first'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', False, 5, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 1, 'bare_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 2, 'bare_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 2, 'ev_same_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 2, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 2, 'ev_same_first'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 2, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 3, 'bare_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 3, 'ev_same_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 3, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 3, 'ev_same_first'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 3, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 4, 'bare_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 4, 'ev_same_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 4, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 4, 'ev_same_first'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 4, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 5, 'bare_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 5, 'ev_same_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 5, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 5, 'ev_same_first'),
    ('wf', 'word_clocks', 'no_owned_words', 'word_clocks', 'unsupported_language', True, 5, 'ev_foreign_first'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', False, 1, 'bare_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', False, 2, 'bare_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', False, 2, 'ev_same_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', False, 2, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', False, 2, 'ev_same_first'),
    (
        'wf',
        'word_clocks',
        'unsupported_language',
        'word_clocks',
        'outside_admitted_source',
        False,
        2,
        'ev_foreign_first',
    ),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', False, 3, 'bare_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', False, 3, 'ev_same_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', False, 3, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', False, 3, 'ev_same_first'),
    (
        'wf',
        'word_clocks',
        'unsupported_language',
        'word_clocks',
        'outside_admitted_source',
        False,
        3,
        'ev_foreign_first',
    ),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', False, 4, 'bare_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', False, 4, 'ev_same_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', False, 4, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', False, 4, 'ev_same_first'),
    (
        'wf',
        'word_clocks',
        'unsupported_language',
        'word_clocks',
        'outside_admitted_source',
        False,
        4,
        'ev_foreign_first',
    ),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', False, 5, 'bare_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', False, 5, 'ev_same_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', False, 5, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', False, 5, 'ev_same_first'),
    (
        'wf',
        'word_clocks',
        'unsupported_language',
        'word_clocks',
        'outside_admitted_source',
        False,
        5,
        'ev_foreign_first',
    ),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', True, 1, 'bare_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', True, 2, 'bare_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', True, 2, 'ev_same_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', True, 2, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', True, 2, 'ev_same_first'),
    (
        'wf',
        'word_clocks',
        'unsupported_language',
        'word_clocks',
        'outside_admitted_source',
        True,
        2,
        'ev_foreign_first',
    ),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', True, 3, 'bare_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', True, 3, 'ev_same_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', True, 3, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', True, 3, 'ev_same_first'),
    (
        'wf',
        'word_clocks',
        'unsupported_language',
        'word_clocks',
        'outside_admitted_source',
        True,
        3,
        'ev_foreign_first',
    ),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', True, 4, 'bare_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', True, 4, 'ev_same_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', True, 4, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', True, 4, 'ev_same_first'),
    (
        'wf',
        'word_clocks',
        'unsupported_language',
        'word_clocks',
        'outside_admitted_source',
        True,
        4,
        'ev_foreign_first',
    ),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', True, 5, 'bare_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', True, 5, 'ev_same_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', True, 5, 'ev_foreign_all'),
    ('wf', 'word_clocks', 'unsupported_language', 'word_clocks', 'outside_admitted_source', True, 5, 'ev_same_first'),
    (
        'wf',
        'word_clocks',
        'unsupported_language',
        'word_clocks',
        'outside_admitted_source',
        True,
        5,
        'ev_foreign_first',
    ),
    ('wf', 'word_clocks', 'outside_admitted_source', 'word_clocks', 'persist_payload_invalid', False, 1, 'bare_all'),
    ('wf', 'word_clocks', 'outside_admitted_source', 'word_clocks', 'persist_payload_invalid', False, 2, 'bare_all'),
    ('wf', 'word_clocks', 'outside_admitted_source', 'word_clocks', 'persist_payload_invalid', False, 2, 'ev_same_all'),
    (
        'wf',
        'word_clocks',
        'outside_admitted_source',
        'word_clocks',
        'persist_payload_invalid',
        False,
        2,
        'ev_foreign_all',
    ),
    (
        'wf',
        'word_clocks',
        'outside_admitted_source',
        'word_clocks',
        'persist_payload_invalid',
        False,
        2,
        'ev_same_first',
    ),
    (
        'wf',
        'word_clocks',
        'outside_admitted_source',
        'word_clocks',
        'persist_payload_invalid',
        False,
        2,
        'ev_foreign_first',
    ),
    ('wf', 'word_clocks', 'outside_admitted_source', 'word_clocks', 'persist_payload_invalid', False, 3, 'bare_all'),
    ('wf', 'word_clocks', 'outside_admitted_source', 'word_clocks', 'persist_payload_invalid', False, 3, 'ev_same_all'),
    (
        'wf',
        'word_clocks',
        'outside_admitted_source',
        'word_clocks',
        'persist_payload_invalid',
        False,
        3,
        'ev_foreign_all',
    ),
    (
        'wf',
        'word_clocks',
        'outside_admitted_source',
        'word_clocks',
        'persist_payload_invalid',
        False,
        3,
        'ev_same_first',
    ),
    (
        'wf',
        'word_clocks',
        'outside_admitted_source',
        'word_clocks',
        'persist_payload_invalid',
        False,
        3,
        'ev_foreign_first',
    ),
    ('wf', 'word_clocks', 'outside_admitted_source', 'word_clocks', 'persist_payload_invalid', False, 4, 'bare_all'),
    ('wf', 'word_clocks', 'outside_admitted_source', 'word_clocks', 'persist_payload_invalid', False, 4, 'ev_same_all'),
    (
        'wf',
        'word_clocks',
        'outside_admitted_source',
        'word_clocks',
        'persist_payload_invalid',
        False,
        4,
        'ev_foreign_all',
    ),
]

FACET_NAMES = (
    'rets',
    'dupe',
    'dupe_state_stable',
    'records_exact',
    'state',
    'attempt',
    'failure',
    'quarantine_reason',
    'recovery_state',
    'worker_failure',
    'worker_failure_evidence',
    'empty_evidence',
    'merge_pending',
    'retry_started_at',
    'available_at_bound',
    'available_at_exact',
    'line_count',
    'line1_level',
    'line1_event',
    'line1_attempt',
    'line1_stage',
    'line1_reason',
    'line1_message',
    'terminal_message',
    'terminal_level',
    'terminal_event',
    'terminal_stage',
    'terminal_reason',
    'warning_present',
    'warning_level',
    'defer_lines',
    'no_message_text',
)


def _assert_facet(transcript, expected, facet):
    lines = _transcript_lines(transcript)
    if facet == 'rets':
        assert transcript['rets'] == expected['rets']
    elif facet == 'dupe':
        assert transcript['dupe'] == expected['dupe']
    elif facet == 'dupe_state_stable':
        assert transcript['state_after_dupe'] == transcript['state']
    elif facet == 'records_exact':
        assert lines == expected['records']
    elif facet == 'state':
        assert transcript['state'] == expected['state']
    elif facet == 'attempt':
        assert transcript['attempt'] == expected['attempt']
    elif facet == 'failure':
        assert transcript['failure'] == expected['failure']
    elif facet == 'quarantine_reason':
        assert transcript['quarantine_reason'] == expected['quarantine_reason']
    elif facet == 'recovery_state':
        assert transcript['recovery_state'] == expected['recovery_state']
    elif facet == 'worker_failure':
        assert transcript['worker_failure'] == expected['worker_failure']
    elif facet == 'worker_failure_evidence':
        assert transcript['worker_failure_evidence'] == expected['worker_failure_evidence']
    elif facet == 'empty_evidence':
        assert transcript['empty_evidence'] == expected['empty_evidence']
    elif facet == 'merge_pending':
        assert transcript['merge_pending'] == expected['merge_pending']
    elif facet == 'retry_started_at':
        assert transcript['retry_started_at'] == expected['retry_started_at']
    elif facet == 'available_at_bound':
        if expected['state'] == 'retry':
            assert 0 < transcript['available_at'] - transcript['last_now'] <= 600
    elif facet == 'available_at_exact':
        if expected['state'] == 'retry':
            backoff = min(600, 5 * 2 ** min(7, max(0, transcript['terminal_attempt'] - 1)))
            assert transcript['available_at'] == transcript['last_now'] + backoff
    elif facet == 'line_count':
        assert len(lines) == expected['line_count']
    elif facet == 'line1_level':
        assert lines[0][0] == expected['line1_level']
    elif facet == 'line1_event':
        assert lines[0][1].split()[0] == 'event=' + expected['line1_event']
    elif facet == 'line1_attempt':
        assert 'attempt=' + expected['line1_attempt'] in lines[0][1]
    elif facet == 'line1_stage':
        if expected['line1_stage'] is None:
            assert 'stage=' not in lines[0][1]
        else:
            assert 'stage=' + expected['line1_stage'] in lines[0][1]
    elif facet == 'line1_reason':
        if expected['line1_reason'] is None:
            assert 'worker_reason=' not in lines[0][1]
        else:
            assert 'worker_reason=' + expected['line1_reason'] in lines[0][1]
    elif facet == 'line1_message':
        assert lines[0][1] == expected['line1_message']
    elif facet == 'terminal_message':
        if expected['terminal_message'] is None:
            assert all('recovery=held' not in message for _level, message in lines)
        else:
            assert lines[-2][1] == expected['terminal_message']
    elif facet == 'terminal_level':
        if expected['terminal_level'] is None:
            assert all(level != 'ERROR' for level, _message in lines)
        else:
            assert lines[-2][0] == expected['terminal_level']
    elif facet == 'terminal_event':
        if expected['terminal_event'] is None:
            assert all('recovery=held' not in message for _level, message in lines)
        else:
            assert lines[-2][1].split()[0] == 'event=' + expected['terminal_event']
    elif facet == 'terminal_stage':
        if expected['terminal_stage'] is None:
            assert all('stage=' not in message for _level, message in lines)
        else:
            assert 'stage=' + expected['terminal_stage'] in lines[-2][1]
    elif facet == 'terminal_reason':
        if expected['terminal_reason'] is None:
            assert all('worker_reason=' not in message for _level, message in lines)
        else:
            assert 'worker_reason=' + expected['terminal_reason'] in lines[-2][1]
    elif facet == 'warning_present':
        events = [message.split()[0] for _level, message in lines]
        assert ('event=batch_recovery' in events) == expected['warning_present']
    elif facet == 'warning_level':
        if expected['warning_present']:
            assert lines[-1][0] == expected['warning_level']
    elif facet == 'defer_lines':
        retry_seen = sum(1 for _level, message in lines if message.startswith('event=batch_retry'))
        assert retry_seen == expected['defer_lines']
    elif facet == 'no_message_text':
        assert all('synthetic' not in message for _level, message in lines)
    else:
        raise AssertionError(facet)


def test_b09_w01w_00000_rets():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w01w_00000_dupe():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w01w_00000_dupe_state_stable():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w01w_00000_records_exact():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w01w_00000_state():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'state')


def test_b09_w01w_00000_attempt():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w01w_00000_failure():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w01w_00000_quarantine_reason():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w01w_00000_recovery_state():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w01w_00000_worker_failure():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w01w_00000_worker_failure_evidence():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w01w_00000_empty_evidence():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w01w_00000_merge_pending():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w01w_00000_retry_started_at():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w01w_00000_available_at_bound():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w01w_00000_available_at_exact():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w01w_00000_line_count():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w01w_00000_line1_level():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w01w_00000_line1_event():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w01w_00000_line1_attempt():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w01w_00000_line1_stage():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w01w_00000_line1_reason():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w01w_00000_line1_message():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w01w_00000_terminal_message():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w01w_00000_terminal_level():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w01w_00000_terminal_event():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w01w_00000_terminal_stage():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w01w_00000_terminal_reason():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w01w_00000_warning_present():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w01w_00000_warning_level():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w01w_00000_defer_lines():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w01w_00000_no_message_text():
    transcript, expected = _case(0)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00001_rets():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00001_dupe():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00001_dupe_state_stable():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00001_records_exact():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00001_state():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00001_attempt():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00001_failure():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00001_quarantine_reason():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00001_recovery_state():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00001_worker_failure():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00001_worker_failure_evidence():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00001_empty_evidence():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00001_merge_pending():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00001_retry_started_at():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00001_available_at_bound():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00001_available_at_exact():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00001_line_count():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00001_line1_level():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00001_line1_event():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00001_line1_attempt():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00001_line1_stage():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00001_line1_reason():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00001_line1_message():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00001_terminal_message():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00001_terminal_level():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00001_terminal_event():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00001_terminal_stage():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00001_terminal_reason():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00001_warning_present():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00001_warning_level():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00001_defer_lines():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00001_no_message_text():
    transcript, expected = _case(1)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00002_rets():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00002_dupe():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00002_dupe_state_stable():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00002_records_exact():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00002_state():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00002_attempt():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00002_failure():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00002_quarantine_reason():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00002_recovery_state():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00002_worker_failure():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00002_worker_failure_evidence():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00002_empty_evidence():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00002_merge_pending():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00002_retry_started_at():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00002_available_at_bound():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00002_available_at_exact():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00002_line_count():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00002_line1_level():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00002_line1_event():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00002_line1_attempt():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00002_line1_stage():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00002_line1_reason():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00002_line1_message():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00002_terminal_message():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00002_terminal_level():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00002_terminal_event():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00002_terminal_stage():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00002_terminal_reason():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00002_warning_present():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00002_warning_level():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00002_defer_lines():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00002_no_message_text():
    transcript, expected = _case(2)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00003_rets():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00003_dupe():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00003_dupe_state_stable():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00003_records_exact():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00003_state():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00003_attempt():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00003_failure():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00003_quarantine_reason():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00003_recovery_state():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00003_worker_failure():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00003_worker_failure_evidence():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00003_empty_evidence():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00003_merge_pending():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00003_retry_started_at():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00003_available_at_bound():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00003_available_at_exact():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00003_line_count():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00003_line1_level():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00003_line1_event():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00003_line1_attempt():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00003_line1_stage():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00003_line1_reason():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00003_line1_message():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00003_terminal_message():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00003_terminal_level():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00003_terminal_event():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00003_terminal_stage():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00003_terminal_reason():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00003_warning_present():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00003_warning_level():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00003_defer_lines():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00003_no_message_text():
    transcript, expected = _case(3)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00004_rets():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00004_dupe():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00004_dupe_state_stable():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00004_records_exact():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00004_state():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00004_attempt():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00004_failure():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00004_quarantine_reason():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00004_recovery_state():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00004_worker_failure():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00004_worker_failure_evidence():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00004_empty_evidence():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00004_merge_pending():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00004_retry_started_at():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00004_available_at_bound():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00004_available_at_exact():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00004_line_count():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00004_line1_level():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00004_line1_event():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00004_line1_attempt():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00004_line1_stage():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00004_line1_reason():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00004_line1_message():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00004_terminal_message():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00004_terminal_level():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00004_terminal_event():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00004_terminal_stage():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00004_terminal_reason():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00004_warning_present():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00004_warning_level():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00004_defer_lines():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00004_no_message_text():
    transcript, expected = _case(4)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00005_rets():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00005_dupe():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00005_dupe_state_stable():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00005_records_exact():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00005_state():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00005_attempt():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00005_failure():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00005_quarantine_reason():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00005_recovery_state():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00005_worker_failure():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00005_worker_failure_evidence():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00005_empty_evidence():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00005_merge_pending():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00005_retry_started_at():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00005_available_at_bound():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00005_available_at_exact():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00005_line_count():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00005_line1_level():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00005_line1_event():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00005_line1_attempt():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00005_line1_stage():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00005_line1_reason():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00005_line1_message():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00005_terminal_message():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00005_terminal_level():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00005_terminal_event():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00005_terminal_stage():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00005_terminal_reason():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00005_warning_present():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00005_warning_level():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00005_defer_lines():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00005_no_message_text():
    transcript, expected = _case(5)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00006_rets():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00006_dupe():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00006_dupe_state_stable():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00006_records_exact():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00006_state():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00006_attempt():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00006_failure():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00006_quarantine_reason():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00006_recovery_state():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00006_worker_failure():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00006_worker_failure_evidence():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00006_empty_evidence():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00006_merge_pending():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00006_retry_started_at():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00006_available_at_bound():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00006_available_at_exact():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00006_line_count():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00006_line1_level():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00006_line1_event():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00006_line1_attempt():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00006_line1_stage():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00006_line1_reason():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00006_line1_message():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00006_terminal_message():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00006_terminal_level():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00006_terminal_event():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00006_terminal_stage():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00006_terminal_reason():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00006_warning_present():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00006_warning_level():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00006_defer_lines():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00006_no_message_text():
    transcript, expected = _case(6)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00007_rets():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00007_dupe():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00007_dupe_state_stable():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00007_records_exact():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00007_state():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00007_attempt():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00007_failure():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00007_quarantine_reason():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00007_recovery_state():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00007_worker_failure():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00007_worker_failure_evidence():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00007_empty_evidence():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00007_merge_pending():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00007_retry_started_at():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00007_available_at_bound():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00007_available_at_exact():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00007_line_count():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00007_line1_level():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00007_line1_event():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00007_line1_attempt():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00007_line1_stage():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00007_line1_reason():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00007_line1_message():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00007_terminal_message():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00007_terminal_level():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00007_terminal_event():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00007_terminal_stage():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00007_terminal_reason():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00007_warning_present():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00007_warning_level():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00007_defer_lines():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00007_no_message_text():
    transcript, expected = _case(7)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00008_rets():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00008_dupe():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00008_dupe_state_stable():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00008_records_exact():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00008_state():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00008_attempt():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00008_failure():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00008_quarantine_reason():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00008_recovery_state():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00008_worker_failure():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00008_worker_failure_evidence():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00008_empty_evidence():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00008_merge_pending():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00008_retry_started_at():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00008_available_at_bound():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00008_available_at_exact():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00008_line_count():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00008_line1_level():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00008_line1_event():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00008_line1_attempt():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00008_line1_stage():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00008_line1_reason():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00008_line1_message():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00008_terminal_message():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00008_terminal_level():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00008_terminal_event():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00008_terminal_stage():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00008_terminal_reason():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00008_warning_present():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00008_warning_level():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00008_defer_lines():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00008_no_message_text():
    transcript, expected = _case(8)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00009_rets():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00009_dupe():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00009_dupe_state_stable():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00009_records_exact():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00009_state():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00009_attempt():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00009_failure():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00009_quarantine_reason():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00009_recovery_state():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00009_worker_failure():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00009_worker_failure_evidence():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00009_empty_evidence():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00009_merge_pending():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00009_retry_started_at():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00009_available_at_bound():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00009_available_at_exact():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00009_line_count():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00009_line1_level():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00009_line1_event():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00009_line1_attempt():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00009_line1_stage():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00009_line1_reason():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00009_line1_message():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00009_terminal_message():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00009_terminal_level():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00009_terminal_event():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00009_terminal_stage():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00009_terminal_reason():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00009_warning_present():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00009_warning_level():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00009_defer_lines():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00009_no_message_text():
    transcript, expected = _case(9)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00010_rets():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00010_dupe():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00010_dupe_state_stable():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00010_records_exact():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00010_state():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00010_attempt():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00010_failure():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00010_quarantine_reason():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00010_recovery_state():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00010_worker_failure():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00010_worker_failure_evidence():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00010_empty_evidence():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00010_merge_pending():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00010_retry_started_at():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00010_available_at_bound():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00010_available_at_exact():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00010_line_count():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00010_line1_level():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00010_line1_event():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00010_line1_attempt():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00010_line1_stage():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00010_line1_reason():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00010_line1_message():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00010_terminal_message():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00010_terminal_level():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00010_terminal_event():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00010_terminal_stage():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00010_terminal_reason():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00010_warning_present():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00010_warning_level():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00010_defer_lines():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00010_no_message_text():
    transcript, expected = _case(10)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00011_rets():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00011_dupe():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00011_dupe_state_stable():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00011_records_exact():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00011_state():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00011_attempt():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00011_failure():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00011_quarantine_reason():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00011_recovery_state():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00011_worker_failure():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00011_worker_failure_evidence():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00011_empty_evidence():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00011_merge_pending():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00011_retry_started_at():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00011_available_at_bound():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00011_available_at_exact():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00011_line_count():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00011_line1_level():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00011_line1_event():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00011_line1_attempt():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00011_line1_stage():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00011_line1_reason():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00011_line1_message():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00011_terminal_message():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00011_terminal_level():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00011_terminal_event():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00011_terminal_stage():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00011_terminal_reason():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00011_warning_present():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00011_warning_level():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00011_defer_lines():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00011_no_message_text():
    transcript, expected = _case(11)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00012_rets():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00012_dupe():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00012_dupe_state_stable():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00012_records_exact():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00012_state():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00012_attempt():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00012_failure():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00012_quarantine_reason():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00012_recovery_state():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00012_worker_failure():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00012_worker_failure_evidence():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00012_empty_evidence():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00012_merge_pending():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00012_retry_started_at():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00012_available_at_bound():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00012_available_at_exact():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00012_line_count():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00012_line1_level():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00012_line1_event():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00012_line1_attempt():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00012_line1_stage():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00012_line1_reason():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00012_line1_message():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00012_terminal_message():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00012_terminal_level():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00012_terminal_event():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00012_terminal_stage():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00012_terminal_reason():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00012_warning_present():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00012_warning_level():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00012_defer_lines():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00012_no_message_text():
    transcript, expected = _case(12)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00013_rets():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00013_dupe():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00013_dupe_state_stable():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00013_records_exact():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00013_state():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00013_attempt():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00013_failure():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00013_quarantine_reason():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00013_recovery_state():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00013_worker_failure():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00013_worker_failure_evidence():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00013_empty_evidence():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00013_merge_pending():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00013_retry_started_at():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00013_available_at_bound():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00013_available_at_exact():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00013_line_count():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00013_line1_level():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00013_line1_event():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00013_line1_attempt():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00013_line1_stage():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00013_line1_reason():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00013_line1_message():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00013_terminal_message():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00013_terminal_level():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00013_terminal_event():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00013_terminal_stage():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00013_terminal_reason():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00013_warning_present():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00013_warning_level():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00013_defer_lines():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00013_no_message_text():
    transcript, expected = _case(13)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00014_rets():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00014_dupe():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00014_dupe_state_stable():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00014_records_exact():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00014_state():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00014_attempt():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00014_failure():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00014_quarantine_reason():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00014_recovery_state():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00014_worker_failure():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00014_worker_failure_evidence():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00014_empty_evidence():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00014_merge_pending():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00014_retry_started_at():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00014_available_at_bound():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00014_available_at_exact():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00014_line_count():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00014_line1_level():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00014_line1_event():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00014_line1_attempt():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00014_line1_stage():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00014_line1_reason():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00014_line1_message():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00014_terminal_message():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00014_terminal_level():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00014_terminal_event():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00014_terminal_stage():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00014_terminal_reason():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00014_warning_present():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00014_warning_level():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00014_defer_lines():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00014_no_message_text():
    transcript, expected = _case(14)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00015_rets():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00015_dupe():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00015_dupe_state_stable():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00015_records_exact():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00015_state():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00015_attempt():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00015_failure():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00015_quarantine_reason():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00015_recovery_state():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00015_worker_failure():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00015_worker_failure_evidence():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00015_empty_evidence():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00015_merge_pending():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00015_retry_started_at():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00015_available_at_bound():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00015_available_at_exact():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00015_line_count():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00015_line1_level():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00015_line1_event():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00015_line1_attempt():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00015_line1_stage():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00015_line1_reason():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00015_line1_message():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00015_terminal_message():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00015_terminal_level():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00015_terminal_event():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00015_terminal_stage():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00015_terminal_reason():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00015_warning_present():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00015_warning_level():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00015_defer_lines():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00015_no_message_text():
    transcript, expected = _case(15)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00016_rets():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00016_dupe():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00016_dupe_state_stable():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00016_records_exact():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00016_state():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00016_attempt():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00016_failure():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00016_quarantine_reason():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00016_recovery_state():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00016_worker_failure():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00016_worker_failure_evidence():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00016_empty_evidence():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00016_merge_pending():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00016_retry_started_at():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00016_available_at_bound():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00016_available_at_exact():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00016_line_count():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00016_line1_level():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00016_line1_event():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00016_line1_attempt():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00016_line1_stage():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00016_line1_reason():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00016_line1_message():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00016_terminal_message():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00016_terminal_level():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00016_terminal_event():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00016_terminal_stage():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00016_terminal_reason():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00016_warning_present():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00016_warning_level():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00016_defer_lines():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00016_no_message_text():
    transcript, expected = _case(16)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00017_rets():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00017_dupe():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00017_dupe_state_stable():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00017_records_exact():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00017_state():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00017_attempt():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00017_failure():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00017_quarantine_reason():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00017_recovery_state():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00017_worker_failure():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00017_worker_failure_evidence():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00017_empty_evidence():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00017_merge_pending():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00017_retry_started_at():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00017_available_at_bound():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00017_available_at_exact():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00017_line_count():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00017_line1_level():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00017_line1_event():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00017_line1_attempt():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00017_line1_stage():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00017_line1_reason():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00017_line1_message():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00017_terminal_message():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00017_terminal_level():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00017_terminal_event():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00017_terminal_stage():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00017_terminal_reason():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00017_warning_present():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00017_warning_level():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00017_defer_lines():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00017_no_message_text():
    transcript, expected = _case(17)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00018_rets():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00018_dupe():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00018_dupe_state_stable():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00018_records_exact():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00018_state():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00018_attempt():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00018_failure():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00018_quarantine_reason():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00018_recovery_state():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00018_worker_failure():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00018_worker_failure_evidence():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00018_empty_evidence():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00018_merge_pending():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00018_retry_started_at():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00018_available_at_bound():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00018_available_at_exact():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00018_line_count():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00018_line1_level():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00018_line1_event():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00018_line1_attempt():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00018_line1_stage():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00018_line1_reason():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00018_line1_message():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00018_terminal_message():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00018_terminal_level():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00018_terminal_event():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00018_terminal_stage():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00018_terminal_reason():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00018_warning_present():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00018_warning_level():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00018_defer_lines():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00018_no_message_text():
    transcript, expected = _case(18)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00019_rets():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00019_dupe():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00019_dupe_state_stable():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00019_records_exact():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00019_state():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00019_attempt():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00019_failure():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00019_quarantine_reason():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00019_recovery_state():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00019_worker_failure():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00019_worker_failure_evidence():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00019_empty_evidence():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00019_merge_pending():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00019_retry_started_at():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00019_available_at_bound():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00019_available_at_exact():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00019_line_count():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00019_line1_level():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00019_line1_event():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00019_line1_attempt():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00019_line1_stage():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00019_line1_reason():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00019_line1_message():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00019_terminal_message():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00019_terminal_level():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00019_terminal_event():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00019_terminal_stage():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00019_terminal_reason():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00019_warning_present():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00019_warning_level():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00019_defer_lines():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00019_no_message_text():
    transcript, expected = _case(19)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00020_rets():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00020_dupe():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00020_dupe_state_stable():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00020_records_exact():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00020_state():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00020_attempt():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00020_failure():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00020_quarantine_reason():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00020_recovery_state():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00020_worker_failure():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00020_worker_failure_evidence():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00020_empty_evidence():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00020_merge_pending():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00020_retry_started_at():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00020_available_at_bound():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00020_available_at_exact():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00020_line_count():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00020_line1_level():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00020_line1_event():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00020_line1_attempt():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00020_line1_stage():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00020_line1_reason():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00020_line1_message():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00020_terminal_message():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00020_terminal_level():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00020_terminal_event():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00020_terminal_stage():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00020_terminal_reason():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00020_warning_present():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00020_warning_level():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00020_defer_lines():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00020_no_message_text():
    transcript, expected = _case(20)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w11w_00021_rets():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w11w_00021_dupe():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w11w_00021_dupe_state_stable():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w11w_00021_records_exact():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w11w_00021_state():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'state')


def test_b09_w11w_00021_attempt():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w11w_00021_failure():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w11w_00021_quarantine_reason():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w11w_00021_recovery_state():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w11w_00021_worker_failure():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w11w_00021_worker_failure_evidence():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w11w_00021_empty_evidence():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w11w_00021_merge_pending():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w11w_00021_retry_started_at():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w11w_00021_available_at_bound():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w11w_00021_available_at_exact():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w11w_00021_line_count():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w11w_00021_line1_level():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w11w_00021_line1_event():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w11w_00021_line1_attempt():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w11w_00021_line1_stage():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w11w_00021_line1_reason():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w11w_00021_line1_message():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w11w_00021_terminal_message():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w11w_00021_terminal_level():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w11w_00021_terminal_event():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w11w_00021_terminal_stage():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w11w_00021_terminal_reason():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w11w_00021_warning_present():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w11w_00021_warning_level():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w11w_00021_defer_lines():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w11w_00021_no_message_text():
    transcript, expected = _case(21)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00022_rets():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00022_dupe():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00022_dupe_state_stable():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00022_records_exact():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00022_state():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00022_attempt():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00022_failure():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00022_quarantine_reason():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00022_recovery_state():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00022_worker_failure():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00022_worker_failure_evidence():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00022_empty_evidence():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00022_merge_pending():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00022_retry_started_at():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00022_available_at_bound():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00022_available_at_exact():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00022_line_count():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00022_line1_level():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00022_line1_event():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00022_line1_attempt():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00022_line1_stage():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00022_line1_reason():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00022_line1_message():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00022_terminal_message():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00022_terminal_level():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00022_terminal_event():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00022_terminal_stage():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00022_terminal_reason():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00022_warning_present():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00022_warning_level():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00022_defer_lines():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00022_no_message_text():
    transcript, expected = _case(22)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00023_rets():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00023_dupe():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00023_dupe_state_stable():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00023_records_exact():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00023_state():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00023_attempt():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00023_failure():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00023_quarantine_reason():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00023_recovery_state():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00023_worker_failure():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00023_worker_failure_evidence():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00023_empty_evidence():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00023_merge_pending():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00023_retry_started_at():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00023_available_at_bound():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00023_available_at_exact():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00023_line_count():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00023_line1_level():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00023_line1_event():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00023_line1_attempt():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00023_line1_stage():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00023_line1_reason():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00023_line1_message():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00023_terminal_message():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00023_terminal_level():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00023_terminal_event():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00023_terminal_stage():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00023_terminal_reason():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00023_warning_present():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00023_warning_level():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00023_defer_lines():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00023_no_message_text():
    transcript, expected = _case(23)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00024_rets():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00024_dupe():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00024_dupe_state_stable():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00024_records_exact():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00024_state():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00024_attempt():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00024_failure():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00024_quarantine_reason():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00024_recovery_state():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00024_worker_failure():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00024_worker_failure_evidence():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00024_empty_evidence():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00024_merge_pending():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00024_retry_started_at():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00024_available_at_bound():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00024_available_at_exact():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00024_line_count():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00024_line1_level():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00024_line1_event():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00024_line1_attempt():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00024_line1_stage():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00024_line1_reason():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00024_line1_message():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00024_terminal_message():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00024_terminal_level():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00024_terminal_event():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00024_terminal_stage():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00024_terminal_reason():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00024_warning_present():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00024_warning_level():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00024_defer_lines():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00024_no_message_text():
    transcript, expected = _case(24)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00025_rets():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00025_dupe():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00025_dupe_state_stable():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00025_records_exact():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00025_state():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00025_attempt():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00025_failure():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00025_quarantine_reason():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00025_recovery_state():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00025_worker_failure():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00025_worker_failure_evidence():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00025_empty_evidence():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00025_merge_pending():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00025_retry_started_at():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00025_available_at_bound():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00025_available_at_exact():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00025_line_count():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00025_line1_level():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00025_line1_event():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00025_line1_attempt():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00025_line1_stage():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00025_line1_reason():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00025_line1_message():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00025_terminal_message():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00025_terminal_level():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00025_terminal_event():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00025_terminal_stage():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00025_terminal_reason():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00025_warning_present():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00025_warning_level():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00025_defer_lines():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00025_no_message_text():
    transcript, expected = _case(25)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00026_rets():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00026_dupe():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00026_dupe_state_stable():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00026_records_exact():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00026_state():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00026_attempt():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00026_failure():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00026_quarantine_reason():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00026_recovery_state():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00026_worker_failure():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00026_worker_failure_evidence():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00026_empty_evidence():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00026_merge_pending():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00026_retry_started_at():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00026_available_at_bound():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00026_available_at_exact():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00026_line_count():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00026_line1_level():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00026_line1_event():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00026_line1_attempt():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00026_line1_stage():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00026_line1_reason():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00026_line1_message():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00026_terminal_message():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00026_terminal_level():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00026_terminal_event():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00026_terminal_stage():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00026_terminal_reason():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00026_warning_present():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00026_warning_level():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00026_defer_lines():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00026_no_message_text():
    transcript, expected = _case(26)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00027_rets():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00027_dupe():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00027_dupe_state_stable():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00027_records_exact():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00027_state():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00027_attempt():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00027_failure():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00027_quarantine_reason():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00027_recovery_state():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00027_worker_failure():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00027_worker_failure_evidence():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00027_empty_evidence():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00027_merge_pending():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00027_retry_started_at():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00027_available_at_bound():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00027_available_at_exact():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00027_line_count():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00027_line1_level():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00027_line1_event():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00027_line1_attempt():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00027_line1_stage():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00027_line1_reason():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00027_line1_message():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00027_terminal_message():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00027_terminal_level():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00027_terminal_event():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00027_terminal_stage():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00027_terminal_reason():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00027_warning_present():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00027_warning_level():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00027_defer_lines():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00027_no_message_text():
    transcript, expected = _case(27)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00028_rets():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00028_dupe():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00028_dupe_state_stable():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00028_records_exact():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00028_state():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00028_attempt():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00028_failure():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00028_quarantine_reason():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00028_recovery_state():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00028_worker_failure():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00028_worker_failure_evidence():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00028_empty_evidence():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00028_merge_pending():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00028_retry_started_at():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00028_available_at_bound():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00028_available_at_exact():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00028_line_count():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00028_line1_level():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00028_line1_event():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00028_line1_attempt():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00028_line1_stage():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00028_line1_reason():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00028_line1_message():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00028_terminal_message():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00028_terminal_level():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00028_terminal_event():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00028_terminal_stage():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00028_terminal_reason():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00028_warning_present():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00028_warning_level():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00028_defer_lines():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00028_no_message_text():
    transcript, expected = _case(28)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00029_rets():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00029_dupe():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00029_dupe_state_stable():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00029_records_exact():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00029_state():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00029_attempt():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00029_failure():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00029_quarantine_reason():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00029_recovery_state():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00029_worker_failure():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00029_worker_failure_evidence():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00029_empty_evidence():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00029_merge_pending():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00029_retry_started_at():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00029_available_at_bound():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00029_available_at_exact():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00029_line_count():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00029_line1_level():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00029_line1_event():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00029_line1_attempt():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00029_line1_stage():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00029_line1_reason():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00029_line1_message():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00029_terminal_message():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00029_terminal_level():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00029_terminal_event():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00029_terminal_stage():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00029_terminal_reason():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00029_warning_present():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00029_warning_level():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00029_defer_lines():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00029_no_message_text():
    transcript, expected = _case(29)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00030_rets():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00030_dupe():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00030_dupe_state_stable():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00030_records_exact():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00030_state():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00030_attempt():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00030_failure():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00030_quarantine_reason():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00030_recovery_state():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00030_worker_failure():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00030_worker_failure_evidence():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00030_empty_evidence():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00030_merge_pending():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00030_retry_started_at():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00030_available_at_bound():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00030_available_at_exact():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00030_line_count():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00030_line1_level():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00030_line1_event():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00030_line1_attempt():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00030_line1_stage():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00030_line1_reason():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00030_line1_message():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00030_terminal_message():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00030_terminal_level():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00030_terminal_event():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00030_terminal_stage():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00030_terminal_reason():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00030_warning_present():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00030_warning_level():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00030_defer_lines():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00030_no_message_text():
    transcript, expected = _case(30)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00031_rets():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00031_dupe():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00031_dupe_state_stable():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00031_records_exact():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00031_state():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00031_attempt():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00031_failure():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00031_quarantine_reason():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00031_recovery_state():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00031_worker_failure():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00031_worker_failure_evidence():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00031_empty_evidence():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00031_merge_pending():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00031_retry_started_at():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00031_available_at_bound():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00031_available_at_exact():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00031_line_count():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00031_line1_level():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00031_line1_event():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00031_line1_attempt():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00031_line1_stage():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00031_line1_reason():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00031_line1_message():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00031_terminal_message():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00031_terminal_level():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00031_terminal_event():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00031_terminal_stage():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00031_terminal_reason():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00031_warning_present():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00031_warning_level():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00031_defer_lines():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00031_no_message_text():
    transcript, expected = _case(31)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00032_rets():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00032_dupe():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00032_dupe_state_stable():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00032_records_exact():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00032_state():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00032_attempt():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00032_failure():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00032_quarantine_reason():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00032_recovery_state():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00032_worker_failure():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00032_worker_failure_evidence():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00032_empty_evidence():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00032_merge_pending():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00032_retry_started_at():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00032_available_at_bound():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00032_available_at_exact():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00032_line_count():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00032_line1_level():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00032_line1_event():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00032_line1_attempt():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00032_line1_stage():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00032_line1_reason():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00032_line1_message():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00032_terminal_message():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00032_terminal_level():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00032_terminal_event():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00032_terminal_stage():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00032_terminal_reason():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00032_warning_present():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00032_warning_level():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00032_defer_lines():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00032_no_message_text():
    transcript, expected = _case(32)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00033_rets():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00033_dupe():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00033_dupe_state_stable():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00033_records_exact():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00033_state():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00033_attempt():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00033_failure():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00033_quarantine_reason():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00033_recovery_state():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00033_worker_failure():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00033_worker_failure_evidence():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00033_empty_evidence():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00033_merge_pending():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00033_retry_started_at():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00033_available_at_bound():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00033_available_at_exact():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00033_line_count():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00033_line1_level():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00033_line1_event():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00033_line1_attempt():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00033_line1_stage():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00033_line1_reason():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00033_line1_message():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00033_terminal_message():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00033_terminal_level():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00033_terminal_event():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00033_terminal_stage():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00033_terminal_reason():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00033_warning_present():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00033_warning_level():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00033_defer_lines():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00033_no_message_text():
    transcript, expected = _case(33)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00034_rets():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00034_dupe():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00034_dupe_state_stable():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00034_records_exact():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00034_state():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00034_attempt():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00034_failure():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00034_quarantine_reason():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00034_recovery_state():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00034_worker_failure():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00034_worker_failure_evidence():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00034_empty_evidence():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00034_merge_pending():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00034_retry_started_at():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00034_available_at_bound():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00034_available_at_exact():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00034_line_count():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00034_line1_level():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00034_line1_event():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00034_line1_attempt():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00034_line1_stage():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00034_line1_reason():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00034_line1_message():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00034_terminal_message():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00034_terminal_level():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00034_terminal_event():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00034_terminal_stage():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00034_terminal_reason():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00034_warning_present():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00034_warning_level():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00034_defer_lines():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00034_no_message_text():
    transcript, expected = _case(34)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00035_rets():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00035_dupe():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00035_dupe_state_stable():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00035_records_exact():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00035_state():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00035_attempt():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00035_failure():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00035_quarantine_reason():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00035_recovery_state():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00035_worker_failure():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00035_worker_failure_evidence():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00035_empty_evidence():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00035_merge_pending():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00035_retry_started_at():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00035_available_at_bound():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00035_available_at_exact():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00035_line_count():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00035_line1_level():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00035_line1_event():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00035_line1_attempt():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00035_line1_stage():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00035_line1_reason():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00035_line1_message():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00035_terminal_message():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00035_terminal_level():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00035_terminal_event():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00035_terminal_stage():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00035_terminal_reason():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00035_warning_present():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00035_warning_level():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00035_defer_lines():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00035_no_message_text():
    transcript, expected = _case(35)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00036_rets():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00036_dupe():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00036_dupe_state_stable():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00036_records_exact():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00036_state():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00036_attempt():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00036_failure():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00036_quarantine_reason():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00036_recovery_state():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00036_worker_failure():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00036_worker_failure_evidence():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00036_empty_evidence():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00036_merge_pending():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00036_retry_started_at():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00036_available_at_bound():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00036_available_at_exact():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00036_line_count():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00036_line1_level():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00036_line1_event():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00036_line1_attempt():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00036_line1_stage():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00036_line1_reason():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00036_line1_message():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00036_terminal_message():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00036_terminal_level():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00036_terminal_event():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00036_terminal_stage():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00036_terminal_reason():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00036_warning_present():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00036_warning_level():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00036_defer_lines():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00036_no_message_text():
    transcript, expected = _case(36)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00037_rets():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00037_dupe():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00037_dupe_state_stable():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00037_records_exact():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00037_state():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00037_attempt():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00037_failure():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00037_quarantine_reason():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00037_recovery_state():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00037_worker_failure():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00037_worker_failure_evidence():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00037_empty_evidence():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00037_merge_pending():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00037_retry_started_at():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00037_available_at_bound():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00037_available_at_exact():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00037_line_count():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00037_line1_level():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00037_line1_event():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00037_line1_attempt():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00037_line1_stage():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00037_line1_reason():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00037_line1_message():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00037_terminal_message():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00037_terminal_level():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00037_terminal_event():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00037_terminal_stage():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00037_terminal_reason():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00037_warning_present():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00037_warning_level():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00037_defer_lines():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00037_no_message_text():
    transcript, expected = _case(37)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00038_rets():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00038_dupe():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00038_dupe_state_stable():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00038_records_exact():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00038_state():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00038_attempt():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00038_failure():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00038_quarantine_reason():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00038_recovery_state():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00038_worker_failure():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00038_worker_failure_evidence():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00038_empty_evidence():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00038_merge_pending():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00038_retry_started_at():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00038_available_at_bound():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00038_available_at_exact():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00038_line_count():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00038_line1_level():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00038_line1_event():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00038_line1_attempt():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00038_line1_stage():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00038_line1_reason():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00038_line1_message():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00038_terminal_message():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00038_terminal_level():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00038_terminal_event():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00038_terminal_stage():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00038_terminal_reason():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00038_warning_present():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00038_warning_level():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00038_defer_lines():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00038_no_message_text():
    transcript, expected = _case(38)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00039_rets():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00039_dupe():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00039_dupe_state_stable():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00039_records_exact():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00039_state():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00039_attempt():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00039_failure():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00039_quarantine_reason():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00039_recovery_state():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00039_worker_failure():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00039_worker_failure_evidence():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00039_empty_evidence():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00039_merge_pending():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00039_retry_started_at():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00039_available_at_bound():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00039_available_at_exact():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00039_line_count():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00039_line1_level():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00039_line1_event():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00039_line1_attempt():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00039_line1_stage():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00039_line1_reason():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00039_line1_message():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00039_terminal_message():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00039_terminal_level():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00039_terminal_event():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00039_terminal_stage():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00039_terminal_reason():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00039_warning_present():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00039_warning_level():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00039_defer_lines():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00039_no_message_text():
    transcript, expected = _case(39)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00040_rets():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00040_dupe():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00040_dupe_state_stable():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00040_records_exact():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00040_state():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00040_attempt():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00040_failure():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00040_quarantine_reason():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00040_recovery_state():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00040_worker_failure():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00040_worker_failure_evidence():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00040_empty_evidence():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00040_merge_pending():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00040_retry_started_at():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00040_available_at_bound():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00040_available_at_exact():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00040_line_count():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00040_line1_level():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00040_line1_event():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00040_line1_attempt():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00040_line1_stage():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00040_line1_reason():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00040_line1_message():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00040_terminal_message():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00040_terminal_level():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00040_terminal_event():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00040_terminal_stage():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00040_terminal_reason():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00040_warning_present():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00040_warning_level():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00040_defer_lines():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00040_no_message_text():
    transcript, expected = _case(40)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00041_rets():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00041_dupe():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00041_dupe_state_stable():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00041_records_exact():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00041_state():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00041_attempt():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00041_failure():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00041_quarantine_reason():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00041_recovery_state():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00041_worker_failure():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00041_worker_failure_evidence():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00041_empty_evidence():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00041_merge_pending():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00041_retry_started_at():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00041_available_at_bound():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00041_available_at_exact():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00041_line_count():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00041_line1_level():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00041_line1_event():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00041_line1_attempt():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00041_line1_stage():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00041_line1_reason():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00041_line1_message():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00041_terminal_message():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00041_terminal_level():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00041_terminal_event():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00041_terminal_stage():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00041_terminal_reason():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00041_warning_present():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00041_warning_level():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00041_defer_lines():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00041_no_message_text():
    transcript, expected = _case(41)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w01w_00042_rets():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w01w_00042_dupe():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w01w_00042_dupe_state_stable():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w01w_00042_records_exact():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w01w_00042_state():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'state')


def test_b09_w01w_00042_attempt():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w01w_00042_failure():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w01w_00042_quarantine_reason():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w01w_00042_recovery_state():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w01w_00042_worker_failure():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w01w_00042_worker_failure_evidence():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w01w_00042_empty_evidence():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w01w_00042_merge_pending():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w01w_00042_retry_started_at():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w01w_00042_available_at_bound():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w01w_00042_available_at_exact():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w01w_00042_line_count():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w01w_00042_line1_level():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w01w_00042_line1_event():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w01w_00042_line1_attempt():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w01w_00042_line1_stage():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w01w_00042_line1_reason():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w01w_00042_line1_message():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w01w_00042_terminal_message():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w01w_00042_terminal_level():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w01w_00042_terminal_event():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w01w_00042_terminal_stage():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w01w_00042_terminal_reason():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w01w_00042_warning_present():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w01w_00042_warning_level():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w01w_00042_defer_lines():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w01w_00042_no_message_text():
    transcript, expected = _case(42)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00043_rets():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00043_dupe():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00043_dupe_state_stable():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00043_records_exact():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00043_state():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00043_attempt():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00043_failure():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00043_quarantine_reason():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00043_recovery_state():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00043_worker_failure():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00043_worker_failure_evidence():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00043_empty_evidence():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00043_merge_pending():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00043_retry_started_at():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00043_available_at_bound():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00043_available_at_exact():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00043_line_count():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00043_line1_level():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00043_line1_event():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00043_line1_attempt():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00043_line1_stage():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00043_line1_reason():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00043_line1_message():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00043_terminal_message():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00043_terminal_level():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00043_terminal_event():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00043_terminal_stage():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00043_terminal_reason():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00043_warning_present():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00043_warning_level():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00043_defer_lines():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00043_no_message_text():
    transcript, expected = _case(43)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00044_rets():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00044_dupe():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00044_dupe_state_stable():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00044_records_exact():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00044_state():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00044_attempt():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00044_failure():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00044_quarantine_reason():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00044_recovery_state():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00044_worker_failure():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00044_worker_failure_evidence():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00044_empty_evidence():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00044_merge_pending():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00044_retry_started_at():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00044_available_at_bound():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00044_available_at_exact():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00044_line_count():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00044_line1_level():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00044_line1_event():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00044_line1_attempt():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00044_line1_stage():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00044_line1_reason():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00044_line1_message():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00044_terminal_message():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00044_terminal_level():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00044_terminal_event():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00044_terminal_stage():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00044_terminal_reason():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00044_warning_present():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00044_warning_level():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00044_defer_lines():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00044_no_message_text():
    transcript, expected = _case(44)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00045_rets():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00045_dupe():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00045_dupe_state_stable():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00045_records_exact():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00045_state():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00045_attempt():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00045_failure():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00045_quarantine_reason():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00045_recovery_state():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00045_worker_failure():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00045_worker_failure_evidence():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00045_empty_evidence():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00045_merge_pending():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00045_retry_started_at():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00045_available_at_bound():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00045_available_at_exact():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00045_line_count():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00045_line1_level():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00045_line1_event():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00045_line1_attempt():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00045_line1_stage():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00045_line1_reason():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00045_line1_message():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00045_terminal_message():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00045_terminal_level():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00045_terminal_event():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00045_terminal_stage():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00045_terminal_reason():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00045_warning_present():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00045_warning_level():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00045_defer_lines():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00045_no_message_text():
    transcript, expected = _case(45)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00046_rets():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00046_dupe():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00046_dupe_state_stable():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00046_records_exact():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00046_state():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00046_attempt():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00046_failure():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00046_quarantine_reason():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00046_recovery_state():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00046_worker_failure():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00046_worker_failure_evidence():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00046_empty_evidence():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00046_merge_pending():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00046_retry_started_at():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00046_available_at_bound():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00046_available_at_exact():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00046_line_count():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00046_line1_level():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00046_line1_event():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00046_line1_attempt():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00046_line1_stage():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00046_line1_reason():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00046_line1_message():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00046_terminal_message():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00046_terminal_level():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00046_terminal_event():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00046_terminal_stage():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00046_terminal_reason():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00046_warning_present():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00046_warning_level():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00046_defer_lines():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00046_no_message_text():
    transcript, expected = _case(46)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00047_rets():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00047_dupe():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00047_dupe_state_stable():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00047_records_exact():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00047_state():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00047_attempt():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00047_failure():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00047_quarantine_reason():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00047_recovery_state():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00047_worker_failure():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00047_worker_failure_evidence():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00047_empty_evidence():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00047_merge_pending():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00047_retry_started_at():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00047_available_at_bound():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00047_available_at_exact():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00047_line_count():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00047_line1_level():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00047_line1_event():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00047_line1_attempt():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00047_line1_stage():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00047_line1_reason():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00047_line1_message():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00047_terminal_message():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00047_terminal_level():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00047_terminal_event():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00047_terminal_stage():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00047_terminal_reason():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00047_warning_present():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00047_warning_level():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00047_defer_lines():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00047_no_message_text():
    transcript, expected = _case(47)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00048_rets():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00048_dupe():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00048_dupe_state_stable():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00048_records_exact():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00048_state():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00048_attempt():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00048_failure():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00048_quarantine_reason():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00048_recovery_state():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00048_worker_failure():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00048_worker_failure_evidence():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00048_empty_evidence():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00048_merge_pending():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00048_retry_started_at():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00048_available_at_bound():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00048_available_at_exact():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00048_line_count():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00048_line1_level():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00048_line1_event():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00048_line1_attempt():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00048_line1_stage():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00048_line1_reason():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00048_line1_message():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00048_terminal_message():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00048_terminal_level():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00048_terminal_event():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00048_terminal_stage():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00048_terminal_reason():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00048_warning_present():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00048_warning_level():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00048_defer_lines():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00048_no_message_text():
    transcript, expected = _case(48)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00049_rets():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00049_dupe():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00049_dupe_state_stable():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00049_records_exact():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00049_state():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00049_attempt():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00049_failure():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00049_quarantine_reason():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00049_recovery_state():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00049_worker_failure():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00049_worker_failure_evidence():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00049_empty_evidence():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00049_merge_pending():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00049_retry_started_at():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00049_available_at_bound():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00049_available_at_exact():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00049_line_count():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00049_line1_level():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00049_line1_event():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00049_line1_attempt():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00049_line1_stage():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00049_line1_reason():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00049_line1_message():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00049_terminal_message():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00049_terminal_level():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00049_terminal_event():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00049_terminal_stage():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00049_terminal_reason():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00049_warning_present():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00049_warning_level():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00049_defer_lines():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00049_no_message_text():
    transcript, expected = _case(49)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00050_rets():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00050_dupe():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00050_dupe_state_stable():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00050_records_exact():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00050_state():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00050_attempt():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00050_failure():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00050_quarantine_reason():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00050_recovery_state():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00050_worker_failure():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00050_worker_failure_evidence():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00050_empty_evidence():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00050_merge_pending():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00050_retry_started_at():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00050_available_at_bound():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00050_available_at_exact():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00050_line_count():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00050_line1_level():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00050_line1_event():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00050_line1_attempt():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00050_line1_stage():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00050_line1_reason():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00050_line1_message():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00050_terminal_message():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00050_terminal_level():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00050_terminal_event():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00050_terminal_stage():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00050_terminal_reason():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00050_warning_present():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00050_warning_level():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00050_defer_lines():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00050_no_message_text():
    transcript, expected = _case(50)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00051_rets():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00051_dupe():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00051_dupe_state_stable():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00051_records_exact():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00051_state():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00051_attempt():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00051_failure():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00051_quarantine_reason():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00051_recovery_state():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00051_worker_failure():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00051_worker_failure_evidence():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00051_empty_evidence():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00051_merge_pending():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00051_retry_started_at():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00051_available_at_bound():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00051_available_at_exact():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00051_line_count():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00051_line1_level():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00051_line1_event():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00051_line1_attempt():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00051_line1_stage():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00051_line1_reason():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00051_line1_message():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00051_terminal_message():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00051_terminal_level():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00051_terminal_event():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00051_terminal_stage():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00051_terminal_reason():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00051_warning_present():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00051_warning_level():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00051_defer_lines():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00051_no_message_text():
    transcript, expected = _case(51)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00052_rets():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00052_dupe():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00052_dupe_state_stable():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00052_records_exact():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00052_state():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00052_attempt():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00052_failure():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00052_quarantine_reason():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00052_recovery_state():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00052_worker_failure():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00052_worker_failure_evidence():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00052_empty_evidence():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00052_merge_pending():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00052_retry_started_at():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00052_available_at_bound():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00052_available_at_exact():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00052_line_count():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00052_line1_level():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00052_line1_event():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00052_line1_attempt():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00052_line1_stage():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00052_line1_reason():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00052_line1_message():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00052_terminal_message():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00052_terminal_level():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00052_terminal_event():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00052_terminal_stage():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00052_terminal_reason():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00052_warning_present():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00052_warning_level():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00052_defer_lines():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00052_no_message_text():
    transcript, expected = _case(52)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00053_rets():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00053_dupe():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00053_dupe_state_stable():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00053_records_exact():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00053_state():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00053_attempt():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00053_failure():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00053_quarantine_reason():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00053_recovery_state():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00053_worker_failure():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00053_worker_failure_evidence():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00053_empty_evidence():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00053_merge_pending():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00053_retry_started_at():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00053_available_at_bound():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00053_available_at_exact():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00053_line_count():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00053_line1_level():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00053_line1_event():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00053_line1_attempt():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00053_line1_stage():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00053_line1_reason():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00053_line1_message():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00053_terminal_message():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00053_terminal_level():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00053_terminal_event():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00053_terminal_stage():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00053_terminal_reason():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00053_warning_present():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00053_warning_level():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00053_defer_lines():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00053_no_message_text():
    transcript, expected = _case(53)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00054_rets():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00054_dupe():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00054_dupe_state_stable():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00054_records_exact():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00054_state():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00054_attempt():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00054_failure():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00054_quarantine_reason():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00054_recovery_state():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00054_worker_failure():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00054_worker_failure_evidence():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00054_empty_evidence():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00054_merge_pending():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00054_retry_started_at():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00054_available_at_bound():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00054_available_at_exact():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00054_line_count():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00054_line1_level():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00054_line1_event():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00054_line1_attempt():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00054_line1_stage():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00054_line1_reason():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00054_line1_message():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00054_terminal_message():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00054_terminal_level():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00054_terminal_event():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00054_terminal_stage():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00054_terminal_reason():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00054_warning_present():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00054_warning_level():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00054_defer_lines():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00054_no_message_text():
    transcript, expected = _case(54)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00055_rets():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00055_dupe():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00055_dupe_state_stable():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00055_records_exact():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00055_state():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00055_attempt():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00055_failure():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00055_quarantine_reason():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00055_recovery_state():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00055_worker_failure():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00055_worker_failure_evidence():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00055_empty_evidence():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00055_merge_pending():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00055_retry_started_at():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00055_available_at_bound():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00055_available_at_exact():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00055_line_count():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00055_line1_level():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00055_line1_event():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00055_line1_attempt():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00055_line1_stage():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00055_line1_reason():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00055_line1_message():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00055_terminal_message():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00055_terminal_level():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00055_terminal_event():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00055_terminal_stage():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00055_terminal_reason():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00055_warning_present():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00055_warning_level():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00055_defer_lines():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00055_no_message_text():
    transcript, expected = _case(55)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00056_rets():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00056_dupe():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00056_dupe_state_stable():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00056_records_exact():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00056_state():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00056_attempt():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00056_failure():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00056_quarantine_reason():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00056_recovery_state():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00056_worker_failure():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00056_worker_failure_evidence():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00056_empty_evidence():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00056_merge_pending():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00056_retry_started_at():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00056_available_at_bound():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00056_available_at_exact():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00056_line_count():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00056_line1_level():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00056_line1_event():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00056_line1_attempt():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00056_line1_stage():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00056_line1_reason():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00056_line1_message():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00056_terminal_message():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00056_terminal_level():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00056_terminal_event():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00056_terminal_stage():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00056_terminal_reason():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00056_warning_present():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00056_warning_level():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00056_defer_lines():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00056_no_message_text():
    transcript, expected = _case(56)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00057_rets():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00057_dupe():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00057_dupe_state_stable():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00057_records_exact():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00057_state():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00057_attempt():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00057_failure():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00057_quarantine_reason():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00057_recovery_state():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00057_worker_failure():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00057_worker_failure_evidence():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00057_empty_evidence():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00057_merge_pending():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00057_retry_started_at():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00057_available_at_bound():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00057_available_at_exact():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00057_line_count():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00057_line1_level():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00057_line1_event():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00057_line1_attempt():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00057_line1_stage():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00057_line1_reason():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00057_line1_message():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00057_terminal_message():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00057_terminal_level():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00057_terminal_event():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00057_terminal_stage():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00057_terminal_reason():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00057_warning_present():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00057_warning_level():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00057_defer_lines():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00057_no_message_text():
    transcript, expected = _case(57)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00058_rets():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00058_dupe():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00058_dupe_state_stable():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00058_records_exact():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00058_state():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00058_attempt():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00058_failure():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00058_quarantine_reason():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00058_recovery_state():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00058_worker_failure():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00058_worker_failure_evidence():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00058_empty_evidence():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00058_merge_pending():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00058_retry_started_at():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00058_available_at_bound():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00058_available_at_exact():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00058_line_count():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00058_line1_level():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00058_line1_event():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00058_line1_attempt():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00058_line1_stage():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00058_line1_reason():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00058_line1_message():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00058_terminal_message():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00058_terminal_level():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00058_terminal_event():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00058_terminal_stage():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00058_terminal_reason():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00058_warning_present():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00058_warning_level():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00058_defer_lines():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00058_no_message_text():
    transcript, expected = _case(58)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00059_rets():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00059_dupe():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00059_dupe_state_stable():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00059_records_exact():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00059_state():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00059_attempt():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00059_failure():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00059_quarantine_reason():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00059_recovery_state():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00059_worker_failure():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00059_worker_failure_evidence():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00059_empty_evidence():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00059_merge_pending():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00059_retry_started_at():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00059_available_at_bound():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00059_available_at_exact():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00059_line_count():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00059_line1_level():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00059_line1_event():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00059_line1_attempt():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00059_line1_stage():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00059_line1_reason():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00059_line1_message():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00059_terminal_message():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00059_terminal_level():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00059_terminal_event():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00059_terminal_stage():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00059_terminal_reason():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00059_warning_present():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00059_warning_level():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00059_defer_lines():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00059_no_message_text():
    transcript, expected = _case(59)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00060_rets():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00060_dupe():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00060_dupe_state_stable():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00060_records_exact():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00060_state():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00060_attempt():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00060_failure():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00060_quarantine_reason():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00060_recovery_state():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00060_worker_failure():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00060_worker_failure_evidence():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00060_empty_evidence():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00060_merge_pending():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00060_retry_started_at():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00060_available_at_bound():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00060_available_at_exact():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00060_line_count():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00060_line1_level():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00060_line1_event():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00060_line1_attempt():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00060_line1_stage():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00060_line1_reason():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00060_line1_message():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00060_terminal_message():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00060_terminal_level():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00060_terminal_event():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00060_terminal_stage():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00060_terminal_reason():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00060_warning_present():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00060_warning_level():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00060_defer_lines():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00060_no_message_text():
    transcript, expected = _case(60)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00061_rets():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00061_dupe():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00061_dupe_state_stable():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00061_records_exact():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00061_state():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00061_attempt():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00061_failure():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00061_quarantine_reason():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00061_recovery_state():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00061_worker_failure():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00061_worker_failure_evidence():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00061_empty_evidence():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00061_merge_pending():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00061_retry_started_at():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00061_available_at_bound():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00061_available_at_exact():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00061_line_count():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00061_line1_level():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00061_line1_event():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00061_line1_attempt():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00061_line1_stage():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00061_line1_reason():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00061_line1_message():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00061_terminal_message():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00061_terminal_level():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00061_terminal_event():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00061_terminal_stage():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00061_terminal_reason():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00061_warning_present():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00061_warning_level():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00061_defer_lines():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00061_no_message_text():
    transcript, expected = _case(61)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00062_rets():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00062_dupe():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00062_dupe_state_stable():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00062_records_exact():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00062_state():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00062_attempt():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00062_failure():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00062_quarantine_reason():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00062_recovery_state():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00062_worker_failure():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00062_worker_failure_evidence():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00062_empty_evidence():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00062_merge_pending():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00062_retry_started_at():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00062_available_at_bound():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00062_available_at_exact():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00062_line_count():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00062_line1_level():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00062_line1_event():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00062_line1_attempt():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00062_line1_stage():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00062_line1_reason():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00062_line1_message():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00062_terminal_message():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00062_terminal_level():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00062_terminal_event():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00062_terminal_stage():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00062_terminal_reason():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00062_warning_present():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00062_warning_level():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00062_defer_lines():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00062_no_message_text():
    transcript, expected = _case(62)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w11w_00063_rets():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w11w_00063_dupe():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w11w_00063_dupe_state_stable():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w11w_00063_records_exact():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w11w_00063_state():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'state')


def test_b09_w11w_00063_attempt():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w11w_00063_failure():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w11w_00063_quarantine_reason():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w11w_00063_recovery_state():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w11w_00063_worker_failure():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w11w_00063_worker_failure_evidence():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w11w_00063_empty_evidence():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w11w_00063_merge_pending():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w11w_00063_retry_started_at():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w11w_00063_available_at_bound():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w11w_00063_available_at_exact():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w11w_00063_line_count():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w11w_00063_line1_level():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w11w_00063_line1_event():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w11w_00063_line1_attempt():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w11w_00063_line1_stage():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w11w_00063_line1_reason():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w11w_00063_line1_message():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w11w_00063_terminal_message():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w11w_00063_terminal_level():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w11w_00063_terminal_event():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w11w_00063_terminal_stage():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w11w_00063_terminal_reason():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w11w_00063_warning_present():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w11w_00063_warning_level():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w11w_00063_defer_lines():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w11w_00063_no_message_text():
    transcript, expected = _case(63)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00064_rets():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00064_dupe():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00064_dupe_state_stable():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00064_records_exact():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00064_state():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00064_attempt():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00064_failure():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00064_quarantine_reason():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00064_recovery_state():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00064_worker_failure():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00064_worker_failure_evidence():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00064_empty_evidence():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00064_merge_pending():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00064_retry_started_at():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00064_available_at_bound():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00064_available_at_exact():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00064_line_count():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00064_line1_level():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00064_line1_event():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00064_line1_attempt():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00064_line1_stage():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00064_line1_reason():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00064_line1_message():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00064_terminal_message():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00064_terminal_level():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00064_terminal_event():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00064_terminal_stage():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00064_terminal_reason():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00064_warning_present():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00064_warning_level():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00064_defer_lines():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00064_no_message_text():
    transcript, expected = _case(64)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00065_rets():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00065_dupe():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00065_dupe_state_stable():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00065_records_exact():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00065_state():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00065_attempt():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00065_failure():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00065_quarantine_reason():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00065_recovery_state():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00065_worker_failure():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00065_worker_failure_evidence():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00065_empty_evidence():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00065_merge_pending():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00065_retry_started_at():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00065_available_at_bound():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00065_available_at_exact():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00065_line_count():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00065_line1_level():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00065_line1_event():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00065_line1_attempt():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00065_line1_stage():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00065_line1_reason():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00065_line1_message():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00065_terminal_message():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00065_terminal_level():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00065_terminal_event():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00065_terminal_stage():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00065_terminal_reason():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00065_warning_present():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00065_warning_level():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00065_defer_lines():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00065_no_message_text():
    transcript, expected = _case(65)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00066_rets():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00066_dupe():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00066_dupe_state_stable():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00066_records_exact():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00066_state():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00066_attempt():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00066_failure():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00066_quarantine_reason():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00066_recovery_state():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00066_worker_failure():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00066_worker_failure_evidence():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00066_empty_evidence():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00066_merge_pending():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00066_retry_started_at():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00066_available_at_bound():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00066_available_at_exact():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00066_line_count():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00066_line1_level():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00066_line1_event():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00066_line1_attempt():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00066_line1_stage():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00066_line1_reason():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00066_line1_message():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00066_terminal_message():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00066_terminal_level():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00066_terminal_event():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00066_terminal_stage():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00066_terminal_reason():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00066_warning_present():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00066_warning_level():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00066_defer_lines():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00066_no_message_text():
    transcript, expected = _case(66)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00067_rets():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00067_dupe():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00067_dupe_state_stable():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00067_records_exact():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00067_state():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00067_attempt():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00067_failure():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00067_quarantine_reason():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00067_recovery_state():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00067_worker_failure():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00067_worker_failure_evidence():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00067_empty_evidence():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00067_merge_pending():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00067_retry_started_at():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00067_available_at_bound():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00067_available_at_exact():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00067_line_count():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00067_line1_level():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00067_line1_event():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00067_line1_attempt():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00067_line1_stage():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00067_line1_reason():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00067_line1_message():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00067_terminal_message():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00067_terminal_level():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00067_terminal_event():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00067_terminal_stage():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00067_terminal_reason():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00067_warning_present():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00067_warning_level():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00067_defer_lines():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00067_no_message_text():
    transcript, expected = _case(67)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00068_rets():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00068_dupe():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00068_dupe_state_stable():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00068_records_exact():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00068_state():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00068_attempt():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00068_failure():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00068_quarantine_reason():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00068_recovery_state():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00068_worker_failure():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00068_worker_failure_evidence():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00068_empty_evidence():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00068_merge_pending():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00068_retry_started_at():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00068_available_at_bound():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00068_available_at_exact():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00068_line_count():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00068_line1_level():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00068_line1_event():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00068_line1_attempt():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00068_line1_stage():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00068_line1_reason():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00068_line1_message():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00068_terminal_message():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00068_terminal_level():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00068_terminal_event():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00068_terminal_stage():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00068_terminal_reason():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00068_warning_present():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00068_warning_level():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00068_defer_lines():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00068_no_message_text():
    transcript, expected = _case(68)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00069_rets():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00069_dupe():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00069_dupe_state_stable():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00069_records_exact():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00069_state():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00069_attempt():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00069_failure():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00069_quarantine_reason():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00069_recovery_state():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00069_worker_failure():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00069_worker_failure_evidence():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00069_empty_evidence():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00069_merge_pending():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00069_retry_started_at():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00069_available_at_bound():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00069_available_at_exact():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00069_line_count():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00069_line1_level():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00069_line1_event():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00069_line1_attempt():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00069_line1_stage():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00069_line1_reason():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00069_line1_message():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00069_terminal_message():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00069_terminal_level():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00069_terminal_event():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00069_terminal_stage():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00069_terminal_reason():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00069_warning_present():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00069_warning_level():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00069_defer_lines():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00069_no_message_text():
    transcript, expected = _case(69)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00070_rets():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00070_dupe():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00070_dupe_state_stable():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00070_records_exact():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00070_state():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00070_attempt():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00070_failure():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00070_quarantine_reason():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00070_recovery_state():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00070_worker_failure():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00070_worker_failure_evidence():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00070_empty_evidence():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00070_merge_pending():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00070_retry_started_at():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00070_available_at_bound():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00070_available_at_exact():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00070_line_count():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00070_line1_level():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00070_line1_event():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00070_line1_attempt():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00070_line1_stage():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00070_line1_reason():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00070_line1_message():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00070_terminal_message():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00070_terminal_level():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00070_terminal_event():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00070_terminal_stage():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00070_terminal_reason():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00070_warning_present():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00070_warning_level():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00070_defer_lines():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00070_no_message_text():
    transcript, expected = _case(70)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00071_rets():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00071_dupe():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00071_dupe_state_stable():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00071_records_exact():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00071_state():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00071_attempt():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00071_failure():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00071_quarantine_reason():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00071_recovery_state():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00071_worker_failure():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00071_worker_failure_evidence():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00071_empty_evidence():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00071_merge_pending():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00071_retry_started_at():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00071_available_at_bound():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00071_available_at_exact():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00071_line_count():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00071_line1_level():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00071_line1_event():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00071_line1_attempt():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00071_line1_stage():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00071_line1_reason():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00071_line1_message():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00071_terminal_message():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00071_terminal_level():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00071_terminal_event():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00071_terminal_stage():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00071_terminal_reason():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00071_warning_present():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00071_warning_level():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00071_defer_lines():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00071_no_message_text():
    transcript, expected = _case(71)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00072_rets():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00072_dupe():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00072_dupe_state_stable():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00072_records_exact():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00072_state():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00072_attempt():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00072_failure():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00072_quarantine_reason():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00072_recovery_state():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00072_worker_failure():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00072_worker_failure_evidence():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00072_empty_evidence():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00072_merge_pending():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00072_retry_started_at():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00072_available_at_bound():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00072_available_at_exact():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00072_line_count():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00072_line1_level():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00072_line1_event():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00072_line1_attempt():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00072_line1_stage():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00072_line1_reason():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00072_line1_message():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00072_terminal_message():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00072_terminal_level():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00072_terminal_event():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00072_terminal_stage():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00072_terminal_reason():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00072_warning_present():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00072_warning_level():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00072_defer_lines():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00072_no_message_text():
    transcript, expected = _case(72)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00073_rets():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00073_dupe():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00073_dupe_state_stable():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00073_records_exact():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00073_state():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00073_attempt():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00073_failure():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00073_quarantine_reason():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00073_recovery_state():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00073_worker_failure():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00073_worker_failure_evidence():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00073_empty_evidence():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00073_merge_pending():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00073_retry_started_at():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00073_available_at_bound():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00073_available_at_exact():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00073_line_count():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00073_line1_level():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00073_line1_event():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00073_line1_attempt():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00073_line1_stage():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00073_line1_reason():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00073_line1_message():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00073_terminal_message():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00073_terminal_level():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00073_terminal_event():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00073_terminal_stage():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00073_terminal_reason():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00073_warning_present():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00073_warning_level():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00073_defer_lines():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00073_no_message_text():
    transcript, expected = _case(73)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00074_rets():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00074_dupe():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00074_dupe_state_stable():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00074_records_exact():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00074_state():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00074_attempt():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00074_failure():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00074_quarantine_reason():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00074_recovery_state():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00074_worker_failure():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00074_worker_failure_evidence():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00074_empty_evidence():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00074_merge_pending():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00074_retry_started_at():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00074_available_at_bound():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00074_available_at_exact():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00074_line_count():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00074_line1_level():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00074_line1_event():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00074_line1_attempt():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00074_line1_stage():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00074_line1_reason():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00074_line1_message():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00074_terminal_message():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00074_terminal_level():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00074_terminal_event():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00074_terminal_stage():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00074_terminal_reason():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00074_warning_present():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00074_warning_level():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00074_defer_lines():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00074_no_message_text():
    transcript, expected = _case(74)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00075_rets():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00075_dupe():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00075_dupe_state_stable():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00075_records_exact():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00075_state():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00075_attempt():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00075_failure():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00075_quarantine_reason():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00075_recovery_state():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00075_worker_failure():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00075_worker_failure_evidence():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00075_empty_evidence():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00075_merge_pending():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00075_retry_started_at():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00075_available_at_bound():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00075_available_at_exact():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00075_line_count():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00075_line1_level():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00075_line1_event():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00075_line1_attempt():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00075_line1_stage():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00075_line1_reason():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00075_line1_message():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00075_terminal_message():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00075_terminal_level():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00075_terminal_event():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00075_terminal_stage():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00075_terminal_reason():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00075_warning_present():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00075_warning_level():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00075_defer_lines():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00075_no_message_text():
    transcript, expected = _case(75)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00076_rets():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00076_dupe():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00076_dupe_state_stable():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00076_records_exact():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00076_state():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00076_attempt():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00076_failure():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00076_quarantine_reason():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00076_recovery_state():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00076_worker_failure():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00076_worker_failure_evidence():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00076_empty_evidence():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00076_merge_pending():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00076_retry_started_at():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00076_available_at_bound():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00076_available_at_exact():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00076_line_count():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00076_line1_level():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00076_line1_event():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00076_line1_attempt():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00076_line1_stage():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00076_line1_reason():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00076_line1_message():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00076_terminal_message():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00076_terminal_level():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00076_terminal_event():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00076_terminal_stage():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00076_terminal_reason():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00076_warning_present():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00076_warning_level():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00076_defer_lines():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00076_no_message_text():
    transcript, expected = _case(76)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00077_rets():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00077_dupe():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00077_dupe_state_stable():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00077_records_exact():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00077_state():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00077_attempt():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00077_failure():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00077_quarantine_reason():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00077_recovery_state():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00077_worker_failure():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00077_worker_failure_evidence():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00077_empty_evidence():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00077_merge_pending():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00077_retry_started_at():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00077_available_at_bound():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00077_available_at_exact():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00077_line_count():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00077_line1_level():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00077_line1_event():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00077_line1_attempt():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00077_line1_stage():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00077_line1_reason():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00077_line1_message():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00077_terminal_message():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00077_terminal_level():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00077_terminal_event():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00077_terminal_stage():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00077_terminal_reason():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00077_warning_present():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00077_warning_level():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00077_defer_lines():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00077_no_message_text():
    transcript, expected = _case(77)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00078_rets():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00078_dupe():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00078_dupe_state_stable():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00078_records_exact():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00078_state():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00078_attempt():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00078_failure():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00078_quarantine_reason():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00078_recovery_state():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00078_worker_failure():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00078_worker_failure_evidence():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00078_empty_evidence():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00078_merge_pending():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00078_retry_started_at():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00078_available_at_bound():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00078_available_at_exact():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00078_line_count():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00078_line1_level():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00078_line1_event():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00078_line1_attempt():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00078_line1_stage():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00078_line1_reason():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00078_line1_message():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00078_terminal_message():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00078_terminal_level():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00078_terminal_event():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00078_terminal_stage():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00078_terminal_reason():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00078_warning_present():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00078_warning_level():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00078_defer_lines():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00078_no_message_text():
    transcript, expected = _case(78)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00079_rets():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00079_dupe():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00079_dupe_state_stable():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00079_records_exact():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00079_state():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00079_attempt():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00079_failure():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00079_quarantine_reason():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00079_recovery_state():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00079_worker_failure():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00079_worker_failure_evidence():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00079_empty_evidence():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00079_merge_pending():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00079_retry_started_at():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00079_available_at_bound():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00079_available_at_exact():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00079_line_count():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00079_line1_level():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00079_line1_event():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00079_line1_attempt():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00079_line1_stage():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00079_line1_reason():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00079_line1_message():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00079_terminal_message():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00079_terminal_level():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00079_terminal_event():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00079_terminal_stage():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00079_terminal_reason():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00079_warning_present():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00079_warning_level():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00079_defer_lines():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00079_no_message_text():
    transcript, expected = _case(79)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00080_rets():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00080_dupe():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00080_dupe_state_stable():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00080_records_exact():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00080_state():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00080_attempt():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00080_failure():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00080_quarantine_reason():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00080_recovery_state():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00080_worker_failure():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00080_worker_failure_evidence():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00080_empty_evidence():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00080_merge_pending():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00080_retry_started_at():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00080_available_at_bound():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00080_available_at_exact():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00080_line_count():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00080_line1_level():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00080_line1_event():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00080_line1_attempt():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00080_line1_stage():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00080_line1_reason():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00080_line1_message():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00080_terminal_message():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00080_terminal_level():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00080_terminal_event():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00080_terminal_stage():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00080_terminal_reason():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00080_warning_present():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00080_warning_level():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00080_defer_lines():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00080_no_message_text():
    transcript, expected = _case(80)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00081_rets():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00081_dupe():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00081_dupe_state_stable():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00081_records_exact():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00081_state():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00081_attempt():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00081_failure():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00081_quarantine_reason():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00081_recovery_state():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00081_worker_failure():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00081_worker_failure_evidence():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00081_empty_evidence():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00081_merge_pending():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00081_retry_started_at():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00081_available_at_bound():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00081_available_at_exact():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00081_line_count():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00081_line1_level():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00081_line1_event():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00081_line1_attempt():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00081_line1_stage():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00081_line1_reason():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00081_line1_message():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00081_terminal_message():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00081_terminal_level():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00081_terminal_event():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00081_terminal_stage():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00081_terminal_reason():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00081_warning_present():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00081_warning_level():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00081_defer_lines():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00081_no_message_text():
    transcript, expected = _case(81)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00082_rets():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00082_dupe():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00082_dupe_state_stable():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00082_records_exact():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00082_state():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00082_attempt():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00082_failure():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00082_quarantine_reason():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00082_recovery_state():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00082_worker_failure():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00082_worker_failure_evidence():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00082_empty_evidence():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00082_merge_pending():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00082_retry_started_at():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00082_available_at_bound():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00082_available_at_exact():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00082_line_count():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00082_line1_level():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00082_line1_event():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00082_line1_attempt():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00082_line1_stage():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00082_line1_reason():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00082_line1_message():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00082_terminal_message():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00082_terminal_level():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00082_terminal_event():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00082_terminal_stage():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00082_terminal_reason():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00082_warning_present():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00082_warning_level():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00082_defer_lines():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00082_no_message_text():
    transcript, expected = _case(82)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00083_rets():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00083_dupe():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00083_dupe_state_stable():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00083_records_exact():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00083_state():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00083_attempt():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00083_failure():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00083_quarantine_reason():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00083_recovery_state():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00083_worker_failure():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00083_worker_failure_evidence():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00083_empty_evidence():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00083_merge_pending():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00083_retry_started_at():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00083_available_at_bound():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00083_available_at_exact():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00083_line_count():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00083_line1_level():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00083_line1_event():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00083_line1_attempt():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00083_line1_stage():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00083_line1_reason():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00083_line1_message():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00083_terminal_message():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00083_terminal_level():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00083_terminal_event():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00083_terminal_stage():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00083_terminal_reason():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00083_warning_present():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00083_warning_level():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00083_defer_lines():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00083_no_message_text():
    transcript, expected = _case(83)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w01w_00084_rets():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w01w_00084_dupe():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w01w_00084_dupe_state_stable():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w01w_00084_records_exact():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w01w_00084_state():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'state')


def test_b09_w01w_00084_attempt():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w01w_00084_failure():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w01w_00084_quarantine_reason():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w01w_00084_recovery_state():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w01w_00084_worker_failure():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w01w_00084_worker_failure_evidence():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w01w_00084_empty_evidence():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w01w_00084_merge_pending():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w01w_00084_retry_started_at():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w01w_00084_available_at_bound():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w01w_00084_available_at_exact():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w01w_00084_line_count():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w01w_00084_line1_level():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w01w_00084_line1_event():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w01w_00084_line1_attempt():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w01w_00084_line1_stage():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w01w_00084_line1_reason():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w01w_00084_line1_message():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w01w_00084_terminal_message():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w01w_00084_terminal_level():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w01w_00084_terminal_event():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w01w_00084_terminal_stage():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w01w_00084_terminal_reason():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w01w_00084_warning_present():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w01w_00084_warning_level():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w01w_00084_defer_lines():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w01w_00084_no_message_text():
    transcript, expected = _case(84)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00085_rets():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00085_dupe():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00085_dupe_state_stable():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00085_records_exact():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00085_state():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00085_attempt():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00085_failure():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00085_quarantine_reason():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00085_recovery_state():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00085_worker_failure():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00085_worker_failure_evidence():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00085_empty_evidence():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00085_merge_pending():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00085_retry_started_at():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00085_available_at_bound():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00085_available_at_exact():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00085_line_count():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00085_line1_level():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00085_line1_event():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00085_line1_attempt():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00085_line1_stage():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00085_line1_reason():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00085_line1_message():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00085_terminal_message():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00085_terminal_level():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00085_terminal_event():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00085_terminal_stage():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00085_terminal_reason():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00085_warning_present():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00085_warning_level():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00085_defer_lines():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00085_no_message_text():
    transcript, expected = _case(85)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00086_rets():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00086_dupe():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00086_dupe_state_stable():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00086_records_exact():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00086_state():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00086_attempt():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00086_failure():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00086_quarantine_reason():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00086_recovery_state():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00086_worker_failure():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00086_worker_failure_evidence():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00086_empty_evidence():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00086_merge_pending():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00086_retry_started_at():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00086_available_at_bound():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00086_available_at_exact():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00086_line_count():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00086_line1_level():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00086_line1_event():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00086_line1_attempt():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00086_line1_stage():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00086_line1_reason():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00086_line1_message():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00086_terminal_message():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00086_terminal_level():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00086_terminal_event():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00086_terminal_stage():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00086_terminal_reason():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00086_warning_present():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00086_warning_level():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00086_defer_lines():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00086_no_message_text():
    transcript, expected = _case(86)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00087_rets():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00087_dupe():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00087_dupe_state_stable():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00087_records_exact():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00087_state():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00087_attempt():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00087_failure():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00087_quarantine_reason():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00087_recovery_state():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00087_worker_failure():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00087_worker_failure_evidence():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00087_empty_evidence():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00087_merge_pending():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00087_retry_started_at():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00087_available_at_bound():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00087_available_at_exact():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00087_line_count():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00087_line1_level():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00087_line1_event():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00087_line1_attempt():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00087_line1_stage():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00087_line1_reason():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00087_line1_message():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00087_terminal_message():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00087_terminal_level():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00087_terminal_event():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00087_terminal_stage():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00087_terminal_reason():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00087_warning_present():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00087_warning_level():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00087_defer_lines():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00087_no_message_text():
    transcript, expected = _case(87)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00088_rets():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00088_dupe():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00088_dupe_state_stable():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00088_records_exact():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00088_state():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00088_attempt():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00088_failure():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00088_quarantine_reason():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00088_recovery_state():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00088_worker_failure():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00088_worker_failure_evidence():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00088_empty_evidence():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00088_merge_pending():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00088_retry_started_at():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00088_available_at_bound():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00088_available_at_exact():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00088_line_count():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00088_line1_level():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00088_line1_event():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00088_line1_attempt():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00088_line1_stage():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00088_line1_reason():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00088_line1_message():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00088_terminal_message():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00088_terminal_level():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00088_terminal_event():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00088_terminal_stage():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00088_terminal_reason():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00088_warning_present():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00088_warning_level():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00088_defer_lines():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00088_no_message_text():
    transcript, expected = _case(88)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00089_rets():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00089_dupe():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00089_dupe_state_stable():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00089_records_exact():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00089_state():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00089_attempt():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00089_failure():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00089_quarantine_reason():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00089_recovery_state():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00089_worker_failure():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00089_worker_failure_evidence():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00089_empty_evidence():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00089_merge_pending():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00089_retry_started_at():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00089_available_at_bound():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00089_available_at_exact():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00089_line_count():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00089_line1_level():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00089_line1_event():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00089_line1_attempt():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00089_line1_stage():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00089_line1_reason():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00089_line1_message():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00089_terminal_message():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00089_terminal_level():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00089_terminal_event():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00089_terminal_stage():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00089_terminal_reason():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00089_warning_present():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00089_warning_level():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00089_defer_lines():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00089_no_message_text():
    transcript, expected = _case(89)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00090_rets():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00090_dupe():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00090_dupe_state_stable():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00090_records_exact():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00090_state():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00090_attempt():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00090_failure():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00090_quarantine_reason():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00090_recovery_state():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00090_worker_failure():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00090_worker_failure_evidence():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00090_empty_evidence():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00090_merge_pending():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00090_retry_started_at():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00090_available_at_bound():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00090_available_at_exact():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00090_line_count():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00090_line1_level():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00090_line1_event():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00090_line1_attempt():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00090_line1_stage():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00090_line1_reason():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00090_line1_message():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00090_terminal_message():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00090_terminal_level():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00090_terminal_event():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00090_terminal_stage():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00090_terminal_reason():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00090_warning_present():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00090_warning_level():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00090_defer_lines():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00090_no_message_text():
    transcript, expected = _case(90)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00091_rets():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00091_dupe():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00091_dupe_state_stable():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00091_records_exact():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00091_state():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00091_attempt():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00091_failure():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00091_quarantine_reason():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00091_recovery_state():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00091_worker_failure():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00091_worker_failure_evidence():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00091_empty_evidence():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00091_merge_pending():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00091_retry_started_at():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00091_available_at_bound():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00091_available_at_exact():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00091_line_count():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00091_line1_level():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00091_line1_event():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00091_line1_attempt():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00091_line1_stage():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00091_line1_reason():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00091_line1_message():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00091_terminal_message():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00091_terminal_level():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00091_terminal_event():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00091_terminal_stage():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00091_terminal_reason():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00091_warning_present():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00091_warning_level():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00091_defer_lines():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00091_no_message_text():
    transcript, expected = _case(91)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00092_rets():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00092_dupe():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00092_dupe_state_stable():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00092_records_exact():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00092_state():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00092_attempt():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00092_failure():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00092_quarantine_reason():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00092_recovery_state():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00092_worker_failure():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00092_worker_failure_evidence():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00092_empty_evidence():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00092_merge_pending():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00092_retry_started_at():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00092_available_at_bound():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00092_available_at_exact():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00092_line_count():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00092_line1_level():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00092_line1_event():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00092_line1_attempt():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00092_line1_stage():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00092_line1_reason():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00092_line1_message():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00092_terminal_message():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00092_terminal_level():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00092_terminal_event():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00092_terminal_stage():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00092_terminal_reason():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00092_warning_present():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00092_warning_level():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00092_defer_lines():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00092_no_message_text():
    transcript, expected = _case(92)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00093_rets():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00093_dupe():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00093_dupe_state_stable():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00093_records_exact():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00093_state():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00093_attempt():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00093_failure():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00093_quarantine_reason():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00093_recovery_state():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00093_worker_failure():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00093_worker_failure_evidence():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00093_empty_evidence():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00093_merge_pending():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00093_retry_started_at():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00093_available_at_bound():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00093_available_at_exact():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00093_line_count():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00093_line1_level():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00093_line1_event():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00093_line1_attempt():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00093_line1_stage():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00093_line1_reason():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00093_line1_message():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00093_terminal_message():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00093_terminal_level():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00093_terminal_event():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00093_terminal_stage():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00093_terminal_reason():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00093_warning_present():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00093_warning_level():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00093_defer_lines():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00093_no_message_text():
    transcript, expected = _case(93)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00094_rets():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00094_dupe():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00094_dupe_state_stable():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00094_records_exact():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00094_state():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00094_attempt():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00094_failure():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00094_quarantine_reason():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00094_recovery_state():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00094_worker_failure():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00094_worker_failure_evidence():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00094_empty_evidence():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00094_merge_pending():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00094_retry_started_at():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00094_available_at_bound():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00094_available_at_exact():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00094_line_count():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00094_line1_level():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00094_line1_event():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00094_line1_attempt():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00094_line1_stage():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00094_line1_reason():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00094_line1_message():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00094_terminal_message():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00094_terminal_level():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00094_terminal_event():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00094_terminal_stage():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00094_terminal_reason():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00094_warning_present():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00094_warning_level():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00094_defer_lines():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00094_no_message_text():
    transcript, expected = _case(94)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00095_rets():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00095_dupe():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00095_dupe_state_stable():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00095_records_exact():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00095_state():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00095_attempt():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00095_failure():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00095_quarantine_reason():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00095_recovery_state():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00095_worker_failure():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00095_worker_failure_evidence():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00095_empty_evidence():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00095_merge_pending():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00095_retry_started_at():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00095_available_at_bound():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00095_available_at_exact():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00095_line_count():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00095_line1_level():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00095_line1_event():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00095_line1_attempt():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00095_line1_stage():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00095_line1_reason():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00095_line1_message():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00095_terminal_message():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00095_terminal_level():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00095_terminal_event():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00095_terminal_stage():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00095_terminal_reason():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00095_warning_present():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00095_warning_level():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00095_defer_lines():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00095_no_message_text():
    transcript, expected = _case(95)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00096_rets():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00096_dupe():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00096_dupe_state_stable():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00096_records_exact():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00096_state():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00096_attempt():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00096_failure():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00096_quarantine_reason():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00096_recovery_state():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00096_worker_failure():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00096_worker_failure_evidence():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00096_empty_evidence():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00096_merge_pending():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00096_retry_started_at():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00096_available_at_bound():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00096_available_at_exact():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00096_line_count():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00096_line1_level():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00096_line1_event():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00096_line1_attempt():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00096_line1_stage():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00096_line1_reason():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00096_line1_message():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00096_terminal_message():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00096_terminal_level():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00096_terminal_event():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00096_terminal_stage():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00096_terminal_reason():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00096_warning_present():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00096_warning_level():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00096_defer_lines():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00096_no_message_text():
    transcript, expected = _case(96)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00097_rets():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00097_dupe():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00097_dupe_state_stable():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00097_records_exact():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00097_state():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00097_attempt():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00097_failure():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00097_quarantine_reason():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00097_recovery_state():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00097_worker_failure():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00097_worker_failure_evidence():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00097_empty_evidence():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00097_merge_pending():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00097_retry_started_at():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00097_available_at_bound():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00097_available_at_exact():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00097_line_count():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00097_line1_level():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00097_line1_event():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00097_line1_attempt():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00097_line1_stage():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00097_line1_reason():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00097_line1_message():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00097_terminal_message():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00097_terminal_level():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00097_terminal_event():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00097_terminal_stage():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00097_terminal_reason():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00097_warning_present():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00097_warning_level():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00097_defer_lines():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00097_no_message_text():
    transcript, expected = _case(97)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00098_rets():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00098_dupe():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00098_dupe_state_stable():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00098_records_exact():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00098_state():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00098_attempt():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00098_failure():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00098_quarantine_reason():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00098_recovery_state():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00098_worker_failure():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00098_worker_failure_evidence():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00098_empty_evidence():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00098_merge_pending():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00098_retry_started_at():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00098_available_at_bound():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00098_available_at_exact():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00098_line_count():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00098_line1_level():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00098_line1_event():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00098_line1_attempt():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00098_line1_stage():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00098_line1_reason():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00098_line1_message():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00098_terminal_message():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00098_terminal_level():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00098_terminal_event():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00098_terminal_stage():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00098_terminal_reason():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00098_warning_present():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00098_warning_level():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00098_defer_lines():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00098_no_message_text():
    transcript, expected = _case(98)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00099_rets():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00099_dupe():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00099_dupe_state_stable():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00099_records_exact():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00099_state():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00099_attempt():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00099_failure():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00099_quarantine_reason():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00099_recovery_state():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00099_worker_failure():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00099_worker_failure_evidence():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00099_empty_evidence():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00099_merge_pending():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00099_retry_started_at():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00099_available_at_bound():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00099_available_at_exact():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00099_line_count():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00099_line1_level():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00099_line1_event():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00099_line1_attempt():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00099_line1_stage():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00099_line1_reason():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00099_line1_message():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00099_terminal_message():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00099_terminal_level():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00099_terminal_event():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00099_terminal_stage():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00099_terminal_reason():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00099_warning_present():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00099_warning_level():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00099_defer_lines():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00099_no_message_text():
    transcript, expected = _case(99)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00100_rets():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00100_dupe():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00100_dupe_state_stable():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00100_records_exact():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00100_state():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00100_attempt():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00100_failure():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00100_quarantine_reason():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00100_recovery_state():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00100_worker_failure():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00100_worker_failure_evidence():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00100_empty_evidence():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00100_merge_pending():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00100_retry_started_at():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00100_available_at_bound():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00100_available_at_exact():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00100_line_count():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00100_line1_level():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00100_line1_event():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00100_line1_attempt():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00100_line1_stage():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00100_line1_reason():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00100_line1_message():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00100_terminal_message():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00100_terminal_level():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00100_terminal_event():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00100_terminal_stage():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00100_terminal_reason():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00100_warning_present():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00100_warning_level():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00100_defer_lines():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00100_no_message_text():
    transcript, expected = _case(100)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00101_rets():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00101_dupe():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00101_dupe_state_stable():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00101_records_exact():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00101_state():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00101_attempt():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00101_failure():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00101_quarantine_reason():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00101_recovery_state():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00101_worker_failure():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00101_worker_failure_evidence():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00101_empty_evidence():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00101_merge_pending():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00101_retry_started_at():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00101_available_at_bound():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00101_available_at_exact():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00101_line_count():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00101_line1_level():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00101_line1_event():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00101_line1_attempt():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00101_line1_stage():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00101_line1_reason():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00101_line1_message():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00101_terminal_message():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00101_terminal_level():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00101_terminal_event():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00101_terminal_stage():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00101_terminal_reason():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00101_warning_present():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00101_warning_level():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00101_defer_lines():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00101_no_message_text():
    transcript, expected = _case(101)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00102_rets():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00102_dupe():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00102_dupe_state_stable():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00102_records_exact():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00102_state():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00102_attempt():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00102_failure():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00102_quarantine_reason():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00102_recovery_state():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00102_worker_failure():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00102_worker_failure_evidence():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00102_empty_evidence():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00102_merge_pending():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00102_retry_started_at():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00102_available_at_bound():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00102_available_at_exact():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00102_line_count():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00102_line1_level():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00102_line1_event():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00102_line1_attempt():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00102_line1_stage():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00102_line1_reason():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00102_line1_message():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00102_terminal_message():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00102_terminal_level():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00102_terminal_event():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00102_terminal_stage():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00102_terminal_reason():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00102_warning_present():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00102_warning_level():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00102_defer_lines():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00102_no_message_text():
    transcript, expected = _case(102)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00103_rets():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00103_dupe():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00103_dupe_state_stable():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00103_records_exact():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00103_state():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00103_attempt():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00103_failure():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00103_quarantine_reason():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00103_recovery_state():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00103_worker_failure():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00103_worker_failure_evidence():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00103_empty_evidence():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00103_merge_pending():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00103_retry_started_at():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00103_available_at_bound():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00103_available_at_exact():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00103_line_count():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00103_line1_level():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00103_line1_event():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00103_line1_attempt():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00103_line1_stage():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00103_line1_reason():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00103_line1_message():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00103_terminal_message():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00103_terminal_level():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00103_terminal_event():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00103_terminal_stage():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00103_terminal_reason():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00103_warning_present():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00103_warning_level():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00103_defer_lines():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00103_no_message_text():
    transcript, expected = _case(103)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00104_rets():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00104_dupe():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00104_dupe_state_stable():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00104_records_exact():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00104_state():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00104_attempt():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00104_failure():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00104_quarantine_reason():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00104_recovery_state():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00104_worker_failure():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00104_worker_failure_evidence():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00104_empty_evidence():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00104_merge_pending():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00104_retry_started_at():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00104_available_at_bound():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00104_available_at_exact():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00104_line_count():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00104_line1_level():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00104_line1_event():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00104_line1_attempt():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00104_line1_stage():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00104_line1_reason():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00104_line1_message():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00104_terminal_message():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00104_terminal_level():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00104_terminal_event():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00104_terminal_stage():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00104_terminal_reason():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00104_warning_present():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00104_warning_level():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00104_defer_lines():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00104_no_message_text():
    transcript, expected = _case(104)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w11w_00105_rets():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w11w_00105_dupe():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w11w_00105_dupe_state_stable():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w11w_00105_records_exact():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w11w_00105_state():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'state')


def test_b09_w11w_00105_attempt():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w11w_00105_failure():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w11w_00105_quarantine_reason():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w11w_00105_recovery_state():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w11w_00105_worker_failure():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w11w_00105_worker_failure_evidence():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w11w_00105_empty_evidence():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w11w_00105_merge_pending():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w11w_00105_retry_started_at():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w11w_00105_available_at_bound():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w11w_00105_available_at_exact():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w11w_00105_line_count():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w11w_00105_line1_level():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w11w_00105_line1_event():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w11w_00105_line1_attempt():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w11w_00105_line1_stage():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w11w_00105_line1_reason():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w11w_00105_line1_message():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w11w_00105_terminal_message():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w11w_00105_terminal_level():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w11w_00105_terminal_event():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w11w_00105_terminal_stage():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w11w_00105_terminal_reason():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w11w_00105_warning_present():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w11w_00105_warning_level():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w11w_00105_defer_lines():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w11w_00105_no_message_text():
    transcript, expected = _case(105)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00106_rets():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00106_dupe():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00106_dupe_state_stable():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00106_records_exact():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00106_state():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00106_attempt():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00106_failure():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00106_quarantine_reason():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00106_recovery_state():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00106_worker_failure():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00106_worker_failure_evidence():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00106_empty_evidence():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00106_merge_pending():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00106_retry_started_at():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00106_available_at_bound():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00106_available_at_exact():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00106_line_count():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00106_line1_level():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00106_line1_event():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00106_line1_attempt():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00106_line1_stage():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00106_line1_reason():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00106_line1_message():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00106_terminal_message():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00106_terminal_level():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00106_terminal_event():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00106_terminal_stage():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00106_terminal_reason():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00106_warning_present():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00106_warning_level():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00106_defer_lines():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00106_no_message_text():
    transcript, expected = _case(106)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00107_rets():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00107_dupe():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00107_dupe_state_stable():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00107_records_exact():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00107_state():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00107_attempt():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00107_failure():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00107_quarantine_reason():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00107_recovery_state():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00107_worker_failure():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00107_worker_failure_evidence():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00107_empty_evidence():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00107_merge_pending():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00107_retry_started_at():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00107_available_at_bound():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00107_available_at_exact():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00107_line_count():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00107_line1_level():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00107_line1_event():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00107_line1_attempt():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00107_line1_stage():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00107_line1_reason():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00107_line1_message():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00107_terminal_message():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00107_terminal_level():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00107_terminal_event():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00107_terminal_stage():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00107_terminal_reason():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00107_warning_present():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00107_warning_level():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00107_defer_lines():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00107_no_message_text():
    transcript, expected = _case(107)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00108_rets():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00108_dupe():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00108_dupe_state_stable():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00108_records_exact():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00108_state():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00108_attempt():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00108_failure():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00108_quarantine_reason():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00108_recovery_state():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00108_worker_failure():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00108_worker_failure_evidence():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00108_empty_evidence():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00108_merge_pending():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00108_retry_started_at():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00108_available_at_bound():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00108_available_at_exact():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00108_line_count():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00108_line1_level():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00108_line1_event():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00108_line1_attempt():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00108_line1_stage():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00108_line1_reason():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00108_line1_message():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00108_terminal_message():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00108_terminal_level():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00108_terminal_event():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00108_terminal_stage():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00108_terminal_reason():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00108_warning_present():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00108_warning_level():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00108_defer_lines():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00108_no_message_text():
    transcript, expected = _case(108)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00109_rets():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00109_dupe():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00109_dupe_state_stable():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00109_records_exact():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00109_state():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00109_attempt():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00109_failure():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00109_quarantine_reason():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00109_recovery_state():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00109_worker_failure():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00109_worker_failure_evidence():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00109_empty_evidence():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00109_merge_pending():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00109_retry_started_at():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00109_available_at_bound():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00109_available_at_exact():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00109_line_count():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00109_line1_level():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00109_line1_event():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00109_line1_attempt():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00109_line1_stage():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00109_line1_reason():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00109_line1_message():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00109_terminal_message():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00109_terminal_level():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00109_terminal_event():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00109_terminal_stage():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00109_terminal_reason():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00109_warning_present():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00109_warning_level():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00109_defer_lines():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00109_no_message_text():
    transcript, expected = _case(109)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00110_rets():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00110_dupe():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00110_dupe_state_stable():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00110_records_exact():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00110_state():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00110_attempt():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00110_failure():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00110_quarantine_reason():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00110_recovery_state():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00110_worker_failure():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00110_worker_failure_evidence():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00110_empty_evidence():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00110_merge_pending():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00110_retry_started_at():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00110_available_at_bound():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00110_available_at_exact():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00110_line_count():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00110_line1_level():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00110_line1_event():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00110_line1_attempt():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00110_line1_stage():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00110_line1_reason():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00110_line1_message():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00110_terminal_message():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00110_terminal_level():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00110_terminal_event():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00110_terminal_stage():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00110_terminal_reason():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00110_warning_present():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00110_warning_level():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00110_defer_lines():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00110_no_message_text():
    transcript, expected = _case(110)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00111_rets():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00111_dupe():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00111_dupe_state_stable():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00111_records_exact():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00111_state():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00111_attempt():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00111_failure():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00111_quarantine_reason():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00111_recovery_state():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00111_worker_failure():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00111_worker_failure_evidence():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00111_empty_evidence():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00111_merge_pending():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00111_retry_started_at():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00111_available_at_bound():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00111_available_at_exact():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00111_line_count():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00111_line1_level():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00111_line1_event():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00111_line1_attempt():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00111_line1_stage():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00111_line1_reason():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00111_line1_message():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00111_terminal_message():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00111_terminal_level():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00111_terminal_event():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00111_terminal_stage():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00111_terminal_reason():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00111_warning_present():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00111_warning_level():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00111_defer_lines():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00111_no_message_text():
    transcript, expected = _case(111)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00112_rets():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00112_dupe():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00112_dupe_state_stable():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00112_records_exact():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00112_state():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00112_attempt():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00112_failure():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00112_quarantine_reason():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00112_recovery_state():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00112_worker_failure():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00112_worker_failure_evidence():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00112_empty_evidence():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00112_merge_pending():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00112_retry_started_at():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00112_available_at_bound():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00112_available_at_exact():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00112_line_count():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00112_line1_level():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00112_line1_event():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00112_line1_attempt():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00112_line1_stage():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00112_line1_reason():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00112_line1_message():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00112_terminal_message():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00112_terminal_level():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00112_terminal_event():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00112_terminal_stage():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00112_terminal_reason():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00112_warning_present():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00112_warning_level():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00112_defer_lines():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00112_no_message_text():
    transcript, expected = _case(112)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00113_rets():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00113_dupe():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00113_dupe_state_stable():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00113_records_exact():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00113_state():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00113_attempt():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00113_failure():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00113_quarantine_reason():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00113_recovery_state():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00113_worker_failure():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00113_worker_failure_evidence():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00113_empty_evidence():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00113_merge_pending():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00113_retry_started_at():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00113_available_at_bound():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00113_available_at_exact():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00113_line_count():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00113_line1_level():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00113_line1_event():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00113_line1_attempt():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00113_line1_stage():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00113_line1_reason():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00113_line1_message():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00113_terminal_message():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00113_terminal_level():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00113_terminal_event():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00113_terminal_stage():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00113_terminal_reason():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00113_warning_present():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00113_warning_level():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00113_defer_lines():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00113_no_message_text():
    transcript, expected = _case(113)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00114_rets():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00114_dupe():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00114_dupe_state_stable():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00114_records_exact():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00114_state():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00114_attempt():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00114_failure():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00114_quarantine_reason():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00114_recovery_state():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00114_worker_failure():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00114_worker_failure_evidence():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00114_empty_evidence():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00114_merge_pending():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00114_retry_started_at():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00114_available_at_bound():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00114_available_at_exact():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00114_line_count():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00114_line1_level():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00114_line1_event():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00114_line1_attempt():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00114_line1_stage():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00114_line1_reason():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00114_line1_message():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00114_terminal_message():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00114_terminal_level():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00114_terminal_event():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00114_terminal_stage():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00114_terminal_reason():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00114_warning_present():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00114_warning_level():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00114_defer_lines():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00114_no_message_text():
    transcript, expected = _case(114)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00115_rets():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00115_dupe():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00115_dupe_state_stable():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00115_records_exact():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00115_state():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00115_attempt():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00115_failure():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00115_quarantine_reason():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00115_recovery_state():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00115_worker_failure():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00115_worker_failure_evidence():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00115_empty_evidence():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00115_merge_pending():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00115_retry_started_at():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00115_available_at_bound():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00115_available_at_exact():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00115_line_count():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00115_line1_level():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00115_line1_event():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00115_line1_attempt():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00115_line1_stage():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00115_line1_reason():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00115_line1_message():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00115_terminal_message():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00115_terminal_level():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00115_terminal_event():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00115_terminal_stage():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00115_terminal_reason():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00115_warning_present():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00115_warning_level():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00115_defer_lines():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00115_no_message_text():
    transcript, expected = _case(115)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00116_rets():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00116_dupe():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00116_dupe_state_stable():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00116_records_exact():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00116_state():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00116_attempt():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00116_failure():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00116_quarantine_reason():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00116_recovery_state():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00116_worker_failure():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00116_worker_failure_evidence():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00116_empty_evidence():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00116_merge_pending():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00116_retry_started_at():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00116_available_at_bound():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00116_available_at_exact():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00116_line_count():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00116_line1_level():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00116_line1_event():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00116_line1_attempt():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00116_line1_stage():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00116_line1_reason():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00116_line1_message():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00116_terminal_message():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00116_terminal_level():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00116_terminal_event():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00116_terminal_stage():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00116_terminal_reason():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00116_warning_present():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00116_warning_level():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00116_defer_lines():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00116_no_message_text():
    transcript, expected = _case(116)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00117_rets():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00117_dupe():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00117_dupe_state_stable():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00117_records_exact():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00117_state():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00117_attempt():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00117_failure():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00117_quarantine_reason():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00117_recovery_state():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00117_worker_failure():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00117_worker_failure_evidence():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00117_empty_evidence():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00117_merge_pending():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00117_retry_started_at():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00117_available_at_bound():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00117_available_at_exact():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00117_line_count():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00117_line1_level():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00117_line1_event():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00117_line1_attempt():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00117_line1_stage():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00117_line1_reason():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00117_line1_message():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00117_terminal_message():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00117_terminal_level():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00117_terminal_event():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00117_terminal_stage():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00117_terminal_reason():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00117_warning_present():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00117_warning_level():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00117_defer_lines():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00117_no_message_text():
    transcript, expected = _case(117)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00118_rets():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00118_dupe():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00118_dupe_state_stable():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00118_records_exact():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00118_state():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00118_attempt():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00118_failure():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00118_quarantine_reason():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00118_recovery_state():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00118_worker_failure():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00118_worker_failure_evidence():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00118_empty_evidence():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00118_merge_pending():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00118_retry_started_at():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00118_available_at_bound():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00118_available_at_exact():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00118_line_count():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00118_line1_level():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00118_line1_event():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00118_line1_attempt():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00118_line1_stage():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00118_line1_reason():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00118_line1_message():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00118_terminal_message():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00118_terminal_level():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00118_terminal_event():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00118_terminal_stage():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00118_terminal_reason():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00118_warning_present():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00118_warning_level():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00118_defer_lines():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00118_no_message_text():
    transcript, expected = _case(118)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00119_rets():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00119_dupe():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00119_dupe_state_stable():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00119_records_exact():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00119_state():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00119_attempt():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00119_failure():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00119_quarantine_reason():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00119_recovery_state():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00119_worker_failure():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00119_worker_failure_evidence():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00119_empty_evidence():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00119_merge_pending():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00119_retry_started_at():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00119_available_at_bound():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00119_available_at_exact():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00119_line_count():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00119_line1_level():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00119_line1_event():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00119_line1_attempt():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00119_line1_stage():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00119_line1_reason():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00119_line1_message():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00119_terminal_message():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00119_terminal_level():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00119_terminal_event():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00119_terminal_stage():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00119_terminal_reason():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00119_warning_present():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00119_warning_level():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00119_defer_lines():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00119_no_message_text():
    transcript, expected = _case(119)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00120_rets():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00120_dupe():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00120_dupe_state_stable():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00120_records_exact():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00120_state():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00120_attempt():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00120_failure():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00120_quarantine_reason():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00120_recovery_state():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00120_worker_failure():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00120_worker_failure_evidence():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00120_empty_evidence():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00120_merge_pending():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00120_retry_started_at():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00120_available_at_bound():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00120_available_at_exact():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00120_line_count():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00120_line1_level():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00120_line1_event():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00120_line1_attempt():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00120_line1_stage():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00120_line1_reason():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00120_line1_message():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00120_terminal_message():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00120_terminal_level():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00120_terminal_event():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00120_terminal_stage():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00120_terminal_reason():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00120_warning_present():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00120_warning_level():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00120_defer_lines():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00120_no_message_text():
    transcript, expected = _case(120)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00121_rets():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00121_dupe():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00121_dupe_state_stable():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00121_records_exact():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00121_state():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00121_attempt():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00121_failure():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00121_quarantine_reason():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00121_recovery_state():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00121_worker_failure():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00121_worker_failure_evidence():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00121_empty_evidence():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00121_merge_pending():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00121_retry_started_at():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00121_available_at_bound():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00121_available_at_exact():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00121_line_count():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00121_line1_level():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00121_line1_event():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00121_line1_attempt():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00121_line1_stage():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00121_line1_reason():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00121_line1_message():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00121_terminal_message():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00121_terminal_level():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00121_terminal_event():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00121_terminal_stage():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00121_terminal_reason():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00121_warning_present():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00121_warning_level():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00121_defer_lines():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00121_no_message_text():
    transcript, expected = _case(121)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00122_rets():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00122_dupe():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00122_dupe_state_stable():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00122_records_exact():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00122_state():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00122_attempt():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00122_failure():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00122_quarantine_reason():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00122_recovery_state():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00122_worker_failure():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00122_worker_failure_evidence():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00122_empty_evidence():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00122_merge_pending():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00122_retry_started_at():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00122_available_at_bound():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00122_available_at_exact():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00122_line_count():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00122_line1_level():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00122_line1_event():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00122_line1_attempt():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00122_line1_stage():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00122_line1_reason():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00122_line1_message():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00122_terminal_message():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00122_terminal_level():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00122_terminal_event():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00122_terminal_stage():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00122_terminal_reason():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00122_warning_present():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00122_warning_level():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00122_defer_lines():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00122_no_message_text():
    transcript, expected = _case(122)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00123_rets():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00123_dupe():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00123_dupe_state_stable():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00123_records_exact():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00123_state():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00123_attempt():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00123_failure():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00123_quarantine_reason():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00123_recovery_state():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00123_worker_failure():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00123_worker_failure_evidence():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00123_empty_evidence():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00123_merge_pending():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00123_retry_started_at():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00123_available_at_bound():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00123_available_at_exact():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00123_line_count():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00123_line1_level():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00123_line1_event():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00123_line1_attempt():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00123_line1_stage():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00123_line1_reason():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00123_line1_message():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00123_terminal_message():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00123_terminal_level():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00123_terminal_event():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00123_terminal_stage():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00123_terminal_reason():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00123_warning_present():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00123_warning_level():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00123_defer_lines():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00123_no_message_text():
    transcript, expected = _case(123)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00124_rets():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00124_dupe():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00124_dupe_state_stable():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00124_records_exact():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00124_state():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00124_attempt():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00124_failure():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00124_quarantine_reason():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00124_recovery_state():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00124_worker_failure():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00124_worker_failure_evidence():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00124_empty_evidence():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00124_merge_pending():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00124_retry_started_at():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00124_available_at_bound():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00124_available_at_exact():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00124_line_count():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00124_line1_level():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00124_line1_event():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00124_line1_attempt():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00124_line1_stage():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00124_line1_reason():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00124_line1_message():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00124_terminal_message():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00124_terminal_level():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00124_terminal_event():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00124_terminal_stage():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00124_terminal_reason():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00124_warning_present():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00124_warning_level():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00124_defer_lines():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00124_no_message_text():
    transcript, expected = _case(124)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00125_rets():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00125_dupe():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00125_dupe_state_stable():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00125_records_exact():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00125_state():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00125_attempt():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00125_failure():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00125_quarantine_reason():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00125_recovery_state():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00125_worker_failure():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00125_worker_failure_evidence():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00125_empty_evidence():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00125_merge_pending():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00125_retry_started_at():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00125_available_at_bound():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00125_available_at_exact():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00125_line_count():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00125_line1_level():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00125_line1_event():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00125_line1_attempt():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00125_line1_stage():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00125_line1_reason():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00125_line1_message():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00125_terminal_message():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00125_terminal_level():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00125_terminal_event():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00125_terminal_stage():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00125_terminal_reason():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00125_warning_present():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00125_warning_level():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00125_defer_lines():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00125_no_message_text():
    transcript, expected = _case(125)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w01w_00126_rets():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w01w_00126_dupe():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w01w_00126_dupe_state_stable():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w01w_00126_records_exact():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w01w_00126_state():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'state')


def test_b09_w01w_00126_attempt():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w01w_00126_failure():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w01w_00126_quarantine_reason():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w01w_00126_recovery_state():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w01w_00126_worker_failure():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w01w_00126_worker_failure_evidence():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w01w_00126_empty_evidence():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w01w_00126_merge_pending():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w01w_00126_retry_started_at():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w01w_00126_available_at_bound():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w01w_00126_available_at_exact():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w01w_00126_line_count():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w01w_00126_line1_level():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w01w_00126_line1_event():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w01w_00126_line1_attempt():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w01w_00126_line1_stage():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w01w_00126_line1_reason():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w01w_00126_line1_message():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w01w_00126_terminal_message():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w01w_00126_terminal_level():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w01w_00126_terminal_event():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w01w_00126_terminal_stage():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w01w_00126_terminal_reason():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w01w_00126_warning_present():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w01w_00126_warning_level():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w01w_00126_defer_lines():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w01w_00126_no_message_text():
    transcript, expected = _case(126)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00127_rets():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00127_dupe():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00127_dupe_state_stable():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00127_records_exact():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00127_state():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00127_attempt():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00127_failure():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00127_quarantine_reason():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00127_recovery_state():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00127_worker_failure():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00127_worker_failure_evidence():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00127_empty_evidence():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00127_merge_pending():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00127_retry_started_at():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00127_available_at_bound():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00127_available_at_exact():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00127_line_count():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00127_line1_level():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00127_line1_event():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00127_line1_attempt():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00127_line1_stage():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00127_line1_reason():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00127_line1_message():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00127_terminal_message():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00127_terminal_level():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00127_terminal_event():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00127_terminal_stage():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00127_terminal_reason():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00127_warning_present():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00127_warning_level():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00127_defer_lines():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00127_no_message_text():
    transcript, expected = _case(127)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00128_rets():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00128_dupe():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00128_dupe_state_stable():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00128_records_exact():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00128_state():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00128_attempt():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00128_failure():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00128_quarantine_reason():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00128_recovery_state():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00128_worker_failure():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00128_worker_failure_evidence():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00128_empty_evidence():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00128_merge_pending():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00128_retry_started_at():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00128_available_at_bound():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00128_available_at_exact():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00128_line_count():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00128_line1_level():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00128_line1_event():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00128_line1_attempt():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00128_line1_stage():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00128_line1_reason():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00128_line1_message():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00128_terminal_message():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00128_terminal_level():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00128_terminal_event():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00128_terminal_stage():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00128_terminal_reason():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00128_warning_present():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00128_warning_level():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00128_defer_lines():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00128_no_message_text():
    transcript, expected = _case(128)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00129_rets():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00129_dupe():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00129_dupe_state_stable():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00129_records_exact():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00129_state():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00129_attempt():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00129_failure():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00129_quarantine_reason():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00129_recovery_state():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00129_worker_failure():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00129_worker_failure_evidence():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00129_empty_evidence():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00129_merge_pending():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00129_retry_started_at():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00129_available_at_bound():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00129_available_at_exact():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00129_line_count():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00129_line1_level():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00129_line1_event():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00129_line1_attempt():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00129_line1_stage():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00129_line1_reason():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00129_line1_message():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00129_terminal_message():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00129_terminal_level():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00129_terminal_event():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00129_terminal_stage():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00129_terminal_reason():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00129_warning_present():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00129_warning_level():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00129_defer_lines():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00129_no_message_text():
    transcript, expected = _case(129)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00130_rets():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00130_dupe():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00130_dupe_state_stable():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00130_records_exact():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00130_state():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00130_attempt():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00130_failure():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00130_quarantine_reason():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00130_recovery_state():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00130_worker_failure():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00130_worker_failure_evidence():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00130_empty_evidence():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00130_merge_pending():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00130_retry_started_at():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00130_available_at_bound():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00130_available_at_exact():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00130_line_count():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00130_line1_level():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00130_line1_event():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00130_line1_attempt():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00130_line1_stage():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00130_line1_reason():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00130_line1_message():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00130_terminal_message():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00130_terminal_level():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00130_terminal_event():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00130_terminal_stage():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00130_terminal_reason():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00130_warning_present():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00130_warning_level():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00130_defer_lines():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00130_no_message_text():
    transcript, expected = _case(130)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00131_rets():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00131_dupe():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00131_dupe_state_stable():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00131_records_exact():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00131_state():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00131_attempt():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00131_failure():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00131_quarantine_reason():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00131_recovery_state():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00131_worker_failure():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00131_worker_failure_evidence():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00131_empty_evidence():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00131_merge_pending():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00131_retry_started_at():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00131_available_at_bound():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00131_available_at_exact():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00131_line_count():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00131_line1_level():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00131_line1_event():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00131_line1_attempt():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00131_line1_stage():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00131_line1_reason():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00131_line1_message():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00131_terminal_message():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00131_terminal_level():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00131_terminal_event():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00131_terminal_stage():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00131_terminal_reason():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00131_warning_present():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00131_warning_level():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00131_defer_lines():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00131_no_message_text():
    transcript, expected = _case(131)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00132_rets():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00132_dupe():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00132_dupe_state_stable():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00132_records_exact():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00132_state():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00132_attempt():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00132_failure():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00132_quarantine_reason():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00132_recovery_state():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00132_worker_failure():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00132_worker_failure_evidence():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00132_empty_evidence():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00132_merge_pending():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00132_retry_started_at():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00132_available_at_bound():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00132_available_at_exact():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00132_line_count():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00132_line1_level():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00132_line1_event():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00132_line1_attempt():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00132_line1_stage():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00132_line1_reason():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00132_line1_message():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00132_terminal_message():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00132_terminal_level():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00132_terminal_event():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00132_terminal_stage():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00132_terminal_reason():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00132_warning_present():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00132_warning_level():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00132_defer_lines():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00132_no_message_text():
    transcript, expected = _case(132)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00133_rets():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00133_dupe():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00133_dupe_state_stable():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00133_records_exact():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00133_state():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00133_attempt():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00133_failure():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00133_quarantine_reason():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00133_recovery_state():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00133_worker_failure():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00133_worker_failure_evidence():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00133_empty_evidence():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00133_merge_pending():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00133_retry_started_at():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00133_available_at_bound():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00133_available_at_exact():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00133_line_count():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00133_line1_level():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00133_line1_event():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00133_line1_attempt():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00133_line1_stage():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00133_line1_reason():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00133_line1_message():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00133_terminal_message():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00133_terminal_level():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00133_terminal_event():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00133_terminal_stage():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00133_terminal_reason():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00133_warning_present():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00133_warning_level():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00133_defer_lines():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00133_no_message_text():
    transcript, expected = _case(133)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00134_rets():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00134_dupe():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00134_dupe_state_stable():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00134_records_exact():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00134_state():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00134_attempt():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00134_failure():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00134_quarantine_reason():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00134_recovery_state():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00134_worker_failure():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00134_worker_failure_evidence():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00134_empty_evidence():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00134_merge_pending():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00134_retry_started_at():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00134_available_at_bound():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00134_available_at_exact():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00134_line_count():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00134_line1_level():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00134_line1_event():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00134_line1_attempt():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00134_line1_stage():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00134_line1_reason():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00134_line1_message():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00134_terminal_message():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00134_terminal_level():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00134_terminal_event():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00134_terminal_stage():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00134_terminal_reason():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00134_warning_present():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00134_warning_level():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00134_defer_lines():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00134_no_message_text():
    transcript, expected = _case(134)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00135_rets():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00135_dupe():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00135_dupe_state_stable():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00135_records_exact():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00135_state():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00135_attempt():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00135_failure():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00135_quarantine_reason():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00135_recovery_state():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00135_worker_failure():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00135_worker_failure_evidence():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00135_empty_evidence():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00135_merge_pending():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00135_retry_started_at():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00135_available_at_bound():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00135_available_at_exact():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00135_line_count():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00135_line1_level():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00135_line1_event():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00135_line1_attempt():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00135_line1_stage():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00135_line1_reason():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00135_line1_message():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00135_terminal_message():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00135_terminal_level():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00135_terminal_event():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00135_terminal_stage():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00135_terminal_reason():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00135_warning_present():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00135_warning_level():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00135_defer_lines():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00135_no_message_text():
    transcript, expected = _case(135)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00136_rets():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00136_dupe():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00136_dupe_state_stable():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00136_records_exact():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00136_state():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00136_attempt():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00136_failure():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00136_quarantine_reason():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00136_recovery_state():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00136_worker_failure():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00136_worker_failure_evidence():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00136_empty_evidence():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00136_merge_pending():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00136_retry_started_at():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00136_available_at_bound():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00136_available_at_exact():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00136_line_count():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00136_line1_level():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00136_line1_event():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00136_line1_attempt():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00136_line1_stage():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00136_line1_reason():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00136_line1_message():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00136_terminal_message():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00136_terminal_level():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00136_terminal_event():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00136_terminal_stage():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00136_terminal_reason():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00136_warning_present():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00136_warning_level():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00136_defer_lines():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00136_no_message_text():
    transcript, expected = _case(136)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00137_rets():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00137_dupe():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00137_dupe_state_stable():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00137_records_exact():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00137_state():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00137_attempt():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00137_failure():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00137_quarantine_reason():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00137_recovery_state():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00137_worker_failure():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00137_worker_failure_evidence():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00137_empty_evidence():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00137_merge_pending():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00137_retry_started_at():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00137_available_at_bound():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00137_available_at_exact():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00137_line_count():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00137_line1_level():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00137_line1_event():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00137_line1_attempt():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00137_line1_stage():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00137_line1_reason():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00137_line1_message():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00137_terminal_message():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00137_terminal_level():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00137_terminal_event():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00137_terminal_stage():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00137_terminal_reason():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00137_warning_present():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00137_warning_level():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00137_defer_lines():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00137_no_message_text():
    transcript, expected = _case(137)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00138_rets():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00138_dupe():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00138_dupe_state_stable():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00138_records_exact():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00138_state():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00138_attempt():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00138_failure():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00138_quarantine_reason():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00138_recovery_state():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00138_worker_failure():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00138_worker_failure_evidence():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00138_empty_evidence():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00138_merge_pending():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00138_retry_started_at():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00138_available_at_bound():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00138_available_at_exact():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00138_line_count():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00138_line1_level():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00138_line1_event():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00138_line1_attempt():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00138_line1_stage():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00138_line1_reason():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00138_line1_message():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00138_terminal_message():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00138_terminal_level():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00138_terminal_event():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00138_terminal_stage():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00138_terminal_reason():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00138_warning_present():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00138_warning_level():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00138_defer_lines():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00138_no_message_text():
    transcript, expected = _case(138)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00139_rets():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00139_dupe():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00139_dupe_state_stable():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00139_records_exact():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00139_state():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00139_attempt():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00139_failure():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00139_quarantine_reason():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00139_recovery_state():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00139_worker_failure():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00139_worker_failure_evidence():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00139_empty_evidence():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00139_merge_pending():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00139_retry_started_at():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00139_available_at_bound():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00139_available_at_exact():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00139_line_count():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00139_line1_level():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00139_line1_event():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00139_line1_attempt():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00139_line1_stage():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00139_line1_reason():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00139_line1_message():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00139_terminal_message():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00139_terminal_level():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00139_terminal_event():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00139_terminal_stage():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00139_terminal_reason():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00139_warning_present():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00139_warning_level():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00139_defer_lines():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00139_no_message_text():
    transcript, expected = _case(139)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00140_rets():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00140_dupe():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00140_dupe_state_stable():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00140_records_exact():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00140_state():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00140_attempt():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00140_failure():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00140_quarantine_reason():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00140_recovery_state():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00140_worker_failure():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00140_worker_failure_evidence():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00140_empty_evidence():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00140_merge_pending():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00140_retry_started_at():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00140_available_at_bound():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00140_available_at_exact():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00140_line_count():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00140_line1_level():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00140_line1_event():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00140_line1_attempt():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00140_line1_stage():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00140_line1_reason():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00140_line1_message():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00140_terminal_message():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00140_terminal_level():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00140_terminal_event():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00140_terminal_stage():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00140_terminal_reason():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00140_warning_present():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00140_warning_level():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00140_defer_lines():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00140_no_message_text():
    transcript, expected = _case(140)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00141_rets():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00141_dupe():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00141_dupe_state_stable():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00141_records_exact():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00141_state():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00141_attempt():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00141_failure():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00141_quarantine_reason():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00141_recovery_state():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00141_worker_failure():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00141_worker_failure_evidence():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00141_empty_evidence():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00141_merge_pending():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00141_retry_started_at():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00141_available_at_bound():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00141_available_at_exact():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00141_line_count():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00141_line1_level():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00141_line1_event():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00141_line1_attempt():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00141_line1_stage():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00141_line1_reason():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00141_line1_message():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00141_terminal_message():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00141_terminal_level():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00141_terminal_event():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00141_terminal_stage():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00141_terminal_reason():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00141_warning_present():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00141_warning_level():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00141_defer_lines():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00141_no_message_text():
    transcript, expected = _case(141)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00142_rets():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00142_dupe():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00142_dupe_state_stable():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00142_records_exact():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00142_state():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00142_attempt():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00142_failure():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00142_quarantine_reason():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00142_recovery_state():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00142_worker_failure():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00142_worker_failure_evidence():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00142_empty_evidence():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00142_merge_pending():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00142_retry_started_at():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00142_available_at_bound():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00142_available_at_exact():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00142_line_count():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00142_line1_level():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00142_line1_event():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00142_line1_attempt():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00142_line1_stage():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00142_line1_reason():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00142_line1_message():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00142_terminal_message():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00142_terminal_level():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00142_terminal_event():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00142_terminal_stage():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00142_terminal_reason():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00142_warning_present():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00142_warning_level():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00142_defer_lines():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00142_no_message_text():
    transcript, expected = _case(142)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00143_rets():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00143_dupe():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00143_dupe_state_stable():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00143_records_exact():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00143_state():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00143_attempt():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00143_failure():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00143_quarantine_reason():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00143_recovery_state():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00143_worker_failure():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00143_worker_failure_evidence():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00143_empty_evidence():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00143_merge_pending():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00143_retry_started_at():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00143_available_at_bound():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00143_available_at_exact():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00143_line_count():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00143_line1_level():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00143_line1_event():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00143_line1_attempt():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00143_line1_stage():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00143_line1_reason():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00143_line1_message():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00143_terminal_message():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00143_terminal_level():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00143_terminal_event():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00143_terminal_stage():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00143_terminal_reason():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00143_warning_present():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00143_warning_level():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00143_defer_lines():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00143_no_message_text():
    transcript, expected = _case(143)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00144_rets():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00144_dupe():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00144_dupe_state_stable():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00144_records_exact():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00144_state():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00144_attempt():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00144_failure():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00144_quarantine_reason():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00144_recovery_state():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00144_worker_failure():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00144_worker_failure_evidence():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00144_empty_evidence():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00144_merge_pending():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00144_retry_started_at():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00144_available_at_bound():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00144_available_at_exact():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00144_line_count():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00144_line1_level():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00144_line1_event():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00144_line1_attempt():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00144_line1_stage():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00144_line1_reason():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00144_line1_message():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00144_terminal_message():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00144_terminal_level():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00144_terminal_event():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00144_terminal_stage():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00144_terminal_reason():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00144_warning_present():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00144_warning_level():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00144_defer_lines():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00144_no_message_text():
    transcript, expected = _case(144)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00145_rets():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00145_dupe():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00145_dupe_state_stable():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00145_records_exact():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00145_state():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00145_attempt():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00145_failure():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00145_quarantine_reason():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00145_recovery_state():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00145_worker_failure():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00145_worker_failure_evidence():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00145_empty_evidence():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00145_merge_pending():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00145_retry_started_at():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00145_available_at_bound():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00145_available_at_exact():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00145_line_count():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00145_line1_level():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00145_line1_event():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00145_line1_attempt():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00145_line1_stage():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00145_line1_reason():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00145_line1_message():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00145_terminal_message():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00145_terminal_level():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00145_terminal_event():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00145_terminal_stage():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00145_terminal_reason():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00145_warning_present():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00145_warning_level():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00145_defer_lines():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00145_no_message_text():
    transcript, expected = _case(145)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w05w_00146_rets():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w05w_00146_dupe():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w05w_00146_dupe_state_stable():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w05w_00146_records_exact():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w05w_00146_state():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'state')


def test_b09_w05w_00146_attempt():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w05w_00146_failure():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w05w_00146_quarantine_reason():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w05w_00146_recovery_state():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w05w_00146_worker_failure():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w05w_00146_worker_failure_evidence():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w05w_00146_empty_evidence():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w05w_00146_merge_pending():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w05w_00146_retry_started_at():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w05w_00146_available_at_bound():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w05w_00146_available_at_exact():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w05w_00146_line_count():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w05w_00146_line1_level():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w05w_00146_line1_event():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w05w_00146_line1_attempt():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w05w_00146_line1_stage():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w05w_00146_line1_reason():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w05w_00146_line1_message():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w05w_00146_terminal_message():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w05w_00146_terminal_level():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w05w_00146_terminal_event():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w05w_00146_terminal_stage():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w05w_00146_terminal_reason():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w05w_00146_warning_present():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w05w_00146_warning_level():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w05w_00146_defer_lines():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w05w_00146_no_message_text():
    transcript, expected = _case(146)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w11w_00147_rets():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w11w_00147_dupe():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w11w_00147_dupe_state_stable():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w11w_00147_records_exact():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w11w_00147_state():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'state')


def test_b09_w11w_00147_attempt():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w11w_00147_failure():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w11w_00147_quarantine_reason():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w11w_00147_recovery_state():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w11w_00147_worker_failure():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w11w_00147_worker_failure_evidence():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w11w_00147_empty_evidence():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w11w_00147_merge_pending():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w11w_00147_retry_started_at():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w11w_00147_available_at_bound():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w11w_00147_available_at_exact():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w11w_00147_line_count():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w11w_00147_line1_level():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w11w_00147_line1_event():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w11w_00147_line1_attempt():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w11w_00147_line1_stage():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w11w_00147_line1_reason():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w11w_00147_line1_message():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w11w_00147_terminal_message():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w11w_00147_terminal_level():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w11w_00147_terminal_event():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w11w_00147_terminal_stage():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w11w_00147_terminal_reason():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w11w_00147_warning_present():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w11w_00147_warning_level():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w11w_00147_defer_lines():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w11w_00147_no_message_text():
    transcript, expected = _case(147)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00148_rets():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00148_dupe():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00148_dupe_state_stable():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00148_records_exact():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00148_state():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00148_attempt():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00148_failure():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00148_quarantine_reason():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00148_recovery_state():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00148_worker_failure():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00148_worker_failure_evidence():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00148_empty_evidence():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00148_merge_pending():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00148_retry_started_at():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00148_available_at_bound():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00148_available_at_exact():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00148_line_count():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00148_line1_level():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00148_line1_event():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00148_line1_attempt():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00148_line1_stage():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00148_line1_reason():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00148_line1_message():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00148_terminal_message():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00148_terminal_level():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00148_terminal_event():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00148_terminal_stage():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00148_terminal_reason():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00148_warning_present():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00148_warning_level():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00148_defer_lines():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00148_no_message_text():
    transcript, expected = _case(148)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00149_rets():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00149_dupe():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00149_dupe_state_stable():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00149_records_exact():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00149_state():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00149_attempt():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00149_failure():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00149_quarantine_reason():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00149_recovery_state():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00149_worker_failure():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00149_worker_failure_evidence():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00149_empty_evidence():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00149_merge_pending():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00149_retry_started_at():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00149_available_at_bound():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00149_available_at_exact():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00149_line_count():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00149_line1_level():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00149_line1_event():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00149_line1_attempt():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00149_line1_stage():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00149_line1_reason():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00149_line1_message():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00149_terminal_message():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00149_terminal_level():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00149_terminal_event():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00149_terminal_stage():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00149_terminal_reason():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00149_warning_present():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00149_warning_level():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00149_defer_lines():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00149_no_message_text():
    transcript, expected = _case(149)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00150_rets():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00150_dupe():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00150_dupe_state_stable():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00150_records_exact():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00150_state():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00150_attempt():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00150_failure():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00150_quarantine_reason():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00150_recovery_state():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00150_worker_failure():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00150_worker_failure_evidence():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00150_empty_evidence():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00150_merge_pending():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00150_retry_started_at():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00150_available_at_bound():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00150_available_at_exact():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00150_line_count():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00150_line1_level():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00150_line1_event():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00150_line1_attempt():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00150_line1_stage():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00150_line1_reason():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00150_line1_message():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00150_terminal_message():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00150_terminal_level():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00150_terminal_event():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00150_terminal_stage():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00150_terminal_reason():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00150_warning_present():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00150_warning_level():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00150_defer_lines():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00150_no_message_text():
    transcript, expected = _case(150)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00151_rets():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00151_dupe():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00151_dupe_state_stable():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00151_records_exact():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00151_state():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00151_attempt():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00151_failure():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00151_quarantine_reason():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00151_recovery_state():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00151_worker_failure():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00151_worker_failure_evidence():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00151_empty_evidence():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00151_merge_pending():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00151_retry_started_at():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00151_available_at_bound():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00151_available_at_exact():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00151_line_count():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00151_line1_level():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00151_line1_event():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00151_line1_attempt():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00151_line1_stage():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00151_line1_reason():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00151_line1_message():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00151_terminal_message():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00151_terminal_level():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00151_terminal_event():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00151_terminal_stage():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00151_terminal_reason():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00151_warning_present():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00151_warning_level():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00151_defer_lines():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00151_no_message_text():
    transcript, expected = _case(151)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w12w_00152_rets():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w12w_00152_dupe():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w12w_00152_dupe_state_stable():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w12w_00152_records_exact():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w12w_00152_state():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'state')


def test_b09_w12w_00152_attempt():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w12w_00152_failure():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w12w_00152_quarantine_reason():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w12w_00152_recovery_state():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w12w_00152_worker_failure():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w12w_00152_worker_failure_evidence():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w12w_00152_empty_evidence():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w12w_00152_merge_pending():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w12w_00152_retry_started_at():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w12w_00152_available_at_bound():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w12w_00152_available_at_exact():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w12w_00152_line_count():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w12w_00152_line1_level():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w12w_00152_line1_event():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w12w_00152_line1_attempt():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w12w_00152_line1_stage():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w12w_00152_line1_reason():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w12w_00152_line1_message():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w12w_00152_terminal_message():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w12w_00152_terminal_level():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w12w_00152_terminal_event():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w12w_00152_terminal_stage():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w12w_00152_terminal_reason():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w12w_00152_warning_present():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w12w_00152_warning_level():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w12w_00152_defer_lines():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w12w_00152_no_message_text():
    transcript, expected = _case(152)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00153_rets():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00153_dupe():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00153_dupe_state_stable():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00153_records_exact():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00153_state():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00153_attempt():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00153_failure():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00153_quarantine_reason():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00153_recovery_state():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00153_worker_failure():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00153_worker_failure_evidence():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00153_empty_evidence():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00153_merge_pending():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00153_retry_started_at():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00153_available_at_bound():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00153_available_at_exact():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00153_line_count():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00153_line1_level():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00153_line1_event():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00153_line1_attempt():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00153_line1_stage():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00153_line1_reason():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00153_line1_message():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00153_terminal_message():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00153_terminal_level():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00153_terminal_event():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00153_terminal_stage():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00153_terminal_reason():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00153_warning_present():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00153_warning_level():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00153_defer_lines():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00153_no_message_text():
    transcript, expected = _case(153)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00154_rets():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00154_dupe():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00154_dupe_state_stable():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00154_records_exact():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00154_state():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00154_attempt():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00154_failure():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00154_quarantine_reason():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00154_recovery_state():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00154_worker_failure():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00154_worker_failure_evidence():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00154_empty_evidence():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00154_merge_pending():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00154_retry_started_at():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00154_available_at_bound():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00154_available_at_exact():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00154_line_count():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00154_line1_level():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00154_line1_event():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00154_line1_attempt():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00154_line1_stage():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00154_line1_reason():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00154_line1_message():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00154_terminal_message():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00154_terminal_level():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00154_terminal_event():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00154_terminal_stage():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00154_terminal_reason():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00154_warning_present():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00154_warning_level():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00154_defer_lines():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00154_no_message_text():
    transcript, expected = _case(154)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00155_rets():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00155_dupe():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00155_dupe_state_stable():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00155_records_exact():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00155_state():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00155_attempt():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00155_failure():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00155_quarantine_reason():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00155_recovery_state():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00155_worker_failure():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00155_worker_failure_evidence():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00155_empty_evidence():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00155_merge_pending():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00155_retry_started_at():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00155_available_at_bound():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00155_available_at_exact():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00155_line_count():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00155_line1_level():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00155_line1_event():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00155_line1_attempt():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00155_line1_stage():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00155_line1_reason():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00155_line1_message():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00155_terminal_message():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00155_terminal_level():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00155_terminal_event():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00155_terminal_stage():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00155_terminal_reason():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00155_warning_present():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00155_warning_level():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00155_defer_lines():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00155_no_message_text():
    transcript, expected = _case(155)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00156_rets():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00156_dupe():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00156_dupe_state_stable():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00156_records_exact():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00156_state():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00156_attempt():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00156_failure():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00156_quarantine_reason():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00156_recovery_state():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00156_worker_failure():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00156_worker_failure_evidence():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00156_empty_evidence():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00156_merge_pending():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00156_retry_started_at():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00156_available_at_bound():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00156_available_at_exact():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00156_line_count():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00156_line1_level():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00156_line1_event():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00156_line1_attempt():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00156_line1_stage():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00156_line1_reason():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00156_line1_message():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00156_terminal_message():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00156_terminal_level():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00156_terminal_event():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00156_terminal_stage():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00156_terminal_reason():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00156_warning_present():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00156_warning_level():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00156_defer_lines():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00156_no_message_text():
    transcript, expected = _case(156)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w13w_00157_rets():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w13w_00157_dupe():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w13w_00157_dupe_state_stable():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w13w_00157_records_exact():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w13w_00157_state():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'state')


def test_b09_w13w_00157_attempt():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w13w_00157_failure():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w13w_00157_quarantine_reason():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w13w_00157_recovery_state():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w13w_00157_worker_failure():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w13w_00157_worker_failure_evidence():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w13w_00157_empty_evidence():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w13w_00157_merge_pending():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w13w_00157_retry_started_at():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w13w_00157_available_at_bound():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w13w_00157_available_at_exact():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w13w_00157_line_count():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w13w_00157_line1_level():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w13w_00157_line1_event():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w13w_00157_line1_attempt():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w13w_00157_line1_stage():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w13w_00157_line1_reason():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w13w_00157_line1_message():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w13w_00157_terminal_message():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w13w_00157_terminal_level():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w13w_00157_terminal_event():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w13w_00157_terminal_stage():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w13w_00157_terminal_reason():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w13w_00157_warning_present():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w13w_00157_warning_level():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w13w_00157_defer_lines():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w13w_00157_no_message_text():
    transcript, expected = _case(157)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00158_rets():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00158_dupe():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00158_dupe_state_stable():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00158_records_exact():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00158_state():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00158_attempt():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00158_failure():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00158_quarantine_reason():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00158_recovery_state():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00158_worker_failure():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00158_worker_failure_evidence():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00158_empty_evidence():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00158_merge_pending():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00158_retry_started_at():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00158_available_at_bound():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00158_available_at_exact():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00158_line_count():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00158_line1_level():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00158_line1_event():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00158_line1_attempt():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00158_line1_stage():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00158_line1_reason():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00158_line1_message():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00158_terminal_message():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00158_terminal_level():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00158_terminal_event():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00158_terminal_stage():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00158_terminal_reason():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00158_warning_present():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00158_warning_level():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00158_defer_lines():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00158_no_message_text():
    transcript, expected = _case(158)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00159_rets():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00159_dupe():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00159_dupe_state_stable():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00159_records_exact():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00159_state():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00159_attempt():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00159_failure():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00159_quarantine_reason():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00159_recovery_state():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00159_worker_failure():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00159_worker_failure_evidence():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00159_empty_evidence():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00159_merge_pending():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00159_retry_started_at():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00159_available_at_bound():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00159_available_at_exact():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00159_line_count():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00159_line1_level():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00159_line1_event():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00159_line1_attempt():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00159_line1_stage():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00159_line1_reason():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00159_line1_message():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00159_terminal_message():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00159_terminal_level():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00159_terminal_event():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00159_terminal_stage():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00159_terminal_reason():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00159_warning_present():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00159_warning_level():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00159_defer_lines():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00159_no_message_text():
    transcript, expected = _case(159)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00160_rets():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00160_dupe():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00160_dupe_state_stable():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00160_records_exact():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00160_state():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00160_attempt():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00160_failure():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00160_quarantine_reason():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00160_recovery_state():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00160_worker_failure():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00160_worker_failure_evidence():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00160_empty_evidence():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00160_merge_pending():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00160_retry_started_at():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00160_available_at_bound():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00160_available_at_exact():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00160_line_count():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00160_line1_level():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00160_line1_event():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00160_line1_attempt():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00160_line1_stage():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00160_line1_reason():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00160_line1_message():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00160_terminal_message():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00160_terminal_level():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00160_terminal_event():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00160_terminal_stage():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00160_terminal_reason():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00160_warning_present():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00160_warning_level():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00160_defer_lines():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00160_no_message_text():
    transcript, expected = _case(160)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00161_rets():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00161_dupe():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00161_dupe_state_stable():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00161_records_exact():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00161_state():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00161_attempt():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00161_failure():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00161_quarantine_reason():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00161_recovery_state():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00161_worker_failure():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00161_worker_failure_evidence():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00161_empty_evidence():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00161_merge_pending():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00161_retry_started_at():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00161_available_at_bound():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00161_available_at_exact():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00161_line_count():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00161_line1_level():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00161_line1_event():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00161_line1_attempt():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00161_line1_stage():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00161_line1_reason():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00161_line1_message():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00161_terminal_message():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00161_terminal_level():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00161_terminal_event():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00161_terminal_stage():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00161_terminal_reason():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00161_warning_present():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00161_warning_level():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00161_defer_lines():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00161_no_message_text():
    transcript, expected = _case(161)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w14w_00162_rets():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w14w_00162_dupe():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w14w_00162_dupe_state_stable():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w14w_00162_records_exact():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w14w_00162_state():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'state')


def test_b09_w14w_00162_attempt():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w14w_00162_failure():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w14w_00162_quarantine_reason():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w14w_00162_recovery_state():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w14w_00162_worker_failure():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w14w_00162_worker_failure_evidence():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w14w_00162_empty_evidence():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w14w_00162_merge_pending():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w14w_00162_retry_started_at():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w14w_00162_available_at_bound():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w14w_00162_available_at_exact():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w14w_00162_line_count():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w14w_00162_line1_level():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w14w_00162_line1_event():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w14w_00162_line1_attempt():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w14w_00162_line1_stage():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w14w_00162_line1_reason():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w14w_00162_line1_message():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w14w_00162_terminal_message():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w14w_00162_terminal_level():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w14w_00162_terminal_event():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w14w_00162_terminal_stage():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w14w_00162_terminal_reason():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w14w_00162_warning_present():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w14w_00162_warning_level():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w14w_00162_defer_lines():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w14w_00162_no_message_text():
    transcript, expected = _case(162)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00163_rets():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00163_dupe():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00163_dupe_state_stable():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00163_records_exact():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00163_state():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00163_attempt():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00163_failure():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00163_quarantine_reason():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00163_recovery_state():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00163_worker_failure():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00163_worker_failure_evidence():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00163_empty_evidence():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00163_merge_pending():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00163_retry_started_at():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00163_available_at_bound():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00163_available_at_exact():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00163_line_count():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00163_line1_level():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00163_line1_event():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00163_line1_attempt():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00163_line1_stage():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00163_line1_reason():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00163_line1_message():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00163_terminal_message():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00163_terminal_level():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00163_terminal_event():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00163_terminal_stage():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00163_terminal_reason():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00163_warning_present():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00163_warning_level():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00163_defer_lines():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00163_no_message_text():
    transcript, expected = _case(163)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00164_rets():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00164_dupe():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00164_dupe_state_stable():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00164_records_exact():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00164_state():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00164_attempt():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00164_failure():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00164_quarantine_reason():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00164_recovery_state():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00164_worker_failure():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00164_worker_failure_evidence():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00164_empty_evidence():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00164_merge_pending():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00164_retry_started_at():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00164_available_at_bound():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00164_available_at_exact():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00164_line_count():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00164_line1_level():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00164_line1_event():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00164_line1_attempt():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00164_line1_stage():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00164_line1_reason():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00164_line1_message():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00164_terminal_message():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00164_terminal_level():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00164_terminal_event():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00164_terminal_stage():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00164_terminal_reason():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00164_warning_present():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00164_warning_level():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00164_defer_lines():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00164_no_message_text():
    transcript, expected = _case(164)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00165_rets():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00165_dupe():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00165_dupe_state_stable():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00165_records_exact():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00165_state():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00165_attempt():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00165_failure():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00165_quarantine_reason():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00165_recovery_state():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00165_worker_failure():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00165_worker_failure_evidence():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00165_empty_evidence():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00165_merge_pending():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00165_retry_started_at():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00165_available_at_bound():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00165_available_at_exact():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00165_line_count():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00165_line1_level():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00165_line1_event():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00165_line1_attempt():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00165_line1_stage():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00165_line1_reason():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00165_line1_message():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00165_terminal_message():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00165_terminal_level():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00165_terminal_event():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00165_terminal_stage():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00165_terminal_reason():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00165_warning_present():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00165_warning_level():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00165_defer_lines():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00165_no_message_text():
    transcript, expected = _case(165)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00166_rets():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00166_dupe():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00166_dupe_state_stable():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00166_records_exact():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00166_state():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00166_attempt():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00166_failure():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00166_quarantine_reason():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00166_recovery_state():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00166_worker_failure():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00166_worker_failure_evidence():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00166_empty_evidence():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00166_merge_pending():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00166_retry_started_at():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00166_available_at_bound():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00166_available_at_exact():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00166_line_count():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00166_line1_level():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00166_line1_event():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00166_line1_attempt():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00166_line1_stage():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00166_line1_reason():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00166_line1_message():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00166_terminal_message():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00166_terminal_level():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00166_terminal_event():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00166_terminal_stage():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00166_terminal_reason():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00166_warning_present():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00166_warning_level():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00166_defer_lines():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00166_no_message_text():
    transcript, expected = _case(166)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w15w_00167_rets():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w15w_00167_dupe():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w15w_00167_dupe_state_stable():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w15w_00167_records_exact():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w15w_00167_state():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'state')


def test_b09_w15w_00167_attempt():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w15w_00167_failure():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w15w_00167_quarantine_reason():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w15w_00167_recovery_state():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w15w_00167_worker_failure():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w15w_00167_worker_failure_evidence():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w15w_00167_empty_evidence():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w15w_00167_merge_pending():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w15w_00167_retry_started_at():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w15w_00167_available_at_bound():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w15w_00167_available_at_exact():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w15w_00167_line_count():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w15w_00167_line1_level():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w15w_00167_line1_event():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w15w_00167_line1_attempt():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w15w_00167_line1_stage():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w15w_00167_line1_reason():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w15w_00167_line1_message():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w15w_00167_terminal_message():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w15w_00167_terminal_level():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w15w_00167_terminal_event():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w15w_00167_terminal_stage():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w15w_00167_terminal_reason():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w15w_00167_warning_present():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w15w_00167_warning_level():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w15w_00167_defer_lines():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w15w_00167_no_message_text():
    transcript, expected = _case(167)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w01w_00168_rets():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w01w_00168_dupe():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w01w_00168_dupe_state_stable():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w01w_00168_records_exact():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w01w_00168_state():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'state')


def test_b09_w01w_00168_attempt():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w01w_00168_failure():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w01w_00168_quarantine_reason():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w01w_00168_recovery_state():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w01w_00168_worker_failure():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w01w_00168_worker_failure_evidence():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w01w_00168_empty_evidence():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w01w_00168_merge_pending():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w01w_00168_retry_started_at():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w01w_00168_available_at_bound():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w01w_00168_available_at_exact():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w01w_00168_line_count():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w01w_00168_line1_level():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w01w_00168_line1_event():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w01w_00168_line1_attempt():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w01w_00168_line1_stage():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w01w_00168_line1_reason():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w01w_00168_line1_message():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w01w_00168_terminal_message():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w01w_00168_terminal_level():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w01w_00168_terminal_event():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w01w_00168_terminal_stage():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w01w_00168_terminal_reason():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w01w_00168_warning_present():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w01w_00168_warning_level():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w01w_00168_defer_lines():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w01w_00168_no_message_text():
    transcript, expected = _case(168)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00169_rets():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00169_dupe():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00169_dupe_state_stable():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00169_records_exact():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00169_state():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00169_attempt():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00169_failure():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00169_quarantine_reason():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00169_recovery_state():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00169_worker_failure():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00169_worker_failure_evidence():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00169_empty_evidence():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00169_merge_pending():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00169_retry_started_at():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00169_available_at_bound():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00169_available_at_exact():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00169_line_count():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00169_line1_level():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00169_line1_event():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00169_line1_attempt():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00169_line1_stage():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00169_line1_reason():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00169_line1_message():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00169_terminal_message():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00169_terminal_level():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00169_terminal_event():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00169_terminal_stage():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00169_terminal_reason():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00169_warning_present():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00169_warning_level():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00169_defer_lines():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00169_no_message_text():
    transcript, expected = _case(169)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00170_rets():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00170_dupe():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00170_dupe_state_stable():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00170_records_exact():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00170_state():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00170_attempt():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00170_failure():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00170_quarantine_reason():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00170_recovery_state():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00170_worker_failure():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00170_worker_failure_evidence():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00170_empty_evidence():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00170_merge_pending():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00170_retry_started_at():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00170_available_at_bound():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00170_available_at_exact():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00170_line_count():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00170_line1_level():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00170_line1_event():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00170_line1_attempt():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00170_line1_stage():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00170_line1_reason():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00170_line1_message():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00170_terminal_message():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00170_terminal_level():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00170_terminal_event():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00170_terminal_stage():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00170_terminal_reason():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00170_warning_present():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00170_warning_level():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00170_defer_lines():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00170_no_message_text():
    transcript, expected = _case(170)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00171_rets():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00171_dupe():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00171_dupe_state_stable():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00171_records_exact():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00171_state():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00171_attempt():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00171_failure():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00171_quarantine_reason():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00171_recovery_state():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00171_worker_failure():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00171_worker_failure_evidence():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00171_empty_evidence():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00171_merge_pending():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00171_retry_started_at():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00171_available_at_bound():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00171_available_at_exact():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00171_line_count():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00171_line1_level():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00171_line1_event():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00171_line1_attempt():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00171_line1_stage():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00171_line1_reason():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00171_line1_message():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00171_terminal_message():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00171_terminal_level():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00171_terminal_event():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00171_terminal_stage():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00171_terminal_reason():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00171_warning_present():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00171_warning_level():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00171_defer_lines():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00171_no_message_text():
    transcript, expected = _case(171)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00172_rets():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00172_dupe():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00172_dupe_state_stable():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00172_records_exact():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00172_state():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00172_attempt():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00172_failure():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00172_quarantine_reason():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00172_recovery_state():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00172_worker_failure():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00172_worker_failure_evidence():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00172_empty_evidence():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00172_merge_pending():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00172_retry_started_at():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00172_available_at_bound():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00172_available_at_exact():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00172_line_count():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00172_line1_level():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00172_line1_event():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00172_line1_attempt():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00172_line1_stage():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00172_line1_reason():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00172_line1_message():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00172_terminal_message():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00172_terminal_level():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00172_terminal_event():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00172_terminal_stage():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00172_terminal_reason():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00172_warning_present():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00172_warning_level():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00172_defer_lines():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00172_no_message_text():
    transcript, expected = _case(172)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w02w_00173_rets():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w02w_00173_dupe():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w02w_00173_dupe_state_stable():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w02w_00173_records_exact():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w02w_00173_state():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'state')


def test_b09_w02w_00173_attempt():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w02w_00173_failure():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w02w_00173_quarantine_reason():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w02w_00173_recovery_state():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w02w_00173_worker_failure():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w02w_00173_worker_failure_evidence():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w02w_00173_empty_evidence():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w02w_00173_merge_pending():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w02w_00173_retry_started_at():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w02w_00173_available_at_bound():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w02w_00173_available_at_exact():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w02w_00173_line_count():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w02w_00173_line1_level():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w02w_00173_line1_event():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w02w_00173_line1_attempt():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w02w_00173_line1_stage():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w02w_00173_line1_reason():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w02w_00173_line1_message():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w02w_00173_terminal_message():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w02w_00173_terminal_level():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w02w_00173_terminal_event():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w02w_00173_terminal_stage():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w02w_00173_terminal_reason():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w02w_00173_warning_present():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w02w_00173_warning_level():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w02w_00173_defer_lines():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w02w_00173_no_message_text():
    transcript, expected = _case(173)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00174_rets():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00174_dupe():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00174_dupe_state_stable():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00174_records_exact():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00174_state():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00174_attempt():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00174_failure():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00174_quarantine_reason():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00174_recovery_state():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00174_worker_failure():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00174_worker_failure_evidence():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00174_empty_evidence():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00174_merge_pending():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00174_retry_started_at():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00174_available_at_bound():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00174_available_at_exact():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00174_line_count():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00174_line1_level():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00174_line1_event():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00174_line1_attempt():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00174_line1_stage():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00174_line1_reason():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00174_line1_message():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00174_terminal_message():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00174_terminal_level():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00174_terminal_event():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00174_terminal_stage():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00174_terminal_reason():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00174_warning_present():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00174_warning_level():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00174_defer_lines():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00174_no_message_text():
    transcript, expected = _case(174)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00175_rets():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00175_dupe():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00175_dupe_state_stable():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00175_records_exact():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00175_state():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00175_attempt():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00175_failure():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00175_quarantine_reason():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00175_recovery_state():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00175_worker_failure():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00175_worker_failure_evidence():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00175_empty_evidence():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00175_merge_pending():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00175_retry_started_at():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00175_available_at_bound():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00175_available_at_exact():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00175_line_count():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00175_line1_level():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00175_line1_event():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00175_line1_attempt():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00175_line1_stage():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00175_line1_reason():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00175_line1_message():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00175_terminal_message():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00175_terminal_level():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00175_terminal_event():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00175_terminal_stage():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00175_terminal_reason():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00175_warning_present():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00175_warning_level():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00175_defer_lines():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00175_no_message_text():
    transcript, expected = _case(175)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00176_rets():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00176_dupe():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00176_dupe_state_stable():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00176_records_exact():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00176_state():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00176_attempt():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00176_failure():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00176_quarantine_reason():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00176_recovery_state():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00176_worker_failure():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00176_worker_failure_evidence():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00176_empty_evidence():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00176_merge_pending():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00176_retry_started_at():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00176_available_at_bound():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00176_available_at_exact():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00176_line_count():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00176_line1_level():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00176_line1_event():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00176_line1_attempt():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00176_line1_stage():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00176_line1_reason():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00176_line1_message():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00176_terminal_message():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00176_terminal_level():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00176_terminal_event():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00176_terminal_stage():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00176_terminal_reason():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00176_warning_present():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00176_warning_level():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00176_defer_lines():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00176_no_message_text():
    transcript, expected = _case(176)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00177_rets():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00177_dupe():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00177_dupe_state_stable():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00177_records_exact():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00177_state():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00177_attempt():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00177_failure():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00177_quarantine_reason():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00177_recovery_state():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00177_worker_failure():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00177_worker_failure_evidence():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00177_empty_evidence():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00177_merge_pending():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00177_retry_started_at():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00177_available_at_bound():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00177_available_at_exact():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00177_line_count():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00177_line1_level():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00177_line1_event():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00177_line1_attempt():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00177_line1_stage():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00177_line1_reason():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00177_line1_message():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00177_terminal_message():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00177_terminal_level():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00177_terminal_event():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00177_terminal_stage():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00177_terminal_reason():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00177_warning_present():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00177_warning_level():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00177_defer_lines():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00177_no_message_text():
    transcript, expected = _case(177)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w03w_00178_rets():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w03w_00178_dupe():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w03w_00178_dupe_state_stable():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w03w_00178_records_exact():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w03w_00178_state():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'state')


def test_b09_w03w_00178_attempt():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w03w_00178_failure():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w03w_00178_quarantine_reason():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w03w_00178_recovery_state():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w03w_00178_worker_failure():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w03w_00178_worker_failure_evidence():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w03w_00178_empty_evidence():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w03w_00178_merge_pending():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w03w_00178_retry_started_at():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w03w_00178_available_at_bound():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w03w_00178_available_at_exact():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w03w_00178_line_count():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w03w_00178_line1_level():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w03w_00178_line1_event():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w03w_00178_line1_attempt():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w03w_00178_line1_stage():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w03w_00178_line1_reason():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w03w_00178_line1_message():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w03w_00178_terminal_message():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w03w_00178_terminal_level():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w03w_00178_terminal_event():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w03w_00178_terminal_stage():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w03w_00178_terminal_reason():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w03w_00178_warning_present():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w03w_00178_warning_level():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w03w_00178_defer_lines():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w03w_00178_no_message_text():
    transcript, expected = _case(178)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00179_rets():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00179_dupe():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00179_dupe_state_stable():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00179_records_exact():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00179_state():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00179_attempt():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00179_failure():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00179_quarantine_reason():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00179_recovery_state():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00179_worker_failure():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00179_worker_failure_evidence():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00179_empty_evidence():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00179_merge_pending():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00179_retry_started_at():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00179_available_at_bound():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00179_available_at_exact():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00179_line_count():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00179_line1_level():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00179_line1_event():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00179_line1_attempt():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00179_line1_stage():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00179_line1_reason():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00179_line1_message():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00179_terminal_message():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00179_terminal_level():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00179_terminal_event():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00179_terminal_stage():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00179_terminal_reason():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00179_warning_present():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00179_warning_level():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00179_defer_lines():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00179_no_message_text():
    transcript, expected = _case(179)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00180_rets():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00180_dupe():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00180_dupe_state_stable():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00180_records_exact():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00180_state():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00180_attempt():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00180_failure():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00180_quarantine_reason():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00180_recovery_state():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00180_worker_failure():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00180_worker_failure_evidence():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00180_empty_evidence():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00180_merge_pending():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00180_retry_started_at():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00180_available_at_bound():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00180_available_at_exact():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00180_line_count():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00180_line1_level():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00180_line1_event():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00180_line1_attempt():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00180_line1_stage():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00180_line1_reason():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00180_line1_message():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00180_terminal_message():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00180_terminal_level():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00180_terminal_event():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00180_terminal_stage():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00180_terminal_reason():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00180_warning_present():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00180_warning_level():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00180_defer_lines():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00180_no_message_text():
    transcript, expected = _case(180)
    _assert_facet(transcript, expected, 'no_message_text')


def test_b09_w04w_00181_rets():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'rets')


def test_b09_w04w_00181_dupe():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'dupe')


def test_b09_w04w_00181_dupe_state_stable():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'dupe_state_stable')


def test_b09_w04w_00181_records_exact():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'records_exact')


def test_b09_w04w_00181_state():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'state')


def test_b09_w04w_00181_attempt():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'attempt')


def test_b09_w04w_00181_failure():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'failure')


def test_b09_w04w_00181_quarantine_reason():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'quarantine_reason')


def test_b09_w04w_00181_recovery_state():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'recovery_state')


def test_b09_w04w_00181_worker_failure():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'worker_failure')


def test_b09_w04w_00181_worker_failure_evidence():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'worker_failure_evidence')


def test_b09_w04w_00181_empty_evidence():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'empty_evidence')


def test_b09_w04w_00181_merge_pending():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'merge_pending')


def test_b09_w04w_00181_retry_started_at():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'retry_started_at')


def test_b09_w04w_00181_available_at_bound():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'available_at_bound')


def test_b09_w04w_00181_available_at_exact():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'available_at_exact')


def test_b09_w04w_00181_line_count():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'line_count')


def test_b09_w04w_00181_line1_level():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'line1_level')


def test_b09_w04w_00181_line1_event():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'line1_event')


def test_b09_w04w_00181_line1_attempt():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'line1_attempt')


def test_b09_w04w_00181_line1_stage():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'line1_stage')


def test_b09_w04w_00181_line1_reason():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'line1_reason')


def test_b09_w04w_00181_line1_message():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'line1_message')


def test_b09_w04w_00181_terminal_message():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'terminal_message')


def test_b09_w04w_00181_terminal_level():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'terminal_level')


def test_b09_w04w_00181_terminal_event():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'terminal_event')


def test_b09_w04w_00181_terminal_stage():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'terminal_stage')


def test_b09_w04w_00181_terminal_reason():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'terminal_reason')


def test_b09_w04w_00181_warning_present():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'warning_present')


def test_b09_w04w_00181_warning_level():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'warning_level')


def test_b09_w04w_00181_defer_lines():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'defer_lines')


def test_b09_w04w_00181_no_message_text():
    transcript, expected = _case(181)
    _assert_facet(transcript, expected, 'no_message_text')
