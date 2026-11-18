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
DEFAULT_SERVICE = 'backend-listen'


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


def overlay_from_runtime_env(
    runtime_env: Path,
    *,
    environment: str = 'prod',
    service: str = DEFAULT_SERVICE,
    owner_uid: Optional[str] = None,
    name: Optional[str] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """``(overlay, report)``. ``report`` lists what was kept, dropped and left unresolved."""
    import yaml

    from testing.pipeline_lab.stack.config import LabStackConfig
    from testing.pipeline_lab.stack.overlay import DEFAULT_ENV

    document = yaml.safe_load(Path(runtime_env).read_text(encoding='utf-8'))
    raw = _service_env(document, environment, service)
    lab_owned = set(LabStackConfig().product_env()) | set(DEFAULT_ENV)
    env: dict[str, str] = {}
    cohort_env: dict[str, str] = {}
    dropped: dict[str, list[str]] = {'secret': [], 'endpoint': [], 'lab_owned': [], 'not_scalar': []}
    for key, entry in sorted(raw.items()):
        value = _scalar(entry)
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
        from config.refactor_modes import _COHORT_ENVS, serving_for

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
            if percent >= 100:
                serving[mode] = True
            else:
                serving[mode] = False
                if percent > 0 or digests:
                    unresolved.append(mode)
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
    }
    return overlay, report
