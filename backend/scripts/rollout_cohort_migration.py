"""Live, counts-only cohort migration. No production operation runs at import time."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from google.cloud.firestore_v1.base_query import FieldFilter

from config.rollout_cohorts import COLLECTION, COHORT_ENVS, valid_uid

KEYS = {
    'batch-pipeline': 'BATCH_PIPELINE_UID_ALLOWLIST',
    'batch-pipeline-recovery': 'BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST',
    'first-summary': 'FIRST_SUMMARY_UID_ALLOWLIST',
    'audio-archive': 'AUDIO_ARCHIVE_UID_ALLOWLIST',
    'dream-agent': 'DREAM_AGENT_UID_ALLOWLIST',
    'speaker-grouping-shadow': 'SPEAKER_GROUPING_SHADOW_UID_ALLOWLIST',
    'stt-live-demand': 'STT_LIVE_DEMAND_UID_ALLOWLIST',
    'sync-legacy-fresh': 'SYNC_LEGACY_FRESH_UID_ALLOWLIST',
    'sync-lineage-resolve': 'SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST',
    'transcription-final-pass': 'TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST',
    'transcription-shadow': 'TRANSCRIPTION_SHADOW_UID_ALLOWLIST',
    'mobile-standard-batch': 'MOBILE_STANDARD_BATCH_UIDS',
}
CLOUD_RUN_HOSTS = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')
# A missing key on a participating host is a real empty cohort (lineage is
# the legacy allow-all exception). Never silently drop that source from comparison.
ALL_HOSTS = frozenset('cloud-run/' + name for name in CLOUD_RUN_HOSTS) | {'helm/backend-listen', 'helm/pusher'}
HOSTS = {
    'stt-live-demand': {'helm/backend-listen'},
    'mobile-standard-batch': {'helm/backend-listen'},
    'sync-lineage-resolve': ALL_HOSTS - {'helm/pusher'},
    'sync-legacy-fresh': {'cloud-run/backend-sync', 'cloud-run/backend-sync-backfill'},
}
LIMIT = 450  # A single bounded atomic seed; refuse to truncate a larger live cohort.


@dataclass(frozen=True)
class Membership:
    members: frozenset[str] = frozenset()
    all_users: bool = False


def _csv(raw):
    members = frozenset(v.strip() for v in raw.split(',') if v.strip())
    if len(members) > LIMIT or any(not valid_uid(v) for v in members):
        raise ValueError('invalid live cohort')
    return members


def _env(entries):
    result = {}
    for entry in entries:
        key = entry['name']
        if key not in set(KEYS.values()) | {'OMI_MESSAGING_CHANNELS_UIDS', 'OMI_MESSAGING_CHANNEL_POLICY'}:
            continue
        if key in result or 'valueFrom' in entry or not isinstance(entry.get('value'), str):
            raise ValueError('ambiguous live cohort binding')
        result[key] = entry['value']
    return result


def _json_command(argv):
    # Both streams are captured. Neither SDK nor CLI errors may disclose UIDs.
    result = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=True)
    return json.loads(result.stdout)


def read_live(environment, kube_context, *, command=_json_command):
    """Read the actually serving Cloud Run revision and installed Helm release values."""
    project = 'based-hardware' if environment == 'prod' else 'based-hardware-dev'
    sources = {}
    for host in CLOUD_RUN_HOSTS:
        base = ['--project', project, '--region', 'us-central1', '--format=json']
        service = command(['gcloud', 'run', 'services', 'describe', host, *base])
        traffic = [row for row in service['status']['traffic'] if row.get('percent', 0)]
        if len(traffic) != 1 or traffic[0]['percent'] != 100:
            raise ValueError('split Cloud Run traffic requires a separate migration')
        revision = command(['gcloud', 'run', 'revisions', 'describe', traffic[0]['revisionName'], *base])
        containers = revision['spec']['containers']
        if len(containers) != 1:
            raise ValueError('ambiguous serving container')
        sources['cloud-run/' + host] = _env(containers[0].get('env', []))
    for host in ('backend-listen', 'pusher'):
        release = f'{environment}-omi-{host}'
        values = command(
            [
                'helm',
                'get',
                'values',
                release,
                '--all',
                '--output',
                'json',
                '--namespace',
                f'{environment}-omi-backend',
                '--kube-context',
                kube_context,
            ]
        )
        sources['helm/' + host] = _env(values['env'])
    return sources


def cohort_sources(sources, name):
    """Inspect declared bindings, never combine divergent host lists into a wider cohort."""
    if name == 'batch-pipeline-shadow':
        # No env allowlist ever existed: legacy membership is everyone, narrowed only by stored denials.
        return [Membership(all_users=True)]
    rows = []
    for host, env in sources.items():
        if name.startswith('messaging-'):
            # Only the API owns messaging channel admission.
            if host != 'cloud-run/backend':
                continue
            if 'OMI_MESSAGING_CHANNEL_POLICY' in env:
                policy = json.loads(env['OMI_MESSAGING_CHANNEL_POLICY'])
                cohort = policy.get(name.removeprefix('messaging-'), {}).get('cohort', [])
                if cohort == '*':
                    rows.append(Membership(all_users=True))
                elif isinstance(cohort, list) and all(valid_uid(v) for v in cohort):
                    rows.append(Membership(frozenset(cohort)))
                else:
                    raise ValueError('invalid messaging cohort')
            else:
                rows.append(Membership(_csv(env.get('OMI_MESSAGING_CHANNELS_UIDS', ''))))
        else:
            key = KEYS[name]
            if name == 'sync-lineage-resolve':
                if host == 'helm/pusher':
                    continue
                members = _csv(env.get(key, ''))
                rows.append(Membership(members, all_users=not members))
            elif host in HOSTS.get(name, ALL_HOSTS):
                rows.append(Membership(_csv(env.get(key, ''))))
    return rows or [Membership()]


def inventory(sources):
    desired, conflicts = {}, {}
    for name in COHORT_ENVS:
        rows = cohort_sources(sources, name)
        desired[name] = rows[0]
        if any(row != rows[0] for row in rows[1:]):
            conflicts[name] = len(rows)
    return desired, conflicts


def validate_stored_documents(client):
    # Verify the same whole-document shape the serving adapter requires. A
    # malformed unrelated field can deny every cohort, including legacy all.
    rows = list(client.collection(COLLECTION).limit(LIMIT + 1).stream(timeout=10.0, retry=None))
    if len(rows) > LIMIT:
        raise ValueError('stored cohort inventory exceeds migration bound')
    for row in rows:
        data = row.to_dict()
        cohorts = data.get('cohorts') if isinstance(data, dict) else None
        if not isinstance(cohorts, dict) or any(
            not isinstance(flags, dict) or any(type(value) is not bool for value in flags.values())
            for flags in cohorts.values()
        ):
            raise ValueError('malformed stored cohort document')


def read_stored(client, environment, name, enabled):
    field = f'cohorts.{environment}.`{name}`'
    rows = list(
        client.collection(COLLECTION)
        .where(filter=FieldFilter(field, '==', enabled))
        .limit(LIMIT + 1)
        .stream(timeout=10.0, retry=None)
    )
    if len(rows) > LIMIT or any(not valid_uid(row.id) for row in rows):
        raise ValueError('stored cohort exceeds migration bound')
    return frozenset(row.id for row in rows)


def migrate(args, *, client_factory, live_reader=read_live):
    sources = live_reader(args.environment, args.kube_context)
    desired, conflicts = inventory(sources)
    if conflicts:
        for name in sorted(COHORT_ENVS):
            rows = cohort_sources(sources, name)
            print(
                f'{name}: sources={len(rows)} min_members={min(len(r.members) for r in rows)} '
                f'max_members={max(len(r.members) for r in rows)} all_sources={sum(r.all_users for r in rows)} '
                f'verdict={"MISMATCH" if name in conflicts else "MATCH"}'
            )
        return 1  # No client and no writes if live hosts disagree.
    if args.seed_live and not args.apply:
        for name, row in sorted(desired.items()):
            print(f'{name}: live_members={len(row.members)} legacy_all={int(row.all_users)} writes=0')
        return 0
    client = client_factory(project=args.project)
    validate_stored_documents(client)
    stored = {
        name: (read_stored(client, args.environment, name, True), read_stored(client, args.environment, name, False))
        for name in desired
    }
    mismatch = False
    for name, row in sorted(desired.items()):
        grants, denials = stored[name]
        # Global legacy cohorts need no enumeration. A false field would narrow them.
        matches = not denials if row.all_users else grants == row.members
        safe_to_seed = not denials if row.all_users else not (grants - row.members)
        if args.verify_live:
            mismatch |= not matches
        else:
            mismatch |= not safe_to_seed
        print(
            f'{name}: live_members={len(row.members)} legacy_all={int(row.all_users)} '
            f'firestore_members={len(grants)} firestore_denials={len(denials)} '
            f'verdict={"MATCH" if matches else "MISMATCH"}'
        )
    if args.verify_live or mismatch:
        return int(mismatch)
    # Re-read before the atomic write. Operators must hold cohort config steady
    # until the post-seed verification and deployment are complete.
    if sources != live_reader(args.environment, args.kube_context):
        raise ValueError('live source changed during seed')
    writes = {}
    for name, row in desired.items():
        for uid in row.members:
            writes.setdefault(uid, {})[name] = True
    if len(writes) > LIMIT:
        raise ValueError('seed exceeds atomic batch bound')
    if writes:
        batch = client.batch()
        for uid, flags in writes.items():
            batch.set(client.collection(COLLECTION).document(uid), {'cohorts': {args.environment: flags}}, merge=True)
        batch.commit(timeout=15.0, retry=None)
    print(f'Seed complete: member_documents={len(writes)}; run --verify-live before deploy.')
    return 0
