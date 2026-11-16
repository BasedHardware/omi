"""The fetch_decode bare-ValueError poison custody family.

The sensor's top worker signature books a deterministic decode/parse poison
(``batch_worker_failed error_class=ValueError stage=fetch_decode``) once per
ladder attempt — five anonymous ERROR lines per drive — and ends in the
anonymous ``stage=unknown worker_reason=unclassified`` terminal quarantine,
for a fault no retry can repair. The fix types the poison arm
(``decode_payload_invalid``), ends the chain at its first occurrence with the
same terminal custody the typed decode trio rides, and demotes the report at
both the worker boundary and the shared terminal report. These tests pin the
family end to end: the closed token, the verdict lattice, the stage scoping,
the boundary route, the demoted channels at both terminals, and the real
poison raise site (a NaN admitted duration through the real retained-manifest
builder).

Failure-Class: FC-fetch-decode-valueerror-poison-walks-gpu-ladder-as-anonymous-per-attempt
"""

import json
import logging
import math
import wave
from dataclasses import replace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import (
    Aborted as GoogleAborted,
)
from google.api_core.exceptions import (
    DeadlineExceeded as GoogleDeadlineExceeded,
)
from google.api_core.exceptions import (
    InvalidArgument as GoogleInvalidArgument,
)
from google.api_core.exceptions import (
    NotFound as GoogleNotFound,
)
from google.api_core.exceptions import (
    ServiceUnavailable as GoogleServiceUnavailable,
)

from database.firestore_transaction_retry import FirestoreContentionExhausted
from diarizer.batch_pipeline import (
    DecodedDurationMismatch,
    decode_payload_failure_reason,
    decode_payload_is_deterministic,
)
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.contracts import ValidationFailureWork
from utils.batch_pipeline.errors import (
    VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS,
    WORKER_VALIDATION_REASON_TOKENS,
    WORKER_VALIDATION_REASONS,
    WORKER_VALIDATION_STAGES,
    report_terminal_quarantine,
    validate_worker_failure,
    validate_worker_failure_evidence,
    validation_disposition_failure,
)
from utils.batch_pipeline.source_audio import (
    InvalidRetainedManifest,
    MAGIC,
    RetainedAudioInvalid,
    RetainedAudioOutsideAdmittedSource,
    materialize,
)
from utils.batch_pipeline.worker_io import DecodeBudget, FirstDecode
from utils.observability.reasons import WorkerValidationReason, WorkerValidationStage, reason_values
from tests.unit.test_batch_pipeline_worker import item, setup_worker

POISON_TOKEN = WorkerValidationReason.DECODE_PAYLOAD_INVALID.value

ALL_STAGES = sorted(reason_values(WorkerValidationStage))


# --- The closed token joins the vocabulary --------------------------------------


def test_the_poison_token_is_the_closed_value():
    assert POISON_TOKEN == 'decode_payload_invalid'


def test_the_poison_token_is_a_closed_worker_validation_reason():
    assert POISON_TOKEN in WORKER_VALIDATION_REASONS


def test_the_poison_token_is_in_the_token_vocabulary():
    assert POISON_TOKEN in WORKER_VALIDATION_REASON_TOKENS


def test_the_poison_token_joins_the_unconditional_disposition_family():
    assert POISON_TOKEN in VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS


def test_the_store_validator_accepts_the_poison_diagnosis():
    validate_worker_failure({'stage': 'fetch_decode', 'reason': POISON_TOKEN})


def test_the_evidence_validator_accepts_the_poison_diagnosis():
    validate_worker_failure_evidence({'stage': 'fetch_decode', 'reason': POISON_TOKEN})


# --- The verdict: bare ValueError joins, the typed family keeps its tokens ------


def _poison_shapes():
    return [
        ValueError('refused'),
        ValueError(),
        UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'invalid start byte'),
        json.JSONDecodeError('bad json', 'doc', 1),
    ]


@pytest.mark.parametrize('shape', [0, 1, 2, 3], ids=['valueerror', 'valueerror_bare', 'unicodedecode', 'jsondecode'])
def test_bare_valueerror_shapes_are_the_poison_family(shape):
    assert decode_payload_is_deterministic(_poison_shapes()[shape]) is True


def test_the_nan_duration_refusal_from_the_real_builder_is_the_poison_family():
    unit = item(duration=60)
    body = (
        MAGIC
        + json.dumps(
            {
                'references': [
                    {
                        'bucket': 'b',
                        'path': f'chunks/{unit.owner_id}/{unit.conversation_id}/x.bin',
                        'generation': 1,
                        'pcm_sha256': 'deadbeef',
                    }
                ],
                'context': {},
                'owner_id': unit.owner_id,
                'conversation_id': unit.conversation_id,
                'capture_at': unit.capture_at,
            }
        ).encode()
    )
    with pytest.raises(ValueError) as excinfo:
        materialize(body, replace(unit, duration_seconds=float('nan')), lambda ref: b'')
    assert decode_payload_is_deterministic(excinfo.value) is True


@pytest.mark.parametrize(
    'fault',
    [
        StagedAudioInvalid('invalid staged WAV container'),
        InvalidRetainedManifest('malformed retained audio manifest'),
        RetainedAudioInvalid('invalid retained PCM'),
        RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source'),
        DecodedDurationMismatch('decoded duration differs from admitted capture'),
    ],
    ids=['staged', 'invalid_manifest', 'retained', 'outside_source', 'duration_mismatch'],
)
def test_the_typed_decode_family_keeps_its_own_tokens(fault):
    assert decode_payload_is_deterministic(fault) is False


@pytest.mark.parametrize(
    'fault',
    [
        TimeoutError('slow read'),
        OSError('disk bad'),
        RuntimeError('boom'),
        KeyError('mood'),
        wave.Error('truncated staged WAV'),
        GoogleInvalidArgument('400 The request is invalid'),
        GoogleNotFound('no such object'),
        GoogleServiceUnavailable('backend down'),
        GoogleDeadlineExceeded('deadline'),
        GoogleAborted('row locked'),
        FirestoreContentionExhausted('budget exhausted'),
        KeyboardInterrupt(),
        SystemExit(1),
    ],
    ids=[
        'timeout',
        'oserror',
        'runtime',
        'keyerror',
        'wave',
        'invalid_argument',
        'not_found',
        'unavailable',
        'deadline',
        'aborted',
        'contention',
        'keyboard_interrupt',
        'system_exit',
    ],
)
def test_every_non_valueerror_class_stays_outside_the_poison_family(fault):
    assert decode_payload_is_deterministic(fault) is False


@pytest.mark.parametrize(
    'hostile', [None, 7, 'refused', 0.5, object(), {'boom': 1}], ids=['none', 'int', 'str', 'float', 'object', 'dict']
)
def test_the_verdict_never_raises_on_hostile_input(hostile):
    assert decode_payload_is_deterministic(hostile) is False


# --- The reason arm: stage-scoped, gated on the anonymous attribution -----------


def test_the_poison_reason_names_the_token_at_fetch_decode():
    assert decode_payload_failure_reason(ValueError('x'), 'fetch_decode', 'unclassified') == POISON_TOKEN


@pytest.mark.parametrize('stage', [s for s in ALL_STAGES if s != 'fetch_decode'], ids=lambda s: s)
def test_the_same_class_at_any_other_stage_stays_outside(stage):
    assert decode_payload_failure_reason(ValueError('x'), stage, 'unclassified') is None


@pytest.mark.parametrize(
    'reason',
    ['staged_audio_invalid', 'retained_audio_invalid', 'decoded_duration_mismatch', 'empty_asr', 'unknown', ''],
    ids=['staged', 'retained', 'duration', 'empty', 'unknown', 'blank'],
)
def test_a_fault_already_attributed_by_a_typed_arm_stays_outside(reason):
    assert decode_payload_failure_reason(ValueError('x'), 'fetch_decode', reason) is None


def test_a_typed_class_is_never_rebooked_as_the_poison_even_anonymously():
    assert decode_payload_failure_reason(RetainedAudioInvalid('x'), 'fetch_decode', 'unclassified') is None


@pytest.mark.parametrize('hostile', [None, 7, 'refused'], ids=['none', 'int', 'str'])
def test_the_reason_arm_never_raises_on_hostile_faults(hostile):
    assert decode_payload_failure_reason(hostile, 'fetch_decode', 'unclassified') is None


# --- The disposition predicate: unconditional at fetch_decode, both flags -------


@pytest.mark.parametrize('disposition_enabled', [False, True], ids=['flag_off', 'flag_on'])
def test_the_poison_diagnosis_demotes_at_both_flags(disposition_enabled):
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': POISON_TOKEN}, disposition_enabled=disposition_enabled
        )
        is True
    )


@pytest.mark.parametrize('stage', [s for s in ALL_STAGES if s != 'fetch_decode'], ids=lambda s: s)
def test_the_poison_token_at_any_other_stage_keeps_the_fault_channel(stage):
    assert validation_disposition_failure({'stage': stage, 'reason': POISON_TOKEN}, disposition_enabled=True) is False


@pytest.mark.parametrize(
    'diagnosis',
    [
        None,
        7,
        'poison',
        {},
        {'stage': 'fetch_decode'},
        {'reason': POISON_TOKEN},
        {'stage': 'fetch_decode', 'reason': POISON_TOKEN, 'extra': 1},
    ],
    ids=['none', 'int', 'str', 'empty', 'stage_only', 'reason_only', 'extra_field'],
)
def test_the_predicate_never_raises_on_hostile_diagnoses(diagnosis):
    assert validation_disposition_failure(diagnosis, disposition_enabled=True) is False


# --- Both terminal report channels demote together ------------------------------


def _terminal_records(caplog, diagnosis, attempt=1):
    logger = logging.getLogger('diarizer.batch_pipeline')
    report_terminal_quarantine(logger, attempt=attempt, diagnosis=diagnosis)
    records = [r for r in caplog.records if 'event=' in r.getMessage()]
    return records


def test_the_verdict_terminal_demotes_the_poison_to_the_info_transition(caplog):
    caplog.set_level(logging.INFO)
    records = _terminal_records(caplog, {'stage': 'fetch_decode', 'reason': POISON_TOKEN}, attempt=3)
    disposition = [r for r in records if 'event=batch_validation_disposition' in r.getMessage()]
    quarantined = [r for r in records if 'event=batch_quarantined' in r.getMessage()]
    assert len(disposition) == 1 and not quarantined
    assert disposition[0].levelno == logging.INFO
    assert (
        'attempt=3 recovery=held stage=fetch_decode worker_reason=decode_payload_invalid' in disposition[0].getMessage()
    )
    # The awaiting-fenced-recovery warning follows every booking.
    assert any('outcome=held reason=awaiting_fenced_recovery' in r.getMessage() for r in records)


def test_the_lease_expiry_terminal_demotes_the_same_way(caplog):
    caplog.set_level(logging.INFO)
    records = _terminal_records(caplog, {'stage': 'fetch_decode', 'reason': POISON_TOKEN}, attempt=99)
    disposition = [r for r in records if 'event=batch_validation_disposition' in r.getMessage()]
    assert len(disposition) == 1
    assert 'attempt=99' in disposition[0].getMessage()


@pytest.mark.parametrize('stage', [s for s in ALL_STAGES if s != 'fetch_decode'], ids=lambda s: s)
def test_the_poison_token_off_its_stage_keeps_the_error_quarantine(caplog, stage):
    caplog.set_level(logging.INFO)
    records = _terminal_records(caplog, {'stage': stage, 'reason': POISON_TOKEN})
    quarantined = [r for r in records if 'event=batch_quarantined' in r.getMessage()]
    disposition = [r for r in records if 'event=batch_validation_disposition' in r.getMessage()]
    assert len(quarantined) == 1 and not disposition
    assert quarantined[0].levelno == logging.ERROR


def test_an_anonymous_diagnosis_still_books_the_anonymous_error_quarantine(caplog):
    caplog.set_level(logging.INFO)
    records = _terminal_records(caplog, {})
    quarantined = [r for r in records if 'event=batch_quarantined' in r.getMessage()]
    assert len(quarantined) == 1
    assert 'stage=unknown worker_reason=unclassified' in quarantined[0].getMessage()


# --- The boundary route: chain ends at the first occurrence ---------------------


def _poison_worker(monkeypatch, caplog, safety, disposition):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', safety)
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', disposition)
    caplog.set_level(logging.INFO)
    worker, words, saved, _, diarized, failures = setup_worker(decode=Mock(side_effect=ValueError('poison-bytes')))
    return worker, words, saved, diarized, failures


@pytest.mark.parametrize(
    'safety,disposition',
    [('true', 'true'), ('true', 'false'), ('false', 'true'), ('false', 'false')],
    ids=['safety+disp', 'safety', 'disp', 'neither'],
)
def test_the_poison_ends_the_chain_on_attempt_one_with_typed_custody(monkeypatch, caplog, safety, disposition):
    worker, words, saved, diarized, failures = _poison_worker(monkeypatch, caplog, safety, disposition)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', POISON_TOKEN)]
    # No GPU work ran, nothing persisted, and the callback still names the class.
    assert not words.calls and not saved and not diarized
    assert failures == [('a', 'ValueError')]
    # The report is the demoted INFO transition — the per-attempt ERROR
    # worker-fault line is gone for this family.
    assert 'event=batch_worker_failed' not in caplog.text
    assert (
        'event=batch_validation_disposition outcome=recovery_handoff error_class=ValueError stage=fetch_decode'
        in caplog.text
    )


def test_the_stale_prepared_decode_race_keeps_the_ladder_outside_the_poison(monkeypatch):
    # FirstDecode.take's stale-attempt guard raises a bare ValueError today,
    # but it has no production caller on the fetch path; the poison arm's
    # contract is the decode/parse family of the pinned bytes. The race
    # class stays a raw ValueError by type — this pins that the guard
    # itself is unchanged and its custody decisions stay at the boundary
    # ordering, not in the guard.
    budget = DecodeBudget(1800)
    unit = item('a', 10)
    handle = FirstDecode(budget, unit, None)
    with pytest.raises(ValueError, match='another attempt'):
        handle.take(replace(unit))
