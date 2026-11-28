"""Execute one workflow-owned Cloud Run move under an exclusive service lease.

The reviewed workflow supplies a transport scoped to the selected service. Its
replace(state, allocations) must condition a single full traffic replacement
on state.etag, preserve existing tags, and wait (with a deadline) for Cloud Run
to settle. read() returns explicit requested and observed revision maps.
The guard must evaluate only the supplied UTC interval and return its verdict.
"""

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

if __package__:
    from . import serving_has
else:
    # Isolated Python does not add the script directory to sys.path.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import serving_has

REVISION = re.compile(r'[a-z][a-z0-9-]{0,62}')
# Values are (donor hold-back percentage points, post-promotion guard seconds).
MIN_WINDOW = 30 * 60
MAX_WINDOW = 4 * 60 * 60
SETTLE_SECONDS = 600  # Existing route-log metric settlement allowance.
HOLDBACK_BY_SERVICE = {
    'backend': (5, 2 * 60 * 60),
    'backend-sync': (5, 2 * 60 * 60),
    'backend-sync-backfill': (5, 2 * 60 * 60),
    'backend-integration': (5, 2 * 60 * 60),
}
VERDICT_EXIT = {'PASS': 0, 'TRIP': 1, 'NO_COMPARATOR': 3, 'INSUFFICIENT_DATA': 4}


class Hold(RuntimeError):
    """The verified partial map remains in place for Release to resolve."""

    def __init__(self, verdict, state):
        super().__init__(verdict)
        self.state = state


@dataclass(frozen=True)
class TrafficState:
    uid: str
    etag: str
    requested: dict
    observed: dict
    tags: tuple = ()
    converged: bool = True
    generation: int = 0
    annotations: dict = field(default_factory=dict)
    tags_observed: bool = True


REVISION_TARGET = 'TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION'
RECOVERY_ANNOTATION = 'omi.me/holdback-recovery'


class CloudRunTraffic:
    """Cloud Run v2 transport. The workflow supplies authenticated JSON HTTP.

    request(method, url, *, body=None, timeout=...) must impose the supplied
    deadline and surface HTTP failures. It must never retry a PATCH.
    """

    def __init__(self, project, region, service, request):
        if service not in HOLDBACK_BY_SERVICE or not all(REVISION.fullmatch(value) for value in (project, region)):
            raise ValueError('invalid_cloud_run_target')
        self.service = service
        self.name = f'projects/{project}/locations/{region}/services/{service}'
        self.url = 'https://run.googleapis.com/v2/' + self.name
        self.request = request
        self.promotion = None

    def _traffic(self, entries):
        result, tags = {}, {}
        for entry in entries:
            revision = entry.get('revision', '')
            percent, tag = entry.get('percent', 0), entry.get('tag', '')
            if (
                entry.get('type') != REVISION_TARGET
                or not valid_revision(self.service, revision)
                or type(percent) is not int
                or not 0 <= percent <= 100
                or tag in tags
            ):
                raise RuntimeError('cloud_run_traffic_unknown')
            if percent:
                result[revision] = result.get(revision, 0) + percent
            if tag:
                tags[tag] = revision
        return result, tuple(sorted(tags.items()))

    def read(self, timeout=15):
        doc = self.request('GET', self.url, timeout=timeout)
        if doc.get('name') != self.name or not doc.get('uid') or not doc.get('etag'):
            raise RuntimeError('traffic_identity_changed')
        requested, tags = self._traffic(doc['traffic'])
        observed, observed_tags = self._traffic(doc['trafficStatuses'])
        generation = doc.get('generation')
        converged = (
            not doc.get('reconciling')
            and generation is not None
            and generation == doc.get('observedGeneration')
            and tags == observed_tags
        )
        return TrafficState(
            doc['uid'],
            doc['etag'],
            requested,
            observed,
            tags,
            converged,
            int(generation or 0),
            doc.get('annotations') or {},
            tags == observed_tags,
        )

    def replace(self, state, target):
        remaining = dict(target)
        traffic = [
            dict(type=REVISION_TARGET, revision=revision, tag=tag, percent=remaining.pop(revision, 0))
            for tag, revision in state.tags
        ]
        traffic += [
            dict(type=REVISION_TARGET, revision=revision, percent=percent)
            for revision, percent in sorted(remaining.items())
        ]
        annotations = dict(state.annotations)
        if self.promotion is not None and target != self.promotion['inverse']:
            if not state.generation:
                raise RuntimeError('traffic_generation_unknown')
            # Store ownership in the same CAS as traffic. A local receipt cannot
            # cover the interval between the server accepting PATCH and runner loss.
            annotations[RECOVERY_ANNOTATION] = json.dumps(
                dict(
                    self.promotion,
                    uid=state.uid,
                    tags=state.tags,
                    generation=state.generation + 1,
                    previous_map=state.requested,
                    requested_map=target,
                ),
                separators=(',', ':'),
            )
        else:
            annotations.pop(RECOVERY_ANNOTATION, None)
        self._patch(state, traffic=traffic, annotations=annotations)
        self._wait_for(state, target, annotations.get(RECOVERY_ANNOTATION))

    def _wait_for(self, state, target, marker):
        deadline = time.monotonic() + 90
        while (remaining_seconds := deadline - time.monotonic()) > 0:
            live = self.read(timeout=min(15, remaining_seconds))
            current_marker = live.annotations.get(RECOVERY_ANNOTATION)
            if (
                live.uid != state.uid
                or live.tags != state.tags
                or current_marker not in (marker, state.annotations.get(RECOVERY_ANNOTATION))
            ):
                raise RuntimeError('traffic_identity_changed')
            if current_marker == marker and live.converged and live.requested == live.observed == target:
                return
            time.sleep(min(2, max(0, deadline - time.monotonic())))
        raise RuntimeError('traffic_move_not_observed')

    def _patch(self, state, *, annotations, **updates):
        if annotations != state.annotations:
            updates['annotations'] = annotations
        self.request(
            'PATCH',
            self.url + '?updateMask=' + ','.join(updates),
            body=dict(name=self.name, etag=state.etag, **updates),
            timeout=15,
        )

    def leave_held(self, state):
        # An intentional hold belongs to Release and must not look interrupted.
        owned_move(state, self.promotion)
        annotations = dict(state.annotations)
        del annotations[RECOVERY_ANNOTATION]
        self._patch(state, annotations=annotations)
        self._wait_for(state, state.requested, None)


def plan_for(service, inverse, donor, *, split):
    return build_plan(service, inverse, donor, split, *HOLDBACK_BY_SERVICE[service])


def build_plan(service, inverse, donor, split, holdback, seconds):
    traffic = {}
    for entry in inverse.split(','):
        revision, separator, percent = entry.partition('=')
        if (
            not separator
            or not valid_revision(service, revision)
            or revision in traffic
            or not re.fullmatch(r'[1-9][0-9]?|100', percent)
        ):
            raise ValueError('invalid_inverse_split')
        traffic[revision] = int(percent)
    if (
        split != (len(traffic) > 1)
        or sum(traffic.values()) != 100
        or type(holdback) is not int
        or type(seconds) is not int
        or not 1 <= holdback < traffic.get(donor, 0) - int(split)
        or not MIN_WINDOW <= seconds <= MAX_WINDOW
        or seconds % 60
    ):
        raise ValueError('invalid_inverse_split')
    return dict(inverse=traffic, donor=donor, holdback=holdback, guard_seconds=seconds)


def valid_revision(service, revision):
    return REVISION.fullmatch(revision) and revision.startswith(service + '-')


def encode_plan(plan):
    inverse = ','.join(f'{revision}={percent}' for revision, percent in sorted(plan['inverse'].items()))
    binding = f"{plan['donor']};{inverse}"
    if 'holdback' in plan:
        return f"holdback-v1;{binding};{plan['holdback']};{plan['guard_seconds']}"
    return binding  # Existing custody records retain their original digest.


def decode_plan(service, wire):
    version, donor, inverse, holdback, seconds = wire.split(';')
    if service not in HOLDBACK_BY_SERVICE or version != 'holdback-v1':
        raise ValueError('invalid_holdback_plan')
    plan = build_plan(service, inverse, donor, ',' in inverse, int(holdback), int(seconds))
    if encode_plan(plan) != wire:
        raise ValueError('invalid_holdback_plan')
    return plan


def allocations(plan, candidate, donor_percent=0):
    result = dict(plan['inverse'])
    donor = plan['donor']
    result[candidate] = result.pop(donor) - donor_percent
    if donor_percent:
        result[donor] = donor_percent
    return result


def promotion_shares(plan):
    if len(plan['inverse']) > 1:
        donor_share = plan['inverse'][plan['donor']]
        yield donor_share - min(10, donor_share - plan['holdback'] - 1)
    yield plan['holdback']
    yield 0


def owned_move(state, identity=None):
    marker = json.loads(state.annotations.get(RECOVERY_ANNOTATION, 'null'))
    if not isinstance(marker, dict) or (identity and any(marker.get(k) != v for k, v in identity.items())):
        raise RuntimeError('rollback_traffic_ownership_lost')
    service, candidate = marker['service'], marker['candidate']
    plan = decode_plan(service, marker['plan'])
    if not valid_revision(service, candidate) or candidate in plan['inverse']:
        raise RuntimeError('rollback_traffic_ownership_lost')
    maps = [plan['inverse'], *(allocations(plan, candidate, share) for share in promotion_shares(plan))]
    if (
        not state.generation
        or state.generation != marker['generation']
        or state.uid != marker['uid']
        or state.tags != tuple(map(tuple, marker['tags']))
        or not state.tags_observed
        or state.requested != marker['requested_map']
        or not any(
            marker['previous_map'] == previous
            and state.requested == requested
            and state.observed in (previous, requested)
            for previous, requested in zip(maps, maps[1:])
        )
    ):
        raise RuntimeError('rollback_traffic_ownership_lost')
    return marker


def check_release_floor(allocations, tags, floor_check):
    # A zero-percent revision can still receive requests through its tag URL.
    for revision in sorted(set(allocations) | {revision for _, revision in tags}):
        if floor_check(revision) is not True:
            raise ValueError('release_floor_rejected')


def restore_completed(service, wire, transport, receipt, *, floor_check):
    plan = decode_plan(service, wire)
    candidate = receipt['candidate']
    if (
        receipt['target'] != transport.name
        or receipt['binding'] != hashlib.sha256(wire.encode()).hexdigest()
        or not valid_revision(service, candidate)
        or candidate in plan['inverse']
    ):
        raise ValueError('rollback_receipt_mismatch')
    expected = allocations(plan, candidate)
    if receipt['final_map'] != expected:
        raise ValueError('rollback_receipt_map_mismatch')
    current = transport.read()
    if (
        not current.converged
        or current.uid != receipt['uid']
        or current.etag != receipt['etag']
        or current.tags != tuple(map(tuple, receipt['tags']))
        or current.requested != expected
        or current.observed != expected
    ):
        raise RuntimeError('rollback_traffic_ownership_lost')
    check_release_floor(plan['inverse'], current.tags, floor_check)
    transport.replace(current, plan['inverse'])


# The published floor lives on origin/main. A long guard window can outlive the
# fetch that preceded promotion, so every check re-reads that ref first and
# fails closed when the refresh cannot be proven.
FLOOR_REFRESH = ('git', 'fetch', '--no-tags', 'origin', '+refs/heads/main:refs/remotes/origin/main')


def refresh_release_floor(*, run=subprocess.run):
    completed = run(list(FLOOR_REFRESH), capture_output=True, text=True, timeout=60)
    if completed.returncode:
        raise ValueError('release_floor_refresh_failed')


def recovery_plan(receipt, run, run_id):
    """Bind downloaded evidence to the failed or cancelled production attempt."""
    service, wire = receipt['service'], receipt['plan']
    binding, source, control = (receipt[key] for key in ('binding', 'source', 'control'))
    if (
        receipt['schema'] != 1
        or receipt['run_id'] != run_id
        or receipt['run_attempt'] != 1
        or run['id'] != run_id
        or run['run_attempt'] != 1
        or run['head_repository']['full_name'] != 'BasedHardware/omi'
        or run['path'] != '.github/workflows/gcp_backend.yml'
        or run['head_branch'] != 'main'
        or run['event'] != 'workflow_dispatch'
        or run['status'] != 'completed'
        or run['conclusion'] not in ('failure', 'cancelled', 'timed_out')
        or not re.fullmatch(r'[0-9a-f]{40}', source)
        or not re.fullmatch(r'[0-9a-f]{40}', control)
        or run['head_sha'] != control
        or not re.fullmatch(
            rf'Holdback prod/{re.escape(service)} sha={source} by selection:[0-9a-f]{{32}} plan={re.escape(binding)}',
            run['display_title'],
        )
        or binding != hashlib.sha256(wire.encode()).hexdigest()
    ):
        raise ValueError('rollback_run_binding_mismatch')
    plan = decode_plan(service, wire)
    if receipt['inverse'] != plan['inverse']:
        raise ValueError('rollback_receipt_inverse_mismatch')
    return service, wire


def restore_interrupted(transport, run, run_id, *, floor_check):
    current = transport.read()
    marker = owned_move(current)
    service, _ = recovery_plan(marker, run, run_id)
    if service != transport.service or marker['target'] != transport.name:
        raise ValueError('rollback_receipt_mismatch')
    check_release_floor(marker['inverse'], current.tags, floor_check)
    transport.replace(current, marker['inverse'])


def promote(
    service,
    wire,
    candidate,
    transport,
    guard,
    *,
    floor_check,
    refresh_floor=None,
    recovery_identity=None,
    sleep=time.sleep,
    now=None,
    on_promoted=None,
):
    """Guard a named candidate and return only after its final map is observed.

    For a split service a guarded canary first borrows up to 10 percentage
    points from the donor. At every step allocations of other revisions stay
    fixed. A failed guard or move restores the original map if this operation
    still owns the requested traffic.

    Every revision in the admitted inverse is checked against the published
    release floor before the first traffic move and again before that inverse
    is restored, so a guard failure cannot re-serve an ineligible revision.
    """
    plan = decode_plan(service, wire)
    inverse, donor = plan['inverse'], plan['donor']
    if not valid_revision(service, candidate) or candidate in inverse:
        raise ValueError('invalid_candidate')
    initial = transport.read()
    if (
        not initial.uid
        or not initial.etag
        or not initial.converged
        or initial.requested != inverse
        or initial.observed != inverse
    ):
        raise ValueError('named_inverse_mismatch')

    if refresh_floor is not None:
        refresh_floor()
    check_release_floor(inverse, initial.tags, floor_check)
    if candidate not in {revision for _, revision in initial.tags} and floor_check(candidate) is not True:
        raise ValueError('release_floor_rejected')

    def read():
        current = transport.read()
        if current.uid != initial.uid or not current.etag or current.tags != initial.tags:
            raise RuntimeError('traffic_identity_changed')
        return current

    def settled(expected):
        current = read()
        if not current.converged or current.requested != expected or current.observed != expected:
            raise RuntimeError('traffic_readback_mismatch')
        if recovery_identity is not None and expected != inverse:
            owned_move(current, recovery_identity)
        return current

    def move(current, donor_percent):
        target = allocations(plan, candidate, donor_percent)
        attempted.append(target)
        transport.replace(current, target)
        return settled(target)

    def guard_window(current, duration):
        start = clock().replace(second=0, microsecond=0) + timedelta(minutes=1)
        end = start + timedelta(seconds=duration)
        settled_at = end + timedelta(seconds=SETTLE_SECONDS)
        sleep(math.ceil((settled_at - clock()).total_seconds()))
        assert_guard_traffic(current)
        if clock() < settled_at:
            raise RuntimeError('guard_window_not_settled')
        verdict = guard(service, candidate, donor, start, end)
        unchanged = assert_guard_traffic(current)
        if verdict in ('NO_COMPARATOR', 'INSUFFICIENT_DATA'):
            raise Hold(verdict, unchanged)
        if verdict != 'PASS':
            raise RuntimeError('holdback_guard_tripped' if verdict == 'TRIP' else 'invalid_guard_verdict')
        return unchanged

    def assert_guard_traffic(starting_state):
        current = settled(starting_state.requested)
        if current.etag != starting_state.etag:
            raise RuntimeError('traffic_changed_during_guard')
        return current

    clock = now if now is not None else lambda: datetime.now(timezone.utc)
    attempted = []
    try:
        current = initial
        *guarded_shares, final_share = promotion_shares(plan)
        windows = (MIN_WINDOW, plan['guard_seconds']) if len(guarded_shares) == 2 else (plan['guard_seconds'],)
        for share, window in zip(guarded_shares, windows):
            current = guard_window(move(current, share), window)
        promoted = move(current, final_share)
        if on_promoted:
            on_promoted(promoted)
        return promoted.observed
    except Hold as held:
        if recovery_identity is not None:
            transport.leave_held(held.state)
        raise
    except BaseException:
        if attempted:
            current = read()
            if current.requested != inverse:
                if current.requested not in attempted or current.observed not in [inverse, *attempted]:
                    raise RuntimeError('rollback_traffic_ownership_lost')
                if recovery_identity is not None:
                    owned_move(current, recovery_identity)
                # A guard window can outlive the floor read before the move.
                if refresh_floor is not None:
                    refresh_floor()
                check_release_floor(inverse, current.tags, floor_check)
                transport.replace(current, inverse)
            settled(inverse)
        raise


def stamp(value):
    return value.strftime('%Y-%m-%dT%H:%M:%SZ')


def guard_command(command, project, region, *, run=subprocess.run):
    """Evaluate the full interval in supported chunks after its final settle."""

    def evaluate(service, candidate, inverse, start, end):
        pending = 'PASS'
        while start < end:
            # Workstream 1 accepts up to an hour. Prefer 30-minute chunks and
            # fold any shorter remainder into the last chunk.
            remaining = end - start
            stop = end if remaining < timedelta(hours=1) else start + timedelta(minutes=30)
            inputs = dict(
                service=service,
                candidate=candidate,
                inverse=inverse,
                project=project,
                region=region,
                window=f'{stamp(start)}/{stamp(stop)}',
            )
            args = [arg for key, value in inputs.items() for arg in ('--' + key, value)]
            try:
                result = run([*command, *args], stdout=subprocess.PIPE, text=True, timeout=150)
                evidence = json.loads(result.stdout)
                verdict = evidence['verdict']
                if result.returncode != VERDICT_EXIT[verdict] or any(
                    evidence[key] != value for key, value in inputs.items()
                ):
                    raise ValueError('guard_binding_mismatch')
            except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, KeyError) as exc:
                raise RuntimeError('guard_evaluation_unproved') from exc
            if verdict == 'TRIP':
                return verdict
            if verdict == 'NO_COMPARATOR' or (verdict == 'INSUFFICIENT_DATA' and pending == 'PASS'):
                pending = verdict
            start = stop
        return pending

    return evaluate


def revision_image_source(revision, project, region, *, repo, describe=None, registry=None):
    """Full source commit of a revision's application image: pinned digest, then
    the registry's OCI revision label or commit tags (serving_has). The
    OMI_BACKEND_RELEASE_SHA env stamp is never read: env merges keep stale
    values, so it can name a release the revision does not serve. Any read
    that cannot prove the source raises ValueError (fail closed)."""
    if describe is None:

        def describe(name):
            flags = ['--project', project, '--region', region, '--format=json']
            return json.loads(serving_has.command([serving_has.GCLOUD, 'run', 'revisions', 'describe', name, *flags]))

    document = describe(revision)
    if (document.get('metadata') or {}).get('name') != revision:
        raise ValueError('revision_identity_mismatch')
    # No service argument: the desktop-backend env-stamp fallback never applies here.
    source = serving_has.image_source(document, repo, registry=registry)
    if not re.fullmatch(r'[0-9a-f]{40}', source or ''):
        raise ValueError('image_source_unproven')
    return source


def release_floor_command(script, project, region, *, repo='.', run=subprocess.run, describe=None, registry=None):
    """Prove each revision's image source, then run the reviewed
    verify_backend_release_floor.py on that exact commit (--sha)."""

    repo = str(Path(repo).resolve())
    script = Path(script).resolve()

    def check(revision):
        try:
            source = revision_image_source(revision, project, region, repo=repo, describe=describe, registry=registry)
            result = run([sys.executable, '-I', str(script), '--sha', source], cwd=repo, timeout=120)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, subprocess.SubprocessError):
            return False
        return result.returncode == 0

    return check


def gcloud_json(method, url, *, body=None, timeout=15):
    # WIF tokens may expire during the soak. Obtain current credentials per
    # request. The workflow provides the account through its existing auth step.
    deadline = time.monotonic() + timeout
    token = subprocess.check_output(
        ['gcloud', 'auth', 'print-access-token'], text=True, timeout=min(15, timeout)
    ).strip()
    remaining = deadline - time.monotonic()
    if not token or remaining <= 0:
        raise RuntimeError('cloud_credentials_unavailable')
    request = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(request, timeout=remaining) as response:
        return json.load(response)


class WorkflowGuardReader:
    """Use only the workflow's existing WIF credential to fetch a read token."""

    def __init__(self):
        if os.environ.get('GITHUB_ACTIONS') != 'true' or not os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
            raise ValueError('workflow_guard_requires_wif')
        self.deadline = time.monotonic() + 120

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('guard_read_deadline')
        return min(60, remaining)

    def run(self, argv):
        if argv != ['gcloud', 'auth', 'print-access-token']:
            raise ValueError('unexpected_guard_command')
        result = subprocess.run(argv, capture_output=True, text=True, timeout=min(15, self.remaining()))
        if result.returncode:
            raise ValueError('guard_credentials_unavailable')
        return result.stdout


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ['workflow-guard']:
        try:
            reader = WorkflowGuardReader()
        except ValueError:
            print('HOLDBACK_FAILED workflow guard requires WIF', file=sys.stderr)
            return 1
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import guard_eval

        return guard_eval.main(argv[1:], reader=reader)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    for mode in ('promote', 'validate-plan', 'restore-completed'):
        command = commands.add_parser(mode)
        command.add_argument('--service', choices=HOLDBACK_BY_SERVICE, required=True)
        command.add_argument('--plan', required=True)
        command.add_argument('--binding', required=True)
        if mode != 'validate-plan':
            command.add_argument('--project', required=True)
            command.add_argument('--region', required=True)
            command.add_argument('--release-floor-check', type=Path, required=True)
            command.add_argument('--promotion-receipt', type=Path, required=True)
        if mode == 'promote':
            command.add_argument('--refresh-floor', action='store_true', required=True)
            command.add_argument('--candidate', required=True)
            command.add_argument('--source', required=True)
            command.add_argument('--control', required=True)
            command.add_argument('--run-id', type=int, required=True)
            command.add_argument('--run-attempt', type=int, required=True)
            command.add_argument('--guard-command', nargs=argparse.REMAINDER)
    recovery = commands.add_parser('recover-run')
    recovery.add_argument('--project', required=True)
    recovery.add_argument('--region', required=True)
    recovery.add_argument('--release-floor-check', type=Path, required=True)
    recovery.add_argument('--run-id', type=int, required=True)
    recovery.add_argument('--run-metadata', type=Path, required=True)
    recovery.add_argument('--promotion-receipt', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.mode == 'recover-run':
            run = json.loads(args.run_metadata.read_text())
            floor_check = release_floor_command(args.release_floor_check, args.project, args.region)
            if args.promotion_receipt is not None:
                receipt = json.loads(args.promotion_receipt.read_text())
                service, wire = recovery_plan(receipt, run, args.run_id)
                transport = CloudRunTraffic(args.project, args.region, service, gcloud_json)
                restore_completed(service, wire, transport, receipt, floor_check=floor_check)
            else:
                target = re.match(r'Holdback prod/([a-z-]+) sha=', run['display_title'])
                if target is None:
                    raise ValueError('rollback_run_binding_mismatch')
                transport = CloudRunTraffic(args.project, args.region, target[1], gcloud_json)
                restore_interrupted(transport, run, args.run_id, floor_check=floor_check)
            print('HOLDBACK_RESTORED exact admitted inverse')
            return 0
        if hashlib.sha256(args.plan.encode()).hexdigest() != args.binding:
            raise ValueError('holdback_binding_mismatch')
        plan = decode_plan(args.service, args.plan)
        if args.mode == 'validate-plan':
            return 0
        transport = CloudRunTraffic(args.project, args.region, args.service, gcloud_json)
        floor_check = release_floor_command(args.release_floor_check, args.project, args.region)
        if args.mode == 'restore-completed':
            restore_completed(
                args.service,
                args.plan,
                transport,
                json.loads(args.promotion_receipt.read_text()),
                floor_check=floor_check,
            )
            print('HOLDBACK_RESTORED exact admitted inverse')
            return 0

        if (
            not all(re.fullmatch(r'[0-9a-f]{40}', sha) for sha in (args.source, args.control))
            or args.run_id <= 0
            or args.run_attempt != 1
        ):
            raise ValueError('invalid_promotion_run_identity')

        identity = dict(
            schema=1,
            service=args.service,
            plan=args.plan,
            inverse=plan['inverse'],
            source=args.source,
            control=args.control,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            target=transport.name,
            binding=args.binding,
            candidate=args.candidate,
        )
        transport.promotion = identity

        def record(state):
            receipt = dict(
                identity,
                uid=state.uid,
                etag=state.etag,
                tags=state.tags,
                final_map=state.observed,
            )
            with args.promotion_receipt.open('x') as output:
                json.dump(receipt, output)

        default = [sys.executable, '-I', str(Path(__file__).with_name('guard_eval.py'))]
        guard = guard_command(args.guard_command or default, args.project, args.region)
        result = promote(
            args.service,
            args.plan,
            args.candidate,
            transport,
            guard,
            floor_check=floor_check,
            refresh_floor=refresh_release_floor,
            recovery_identity=identity,
            on_promoted=record,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except Hold as error:
        print(f'HOLDBACK_HELD {error}', file=sys.stderr)
        return 75
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError):
        print('HOLDBACK_FAILED inspect workflow traffic and guard evidence', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
