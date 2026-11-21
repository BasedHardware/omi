#!/usr/bin/env python3
"""Workflow-owned integration canary. This component does not grant live admission.

The existing workflow must retain its environment approval, concurrency, release
eligibility, Firestore, holds, drift and exact composition gates. The private state
file contains serving configuration (including literal env); NEVER upload it as an
artifact. Only the constant CLI receipts are safe for workflow logs.

Timing design: integration-canary.md / integration_canary.py, 504f33f3,
SCA-2283 offline contract. No runtime import from the design/tools repository.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import tempfile

if __package__:
    from .runtime_env_canary_ops import RETIRED_BATCH_ENV
    from .integration_canary_metrics import (
        Clock,
        Metrics,
        PROJECT,
        REGION,
        SERVICE,
        Refused,
        Transport,
        command,
        decode,
        decision,
        require,
        io_budget,
    )
else:
    from runtime_env_canary_ops import RETIRED_BATCH_ENV
    from integration_canary_metrics import (
        Clock,
        Metrics,
        PROJECT,
        REGION,
        SERVICE,
        Refused,
        Transport,
        command,
        decode,
        decision,
        require,
        io_budget,
    )

SOURCE = '0714c5198be8f0183c8fd7dd3810d53c91af17a4'
SOURCE_FLOOR = '51b449ec8843980b16a8c07ff1069f4f1660796b'
RESTORED_DEFAULTS = {'BATCH_PIPELINE_SERVING_SWEEP_PAGE_ROWS': '200', 'BATCH_PIPELINE_SERVING_TICK_SECONDS': '10'}
ROLLBACK = 'backend-integration-provfix-off1114'
SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', SERVICE)
QUALITY = {
    'HOME_TRANSCRIPTION_QUEUE_HOLD_ENABLED': 'true',
    'HOME_TRANSCRIPTION_MAX_AGE_SECONDS': '86400',
    'RECORD_SEAL_REPAIR_FRESH_ENABLED': 'true',
}
PROVIDER = 'BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED'
STAMP = 'OMI_BACKEND_RELEASE_SHA'
DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
RUN_URL = f'https://{REGION}-run.googleapis.com/apis/serving.knative.dev/v1/namespaces/{PROJECT}/services/{SERVICE}'
MAX_STATE = 8 * 1024 * 1024
GENERATED_ANNOTATIONS = {
    'run.googleapis.com/operation-id',
    'run.googleapis.com/ingress-status',
    'run.googleapis.com/urls',
    'serving.knative.dev/creator',
    'serving.knative.dev/lastModifier',
}
# The existing native ops fold's ownership, preserved BEFORE the candidate rather
# than folded into a new revision after canary. Queue bindings and secret refs
# receive the additional structural preservation check below.
OPS_PREFIXES = (
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


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest_bytes(raw):
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def env_map(entries):
    require(isinstance(entries, list), 'env_not_list')
    result = {}
    for entry in entries:
        require(isinstance(entry, dict) and isinstance(entry.get('name'), str), 'invalid_env')
        name = entry['name']
        require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) and name not in result, 'invalid_env')
        require(set(entry) in ({'name'}, {'name', 'value'}, {'name', 'valueFrom'}), 'invalid_env')
        entry = copy.deepcopy(entry)
        if set(entry) == {'name'}:
            # Cloud Run omits the default empty literal on export. Normalize
            # here so preparation and all template comparisons agree.
            entry['value'] = ''
        if 'value' in entry:
            require(isinstance(entry['value'], str), 'invalid_env_literal')
        else:
            ref = entry['valueFrom']
            require(isinstance(ref, dict) and set(ref) == {'secretKeyRef'}, 'invalid_secret_ref')
            secret = ref['secretKeyRef']
            require(isinstance(secret, dict) and set(secret) == {'name', 'key'}, 'invalid_secret_ref')
            require(all(isinstance(v, str) and v for v in secret.values()), 'invalid_secret_ref')
        result[name] = copy.deepcopy(entry)
    return result


def contract(entries):
    env = env_map(entries)
    for name, value in QUALITY.items():
        require(env.get(name) == {'name': name, 'value': value}, 'quality_contract')
    require(not RETIRED_BATCH_ENV.intersection(env), 'retired_batch_env')
    require(PROVIDER not in env or env[PROVIDER] == {'name': PROVIDER, 'value': 'false'}, 'provider_contract')
    return env


def app(spec):
    containers = spec.get('containers')
    require(isinstance(containers, list) and containers, 'containers_missing')
    apps = containers if len(containers) == 1 else [c for c in containers if c.get('ports')]
    require(len(apps) == 1, 'ingress_ambiguous')
    return apps[0]


def annotations(meta):
    return {k: v for k, v in meta.get('annotations', {}).items() if k not in GENERATED_ANNOTATIONS}


def labels(meta):
    return {
        k: v
        for k, v in meta.get('labels', {}).items()
        if not k.startswith(('serving.knative.dev/', 'cloud.googleapis.com/', 'run.googleapis.com/'))
    }


def template(revision, name):
    """Clone the ACTUAL serving revision, not the potentially failed service template."""
    meta = revision['metadata']
    return {
        'metadata': {'name': name, 'labels': labels(meta), 'annotations': annotations(meta)},
        'spec': copy.deepcopy(revision['spec']),
    }


def template_config(value):
    """Compare every runtime spec field and non-generated annotation/user label."""
    spec = copy.deepcopy(value['spec'])
    # Env order has no runtime meaning and the API may canonicalize it.
    for container in spec.get('containers', []):
        if 'env' in container:
            container['env'] = sorted(env_map(container['env']).values(), key=lambda e: e['name'])
    return {'spec': spec, 'annotations': annotations(value['metadata']), 'labels': labels(value['metadata'])}


def service_config(doc):
    spec = copy.deepcopy(doc['spec'])
    spec['template'] = template_config(spec['template']) | {'name': spec['template']['metadata'].get('name')}
    return {
        'name': doc['metadata'].get('name'),
        'uid': doc['metadata'].get('uid'),
        'namespace': doc['metadata'].get('namespace'),
        'labels': labels(doc['metadata']),
        'annotations': annotations(doc['metadata']),
        'spec': spec,
    }


def observed(doc):
    generation = doc.get('metadata', {}).get('generation')
    value = doc.get('status', {}).get('observedGeneration')
    require(type(generation) is int and generation > 0, 'generation_missing')
    require(str(generation) == str(value), 'generation_unobserved')


def ready(doc, service=False):
    conditions = doc.get('status', {}).get('conditions', [])
    status = [c.get('status') for c in conditions if c.get('type') == 'Ready']
    require(status == ['True'], 'not_ready')
    if service:
        observed(doc)


def identity(doc, name, service=False):
    meta = doc.get('metadata', {})
    require(meta.get('name') == name and bool(meta.get('uid')), 'identity_mismatch')
    require(bool(meta.get('resourceVersion')), 'resource_version_missing')
    require(isinstance(meta.get('namespace'), str) and bool(meta['namespace']), 'namespace_missing')
    if not service:
        require(meta.get('labels', {}).get('serving.knative.dev/service') in SERVICES, 'revision_owner_missing')


def traffic(entries, spec=False, latest=None):
    require(isinstance(entries, list) and bool(entries), 'traffic_missing')
    result = {}
    for row in entries:
        percent = row.get('percent', 0)
        require(type(percent) is int and 0 <= percent <= 100, 'traffic_invalid')
        if percent:
            name = latest if row.get('latestRevision') and latest else row.get('revisionName')
            require(isinstance(name, str) and (not row.get('latestRevision') or latest), 'traffic_not_named')
            result[name] = result.get(name, 0) + percent
        elif spec:
            require(row.get('revisionName') and not row.get('latestRevision'), 'tag_not_named')
    require(sum(result.values()) == 100, 'traffic_not_100')
    return result


def validate_predecessor(name):
    require(
        isinstance(name, str)
        and len(name) <= 63
        and re.fullmatch(r'backend-integration-[a-z0-9](?:[a-z0-9-]*[a-z0-9])?', name),
        'rollback_revision_invalid',
    )


def expected_traffic(percent, candidate, rollback=ROLLBACK):
    return {rollback: 100} if percent == 0 else ({rollback: 75, candidate: 25} if percent == 25 else {candidate: 100})


def check_traffic(doc, expected):
    require(traffic(doc['spec'].get('traffic'), True) == expected, 'requested_traffic_drift')
    require(traffic(doc.get('status', {}).get('traffic')) == expected, 'actual_traffic_drift')

    def bindings(entries):
        result = {}
        for entry in entries:
            if entry.get('tag'):
                tag = entry['tag']
                require(
                    isinstance(tag, str) and tag not in result and entry.get('revisionName'), 'traffic_tag_ambiguous'
                )
                result[tag] = entry['revisionName']
        return result

    require(bindings(doc['spec']['traffic']) == bindings(doc['status']['traffic']), 'actual_tag_drift')


def write_body(doc):
    result = copy.deepcopy(doc)
    result.pop('status', None)
    for key in ('creationTimestamp', 'generation', 'selfLink', 'managedFields'):
        result['metadata'].pop(key, None)
    # resourceVersion is deliberately retained: one true v1 PUT compare-and-swap.
    require(bool(result['metadata'].get('resourceVersion')), 'cas_version_missing')
    return result


class Journal:
    """Atomic 0600 journal plus a separate flock inode (atomic replace changes inode)."""

    def __init__(self, path):
        self.path = Path(path)
        self.lock = None

    def __enter__(self):
        flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
        self.lock = os.open(str(self.path) + '.lock', flags, 0o600)
        try:
            info = os.fstat(self.lock)
            require(
                stat.S_ISREG(info.st_mode)
                and info.st_nlink == 1
                and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600,
                'unsafe_journal_lock',
            )
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, Refused):
            os.close(self.lock)
            self.lock = None
            raise Refused('journal_busy') from None
        return self

    def __exit__(self, *_):
        if self.lock is not None:
            os.close(self.lock)

    def read(self):
        descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'rb') as handle:
            info = os.fstat(handle.fileno())
            require(
                stat.S_ISREG(info.st_mode)
                and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_nlink == 1,
                'unsafe_journal',
            )
            raw = handle.read(MAX_STATE + 1)
        require(len(raw) <= MAX_STATE, 'journal_too_large')
        return decode(raw)

    def save(self, state, create=False):
        raw = canonical(state).encode()
        require(len(raw) <= MAX_STATE, 'journal_too_large')
        if create:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(descriptor)
        descriptor, temporary = tempfile.mkstemp(prefix='.integration-canary-', dir=self.path.parent)
        try:
            with os.fdopen(descriptor, 'wb') as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class Cloud:
    def __init__(self, transport):
        self.transport = transport

    def read(self, kind, name):
        require(
            kind in ('services', 'revisions') and re.fullmatch(r'[a-z][a-z0-9-]{0,62}', name), 'read_target_invalid'
        )
        return decode(
            command(
                [
                    'gcloud',
                    'run',
                    kind,
                    'describe',
                    name,
                    '--project',
                    PROJECT,
                    '--region',
                    REGION,
                    '--format=json',
                    '--quiet',
                ]
            )
        )

    def put(self, body):
        return self.transport.request('PUT', RUN_URL, body=body).doc

    def head(self):
        return command(['git', 'rev-parse', '--verify', 'HEAD'])

    def prove_source(self, source):
        # The native workflow separately admits this exact SHA against main and
        # Release Eligibility. This floor proves the reviewed controller/quality
        # source is included; it never resolves a mutable main tip as authority.
        command(['git', 'merge-base', '--is-ancestor', SOURCE_FLOOR, source])
        # Execute the admitted source's pure configuration defaults in an
        # isolated bounded child. Never print its environment or configuration.
        script = (
            "import json,os,sys;from pathlib import Path;"
            "sys.path.insert(0,str(Path.cwd()/'backend'));"
            "os.environ.pop('BATCH_PIPELINE_SERVING_SWEEP_PAGE_ROWS',None);"
            "os.environ.pop('BATCH_PIPELINE_SERVING_TICK_SECONDS',None);"
            "from config.batch_pipeline import serving_sweep_page_rows,serving_tick_seconds;"
            "print(json.dumps([serving_sweep_page_rows(),serving_tick_seconds()]))"
        )
        require(decode(command(['python3', '-I', '-c', script])) == [100, 20], 'source_defaults_not_100_20')


class Registry:
    """Native base-image commit-tag policy plus existing workers-role image policy."""

    def __init__(self, transport):
        self.transport = transport
        self.reads = 0
        self.git_reads = 0

    def get(self, repository, kind, ref):
        self.reads += 1
        require(self.reads <= 4, 'registry_request_budget')
        return self.transport.request(
            'GET', f'https://gcr.io/v2/{PROJECT}/{repository}/{kind}/{ref}', registry_blob=kind == 'blobs'
        )

    def verify(self, image, source, restored_defaults=False):
        self.reads = self.git_reads = 0
        self.restored_defaults = restored_defaults
        with io_budget(60, getattr(self.transport, 'clock', Clock())):
            return self._verify(image, source)

    def git(self, argv):
        self.git_reads += 1
        require(self.git_reads <= 16, 'registry_git_budget')
        return command(argv)

    def _verify(self, image, source):
        # Fixed repositories only. A tag is admitted only for the base image, SHA7 exactly.
        match = re.fullmatch(
            r'gcr\.io/based-hardware/(backend|backend-workers)(?:@(sha256:[0-9a-f]{64})|:([0-9a-f]{7}))', image
        )
        require(match is not None, 'image_reference_refused')
        repository, pinned, tag = match.groups()
        require(not tag or (repository == 'backend' and tag == source[:7]), 'image_tag_refused')
        manifest = self.get(repository, 'manifests', pinned or tag)
        digest = digest_bytes(manifest.raw)
        require(not pinned or digest == pinned, 'registry_digest_mismatch')
        require(manifest.headers.get('docker-content-digest', digest) == digest, 'registry_digest_mismatch')
        root_digest = digest
        if 'manifests' in manifest.doc:
            choices = [
                m
                for m in manifest.doc['manifests']
                if m.get('platform', {}).get('os') == 'linux' and m.get('platform', {}).get('architecture') == 'amd64'
            ]
            require(len(choices) == 1 and DIGEST.fullmatch(choices[0].get('digest', '')), 'registry_platform_ambiguous')
            digest = choices[0]['digest']
            manifest = self.get(repository, 'manifests', digest)
            require(
                digest_bytes(manifest.raw) == digest and 'manifests' not in manifest.doc, 'registry_digest_mismatch'
            )
        config_digest = manifest.doc.get('config', {}).get('digest', '')
        require(DIGEST.fullmatch(config_digest), 'registry_config_missing')
        config_reply = self.get(repository, 'blobs', config_digest)
        require(digest_bytes(config_reply.raw) == config_digest, 'registry_config_mismatch')
        config = config_reply.doc.get('config', {})
        if self.restored_defaults:
            image_env = config.get('Env', [])
            require(
                isinstance(image_env, list) and all(isinstance(item, str) for item in image_env), 'registry_env_invalid'
            )
            require(
                not {item.partition('=')[0] for item in image_env} & set(RESTORED_DEFAULTS),
                'image_bakes_restored_override',
            )
        source_label = config.get('Labels', {}).get('org.opencontainers.image.revision', '')
        if source_label:
            require(source_label == source, 'registry_source_mismatch')
        else:
            require(repository == 'backend', 'registry_source_missing')
            # Native serving_has permits commit tags when the OCI revision label is absent.
            tag_reply = self.get(repository, 'tags', 'list')
            tags = tag_reply.doc
            require(not tags.get('nextPageToken') and not tag_reply.headers.get('link'), 'registry_tags_incomplete')
            commit_tags = tags.get('manifest', {}).get(root_digest, {}).get('tag', [])
            require(isinstance(commit_tags, list), 'registry_tags_invalid')
            hex_tags = [t for t in commit_tags if isinstance(t, str) and re.fullmatch(r'[0-9a-f]{7,40}', t)]
            require(0 < len(hex_tags) <= 8, 'registry_commit_tag_budget')
            commits = set()
            for value in hex_tags:
                commit = self.git(['git', 'rev-parse', '--verify', '--quiet', value + '^{commit}'])
                require(re.fullmatch('[0-9a-f]{40}', commit), 'registry_commit_unresolved')
                commits.add(commit)
            require(source in commits, 'registry_commit_tags_ambiguous')
            if commits != {source}:
                tree = self.git(['git', 'rev-parse', '--verify', source + '^{tree}'])
                for commit in sorted(commits - {source}):
                    require(
                        self.git(['git', 'rev-parse', '--verify', commit + '^{tree}']) == tree,
                        'registry_commit_tags_ambiguous',
                    )
                    self.git(['git', 'merge-base', '--is-ancestor', commit, source])
        if repository == 'backend-workers':
            require('OMI_ROLE=workers' in config.get('Env', []), 'registry_role_mismatch')
        return f'gcr.io/{PROJECT}/{repository}@{root_digest}'


class Controller:
    def __init__(self, journal, cloud, registry, metrics, clock=None, environ=None, discovery=None):
        self.journal, self.cloud, self.registry, self.metrics = journal, cloud, registry, metrics
        self.clock = clock or Clock()
        self.environ = os.environ if environ is None else environ
        self.state = None
        self.discovery = discovery
        self.deadline = self.clock.monotonic() + 2700

    def bind(self):
        require(self.environ.get('GITHUB_ACTIONS') == 'true', 'workflow_only')
        run = self.environ.get('GITHUB_RUN_ID', '')
        attempt = self.environ.get('GITHUB_RUN_ATTEMPT', '')
        require(
            run.isascii() and run.isdigit() and attempt.isascii() and attempt.isdigit(), 'workflow_identity_missing'
        )
        return run, attempt

    def save(self):
        self.journal.save(self.state)

    def load(self):
        run, attempt = self.bind()
        self.state = self.journal.read()
        require(self.state.get('schema') == 1 and self.state.get('run_id') == run, 'journal_binding')
        require(self.state.get('run_attempt') == attempt, 'journal_binding')
        require(
            (self.state.get('source') == SOURCE or self.state.get('profile') == 'integration-only')
            and self.state.get('project') == PROJECT
            and self.state.get('region') == REGION
            and (self.state.get('rollback') == ROLLBACK or self.state.get('profile') == 'integration-only'),
            'journal_binding',
        )
        require(set(self.state.get('services', {})) == set(self.selected_services()), 'journal_services')
        require(self.cloud.head() == self.state['source'], 'source_checkout_mismatch')
        if self.state.get('profile') == 'integration-only':
            self.bind_extension(self.state['source'])
            require(self.state.get('control_sha') == self.environ.get('GITHUB_WORKFLOW_SHA'), 'control_source_changed')
            require(self.state.get('inverse') == RESTORED_DEFAULTS, 'saved_inverse_changed')
            require(
                self.state.get('post_wrap_guard', 'internal') in {'internal', 'external'}, 'post_wrap_guard_invalid'
            )
        validate_predecessor(self.state['rollback'])
        saved = self.state['services'][SERVICE]
        revision = saved['revision']
        require(revision['metadata'].get('name') == self.state['rollback'], 'journal_rollback_binding')
        identity(revision, self.state['rollback'])
        require(
            revision['metadata']['labels'].get('serving.knative.dev/service') == SERVICE
            and revision['metadata']['namespace'] == saved['service']['metadata']['namespace'],
            'journal_rollback_binding',
        )
        require(
            traffic(saved['service']['status']['traffic']) == {self.state['rollback']: 100}
            and traffic(
                saved['service']['spec']['traffic'], latest=saved['service']['status'].get('latestReadyRevisionName')
            )
            == {self.state['rollback']: 100},
            'journal_rollback_binding',
        )
        baseline = self.state['baseline']
        require(self.state['baseline_hash'] == digest_bytes(canonical(baseline).encode()), 'baseline_changed')
        return self.state

    def selected_services(self):
        return (SERVICE,) if self.state and self.state.get('profile') == 'integration-only' else SERVICES

    def bind_extension(self, source):
        require(isinstance(source, str) and re.fullmatch(r'[0-9a-f]{40}', source), 'release_binding')
        require(
            self.environ.get('GITHUB_REPOSITORY') == 'BasedHardware/omi'
            and self.environ.get('GITHUB_REF') == 'refs/heads/main'
            and self.environ.get('GITHUB_WORKFLOW_REF')
            == 'BasedHardware/omi/.github/workflows/gcp_backend.yml@refs/heads/main'
            and re.fullmatch(r'[0-9a-f]{40}', self.environ.get('GITHUB_WORKFLOW_SHA', '')),
            'native_workflow_binding',
        )
        with io_budget(60, self.clock):
            self.cloud.prove_source(source)

    def tick(self):
        require(self.clock.monotonic() < self.deadline, 'controller_deadline')

    def integration(self):
        self.tick()
        doc = self.cloud.read('services', SERVICE)
        identity(doc, SERVICE, True)
        original = self.state['services'][SERVICE]['service']
        require(
            doc['metadata']['uid'] == original['metadata']['uid']
            and doc['metadata']['namespace'] == original['metadata']['namespace'],
            'service_replaced',
        )
        return doc

    def prepare(
        self,
        source,
        image,
        candidate,
        project=PROJECT,
        region=REGION,
        integration_only=False,
        post_wrap_guard='internal',
        rollback_revision=ROLLBACK,
    ):
        run, attempt = self.bind()
        validate_predecessor(rollback_revision)
        require(integration_only or rollback_revision == ROLLBACK, 'rollback_profile_binding')
        require((source == SOURCE or integration_only) and project == PROJECT and region == REGION, 'release_binding')
        require(
            post_wrap_guard in {'internal', 'external'} and (integration_only or post_wrap_guard == 'internal'),
            'post_wrap_guard_invalid',
        )
        if integration_only:
            self.bind_extension(source)
            # A fake/captured snapshot is not a live producer. The executable
            # entry point must bind a reviewed authenticated discovery reader;
            # no file or caller-supplied "healthy" switch is accepted here.
            if post_wrap_guard == 'internal':
                require(self.discovery is not None, 'discovery_reader_not_bound')
                self.discovery.preflight(source=source, rollback=rollback_revision)
        require(self.cloud.head() == source, 'source_checkout_mismatch')
        require(
            candidate == f'{SERVICE}-{source[:7]}-{run}-{attempt}'
            and len(candidate) <= 63
            and candidate != rollback_revision,
            'candidate_name_invalid',
        )
        require(not self.journal.path.exists(), 'journal_already_exists')
        image = (
            self.registry.verify(image, source, restored_defaults=True)
            if integration_only
            else self.registry.verify(image, source)
        )
        snapshots = {}
        selected = (SERVICE,) if integration_only else SERVICES
        for service in selected:
            doc = self.cloud.read('services', service)
            identity(doc, service, True)
            if service == SERVICE:
                # A failed latest template can make aggregate Ready=False while
                # the exact retained Ready revision still serves 100%. Never
                # clone that template or waive readiness of the serving revision.
                observed(doc)
            else:
                ready(doc, True)
            actual = traffic(doc.get('status', {}).get('traffic'))
            require(len(actual) == 1, 'split_serving_traffic')
            revision_name = next(iter(actual))
            if service == SERVICE:
                require(revision_name == rollback_revision, 'rollback_not_serving')
            revision = self.cloud.read('revisions', revision_name)
            identity(revision, revision_name)
            require(revision['metadata']['labels']['serving.knative.dev/service'] == service, 'revision_owner_mismatch')
            require(revision['metadata']['namespace'] == doc['metadata']['namespace'], 'revision_namespace_mismatch')
            ready(revision)
            serving_env = env_map(app(revision['spec']).get('env', []))
            if integration_only:
                require(
                    all(serving_env.get(k) == {'name': k, 'value': v} for k, v in RESTORED_DEFAULTS.items()),
                    'saved_inverse_not_200_10',
                )
            require(
                PROVIDER not in serving_env or serving_env[PROVIDER] == {'name': PROVIDER, 'value': 'false'},
                'provider_live_contract',
            )
            # Pin actual names, including any positive latestRevision spec entries.
            require(
                traffic(doc['spec'].get('traffic'), latest=doc['status'].get('latestReadyRevisionName')) == actual,
                'requested_traffic_drift',
            )
            snapshots[service] = {'service': doc, 'revision': revision}
        baseline = self.metrics.collect(30, preflight=True)
        baseline = {k: v for k, v in baseline.items() if k != 'rows'} | {
            'rows': [r.__dict__ for r in baseline['rows']],
        }
        # Detect changes during snapshot/baseline reads before exposing the snapshot to the renderer.
        for service in selected:
            later = self.cloud.read('services', service)
            require(later == snapshots[service]['service'], 'prepare_snapshot_drift')
        self.state = {
            'schema': 1,
            'run_id': run,
            'run_attempt': attempt,
            'source': source,
            'project': project,
            'region': region,
            'candidate': candidate,
            'rollback': rollback_revision,
            'image': image,
            'services': snapshots,
            'baseline': baseline,
            'baseline_hash': digest_bytes(canonical(baseline).encode()),
            'prepared_at': self.clock.time(),
            'phase': 'prepared',
            'intent': None,
            'moves': [],
        }
        if integration_only:
            self.state.update(
                profile='integration-only',
                control_sha=self.environ['GITHUB_WORKFLOW_SHA'],
                inverse=dict(RESTORED_DEFAULTS),
                post_wrap_guard=post_wrap_guard,
            )
        self.journal.save(self.state, create=True)

    def verify_config(self, doc, expected):
        require(service_config(doc) == service_config(expected), 'service_config_drift')

    def retained(self):
        revision = self.cloud.read('revisions', self.state['rollback'])
        require(revision == self.state['services'][SERVICE]['revision'], 'rollback_revision_drift')
        ready(revision)
        return revision

    def verify_revision(self, require_ready=True):
        rev = self.cloud.read('revisions', self.state['candidate'])
        identity(rev, self.state['candidate'])
        old = self.state['services'][SERVICE]['revision']
        require(
            rev['metadata']['namespace'] == old['metadata']['namespace']
            and rev['metadata']['labels'].get('serving.knative.dev/service') == SERVICE,
            'candidate_owner_mismatch',
        )
        if require_ready:
            ready(rev)
        require(
            template_config(rev) == template_config(self.state['plan']['spec']['template']), 'candidate_config_drift'
        )
        require(app(rev['spec'])['image'] == self.state['image'], 'candidate_digest_drift')
        env = contract(app(rev['spec']).get('env', []))
        require(env.get(STAMP) == {'name': STAMP, 'value': self.state['source']}, 'candidate_stamp_drift')
        image = (
            self.registry.verify(self.state['image'], self.state['source'], restored_defaults=True)
            if self.state.get('profile') == 'integration-only'
            else self.registry.verify(self.state['image'], self.state['source'])
        )
        require(image == self.state['image'], 'candidate_source_drift')
        if self.state.get('profile') == 'integration-only':
            require(not set(RESTORED_DEFAULTS) & set(env), 'restored_defaults_drift')
        pinned = self.state.get('candidate_uid')
        require(pinned is None or rev['metadata']['uid'] == pinned, 'candidate_replaced')
        self.state['candidate_uid'] = rev['metadata']['uid']
        return rev

    def candidate(self, runtime_state):
        self.load()
        if self.state['phase'] != 'prepared' or self.state['intent']:
            # Read-only reconciliation can report a landed candidate but NEVER repeat the PUT.
            if self.state.get('plan'):
                doc = self.integration()
                self.verify_config(doc, self.state['plan'])
                self.verify_revision()
                check_traffic(doc, {self.state['rollback']: 100})
            raise Refused('candidate_reuse_refused')
        runtime_services = runtime_state.get('services', {})
        require(set(self.selected_services()) <= set(runtime_services), 'runtime_services_missing')
        for service in self.selected_services():
            contract(runtime_services[service]['env'])
        original = self.state['services'][SERVICE]
        doc = self.integration()
        require(doc == original['service'], 'candidate_prepare_drift')
        old_rev = self.cloud.read('revisions', self.state['rollback'])
        require(old_rev == original['revision'], 'rollback_revision_drift')
        observed(doc)
        ready(old_rev)
        result = copy.deepcopy(doc)
        result['spec']['template'] = template(old_rev, self.state['candidate'])
        ingress = app(result['spec']['template']['spec'])
        live_env = env_map(ingress.get('env', []))
        declared = contract(runtime_services[SERVICE]['env'])
        forbidden = runtime_services[SERVICE].get('forbidden_env', [])
        require(isinstance(forbidden, list) and all(isinstance(k, str) for k in forbidden), 'invalid_forbidden_env')
        require(not set(forbidden) & set(declared), 'forbidden_env_declared')
        require(RETIRED_BATCH_ENV <= set(forbidden), 'retired_batch_env_not_removed')
        if self.state.get('profile') == 'integration-only':
            removals = set(RESTORED_DEFAULTS) | RETIRED_BATCH_ENV
            require(removals <= set(forbidden), 'restored_defaults_not_removed')
            expected = {key: value for key, value in live_env.items() if key not in removals}
            expected.update(
                {
                    key: {'name': key, 'value': value}
                    for key, value in {
                        **QUALITY,
                        PROVIDER: 'false',
                        STAMP: self.state['source'],
                    }.items()
                }
            )
            require(declared == expected, 'unruled_environment_change')
        # Queue routing/ops optimizations and all existing secret references stay live.
        for name, entry in live_env.items():
            protected = 'valueFrom' in entry or 'QUEUE' in name or name.startswith(OPS_PREFIXES)
            named_decision = name in QUALITY or (
                self.state.get('profile') == 'integration-only' and name in {PROVIDER, STAMP}
            )
            if protected and not named_decision and name not in forbidden:
                require(name not in declared or declared[name] == entry, 'serving_ops_env_changed')
        require(live_env.get(PROVIDER, {'value': 'false'}).get('value') == 'false', 'provider_live_contract')
        for name in forbidden:
            live_env.pop(name, None)
        live_env.update(declared)
        live_env[STAMP] = {'name': STAMP, 'value': self.state['source']}
        ingress['env'] = list(live_env.values())
        ingress['image'] = self.state['image']
        result['spec']['template']['metadata']['labels']['commit-sha'] = self.state['source']
        service_account = runtime_services[SERVICE].get('service_account')
        require(
            not service_account or service_account == old_rev['spec'].get('serviceAccountName'),
            'service_account_changed',
        )
        # Pin positive traffic and preserve all zero-percent named tags.
        result['spec']['traffic'] = self.traffic_plan(doc, 0)
        self.state['plan'] = result
        self.mutate(doc, result, 'candidate')
        # Candidate readiness/acceptance remains the native workflow's next step.
        self.state['phase'] = 'candidate_written'
        self.save()

    def traffic_plan(self, doc, percent):
        zero = [copy.deepcopy(t) for t in doc['spec']['traffic'] if t.get('percent', 0) == 0]
        for row in zero:
            require(row.get('revisionName') and not row.get('latestRevision'), 'tag_not_named')
        targets = expected_traffic(percent, self.state['candidate'], self.state['rollback'])
        # Preserve tags attached to positive targets by retaining their named zero alias.
        tags = {t.get('tag') for t in zero if t.get('tag')}
        for row in doc['spec']['traffic']:
            if row.get('percent', 0) > 0 and row.get('tag') and row['tag'] not in tags:
                alias = copy.deepcopy(row)
                alias['percent'] = 0
                if alias.pop('latestRevision', False):
                    serving = doc.get('status', {}).get('latestReadyRevisionName')
                    require(isinstance(serving, str) and bool(serving), 'traffic_not_named')
                    alias['revisionName'] = serving
                require(alias.get('revisionName'), 'tag_not_named')
                zero.append(alias)
                tags.add(row['tag'])
        return [{'revisionName': name, 'percent': pct} for name, pct in targets.items()] + zero

    def mutate(self, before, after, kind):
        self.tick()
        require(self.state['intent'] is None, 'uncertain_write_refused')
        body = write_body(after)
        require(body['metadata']['resourceVersion'] == before['metadata']['resourceVersion'], 'cas_version_mismatch')
        self.state['intent'] = {
            'kind': kind,
            'before': before,
            'after': after,
            'at': self.clock.time(),
            'status': 'uncertain',
        }
        self.save()  # Durable intent BEFORE a single write attempt, even if response is lost.
        self.cloud.put(body)
        # No exception handler retries a failed/uncertain write.
        self.state['intent']['status'] = 'submitted'
        self.save()
        if kind == 'candidate':
            landed = self.integration()
            self.verify_config(landed, after)
            check_traffic(landed, {self.state['rollback']: 100})
            self.state['known'] = landed
            self.state['intent'] = None
            self.save()

    def verified(self, expected, percent, check_generation=True):
        doc = self.integration()
        self.verify_config(doc, expected)
        if check_generation:
            require(doc['metadata'].get('generation') == expected['metadata'].get('generation'), 'foreign_generation')
        ready(doc, True)
        check_traffic(doc, expected_traffic(percent, self.state['candidate'], self.state['rollback']))
        self.retained()
        self.verify_revision()
        require(
            doc['status'].get('latestCreatedRevisionName') == self.state['candidate']
            and doc['status'].get('latestReadyRevisionName') == self.state['candidate'],
            'candidate_not_latest_ready',
        )
        return doc

    def move(self, percent):
        old_percent = 0 if percent == 25 else 25
        before = self.verified(self.state['known'], old_percent)
        after = copy.deepcopy(before)
        after['spec']['traffic'] = self.traffic_plan(before, percent)
        self.mutate(before, after, f'traffic_{percent}')
        stop = min(self.deadline, self.clock.monotonic() + 120)
        while True:
            # Traffic convergence may lag a successful PUT. Only read; never retry it.
            doc = self.integration()
            self.verify_config(doc, after)
            actual = traffic(doc.get('status', {}).get('traffic'))
            require(
                actual
                in (
                    expected_traffic(old_percent, self.state['candidate'], self.state['rollback']),
                    expected_traffic(percent, self.state['candidate'], self.state['rollback']),
                ),
                'traffic_convergence_drift',
            )
            if actual == expected_traffic(percent, self.state['candidate'], self.state['rollback']):
                doc = self.verified(after, percent, check_generation=False)
                break
            require(self.clock.monotonic() < stop, 'traffic_readback_timeout')
            self.clock.sleep(5)
        anchor = self.clock.time()
        self.state['moves'].append({'percent': percent, 'verified_at': anchor})
        self.state.update(
            known=doc, intent=None, phase=f'traffic_{percent}', moved_at=anchor, moved_monotonic=self.clock.monotonic()
        )
        self.move_monotonic = self.clock.monotonic()
        self.save()

    def sample(self, percent):
        self.tick()
        doc = self.verified(self.state['known'], percent)
        evidence = self.metrics.collect()
        verdict = decision(
            evidence['rows'],
            moved_at=self.state['moved_at'],
            now=self.clock.time(),
            baseline_share=self.state['baseline']['share'],
            end=evidence['end'],
        )
        self.state.update(known=doc, health=verdict, metrics_read_at=evidence['read_at'])
        self.save()
        # Constant receipt only: never print metadata, provider errors, env, argv, or tokens.
        print('integration_canary: ' + verdict['state'], flush=True)
        if verdict['state'] == 'rollback':
            self.rollback(loaded=True)
            raise Refused('qualified_health_rollback')
        return verdict

    def observe(self, percent, seconds):
        # Persisted wall anchor describes the observation; monotonic time bounds waits.
        # Promotion and observation belong to this foreground invocation; wall
        # clock corrections cannot shorten its five-minute verified hold.
        require(hasattr(self, 'move_monotonic'), 'monotonic_move_anchor_missing')
        stop = self.move_monotonic + seconds
        while True:
            self.sample(percent)
            remaining = stop - self.clock.monotonic()
            if remaining <= 0:
                return
            self.clock.sleep(min(60, remaining))

    def promote(self):
        self.load()
        require(self.state.get('profile') != 'integration-only', 'use_scoped_continuation')
        require(self.state['phase'] == 'candidate_written' and self.state['intent'] is None, 'promotion_reuse_refused')
        self.verified(self.state['known'], 0)
        self.metrics.collect(30, preflight=True)  # Refresh headroom, NEVER replace the pinned baseline.
        self.move(25)
        self.observe(25, 300)
        # Actual complete minute coverage has just been read. The 10m health rule
        # remains immature at +5m; the captain separately permits this transition.
        self.move(100)
        self.observe(100, 1200)
        require(self.state['health']['state'] == 'below_threshold', 'final_window_immature')
        self.state['phase'] = 'complete'
        self.save()

    def continuation_anchor(self):
        wall = self.clock.time() - self.state['moved_at']
        elapsed = self.clock.monotonic() - self.state['moved_monotonic']
        require(wall >= 0 and elapsed >= 0 and abs(wall - elapsed) <= 5, 'continuation_clock_changed')
        self.move_monotonic = self.state['moved_monotonic']
        return elapsed

    def stage(self):
        """One 25% CAS, then the persisted five-minute verified hold.

        Re-entry after an interrupted read/hold is read-only until the hold is
        proved. An uncertain mutation intent never authorizes a second PUT.
        """
        self.load()
        require(
            self.state.get('profile') == 'integration-only' and self.state['intent'] is None, 'scoped_stage_binding'
        )
        require(self.state['phase'] in ('candidate_written', 'traffic_25', 'held_25'), 'stage_phase_invalid')
        if self.state['phase'] == 'candidate_written':
            self.verified(self.state['known'], 0)
            self.metrics.collect(30, preflight=True)
            self.move(25)
        self.verified(self.state['known'], 25)
        self.continuation_anchor()
        self.observe(25, 300)
        self.state.update(phase='held_25', hold_verified_at=self.clock.time())
        self.save()

    def complete(self):
        """Continue the same workflow/run and retained inverse to 100%.

        CPU/request acceptance and the post-wrap discovery window are separate
        proofs. A twenty-minute HTTP watch is never a discovery-window pass.
        """
        self.load()
        require(
            self.state.get('profile') == 'integration-only' and self.state['intent'] is None, 'scoped_complete_binding'
        )
        require(self.state['phase'] in ('held_25', 'traffic_100', 'awaiting_postwrap'), 'complete_phase_invalid')
        external = self.state.get('post_wrap_guard', 'internal') == 'external'
        require(external or self.discovery is not None, 'discovery_reader_not_bound')
        if self.state['phase'] == 'held_25':
            require(self.continuation_anchor() >= 300, 'verified_hold_incomplete')
            self.verified(self.state['known'], 25)
            self.metrics.collect(30, preflight=True)
            self.move(100)
        self.verified(self.state['known'], 100)
        self.continuation_anchor()
        self.observe(100, 1200)
        require(self.state['health']['state'] == 'below_threshold', 'final_window_immature')
        self.state['phase'] = 'awaiting_postwrap'
        self.save()
        if external:
            # Captain 08:22: Pipeline's read-only guard owns the subsequent
            # wrap/recount/progress window. This handoff is not a guard pass.
            self.state.update(
                phase='external_guard_pending',
                external_handoff=self.receiving_binding()
                | {
                    'traffic_percent': 100,
                    'sweep_page_rows': 100,
                    'tick_seconds': 20,
                    'provider_release': False,
                    'rollback_revision': self.state['rollback'],
                },
                discovery={'state': 'external_pending', 'owner': 'SCA-2015', 'rollback_executor': 'SCA-2283'},
            )
            self.save()
            return
        while not self.guard():
            self.tick()
            self.clock.sleep(60)

    def guard(self):
        self.load()
        require(self.state.get('post_wrap_guard', 'internal') == 'internal', 'post_wrap_guard_external')
        require(
            self.state.get('profile') == 'integration-only'
            and self.state['phase'] in ('awaiting_postwrap', 'complete')
            and self.state['intent'] is None,
            'scoped_guard_binding',
        )
        require(self.discovery is not None, 'discovery_reader_not_bound')
        self.sample(100)
        binding = self.receiving_binding()
        # This is an internal adapter boundary, not a file/boolean CLI. Its
        # authenticated producer must bind originating artifact digests, the
        # complete participating committer vector, post-receiving positive wrap,
        # bounded complete recount and existing progress guard semantics. No
        # census TTL, proxy metric or guard threshold is invented here. The CLI
        # intentionally has no such live adapter until SCA-2015 establishes it.
        verdict = self.discovery.collect(binding=binding)
        require(
            isinstance(verdict, dict) and verdict.get('binding_sha256') == digest_bytes(canonical(binding).encode()),
            'discovery_binding_mismatch',
        )
        require(
            verdict.get('state') in {'awaiting_receipt', 'unavailable', 'rollback', 'qualified'},
            'discovery_decision_invalid',
        )
        require(
            isinstance(verdict.get('artifact_digests'), list)
            and len(verdict['artifact_digests']) <= 16
            and all(isinstance(value, str) and DIGEST.fullmatch(value) for value in verdict['artifact_digests'])
            and len(verdict['artifact_digests']) == len(set(verdict['artifact_digests'])),
            'discovery_artifact_identity_missing',
        )
        if verdict['state'] in {'qualified', 'rollback'}:
            require(bool(verdict['artifact_digests']), 'discovery_artifact_identity_missing')
        # Persist only the counts-free adapter decision and immutable references,
        # never an arbitrary producer payload in the sanitized receipt.
        self.state['discovery'] = {key: verdict[key] for key in ('state', 'binding_sha256', 'artifact_digests')}
        if verdict['state'] == 'rollback':
            self.save()
            self.rollback(loaded=True)
            raise Refused('discovery_guard_rollback')
        if verdict['state'] != 'qualified':
            self.state['phase'] = 'awaiting_postwrap'
            self.save()
            return False
        self.state['phase'] = 'complete'
        self.save()
        return True

    def receiving_binding(self):
        """Metadata-only receiving generation, never the private environment."""
        return {
            'project': PROJECT,
            'region': REGION,
            'service': SERVICE,
            'source': self.state['source'],
            'image': self.state['image'],
            'revision': self.state['candidate'],
            'revision_uid': self.state['candidate_uid'],
            'generation': self.state['known']['metadata']['generation'],
            'config_sha256': digest_bytes(canonical(service_config(self.state['known'])).encode()),
            'run_id': self.state['run_id'],
            'run_attempt': self.state['run_attempt'],
            'control_sha': self.state['control_sha'],
            'receiving_verified_at': self.state['moved_at'],
        }

    def rollback(self, loaded=False):
        if not loaded:
            self.load()
        doc = self.integration()
        original = self.state['services'][SERVICE]
        self.retained()
        pending = self.state.get('intent')
        if pending and pending['kind'] == 'traffic_25':
            # A lost response plus the exact pre-write 0% snapshot cannot prove
            # the remote request has finished. A no-op here would acknowledge a
            # rollback while an in-flight CAS could still land 25% afterwards.
            require(service_config(doc) != service_config(pending['before']), 'unsettled_promotion_refused')
        # A failure can occur before candidate creation. The exact prepare snapshot
        # is an idempotent no-op; no candidate read should then be required.
        if service_config(doc) == service_config(original['service']):
            observed(doc)
            check_traffic(doc, {self.state['rollback']: 100})
            self.state.update(phase='rolled_back', intent=None, known=doc)
            self.save()
            return
        require(self.state.get('plan'), 'rollback_without_plan')
        allowed = [self.state.get('known')]
        intent = self.state.get('intent')
        if intent:
            allowed.extend([intent['before'], intent['after']])
        matching = [d for d in allowed if d and service_config(d) == service_config(doc)]
        require(bool(matching), 'rollback_foreign_writer')
        generations = {d['metadata'].get('generation') for d in matching}
        if intent and service_config(doc) == service_config(intent['after']):
            generations.add(intent['before']['metadata']['generation'] + 1)
        require(doc['metadata'].get('generation') in generations, 'rollback_foreign_generation')
        actual = traffic(doc.get('status', {}).get('traffic'))
        require(
            actual in [expected_traffic(p, self.state['candidate'], self.state['rollback']) for p in (0, 25, 100)],
            'rollback_foreign_traffic',
        )
        requested = traffic(doc['spec']['traffic'], True)
        if requested == actual == {self.state['rollback']: 100}:
            # A failed latest candidate can make service Ready=False even while
            # the retained Ready revision serves 100%; this is already restored.
            observed(doc)
            self.state.update(phase='rolled_back', intent=None, known=doc)
            self.save()
            return
        require(not intent or intent['kind'] != 'rollback', 'uncertain_rollback_refused')
        self.verify_revision(require_ready=False)
        # Uncertain promotions may only be compensated from their exact known
        # before/after config. This is a new, journalled rollback CAS, never replay.
        if intent:
            self.state.setdefault('reconciled_intents', []).append(intent)
            self.state['intent'] = None
        after = copy.deepcopy(doc)
        after['spec']['traffic'] = self.traffic_plan(doc, 0)
        self.mutate(doc, after, 'rollback')
        stop = min(self.deadline, self.clock.monotonic() + 120)
        while True:
            current = self.integration()
            self.verify_config(current, after)
            actual_seen = traffic(current.get('status', {}).get('traffic'))
            require(actual_seen in (actual, {self.state['rollback']: 100}), 'rollback_convergence_drift')
            if actual_seen == {self.state['rollback']: 100}:
                # Service Ready may describe the failed latest candidate. Prove
                # the retained revision itself is Ready and the service observed
                # this generation's exact traffic request.
                observed(current)
                self.retained()
                check_traffic(current, {self.state['rollback']: 100})
                break
            require(self.clock.monotonic() < stop, 'rollback_readback_timeout')
            self.clock.sleep(5)
        self.state.update(phase='rolled_back', intent=None, known=current, rollback_verified_at=self.clock.time())
        self.save()

    def failure_receipt(self):
        if self.state:
            self.state['operator_receipt'] = {
                'at': self.clock.time(),
                'phase': self.state.get('phase'),
                'write': 'uncertain' if self.state.get('intent') else 'none_pending',
                'action': 'Use workflow failure-path rollback with this private journal; '
                'if refused, retain lock/evidence for release-owner inspection. Never replay a write.',
            }
            self.save()


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused('invalid_cli_arguments')


def main(argv=None):
    controller = None
    old_handlers = {}
    try:
        parser = SafeParser(description=__doc__)
        commands = parser.add_subparsers(dest='step', required=True, parser_class=SafeParser)
        for name in ('prepare', 'candidate', 'promote', 'rollback', 'stage', 'complete', 'guard'):
            sub = commands.add_parser(name)
            sub.add_argument('--state', required=True, type=Path)
            if name == 'prepare':
                for option in ('source', 'image', 'candidate'):
                    sub.add_argument('--' + option, required=True)
                sub.add_argument('--project', default=PROJECT)
                sub.add_argument('--region', default=REGION)
                sub.add_argument('--integration-only', action='store_true')
                sub.add_argument('--post-wrap-guard', choices=('internal', 'external'), default='internal')
                sub.add_argument('--rollback-revision', default=ROLLBACK)
            if name == 'candidate':
                sub.add_argument('--runtime-state', required=True, type=Path)
        args = parser.parse_args(argv)

        def cancel(_signum, _frame):
            raise InterruptedError('cancelled')

        for sig in (signal.SIGTERM, signal.SIGALRM):
            old_handlers[sig] = signal.signal(sig, cancel)
        signal.setitimer(signal.ITIMER_REAL, 2700)
        transport = Transport()
        with Journal(args.state) as journal:
            controller = Controller(journal, Cloud(transport), Registry(transport), Metrics(transport))
            try:
                controller.bind()
                if args.step == 'prepare':
                    controller.prepare(
                        args.source,
                        args.image,
                        args.candidate,
                        args.project,
                        args.region,
                        integration_only=args.integration_only,
                        post_wrap_guard=args.post_wrap_guard,
                        rollback_revision=args.rollback_revision,
                    )
                elif args.step == 'candidate':
                    with args.runtime_state.open('rb') as handle:
                        raw = handle.read(MAX_STATE + 1)
                    require(len(raw) <= MAX_STATE, 'runtime_state_too_large')
                    controller.candidate(decode(raw))
                else:
                    result = getattr(controller, args.step)()
                    if args.step == 'guard' and result is False:
                        print('integration_canary: postwrap_window_unproved', flush=True)
                        return 3
            except (Exception, KeyboardInterrupt):
                # Keep the lock through the failure receipt so a cancellation
                # rollback cannot race a stale journal overwrite.
                try:
                    controller.failure_receipt()
                except Exception:
                    pass
                raise
        print('integration_canary: step_complete', flush=True)
        return 0
    except (Exception, KeyboardInterrupt):
        # Do not serialize exception text: libraries may include credentials or payloads.
        print(
            'integration_canary: refused; retain private journal and use workflow rollback; '
            'uncertain writes must not be replayed',
            file=sys.stderr,
            flush=True,
        )
        return 1
    finally:
        if old_handlers:
            signal.setitimer(signal.ITIMER_REAL, 0)
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)


if __name__ == '__main__':
    raise SystemExit(main())
