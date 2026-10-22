#!/usr/bin/env python3
"""Read-only runtime-config drift check: serving workloads versus the repository.

What is compared
  * Cloud Run: the revisions that actually serve traffic (``status.traffic``),
    never ``spec.template``. A ``services update`` against a traffic-pinned
    service creates a 0%-traffic revision whose template looks "fixed" while
    nothing serves it (the 2026-10-18 23:50Z misread).
  * GKE (``--gke``): the ReplicaSets of each Deployment that currently hold
    ready pods (listen, pusher, batch-pipeline-worker), never only the
    Deployment template.
  * ``envFrom``: the ConfigMaps a GKE container bulk-loads through ``envFrom``
    are resolved (live read or offline fixture) and their keys join the same
    name/hash comparison, so a missing or out-of-date ConfigMap key is visible
    instead of a silent ``OK``. Unresolvable references report ``INVENTORY``.
    Live reads cannot prove the current ConfigMap data matches what already
    running pods resolved at container start, so live envFrom keys compare as
    ``INVENTORY`` (offline fixtures are snapshots and compare exactly) — but a
    key the serving ReplicaSet sets through an explicit ``env`` entry shadows
    ``envFrom`` and is always compared, proven or not. envFrom references are
    compared per serving target (never as a union across a mixed rollout), and
    a reference identity carries its prefix and optionality. When several
    expected sources export the same key, the value comparison honors K8s
    last-source-wins: a key whose effective source is a reference the
    repository cannot enumerate (external ConfigMap) is not compared against
    the repository ConfigMap's manifest digest.
  * Explicit ``valueFrom.configMapKeyRef`` bindings compare by reference
    identity (ConfigMap name, key, optionality) in addition to name. The
    immutable pod spec proves the binding, so a rollout that rebinds a key to
    a different ConfigMap or key is drift; only when the binding matches does
    the key stay value-unproven on a live read (the ConfigMap data the
    container resolved at start cannot be re-read; K8s requires a pod restart).

Each serving target's application-container env is compared with the
expected env (``runtime_env.yaml`` / rendered deploy state for Cloud Run,
the chart's Helm values for GKE — including deploy-time override inputs via
``--gke-helm-arg`` / ``--gke-helm-arg-file`` so an intentionally overridden
rollout is not reported as drift) by key name *and* by a truncated SHA-256 of
the value or secret reference. Values are never printed; hashes of keys whose
names look sensitive (UIDs, allowlists, secrets, tokens) are redacted too.

By default this is a non-blocking visibility report (exit 0). ``--strict``
exits 1 on drift and 2 on fetch/render errors, for use as a train post-gate;
when drift and fetch errors coexist, ``2`` wins (the comparison did not
complete).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Callable, Mapping, Sequence, cast

import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_backend_runtime_env  # noqa: E402
from attach_cloud_run_gmp_sidecar import SIDECAR_NAME  # noqa: E402
from runtime_env_validation.common import compute_project  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / 'backend/deploy/runtime_env.yaml'
DEFAULT_REGION = 'us-central1'
DEFAULT_SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')
HASH_LENGTH = 12
REDACTED_HASH = 'redacted'
# Marks a ConfigMap lookup that returned NotFound under an optional reference;
# distinct from a real empty mapping so required references still fail.
_NOT_FOUND_SENTINEL = object()
# Case-insensitive: env keys are conventionally uppercase, but lowercase and
# mixed-case names (api_key, dbPassword) are equally credentials whose digests
# must not be published. ``_KEY`` (not just ``API_KEY``) covers credential-like
# bindings declared as secrets in the manifest (ADMIN_KEY, FAL_KEY), and the
# explicit ``OAUTH`` alternative covers credential-bearing blobs such as
# MCP_OAUTH_CLIENTS_JSON that no ``_KEY`` suffix would catch. ``SALT`` covers
# salt-named credentials declared as secrets in the manifest
# (DREAM_AGENT_FEEDBACK_SALT): a binding accidentally deployed as a literal
# would otherwise publish a digest candidate salts can be tested against.
_SENSITIVE_KEY_RE = re.compile(
    r'(UID|ALLOWLIST|SECRET|TOKEN|PASSWORD|CREDENTIAL|API_KEY|PRIVATE|OAUTH|_KEY|SALT)', re.IGNORECASE
)

# Keys intentionally set outside backend/deploy/runtime_env.yaml (for example,
# per-revision provenance markers, sidecar ports attached post-deploy, or
# live-managed canary UID allowlists that must not live in the public repo).
LIVE_MANAGED_ENV_ALLOWLIST: dict[str, frozenset[str]] = {
    '*': frozenset(
        {
            'BATCH_PIPELINE_UID_ALLOWLIST',
        }
    ),
    'backend': frozenset(
        {
            'OMI_BACKEND_RELEASE_SHA',
        }
    ),
    'backend-sync': frozenset(
        {
            'FIRST_SUMMARY_UID_ALLOWLIST',
            'SYNC_BACKFILL_ORDER_UID_ALLOWLIST',
            'FAIR_USE_EXEMPT_UIDS',
            'DREAM_AGENT_FULL_CONTEXT_UIDS',
        }
    ),
    'backend-sync-backfill': frozenset(
        {
            'FIRST_SUMMARY_UID_ALLOWLIST',
            'SYNC_BACKFILL_ORDER_UID_ALLOWLIST',
            'FAIR_USE_EXEMPT_UIDS',
            'DREAM_AGENT_FULL_CONTEXT_UIDS',
        }
    ),
    'backend-integration': frozenset(
        {
            'FIRST_SUMMARY_UID_ALLOWLIST',
        }
    ),
}


@dataclass(frozen=True)
class GkeWorkload:
    chart: str
    values_file: str  # formatted with env=
    deployment: str  # formatted with env=
    container: str
    # Image pins only satisfy the chart's render-time guards; they never reach the env.
    helm_image_args: tuple[str, ...] = ('image.tag=drift-check', 'image.digest=')
    # True when the chart template builds envFrom solely from
    # ``runtimeConfigMapName`` and ignores ``.Values.envFrom`` (the pusher
    # template). Values mode must then read the same field the template reads,
    # or a renamed runtime ConfigMap with a stale leftover ``envFrom`` value
    # would flag a correctly rendered rollout as reference drift.
    envfrom_from_runtime_config_map: bool = False


GKE_WORKLOADS: dict[str, GkeWorkload] = {
    'backend-listen': GkeWorkload(
        chart='backend/charts/backend-listen',
        values_file='backend/charts/backend-listen/{env}_omi_backend_listen_values.yaml',
        deployment='{env}-omi-backend-listen',
        container='backend-listen',
    ),
    'pusher': GkeWorkload(
        chart='backend/charts/pusher',
        values_file='backend/charts/pusher/{env}_omi_pusher_values.yaml',
        deployment='{env}-omi-pusher',
        container='pusher',
        # The pusher deployment template ignores .Values.envFrom and always
        # constructs envFrom from runtimeConfigMapName.
        envfrom_from_runtime_config_map=True,
    ),
    'batch-pipeline-worker': GkeWorkload(
        chart='backend/charts/batch-pipeline-worker',
        values_file='backend/charts/batch-pipeline-worker/{env}_omi_batch-pipeline-worker_values.yaml',
        deployment='{env}-omi-batch-pipeline-worker',
        container='worker',
        helm_image_args=('image.digest=sha256:' + '0' * 64,),
    ),
}
DEFAULT_GKE_WORKLOADS = tuple(GKE_WORKLOADS)

# name -> value hash, or None when the expected value is not knowable offline
# (for example a deploy-time ``env_var`` binding with no rendered state).
ExpectedEnv = dict[str, str | None]
LiveEnv = dict[str, str]


@dataclass(frozen=True)
class ValueMismatch:
    key: str
    expected_hash: str
    live_hash: str
    target: str


@dataclass(frozen=True)
class ServingTarget:
    """One serving revision (Cloud Run) or ready ReplicaSet (GKE)."""

    name: str
    weight: int  # traffic percent (Cloud Run) or ready replicas (GKE)
    key_count: int
    fingerprint: str
    display_fingerprint: str = ''  # redacted form; the only one safe to publish
    # Keys this target sets through explicit ``env`` entries. Explicit entries
    # shadow ``envFrom`` (K8s precedence) and the serving spec is immutable, so
    # their values stay knowable even when live ConfigMap data is unproven.
    explicit_keys: frozenset[str] = frozenset()
    # ``key -> configMapKeyRef identity hash`` for this target's explicit
    # ``valueFrom.configMapKeyRef`` bindings (live reads only; ``{}`` when the
    # binding identities are not tracked). The immutable pod spec proves the
    # reference, so a binding whose identity hash differs from the expected one
    # is drift even though the resolved ConfigMap value is unknowable.
    explicit_keyref_hashes: Mapping[str, str] = field(default_factory=dict)
    # envFrom ConfigMap references (identity includes prefix and optionality)
    # declared by this target's spec. Compared per target, never unioned: in a
    # mixed rollout the ReplicaSets that serve side by side may disagree.
    envfrom_refs: tuple[str, ...] = ()
    # References on this target whose ConfigMap data could not be read or
    # cannot be proven for the running pods. Expected envFrom keys are excused
    # from missing assertions only on targets that hold such a reference.
    envfrom_degraded_refs: frozenset[str] = frozenset()
    # envFrom-only keys of this target: contributed by ConfigMaps whose current
    # live data cannot be proven for the running pods (K8s never refreshes
    # envFrom). Their presence in ``env_map`` is evidence of nothing, so they
    # are excluded from live-only drift assertions for this target.
    unproven_envfrom_keys: frozenset[str] = frozenset()
    # (reference identity -> prefixed keys it contributed), for references whose
    # data was readable. Used to excuse keys of expected sources the repository
    # cannot enumerate when the serving target holds the same reference.
    envfrom_key_contributions: tuple[tuple[str, frozenset[str]], ...] = ()
    # envFrom-only keys whose effective value a later opaque Secret source may
    # override (K8s last-source-wins; Secret contents are never read). They
    # cannot be value-proven from the earlier known source's data, so they
    # degrade to INVENTORY instead of asserting the snapshot value.
    opaque_shadowed_keys: frozenset[str] = frozenset()
    # Cloud Run keys whose live secret reference was rewritten from the
    # revision's ``run.googleapis.com/secrets`` annotation, mapped to a
    # segment-preserving comparison form (see ``_secret_ref_form``). The
    # platform normalizes the project segment to a number while repository
    # state may carry the project ID or the bare name: only a genuine
    # ID-vs-number/implicit form difference degrades to INVENTORY; unequal
    # projects, names or versions stay real drift. A matching full hash proves OK.
    alias_ref_forms: Mapping[str, str] = field(default_factory=dict)
    # Explicit env keys bound through ``valueFrom.configMapKeyRef`` (live reads
    # only). The immutable pod spec proves the binding, but the value the
    # container resolved at start cannot be re-read: K8s requires a pod restart
    # to pick up ConfigMap changes, so a matching reference hash is not proof
    # the data matches. These keys report INVENTORY, never a verified OK.
    explicit_unproven_keys: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ServiceEnvDrift:
    service: str
    manifest_key_count: int
    live_key_count: int
    allowlisted_live_only: tuple[str, ...]
    unallowlisted_live_only: tuple[str, ...]
    error: str | None = None
    platform: str = 'cloud_run'
    source: str = 'serving'  # serving | snapshot (offline env-only fixture)
    serving: tuple[ServingTarget, ...] = ()
    value_mismatches: tuple[ValueMismatch, ...] = ()
    missing_from_live: tuple[str, ...] = ()
    value_unchecked_keys: int = 0
    template_name: str | None = None
    template_matches_serving: bool | None = None
    expected_available: bool = True
    envfrom_refs: tuple[str, ...] = ()  # expected envFrom ConfigMap references
    envfrom_mismatched_refs: tuple[str, ...] = ()  # live vs expected reference drift
    envfrom_unresolved: tuple[str, ...] = ()  # references whose keys could not be compared
    envfrom_unproven: tuple[str, ...] = ()  # live refs whose data may differ from running pods' env
    # Explicit env keys bound through configMapKeyRef whose value comparison was
    # skipped on a live read: the spec proves the binding, never the data the
    # container resolved at start (ConfigMap updates need a pod restart).
    explicit_unproven_keys: tuple[str, ...] = ()
    # Cloud Run keys whose alias-resolved secret reference is form-ambiguous
    # (annotation project number vs repository project ID): value comparison
    # skipped, reported as unchecked (INVENTORY).
    alias_unproven_keys: tuple[str, ...] = ()

    @property
    def has_drift(self) -> bool:
        return bool(
            self.unallowlisted_live_only
            or self.value_mismatches
            or self.missing_from_live
            or self.envfrom_mismatched_refs
        )

    @property
    def status(self) -> str:
        if self.error:
            return 'ERROR'
        if self.has_drift:
            return 'DRIFT'
        if (
            not self.expected_available
            or self.envfrom_unresolved
            or self.envfrom_unproven
            or self.explicit_unproven_keys
            or self.alias_unproven_keys
        ):
            return 'INVENTORY'
        return 'OK'


# ── hashing ─────────────────────────────────────────────────────────────────


def value_hash(kind: str, payload: str) -> str:
    """Truncated SHA-256 of a typed value; the raw value never leaves this function."""
    return hashlib.sha256(f'omi-env-v1\0{kind}\0{payload}'.encode('utf-8')).hexdigest()[:HASH_LENGTH]


def _secret_ref_hash(resource: str, version: str, *, optional: bool = False) -> str:
    # A project-qualified Secret Manager reference keeps its project so rebinding
    # projects/a/secrets/x to projects/b/secrets/x is a visible hash change; a bare
    # native-secret name hashes by name only, as before. ``optional`` joins the
    # digest (normalized) so a chart/serving difference in optionality is drift.
    ref = resource if '/' in resource else resource.rsplit('/', 1)[-1]
    suffix = ':optional' if optional else ''
    return value_hash('secret', f'{ref}:{version or "latest"}{suffix}')


_PROJECT_SECRET_RE = re.compile(r'^projects/(?P<project>[^/]+)/secrets/(?P<name>[^/]+)$')


def _secret_ref_form(resource: str, version: str) -> str:
    """Canonical comparison form ``project\\0name\\0version`` for a secret reference.

    The form keeps every segment: the alias comparison decides per segment
    which differences are provable (see ``_alias_mismatch_is_form_ambiguous``).
    A non-matching resource (a bare name) keeps the whole string as the name.
    """
    match = _PROJECT_SECRET_RE.match(resource)
    if match:
        return f'{match.group("project")}\x00{match.group("name")}\x00{version or "latest"}'
    return f'\x00{resource}\x00{version or "latest"}'


def _alias_mismatch_is_form_ambiguous(expected_form: str, live_form: str) -> bool:
    """Whether an expected/live secret-reference mismatch is only a form difference.

    The platform normalizes the project segment of the
    ``run.googleapis.com/secrets`` annotation to a project *number* while
    repository state may carry the project *ID* or the bare name (the
    service's own project is implicit). Only that ambiguity is unprovable:
    a project *number* versus a project *ID* (in either direction), or an
    implicit bare name versus a qualified reference. Two different project
    *numbers*, two different project IDs, or any name/version difference are
    provably different references (real drift).
    """
    expected_project, _, expected_rest = expected_form.partition('\x00')
    live_project, _, live_rest = live_form.partition('\x00')
    if expected_rest != live_rest:
        return False  # secret name or version differs: real drift
    if expected_project == live_project:
        return True  # identical reference; nothing provably differs
    if not expected_project or not live_project:
        return True  # implicit (bare-name) project vs qualified: form ambiguity
    if expected_project.isdigit() != live_project.isdigit():
        return True  # project ID vs project number: the platform-normalized form
    return False  # two different numbers or two different IDs: provably different projects


def env_entry_hash(entry: Mapping[str, Any]) -> str:
    """Hash one Kubernetes-shaped env entry ({name, value} or {name, valueFrom})."""
    value_from = entry.get('valueFrom')
    if isinstance(value_from, Mapping):
        secret = value_from.get('secretKeyRef')
        if isinstance(secret, Mapping):
            return _secret_ref_hash(
                str(secret.get('name', '')), str(secret.get('key', '')), optional=bool(secret.get('optional'))
            )
        config_map = value_from.get('configMapKeyRef')
        if isinstance(config_map, Mapping):
            optional = ':optional' if config_map.get('optional') else ''
            return value_hash('configmap', f'{config_map.get("name", "")}:{config_map.get("key", "")}{optional}')
        field_ref = value_from.get('fieldRef')
        if isinstance(field_ref, Mapping):
            # The API server adds apiVersion: v1 to fieldRef; Helm output omits it.
            return value_hash('field', str(field_ref.get('fieldPath', '')))
        return value_hash('valueFrom', json.dumps(value_from, sort_keys=True, separators=(',', ':')))
    raw = entry.get('value')
    return value_hash('value', '' if raw is None else str(raw))


def env_fingerprint(env: Mapping[str, str], *, redacted: bool = False) -> str:
    # `redacted` swaps sensitive-key hashes for a placeholder before hashing, so a
    # published fingerprint cannot be brute-forced against candidate sensitive
    # values; the full fingerprint stays internal for equality checks only.
    parts = [
        f'{name}={REDACTED_HASH if redacted and _SENSITIVE_KEY_RE.search(name) else env[name]}' for name in sorted(env)
    ]
    return value_hash('env-set', '\n'.join(parts))


def display_hash(key: str, digest: str) -> str:
    return REDACTED_HASH if _SENSITIVE_KEY_RE.search(key) else digest


def _envfrom_sources(container: Mapping[str, Any] | None) -> tuple[tuple[str, str, bool], ...]:
    """``(name, prefix, optional)`` for each envFrom ConfigMap source on one container.

    ``envFrom.secretRef`` sources are absent from this tuple by design: the
    checker never reads Secret contents. They are tracked separately (see
    ``_envfrom_source_descriptors``) as unresolved identities so an unexpected
    serving Secret cannot silently inject env without changing the comparison.
    """
    if not isinstance(container, Mapping):
        return ()
    sources: list[tuple[str, str, bool]] = []
    for source in container.get('envFrom') or []:
        if not isinstance(source, Mapping):
            continue
        ref = source.get('configMapRef')
        name = ref.get('name') if isinstance(ref, Mapping) else None
        if isinstance(name, str) and name:
            prefix = source.get('prefix')
            # Omitted `optional` normalizes to false: a missing ConfigMap blocks
            # the expected pod by default, so optionality changes the meaning of
            # the reference and belongs in its identity.
            optional = isinstance(ref, Mapping) and ref.get('optional') is True
            sources.append((name, prefix if isinstance(prefix, str) else '', optional))
    # Duplicates are preserved: the K8s API resolves the last envFrom source
    # when several export the same key, so `A, B, A` and `A, B` are different
    # effective environments, not the same set of references.
    return tuple(sources)


def _envfrom_source_descriptors(container: Mapping[str, Any] | None) -> tuple[tuple[str, bool, str, str, bool], ...]:
    """``(identity, is_secret, name, prefix, optional)`` for every envFrom source, in spec order.

    ConfigMap identities are the bare name; Secret identities are
    ``secret:<name>`` so the two namespaces cannot collide. Secret sources are
    tracked as identities only — their contents are never read — so an
    unexpected serving Secret bulk-load changes the reference comparison
    instead of silently injecting env. Spec order is preserved: the K8s API
    resolves the last source when several export the same key, so interleaved
    ConfigMap and Secret sources in different orders are different effective
    environments.
    """
    if not isinstance(container, Mapping):
        return ()
    descriptors: list[tuple[str, bool, str, str, bool]] = []
    for source in container.get('envFrom') or []:
        if not isinstance(source, Mapping):
            continue
        prefix = source.get('prefix')
        prefix_str = prefix if isinstance(prefix, str) else ''
        ref = source.get('configMapRef')
        is_secret = False
        if not (isinstance(ref, Mapping) and isinstance(ref.get('name'), str) and ref['name']):
            ref = source.get('secretRef')
            is_secret = True
        name = ref.get('name') if isinstance(ref, Mapping) else None
        if not (isinstance(name, str) and name):
            continue
        optional = isinstance(ref, Mapping) and ref.get('optional') is True
        base = f'secret:{name}' if is_secret else name
        descriptors.append((_envfrom_ref_identity(base, prefix_str, optional), is_secret, name, prefix_str, optional))
    return tuple(descriptors)


def _explicit_configmap_keyref_hashes(entries: object) -> dict[str, str]:
    """``name -> configMapKeyRef identity hash`` for one container's env list.

    The identity hash covers the ConfigMap name, key and optionality (see
    ``env_entry_hash``); it is provable from the immutable pod spec even when
    the resolved ConfigMap data is not.
    """
    if not isinstance(entries, list):
        return {}
    hashes: dict[str, str] = {}
    for entry in entries:
        if not (isinstance(entry, dict) and isinstance(entry.get('name'), str) and entry['name']):
            continue
        value_from = entry.get('valueFrom')
        if isinstance(value_from, Mapping) and isinstance(value_from.get('configMapKeyRef'), Mapping):
            hashes[entry['name']] = env_entry_hash(entry)
    return hashes


def _envfrom_ref_identity(name: str, prefix: str, optional: bool) -> str:
    ident = f'{name}#{prefix}' if prefix else name
    return f'{ident}?optional' if optional else ident


def _parse_envfrom_ref_identity(ref: str) -> tuple[str, str]:
    """(name, prefix) encoded in a reference identity (``name[#prefix][?optional]``)."""
    base = ref.removesuffix('?optional')
    name, _, prefix = base.partition('#')
    return name, prefix


def _config_map_data_keys(data: Mapping[str, Any]) -> LiveEnv:
    """Hashes of the env keys a ConfigMap contributes through ``envFrom``."""
    return {str(key): value_hash('value', str(value)) for key, value in sorted(data.items())}


def _env_list_to_live(entries: object, *, scope: str) -> LiveEnv:
    if not isinstance(entries, list):
        raise ValueError(f'{scope} env must be a list')
    return {
        entry['name']: env_entry_hash(entry)
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get('name'), str) and entry['name']
    }


def _application_container(containers: object, *, scope: str, name: str | None = None) -> Mapping[str, Any]:
    if not isinstance(containers, list):
        raise ValueError(f'{scope} has no containers list')
    candidates = [c for c in containers if isinstance(c, dict) and c.get('name') != SIDECAR_NAME]
    if name is not None:
        named = [c for c in candidates if c.get('name') == name]
        if len(named) == 1:
            return named[0]
    if len(candidates) != 1:
        raise ValueError(f'{scope} expected 1 application container, found {len(candidates)}')
    return candidates[0]


# ── expected env (repository side) ──────────────────────────────────────────


def _manifest_env_config(env: str, manifest_path: Path) -> dict[str, Any]:
    manifest = render_backend_runtime_env._load_yaml(manifest_path)
    environments = render_backend_runtime_env._as_config_dict(manifest.get('environments')) or {}
    env_config = render_backend_runtime_env._as_config_dict(environments.get(env))
    if env_config is None:
        raise ValueError(f'Missing {env!r} environment in {manifest_path}')
    return env_config


def _manifest_entry_hash(name: str, entry: object, *, secret: bool, environ: Mapping[str, str]) -> str | None:
    """Expected hash for one manifest binding; None when only the deploy can resolve it."""
    config = render_backend_runtime_env._as_config_dict(entry) or {}
    if secret:
        if 'secret' in config:
            return _secret_ref_hash(str(config['secret']), str(config.get('version', 'latest')))
        env_var = config.get('env_var')
        resolved = environ.get(env_var, '') if isinstance(env_var, str) else ''
        return _secret_ref_hash(resolved, str(config.get('version', 'latest'))) if resolved else None
    if 'value' in config:
        return value_hash('value', str(config['value']))
    env_var = config.get('env_var')
    if isinstance(env_var, str) and environ.get(env_var):
        return value_hash('value', environ[env_var])
    # A manifest `default` is only the fallback; the deploy usually supplies the value, so
    # without rendered state this key is compared by name only (no false value drift).
    return None


def _is_renderer_secret_entry(entry: Mapping[str, Any]) -> bool:
    """True when a rendered ``valueFrom`` entry matches the renderer's only nested shape.

    ``render_backend_runtime_env.py`` emits exactly ``valueFrom.secretKeyRef``
    with non-empty ``name`` and ``key`` strings (see ``_render_secret_entries``);
    every other nested source is not renderer output.
    """
    secret = (entry.get('valueFrom') or {}).get('secretKeyRef')
    return (
        isinstance(secret, Mapping)
        and isinstance(secret.get('name'), str)
        and bool(secret.get('name'))
        and isinstance(secret.get('key'), str)
        and bool(secret.get('key'))
    )


def _canonical_manifest_secret_form(name: str, entry: object, *, environ: Mapping[str, str]) -> str:
    """Comparison form for a manifest secret binding (see ``_secret_ref_form``)."""
    config = render_backend_runtime_env._as_config_dict(entry) or {}
    if 'secret' in config:
        resource = str(config['secret'])
    else:
        env_var = config.get('env_var')
        resource = environ.get(env_var, '') if isinstance(env_var, str) else ''
    return _secret_ref_form(resource or name, str(config.get('version', 'latest')))


def expected_cloud_run_env(
    *,
    env: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    rendered_state_path: Path | None = None,
    environ: Mapping[str, str] | None = None,
    canonical_secret_hashes: dict[str, dict[str, str]] | None = None,
) -> tuple[str, str, dict[str, ExpectedEnv]]:
    """Expected Cloud Run env per service: rendered deploy state wins over the raw manifest.

    When ``canonical_secret_hashes`` is given it receives, per service, a
    project-stripped hash for every secret binding: a live revision that
    resolves its secret through the ``run.googleapis.com/secrets`` annotation
    may legitimately differ in the project segment alone (ID vs number), so
    the comparison needs the canonical form to tell form differences from
    real name/version drift.
    """
    env_config = _manifest_env_config(env, manifest_path)
    project = compute_project(env_config)
    region = str(env_config.get('region') or DEFAULT_REGION)
    cloud_run = render_backend_runtime_env._as_config_dict(env_config.get('cloud_run')) or {}
    services = render_backend_runtime_env._as_config_dict(cloud_run.get('services')) or {}
    environ = {} if environ is None else environ

    rendered_services: dict[str, Any] = {}
    if rendered_state_path is not None:
        # A supplied path must exist and be the renderer's state: silently falling
        # back to the raw manifest would drop exact-value coverage for deploy-time
        # bindings while appearing to have consumed the requested file.
        if not rendered_state_path.is_file():
            raise ValueError(f'Rendered state file not found: {rendered_state_path}')
        loaded_state = json.loads(rendered_state_path.read_text(encoding='utf-8'))
        if not (isinstance(loaded_state, dict) and isinstance(loaded_state.get('services'), dict)):
            raise ValueError(f'Rendered state {rendered_state_path} must contain a "services" mapping')
        rendered_services = loaded_state['services']

    expected: dict[str, ExpectedEnv] = {}
    for service_name, raw_service_config in services.items():
        service_config = render_backend_runtime_env._as_config_dict(raw_service_config) or {}
        env_map = render_backend_runtime_env._as_config_dict(service_config.get('env')) or {}
        secrets_map = render_backend_runtime_env._as_config_dict(service_config.get('secrets')) or {}
        service_expected: ExpectedEnv = {}
        service_canonical: dict[str, str] = {}
        bindings: dict[str, Any] = {**env_map, **secrets_map}
        for key, entry in env_map.items():
            # Unresolved deploy-time bindings stay name-only (None): the renderer may omit them.
            service_expected[str(key)] = _manifest_entry_hash(str(key), entry, secret=False, environ=environ)
        for key, entry in secrets_map.items():
            service_expected[str(key)] = _manifest_entry_hash(str(key), entry, secret=True, environ=environ)
            service_canonical[str(key)] = _canonical_manifest_secret_form(str(key), entry, environ=environ)
        raw_rendered = rendered_services.get(service_name)
        if rendered_state_path is not None and not isinstance(raw_rendered, Mapping):
            # The rendered state is all-or-nothing per service: a missing or
            # malformed entry must not silently fall back to the raw manifest,
            # where deploy-time env_var bindings degrade to name-only checks
            # while the command claims to validate the exact renderer output.
            raise ValueError(f'Rendered state {rendered_state_path} has no valid entry for service {service_name!r}')
        rendered_service = render_backend_runtime_env._as_config_dict(raw_rendered) or {}
        if rendered_state_path is not None and not isinstance(rendered_service.get('env'), list):
            # The renderer emits an env list for every service; anything else is
            # not renderer output, and consuming it would quietly re-source this
            # service's expected values from the raw manifest.
            raise ValueError(f'Rendered state {rendered_state_path} entry for service {service_name!r} has no env list')
        rendered_env: list[Any] = rendered_service.get('env') or []
        if rendered_state_path is not None and not all(
            isinstance(entry, dict) and isinstance(entry.get('name'), str) and entry['name'] for entry in rendered_env
        ):
            # Every renderer-emitted entry is a mapping with a non-empty name;
            # anything else is corruption, and skipping it would silently keep
            # the manifest's expectation for that key.
            raise ValueError(
                f'Rendered state {rendered_state_path} entry for service {service_name!r} '
                'has a malformed env entry (every entry must be a mapping with a non-empty name)'
            )
        if rendered_state_path is not None and not all(
            ('value' in entry) != isinstance(entry.get('valueFrom'), Mapping) for entry in rendered_env
        ):
            # The renderer emits exactly one of ``value`` or
            # ``valueFrom.secretKeyRef`` per entry; an entry with neither (or
            # with both) is not renderer output. Accepting a value-less entry
            # would hash it as an empty literal, so a corrupted state matching
            # an empty serving value could report OK.
            raise ValueError(
                f'Rendered state {rendered_state_path} entry for service {service_name!r} '
                'has a malformed env entry (each must carry exactly one of value or valueFrom)'
            )
        if rendered_state_path is not None and not all(
            _is_renderer_secret_entry(entry) for entry in rendered_env if isinstance(entry.get('valueFrom'), Mapping)
        ):
            # The renderer emits only ``valueFrom.secretKeyRef`` with valid
            # name/key fields; any other nested source (``{}``, ``fieldRef``,
            # ``configMapKeyRef``, a missing name/key) is not renderer output
            # and would hash into a domain where a matching fixture can report
            # OK. Validate the supported nested shape, not just its container.
            raise ValueError(
                f'Rendered state {rendered_state_path} entry for service {service_name!r} '
                'has a malformed env entry (valueFrom must be secretKeyRef with name and key)'
            )
        if rendered_service:
            # The rendered state is the exact deploy contract. The renderer
            # omits an env_var binding only when it is explicitly provisional
            # and unset at deploy time; a required env_var that is unset fails
            # the renderer instead of being skipped, so a state file that omits
            # one is truncated, not exact. Only explicitly provisional
            # omissions may drop out of the expected set; any other omission is
            # rejected as an incomplete state instead of being silently
            # excused as a name-only requirement.
            rendered_names = {
                entry['name']
                for entry in rendered_service.get('env', []) or []
                if isinstance(entry, dict) and isinstance(entry.get('name'), str) and entry['name']
            }
            # The renderer can only emit manifest ``env`` and ``secrets``
            # bindings: a well-formed rendered name with no such binding is
            # not renderer output for this service (stale file, wrong service,
            # hand edit). Merging it would declare a key the manifest never
            # authorized, so a serving revision that still carries that stale
            # key would compare OK — hiding exactly the live-only drift this
            # command exists to detect. Reject instead of merge.
            extra = sorted(rendered_names - set(env_map) - set(secrets_map))
            if extra:
                raise ValueError(
                    f'Rendered state {rendered_state_path} declares {extra[0]!r} for service '
                    f'{service_name!r}, which the manifest does not bind; the renderer emits '
                    'only manifest env and secrets bindings'
                )
            bindings = {**env_map, **secrets_map}
            provisional_omitted: set[str] = set()
            for key in service_expected:
                if key in rendered_names or not isinstance(bindings.get(key), Mapping):
                    continue
                if not bindings[key].get('env_var'):
                    continue
                if bindings[key].get('provisional'):
                    provisional_omitted.add(key)
                else:
                    raise ValueError(
                        f'Rendered state {rendered_state_path} omits required env_var binding '
                        f'{key!r} for service {service_name!r}; the renderer fails rather than omit it'
                    )
            service_expected = {
                key: digest for key, digest in service_expected.items() if key not in provisional_omitted
            }
        for entry in rendered_env:
            if not (isinstance(entry, dict) and isinstance(entry.get('name'), str) and entry['name']):
                continue
            key = entry['name']
            # The renderer resolves deploy-time bindings but cannot legitimately
            # alter a manifest-owned literal or fixed ``secret`` reference: a
            # state generated from an older commit or another environment would
            # then replace the manifest's hash unchecked, and a still-stale
            # serving revision would compare OK — hiding repository drift the
            # command exists to catch. Validate those entries against the
            # current manifest; replacement stays reserved for deploy-time
            # ``env_var`` bindings the manifest cannot resolve.
            if key in service_expected and service_expected[key] is not None:
                manifest_hash = service_expected[key]
                assert manifest_hash is not None  # guarded above; narrows for the type checker
                rendered_hash = env_entry_hash(entry)
                if rendered_hash != manifest_hash:
                    binding = bindings.get(key) if rendered_state_path is not None else None
                    is_deploy_time = isinstance(binding, Mapping) and bool(binding.get('env_var'))
                    if not is_deploy_time:
                        raise ValueError(
                            f'Rendered state {rendered_state_path} entry for {key!r} on service '
                            f'{service_name!r} contradicts the manifest binding '
                            f'(manifest hash {display_hash(key, manifest_hash)}, '
                            f'rendered hash {display_hash(key, rendered_hash)}); '
                            'the renderer emits literals and fixed secret references unchanged'
                        )
            service_expected[key] = env_entry_hash(entry)
            secret_ref = (entry.get('valueFrom') or {}).get('secretKeyRef')
            if isinstance(secret_ref, Mapping):
                service_canonical[key] = _secret_ref_form(
                    str(secret_ref.get('name', '')), str(secret_ref.get('key', ''))
                )
        expected[str(service_name)] = service_expected
        if canonical_secret_hashes is not None:
            canonical_secret_hashes[str(service_name)] = service_canonical
    return project, region, expected


def declared_manifest_keys(
    *,
    env: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    rendered_state_path: Path | None = None,
) -> tuple[str, str, dict[str, frozenset[str]]]:
    project, region, expected = expected_cloud_run_env(
        env=env, manifest_path=manifest_path, rendered_state_path=rendered_state_path
    )
    return project, region, {service: frozenset(keys) for service, keys in expected.items()}


def manifest_config_map(env: str, manifest_path: Path = DEFAULT_MANIFEST) -> tuple[str | None, dict[str, Any]]:
    """The environment's shared GKE ConfigMap (name, entries) from the manifest."""
    env_config = _manifest_env_config(env, manifest_path)
    gke = render_backend_runtime_env._as_config_dict(env_config.get('gke')) or {}
    config_map = render_backend_runtime_env._as_config_dict(gke.get('config_map')) or {}
    name = config_map.get('name')
    entries = render_backend_runtime_env._as_config_dict(config_map.get('entries')) or {}
    return (str(name) if isinstance(name, str) and name else None), entries


def _expected_envfrom_entries(entries: Mapping[str, Any]) -> ExpectedEnv:
    """Expected hashes for envFrom ConfigMap keys; deploy-time sources stay name-only."""
    expected: ExpectedEnv = {}
    for key, raw in entries.items():
        entry = render_backend_runtime_env._as_config_dict(raw) or {}
        if entry.get('source') == 'literal' and isinstance(entry.get('value'), str):
            expected[str(key)] = value_hash('value', str(entry['value']))
        else:
            expected[str(key)] = None  # environment-sourced: only deploy time knows the value
    return expected


def expected_gke_envfrom_refs(workload: str, *, env: str, root: Path = ROOT) -> tuple[str, ...]:
    """envFrom source identities (prefix and optionality included) the chart declares for this workload.

    ``secretRef`` sources appear as ``secret:<name>`` identities in spec order;
    their contents are never read.
    """
    spec = GKE_WORKLOADS[workload]
    values = _load_values(root / spec.values_file.format(env=env))
    if spec.envfrom_from_runtime_config_map:
        # Mirror the pusher template: envFrom comes from
        # runtimeConfigMapName alone; .Values.envFrom is dead config there
        # and must not become the expected reference.
        name = values.get('runtimeConfigMapName')
        if isinstance(name, str) and name:
            return (_envfrom_ref_identity(name, '', False),)
        return ()
    descriptors = _envfrom_source_descriptors({'envFrom': values.get('envFrom')})
    if not descriptors:
        name = values.get('runtimeConfigMapName')
        if isinstance(name, str) and name:
            descriptors = ((_envfrom_ref_identity(name, '', False), False, name, '', False),)
    # Duplicates preserved for the same last-source-wins reason as the serving read.
    return tuple(identity for identity, _is_secret, _name, _prefix, _optional in descriptors)


def _load_values(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a YAML mapping')
    return loaded


def expected_gke_env_from_values(
    workload: str, *, env: str, root: Path = ROOT
) -> tuple[ExpectedEnv | None, dict[str, str]]:
    """Expected env from the chart values ``env`` list; None when the chart builds env in its template.

    Returns ``(expected, keyref_hashes)`` where ``keyref_hashes`` maps each key
    the chart binds through ``valueFrom.configMapKeyRef`` to its binding
    identity hash (post template-rewrite), so the comparison can prove binding
    drift even though the resolved ConfigMap data is unknowable.
    """
    spec = GKE_WORKLOADS[workload]
    values = _load_values(root / spec.values_file.format(env=env))
    entries = values.get('env')
    if not isinstance(entries, list):
        return None, {}
    expected: ExpectedEnv = {}
    keyref_hashes: dict[str, str] = {}
    runtime_config_map = values.get('runtimeConfigMapName')
    for raw in entries:
        if not isinstance(raw, dict) or not isinstance(raw.get('name'), str):
            continue
        name = str(raw['name'])
        entry: dict[str, Any] = dict(raw)
        # Mirror the two chart-template rewrites so values mode matches `helm template`.
        if workload == 'backend-listen' and name == 'GOOGLE_CLOUD_PROJECT':
            entry = {'name': name, 'value': values.get('runtimeGcpProjectId', entry.get('value'))}
        value_from = entry.get('valueFrom')
        if isinstance(value_from, dict) and isinstance(value_from.get('configMapKeyRef'), dict) and runtime_config_map:
            entry['valueFrom'] = {'configMapKeyRef': {**value_from['configMapKeyRef'], 'name': runtime_config_map}}
        if isinstance(entry.get('valueFrom'), dict) and isinstance(entry['valueFrom'].get('configMapKeyRef'), dict):
            keyref_hashes[name] = env_entry_hash(entry)
        expected[name] = env_entry_hash(entry)
    return expected, keyref_hashes


def _redact_helm_override_values(text: str, helm_args: Sequence[str]) -> str:
    """Replace literal override values (from ``--set*`` tokens) in text.

    ``helm`` failure output can echo the offending token; the checker's contract
    is that values never reach a report, so every literal value is replaced
    before any stderr is stored on an error result. Both token shapes are
    handled: ``--set-string NAME=value`` (the bare ``NAME=value`` argv entry)
    and the inline ``--set-string=NAME=value`` form. In each shape the value is
    everything after the name's ``=`` — a value may itself contain ``=`` (base64
    padding, connection strings), so only the name segment is skipped, never a
    tail of the value.
    """
    for token in helm_args:
        if not token.startswith('-'):
            # Bare ``NAME=value`` argv entry (follows a separate --set* flag).
            _name, eq, value = token.partition('=')
        else:
            # Inline ``--set*=NAME=value`` flag; drop the flag prefix first.
            _flag, eq, value = token.partition('=')[2].partition('=')
        if eq and value:
            text = text.replace(value, '<redacted>')
    return text


def expected_gke_env_from_helm(
    workload: str,
    *,
    env: str,
    root: Path = ROOT,
    runner: Callable[..., Any] = subprocess.run,
    helm_args: Sequence[str] = (),
) -> tuple[ExpectedEnv, tuple[str, ...], dict[str, str]]:
    """Expected env and envFrom ConfigMap refs from ``helm template`` of the chart
    with its prod/dev values (exact chart semantics).

    ``helm_args`` carries the exact deployed override inputs (dispatch
    ``--set-string env[i].value=...`` tokens and ``-f <private values>``
    fragments from ``listen_helm_env_overrides.py``'s argv file). Without
    them, a legitimately overridden rollout compares against chart defaults
    and shows false value drift.

    Returns ``(expected, envfrom_refs, keyref_hashes)``; ``keyref_hashes`` maps
    each key the rendered chart binds through ``valueFrom.configMapKeyRef`` to
    its binding identity hash, so the comparison can prove binding drift even
    though the resolved ConfigMap data is unknowable on a live read.
    """
    spec = GKE_WORKLOADS[workload]
    deployment = spec.deployment.format(env=env)
    try:
        result = runner(
            [
                'helm',
                'template',
                deployment,
                str(root / spec.chart),
                '-f',
                str(root / spec.values_file.format(env=env)),
                *helm_args,
                '--namespace',
                f'{env}-omi-backend',
                *(arg for pin in spec.helm_image_args for arg in ('--set-string', pin)),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        # CalledProcessError's default str() embeds the full argv, which can
        # carry literal override values; re-raise with a redacted message so no
        # report (markdown, JSON, summary file) can disclose them.
        stderr = _redact_helm_override_values((exc.stderr or '')[-500:], helm_args)
        raise ValueError(f'helm template for {workload} failed (exit {exc.returncode}): {stderr}') from None
    for document in yaml.safe_load_all(result.stdout):
        if isinstance(document, dict) and document.get('kind') == 'Deployment':
            if (document.get('metadata') or {}).get('name') != deployment:
                continue
            pod_spec = ((document.get('spec') or {}).get('template') or {}).get('spec') or {}
            container = _application_container(
                pod_spec.get('containers'), scope=f'helm {workload}', name=spec.container
            )
            expected_env_map = cast(
                'ExpectedEnv', _env_list_to_live(container.get('env', []), scope=f'helm {workload}')
            )
            return (
                expected_env_map,
                tuple(identity for identity, _s, _n, _p, _o in _envfrom_source_descriptors(container)),
                _explicit_configmap_keyref_hashes(container.get('env', [])),
            )
    raise ValueError(f'helm template rendered no Deployment {deployment!r}')


# ── live env (serving side) ─────────────────────────────────────────────────


@dataclass
class LiveService:
    targets: list[tuple[ServingTarget, LiveEnv]] = field(default_factory=list)
    source: str = 'serving'
    template_name: str | None = None
    template_env: LiveEnv | None = None
    # The Deployment template's ordered envFrom identities. The template
    # comparison checks them alongside the env fingerprint: two ConfigMaps
    # with identical data but different names are still a rebind the
    # fingerprint alone cannot see.
    template_envfrom_refs: tuple[str, ...] = ()
    envfrom_unresolved: tuple[str, ...] = ()  # referenced ConfigMaps whose data could not be read
    # References whose current ConfigMap data cannot be proven to match what the
    # running pods resolved at container start (all live reads; K8s does not
    # refresh envFrom for existing processes). Per-target detail lives on each
    # ServingTarget; these are the workload-wide aggregates for the report.
    envfrom_unproven: tuple[str, ...] = ()


def _run_json(runner: Callable[..., Any], argv: list[str]) -> Any:
    result = runner(argv, check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def serving_revisions(service_doc: Mapping[str, Any]) -> list[tuple[str, int]]:
    """Revisions with traffic > 0 from ``status.traffic``; resolves ``latestRevision: true`` entries."""
    status = service_doc.get('status')
    if not isinstance(status, Mapping) or not isinstance(status.get('traffic'), list):
        raise ValueError('service has no status.traffic; refusing to fall back to spec.template')
    weights: dict[str, int] = {}
    for entry in status['traffic']:
        if not isinstance(entry, Mapping):
            continue
        percent = int(entry.get('percent') or 0)
        if percent <= 0:
            continue
        name = entry.get('revisionName')
        if not name and entry.get('latestRevision'):
            name = status.get('latestReadyRevisionName')
        if not isinstance(name, str) or not name:
            raise ValueError('status.traffic entry has no resolvable revision name')
        weights[name] = weights.get(name, 0) + percent
    if not weights:
        raise ValueError('status.traffic routes no traffic to any revision')
    return sorted(weights.items(), key=lambda item: (-item[1], item[0]))


def _template_env(service_doc: Mapping[str, Any], *, service: str) -> tuple[str | None, LiveEnv | None]:
    template = (service_doc.get('spec') or {}).get('template')
    if not isinstance(template, Mapping):
        return None, None
    containers = (template.get('spec') or {}).get('containers')
    if containers is None:
        return None, None
    container = _application_container(containers, scope=f'Cloud Run service {service} template')
    name = (template.get('metadata') or {}).get('name')
    # Alias resolution matches _revision_env so template and serving
    # fingerprints stay comparable when cross-project secrets are declared.
    env, _alias_resolved = _resolve_secret_aliases(
        container.get('env', []), _secret_alias_map(template.get('metadata'))
    )
    return (name if isinstance(name, str) else None), _env_list_to_live(env, scope=service)


# Cloud Run represents cross-project secrets (projects/p/secrets/s) through
# this annotation while the container env carries only a lookup alias in
# secretKeyRef.name; the annotation maps the declared name to the resource.
SECRET_ALIAS_ANNOTATION = 'run.googleapis.com/secrets'


def _secret_alias_map(metadata: Mapping[str, Any] | None) -> dict[str, str]:
    """``declared name -> secret resource`` from a revision/template annotation.

    The grammar matches ``attach_cloud_run_gmp_sidecar.py``:
    ``name:projects/<number>/secrets/<secret>,name2:...``. Malformed entries
    are skipped: the checker must not guess a rewrite, only apply one the
    platform itself declared.
    """
    annotations = (metadata or {}).get('annotations') or {}
    raw = annotations.get(SECRET_ALIAS_ANNOTATION)
    if not isinstance(raw, str) or not raw.strip():
        return {}
    aliases: dict[str, str] = {}
    for candidate in raw.split(','):
        entry = candidate.strip()
        if not entry:
            continue
        name, separator, resource = entry.partition(':')
        if name and separator and resource:
            aliases[name] = resource
    return aliases


def _resolve_secret_aliases(entries: object, aliases: Mapping[str, str]) -> tuple[list[Any], dict[str, str]]:
    """Rewrite ``secretKeyRef.name`` aliases to their declared secret resources.

    Expected hashes keep a project-qualified reference intact (see
    ``_secret_ref_hash``), so a live alias must resolve through the annotation
    before hashing or a correctly deployed cross-project secret reports a value
    mismatch. Only names the annotation explicitly declares are rewritten.
    Returns ``(entries, comparison forms)`` where the form keeps the project
    segment separate (see ``_secret_ref_form``): a full-hash difference is
    degraded to INVENTORY only when it is confined to a genuine
    ID-vs-number/implicit project form difference; unequal projects, names or
    versions stay real drift.
    """
    if not isinstance(entries, list) or not aliases:
        return (entries if isinstance(entries, list) else []), {}
    resolved: list[Any] = []
    canonical: dict[str, str] = {}
    for entry in entries:
        if isinstance(entry, dict):
            value_from = entry.get('valueFrom')
            secret = value_from.get('secretKeyRef') if isinstance(value_from, dict) else None
            if isinstance(secret, dict):
                resource = aliases.get(str(secret.get('name', ''))) or aliases.get(str(entry.get('name', '')))
                if resource:
                    entry_name = entry.get('name')
                    entry = {
                        **entry,
                        'valueFrom': {'secretKeyRef': {**secret, 'name': resource}},
                    }
                    if isinstance(entry_name, str) and entry_name:
                        canonical[entry_name] = _secret_ref_form(resource, str(secret.get('key', '')))
        resolved.append(entry)
    return resolved, canonical


def _revision_env(revision_doc: Mapping[str, Any], *, revision: str) -> tuple[LiveEnv, dict[str, str]]:
    containers = (revision_doc.get('spec') or {}).get('containers')
    container = _application_container(containers, scope=f'Cloud Run revision {revision}')
    env, alias_resolved = _resolve_secret_aliases(
        container.get('env', []), _secret_alias_map(revision_doc.get('metadata'))
    )
    return _env_list_to_live(env, scope=f'revision {revision}'), alias_resolved


def read_cloud_run_service(
    service: str,
    *,
    project: str,
    region: str,
    offline_services: Mapping[str, Any] | None = None,
    offline_revisions: Mapping[str, Any] | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> LiveService:
    if offline_services is not None:
        service_doc = offline_services.get(service)
        if not isinstance(service_doc, Mapping):
            raise ValueError(f'Missing service {service!r} in offline Cloud Run state')
        if isinstance(service_doc.get('env'), list):
            # Env-only snapshot fixture (no traffic information): compare it as given.
            # Anything else — including a spec.template without status.traffic — is
            # refused below by serving_revisions() instead of being misread as serving.
            env = _env_list_to_live(service_doc['env'], scope=service)
            target = ServingTarget(
                name='snapshot',
                weight=100,
                key_count=len(env),
                fingerprint=env_fingerprint(env),
                display_fingerprint=env_fingerprint(env, redacted=True),
            )
            return LiveService(targets=[(target, env)], source='snapshot')
    else:
        service_doc = _run_json(
            runner,
            [
                'gcloud',
                'run',
                'services',
                'describe',
                service,
                f'--project={project}',
                f'--region={region}',
                '--format=json',
            ],
        )
        if not isinstance(service_doc, Mapping):
            raise ValueError(f'Cloud Run service {service} describe did not return a JSON object')

    live = LiveService()
    live.template_name, live.template_env = _template_env(service_doc, service=service)
    for revision, percent in serving_revisions(service_doc):
        if offline_revisions is not None:
            revision_doc = offline_revisions.get(revision)
            if not isinstance(revision_doc, Mapping):
                raise ValueError(f'Missing serving revision {revision!r} in offline Cloud Run state')
        else:
            revision_doc = _run_json(
                runner,
                [
                    'gcloud',
                    'run',
                    'revisions',
                    'describe',
                    revision,
                    f'--project={project}',
                    f'--region={region}',
                    '--format=json',
                ],
            )
        env, alias_canonical = _revision_env(revision_doc, revision=revision)
        live.targets.append(
            (
                ServingTarget(
                    name=revision,
                    weight=percent,
                    key_count=len(env),
                    fingerprint=env_fingerprint(env),
                    display_fingerprint=env_fingerprint(env, redacted=True),
                    alias_ref_forms=alias_canonical,
                ),
                env,
            )
        )
    return live


def read_gke_workload(
    workload: str,
    *,
    env: str,
    kube_context: str | None,
    offline_gke: Mapping[str, Any] | None = None,
    runner: Callable[..., Any] = subprocess.run,
    replicaset_cache: dict[str, Any] | None = None,
    configmap_cache: dict[str, Any] | None = None,
) -> LiveService:
    """Env of every ReplicaSet of the Deployment that holds ready pods (what is actually serving)."""
    spec = GKE_WORKLOADS[workload]
    deployment_name = spec.deployment.format(env=env)
    namespace = f'{env}-omi-backend'
    if offline_gke is not None:
        workload_doc = offline_gke.get(workload)
        if not isinstance(workload_doc, Mapping):
            raise ValueError(f'Missing GKE workload {workload!r} in offline state')
        deployment = workload_doc.get('deployment') or {}
        replicasets = workload_doc.get('replicasets') or []
        configmaps = workload_doc.get('configmaps')
        if not isinstance(configmaps, Mapping):
            shared = offline_gke.get('configmaps')
            configmaps = shared if isinstance(shared, Mapping) else {}

        def resolve_configmap(ref: str, *, optional: bool = False) -> Mapping[str, Any] | None:
            # None marks an offline fixture that does not carry this ConfigMap's
            # data; the workload reports INVENTORY rather than guessing.
            doc = configmaps.get(ref)
            if isinstance(doc, Mapping) and isinstance(doc.get('data'), Mapping):
                return doc['data']
            if (
                isinstance(doc, Mapping)
                and doc
                and all(isinstance(k, str) and isinstance(v, str) for k, v in doc.items())
            ):
                return doc  # plain key -> value fixture
            return None

        def configmap_is_proven(ref: str) -> bool:
            # An offline fixture is a captured snapshot: the data given is exactly
            # what the captured pods resolved. Nothing to prove.
            return True

    else:
        if not kube_context:
            raise ValueError('--kube-context is required for live GKE reads')
        base = ['kubectl', f'--context={kube_context}', '-n', namespace, 'get']
        deployment = _run_json(runner, [*base, 'deployment', deployment_name, '-o', 'json'])
        cache = replicaset_cache if replicaset_cache is not None else {}
        if namespace not in cache:
            cache[namespace] = _run_json(runner, [*base, 'replicasets', '-o', 'json']).get('items', [])
        replicasets = cache[namespace]
        cm_cache = configmap_cache if configmap_cache is not None else {}

        def resolve_configmap(ref: str, *, optional: bool = False) -> Mapping[str, Any] | None:
            # A live read that fails raises (fetch error); one that succeeds but has
            # no data mapping resolves to an empty key set. An optional reference
            # whose ConfigMap is NotFound is not a fetch failure: K8s permits the
            # pod to run without it, so it resolves to an empty (unproven) set and
            # the workload reports INVENTORY instead of ERROR. The not-found fact
            # is cached distinctly from a real empty mapping so a later REQUIRED
            # reference to the same name still fails instead of reading the
            # optional caller's empty result from the shared cache.
            if ref not in cm_cache:
                try:
                    cm_doc = _run_json(runner, [*base, 'configmap', ref, '-o', 'json'])
                except subprocess.CalledProcessError as exc:
                    stderr = getattr(exc, 'stderr', '') or ''
                    if optional and 'NotFound' in stderr:
                        cm_cache[ref] = _NOT_FOUND_SENTINEL
                    else:
                        raise
                else:
                    cm_cache[ref] = cm_doc.get('data') if isinstance(cm_doc.get('data'), Mapping) else {}
            if cm_cache[ref] is _NOT_FOUND_SENTINEL:
                if optional:
                    return {}
                raise ValueError(f'ConfigMap {ref!r} not found (required by this reference)')
            return cm_cache[ref]

        def configmap_is_proven(ref: str) -> bool:
            # Kubernetes never refreshes envFrom for running containers, and a
            # ConfigMap's metadata carries no trustworthy last-write timestamp
            # (updates bump resourceVersion, which is not comparable across
            # objects, and leave creationTimestamp untouched). A live read
            # therefore cannot prove the ready pods resolved this data; the
            # workload reports INVENTORY for envFrom keys instead of asserting OK.
            return False

    def envfrom_entries(container: Mapping[str, Any] | None) -> LiveEnv:
        merged: LiveEnv = {}
        for name, prefix, optional in _envfrom_sources(container):
            # Optionality forwards here too (the Deployment template path): a
            # missing optional ConfigMap is legal K8s and resolves to empty,
            # not a workload-wide fetch error.
            data = resolve_configmap(name, optional=optional)
            if data is None:
                continue
            for key, digest in _config_map_data_keys(data).items():
                # K8s precedence: when several envFrom sources export the same
                # key, the last source wins — so later sources overwrite.
                merged[f'{prefix}{key}'] = digest
        return merged

    live = LiveService()
    refs_unresolved: set[str] = set()
    refs_unproven: set[str] = set()
    template_spec = ((deployment.get('spec') or {}).get('template') or {}).get('spec') or {}
    if template_spec.get('containers') is not None:
        container = _application_container(template_spec['containers'], scope=deployment_name, name=spec.container)
        live.template_name = deployment_name
        template_env = _env_list_to_live(container.get('env', []), scope=deployment_name)
        # envFrom keys join the template fingerprint too, so template vs serving
        # stays comparable when both bulk-load the same ConfigMap.
        live.template_env = {**envfrom_entries(container), **template_env}
        # ... and so do the envFrom identities: expanding only their data would
        # give template-A and template-B identical fingerprints whenever the two
        # ConfigMaps currently hold the same entries. Secret sources contribute
        # identities only (contents are never read), in spec order.
        live.template_envfrom_refs = tuple(
            identity for identity, _is_secret, _name, _prefix, _optional in _envfrom_source_descriptors(container)
        )
    for rs in replicasets:
        if not isinstance(rs, Mapping):
            continue
        owners = (rs.get('metadata') or {}).get('ownerReferences') or []
        if not any(o.get('kind') == 'Deployment' and o.get('name') == deployment_name for o in owners):
            continue
        ready = int((rs.get('status') or {}).get('readyReplicas') or 0)
        if ready <= 0:
            continue
        rs_name = str((rs.get('metadata') or {}).get('name') or 'replicaset')
        pod_spec = ((rs.get('spec') or {}).get('template') or {}).get('spec') or {}
        container = _application_container(pod_spec.get('containers'), scope=rs_name, name=spec.container)
        env_list = container.get('env', [])
        env_map = _env_list_to_live(env_list, scope=rs_name)
        explicit_keys = frozenset(env_map)
        # Live reads only: an explicit configMapKeyRef binding proves the
        # reference, not the data the container resolved at start (K8s needs a
        # pod restart to pick up ConfigMap changes), so those keys stay
        # value-unproven. An offline snapshot is the captured truth and proves
        # them. The binding identities are kept per key so the comparison can
        # still flag a rollout that rebound a key to a different ConfigMap or
        # key — the immutable pod spec proves the reference even when the
        # resolved data is unknowable.
        if offline_gke is None and kube_context:
            keyref_hashes = _explicit_configmap_keyref_hashes(env_list)
            explicit_unproven = frozenset(keyref_hashes)
        else:
            keyref_hashes = {}
            explicit_unproven = frozenset()
        # envFrom references are tracked per ReplicaSet (they are part of its
        # immutable spec) so the comparison can catch two serving ReplicaSets
        # that disagree, instead of only their union. Secret sources join as
        # identity-only entries (contents never read) in spec order.
        descriptors = _envfrom_source_descriptors(container)
        target_refs = tuple(identity for identity, _is_secret, _name, _prefix, _optional in descriptors)
        target_unproven_keys: set[str] = set()
        target_degraded_refs: set[str] = set()
        target_contributions: list[tuple[str, frozenset[str]]] = []
        # Keys an earlier known (ConfigMap) source contributed that a later
        # opaque Secret source may override (K8s last-source-wins). Secret
        # contents are never read, so those keys' effective values are
        # unproven until a later known source or an explicit env entry
        # re-binds them; comparing the ConfigMap's snapshot value would
        # report false drift for a correct rollout. A prefixed opaque source
        # can only produce names starting with its prefix, so only those
        # earlier keys are shadowed.
        target_shadowed_keys: set[str] = set()
        contributed_keys: set[str] = set()
        for identity, is_secret, source_name, source_prefix, optional in descriptors:
            if is_secret:
                # Secrets stay opaque: identity comparison only, keys unresolved.
                refs_unresolved.add(identity)
                target_degraded_refs.add(identity)
                target_shadowed_keys |= {key for key in contributed_keys if key.startswith(source_prefix)}
                continue
            data = resolve_configmap(source_name, optional=optional)
            if data is None:
                refs_unresolved.add(identity)
                target_degraded_refs.add(identity)
                # An unreadable later source is as opaque as a Secret: its keys
                # are unknown, so it may override any earlier known source's
                # key its prefix can reach (K8s last-source-wins). Earlier keys
                # stay value-unproven until a later known source re-exports
                # them.
                target_shadowed_keys |= {key for key in contributed_keys if key.startswith(source_prefix)}
                continue
            contributed = frozenset(f'{source_prefix}{key}' for key in data)
            if contributed:
                target_contributions.append((identity, contributed))
            # A later known source that exports a key re-proves it: the last
            # contributing source is the effective one.
            contributed_keys |= contributed
            target_shadowed_keys -= contributed
            if not configmap_is_proven(source_name):
                refs_unproven.add(identity)
                target_degraded_refs.add(identity)
                # The current ConfigMap data may include keys added after these
                # pods started; only the pod spec is immutable, so every key this
                # unproven source contributes is excluded from live-only checks.
                target_unproven_keys |= set(contributed)
        # Explicit env entries win over envFrom keys, matching pod runtime semantics.
        env_map = {**envfrom_entries(container), **env_map}
        live.targets.append(
            (
                ServingTarget(
                    name=rs_name,
                    weight=ready,
                    key_count=len(env_map),
                    fingerprint=env_fingerprint(env_map),
                    display_fingerprint=env_fingerprint(env_map, redacted=True),
                    explicit_keys=explicit_keys,
                    envfrom_refs=target_refs,
                    envfrom_degraded_refs=frozenset(target_degraded_refs),
                    unproven_envfrom_keys=frozenset(target_unproven_keys - explicit_keys),
                    envfrom_key_contributions=tuple(target_contributions),
                    opaque_shadowed_keys=frozenset(target_shadowed_keys - explicit_keys),
                    explicit_unproven_keys=explicit_unproven,
                    explicit_keyref_hashes=keyref_hashes,
                ),
                env_map,
            )
        )
    if not live.targets:
        raise ValueError(f'Deployment {deployment_name} has no ReplicaSet with ready pods')
    live.envfrom_unresolved = tuple(sorted(refs_unresolved))
    live.envfrom_unproven = tuple(sorted(refs_unproven))
    live.targets.sort(key=lambda item: (-item[0].weight, item[0].name))
    return live


# ── comparison ──────────────────────────────────────────────────────────────


def compare_service(
    service: str,
    *,
    expected: ExpectedEnv | None,
    live: LiveService,
    allowed: frozenset[str],
    platform: str,
    expected_envfrom_refs: tuple[str, ...] = (),
    expected_envfrom_unresolved: tuple[str, ...] = (),
    expected_envfrom_keys: frozenset[str] = frozenset(),
    expected_envfrom_keys_by_ref: Mapping[str, frozenset[str]] | None = None,
    expected_keyref_hashes: Mapping[str, str] | None = None,
    expected_canonical_secret_hashes: Mapping[str, str] | None = None,
) -> ServiceEnvDrift:
    expected_env: ExpectedEnv = expected or {}
    declared = frozenset(expected_env)
    envfrom_mismatched: tuple[str, ...] = ()
    envfrom_unresolved: tuple[str, ...] = ()
    envfrom_unproven: tuple[str, ...] = ()
    expected_ref_set = set(expected_envfrom_refs)
    if expected is not None:
        # References are compared per serving target as ordered sequences, and
        # never as a union: during a mixed rollout two ready ReplicaSets can
        # disagree (one rebinding or dropping the ConfigMap, one still serving
        # the previous spec), and a union of their references would hide that
        # as equal. Order matters too — the K8s API resolves the last envFrom
        # source when several export the same key, so a reordered reference
        # list is a different effective environment.
        mismatched: set[str] = set()
        for target, _env_map in live.targets:
            mismatched |= set(target.envfrom_refs) ^ expected_ref_set
            if list(target.envfrom_refs) != list(expected_envfrom_refs):
                # A reordered or duplicate-bearing reference list: flag the
                # union of both orders' identities so the report names the refs.
                mismatched |= set(target.envfrom_refs) | expected_ref_set
        envfrom_mismatched = tuple(sorted(mismatched))
        envfrom_unresolved = tuple(
            sorted((set(live.envfrom_unresolved) | set(expected_envfrom_unresolved)) - mismatched)
        )
        # Live ConfigMap data cannot prove what already-running pods resolved at
        # container start (K8s never refreshes envFrom); comparisons on those keys
        # would be assertions, so they are skipped and the workload reports INVENTORY.
        envfrom_unproven = tuple(sorted(set(live.envfrom_unproven) - set(live.envfrom_unresolved) - mismatched))
    # Expected references whose keys the repository cannot enumerate (external
    # ConfigMaps), excluding any whose identity already drifted: their
    # contributed keys degrade to INVENTORY instead of asserting a value.
    expected_unresolved_refs: set[str] = (
        set(expected_envfrom_unresolved) - set(envfrom_mismatched) if expected is not None else set()
    )
    live_only: set[str] = set()
    missing: set[str] = set()
    mismatches: list[ValueMismatch] = []
    # Cloud Run keys whose alias-resolved reference is form-ambiguous (the
    # annotation's project number vs the repository's project ID): skipped
    # from value assertions, reported as unchecked (INVENTORY).
    alias_unproven: set[str] = set()
    # Explicit configMapKeyRef keys whose value comparison was skipped per
    # target (live reads: the binding is proven, the resolved data is not).
    explicit_unproven: set[str] = set()
    # Expected envFrom keys are tracked per reference (thread: scoping the
    # missing-key suppression to the degraded source): when only one expected
    # reference is degraded (unproven or unreadable), only the keys that
    # reference contributes are excused on a target holding it — a snapshot
    # that proves ConfigMap A while omitting B must still report keys missing
    # from the proven A.
    envfrom_keys_by_ref: Mapping[str, frozenset[str]] = expected_envfrom_keys_by_ref or {}
    for target, env_map in live.targets:
        # envFrom-only keys of unproven sources are excluded per target: the
        # current ConfigMap data may have gained (or lost) keys after these pods
        # started, so their presence proves nothing about the running workload.
        target_excused = set(target.unproven_envfrom_keys)
        # Keys contributed by an expected reference the repository cannot
        # enumerate, on a target that holds that same reference (offline
        # snapshots where the fixture resolves the external ConfigMap's data).
        unresolved_contributions: set[str] = set()
        if expected is not None:
            # Keys contributed by an expected reference the repository cannot
            # enumerate (external ConfigMap) are also excused on targets that
            # hold that same reference: the identities match, so the serving
            # bulk-load is exactly what the chart declared. Reporting those
            # keys as unallowlisted live-only drift would fail --strict for a
            # correct rollout; they surface as INVENTORY instead.
            unresolved_contributions = {
                key for ref, keys in target.envfrom_key_contributions if ref in expected_unresolved_refs for key in keys
            }
            target_excused |= unresolved_contributions
        live_only |= (set(env_map) - declared) - target_excused if expected is not None else set(env_map) - declared
        if expected is None:
            continue
        # Expected envFrom keys are excused only on targets that hold a degraded
        # (unproven or unreadable) expected reference. A serving ReplicaSet that
        # lacks the reference genuinely lacks those keys; excusing them globally
        # would convert real reference drift into INVENTORY.
        degraded_expected_refs = target.envfrom_degraded_refs & expected_ref_set
        skip_missing = frozenset()
        if degraded_expected_refs:
            # Only the keys the degraded references actually contribute are
            # excused. A degraded reference absent from the per-ref map (an
            # external ConfigMap whose keys the repository cannot enumerate)
            # contributes no expected keys, so it excuses nothing: excusing the
            # whole expected envFrom set here would hide a proven sibling
            # source's missing keys.
            skip_missing = frozenset().union(
                *(envfrom_keys_by_ref.get(ref, frozenset()) for ref in degraded_expected_refs)
            )
            # An opaque later source may also *supply* an expected key the
            # earlier known sources did not contribute: Secret contents are
            # never readable in any run mode, and an unresolved ConfigMap's
            # data is unknown in this run, so the key's absence from env_map
            # proves nothing — it may come from the opaque source (K8s
            # last-source-wins makes a later source the effective one). Excuse
            # only expected names the source's prefix can reach (a ``prefix:
            # SECRET_`` source can never supply an unprefixed key, whose
            # absence stays proven missing drift). A degraded-but-read source
            # (live ConfigMap whose data cannot prove what running pods
            # resolved) is excluded: its key set is known, so it cannot supply
            # names beyond its contribution.
            known_key_sets = dict(target.envfrom_key_contributions)
            opaque_prefixes = [
                _parse_envfrom_ref_identity(ref)[1] for ref in target.envfrom_degraded_refs if ref not in known_key_sets
            ]
            if opaque_prefixes:
                skip_missing |= {
                    key for key in expected_envfrom_keys for prefix in opaque_prefixes if key.startswith(prefix)
                }
        missing |= declared - set(env_map) - skip_missing
        # Unproven live ConfigMap data only degrades keys whose effective value
        # comes from envFrom. A key this target sets through an explicit env
        # entry shadows envFrom (K8s precedence) and its spec is immutable, so
        # the value stays knowable and must not be excused — except a
        # configMapKeyRef binding: its spec proves the reference, while the
        # value the container resolved at start can differ from the ConfigMap's
        # current data without any rollout (K8s requires a restart to refresh
        # it), so it is skipped like envFrom keys and reported as INVENTORY.
        # Key presence is still checked even when the expected value is unknown
        # (deploy-time binding): a None hash skips only the value comparison,
        # never the key.
        # The same precedence holds for unresolved external sources: when the
        # repository cannot enumerate an expected reference's keys but the
        # snapshot resolved its data, the effective value of a duplicated key
        # follows K8s last-source-wins, not the repository ConfigMap's manifest
        # entry — comparing it against the repo digest would report false
        # drift for a correct rollout. Only keys whose effective value the
        # repository does prove (an explicit env entry shadows the unresolved
        # source, or a later contributing source on this target overrides it)
        # are value-compared. Excluded keys need no separate INVENTORY
        # attribution: the unresolved reference itself already reports the
        # workload as INVENTORY (envfrom_unresolved).
        value_excluded: set[str] = set()
        if unresolved_contributions:
            # Per-target later-source-wins resolution: a key's effective source
            # is the last envFrom source that contributed it in spec order.
            effective_source: dict[str, str] = {}
            for ref, keys in target.envfrom_key_contributions:
                for key in keys:
                    effective_source[key] = ref
            for key in unresolved_contributions & declared:
                if key in target.explicit_keys:
                    continue  # explicit env entry shadows envFrom; compared above
                if effective_source.get(key) in expected_unresolved_refs:
                    value_excluded.add(key)
        explicit_unproven |= target.explicit_unproven_keys - target.unproven_envfrom_keys
        # Keys a later opaque Secret source may override are excluded from the
        # value comparison for the same reason unresolved-source keys are: the
        # effective value is unknowable (Secret contents are never read), so
        # asserting the earlier ConfigMap source's value would report false
        # drift. The Secret source's own identity already reports INVENTORY.
        value_excluded |= target.opaque_shadowed_keys
        for key in sorted(
            (declared & set(env_map)) - target.unproven_envfrom_keys - target.explicit_unproven_keys - value_excluded
        ):
            want = expected_env[key]
            if want is None or env_map[key] == want:
                continue
            # A key resolved through the run.googleapis.com/secrets annotation
            # may legitimately differ from the expected reference in the
            # project segment's *form* alone (the platform writes the project
            # number, repository state may carry the project ID or the bare
            # name). Only that ID-vs-number/implicit form difference degrades
            # to INVENTORY; unequal projects, a different secret name or a
            # different version is real drift.
            if key in target.alias_ref_forms and _alias_mismatch_is_form_ambiguous(
                (expected_canonical_secret_hashes or {}).get(key, '\x00\x00'), target.alias_ref_forms[key]
            ):
                alias_unproven.add(key)
                continue
            mismatches.append(ValueMismatch(key=key, expected_hash=want, live_hash=env_map[key], target=target.name))
        # A configMapKeyRef binding is provable from the immutable pod spec
        # even when the resolved ConfigMap data is not: compare the reference
        # identity hashes before degrading a key to INVENTORY. A rollout that
        # rebound a key to a different ConfigMap or key is drift; only a
        # matching binding stays value-unproven (the live ConfigMap data still
        # cannot prove what the running pods resolved at start).
        if expected_keyref_hashes:
            for key, expected_identity in expected_keyref_hashes.items():
                live_identity = target.explicit_keyref_hashes.get(key)
                if live_identity is not None and live_identity != expected_identity:
                    mismatches.append(
                        ValueMismatch(
                            key=key, expected_hash=expected_identity, live_hash=live_identity, target=target.name
                        )
                    )
        # The reverse direction is provable too: a key the chart renders as a
        # literal (or any non-keyref source) that serving binds through
        # configMapKeyRef. The subtraction above already removed it from value
        # comparison (explicit_unproven), and expected_keyref_hashes cannot
        # contain it (the expected source is not a keyref), so without this
        # check the source change would vanish into INVENTORY with a strict
        # exit 0. The immutable pod spec proves the live binding and the
        # repository proves the expected source, so compare them directly.
        # Their hashes live in disjoint domains (``value:`` vs ``configmap:``),
        # so a source change always shows as a mismatch; an expected source the
        # repository cannot prove (None hash, deploy-time binding) still skips
        # the comparison — name-only, no false drift.
        for key, live_identity in target.explicit_keyref_hashes.items():
            if key in (expected_keyref_hashes or {}):
                continue  # expected keyref: handled by the identity check above
            want = expected_env.get(key)
            if want is None:
                continue
            if live_identity != want:
                mismatches.append(
                    ValueMismatch(key=key, expected_hash=want, live_hash=live_identity, target=target.name)
                )
    template_matches: bool | None = None
    if live.template_env is not None and live.source == 'serving':
        template_fp = env_fingerprint(live.template_env)
        template_matches = all(
            target.fingerprint == template_fp
            # envFrom identities belong to the template comparison too: a
            # template rebinding ConfigMap A to ConfigMap B with identical data
            # passes the fingerprint but is exactly the divergence this field
            # exists to reveal. Compared unconditionally — an empty template
            # identity list against a still-referencing ReplicaSet is itself
            # divergence the next rollout would apply.
            and list(target.envfrom_refs) == list(live.template_envfrom_refs)
            for target, _ in live.targets
        )
    primary = live.targets[0][0]
    return ServiceEnvDrift(
        service=service,
        manifest_key_count=len(declared),
        live_key_count=primary.key_count,
        allowlisted_live_only=tuple(sorted(live_only & allowed)),
        unallowlisted_live_only=tuple(sorted(live_only - allowed)) if expected is not None else (),
        platform=platform,
        source=live.source,
        serving=tuple(target for target, _ in live.targets),
        value_mismatches=tuple(mismatches),
        missing_from_live=tuple(sorted(missing)),
        value_unchecked_keys=sum(1 for digest in expected_env.values() if digest is None),
        template_name=live.template_name,
        template_matches_serving=template_matches,
        expected_available=expected is not None,
        envfrom_refs=expected_envfrom_refs if expected is not None else (),
        envfrom_mismatched_refs=envfrom_mismatched,
        envfrom_unresolved=envfrom_unresolved,
        envfrom_unproven=envfrom_unproven,
        explicit_unproven_keys=tuple(sorted(explicit_unproven)),
        alias_unproven_keys=tuple(sorted(alias_unproven)),
    )


def allowlist_for_service(
    service: str,
    allowlist_map: Mapping[str, frozenset[str]] = LIVE_MANAGED_ENV_ALLOWLIST,
) -> frozenset[str]:
    return allowlist_map.get('*', frozenset()) | allowlist_map.get(service, frozenset())


def load_allowlist_file(path: Path) -> dict[str, frozenset[str]]:
    raw = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(raw, dict):
        raise ValueError(f'{path} must contain a mapping of service name (or "*") to key lists')
    merged: dict[str, set[str]] = {key: set(values) for key, values in LIVE_MANAGED_ENV_ALLOWLIST.items()}
    for scope, keys in raw.items():
        if not isinstance(scope, str) or not isinstance(keys, list) or not all(isinstance(k, str) and k for k in keys):
            raise ValueError(f'{path}: allowlist entry for {scope!r} must be a list of non-empty key names')
        merged.setdefault(scope, set()).update(keys)
    return {scope: frozenset(names) for scope, names in merged.items()}


def _error_result(service: str, *, declared: int, platform: str, exc: Exception) -> ServiceEnvDrift:
    return ServiceEnvDrift(
        service=service,
        manifest_key_count=declared,
        live_key_count=0,
        allowlisted_live_only=(),
        unallowlisted_live_only=(),
        error=str(exc),
        platform=platform,
    )


def _split_offline_state(state: Mapping[str, Any] | None) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
    if state is None:
        return None, None
    services = state.get('services')
    revisions = state.get('revisions')
    return (
        services if isinstance(services, Mapping) else state,
        revisions if isinstance(revisions, Mapping) else {},
    )


def inspect_services_drift(
    *,
    env: str,
    services: Sequence[str] = DEFAULT_SERVICES,
    project: str | None = None,
    region: str | None = None,
    manifest_path: Path = DEFAULT_MANIFEST,
    rendered_state_path: Path | None = None,
    cloud_run_state: Mapping[str, Any] | None = None,
    allowlist_map: Mapping[str, frozenset[str]] = LIVE_MANAGED_ENV_ALLOWLIST,
    runner: Any = subprocess.run,
    environ: Mapping[str, str] | None = None,
    canonical_secret_hashes: dict[str, dict[str, str]] | None = None,
) -> tuple[str, str, tuple[ServiceEnvDrift, ...]]:
    # The canonical map is derived, not caller input: default-construct it so
    # the alias degradation works for every caller (the parameter stays so
    # tests can observe what was derived).
    if canonical_secret_hashes is None:
        canonical_secret_hashes = {}
    manifest_project, manifest_region, expected_by_service = expected_cloud_run_env(
        env=env,
        manifest_path=manifest_path,
        rendered_state_path=rendered_state_path,
        environ=environ,
        canonical_secret_hashes=canonical_secret_hashes,
    )
    resolved_project = project or manifest_project
    resolved_region = region or manifest_region
    offline_services, offline_revisions = _split_offline_state(cloud_run_state)

    results: list[ServiceEnvDrift] = []
    for service in services:
        if service not in expected_by_service:
            raise ValueError(f'Service {service!r} is not declared in {manifest_path} for env {env!r}')
        expected = expected_by_service[service]
        try:
            live = read_cloud_run_service(
                service,
                project=resolved_project,
                region=resolved_region,
                offline_services=offline_services,
                offline_revisions=offline_revisions,
                runner=runner,
            )
            results.append(
                compare_service(
                    service,
                    expected=expected,
                    live=live,
                    allowed=allowlist_for_service(service, allowlist_map),
                    platform='cloud_run',
                    expected_canonical_secret_hashes=(canonical_secret_hashes or {}).get(service) or {},
                )
            )
        except Exception as exc:
            results.append(_error_result(service, declared=len(expected), platform='cloud_run', exc=exc))
    return resolved_project, resolved_region, tuple(results)


def inspect_gke_drift(
    *,
    env: str,
    workloads: Sequence[str] = DEFAULT_GKE_WORKLOADS,
    kube_context: str | None = None,
    render: str = 'values',
    gke_state: Mapping[str, Any] | None = None,
    expected_overrides: Mapping[str, ExpectedEnv] | None = None,
    allowlist_map: Mapping[str, frozenset[str]] = LIVE_MANAGED_ENV_ALLOWLIST,
    runner: Any = subprocess.run,
    root: Path = ROOT,
    manifest_path: Path = DEFAULT_MANIFEST,
    helm_args_for: Mapping[str, Sequence[str]] | None = None,
) -> tuple[ServiceEnvDrift, ...]:
    cm_name, cm_entries = manifest_config_map(env, manifest_path)
    envfrom_expected = _expected_envfrom_entries(cm_entries) if cm_name else {}
    results: list[ServiceEnvDrift] = []
    replicaset_cache: dict[str, Any] = {}
    configmap_cache: dict[str, Any] = {}
    for workload in workloads:
        if workload not in GKE_WORKLOADS:
            raise ValueError(f'Unknown GKE workload {workload!r}; known: {", ".join(GKE_WORKLOADS)}')
        # Override arguments are workload-scoped: an argv generated from one
        # chart's env indices must not be applied to a different chart.
        workload_helm_args = (helm_args_for or {}).get(workload, ())
        expected: ExpectedEnv | None = None
        expected_refs: tuple[str, ...] = ()
        expected_unresolved: tuple[str, ...] = ()
        expected_envfrom_keys: frozenset[str] = frozenset()
        expected_envfrom_keys_by_ref: dict[str, frozenset[str]] = {}
        expected_keyref_hashes: dict[str, str] = {}
        try:
            # Values mode cannot honor override tokens: it reads the chart
            # values file directly, so every --gke-helm-arg /
            # --gke-helm-arg-file token (exact deployed values or --set-string
            # inputs) would be silently ignored and the comparison would run
            # against repository defaults, reporting false drift for a
            # legitimately overridden rollout. Reject the incompatible
            # invocation as an operational error instead (per workload, so
            # token-free workloads in the same run still report).
            if render != 'helm' and workload_helm_args:
                raise ValueError(
                    f'--gke-render {render!r} ignores --gke-helm-arg override tokens for {workload!r}; '
                    'use --gke-render helm so the expected state is rendered from the exact deployed inputs'
                )
            if expected_overrides is not None and workload in expected_overrides:
                expected = dict(expected_overrides[workload])
                expected_refs = expected_gke_envfrom_refs(workload, env=env, root=root)
            elif render == 'helm':
                expected, expected_refs, expected_keyref_hashes = expected_gke_env_from_helm(
                    workload, env=env, root=root, runner=runner, helm_args=workload_helm_args
                )
            else:
                expected, expected_keyref_hashes = expected_gke_env_from_values(workload, env=env, root=root)
                expected_refs = expected_gke_envfrom_refs(workload, env=env, root=root)
            if expected is not None:
                merged_keys: set[str] = set()
                for ref in expected_refs:
                    source_name, source_prefix = _parse_envfrom_ref_identity(ref)
                    if source_name == cm_name:
                        # The expected keys carry the reference's prefix: a
                        # ``prefix: CFG_`` source yields ``CFG_<key>``, the env
                        # names a pod actually receives.
                        ref_keys = {f'{source_prefix}{key}' for key in envfrom_expected}
                        for key, digest in envfrom_expected.items():
                            expected.setdefault(f'{source_prefix}{key}', digest)
                        merged_keys |= ref_keys
                        expected_envfrom_keys_by_ref[ref] = frozenset(ref_keys)
                    else:
                        # The chart references a ConfigMap whose expected keys the
                        # repository cannot enumerate; report inventory, not silence.
                        expected_unresolved = (*expected_unresolved, ref)
                expected_envfrom_keys = frozenset(merged_keys)
            live = read_gke_workload(
                workload,
                env=env,
                kube_context=kube_context,
                offline_gke=gke_state,
                runner=runner,
                replicaset_cache=replicaset_cache,
                configmap_cache=configmap_cache,
            )
            results.append(
                compare_service(
                    workload,
                    expected=expected,
                    live=live,
                    allowed=allowlist_for_service(workload, allowlist_map),
                    platform='gke',
                    expected_envfrom_refs=expected_refs if expected is not None else (),
                    expected_envfrom_unresolved=expected_unresolved,
                    expected_envfrom_keys=expected_envfrom_keys,
                    expected_envfrom_keys_by_ref=expected_envfrom_keys_by_ref,
                    expected_keyref_hashes=expected_keyref_hashes,
                )
            )
        except Exception as exc:
            results.append(_error_result(workload, declared=len(expected or {}), platform='gke', exc=exc))
    return tuple(results)


# ── reports ─────────────────────────────────────────────────────────────────


def _template_cell(item: ServiceEnvDrift) -> str:
    if item.template_matches_serving is None:
        return 'n/a'
    return 'yes' if item.template_matches_serving else '**no**'


def render_markdown_report(
    *,
    env: str,
    project: str,
    region: str,
    results: Sequence[ServiceEnvDrift],
) -> str:
    lines = [
        f'## Runtime env drift: serving workloads vs repository ({env} / `{project}` / `{region}`)',
        '',
        'Read-only comparison of the env that is **serving** (Cloud Run `status.traffic` revisions; GKE ReplicaSets '
        'with ready pods) against `backend/deploy/runtime_env.yaml` and chart values, by key name and value hash. '
        'Values are never printed; hashes of sensitive-looking keys are redacted.',
        '',
        '| Workload | Platform | Serving | Expected keys | Live keys | Value mismatches | Missing live | '
        'Unallowlisted live-only | Allowlisted live-only | Template = serving | Status |',
        '| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |',
    ]
    for item in results:
        status = f'ERROR ({item.error})' if item.error else item.status
        serving = ', '.join(
            f'`{t.name}` ({t.weight}{"%" if item.platform == "cloud_run" else " ready"})' for t in item.serving
        )
        lines.append(
            f'| `{item.service}` | {item.platform} | {serving or "-"} | {item.manifest_key_count} | {item.live_key_count} | '
            f'{len(item.value_mismatches)} | {len(item.missing_from_live)} | {len(item.unallowlisted_live_only)} | '
            f'{len(item.allowlisted_live_only)} | {_template_cell(item)} | {status} |'
        )
    lines.append('')
    for item in results:
        lines.append(f'### `{item.service}` ({item.platform})')
        if item.error:
            lines.extend([f'- Fetch error: `{item.error}`', ''])
            continue
        for target in item.serving:
            lines.append(
                f'- Serving `{target.name}`: weight {target.weight}, {target.key_count} keys, '
                f'env fingerprint `{target.display_fingerprint}`'
            )
        if item.template_matches_serving is False:
            lines.append(
                f'- Template `{item.template_name}` differs from what is serving. Read serving revisions, not the template.'
            )
        if not item.expected_available:
            lines.append(
                '- Expected env unavailable in values mode (chart builds env in its template); use `--gke-render helm`.'
            )
        if item.envfrom_unresolved:
            refs_str = ', '.join(f'`{name}`' for name in item.envfrom_unresolved)
            lines.append(f'- envFrom ConfigMap keys not compared (unresolved): {refs_str}')
        if item.envfrom_unproven:
            refs_str = ', '.join(f'`{name}`' for name in item.envfrom_unproven)
            lines.append(
                f'- envFrom ConfigMap keys not compared (live data unproven for running pods; '
                f'K8s never refreshes envFrom): {refs_str}'
            )
        if item.explicit_unproven_keys:
            keys_str = ', '.join(f'`{name}`' for name in item.explicit_unproven_keys)
            lines.append(
                f'- Explicit env keys not value-compared (configMapKeyRef binding; live ConfigMap data '
                f'cannot prove the value running pods resolved): {keys_str}'
            )
        if item.alias_unproven_keys:
            keys_str = ', '.join(f'`{name}`' for name in item.alias_unproven_keys)
            lines.append(
                f'- Alias-resolved secret keys not value-compared (project-ID/number form ambiguity; '
                f'name and version matched): {keys_str}'
            )
        if item.envfrom_mismatched_refs:
            refs_str = ', '.join(f'`{name}`' for name in item.envfrom_mismatched_refs)
            lines.append(f'- envFrom ConfigMap reference drift (live vs expected): {refs_str}')
        elif item.envfrom_refs:
            refs_str = ', '.join(f'`{name}`' for name in item.envfrom_refs)
            lines.append(f'- envFrom ConfigMaps (expected and serving): {refs_str}')
        if item.value_unchecked_keys:
            lines.append(
                f'- Keys compared by name only (deploy-time binding, no rendered state): {item.value_unchecked_keys}'
            )
        allowlisted_str = ', '.join(f'`{name}`' for name in item.allowlisted_live_only) or 'none'
        lines.append(f'- Allowlisted live-managed keys ({len(item.allowlisted_live_only)}): {allowlisted_str}')
        drift_str = ', '.join(f'`{name}`' for name in item.unallowlisted_live_only) or 'none'
        lines.append(
            f'- Unallowlisted live keys missing from manifest ({len(item.unallowlisted_live_only)}): {drift_str}'
        )
        missing_str = ', '.join(f'`{name}`' for name in item.missing_from_live) or 'none'
        lines.append(f'- Expected keys absent from serving env ({len(item.missing_from_live)}): {missing_str}')
        lines.append(f'- Value mismatches ({len(item.value_mismatches)}):' + ('' if item.value_mismatches else ' none'))
        for mismatch in item.value_mismatches:
            lines.append(
                f'  - `{mismatch.key}` on `{mismatch.target}`: expected `{display_hash(mismatch.key, mismatch.expected_hash)}`, '
                f'serving `{display_hash(mismatch.key, mismatch.live_hash)}`'
            )
        lines.append('')
    return '\n'.join(lines)


def render_json_report(
    *,
    env: str,
    project: str,
    region: str,
    results: Sequence[ServiceEnvDrift],
) -> str:
    payload = {
        'env': env,
        'project': project,
        'region': region,
        'drift': any(item.has_drift for item in results),
        'errors': sum(1 for item in results if item.error),
        # Keyed by platform and name: Cloud Run and GKE results can share a
        # workload name (e.g. --service pusher --gke-workload pusher), and a
        # name-only key would silently drop one platform's entry.
        'services': {
            f'{item.platform}:{item.service}': {
                'platform': item.platform,
                'status': item.status,
                'source': item.source,
                'manifest_key_count': item.manifest_key_count,
                'live_key_count': item.live_key_count,
                'serving': [
                    {'name': t.name, 'weight': t.weight, 'key_count': t.key_count, 'fingerprint': t.display_fingerprint}
                    for t in item.serving
                ],
                'template_name': item.template_name,
                'template_matches_serving': item.template_matches_serving,
                'allowlisted_live_only': list(item.allowlisted_live_only),
                'unallowlisted_live_only': list(item.unallowlisted_live_only),
                'missing_from_live': list(item.missing_from_live),
                'value_unchecked_keys': item.value_unchecked_keys,
                'envfrom_refs': list(item.envfrom_refs),
                'envfrom_mismatched_refs': list(item.envfrom_mismatched_refs),
                'envfrom_unresolved': list(item.envfrom_unresolved),
                'envfrom_unproven': list(item.envfrom_unproven),
                'explicit_unproven_keys': list(item.explicit_unproven_keys),
                'alias_unproven_keys': list(item.alias_unproven_keys),
                'value_mismatches': [
                    {
                        'key': m.key,
                        'target': m.target,
                        'expected_hash': display_hash(m.key, m.expected_hash),
                        'live_hash': display_hash(m.key, m.live_hash),
                    }
                    for m in item.value_mismatches
                ],
                **({'error': item.error} if item.error else {}),
            }
            for item in results
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True) + '\n'


def exit_code(results: Sequence[ServiceEnvDrift], *, strict: bool) -> int:
    if not strict:
        return 0
    # An incomplete comparison outranks drift found elsewhere: a train gate must not
    # read a fetch/render failure as an ordinary, already-diagnosed drift case.
    if any(item.error for item in results):
        return 2
    if any(item.has_drift for item in results):
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--env', choices=('dev', 'prod'), default='prod')
    parser.add_argument('--project', help='GCP project ID (defaults to manifest compute_project for --env).')
    parser.add_argument('--region', help='Cloud Run region (defaults to manifest region for --env).')
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        '--rendered-state',
        type=Path,
        help='Optional state JSON from render_backend_runtime_env.py --state-output (exact expected values).',
    )
    parser.add_argument(
        '--cloud-run-state',
        type=Path,
        help='Offline JSON fixture: {"services": {name: describe-doc}, "revisions": {name: revision-doc}}.',
    )
    parser.add_argument(
        '--allowlist-file',
        type=Path,
        help='Optional YAML/JSON file extending the live-managed key allowlist.',
    )
    parser.add_argument('--service', action='append', dest='services', help='Cloud Run service name (repeatable).')
    parser.add_argument('--no-cloud-run', action='store_true', help='Skip Cloud Run services (GKE only).')
    parser.add_argument('--gke', action='store_true', help='Also check GKE workloads (listen, pusher, batch worker).')
    parser.add_argument(
        '--gke-workload',
        action='append',
        dest='gke_workloads',
        choices=tuple(GKE_WORKLOADS),
        help='GKE workload to check (repeatable; implies --gke).',
    )
    parser.add_argument('--kube-context', help='Explicit kubectl context for live GKE reads (required with --gke).')
    parser.add_argument(
        '--gke-render',
        choices=('values', 'helm', 'auto'),
        default='auto',
        help='Expected GKE env source: chart values env list, `helm template`, or helm when on PATH.',
    )
    parser.add_argument(
        '--gke-helm-arg',
        action='append',
        dest='gke_helm_args',
        help='Extra helm argument for the expected-state render (repeatable), e.g. '
        '--gke-helm-arg="--set-string" --gke-helm-arg="env[0].value=x" (use the --opt=value form for '
        'values that start with "-"). Use the exact tokens the deploy passed so an intentionally '
        'overridden rollout is not reported as drift.',
    )
    parser.add_argument(
        '--gke-helm-arg-file',
        type=Path,
        help='File with one helm argument per line (the argv file written by '
        'listen_helm_env_overrides.py --output-argv-file in the deploy workflow).',
    )
    parser.add_argument(
        '--gke-helm-arg-workload',
        choices=(*GKE_WORKLOADS, 'all'),
        default='backend-listen',
        help='Workload the --gke-helm-arg / --gke-helm-arg-file tokens apply to. Override '
        'arguments encode one chart env-index list (the argv file is generated from '
        'backend-listen values), so applying them to another chart can rewrite a '
        'different variable or fail the render; pass "all" only for chart-agnostic '
        'arguments such as -f flags valid for every workload.',
    )
    parser.add_argument(
        '--gke-state',
        type=Path,
        help='Offline GKE JSON fixture: {workload: {deployment, replicasets}} plus optional '
        'shared {"configmaps": {name: {"data": {...}}}} for envFrom resolution.',
    )
    parser.add_argument('--format', choices=('markdown', 'json'), default='markdown')
    parser.add_argument(
        '--summary-file', type=Path, help='Append markdown report to this file (e.g. GITHUB_STEP_SUMMARY).'
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Exit 1 on drift (value mismatch, missing or unallowlisted key), 2 on fetch/render errors '
        '(2 wins when both: the comparison did not complete).',
    )
    args = parser.parse_args(argv)

    if args.no_cloud_run and not (args.gke or args.gke_workloads):
        parser.error('--no-cloud-run requires --gke or --gke-workload; otherwise there is nothing to check')

    services = tuple(args.services or DEFAULT_SERVICES)

    try:
        # Input loads belong inside the handled section: a missing or malformed
        # --cloud-run-state / --gke-state / --allowlist-file is an operational
        # (exit 2) failure, not drift, and must not escape as an uncaught
        # exception or be misclassified as confirmed drift (exit 1).
        allowlist_map = load_allowlist_file(args.allowlist_file) if args.allowlist_file else LIVE_MANAGED_ENV_ALLOWLIST
        gke_helm_args = list(args.gke_helm_args or [])
        if args.gke_helm_arg_file is not None:
            # One token per line — the same format listen_helm_env_overrides.py
            # writes for the deploy workflow, so the checker can render the
            # exact deployed chart inputs instead of repository defaults.
            gke_helm_args.extend(
                line for line in args.gke_helm_arg_file.read_text(encoding='utf-8').splitlines() if line.strip()
            )
        # Override tokens are scoped to one workload: they encode that chart's
        # env indices, and a blind forward to every chart could rewrite a
        # different variable (or fail the render) on the other workloads.
        gke_helm_args_for: dict[str, Sequence[str]] = {'*': ()}
        if gke_helm_args:
            gke_helm_args_for = {
                workload: (gke_helm_args if args.gke_helm_arg_workload in (workload, 'all') else ())
                for workload in GKE_WORKLOADS
            }
        # Offline fixture loads belong inside the handled section: a missing or
        # malformed --cloud-run-state / --gke-state is an operational (exit 2)
        # failure, not drift, and must not escape as an uncaught exception.
        offline_state = (
            cast(Mapping[str, Any], json.loads(args.cloud_run_state.read_text(encoding='utf-8')))
            if args.cloud_run_state
            else None
        )
        project, region, results = inspect_services_drift(
            env=args.env,
            services=() if args.no_cloud_run else services,
            project=args.project,
            region=args.region,
            manifest_path=args.manifest,
            rendered_state_path=args.rendered_state,
            cloud_run_state=offline_state,
            allowlist_map=allowlist_map,
        )
        if args.gke or args.gke_workloads:
            render = args.gke_render
            if render == 'auto':
                render = 'helm' if shutil.which('helm') else 'values'
            gke_state = (
                cast(Mapping[str, Any], json.loads(args.gke_state.read_text(encoding='utf-8')))
                if args.gke_state
                else None
            )
            results = results + inspect_gke_drift(
                env=args.env,
                workloads=tuple(args.gke_workloads or DEFAULT_GKE_WORKLOADS),
                kube_context=args.kube_context,
                render=render,
                gke_state=gke_state,
                allowlist_map=allowlist_map,
                manifest_path=args.manifest,
                helm_args_for=gke_helm_args_for,
            )
    except Exception as exc:
        # Expected-state render failures (unreadable/malformed manifest or rendered
        # state) are operational errors, not drift: report and exit with the
        # documented render-error status instead of a traceback and exit 1.
        print(f'ERROR: could not render expected state: {exc}', file=sys.stderr)
        return 2 if args.strict else 0

    markdown = render_markdown_report(env=args.env, project=project, region=region, results=results)
    if args.format == 'json':
        sys.stdout.write(render_json_report(env=args.env, project=project, region=region, results=results))
    else:
        sys.stdout.write(markdown)

    if args.summary_file is not None:
        try:
            with args.summary_file.open('a', encoding='utf-8') as handle:
                handle.write(markdown)
                if not markdown.endswith('\n'):
                    handle.write('\n')
        except OSError as exc:
            print(f'WARNING: could not write summary file {args.summary_file}: {exc}', file=sys.stderr)

    return exit_code(results, strict=args.strict)


if __name__ == '__main__':
    raise SystemExit(main())
