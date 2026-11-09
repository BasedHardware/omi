# Failure-Class: FC-empty-ladder-recovery-handoff-misclassified-as-worker-fault
"""The flag surface the demoted holds wait behind, pinned defaults and grids.

The lane's admission bounds (``independent_allowed`` at ``MAX_AUDIO_SECONDS``,
``below_silence_threshold``), the wake-lease and dispatch-batch defaults, the
strict-VAD silence threshold rule, and the read-per-call purity of
``empty_ladder_handoff`` (environment reads never leak into its arguments).
"""

import logging
from unittest.mock import Mock

import numpy as np
import pytest

from config.batch_language_recovery import (
    MAX_AUDIO_SECONDS,
    allowed as independent_allowed,
    enabled as independent_enabled,
    below_silence_threshold,
)
from config.batch_pipeline import (
    empty_asr_disposition_enabled,
    empty_asr_recovery_enabled,
    recovery_dispatch_batch_size,
    recovery_policy_refresh_enabled,
    recovery_wake_lease_seconds,
    second_multilingual_enabled,
    worker_silence_disposition_enabled,
    worker_validation_disposition_enabled,
)
from config.batch_pipeline_empty_asr import empty_ladder_handoff, safety_net_enabled, terminal_empty_allowed
from tests.unit.test_batch_pipeline_worker import item, setup_worker


def test_max_audio_seconds_is_the_documented_independent_bound():
    assert MAX_AUDIO_SECONDS == 60.0


def test_independent_enabled_default_is_on():
    assert independent_enabled() is True


def test_independent_allowed_at_half_a_second():
    assert independent_allowed(0.5) is True


def test_independent_allowed_at_thirty_seconds():
    assert independent_allowed(30) is True


def test_independent_allowed_just_under_the_bound():
    assert independent_allowed(59.9) is True


def test_independent_allowed_at_the_bound():
    assert independent_allowed(60.0) is True


def test_independent_allowed_just_over_the_bound():
    assert independent_allowed(60.1) is False


def test_independent_allowed_at_two_minutes():
    assert independent_allowed(120) is False


def test_below_silence_threshold_accepts_zero_measured_speech():
    assert below_silence_threshold(0.0) is True


def test_below_silence_threshold_rejects_five_seconds():
    assert below_silence_threshold(5.0) is False


def test_wake_lease_default_is_positive():
    assert recovery_wake_lease_seconds() > 0


def test_dispatch_batch_default_is_positive():
    assert recovery_dispatch_batch_size() >= 1


def test_policy_refresh_default_is_on():
    assert recovery_policy_refresh_enabled() is True


def test_second_multilingual_default_is_on():
    assert second_multilingual_enabled() is True


def test_recovery_flag_default_is_off():
    assert empty_asr_recovery_enabled() is False


def test_disposition_flag_default_is_off():
    assert empty_asr_disposition_enabled() is False


def test_validation_flag_default_is_on():
    assert worker_validation_disposition_enabled() is True


def test_silence_flag_default_is_off():
    assert worker_silence_disposition_enabled() is False


def test_safety_net_default_is_on():
    assert safety_net_enabled() is True


def test_terminal_empty_requires_no_strict_spans_under_safety_on():
    assert terminal_empty_allowed([]) is True


def test_terminal_empty_refuses_positive_spans_under_safety_on():
    assert terminal_empty_allowed([{"start": 0.0, "end": 1.0}]) is False


def test_terminal_empty_allows_positive_spans_under_safety_off(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "false")
    assert terminal_empty_allowed([{"start": 0.0, "end": 1.0}]) is True


def test_handoff_reads_no_environment_inside_empty_asr_recovery_arg(monkeypatch):
    """Env true + args false must not produce True: flags are arguments, not reads."""
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "false")
    assert (
        empty_ladder_handoff("empty_asr", recovery_enabled=False, disposition_enabled=False, safety_enabled=False)
        is False
    )


def test_handoff_reads_no_environment_inside_no_owned_disposition_arg(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "false")
    assert (
        empty_ladder_handoff("no_owned_words", recovery_enabled=False, disposition_enabled=False, safety_enabled=False)
        is False
    )


def test_handoff_reads_no_environment_inside_empty_asr_safety_arg(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "false")
    assert (
        empty_ladder_handoff("empty_asr", recovery_enabled=False, disposition_enabled=False, safety_enabled=True)
        is True
    )


def test_handoff_reads_no_environment_inside_no_owned_safety_arg(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "true")
    assert (
        empty_ladder_handoff("no_owned_words", recovery_enabled=False, disposition_enabled=False, safety_enabled=False)
        is False
    )


def test_wake_lease_zero_is_the_kill_switch(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_RECOVERY_WAKE_LEASE_SECONDS", "0")
    assert recovery_wake_lease_seconds() == 0


def test_dispatch_batch_env_override(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_RECOVERY_DISPATCH_BATCH_SIZE", "25")
    assert recovery_dispatch_batch_size() == 25


def test_policy_refresh_env_false(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_RECOVERY_POLICY_REFRESH_ENABLED", "false")
    assert recovery_policy_refresh_enabled() is False


def test_second_multilingual_env_false(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_SECOND_MULTILINGUAL_ENABLED", "false")
    assert second_multilingual_enabled() is False


def test_recovery_env_true(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED", "true")
    assert empty_asr_recovery_enabled() is True


def test_disposition_env_true(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED", "true")
    assert empty_asr_disposition_enabled() is True


def test_validation_env_false(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", "false")
    assert worker_validation_disposition_enabled() is False


def test_silence_env_true(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED", "true")
    assert worker_silence_disposition_enabled() is True


def test_safety_env_false(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "false")
    assert safety_net_enabled() is False


def test_validation_env_true(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", "true")
    assert worker_validation_disposition_enabled() is True


def test_silence_env_false(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED", "false")
    assert worker_silence_disposition_enabled() is False


def test_handoff_reads_no_environment_inside_empty_asr_disposition_arg(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED", "false")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "false")
    assert (
        empty_ladder_handoff("empty_asr", recovery_enabled=False, disposition_enabled=True, safety_enabled=False)
        is True
    )


def test_handoff_reads_no_environment_inside_no_owned_safety_arg_true(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "false")
    assert (
        empty_ladder_handoff("no_owned_words", recovery_enabled=False, disposition_enabled=False, safety_enabled=True)
        is True
    )
