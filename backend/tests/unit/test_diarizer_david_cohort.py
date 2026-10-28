"""Reviewed batch stages bind the same cohort on live and offline-sync hosts."""

import json
from pathlib import Path

import pytest
import yaml
from config import transcription_final_pass as flags

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize('host', ['backend', 'backend-sync', 'backend-sync-backfill', 'pusher'])
def test_prepared_cohort_matches_reviewed_stage(monkeypatch, host):
    manifest = yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)[
        'environments'
    ]['prod']
    binding = manifest['gke']['pusher']['env'] if host == 'pusher' else manifest['cloud_run']['services'][host]['env']
    stages = json.loads((ROOT / 'config/diarization-cohort-stages.json').read_text())
    keys = tuple(key for key in stages['A'] if host == 'pusher' or not key.endswith('_UID_ALLOWLIST'))
    selected = {key: binding[key]['value'] for key in keys}
    assert selected == {key: stages['E'][key] for key in keys}
    assert selected == {key: manifest['gke']['pusher']['env'][key]['value'] for key in keys}
    for key, value in selected.items():
        monkeypatch.setenv(key, value)
    uid = 'synthetic-rollout-member'
    monkeypatch.setattr(flags, 'in_rollout_cohort', lambda owner, name: owner == uid)
    assert ('TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST' in binding) == (host == 'pusher')
    assert flags.enabled_for(uid)
    assert not flags.enabled_for('synthetic-outside-cohort')
    assert flags.authoritative_for(uid) == (selected['TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE'] == 'true')
    assert flags.sync_enabled_for(uid) == (selected['TRANSCRIPTION_FINAL_PASS_SYNC_ENABLED'] == 'true')
    assert selected['TRANSCRIPTION_FINAL_PASS_BACKEND'] == 'pyannote'
    assert selected['HOSTED_DIARIZATION_API_URL'] == 'http://172.16.160.20/diarizer-batch'
    assert ('TRANSCRIPTION_SHADOW_UID_ALLOWLIST' in binding) == (host == 'pusher')
    assert binding['TRANSCRIPTION_SHADOW_PERCENT']['value'] == selected['TRANSCRIPTION_FINAL_PASS_PERCENT']
    if host == 'pusher':
        chart = yaml.load(
            (ROOT / 'backend/charts/pusher/prod_omi_pusher_values.yaml').read_text(), Loader=yaml.CSafeLoader
        )
        chart_values = {entry['name']: entry.get('value') for entry in chart['env']}
        assert {key: chart_values[key] for key in keys} == selected


def test_prepared_cohort_does_not_enable_integration_or_dev():
    manifest = yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)[
        'environments'
    ]
    for host in ('backend-integration',):
        env = manifest['prod']['cloud_run']['services'][host]['env']
        assert env.get('TRANSCRIPTION_FINAL_PASS_DIARIZER', {}).get('value', 'legacy') == 'legacy'
    for host in ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration'):
        env = manifest['dev']['cloud_run']['services'][host]['env']
        assert env.get('TRANSCRIPTION_FINAL_PASS_DIARIZER', {}).get('value', 'legacy') == 'legacy'
    for host in ('backend-listen', 'pusher'):
        env = manifest['dev']['gke'][host]['env']
        assert env.get('TRANSCRIPTION_FINAL_PASS_DIARIZER', {}).get('value', 'legacy') == 'legacy'


@pytest.mark.parametrize(
    'stage,percent,authoritative,cap',
    [
        ('A', '0', 'false', '1'),
        ('B', '0', 'true', '1'),
        ('C', '1', 'true', '80'),
        ('D', '5', 'true', '400'),
        ('E', '5', 'true', '1200'),
    ],
)
def test_ramp_data_preserves_scope_and_capacity(monkeypatch, stage, percent, authoritative, cap):
    values = json.loads((ROOT / 'config/diarization-cohort-stages.json').read_text())[stage]
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    assert values['TRANSCRIPTION_FINAL_PASS_PERCENT'] == values['TRANSCRIPTION_SHADOW_PERCENT'] == percent
    assert values['TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE'] == authoritative
    assert values['TRANSCRIPTION_SHADOW_DAILY_AUDIO_HOURS'] == cap
    sync_audio_cap = {'D': '50', 'E': '150'}.get(stage, '10')
    sync_request_cap = {'D': '5000', 'E': '15000'}.get(stage, '1000')
    assert values['TRANSCRIPTION_SYNC_FINAL_PASS_HOURLY_AUDIO_HOURS'] == sync_audio_cap
    assert values['TRANSCRIPTION_SYNC_FINAL_PASS_HOURLY_REQUESTS'] == sync_request_cap
    assert values['TRANSCRIPTION_SHADOW_ENABLED'] == 'true'
    assert values['TRANSCRIPTION_SHADOW_KILL_SWITCH'] == 'false'
    assert values['TRANSCRIPTION_FINAL_PASS_SYNC_ENABLED'] == ('false' if stage == 'A' else 'true')
    uid = 'synthetic-rollout-member'
    monkeypatch.setattr(flags, 'in_rollout_cohort', lambda owner, name: owner == uid)
    assert flags.sync_enabled_for(uid) == (stage != 'A')
    assert values['TRANSCRIPTION_SHADOW_UID_ALLOWLIST'] == values['TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST']
    assert flags.enabled_for(uid)
    if percent == '0':
        assert not flags.enabled_for('synthetic-outside-cohort')
    else:
        assert float(cap) >= 6300 * float(percent) / 100
        assert 142 * float(percent) / 5 * 0.042 < 24
        diarizer_values = yaml.safe_load(
            (ROOT / 'backend/charts/diarizer/prod_omi_diarizer_batch_values.yaml').read_text()
        )['autoscaling']
        scale_up_step = max(
            policy['value'] for policy in diarizer_values['behavior']['scaleUp']['policies'] if policy['type'] == 'Pods'
        )
        assert diarizer_values['maxReplicas'] == 18
        assert scale_up_step == 3
        projected_peak_replicas = 5 * float(percent) / 5
        assert projected_peak_replicas <= 18 - 3
