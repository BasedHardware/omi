"""The fenced recovery lane keys on the same closed guard code the worker stores.

The redrive hold only helps users if everything downstream of the demoted log line still classifies the unit as language-guarded: lane selection, the independent (Soniox) bounds, the guarded Modulate long lane, the silence threshold, the words-repair eligibility, and the recovery evidence shapes. This suite pins every predicate cell those lanes read, proving the classification change moved severity and nothing else.

Failure-Class: FC-language-guard-redrive-misclassified-as-worker-fault
"""

import hashlib
import math

import pytest

from config import batch_language_recovery as blr
from utils.batch_pipeline.contracts import worker_vad_speech
from config.batch_language_recovery import (
    MAX_AUDIO_SECONDS,
    PROVIDER,
    SILENCE_THRESHOLD_SECONDS,
    allowed,
    below_silence_threshold,
    duration_limited,
    enabled,
    guarded_exhausted,
    independent_attempted,
    inherited_language,
    language_guarded,
    long_recovery_allowed,
    prior_modulate_empty,
    words_repair_eligible,
)


def _guard_job(stage='vad_windows'):
    return {'worker_failure': {'stage': stage, 'reason': 'unsupported_language'}}


def _receipt(uri, duration_seconds, speech_samples):
    return {
        'version': 1,
        'state': 'measured',
        'speech_samples': speech_samples,
        'captured_samples': int(duration_seconds * 16000),
        'sample_rate_hz': 16000,
        'input_uri_sha256': hashlib.sha256(uri.encode()).hexdigest(),
    }


def _repair_job(**overrides):
    job = {
        'worker_failure': {'stage': 'vad_windows', 'reason': 'unsupported_language'},
        'audio_uri': 'gs://bucket/a.enc',
        'duration_seconds': 30.0,
        'worker_vad_receipt': _receipt('gs://bucket/a.enc', 30.0, 48000),
        'recovery': {
            'provider': 'modulate',
            'failure': {'stage': 'payload_validation', 'reason': 'invalid_payload'},
            'recognizers': {
                'modulate': {'outcome': 'words', 'word_count': 3},
                'soniox': {'outcome': 'empty', 'word_count': 0},
            },
        },
    }
    for key, value in overrides.items():
        if value is None:
            job.pop(key, None)
        else:
            job[key] = value
    return job


def test_language_guarded_worker_failure_fetch_decode_is_guarded():
    """A stored guard failure at fetch_decode selects the guarded recovery lane."""
    assert language_guarded(_guard_job("fetch_decode")) is True


def test_language_guarded_worker_failure_vad_windows_is_guarded():
    """A stored guard failure at vad_windows selects the guarded recovery lane."""
    assert language_guarded(_guard_job("vad_windows")) is True


def test_language_guarded_worker_failure_word_clocks_is_guarded():
    """A stored guard failure at word_clocks selects the guarded recovery lane."""
    assert language_guarded(_guard_job("word_clocks")) is True


def test_language_guarded_worker_failure_assemble_words_is_guarded():
    """A stored guard failure at assemble_words selects the guarded recovery lane."""
    assert language_guarded(_guard_job("assemble_words")) is True


def test_language_guarded_worker_failure_asr_recovery_is_guarded():
    """A stored guard failure at asr_recovery selects the guarded recovery lane."""
    assert language_guarded(_guard_job("asr_recovery")) is True


def test_language_guarded_stt_route_provider_reason_is_guarded():
    """The intake flip stamps the same provider reason and drains guarded."""
    assert language_guarded({'stt_route': {'provider_reason': 'unsupported_language'}}) is True


def test_language_guarded_empty_job_is_not_guarded():
    assert language_guarded({}) is False


def test_language_guarded_reason_staged_audio_invalid_is_not_guarded():
    """staged_audio_invalid does not select the guarded lane."""
    assert language_guarded({"worker_failure": {"stage": "vad_windows", "reason": "staged_audio_invalid"}}) is False


def test_language_guarded_reason_retained_audio_invalid_is_not_guarded():
    """retained_audio_invalid does not select the guarded lane."""
    assert language_guarded({"worker_failure": {"stage": "vad_windows", "reason": "retained_audio_invalid"}}) is False


def test_language_guarded_reason_decoded_duration_mismatch_is_not_guarded():
    """decoded_duration_mismatch does not select the guarded lane."""
    assert (
        language_guarded({"worker_failure": {"stage": "vad_windows", "reason": "decoded_duration_mismatch"}}) is False
    )


def test_language_guarded_reason_word_shape_is_not_guarded():
    """word_shape does not select the guarded lane."""
    assert language_guarded({"worker_failure": {"stage": "vad_windows", "reason": "word_shape"}}) is False


def test_language_guarded_reason_word_clock_is_not_guarded():
    """word_clock does not select the guarded lane."""
    assert language_guarded({"worker_failure": {"stage": "vad_windows", "reason": "word_clock"}}) is False


def test_language_guarded_reason_word_sequence_is_not_guarded():
    """word_sequence does not select the guarded lane."""
    assert language_guarded({"worker_failure": {"stage": "vad_windows", "reason": "word_sequence"}}) is False


def test_language_guarded_reason_vad_nonfinite_is_not_guarded():
    """vad_nonfinite does not select the guarded lane."""
    assert language_guarded({"worker_failure": {"stage": "vad_windows", "reason": "vad_nonfinite"}}) is False


def test_language_guarded_reason_vad_order_is_not_guarded():
    """vad_order does not select the guarded lane."""
    assert language_guarded({"worker_failure": {"stage": "vad_windows", "reason": "vad_order"}}) is False


def test_language_guarded_reason_vad_bounds_is_not_guarded():
    """vad_bounds does not select the guarded lane."""
    assert language_guarded({"worker_failure": {"stage": "vad_windows", "reason": "vad_bounds"}}) is False


def test_language_guarded_reason_empty_asr_is_not_guarded():
    """empty_asr does not select the guarded lane."""
    assert language_guarded({"worker_failure": {"stage": "vad_windows", "reason": "empty_asr"}}) is False


def test_language_guarded_reason_no_owned_words_is_not_guarded():
    """no_owned_words does not select the guarded lane."""
    assert language_guarded({"worker_failure": {"stage": "vad_windows", "reason": "no_owned_words"}}) is False


def test_language_guarded_reason_outside_admitted_source_is_not_guarded():
    """outside_admitted_source does not select the guarded lane."""
    assert language_guarded({"worker_failure": {"stage": "vad_windows", "reason": "outside_admitted_source"}}) is False


def test_language_guarded_stt_route_other_reason_is_not_guarded():
    assert language_guarded({'stt_route': {'provider_reason': 'byok'}}) is False


def test_language_guarded_none_worker_failure_is_not_guarded():
    assert language_guarded({'worker_failure': None}) is False


def test_language_guarded_malformed_worker_failure_str_raises():
    """The lane selector assumes the stored closed shape; truthy garbage raises."""
    with pytest.raises(AttributeError):
        language_guarded({"worker_failure": "x"})


def test_language_guarded_malformed_worker_failure_int_raises():
    """The lane selector assumes the stored closed shape; truthy garbage raises."""
    with pytest.raises(AttributeError):
        language_guarded({"worker_failure": 42})


def test_language_guarded_stt_route_guard_overrides_reason_staged_audio_invalid():
    """A flipped stt_route keeps the unit guarded even beside staged_audio_invalid."""
    job = {"worker_failure": {"stage": "vad_windows", "reason": "staged_audio_invalid"}}
    job['stt_route'] = {'provider_reason': 'unsupported_language'}
    assert language_guarded(job) is True


def test_language_guarded_stt_route_guard_overrides_reason_retained_audio_invalid():
    """A flipped stt_route keeps the unit guarded even beside retained_audio_invalid."""
    job = {"worker_failure": {"stage": "vad_windows", "reason": "retained_audio_invalid"}}
    job['stt_route'] = {'provider_reason': 'unsupported_language'}
    assert language_guarded(job) is True


def test_language_guarded_stt_route_guard_overrides_reason_decoded_duration_mismatch():
    """A flipped stt_route keeps the unit guarded even beside decoded_duration_mismatch."""
    job = {"worker_failure": {"stage": "vad_windows", "reason": "decoded_duration_mismatch"}}
    job['stt_route'] = {'provider_reason': 'unsupported_language'}
    assert language_guarded(job) is True


def test_language_guarded_stt_route_guard_overrides_reason_word_shape():
    """A flipped stt_route keeps the unit guarded even beside word_shape."""
    job = {"worker_failure": {"stage": "vad_windows", "reason": "word_shape"}}
    job['stt_route'] = {'provider_reason': 'unsupported_language'}
    assert language_guarded(job) is True


def test_language_guarded_stt_route_guard_overrides_reason_word_clock():
    """A flipped stt_route keeps the unit guarded even beside word_clock."""
    job = {"worker_failure": {"stage": "vad_windows", "reason": "word_clock"}}
    job['stt_route'] = {'provider_reason': 'unsupported_language'}
    assert language_guarded(job) is True


def test_language_guarded_stt_route_guard_overrides_reason_word_sequence():
    """A flipped stt_route keeps the unit guarded even beside word_sequence."""
    job = {"worker_failure": {"stage": "vad_windows", "reason": "word_sequence"}}
    job['stt_route'] = {'provider_reason': 'unsupported_language'}
    assert language_guarded(job) is True


def test_language_guarded_stt_route_guard_overrides_reason_vad_nonfinite():
    """A flipped stt_route keeps the unit guarded even beside vad_nonfinite."""
    job = {"worker_failure": {"stage": "vad_windows", "reason": "vad_nonfinite"}}
    job['stt_route'] = {'provider_reason': 'unsupported_language'}
    assert language_guarded(job) is True


def test_language_guarded_stt_route_guard_overrides_reason_vad_order():
    """A flipped stt_route keeps the unit guarded even beside vad_order."""
    job = {"worker_failure": {"stage": "vad_windows", "reason": "vad_order"}}
    job['stt_route'] = {'provider_reason': 'unsupported_language'}
    assert language_guarded(job) is True


def test_language_guarded_stt_route_guard_overrides_reason_vad_bounds():
    """A flipped stt_route keeps the unit guarded even beside vad_bounds."""
    job = {"worker_failure": {"stage": "vad_windows", "reason": "vad_bounds"}}
    job['stt_route'] = {'provider_reason': 'unsupported_language'}
    assert language_guarded(job) is True


def test_language_guarded_stt_route_guard_overrides_reason_empty_asr():
    """A flipped stt_route keeps the unit guarded even beside empty_asr."""
    job = {"worker_failure": {"stage": "vad_windows", "reason": "empty_asr"}}
    job['stt_route'] = {'provider_reason': 'unsupported_language'}
    assert language_guarded(job) is True


def test_language_guarded_stt_route_guard_overrides_reason_no_owned_words():
    """A flipped stt_route keeps the unit guarded even beside no_owned_words."""
    job = {"worker_failure": {"stage": "vad_windows", "reason": "no_owned_words"}}
    job['stt_route'] = {'provider_reason': 'unsupported_language'}
    assert language_guarded(job) is True


def test_language_guarded_stt_route_guard_overrides_reason_outside_admitted_source():
    """A flipped stt_route keeps the unit guarded even beside outside_admitted_source."""
    job = {"worker_failure": {"stage": "vad_windows", "reason": "outside_admitted_source"}}
    job['stt_route'] = {'provider_reason': 'unsupported_language'}
    assert language_guarded(job) is True


def test_language_guarded_worker_failure_guard_overrides_stt_route():
    job = {
        'stt_route': {'provider_reason': 'byok'},
        'worker_failure': {'stage': 'vad_windows', 'reason': 'unsupported_language'},
    }
    assert language_guarded(job) is True


def test_independent_allowed_0_001_is_True():
    """The independent Soniox bound at 0.001s."""
    assert allowed(0.001) is True


def test_independent_allowed_1_is_True():
    """The independent Soniox bound at 1s."""
    assert allowed(1) is True


def test_independent_allowed_30_is_True():
    """The independent Soniox bound at 30s."""
    assert allowed(30) is True


def test_independent_allowed_59_999_is_True():
    """The independent Soniox bound at 59.999s."""
    assert allowed(59.999) is True


def test_independent_allowed_60_is_True():
    """The independent Soniox bound at 60s."""
    assert allowed(60) is True


def test_independent_allowed_60_001_is_False():
    """The independent Soniox bound at 60.001s."""
    assert allowed(60.001) is False


def test_independent_allowed_0_is_False():
    """The independent Soniox bound at 0s."""
    assert allowed(0) is False


def test_independent_allowed__1_is_False():
    """The independent Soniox bound at -1s."""
    assert allowed(-1) is False


def test_independent_allowed_float__inf___is_False():
    """The independent Soniox bound at infs."""
    assert allowed(float("inf")) is False


def test_independent_allowed_float__nan___is_False():
    """The independent Soniox bound at nans."""
    assert allowed(float("nan")) is False


def test_independent_cap_env_30_probe_30_is_True(monkeypatch):
    """A scoped operator cap of 30s can only lower the 60s ceiling."""
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_RECOVERY_MAX_SECONDS', '30')
    assert allowed(30) is True


def test_independent_cap_env_30_probe_45_is_False(monkeypatch):
    """A scoped operator cap of 30s can only lower the 60s ceiling."""
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_RECOVERY_MAX_SECONDS', '30')
    assert allowed(45) is False


def test_independent_cap_env_120_probe_61_is_False(monkeypatch):
    """A scoped operator cap of 120s can only lower the 60s ceiling."""
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_RECOVERY_MAX_SECONDS', '120')
    assert allowed(61) is False


def test_independent_cap_env_120_probe_45_is_True(monkeypatch):
    """A scoped operator cap of 120s can only lower the 60s ceiling."""
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_RECOVERY_MAX_SECONDS', '120')
    assert allowed(45) is True


def test_independent_cap_env_abc_probe_30_is_False(monkeypatch):
    """A scoped operator cap of abcs can only lower the 60s ceiling."""
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_RECOVERY_MAX_SECONDS', 'abc')
    assert allowed(30) is False


def test_independent_disabled_holds_30s(monkeypatch):
    """The kill switch holds every independent attempt."""
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'false')
    assert allowed(30) is False


def test_independent_disabled_holds_60s(monkeypatch):
    """The kill switch holds every independent attempt."""
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'false')
    assert allowed(60) is False


def test_long_recovery_default_cap_holds_61s():
    """No guarded Modulate long lane without an explicit operator cap."""
    assert long_recovery_allowed(61) is False


def test_long_recovery_default_cap_holds_3600s():
    """No guarded Modulate long lane without an explicit operator cap."""
    assert long_recovery_allowed(3600) is False


def test_long_recovery_cap_3600_60_1_is_True(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_GUARDED_LONG_RECOVERY_MAX_SECONDS', '3600')
    assert long_recovery_allowed(60.1) is True


def test_long_recovery_cap_3600_3600_is_True(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_GUARDED_LONG_RECOVERY_MAX_SECONDS', '3600')
    assert long_recovery_allowed(3600) is True


def test_long_recovery_cap_3600_3601_is_False(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_GUARDED_LONG_RECOVERY_MAX_SECONDS', '3600')
    assert long_recovery_allowed(3601) is False


def test_long_recovery_cap_3600_7200_is_False(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_GUARDED_LONG_RECOVERY_MAX_SECONDS', '3600')
    assert long_recovery_allowed(7200) is False


def test_long_recovery_cap_3600_7201_is_False(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_GUARDED_LONG_RECOVERY_MAX_SECONDS', '3600')
    assert long_recovery_allowed(7201) is False


def test_long_recovery_cap_100_60_is_False(monkeypatch):
    """The long lane starts above the independent ceiling, never below it."""
    monkeypatch.setenv('BATCH_PIPELINE_GUARDED_LONG_RECOVERY_MAX_SECONDS', '100')
    assert long_recovery_allowed(60) is False


def test_long_recovery_cap_100_60_1_is_True(monkeypatch):
    """The long lane starts above the independent ceiling, never below it."""
    monkeypatch.setenv('BATCH_PIPELINE_GUARDED_LONG_RECOVERY_MAX_SECONDS', '100')
    assert long_recovery_allowed(60.1) is True


def test_long_recovery_cap_100_100_is_True(monkeypatch):
    """The long lane starts above the independent ceiling, never below it."""
    monkeypatch.setenv('BATCH_PIPELINE_GUARDED_LONG_RECOVERY_MAX_SECONDS', '100')
    assert long_recovery_allowed(100) is True


def test_long_recovery_cap_100_100_1_is_False(monkeypatch):
    """The long lane starts above the independent ceiling, never below it."""
    monkeypatch.setenv('BATCH_PIPELINE_GUARDED_LONG_RECOVERY_MAX_SECONDS', '100')
    assert long_recovery_allowed(100.1) is False


def test_long_recovery_disabled_holds(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_GUARDED_LONG_RECOVERY_MAX_SECONDS', '3600')
    assert long_recovery_allowed(100) is False


def test_below_silence_0_is_True():
    """Silero-frame threshold at 0s."""
    assert below_silence_threshold(0) is True


def test_below_silence_0_01_is_True():
    """Silero-frame threshold at 0.01s."""
    assert below_silence_threshold(0.01) is True


def test_below_silence_0_031_is_True():
    """Silero-frame threshold at 0.031s."""
    assert below_silence_threshold(0.031) is True


def test_below_silence_0_0319999_is_False():
    """Silero-frame threshold at 0.0319999s."""
    assert below_silence_threshold(0.0319999) is False


def test_below_silence_0_032_is_False():
    """Silero-frame threshold at 0.032s."""
    assert below_silence_threshold(0.032) is False


def test_below_silence_0_0320001_is_False():
    """Silero-frame threshold at 0.0320001s."""
    assert below_silence_threshold(0.0320001) is False


def test_below_silence_1_is_False():
    """Silero-frame threshold at 1s."""
    assert below_silence_threshold(1) is False


def test_below_silence_neg0_01_is_False():
    """Silero-frame threshold at -0.01s."""
    assert below_silence_threshold(-0.01) is False


def test_below_silence_float__inf___is_False():
    """Silero-frame threshold at infs."""
    assert below_silence_threshold(float("inf")) is False


def test_below_silence_float__nan___is_False():
    """Silero-frame threshold at nans."""
    assert below_silence_threshold(float("nan")) is False


def test_words_repair_eligible_valid_guarded_job():
    assert words_repair_eligible(_repair_job()) is True


def test_words_repair_ineligible_non_guard_reason():
    """The repair lane refuses the non_guard_reason shape."""
    assert (
        words_repair_eligible(_repair_job(**{'worker_failure': {'stage': 'vad_windows', 'reason': 'empty_asr'}}))
        is False
    )


def test_words_repair_ineligible_provider_soniox():
    """The repair lane refuses the provider_soniox shape."""
    assert words_repair_eligible(_repair_job(**{'recovery': {'provider': 'soniox'}})) is False


def test_words_repair_ineligible_failure_mismatch():
    """The repair lane refuses the failure_mismatch shape."""
    assert (
        words_repair_eligible(
            _repair_job(
                **{'recovery': {'provider': 'modulate', 'failure': {'stage': 'provider', 'reason': 'provider_failed'}}}
            )
        )
        is False
    )


def test_words_repair_ineligible_failure_missing():
    """The repair lane refuses the failure_missing shape."""
    assert words_repair_eligible(_repair_job(**{'recovery': {'provider': 'modulate'}})) is False


def test_words_repair_ineligible_modulate_outcome_empty():
    """The repair lane refuses the modulate_outcome_empty shape."""
    assert (
        words_repair_eligible(
            _repair_job(
                **{
                    'recovery': {
                        'provider': 'modulate',
                        'failure': {'stage': 'payload_validation', 'reason': 'invalid_payload'},
                        'recognizers': {
                            'modulate': {'outcome': 'empty', 'word_count': 0},
                            'soniox': {'outcome': 'empty', 'word_count': 0},
                        },
                    }
                }
            )
        )
        is False
    )


def test_words_repair_ineligible_modulate_word_count_zero():
    """The repair lane refuses the modulate_word_count_zero shape."""
    assert (
        words_repair_eligible(
            _repair_job(
                **{
                    'recovery': {
                        'provider': 'modulate',
                        'failure': {'stage': 'payload_validation', 'reason': 'invalid_payload'},
                        'recognizers': {
                            'modulate': {'outcome': 'words', 'word_count': 0},
                            'soniox': {'outcome': 'empty', 'word_count': 0},
                        },
                    }
                }
            )
        )
        is False
    )


def test_words_repair_ineligible_modulate_word_count_str():
    """The repair lane refuses the modulate_word_count_str shape."""
    assert (
        words_repair_eligible(
            _repair_job(
                **{
                    'recovery': {
                        'provider': 'modulate',
                        'failure': {'stage': 'payload_validation', 'reason': 'invalid_payload'},
                        'recognizers': {
                            'modulate': {'outcome': 'words', 'word_count': '3'},
                            'soniox': {'outcome': 'empty', 'word_count': 0},
                        },
                    }
                }
            )
        )
        is False
    )


def test_words_repair_ineligible_soniox_outcome_error():
    """The repair lane refuses the soniox_outcome_error shape."""
    assert (
        words_repair_eligible(
            _repair_job(
                **{
                    'recovery': {
                        'provider': 'modulate',
                        'failure': {'stage': 'payload_validation', 'reason': 'invalid_payload'},
                        'recognizers': {
                            'modulate': {'outcome': 'words', 'word_count': 3},
                            'soniox': {'outcome': 'error', 'word_count': 0},
                        },
                    }
                }
            )
        )
        is False
    )


def test_words_repair_ineligible_soniox_words_zero_count():
    """The repair lane refuses the soniox_words_zero_count shape."""
    assert (
        words_repair_eligible(
            _repair_job(
                **{
                    'recovery': {
                        'provider': 'modulate',
                        'failure': {'stage': 'payload_validation', 'reason': 'invalid_payload'},
                        'recognizers': {
                            'modulate': {'outcome': 'words', 'word_count': 3},
                            'soniox': {'outcome': 'words', 'word_count': 0},
                        },
                    }
                }
            )
        )
        is False
    )


def test_words_repair_ineligible_audio_uri_int():
    """The repair lane refuses the audio_uri_int shape."""
    assert words_repair_eligible(_repair_job(**{'audio_uri': 42})) is False


def test_words_repair_ineligible_duration_zero():
    """The repair lane refuses the duration_zero shape."""
    assert words_repair_eligible(_repair_job(**{'duration_seconds': 0})) is False


def test_words_repair_ineligible_duration_over_max():
    """The repair lane refuses the duration_over_max shape."""
    assert words_repair_eligible(_repair_job(**{'duration_seconds': 61})) is False


def test_words_repair_ineligible_duration_string():
    """The repair lane refuses the duration_string shape."""
    assert words_repair_eligible(_repair_job(**{'duration_seconds': '30'})) is False


def test_words_repair_ineligible_receipt_unbound():
    """The repair lane refuses the receipt_unbound shape."""
    assert (
        words_repair_eligible(_repair_job(**{'worker_vad_receipt': _receipt('gs://bucket/other.enc', 30.0, 48000)}))
        is False
    )


def test_words_repair_ineligible_receipt_speech_over_captured():
    """The repair lane refuses the receipt_speech_over_captured shape."""
    assert (
        words_repair_eligible(_repair_job(**{'worker_vad_receipt': _receipt('gs://bucket/a.enc', 30.0, 999999999)}))
        is False
    )


def test_words_repair_ineligible_receipt_missing():
    """The repair lane refuses the receipt_missing shape."""
    assert words_repair_eligible(_repair_job(**{'worker_vad_receipt': None})) is False


def test_words_repair_ineligible_audio_uri_missing():
    """The repair lane refuses the audio_uri_missing shape."""
    assert words_repair_eligible(_repair_job(**{'audio_uri': None})) is False


def test_words_repair_ineligible_duration_missing():
    """The repair lane refuses the duration_missing shape."""
    assert words_repair_eligible(_repair_job(**{'duration_seconds': None})) is False


def test_words_repair_eligible_soniox_words_variant():
    """A validated Soniox words answer also admits the repair."""
    job = _repair_job()
    job['recovery']['recognizers']['soniox'] = {'outcome': 'words', 'word_count': 2}
    assert words_repair_eligible(job) is True


def test_words_repair_eligible_at_the_exact_independent_ceiling():
    job = _repair_job(duration_seconds=60.0, worker_vad_receipt=_receipt('gs://bucket/a.enc', 60.0, 48000))
    assert words_repair_eligible(job) is True


def test_words_repair_ineligible_just_over_the_ceiling():
    job = _repair_job(duration_seconds=60.0001, worker_vad_receipt=_receipt('gs://bucket/a.enc', 60.0001, 48000))
    assert words_repair_eligible(job) is False


def test_words_repair_ineligible_sub_frame_worker_speech():
    """A sub-frame receipt proves no speech; the repair lane stays shut."""
    job = _repair_job(worker_vad_receipt=_receipt('gs://bucket/a.enc', 30.0, 100))
    assert words_repair_eligible(job) is False


def test_prior_modulate_empty_receipt_shape():
    job = {'recovery': {'provider': 'modulate', 'recognizers': {'modulate': {'outcome': 'empty', 'word_count': 0}}}}
    assert prior_modulate_empty(job) is True


def test_prior_modulate_empty_historical_failure_shape():
    job = {'recovery': {'provider': 'modulate', 'failure': {'stage': 'response_validation', 'reason': 'empty_asr'}}}
    assert prior_modulate_empty(job) is True


def test_prior_modulate_empty_soniox_provider_skipped():
    job = {'recovery': {'provider': 'soniox', 'recognizers': {'modulate': {'outcome': 'empty', 'word_count': 0}}}}
    assert prior_modulate_empty(job) is False


def test_prior_modulate_empty_words_receipt_is_not_empty():
    job = {'recovery': {'provider': 'modulate', 'recognizers': {'modulate': {'outcome': 'words', 'word_count': 2}}}}
    assert prior_modulate_empty(job) is False


def test_prior_modulate_empty_plain_job_is_false():
    assert prior_modulate_empty({}) is False


def test_prior_modulate_empty_paid_marker_falls_through():
    job = {
        'speech_redrive': {
            'provider': 'soniox',
            'prior_speech_redrive': {
                'provider': 'modulate',
                'recognizers': {'modulate': {'outcome': 'empty', 'word_count': 0}},
            },
        }
    }
    assert prior_modulate_empty(job) is True


def test_independent_attempted_outcome_started_is_true():
    job = {'recovery': {'recognizers': {'soniox': {'outcome': 'started'}}}}
    assert independent_attempted(job) is True


def test_independent_attempted_outcome_words_is_true():
    job = {'recovery': {'recognizers': {'soniox': {'outcome': 'words'}}}}
    assert independent_attempted(job) is True


def test_independent_attempted_outcome_empty_is_true():
    job = {'recovery': {'recognizers': {'soniox': {'outcome': 'empty'}}}}
    assert independent_attempted(job) is True


def test_independent_attempted_outcome_error_is_true():
    job = {'recovery': {'recognizers': {'soniox': {'outcome': 'error'}}}}
    assert independent_attempted(job) is True


def test_independent_attempted_missing_is_false():
    assert independent_attempted({}) is False


def test_independent_attempted_refused_is_false():
    job = {'recovery': {'recognizers': {'soniox': {'outcome': 'refused'}}}}
    assert independent_attempted(job) is False


def test_guarded_exhausted_both_empty():
    job = {
        'recovery': {
            'recognizers': {
                'modulate': {'outcome': 'empty', 'word_count': 0},
                'soniox': {'outcome': 'empty', 'word_count': 0},
            }
        }
    }
    assert guarded_exhausted(job) is True


def test_guarded_exhausted_soniox_error_is_not_exhausted():
    job = {
        'recovery': {
            'recognizers': {
                'modulate': {'outcome': 'empty', 'word_count': 0},
                'soniox': {'outcome': 'error', 'word_count': 0},
            }
        }
    }
    assert guarded_exhausted(job) is False


def test_guarded_exhausted_modulate_words_is_not_exhausted():
    job = {
        'recovery': {
            'recognizers': {
                'modulate': {'outcome': 'words', 'word_count': 2},
                'soniox': {'outcome': 'empty', 'word_count': 0},
            }
        }
    }
    assert guarded_exhausted(job) is False


def test_duration_limited_exact_shape():
    """The #23795 hold shape reopens only for the operator take-over."""
    job = {
        'recovery_state': 'failed_held',
        'recovery': {'refusal': {'reason': 'independent_duration_limit', 'max_audio_seconds': MAX_AUDIO_SECONDS}},
    }
    assert duration_limited(job) is True


def test_duration_limited_refuses_started():
    assert (
        duration_limited(
            {
                'recovery_state': 'failed_held',
                'recovery': {
                    'refusal': {'reason': 'independent_duration_limit', 'max_audio_seconds': MAX_AUDIO_SECONDS},
                    'started_at': 5,
                },
            }
        )
        is False
    )


def test_duration_limited_refuses_recognizers():
    assert (
        duration_limited(
            {
                'recovery_state': 'failed_held',
                'recovery': {
                    'refusal': {'reason': 'independent_duration_limit', 'max_audio_seconds': MAX_AUDIO_SECONDS},
                    'recognizers': {'modulate': {'outcome': 'started'}},
                },
            }
        )
        is False
    )


def test_duration_limited_refuses_wrong_reason():
    assert (
        duration_limited(
            {
                'recovery_state': 'failed_held',
                'recovery': {'refusal': {'reason': 'other', 'max_audio_seconds': MAX_AUDIO_SECONDS}},
            }
        )
        is False
    )


def test_duration_limited_refuses_wrong_max():
    assert (
        duration_limited(
            {
                'recovery_state': 'failed_held',
                'recovery': {'refusal': {'reason': 'independent_duration_limit', 'max_audio_seconds': 30}},
            }
        )
        is False
    )


def test_duration_limited_refuses_wrong_state():
    assert (
        duration_limited(
            {
                'recovery_state': 'running',
                'recovery': {
                    'refusal': {'reason': 'independent_duration_limit', 'max_audio_seconds': MAX_AUDIO_SECONDS}
                },
            }
        )
        is False
    )


def test_inherited_language_en_en_is_en():
    """Inheritance prefers a bound declaration; unknown codes are not declarations."""
    assert inherited_language('en', 'en') == 'en'


def test_inherited_language_en_none_is_en():
    """Inheritance prefers a bound declaration; unknown codes are not declarations."""
    assert inherited_language('en', None) == 'en'


def test_inherited_language_none_en_is_en():
    """Inheritance prefers a bound declaration; unknown codes are not declarations."""
    assert inherited_language(None, 'en') == 'en'


def test_inherited_language_multi_en_is_en():
    """Inheritance prefers a bound declaration; unknown codes are not declarations."""
    assert inherited_language('multi', 'en') == 'en'


def test_inherited_language_en_multi_is_en():
    """Inheritance prefers a bound declaration; unknown codes are not declarations."""
    assert inherited_language('en', 'multi') == 'en'


def test_inherited_language_und_und_is_none():
    """Inheritance prefers a bound declaration; unknown codes are not declarations."""
    assert inherited_language('und', 'und') == None


def test_inherited_language_none_none_is_none():
    """Inheritance prefers a bound declaration; unknown codes are not declarations."""
    assert inherited_language(None, None) == None


def test_inherited_language_zz_en_is_en():
    """Inheritance prefers a bound declaration; unknown codes are not declarations."""
    assert inherited_language('zz', 'en') == 'en'


def test_inherited_language_en_zz_is_en():
    """Inheritance prefers a bound declaration; unknown codes are not declarations."""
    assert inherited_language('en', 'zz') == 'en'


def test_worker_vad_speech_full_frame_receipt():
    job = {'audio_uri': 'gs://b/a', 'duration_seconds': 30.0, 'worker_vad_receipt': _receipt('gs://b/a', 30.0, 48000)}
    assert worker_vad_speech(job) == 3.0


def test_worker_vad_speech_zero_samples_is_none():
    job = {'audio_uri': 'gs://b/a', 'duration_seconds': 30.0, 'worker_vad_receipt': _receipt('gs://b/a', 30.0, 0)}
    assert worker_vad_speech(job) is None


def test_worker_vad_speech_sub_frame_samples_is_none():
    job = {'audio_uri': 'gs://b/a', 'duration_seconds': 30.0, 'worker_vad_receipt': _receipt('gs://b/a', 30.0, 160)}
    assert worker_vad_speech(job) is None


def test_worker_vad_speech_unbound_receipt_is_none():
    job = {
        'audio_uri': 'gs://b/a',
        'duration_seconds': 30.0,
        'worker_vad_receipt': _receipt('gs://b/other', 30.0, 48000),
    }
    assert worker_vad_speech(job) is None


def test_language_guard_empty_evidence_shape():
    """The recovery lane names the guard disposition with its two recognizer receipts."""
    from utils.batch_pipeline.recovery_disposition import LANGUAGE_GUARD_EMPTY_EVIDENCE

    assert LANGUAGE_GUARD_EMPTY_EVIDENCE == {
        'gpu_language_guard': 'unsupported_language',
        'multilingual_recovery': 'empty',
        'second_multilingual_recovery': 'empty',
    }


def test_two_provider_empty_evidence_shape():
    from utils.batch_pipeline.recovery_disposition import TWO_PROVIDER_EMPTY_EVIDENCE

    assert TWO_PROVIDER_EMPTY_EVIDENCE == {
        'gpu_padded_retry': 'skipped_long_speech',
        'multilingual_recovery': 'empty',
        'second_multilingual_recovery': 'empty',
    }


def test_second_chance_empty_evidence_shape():
    from utils.batch_pipeline.recovery_disposition import SECOND_CHANCE_EMPTY_EVIDENCE

    assert SECOND_CHANCE_EMPTY_EVIDENCE == {'multilingual_recovery': 'empty', 'second_multilingual_recovery': 'empty'}


def test_recovery_provider_is_soniox():
    assert PROVIDER == "soniox"


def test_max_audio_seconds_is_60():
    assert MAX_AUDIO_SECONDS == 60.0


def test_silence_threshold_is_one_silero_frame():
    assert SILENCE_THRESHOLD_SECONDS == 0.032


def test_repair_epoch_is_4():
    assert blr.REPAIR_EPOCH == 4


def test_repair_provider_is_modulate():
    assert blr.REPAIR_PROVIDER == "modulate"
