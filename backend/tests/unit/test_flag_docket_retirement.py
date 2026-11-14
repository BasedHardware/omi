"""Serving defaults retained by David's 2026-11-09 flag docket."""

import pytest

from config import sync_reprocess, stt_cap_dispatch, rollout_cohorts
from config.refactor_modes import default_off, default_on


@pytest.mark.parametrize('coverage', ['off', 'shadow', 'serve'])
@pytest.mark.parametrize('stage,emulator', [('dev', ''), ('prod', ''), ('local', 'localhost:8080')])
@pytest.mark.parametrize('value', [None, '', ' ', 'false', '0', 'off', 'no', 'true', '1', 'yes', 'bad'])
def test_revision_retirement_preserves_both_child_switches(monkeypatch, coverage, stage, emulator, value):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', coverage)
    monkeypatch.setenv('OMI_ENV_STAGE', stage)
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', emulator)
    monkeypatch.delenv('REPEAT_WORK_REVISION_ENABLED', raising=False)
    for name, getter, default in [
        ('SYNC_REPROCESS_COALESCE_ENABLED', sync_reprocess.coalesce_enabled, stage == 'prod' or bool(emulator)),
        ('CONVERSATION_LLM_INPUT_DEDUPE_ENABLED', sync_reprocess.dedupe_enabled, True),
    ]:
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
        if coverage == 'serve':
            expected = False if value is None else default_off(name)
        elif value is None or not value.strip():
            expected = default
        else:
            expected = default_on(name)
        assert getter() is expected


@pytest.mark.parametrize('value', [None, '', 'false', '0', 'off', 'true', '1', 'yes', 'bad'])
@pytest.mark.parametrize('coverage', ['off', 'shadow', 'serve'])
def test_ladder_retirement_keeps_stt_cap_admission_identical(monkeypatch, value, coverage):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', coverage)
    monkeypatch.delenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', raising=False)
    if value is None:
        monkeypatch.delenv('STT_CAP_DISPATCH_ENFORCEMENT', raising=False)
    else:
        monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', value)
    assert stt_cap_dispatch.execution_admission_configured() is stt_cap_dispatch.enabled()
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'all')
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', 'live,sync')
    for lane in ('live', 'sync', 'batch'):
        assert stt_cap_dispatch.execution_admission_enabled('synthetic-owner', lane) is (
            stt_cap_dispatch.enabled() and stt_cap_dispatch.selected('synthetic-owner', lane)
        )


def test_migrated_membership_has_no_environment_fallback(monkeypatch):
    monkeypatch.setenv('AUDIO_ARCHIVE_UID_ALLOWLIST', 'synthetic-owner')
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_UIDS', 'synthetic-owner')
    for cohort in ('audio-archive', 'mobile-standard-batch'):
        assert rollout_cohorts.COHORT_ENVS[cohort]() == ''
        assert not rollout_cohorts.legacy_membership('synthetic-owner', cohort)
    assert 'first-summary' not in rollout_cohorts.COHORT_ENVS


def test_injected_cohorts_keep_member_admission_and_revocation(monkeypatch):
    from config import audio_archive
    from utils.sync.mobile_standard_batch import mobile_standard_batch_enabled

    monkeypatch.setenv('AUDIO_ARCHIVE_SYNC_ENABLED', 'true')
    monkeypatch.setenv('AUDIO_ARCHIVE_PERCENT', '0')
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_ENABLED', 'true')
    monkeypatch.setenv('MOBILE_STANDARD_BATCH_PERCENT', '0')
    members = {'audio-archive', 'mobile-standard-batch'}
    monkeypatch.setattr(
        rollout_cohorts,
        '_membership_resolver',
        lambda uid, name, **kwargs: uid == 'synthetic-owner' and name in members,
    )
    assert audio_archive.admitted('synthetic-owner', 'SYNC')
    assert mobile_standard_batch_enabled('synthetic-owner')
    assert not audio_archive.admitted('synthetic-nonmember', 'SYNC')
    assert not mobile_standard_batch_enabled('synthetic-nonmember')
    members.clear()
    assert not audio_archive.admitted('synthetic-owner', 'SYNC')
    assert not mobile_standard_batch_enabled('synthetic-owner')
