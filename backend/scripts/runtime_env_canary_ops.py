"""Compose existing serving ops into the ruled canary's candidate, never apply.

The workflow-owned controller supplies the private authenticated snapshot. This
module is pure composition, not admission or a replacement for that live reader.
"""

from __future__ import annotations

from copy import deepcopy
import re

SOURCE = '0714c5198be8f0183c8fd7dd3810d53c91af17a4'
RESTORED_DEFAULTS = {
    'BATCH_PIPELINE_SERVING_SWEEP_PAGE_ROWS': '200',
    'BATCH_PIPELINE_SERVING_TICK_SECONDS': '10',
}
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
RETIRED_BATCH_ENV = frozenset({'BATCH_PROJECTION_FINISH_BACKOFF_ENABLED', 'BATCH_HELD_POLL_SKIP_ENABLED'})
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
    integration_only = snapshot.get('profile') == 'integration-only'
    selected = ('backend-integration',) if integration_only else SERVICES
    if (
        not isinstance(source, str)
        or not re.fullmatch(r'[0-9a-f]{40}', source)
        or snapshot.get('source') != source
        or (not integration_only and source != SOURCE)
        or set(snapshot.get('services', {})) != set(selected)
    ):
        raise ValueError('canary ops snapshot source/scope mismatch')
    config = deepcopy(config)
    services = config['cloud_run']['services']
    for service in selected:
        live = app_env(snapshot['services'][service]['revision'])
        desired = services[service]
        if integration_only:
            # This narrow recovery is not a full manifest reconciliation. Carry
            # every existing literal/secret binding, then apply only the named
            # quality/provider/stamp decisions and authorized removals.
            symbolic = {
                key: deepcopy(entry)
                for key, entry in desired.get('env', {}).items()
                if isinstance(entry, dict) and entry.get('env_var')
            }
            env, secrets = {}, {}
            for key, entry in live.items():
                if 'valueFrom' in entry:
                    ref = entry['valueFrom']['secretKeyRef']
                    secrets[key] = {'secret': ref['name'], 'version': ref['key']}
                else:
                    if key in symbolic:
                        # Retain native workflow-input contracts. The renderer
                        # resolves the protected binding (or retained fallback);
                        # candidate() then requires exact equality to the live
                        # inverse, so a changed binding cannot alter this scope.
                        env[key] = symbolic[key] | {'default': entry.get('value', '')}
                    else:
                        env[key] = {'value': entry.get('value', ''), 'category': 'ops_kill'}
            desired['env'], desired['secrets'] = env, secrets
            desired['forbidden_env'] = sorted(set(desired.get('forbidden_env', [])) | set(RESTORED_DEFAULTS))
        env = desired.setdefault('env', {})
        secrets = desired.setdefault('secrets', {})
        forbidden = set(desired.get('forbidden_env', []))
        if any(k in forbidden for k in QUALITY):
            raise ValueError('canary quality disposition conflicts with manifest')
        for key, entry in live.items():
            if integration_only:
                continue  # The complete retained map and symbolic contracts are already bound above.
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
        for key in RETIRED_BATCH_ENV:
            env.pop(key, None)
            secrets.pop(key, None)
        desired['forbidden_env'] = sorted(forbidden | RETIRED_BATCH_ENV)
        if integration_only:
            for key, saved in RESTORED_DEFAULTS.items():
                if live.get(key) != {'name': key, 'value': saved}:
                    raise ValueError('canary saved inverse differs from ruled 200/10')
                env.pop(key, None)
                secrets.pop(key, None)
            desired['forbidden_env'] = sorted(set(desired.get('forbidden_env', [])) | set(RESTORED_DEFAULTS))
    return config
