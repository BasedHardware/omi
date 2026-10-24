"""Admission-only rollback. Aggregate safety input; no customer database or object IO."""

import concurrent.futures
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request

from guard import Client, finite, log

PROJECT = 'based-hardware'
REGION = 'us-central1'
SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')
ROOT = f'projects/{PROJECT}/locations/{REGION}/services/'
KEY = 'BATCH_PIPELINE_PERCENT'
WINDOW = 1800
MAX_AGE = 600


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def percent(containers):
    # Match the unique application env entry; preserve metrics sidecars byte for byte.
    matches = [e for container in containers for e in container.get('env', []) if e.get('name') == KEY]
    if len(matches) != 1 or set(matches[0]) != {'name', 'value'}:
        raise ValueError('percent_missing_duplicate_or_secret')
    value = matches[0]['value']
    if not isinstance(value, str) or not value.isdecimal() or not 0 <= int(value) <= 100:
        raise ValueError('percent_invalid')
    return int(value)


def containers_at_zero(containers):
    """Equivalent to --update-env-vars: retain every other env/valueSource and field."""
    percent(containers)
    result = copy.deepcopy(containers)
    for container in result:
        for env in container.get('env', []):
            if env['name'] == KEY:
                env['value'] = '0'
    return result


def config_signature(template):
    value = copy.deepcopy(template)
    value.pop('revision', None)
    value['containers'] = containers_at_zero(value['containers'])
    return digest(value)


def ready(service):
    return (
        not service.get('reconciling', False)
        and service.get('generation') == service.get('observedGeneration')
        and service.get('terminalCondition', {}).get('state') == 'CONDITION_SUCCEEDED'
        and bool(service.get('etag'))
    )


def serving_name(service):
    traffic = service.get('trafficStatuses', [])
    # Fail closed on splits and tagged routes, including tag URLs with zero default traffic.
    if len(traffic) != 1 or traffic[0].get('percent') != 100 or traffic[0].get('tag'):
        raise ValueError('unsupported_split_or_tagged_traffic')
    name = traffic[0].get('revision', '')
    prefix = service['name'] + '/revisions/'
    if '/' not in name:
        name = prefix + name
    if not name.startswith(prefix) or '/' in name[len(prefix) :] or not name[len(prefix) :]:
        raise ValueError('revision_binding')
    return name


def revision_matches(template, revision):
    # Output-only fields live on Revision, so compare the corresponding template fields.
    return all(revision.get(k) == v for k, v in template.items() if k != 'revision')


def immutable_template(template, revision):
    """Resolve mutable template tags to the artifact reported by its serving revision.

    Call only after checking latestCreated == latestReady == serving, or against
    a persisted exact source-template hash. All other container fields must match.
    """
    result = copy.deepcopy(template)
    actual = revision['containers']
    if len(result['containers']) != len(actual):
        raise ValueError('container_count_drift')
    for container, serving in zip(result['containers'], actual):
        image = serving['image']
        if not re.search(r'@sha256:[a-f0-9]{64}$', image):
            raise ValueError('serving_image_not_immutable')

        def repository(ref):
            ref = ref.split('@')[0]
            parent, _, leaf = ref.rpartition('/')
            return parent + '/' + leaf.split(':')[0]

        if repository(container['image']) != repository(image):
            raise ValueError('image_repository_drift')
        container['image'] = image
    if not revision_matches(result, revision):
        raise ValueError('template_revision_configuration_drift')
    return result


def observe(cloud, service_id):
    service = cloud.get(ROOT + service_id)
    if service.get('name') != ROOT + service_id or not ready(service):
        raise ValueError('service_not_ready')
    name = serving_name(service)
    revision = cloud.get(name)
    if revision.get('name') != name or revision.get('reconciling', False):
        raise ValueError('revision_not_ready')
    return service, revision


def snapshot(cloud):
    result = {}
    for service_id in SERVICES:
        service, revision = observe(cloud, service_id)
        if (
            service.get('latestCreatedRevision') != revision['name']
            or service.get('latestReadyRevision') != revision['name']
        ):
            raise ValueError('unserved_template_or_revision_drift')
        template = immutable_template(service['template'], revision)
        result[service_id] = {
            'revision': revision['name'],
            'percent': percent(revision['containers']),
            'config': config_signature(template),
            'source_config': config_signature(service['template']),
        }
    return result


def decision(sample, identity, since, now, first_write_since=None):
    """P90 fast-mode safety only. Unknown is BLIND; quality remains WATCH."""
    if sample.get('schema_version') != 1 or sample.get('identity') != identity or sample.get('arm_since') != since:
        return 'BLIND', ['aggregate_identity_or_epoch_mismatch']
    first_write = sample.get('since')
    if (
        not finite(first_write)
        or isinstance(first_write, bool)
        or not 0 <= first_write <= since
        or (first_write_since is not None and first_write != first_write_since)
    ):
        return 'BLIND', ['first_write_epoch_missing_or_changed']
    observed, completed = sample.get('observed_at'), sample.get('read_completed_at')
    if not all(finite(t) and not isinstance(t, bool) for t in (observed, completed)):
        return 'BLIND', ['aggregate_time_missing']
    if not since <= observed <= completed <= now or now - observed > MAX_AGE:
        return 'BLIND', ['aggregate_stale_or_future']
    custody = sample.get('custody', {})
    fields = {
        'custody_missing': custody.get('missing'),
        'terminal_speech': sample.get('proven_terminal_loss_speech_seconds'),
        'failed_held_speech': sample.get('proven_failed_held_speech_seconds'),
        'projection_wedge': sample.get('since_t0_projection_obligations_over_15m'),
        'stuck_jobs': sample.get('since_t0_stuck_jobs_over_30m'),
    }
    unknowns = [
        custody.get('unknown'),
        sample.get('terminal_unrecovered_speech_unknown_units'),
        sample.get('since_t0_failed_held_unknown_duration'),
        sample.get('terminal_unrecovered_speech_vad_fallback_units'),
        sample.get('since_t0_failed_held_vad_fallback_units'),
    ]
    usable = lambda x: finite(x) and not isinstance(x, bool) and x >= 0
    trips = [key for key, value in fields.items() if usable(value) and value > 0]
    complete = all(usable(v) for v in [*fields.values(), *unknowns]) and not any(unknowns)
    # Before arming, only a complete snapshot can pin an epoch. Once armed, an independently
    # proven trip still wins over missing measurements, as in P90.
    if not complete and not (trips and now - since >= WINDOW):
        return 'BLIND', ['safety_measurement_unknown_no_advance']
    if now - since < WINDOW:
        return 'WARMUP', []
    if trips:
        return 'TRIP', trips
    return 'CLEAN', []


class Cloud:
    """GKE metadata token only. Poll services, avoiding project-wide operations IAM."""

    def request(self, path, body=None, mask=None):
        token_request = urllib.request.Request(
            'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token',
            headers={'Metadata-Flavor': 'Google'},
        )
        with urllib.request.urlopen(token_request, timeout=10) as response:
            token = json.load(response)['access_token']
        url = 'https://run.googleapis.com/v2/' + path
        if mask:
            url += '?' + urllib.parse.urlencode({'updateMask': mask})
        request = urllib.request.Request(
            url,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
            method='GET' if body is None else 'PATCH',
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)

    def get(self, path):
        return self.request(path)

    def patch(self, service, body, mask):
        return self.request(service['name'], dict(body, name=service['name'], etag=service['etag']), mask)


def rollback_one(cloud, service_id, pin, deadline, sleep=time.sleep, clock=time.monotonic):
    """Two etag-guarded writes: candidate with old traffic pinned, then explicit promotion.

    Intent and the unique candidate name are durable before this function runs. A later
    CronJob resumes an interrupted write without replaying a different serving template.
    """
    candidate = ROOT + service_id + '/revisions/' + pin['candidate']
    while clock() < deadline:
        service = cloud.get(ROOT + service_id)
        if not ready(service):
            sleep(3)
            continue
        current_name = serving_name(service)
        current = cloud.get(current_name)
        template = service['template']
        expected_config = pin['config'] if service.get('latestCreatedRevision') == candidate else pin['source_config']
        if config_signature(template) != expected_config:
            raise ValueError('rollback_configuration_drift')
        if current_name not in {pin['revision'], candidate}:
            raise ValueError('rollback_serving_drift')
        if current_name == candidate:
            if percent(current['containers']) != 0 or not revision_matches(template, current):
                raise ValueError('rollback_readback_mismatch')
            return True
        if current_name != pin['revision'] or percent(current['containers']) != pin['percent']:
            raise ValueError('rollback_source_drift')
        latest = service.get('latestCreatedRevision')
        if latest == candidate:
            if service.get('latestReadyRevision') != candidate:
                raise ValueError('rollback_candidate_not_ready')
            new = cloud.get(candidate)
            if percent(new['containers']) != 0 or not revision_matches(template, new):
                raise ValueError('rollback_candidate_mismatch')
            cloud.patch(
                service,
                {
                    'traffic': [
                        {
                            'type': 'TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION',
                            'revision': pin['candidate'],
                            'percent': 100,
                        }
                    ]
                },
                'traffic',
            )
        elif latest == current_name:
            new_template = immutable_template(template, current)
            new_template['revision'] = pin['candidate']
            new_template['containers'] = containers_at_zero(new_template['containers'])
            cloud.patch(
                service,
                {
                    'template': new_template,
                    'traffic': [
                        {
                            'type': 'TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION',
                            'revision': current_name.rsplit('/', 1)[-1],
                            'percent': 100,
                        }
                    ],
                },
                'template.containers,template.revision,traffic',
            )
        else:
            raise ValueError('rollback_unserved_template_drift')
        sleep(3)
    raise TimeoutError('rollback_readback_deadline')


def persist(kube, cm, state, verdict):
    return kube.kube(
        kube.path('state'),
        [
            {'op': 'test', 'path': '/metadata/resourceVersion', 'value': cm['metadata']['resourceVersion']},
            {'op': 'add', 'path': '/data', 'value': {'state': json.dumps(state, sort_keys=True), 'verdict': verdict}},
        ],
    )


def run(kube, cloud, sample_path, dry_run=False, now=None):
    fixed_clock = now is not None
    now = time.time() if now is None else now
    cm = kube.kube(kube.path('state'))
    state = json.loads(cm.get('data', {}).get('state', '{}'))
    if not state.get('pending'):
        fleet = snapshot(cloud)
        # Start only after all four actual serving revisions have been verified.
        now = now if fixed_clock else time.time()
        identity = digest(fleet)
        percents = {row['percent'] for row in fleet.values()}
        if percents == {0}:
            persist(kube, cm, {}, 'NOOP')
            log('batch_guard', verdict='NOOP', admission_percent=0)
            return 0
        if len(percents) != 1:
            raise ValueError('partial_apply_no_common_epoch')
        if state.get('identity') != identity:
            state = {'identity': identity, 'since': now}
        try:
            sample = json.loads(Path(sample_path).read_text())
            verdict, reasons = decision(sample, identity, state['since'], now, state.get('first_write_since'))
            if verdict in {'WARMUP', 'CLEAN', 'TRIP'}:
                state['first_write_since'] = sample['since']
        except (OSError, ValueError, TypeError, KeyError):
            verdict, reasons = 'BLIND', ['aggregate_unavailable']
        if verdict == 'TRIP' and not dry_run:
            nonce = os.urandom(6).hex()
            state['pending'] = {key: dict(pin, candidate=key + '-guard-' + nonce) for key, pin in fleet.items()}
        persist(kube, cm, state, verdict)
        log('batch_guard', verdict=verdict, reasons=reasons, dry_run=dry_run, identity=identity, since=state['since'])
        if not state.get('pending'):
            return 1 if verdict in {'TRIP', 'BLIND'} else 0
    if dry_run:
        log('batch_rollback', verdict='BLIND', result='pending_suppressed_by_dry_run')
        return 1
    pins = state['pending']
    if set(pins) != set(SERVICES):
        raise ValueError('rollback_intent_services')
    # Independent services continue even if one fails. No operations.get/project role needed.
    deadline = time.monotonic() + 600
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {key: pool.submit(rollback_one, cloud, key, pins[key], deadline) for key in SERVICES}
        results = {}
        for key, future in futures.items():
            try:
                results[key] = future.result()
            except Exception:
                results[key] = False
    # Re-read *every* traffic-serving revision after the entire rollback, not the service spec.
    try:
        after = snapshot(cloud)
        verified = all(row['percent'] == 0 and row['config'] == pins[key]['config'] for key, row in after.items())
    except Exception:
        verified = False
    complete = all(results.values()) and verified
    # Retain pins on failure, including Job interruption: next scheduled run retries safely.
    fresh_cm = kube.kube(kube.path('state'))
    if json.loads(fresh_cm.get('data', {}).get('state', '{}')) != state:
        raise ValueError('rollback_intent_changed')
    if complete:
        state.pop('pending')
    persist(kube, fresh_cm, state, 'ROLLED_BACK' if complete else 'ROLLBACK_FAILED')
    log(
        'batch_rollback',
        verdict='TRIP' if complete else 'BLIND',
        result='verified_zero_all_four' if complete else 'ROLLBACK_FAILED',
        services=results,
    )
    return 1 if complete else 2


def main():
    kube = Client('', os.environ['NAMESPACE'], '', os.environ['STATE_NAME'])
    try:
        return run(kube, Cloud(), '/safety/snapshot.json', os.environ.get('DRY_RUN') == 'true')
    except Exception as exc:
        # Exception type only: HTTP bodies/templates can contain env values or credentials.
        log('batch_guard_error', verdict='BLIND', error=type(exc).__name__)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
