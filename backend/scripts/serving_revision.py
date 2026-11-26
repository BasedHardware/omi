"""Canonical Cloud Run serving identity. No args: legacy JSON-stdin revision selector.

With SERVICE: describe status.traffic, then the revision actually receiving 100%. Its release is the source commit
of the revision's image digest (serving_has.py), not OMI_BACKEND_RELEASE_SHA; for split traffic use serving_has.py.
desktop-backend is the exception: its image keeps no registry evidence after deploy, so the workflow-stamped
OMI_DESKTOP_BACKEND_RELEASE_SHA validated against the workflow revision name resolves it (serving_has.py); its
commit-sha label is dispatch-head metadata (SCA-3013/SCA-3485) and reports as a mismatch, never as the release.
Only release identity and env shapes are printed; subprocess errors are suppressed.
Caller selects a read-only GCP agent tier before invoking this command.
"""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import serving_has  # noqa: E402

SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration', 'desktop-backend')
TRAIN_KEYS = (
    'DREAM_AGENT_ELIGIBILITY',
    'DREAM_ON_DEMAND_ENABLED',
    'DREAM_AGENT_PAID_PERCENT',
    'DREAM_AGENT_PASSES_PER_DAY',
    'DREAM_AGENT_CONCURRENCY',
    'DREAM_AGENT_UID_ALLOWLIST',
    'EPISODES_UID_ALLOWLIST',
    'BATCH_PIPELINE_PERCENT',
    'BATCH_PIPELINE_SHADOW_PERCENT',
    'BATCH_PIPELINE_ENABLED',
    'STT_CAP_RECOVERY_COHORT',
    'STT_CAP_DISPATCH_ENFORCEMENT',
    'STT_CAP_DISPATCH_LANES',
    'SYNC_LINEAGE_RESOLVE_ENABLED',
)


REVISION_NAME = re.compile(r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?')


def revision_name(value):
    return isinstance(value, str) and REVISION_NAME.fullmatch(value) is not None


def traffic_revision(traffic):
    positive = []
    for target in traffic:
        name = target.get('revisionName')
        # Cloud Run can omit the zero percentage of a tagged route.
        percent = target.get('percent', 0 if target.get('tag') and revision_name(name) else None)
        if type(percent) is not int or not 0 <= percent <= 100:
            raise ValueError('traffic_unknown')
        if percent:
            positive.append((name, percent))
    if len(positive) != 1 or positive[0][1] != 100 or not revision_name(positive[0][0]):
        raise ValueError('traffic_not_100_percent')
    return positive[0][0]


def serving_revision(doc):
    return traffic_revision(doc.get('status', {}).get('traffic', []))


def backfill_pin(doc, serving, release, revision, opts):
    requested = doc.get('spec', {}).get('traffic', [])
    if traffic_revision(requested) != serving or any(
        target.get('latestRevision', False) is not False for target in requested if target.get('percent')
    ):
        raise ValueError('backfill_pin_mismatch')
    if opts.expected_sha is None:
        label = revision.get('metadata', {}).get('labels', {}).get('commit-sha', '')
        if not re.fullmatch(r'[0-9a-f]{7,40}', label) or serving_has.resolve(opts.repo, label) != release:
            raise ValueError('backfill_source_mismatch')


def rollback_evidence(value):
    fields = value.split(':')
    if len(fields) == 5:
        service, inverse, source, created, ready = fields
        if (
            service in SERVICES
            and re.fullmatch(r'[0-9a-f]{40}', source)
            and all(revision_name(name) and name.startswith(service + '-') for name in (inverse, created, ready))
        ):
            return service, (inverse, source, created, ready)
    raise argparse.ArgumentTypeError('expected SERVICE:INVERSE:SOURCE_SHA:LATEST_CREATED:LATEST_READY')


def preflight_divergence(doc, serving, release, evidence, *, pinned=False):
    status = doc.get('status', {})
    created = status.get('latestCreatedRevisionName')
    ready = status.get('latestReadyRevisionName')
    if not revision_name(created) or not revision_name(ready):
        raise ValueError('latest_revision_unknown')
    if serving == created == ready:
        return None
    if pinned:
        return f'latest Created/Ready differs from serving: created={created} ready={ready} pin={serving}'
    if evidence != (serving, release, created, ready):
        raise ValueError('rollback_evidence_mismatch')
    return f'latest Created/Ready differs from serving: created={created} ready={ready} inverse={serving}'


def entries(revision):
    return {x['name']: x for x in revision['spec']['containers'][0].get('env', [])}


def shape(entry):
    if entry is None:
        return 'absent'
    if 'valueFrom' in entry:
        return 'set:secretref'
    v = entry.get('value', '')
    if not v:
        return 'empty'
    kind = 'bool' if v.lower() in ('true', 'false') else 'int' if re.fullmatch(r'-?\d+', v) else 'str'
    return f'set:{kind}:len={len(v)}'


def cohort_set(entry):
    if not entry:
        return False
    if 'valueFrom' in entry:
        return True
    return bool(re.fullmatch(r'uid:[^,\s]{28}', entry.get('value', '')))


def command(argv):
    r = subprocess.run(argv, capture_output=True, text=True, timeout=90)
    if r.returncode:
        raise ValueError('command_failed')
    return r.stdout


def read_service(service, project='based-hardware', region='us-central1', *, command_runner=None):
    command_runner = command if command_runner is None else command_runner
    flags = ['--project', project, '--region', region, '--format=json']
    gcloud = os.environ.get('GCLOUD', 'gcloud')
    doc = json.loads(command_runner([gcloud, 'run', 'services', 'describe', service, *flags]))
    revision_name = serving_revision(doc)
    revision = json.loads(command_runner([gcloud, 'run', 'revisions', 'describe', revision_name, *flags]))
    if revision.get('metadata', {}).get('name') != revision_name:
        raise ValueError('revision_identity_mismatch')
    if not any(
        c.get('type') == 'Ready' and c.get('status') == 'True' for c in revision.get('status', {}).get('conditions', [])
    ):
        raise ValueError('revision_not_ready')
    return doc, revision_name, revision


def timestamp(value):
    result = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timezone_required')
    return result


def release_of(revision, repo, service=None):
    """The revision's release is the source commit of its image (digest -> OCI revision label or commit tag), never
    OMI_BACKEND_RELEASE_SHA: env merges never remove a value, so sync/integration reported 0a31a3ed across many
    deploys (10-31..11-02) and five lanes read it as "not serving". desktop-backend's release-stamp exception is
    serving_has.RELEASE_STAMP_ENV (SCA-3485). Patched in tests."""
    return serving_has.image_source(revision, repo, service=service)


def validate(doc, revision_name, revision, opts):
    env = entries(revision)
    release = release_of(revision, opts.repo, getattr(opts, 'service', None))
    if not re.fullmatch(r'[0-9a-f]{40}', release):
        raise ValueError('missing_or_invalid_release_sha')
    label = revision.get('metadata', {}).get('labels', {}).get('commit-sha')
    label_state = (
        'match'
        if label and re.fullmatch(r'[0-9a-f]{7,40}', label) and release.startswith(label)
        else 'mismatch' if label else 'absent'
    )
    if getattr(opts, 'require_label_match', False) and label_state != 'match':
        raise ValueError('commit_label_release_mismatch')
    if opts.latest:
        status = doc.get('status', {})
        if revision_name != status.get('latestReadyRevisionName') or revision_name != status.get(
            'latestCreatedRevisionName'
        ):
            raise ValueError('traffic_not_latest')
    if opts.expected_sha and release != opts.expected_sha:
        raise ValueError('release_sha_mismatch')
    if opts.created_after and timestamp(revision['metadata']['creationTimestamp']) <= timestamp(opts.created_after):
        raise ValueError('revision_too_old')
    if opts.contains:
        # Ancestor, or a proven-equivalent squash merge of that reviewed head (lead 7bc379).
        r = subprocess.run(
            [
                sys.executable,
                '-I',
                str(Path(__file__).resolve().with_name('contains_commit.py')),
                '--repo',
                opts.repo,
                opts.contains,
                release,
            ],
            capture_output=True,
            timeout=120,
        )
        if r.returncode:
            raise ValueError('release_does_not_contain_commit')
    return release, env, label_state


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        try:
            print(serving_revision(json.load(sys.stdin)))
        except (ValueError, TypeError, KeyError, AttributeError):
            return 1
        return 0
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('service')
    p.add_argument('--created-after')
    p.add_argument('--contains')
    p.add_argument('--repo', default=serving_has.default_repo())
    p.add_argument('--env-shape', nargs='+', default=[])
    p.add_argument('--wait', type=float, default=0, metavar='MAX_MIN')
    p.add_argument('--project', default='based-hardware')
    p.add_argument('--region', default='us-central1')
    policy = p.add_mutually_exclusive_group()
    policy.add_argument('--latest', action='store_true')
    policy.add_argument('--preflight', action='store_true')
    p.add_argument(
        '--rollback',
        action='append',
        type=rollback_evidence,
        default=[],
        help='documented SERVICE:INVERSE:SOURCE_SHA:LATEST_CREATED:LATEST_READY',
    )
    p.add_argument('--require-label-match', action='store_true')
    p.add_argument('--expected-sha')
    p.add_argument('--release-only', action='store_true')
    p.add_argument('--cohort-set', action='store_true')
    p.add_argument('--train-readback', action='store_true')
    o = p.parse_args(argv)
    evidence = dict(o.rollback)
    if o.rollback and (not o.preflight or len(evidence) != len(o.rollback)):
        p.error('--rollback requires --preflight and one entry per service')
    if o.wait < 0:
        p.error('--wait must be nonnegative')
    deadline = time.monotonic() + o.wait * 60
    while True:
        try:
            doc, name, revision = read_service(o.service, o.project, o.region)
            release, env, label = validate(doc, name, revision, o)
            pinned = o.preflight and o.service == 'backend-sync-backfill'
            if pinned:
                backfill_pin(doc, name, release, revision, o)
            divergence = (
                preflight_divergence(doc, name, release, evidence.get(o.service), pinned=pinned)
                if o.preflight
                else None
            )
            if o.train_readback:
                # Enforcement must be on for both cap services. The recovery cohort is optional since #22991 and was
                # unset on 10-24 (plan-cap-100 step 3), so a missing cohort is not a readback failure; a malformed
                # one still is (infra 10-25: the next train's readback would have failed after a good deploy).
                cohort = env.get('STT_CAP_RECOVERY_COHORT')
                if o.service in ('backend', 'backend-sync') and (
                    (cohort is not None and not cohort_set(cohort))
                    or env.get('STT_CAP_DISPATCH_ENFORCEMENT', {}).get('value') != 'true'
                ):
                    raise ValueError('cap_readback_mismatch')
            if o.cohort_set and not cohort_set(env.get('STT_CAP_RECOVERY_COHORT')):
                raise ValueError('cohort_not_set')
            if o.release_only:
                print(release)
            else:
                print(f'READBACK {o.service} revision={name} release={release} label={label} traffic=100')
                for key in dict.fromkeys([*o.env_shape, *(TRAIN_KEYS if o.train_readback else ())]):
                    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
                        raise ValueError('invalid_env_key')
                    print(f'ENV_SHAPE {o.service} {key} {shape(env.get(key))}')
                if divergence:
                    print(f'READBACK_DIVERGENCE {divergence}')
            return 0
        except (ValueError, KeyError, TypeError, AttributeError, IndexError, OSError, subprocess.TimeoutExpired):
            # Never expose provider errors or values from malformed environment documents.
            if time.monotonic() >= deadline:
                print(f'READBACK_FAILED {o.service}', file=sys.stderr)
                return 124 if o.wait else 1
            time.sleep(min(30, max(0, deadline - time.monotonic())))


if __name__ == '__main__':
    sys.exit(main())
