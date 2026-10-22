"""Hermetic regression coverage for shared parser and cohort migrations."""

import hashlib
import importlib
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest


from config import refactor_modes
from config.policy.batch import cohort_bucket
from config.refactor_switches import default_off, default_on


@pytest.mark.parametrize('mode,expected', [('shadow', False), ('serve', True)])
def test_legacy_messaging_switch_uses_shared_opt_in_only_when_serving(monkeypatch, mode, expected):
    from config.messaging import channel_policy

    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    monkeypatch.setenv('OMI_MESSAGING_CHANNELS', 'true')
    monkeypatch.delenv('OMI_MESSAGING_CHANNEL_POLICY', raising=False)
    assert channel_policy('telegram')['enabled'] is expected


@pytest.fixture(autouse=True)
def clean_mode(monkeypatch):
    for key in (
        'CAPTURE_COVERAGE_MODE',
        'CAPTURE_COVERAGE_MODE_SERVE_PERCENT',
        'CAPTURE_COVERAGE_MODE_SERVE_UID_SHA256S',
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize('mode', ['off', 'shadow', 'invalid'])
@pytest.mark.parametrize('legacy', [True, False])
@pytest.mark.parametrize('raw', ['', 'false', 'true', 'on', 'no', 'FLASE'])
def test_shadow_and_off_preserve_legacy_parser_exactly(monkeypatch, mode, legacy, raw):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    monkeypatch.setenv('SYNTHETIC_SWITCH', raw)
    assert default_on('SYNTHETIC_SWITCH', legacy) is legacy
    assert default_off('SYNTHETIC_SWITCH', legacy) is legacy


@pytest.mark.parametrize('raw', ['', 'true', 'TRUE', 'on', '1', 'yes', 'false', 'off', '0', 'no', 'FLASE'])
def test_serve_uses_shared_token_grammar_with_hermetic_environment(raw):
    env = {'CAPTURE_COVERAGE_MODE': 'serve', 'SYNTHETIC_SWITCH': raw}
    assert default_on('SYNTHETIC_SWITCH', False, environ=env) == refactor_modes.default_on(
        'SYNTHETIC_SWITCH', environ=env
    )
    assert default_off('SYNTHETIC_SWITCH', True, environ=env) == refactor_modes.default_off(
        'SYNTHETIC_SWITCH', environ=env
    )


def test_only_admitted_identity_migrates_in_shadow():
    identity = 'synthetic-' + str(1)
    env = {
        'CAPTURE_COVERAGE_MODE': 'shadow',
        'CAPTURE_COVERAGE_MODE_SERVE_UID_SHA256S': refactor_modes.uid_digest(identity),
    }
    assert default_on('SYNTHETIC_SWITCH', False, uid=identity, environ=env)
    assert not default_on('SYNTHETIC_SWITCH', False, uid='synthetic-' + str(2), environ=env)
    assert not default_on('SYNTHETIC_SWITCH', False, environ=env)


DEFAULT_ON_READERS = [
    ('action_item_identity', 'action_item_identity_preserve_enabled', 'ACTION_ITEM_IDENTITY_PRESERVE_ENABLED'),
    ('action_item_identity', 'action_item_refresh_preserve_enabled', 'ACTION_ITEM_REFRESH_PRESERVE_ENABLED'),
    ('audio_timeline', 'live_speaker_capture_clock_enabled', 'LIVE_SPEAKER_CAPTURE_CLOCK'),
    ('batch_pipeline', 'fresh_gpu_priority_enabled', 'BATCH_PIPELINE_FRESH_GPU_PRIORITY_ENABLED'),
    ('batch_pipeline', 'long_speech_handoff_enabled', 'BATCH_PIPELINE_LONG_SPEECH_HANDOFF_ENABLED'),
    ('batch_pipeline', 'second_multilingual_enabled', 'BATCH_PIPELINE_SECOND_MULTILINGUAL_ENABLED'),
    ('batch_pipeline', 'worker_validation_disposition_enabled', 'BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED'),
    ('batch_pipeline_gpu_skip', 'diarize_speech_only_enabled', 'BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED'),
    ('live_stt_replay', 'nonwindow_replay_settle_enabled', 'LISTEN_NONWINDOW_REPLAY_SETTLE_ENABLED'),
    ('live_stt_resilience', 'drain_death_censor_enabled', 'LISTEN_STT_DRAIN_DEATH_CENSOR_ENABLED'),
    ('sync_lineage', 'sync_lineage_resolve_enabled', 'SYNC_LINEAGE_RESOLVE_ENABLED'),
    ('sync_live_dedupe', 'sync_live_dedupe_enabled', 'SYNC_LINEAGE_LIVE_DEDUPE_ENABLED'),
    ('sync_audio_coverage', 'sync_wal_audio_coverage_enabled', 'SYNC_WAL_AUDIO_COVERAGE_ENABLED'),
    ('sync_finalize', 'sync_finalize_target_recovery_enabled', 'SYNC_FINALIZE_TARGET_RECOVERY_ENABLED'),
    ('episodes', 'episodes_enabled', 'EPISODES_ENABLED'),
    ('conversation_smart_merge', 'smart_merge_audit_enabled', 'CONVERSATION_SMART_MERGE_AUDIT_ENABLED'),
]


@pytest.mark.parametrize('module,function,key', DEFAULT_ON_READERS)
@pytest.mark.parametrize(
    'raw,expected', [('on', True), ('TRUE', True), ('false', False), ('no', False), ('FLASE', True)]
)
def test_default_on_call_sites_use_central_parser(monkeypatch, module, function, key, raw, expected):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.setenv(key, raw)
    assert getattr(importlib.import_module('config.' + module), function)() is expected


@pytest.mark.parametrize('token', ['on', 'true', 'TRUE', '1', 'yes'])
def test_owner_concurrency_accepts_on_tokens_only_after_migration(monkeypatch, token):
    from config.sync_owner_concurrency import preparation_width

    monkeypatch.setenv('SYNC_BACKFILL_OWNER_CONCURRENCY_ENABLED', token)
    monkeypatch.setenv('SYNC_BACKFILL_OWNER_CONCURRENCY', '3')
    assert preparation_width() == (3 if token == 'on' else 1)
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    assert preparation_width() == 3
    monkeypatch.setenv('SYNC_BACKFILL_OWNER_CONCURRENCY_ENABLED', 'no')
    assert preparation_width() == 1


@pytest.mark.parametrize(
    'key,function',
    [
        ('SYNC_REPROCESS_COALESCE_ENABLED', 'coalesce_enabled'),
        ('CONVERSATION_LLM_INPUT_DEDUPE_ENABLED', 'dedupe_enabled'),
    ],
)
@pytest.mark.parametrize('token', ['false', 'off', '0', 'no', '', 'invalid'])
def test_explicit_child_disable_wins_over_repeat_work_in_serve(monkeypatch, key, function, token):
    from config import sync_reprocess

    monkeypatch.setenv('REPEAT_WORK_REVISION_ENABLED', 'true')
    monkeypatch.setenv(key, token)
    assert getattr(sync_reprocess, function)()  # exact legacy inheritance in shadow
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    assert not getattr(sync_reprocess, function)()
    monkeypatch.delenv(key)
    assert getattr(sync_reprocess, function)()


def test_backfill_default_zero_is_gated_and_allowlist_still_wins(monkeypatch):
    from utils.sync.backfill_order import newest_first

    identity = 'synthetic-' + str(7)
    monkeypatch.setenv('SYNC_BACKFILL_ORDER', 'newest')
    monkeypatch.delenv('SYNC_BACKFILL_ORDER_PERCENT', raising=False)
    monkeypatch.delenv('SYNC_BACKFILL_ORDER_UID_ALLOWLIST', raising=False)
    assert newest_first(identity)
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    assert not newest_first(identity)
    monkeypatch.setenv('SYNC_BACKFILL_ORDER_UID_ALLOWLIST', identity)
    assert newest_first(identity)
    monkeypatch.setenv('SYNC_BACKFILL_ORDER_PERCENT', '100')
    assert newest_first('synthetic-' + str(8))


RECIPES = [
    ('audio-archive', 64, 'fraction', ':', False),
    ('batch-pipeline-shadow', 32, 'fraction', ':', False),
    ('capture_shared_speech_v1', 64, 'fraction', ':', False),
    ('', 32, 'modulo', ':', False),  # demand processing
    ('dream-agent-paid', 32, 'modulo', ':', False),
    ('listen_poll', 64, 'modulo', ':', False),  # Firestore lever name is the salt
    ('relevance-arm-v2', 64, 'fraction', '\0', True),
    ('live-demand', 64, 'fraction', ':', False),
    ('free-tier-cohort', 32, 'modulo', ':', False),
    ('', 32, 'fraction', ':', False),  # batch, final pass, backfill order
]


@pytest.mark.parametrize('salt,bits,formula,separator,clamp', RECIPES)
def test_deployed_cohort_samples_preserve_legacy_assignments(salt, bits, formula, separator, clamp):
    for sample in range(512):
        identity = 'synthetic-' + str(sample)
        payload = f'{salt}{separator}{identity}' if salt else identity
        integer = int.from_bytes(hashlib.sha256(payload.encode()).digest()[: bits // 8], 'big')
        legacy = integer % 100 if formula == 'modulo' else integer / 2**bits * 100
        if clamp:
            legacy = min(legacy, math.nextafter(100.0, 0.0))
        assert (
            cohort_bucket(identity, salt, bits=bits, formula=formula, separator=separator, clamp_upper=clamp) == legacy
        )


def test_bucket_preserves_largest_uint64_rounding_and_explicit_clamp(monkeypatch):
    import config.policy.batch as batch

    class Digest:
        def digest(self):
            return b'\xff' * 32

    monkeypatch.setattr(batch.hashlib, 'sha256', lambda value: Digest())
    assert cohort_bucket('synthetic', 'sample', bits=64) == 100
    assert cohort_bucket('synthetic', 'sample', bits=64, clamp_upper=True) == math.nextafter(100.0, 0.0)


def test_policy_flags_do_not_leak_process_mode_or_boolean_values(monkeypatch):
    from config.policy.batch import resolve_batch_policy
    from config.policy.kill_switches import kill_switch

    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    flags = {'BATCH_PIPELINE_ENABLED': 'on', 'BATCH_PIPELINE_PERCENT': '100'}
    assert not resolve_batch_policy('synthetic', flags=flags).batch_enabled
    assert not kill_switch('BATCH_PIPELINE_OWNER_DRAIN_ENABLED', flags={'BATCH_PIPELINE_OWNER_DRAIN_ENABLED': 'on'})
    flags['CAPTURE_COVERAGE_MODE'] = 'serve'
    assert resolve_batch_policy('synthetic', flags=flags).batch_enabled
    assert kill_switch(
        'BATCH_PIPELINE_OWNER_DRAIN_ENABLED',
        flags={'CAPTURE_COVERAGE_MODE': 'serve', 'BATCH_PIPELINE_OWNER_DRAIN_ENABLED': 'on'},
    )


def test_registry_fail_fields_follow_shared_boolean_defaults():
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, str(root / 'scripts/render_feature_flag_registry.py'), '--check-parsers'],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    rows = [
        json.loads(line.strip()[2:])
        for line in (root / 'config/feature-flags.yaml').read_text().splitlines()
        if line.strip().startswith('- {')
    ]
    by_key = {row['key']: row for row in rows}
    assert by_key['BATCH_PIPELINE_FRESH_GPU_PRIORITY_ENABLED']['fail'] == 'open'
    assert by_key['SYNC_BACKFILL_OWNER_CONCURRENCY_ENABLED']['fail'] == 'open'


def test_jev_empty_salt_retains_the_legacy_nul_prefix():
    from config.jev_decisions import uid_bucket

    identity = 'synthetic-' + str(17)
    legacy = int.from_bytes(hashlib.sha256(('\0' + identity).encode()).digest()[:8], 'big') / 2**64 * 100
    assert uid_bucket(identity, '') == min(legacy, math.nextafter(100.0, 0.0))


def test_translation_kill_switch_uses_shared_parser_only_in_serve(monkeypatch):
    from config.translation import resolve_ondemand_config

    env = {'TRANSLATION_DEMAND_GATE_ENABLED': 'on'}
    with pytest.raises(ValueError, match='must be true or false'):
        resolve_ondemand_config(env)
    env['CAPTURE_COVERAGE_MODE'] = 'serve'
    # Parsing gets past the switch; the remaining zero-spend defaults remain valid.
    assert resolve_ondemand_config(env).gate_enabled


@pytest.mark.parametrize('stage,expected', [('dev', True), ('local', True), ('offline', True), ('prod', False)])
def test_stage_specific_diagnostic_defaults_survive_migration(monkeypatch, stage, expected):
    from config.speaker_match_scores import enabled

    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.setenv('OMI_ENV_STAGE', stage)
    monkeypatch.delenv('SPEAKER_MATCH_SCORES_ENABLED', raising=False)
    assert enabled() is expected


@pytest.mark.parametrize('percent', ['inf', '-inf', 'nan', '-1', '101', 'invalid'])
def test_invalid_serve_percent_does_not_admit(percent):
    assert not refactor_modes.serving_for(
        'CAPTURE_COVERAGE_MODE', 'synthetic', environ={'CAPTURE_COVERAGE_MODE_SERVE_PERCENT': percent}
    )
