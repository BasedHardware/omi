"""Build a run overlay from the ref's own ``backend/deploy/runtime_env.yaml`` (production profile).

The lab clears the process env (``stack/env.py``), so without this every product flag takes
its code default, not the value production ran with. This reads the generated runtime env
of one service at the ref under test and returns an overlay in the one schema
(``{name, env, model_config, serving, gates, strict}``):

- ``env``: scalar rollout / ops values, minus anything secret-shaped, any endpoint, project
  or bucket (the lab owns those: loopback emulators, the proxy, local storage) and the
  variables the lab stack pins itself;
- ``serving``: every cohort (``<NAME>_SERVE_PERCENT`` / ``<NAME>_SERVE_UID_SHA256S``) pinned to
  a boolean. With the owner uid (read from an environment variable, never written) the
  decision is the product's own ``serving_for`` against the production env; without it,
  100 % cohorts pin ``true``, empty ones ``false`` and partial ones ``false`` and are listed
  as ``unresolved`` so the lead can decide.
- every other serve decision the ref's code makes (``serving_for('<NAME>', ...)`` literals and
  ``*_MODE`` env) is pinned too: with no cohort env it is uid-independent, so the pin is the
  product's own answer for any uid and ``decisions.jsonl`` shows no ``unpinned`` rows;
- uid allow-lists (``*_UID_ALLOWLIST``, ``*_UIDS``, ``*_UID``): with the owner uid, the owner's
  membership is carried over to the lab uid (the value becomes ``local-dev-user`` or empty);
  without it the list is emptied and listed in ``unresolved``. A production uid never reaches
  the overlay (checked).

**Service.** ``backend-sync`` is the default: the v3 reconcile task targets the host of
``SYNC_TASKS_HANDLER_URL`` (``utils/conversations/v3/triggers.task_base``), which is
backend-sync, and that task runs the outline, the planner, the notes drain
(``process_conversation`` for each v3 conversation: memories, tasks, pushes) and the
conversation-created fanout. The recording intake (``mark_new``, ``recording_short_path``)
runs where captures finalize, but reads only the admission switches, which every service
carries identically (``deploy/compose_runtime_env._apply_conversations_v3_stage``).

Nothing here reaches the network or writes the uid anywhere.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Optional

SECRETISH = re.compile(r'(TOKEN|SECRET|PASSWORD|API_KEY|CREDENTIAL|PRIVATE|_KEY$|_KEYS$|DSN)', re.IGNORECASE)
ENDPOINTISH = re.compile(
    r'(_URL|_URLS|_URI|_HOST|_HOSTS|_PORT|_ENDPOINT|_ENDPOINTS|_BUCKET|_BUCKETS|_PROJECT|_PROJECT_ID|_REGION|'
    r'_QUEUE|_QUEUES|_TOPIC|_SUBSCRIPTION|_SERVICE_ACCOUNT|_DATASET|_INSTANCE|_LOCATION)$'
)
COHORT_SUFFIXES = ('_SERVE_PERCENT', '_SERVE_UID_SHA256S')
DEFAULT_SERVICE = 'backend-sync'
UID_LIST = re.compile(r'(_UID_ALLOWLIST|_ALLOWLIST_UIDS|_UIDS|_UID)$')
SERVING_LITERAL = re.compile(r"serving_for\(\s*['\"]([A-Z][A-Z0-9_]+)['\"]")
# Mode names bound through constants (``X_MODE_ENV = 'X_MODE'``) are found as string literals.
MODE_LITERAL = re.compile(r"['\"]([A-Z][A-Z0-9_]*_MODE)['\"]")
V3_SWITCHES = (
    'CONVERSATIONS_V3',
    'CONVERSATIONS_V3_STAGE',
    'CONVERSATIONS_V3_RECORDING_ROTATION',
    'CONVERSATIONS_V3_ROTATION_MIN_SECONDS',
    'CONVERSATIONS_V3_ROTATION_MAX_SECONDS',
    'CONVERSATIONS_V3_BACKFILL',
    'CONVERSATIONS_V3_UID_ALLOWLIST',
    'OMI_SHAPED_AGENT_MODE',
    'OCCASION_CONVERSATIONS_ENABLED',
)


def static_mode_names(backend: Path) -> set[str]:
    """Serve-mode names in the ref's product code: ``serving_for`` literals and ``'*_MODE'`` strings.

    A superset is harmless: pinning a name nothing reads changes nothing.
    """
    names: set[str] = set()
    for path in Path(backend).rglob('*.py'):
        parts = path.relative_to(backend).parts
        if parts and parts[0] in {'tests', 'testing', '.venv', 'scripts'}:
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        if 'serving_for' in text:
            names.update(SERVING_LITERAL.findall(text))
        if '_MODE' in text:
            names.update(MODE_LITERAL.findall(text))
    return names


def _service_env(document: Mapping[str, Any], environment: str, service: str) -> dict[str, Any]:
    env_block = (document.get('environments') or {}).get(environment)
    if not isinstance(env_block, Mapping):
        raise ValueError(f'runtime env has no environment {environment!r}')
    candidates = [
        (env_block.get('gke') or {}).get(service),
        ((env_block.get('cloud_run') or {}).get('services') or {}).get(service),
        ((env_block.get('cloud_run') or {}).get('jobs') or {}).get(service),
    ]
    for candidate in candidates:
        if isinstance(candidate, Mapping) and isinstance(candidate.get('env'), Mapping):
            return dict(candidate['env'])
    raise ValueError(f'runtime env {environment} has no service {service!r} with env')


def _scalar(entry: Any) -> Optional[str]:
    value = entry.get('value') if isinstance(entry, Mapping) else entry
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (str, int, float)):
        return str(value)
    return None


def remap_uid_list(value: str, owner_uid: Optional[str]) -> tuple[str, str]:
    """``(value, state)``: a uid allow-list reduced to the lab uid when the owner (or the lab uid) is on it."""
    from testing.pipeline_lab.stack import LAB_UID

    members = [m.strip() for m in value.split(',') if m.strip()]
    if LAB_UID in members or (owner_uid and owner_uid in members):
        return LAB_UID, 'owner_member'
    if owner_uid:
        return '', 'owner_not_member'
    return '', 'unresolved' if members else 'empty'


def filter_live_env(describe: Mapping[str, Any], owner_uid: str) -> dict[str, Any]:
    """The non-secret plain env of a Cloud Run service as served, from ``gcloud run services describe
    --format=json``. Secret-named variables and secret references are dropped here, so their values
    are never written; uid allow-lists are reduced to the lab uid (owner membership) and any other
    occurrence of the owner uid is replaced, so no production uid is written either. The revision
    receiving traffic and its release sha are kept for the record."""
    from testing.pipeline_lab.stack import LAB_UID

    if not owner_uid:
        raise ValueError('filter_live_env needs the owner uid to scrub uid allow-lists')
    spec = ((describe.get('spec') or {}).get('template') or {}).get('spec') or {}
    env: dict[str, str] = {}
    dropped = 0
    for container in spec.get('containers') or []:
        for entry in container.get('env') or []:
            name = str(entry.get('name') or '')
            if not name or 'value' not in entry or SECRETISH.search(name):
                dropped += 1
                continue
            value = str(entry.get('value') or '')
            if UID_LIST.search(name) and not name.endswith(COHORT_SUFFIXES):
                value, _ = remap_uid_list(value, owner_uid)
            env[name] = value.replace(owner_uid, LAB_UID)
    traffic = [
        {'revision': t.get('revisionName'), 'percent': t.get('percent')}
        for t in (describe.get('status') or {}).get('traffic') or []
    ]
    return {
        'service': (describe.get('metadata') or {}).get('name'),
        'traffic': traffic,
        'release_sha': env.get('OMI_BACKEND_RELEASE_SHA'),
        'dropped_secret_or_ref': dropped,
        'env': env,
    }


def overlay_from_runtime_env(
    runtime_env: Path,
    *,
    environment: str = 'prod',
    service: str = DEFAULT_SERVICE,
    owner_uid: Optional[str] = None,
    name: Optional[str] = None,
    live_env: Optional[Mapping[str, Any]] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """``live_env`` (from :func:`filter_live_env`) overlays the served revision's plain values on the
    runtime env: production also sets ops-file and live-only keys that ``runtime_env.yaml`` lacks
    (``deploy/ops/prod.yaml``, ``deploy/ops/live_only.yaml``). Every filter below applies to both."""
    """``(overlay, report)``. ``report`` lists what was kept, dropped and left unresolved."""
    import yaml

    from testing.pipeline_lab.stack.config import LabStackConfig
    from testing.pipeline_lab.stack.overlay import DEFAULT_ENV

    document = yaml.safe_load(Path(runtime_env).read_text(encoding='utf-8'))
    raw = _service_env(document, environment, service)
    live_report: dict[str, Any] = {}
    if live_env is not None:
        live = {str(k): v for k, v in (live_env.get('env') or {}).items()}
        live_report = {
            'service': live_env.get('service'),
            'release_sha': live_env.get('release_sha'),
            'traffic': live_env.get('traffic'),
            'added': sorted(k for k in live if k not in raw),
            'overridden': sorted(k for k in live if k in raw and _scalar(raw[k]) != live[k]),
        }
        raw = {**raw, **live}
    lab_owned = set(LabStackConfig().product_env()) | set(DEFAULT_ENV)
    env: dict[str, str] = {}
    cohort_env: dict[str, str] = {}
    dropped: dict[str, list[str]] = {'secret': [], 'endpoint': [], 'lab_owned': [], 'not_scalar': []}
    uid_lists: dict[str, str] = {}
    for key, entry in sorted(raw.items()):
        value = _scalar(entry)
        if value is not None and UID_LIST.search(key) and not key.endswith(COHORT_SUFFIXES):
            env[key], uid_lists[key] = remap_uid_list(value, owner_uid)
            continue
        if value is None:
            dropped['not_scalar'].append(key)
        elif key.endswith(COHORT_SUFFIXES):
            cohort_env[key] = value
        elif SECRETISH.search(key):
            dropped['secret'].append(key)
        elif ENDPOINTISH.search(key) or '://' in value:
            dropped['endpoint'].append(key)
        elif key in lab_owned:
            dropped['lab_owned'].append(key)
        else:
            env[key] = value
    serving: dict[str, bool] = {}
    unresolved: list[str] = []
    names = sorted({key[: -len(suffix)] for key in cohort_env for suffix in COHORT_SUFFIXES if key.endswith(suffix)})
    if names:
        from config.refactor_modes import _COHORT_ENVS, mode as parsed_mode, serving_for

        reverse = {pair[0]: mode for mode, pair in _COHORT_ENVS.items()}
        reverse.update({pair[1]: mode for mode, pair in _COHORT_ENVS.items()})
        modes = sorted({reverse.get(f'{n}_SERVE_PERCENT') or reverse.get(f'{n}_SERVE_UID_SHA256S') or n for n in names})
        production = {**env, **cohort_env}
        for mode in modes:
            percent_env, digests_env = _COHORT_ENVS.get(mode, (f'{mode}_SERVE_PERCENT', f'{mode}_SERVE_UID_SHA256S'))
            if owner_uid:
                serving[mode] = bool(serving_for(mode, owner_uid, environ=production))
                continue
            try:
                percent = float(cohort_env.get(percent_env) or 0)
            except ValueError:
                percent = 0.0
            digests = [d for d in (cohort_env.get(digests_env) or '').split(',') if d.strip()]
            if parsed_mode(mode, environ=production) == 'off':
                # An unset mode is off unless the family is a frozen legacy shadow (refactor_modes).
                serving[mode] = False
            elif percent >= 100:
                serving[mode] = True
            else:
                serving[mode] = False
                if percent > 0 or digests:
                    unresolved.append(mode)
    pinned_static: list[str] = []
    backend = Path(runtime_env).resolve().parents[1]
    static = static_mode_names(backend) if (backend / 'config' / 'refactor_modes.py').is_file() else set()
    static.update(key for key in env if key.endswith('_MODE'))
    if static - set(serving):
        from config.refactor_modes import serving_for as product_serving_for

        production = {**env, **cohort_env}
        for mode in sorted(static - set(serving)):
            # No cohort env for this name: the answer is the same for every uid.
            serving[mode] = bool(product_serving_for(mode, owner_uid or 'pipeline-lab-probe', environ=production))
            pinned_static.append(mode)
    unresolved.extend(f'uid_list:{key}' for key, state in sorted(uid_lists.items()) if state == 'unresolved')
    overlay = {
        'name': name or f'runtime-env:{environment}:{service}',
        'env': env,
        'model_config': {},
        'serving': serving,
        'gates': {},
        'strict': False,
    }
    report = {
        'environment': environment,
        'service': service,
        'kept': len(env),
        'cohorts': len(serving),
        'owner_resolved': bool(owner_uid),
        'unresolved': unresolved,
        'dropped': {k: len(v) for k, v in dropped.items()},
        'dropped_names': dropped,
        'pinned_static': len(pinned_static),
        'uid_lists': uid_lists,
        'v3': {key: env.get(key, '(unset: code default)') for key in V3_SWITCHES},
        'live': {
            k: (len(v) if isinstance(v, list) and k in ('added', 'overridden') else v) for k, v in live_report.items()
        },
        'live_names': {k: live_report[k] for k in ('added', 'overridden') if k in live_report},
    }
    if owner_uid:
        import json

        if owner_uid in json.dumps(overlay):
            raise ValueError('the owner uid survived into the overlay')
    return overlay, report
