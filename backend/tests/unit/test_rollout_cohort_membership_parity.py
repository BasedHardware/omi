"""Real gates retain the legacy result with missing or identically seeded Firestore fields."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from config import audio_archive, dream_agent, live_demand, messaging, speaker_grouping, sync_lineage
from scripts.rollout_cohort_migration import KEYS
from utils import rollout_cohorts as runtime
from utils.conversations import transcription_shadow
from utils.sync.mobile_standard_batch import mobile_standard_batch_enabled

ROOT = Path(__file__).resolve().parents[3]


def members(env, key):
    return {v.strip() for v in env.get(key, '').split(',') if v.strip()}


@pytest.mark.parametrize('stage', ['dev', 'prod'])
@pytest.mark.parametrize('component', ['backend-listen', 'pusher'])
@pytest.mark.parametrize('seeded', [False, True])
def test_chart_deploy_never_flips_any_listed_gate(monkeypatch, stage, component, seeded):
    env = {
        row['name']: str(row.get('value', ''))
        for row in yaml.safe_load(
            (ROOT / f'backend/charts/{component}/{stage}_omi_{component.replace("-", "_")}_values.yaml').read_text()
        )['env']
    }
    for key in set(env) | set(KEYS.values()):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv('OMI_ENV_STAGE', stage)
    runtime.configure_rollout_runtime()
    uids = {'synthetic-nonmember', *(uid for key in KEYS.values() for uid in members(env, key))}
    flags = {uid: {name: True for name, key in KEYS.items() if uid in members(env, key)} for uid in uids}
    monkeypatch.setattr(runtime, '_cache', runtime._TTLReads(lambda uid: {stage: flags[uid]} if seeded else {}))
    for uid in uids:
        demand_percent = float(env.get('STT_LIVE_DEMAND_PERCENT', '0'))
        demand_hash = int.from_bytes(hashlib.sha256(('live-demand:' + uid).encode()).digest()[:8], 'big') / 2**64 * 100
        assert live_demand.resolve_live_demand().admits(uid) == (
            env.get('STT_LIVE_DEMAND_ENABLED', 'false') == 'true'
            and (uid in members(env, 'STT_LIVE_DEMAND_UID_ALLOWLIST') or demand_hash < demand_percent)
        )
        mobile_hash = int(hashlib.sha256(f'mobile-standard-batch:{uid}'.encode()).hexdigest()[:8], 16) % 10000
        assert mobile_standard_batch_enabled(uid) == (
            env.get('MOBILE_STANDARD_BATCH_ENABLED', '') == 'true'
            and (
                uid in members(env, 'MOBILE_STANDARD_BATCH_UIDS')
                or mobile_hash < int(env.get('MOBILE_STANDARD_BATCH_PERCENT', '0')) * 100
            )
        )
        assert dream_agent.allowlisted(uid) == (uid in members(env, 'DREAM_AGENT_UID_ALLOWLIST'))
        assert sync_lineage.sync_lineage_resolve_uid_allowed(uid) == (
            not members(env, 'SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST')
            or uid in members(env, 'SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST')
        )
        assert speaker_grouping.configuration(uid).detailed == (
            env.get('SPEAKER_GROUPING_SHADOW', 'off') in ('owner', 'cohort')
            and uid in members(env, 'SPEAKER_GROUPING_SHADOW_UID_ALLOWLIST')
        )
        audio_hash = int.from_bytes(hashlib.sha256(('audio-archive:' + uid).encode()).digest()[:8], 'big') / 2**64 * 100
        assert audio_archive.admitted(uid, 'COALESCE') == (
            env.get('AUDIO_ARCHIVE_COALESCE_ENABLED', 'false') == 'true'
            and (
                uid in members(env, 'AUDIO_ARCHIVE_UID_ALLOWLIST')
                or audio_hash < float(env.get('AUDIO_ARCHIVE_PERCENT', '0'))
            )
        )
        conversation = SimpleNamespace(private_cloud_sync_enabled=True, discarded=False, uses_custom_stt=False)
        shadow_hash = int.from_bytes(hashlib.sha256(uid.encode()).digest()[:4], 'big') / 2**32 * 100
        assert transcription_shadow._enabled(uid, conversation) == (
            env.get('TRANSCRIPTION_SHADOW_KILL_SWITCH', 'false') != 'true'
            and env.get('TRANSCRIPTION_SHADOW_ENABLED', 'false') == 'true'
            and (
                uid in members(env, 'TRANSCRIPTION_SHADOW_UID_ALLOWLIST')
                or shadow_hash < float(env.get('TRANSCRIPTION_SHADOW_PERCENT', '0'))
            )
        )


@pytest.mark.parametrize('stage', ['dev', 'prod'])
@pytest.mark.parametrize('seeded', [False, True])
def test_cloud_run_merge_keeps_live_imessage_membership(monkeypatch, stage, seeded):
    monkeypatch.setenv('OMI_ENV_STAGE', stage)
    # A retained live policy, rather than a UID literal in the manifest.
    monkeypatch.setenv(
        'OMI_MESSAGING_CHANNEL_POLICY',
        json.dumps(
            {
                'telegram': {'enabled': True, 'cohort': '*'},
                'imessage': {'enabled': True, 'cohort': ['synthetic-member'], 'seat_cap': 'off'},
            }
        ),
    )
    runtime.configure_rollout_runtime()
    monkeypatch.setattr(
        runtime,
        '_cache',
        runtime._TTLReads(
            lambda uid: {stage: {'messaging-imessage': True}} if seeded and uid == 'synthetic-member' else {}
        ),
    )
    assert messaging.cohort_enabled('synthetic-member', 'imessage')
    assert not messaging.cohort_enabled('synthetic-nonmember', 'imessage')
    assert messaging.cohort_enabled('synthetic-nonmember', 'telegram')
