"""Compose existing serving ops into the ruled canary's candidate, never apply.

The workflow-owned controller supplies the private authenticated snapshot. This
module is pure composition, not admission or a replacement for that live reader.
"""

from __future__ import annotations

from copy import deepcopy

SOURCE = '0714c5198be8f0183c8fd7dd3810d53c91af17a4'
SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')
# Existing native ops_env fold ownership, carried forward before the candidate
# instead of restoring these keys after its first traffic move.
PREFIXES = (
    'BATCH_PIPELINE_',
    'SYNC_ASSIGNMENT',
    'VAD_CACHE',
    'SYNC_JOB_',
    'FIRST_SUMMARY',
    'SUMMARY_DEBT',
    'SYNC_TASKS',
    'REPEAT_WORK',
    'DEMAND_PROCESSING',
    'SYNC_REPROCESS',
    'SYNC_BACKFILL',
    'DREAM_',
    'EPISODES_',
    'STT_CAP_',
    'SYNC_LINEAGE_',
    'STT_PRERECORDED_',
    'PFX_',
    'FSR_',
    'FIRESTORE_READ_',
)
QUALITY = {
    'HOME_TRANSCRIPTION_QUEUE_HOLD_ENABLED': 'true',
    'HOME_TRANSCRIPTION_MAX_AGE_SECONDS': '86400',
    'RECORD_SEAL_REPAIR_FRESH_ENABLED': 'true',
}
BACKOFF = 'BATCH_PROJECTION_FINISH_BACKOFF_ENABLED'
PROVIDER = 'BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED'


def app_env(revision):
    containers = revision['spec']['containers']
    ingress = [c for c in containers if c.get('ports')]
    if len(containers) == 1:
        ingress = containers
    if len(ingress) != 1:
        raise ValueError('canary snapshot ingress ambiguous')
    entries = ingress[0].get('env', [])
    result = {}
    for entry in entries:
        key = entry.get('name')
        if not isinstance(key, str) or not key or key in result:
            raise ValueError('canary snapshot env ambiguous')
        if 'valueFrom' in entry:
            if 'value' in entry or set(entry['valueFrom']) != {'secretKeyRef'}:
                raise ValueError('canary snapshot secret invalid')
            ref = entry['valueFrom']['secretKeyRef']
            if set(ref) != {'name', 'key'} or not all(isinstance(v, str) and v for v in ref.values()):
                raise ValueError('canary snapshot secret invalid')
        elif not isinstance(entry.get('value', ''), str):
            raise ValueError('canary snapshot literal invalid')
        result[key] = entry
    return result


def compose(config, snapshot, source):
    if source != SOURCE or snapshot.get('source') != SOURCE or set(snapshot.get('services', {})) != set(SERVICES):
        raise ValueError('canary ops snapshot source/scope mismatch')
    config = deepcopy(config)
    services = config['cloud_run']['services']
    for service in SERVICES:
        live = app_env(snapshot['services'][service]['revision'])
        desired = services[service]
        env = desired.setdefault('env', {})
        secrets = desired.setdefault('secrets', {})
        forbidden = set(desired.get('forbidden_env', []))
        if any(k in forbidden for k in QUALITY):
            raise ValueError('canary quality disposition conflicts with manifest')
        for key, entry in live.items():
            if not key.startswith(PREFIXES) or key in forbidden:
                continue
            if 'valueFrom' in entry:
                ref = entry['valueFrom']['secretKeyRef']
                env.pop(key, None)
                secrets[key] = {'secret': ref['name'], 'version': ref['key']}
            else:
                secrets.pop(key, None)
                env[key] = {'value': entry.get('value', ''), 'category': 'ops_kill'}
        for key, value in {**QUALITY, 'OMI_BACKEND_RELEASE_SHA': source, PROVIDER: 'false'}.items():
            secrets.pop(key, None)
            env[key] = {'value': value, 'category': 'rollout'}
        if service in ('backend-sync', 'backend-integration'):
            if BACKOFF in forbidden:
                raise ValueError('canary backoff disposition conflicts with manifest')
            secrets.pop(BACKOFF, None)
            env[BACKOFF] = {'value': 'false', 'category': 'rollout'}
        else:
            env.pop(BACKOFF, None)
            secrets.pop(BACKOFF, None)
            desired['forbidden_env'] = sorted(forbidden | {BACKOFF})
    return config
