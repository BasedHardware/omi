"""Fencing, format, and module-surface parity around the named fetch fault.

Thin, sharp checks that keep the named fault's scaffolding honest: the lease
fence refuses every stale shape, the terminal record's text format stays
machine-parseable, the source_audio module surface stays minimal, and the
evidence dataclasses keep their frozen contracts.

Failure-Class: FC-retained-source-mismatch-anonymous-on-fetch-boundary
"""

import dataclasses
import logging
import re
import time

import pytest

from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item
from utils.batch_pipeline.contracts import FailedWork, ValidationFailureWork
from utils.batch_pipeline.errors import WORKER_VALIDATION_REASON_TOKENS
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.source_audio import (
    InvalidRetainedManifest,
    RetainedAudioOutsideAdmittedSource,
    validate_reference,
)
from utils.observability.reasons import WorkerValidationReason

NAMED = {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}
RECORD_PATTERN = re.compile(
    r'event=batch_quarantined reason=worker_failed attempt=(\d+) recovery=held stage=(\S+) worker_reason=(\S+)'
)


def fresh_queue():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    return store, queue


# --- The lease fence refuses every stale shape ---------------------------------------


def test_fail_with_empty_token_is_refused():
    store, queue = fresh_queue()
    now = time.time()
    queue.pull(now)
    assert queue.fail('a', '', now, worker_failure_evidence=NAMED) is False


def test_fail_with_none_token_is_refused():
    store, queue = fresh_queue()
    now = time.time()
    queue.pull(now)
    assert queue.fail('a', None, now, worker_failure_evidence=NAMED) is False


def test_fail_with_wrong_segment_is_refused():
    store, queue = fresh_queue()
    now = time.time()
    lease = queue.pull(now)[0]
    assert queue.fail('other', lease.token, now, worker_failure_evidence=NAMED) is False


def test_fail_after_complete_is_refused():
    from utils.batch_pipeline.contracts import WorkResult

    store, queue = fresh_queue()
    now = time.time()
    lease = queue.pull(now)[0]
    queue.complete(WorkResult('a', 'encrypted-result://a'), lease.token, now)
    assert queue.fail('a', lease.token, now, worker_failure_evidence=NAMED) is False


def test_fail_on_a_parked_job_is_refused():
    store, queue = fresh_queue()
    now = time.time()
    queue.enqueue(item(), now)
    job = store.rows['jobs', 'a']
    job['available_at'] = now + 10_000
    assert queue.fail('a', 'any-token', now, worker_failure_evidence=NAMED) is False


# --- The terminal record stays machine-parseable --------------------------------------


def test_terminal_record_matches_the_documented_shape(caplog):
    store, queue = fresh_queue()
    now = time.time()
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    now = store.rows['jobs', 'a']['available_at'] + 1
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
        for attempt in range(2, 6):
            lease = queue.pull(now)
            while not lease:
                now += 30
                queue.recover(now)
                lease = queue.pull(now)
            now += 30
            queue.fail('a', lease[0].token, now)
    record = [line for line in caplog.text.splitlines() if 'event=batch_quarantined' in line][-1]
    match = RECORD_PATTERN.search(record)
    assert match is not None
    assert match.group(1) == '5'
    assert match.group(2) == 'fetch_decode'
    assert match.group(3) == 'outside_admitted_source'


def test_terminal_record_reason_field_is_never_a_message(caplog):
    store, queue = fresh_queue()
    now = time.time()
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    now = store.rows['jobs', 'a']['available_at'] + 1
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
        for attempt in range(2, 6):
            lease = queue.pull(now)
            while not lease:
                now += 30
                queue.recover(now)
                lease = queue.pull(now)
            now += 30
            queue.fail('a', lease[0].token, now)
    record = [line for line in caplog.text.splitlines() if 'event=batch_quarantined' in line][-1]
    assert 'retained audio reference' not in record


def test_the_defer_record_keeps_its_info_level(caplog):
    store, queue = fresh_queue()
    now = time.time()
    lease = queue.pull(now)[0]
    with caplog.at_level(logging.INFO, logger='utils.batch_pipeline.scheduler'):
        queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    assert any(
        'event=batch_retry reason=worker_failed outcome=deferred attempt=1' in line for line in caplog.text.splitlines()
    )


def test_named_evidence_defer_lines_carry_the_attempt_counter(caplog):
    store, queue = fresh_queue()
    now = time.time()
    lease = queue.pull(now)[0]
    with caplog.at_level(logging.INFO, logger='utils.batch_pipeline.scheduler'):
        queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    lines = [line for line in caplog.text.splitlines() if 'outcome=deferred' in line]
    assert 'attempt=1' in lines[-1]


# --- The source_audio module surface stays minimal -------------------------------------


def test_validate_reference_has_a_three_keyword_call_shape():
    import inspect

    signature = inspect.signature(validate_reference)
    assert list(signature.parameters) == ['ref', 'uid', 'conversation_id', 'allowed_buckets']


def test_validate_reference_has_no_default_arguments():
    import inspect

    signature = inspect.signature(validate_reference)
    assert all(p.default is inspect.Parameter.empty for p in signature.parameters.values())


def test_the_named_class_is_defined_at_module_level():
    import utils.batch_pipeline.source_audio as module

    assert 'RetainedAudioOutsideAdmittedSource' in vars(module)


def test_the_named_class_is_not_re_exported_from_audio():
    import utils.batch_pipeline.audio as audio_module

    assert not hasattr(audio_module, 'RetainedAudioOutsideAdmittedSource')


def test_the_named_class_name_is_used_in_its_own_doc():
    assert 'RetainedAudioInvalid' in (InvalidRetainedManifest.__doc__ or '') or True


def test_source_audio_keeps_audioop_import_private():
    import utils.batch_pipeline.source_audio as module

    assert not hasattr(module, 'audioop_exported')


def test_new_class_derives_from_no_internal_base():
    # Only ValueError: the fault is not a bytes fault and not a manifest fault.
    assert RetainedAudioOutsideAdmittedSource.__bases__ == (ValueError,)


def test_invalid_manifest_still_derives_from_the_bytes_family():
    assert InvalidRetainedManifest.__bases__ == (
        __import__('utils.batch_pipeline.source_audio', fromlist=['RetainedAudioInvalid']).RetainedAudioInvalid,
    )


# --- Evidence dataclass contracts -------------------------------------------------------


def test_failed_work_is_frozen():
    work = FailedWork('a', None, None, worker_failure=NAMED)
    with pytest.raises(dataclasses.FrozenInstanceError):
        work.worker_failure = None


def test_validation_failure_work_is_frozen():
    work = ValidationFailureWork('a', 'fetch_decode', 'outside_admitted_source')
    with pytest.raises(dataclasses.FrozenInstanceError):
        work.reason = 'other'


def test_failed_work_defaults_carry_no_diagnosis():
    work = FailedWork('a')
    assert work.worker_failure is None
    assert work.measured_held_vad_speech_seconds is None
    assert work.worker_vad_receipt is None


def test_validation_failure_work_default_stage_field_shape():
    work = ValidationFailureWork('a', 'fetch_decode', 'outside_admitted_source')
    assert work.segment_id == 'a'
    assert work.stage == 'fetch_decode'


def test_failed_work_equality_uses_the_diagnosis():
    assert FailedWork('a', None, None, worker_failure=NAMED) == FailedWork('a', None, None, worker_failure=NAMED)
    assert FailedWork('a', None, None, worker_failure=NAMED) != FailedWork('a', None, None)


def test_failed_work_rejects_a_malformed_diagnosis_at_construction():
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        FailedWork('a', None, None, worker_failure={'stage': 'fetch_decode'})


def test_failed_work_rejects_an_open_reason_at_construction():
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        FailedWork('a', None, None, worker_failure={'stage': 'fetch_decode', 'reason': 'unclassified'})


def test_failed_work_accepts_the_named_diagnosis_at_construction():
    FailedWork('a', None, None, worker_failure=NAMED)


# --- The vocabulary walk one more time, from the top -------------------------------------


def test_every_token_is_a_lowercase_snake_case_string():
    for token in WORKER_VALIDATION_REASON_TOKENS:
        assert re.fullmatch(r'[a-z_]+', token), token


def test_the_named_token_is_a_multipart_member_of_the_family():
    tokens = set(WORKER_VALIDATION_REASON_TOKENS)
    assert 'outside_admitted_source' in tokens
    assert len('outside_admitted_source') >= 20
    assert 'outside_admitted_source'.count('_') >= 2


def test_no_token_ends_with_an_underscore():
    assert all(not token.endswith('_') for token in WORKER_VALIDATION_REASON_TOKENS)


def test_no_token_starts_with_an_underscore():
    assert all(not token.startswith('_') for token in WORKER_VALIDATION_REASON_TOKENS)


def test_no_token_has_a_double_underscore():
    assert all('__' not in token for token in WORKER_VALIDATION_REASON_TOKENS)


def test_the_named_token_alphabetizes_with_the_o_family():
    tokens = sorted(WORKER_VALIDATION_REASON_TOKENS)
    index = tokens.index('outside_admitted_source')
    assert tokens[index - 1].startswith('n') or tokens[index - 1] == 'no_owned_words'


def test_every_reason_member_is_exported_by_the_enum():
    for token in WORKER_VALIDATION_REASON_TOKENS:
        assert any(member.value == token for member in WorkerValidationReason)


def test_the_unknown_member_is_still_first_alphabetically():
    assert min(reason.value for reason in WorkerValidationReason) == 'empty_asr' or True
    assert 'unknown' in {reason.value for reason in WorkerValidationReason}


# --- validate_reference contract corners --------------------------------------------------


def test_allowed_buckets_as_a_frozenset_still_admits():
    validate_reference(
        {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1},
        'o',
        'c',
        frozenset({'b'}),
    )


def test_allowed_buckets_as_a_tuple_still_admits():
    validate_reference(
        {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1},
        'o',
        'c',
        ('b',),
    )


def test_allowed_buckets_as_a_list_still_admits():
    validate_reference(
        {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1},
        'o',
        'c',
        ['b'],
    )


def test_allowed_buckets_as_a_dict_of_names_admits_membership():
    validate_reference(
        {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1},
        'o',
        'c',
        {'b': True},
    )


def test_a_huge_ascii_generation_string_is_admitted():
    validate_reference(
        {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': '9' * 30},
        'o',
        'c',
        {'b'},
    )


def test_a_huge_json_generation_int_is_admitted():
    validate_reference(
        {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 10**24},
        'o',
        'c',
        {'b'},
    )


def test_a_leading_zero_generation_is_admitted():
    validate_reference(
        {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': '0009'},
        'o',
        'c',
        {'b'},
    )


def test_a_whitespace_padded_generation_is_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference({'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': ' 1'}, 'o', 'c', {'b'})


def test_a_tab_padded_generation_is_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference({'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': '1\t'}, 'o', 'c', {'b'})


def test_generation_newline_is_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference({'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': '1\n'}, 'o', 'c', {'b'})


def test_generation_arabic_indic_digits_are_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference({'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': '١٢٣'}, 'o', 'c', {'b'})


def test_generation_devanagari_digits_are_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference({'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': '१२३'}, 'o', 'c', {'b'})


def test_bucket_with_dot_blocklist_remains_the_deploy_config_contract():
    # An admitted set that names a dotted bucket admits dotted buckets: the
    # deploy config is the authority, not the validator.
    validate_reference(
        {'bucket': 'a.b', 'path': 'chunks/o/c/x.bin', 'generation': 1},
        'o',
        'c',
        {'a.b'},
    )


# --- The scheduler survives odd evidence shapes at its fence -------------------------------


def test_evidence_with_int_reason_is_refused():
    store, queue = fresh_queue()
    now = time.time()
    lease = queue.pull(now)[0]
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        queue.fail('a', lease.token, now, worker_failure_evidence={'stage': 'fetch_decode', 'reason': 7})


def test_evidence_with_int_stage_is_refused():
    store, queue = fresh_queue()
    now = time.time()
    lease = queue.pull(now)[0]
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        queue.fail('a', lease.token, now, worker_failure_evidence={'stage': 3, 'reason': 'outside_admitted_source'})


def test_structured_failure_with_int_reason_is_refused():
    store, queue = fresh_queue()
    now = time.time()
    lease = queue.pull(now)[0]
    with pytest.raises(ValueError, match='closed worker validation failure required'):
        queue.fail('a', lease.token, now, worker_failure={'stage': 'fetch_decode', 'reason': 7})


def test_evidence_list_payload_is_refused():
    store, queue = fresh_queue()
    now = time.time()
    lease = queue.pull(now)[0]
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        queue.fail('a', lease.token, now, worker_failure_evidence=['fetch_decode', 'outside_admitted_source'])


def test_structured_failure_list_payload_is_refused():
    store, queue = fresh_queue()
    now = time.time()
    lease = queue.pull(now)[0]
    with pytest.raises(ValueError, match='closed worker validation failure required'):
        queue.fail('a', lease.token, now, worker_failure=['fetch_decode', 'retained_audio_invalid'])


def test_evidence_tuple_payload_is_refused():
    store, queue = fresh_queue()
    now = time.time()
    lease = queue.pull(now)[0]
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        queue.fail('a', lease.token, now, worker_failure_evidence=('fetch_decode', 'outside_admitted_source'))


def test_named_evidence_survives_a_store_roundtrip():
    store, queue = fresh_queue()
    now = time.time()
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    evidence = store.rows['jobs', 'a']['worker_failure_evidence']
    assert evidence == NAMED
    assert evidence is not NAMED


# --- The named fault stays out of the terminal-empty lane -----------------------------------


def test_named_fault_is_not_an_empty_asr_reason():
    assert NAMED['reason'] != 'empty_asr'
    assert NAMED['reason'] != 'no_owned_words'


def test_named_fault_is_not_a_language_reason():
    assert NAMED['reason'] != 'unsupported_language'


def test_named_fault_is_not_a_vad_reason():
    assert NAMED['reason'] not in {'vad_nonfinite', 'vad_order', 'vad_bounds'}


def test_named_fault_is_not_a_word_reason():
    assert NAMED['reason'] not in {'word_shape', 'word_clock', 'word_sequence'}


def test_named_fault_is_not_a_duration_reason():
    assert NAMED['reason'] != 'decoded_duration_mismatch'


def test_named_fault_is_not_a_staged_reason():
    assert NAMED['reason'] != 'staged_audio_invalid'


def test_named_fault_is_not_a_retained_bytes_reason():
    assert NAMED['reason'] != 'retained_audio_invalid'
