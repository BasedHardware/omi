"""Invariant `staging-mirrors-prod` (contract (i)): staging differs from prod only on the allowlist.

Staging is composed from the prod overlay plus ``backend/deploy/runtime_env/staging.overlay.yaml``
(``compose_runtime_env.compose_staging``). This check composes both and fails on any Cloud Run
service, env var, secret binding or flag that differs outside ``STAGING_DIFF_ALLOWLIST``. Messages
name variables, never values. Registered by lane 1 in ``scripts/cross_service_contract.INVARIANTS``.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

INVARIANT = 'staging-mirrors-prod'

# Env names (fnmatch patterns) whose staging value may differ from prod: project and data-plane ids,
# URLs and audiences, queue names, bucket names, Redis, database, auth project, identity, vendor caps.
STAGING_DIFF_ALLOWLIST: tuple[str, ...] = (
    '*_PROJECT',
    'GOOGLE_CLOUD_PROJECT',
    '*_PROJECT_ID',
    '*_URL',
    '*_URI',
    '*_URIS',
    '*_AUDIENCE',
    '*_QUEUE',
    'BUCKET_*',
    'REDIS_*',
    'FIRESTORE_DATABASE_ID',
    'FIREBASE_AUTH_PROJECT_ID',
    'FIREBASE_SIGNER_SERVICE_ACCOUNT',
    '*_SERVICE_ACCOUNT',
    '*_INVOKER_SA',
    'OMI_DEPLOYMENT',
    '*_CEILING_USD',
    '*_DAILY_USD',
    # Deploy-time inputs prod takes from the deploy action (OAuth client ids, ladder prices, gateway URL).
    'GOOGLE_CLIENT_ID',
    'MCP_OAUTH_CLAUDE_CLIENT_*',
    'LADDER_V1_*_PRICE_ID',
    'SYNC_LEDGER_FENCE_MODE',
    # Messaging channels are prod-only (bot tokens, webhooks); staging turns them off.
    'OMI_TELEGRAM_ENABLED',
    'OMI_IMESSAGE_ENABLED',
    # Prod live-service residue (set on prod services outside runtime_env.yaml) that the code
    # reads with os.environ[...]; staging sets prod's value explicitly.
    'SUBSCRIPTION_LAUNCH_DATE',
    'SYNC_DISPATCH_MODE',
    'ACCOUNT_DELETION_DISPATCH_MODE',
    # A2 job-store shadow: staging-only (prod stays on the Firestore store).
    'BATCH_JOBSTORE_MODE',
    'JOBSTORE_*',
    # Enrichment queue route: staging at M2 (plan C3), prod stays sync_handler until M3.
    'ENRICHMENT_ROUTE',
    # Code defaults point at mail.omi.me; the staging fence requires an explicit non-prod sender
    # (staging has no RESEND_API_KEY, so email is no-send). MCP_AUTHORIZATION_SERVER_URL is *_URL.
    'LIFECYCLE_EMAIL_FROM_ADDRESS',
    'SHARE_EMAIL_FROM_ADDRESS',
)
# Cloud Run flags that may differ: network placement and replica counts.
STAGING_FLAG_ALLOWLIST: tuple[str, ...] = (
    '--network',
    '--subnet',
    '--vpc-egress',
    '--min-instances',
    '--max-instances',
)
STAGING_SECRET_PREFIX = 'staging-'


def _load_composer(root: Path) -> ModuleType:
    path = root / 'backend' / 'deploy' / 'compose_runtime_env.py'
    spec = importlib.util.spec_from_file_location('_staging_compose_runtime_env', path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _allowed(name: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def _env_values(entries: dict[str, Any]) -> dict[str, str | None]:
    """Static env value per name; ``None`` for a deploy-time input (env_var) whose prod value is not in Git."""
    out: dict[str, str | None] = {}
    for name, entry in (entries or {}).items():
        if isinstance(entry, dict) and 'value' in entry:
            out[name] = str(entry['value'])
        else:
            out[name] = None
    return out


def staging_diff(root: Path) -> list[tuple[str, str, str]]:
    """``(scope, name, problem)`` for every difference outside the allowlist. Empty means mirrored."""
    composer = _load_composer(root)
    runtime_env_dir = root / 'backend' / 'deploy' / 'runtime_env'
    base = runtime_env_dir / '_base.yaml'
    if not (runtime_env_dir / 'staging.overlay.yaml').exists():
        return [('overlay', 'staging.overlay.yaml', 'missing')]
    try:
        staging = composer.compose_staging(
            base_path=base,
            runtime_env_dir=runtime_env_dir,
            inputs={'STAGING_REDIS_HOST': '10.0.0.1'},  # placeholder private address; deploy supplies the real one
        )
    except ValueError as exc:
        return [('compose', 'staging', line.strip()) for line in str(exc).splitlines()[1:] or [str(exc)]]
    prod = composer.compose_environment('prod', base_path=base, runtime_env_dir=runtime_env_dir)

    problems: list[tuple[str, str, str]] = []
    prod_services = prod.get('cloud_run', {}).get('services', {})
    staging_services = staging.get('cloud_run', {}).get('services', {})
    for service in sorted(set(prod_services) ^ set(staging_services)):
        problems.append((service, 'service', 'present in only one of prod/staging'))

    for service in sorted(set(prod_services) & set(staging_services)):
        p_cfg, s_cfg = prod_services[service], staging_services[service]
        p_env, s_env = _env_values(p_cfg.get('env', {})), _env_values(s_cfg.get('env', {}))
        p_mounts = p_cfg.get('secrets', {}) or {}
        s_mounts = s_cfg.get('secrets', {}) or {}
        for name in sorted(set(p_env) | set(s_env)):
            if name in s_mounts or name in p_mounts:
                continue  # judged as a secret binding below
            if name in p_env and name in s_env and p_env[name] == s_env[name]:
                continue
            if _allowed(name, STAGING_DIFF_ALLOWLIST):
                continue
            if name not in s_env:
                problems.append((service, name, 'env missing in staging'))
            elif name not in p_env:
                problems.append((service, name, 'env only in staging'))
            else:
                problems.append((service, name, 'env value differs from prod'))
        for name in sorted(set(s_mounts)):
            ref = str((s_mounts[name] or {}).get('secret', ''))
            if not ref.startswith(STAGING_SECRET_PREFIX):
                problems.append((service, name, 'staging secret binding is not a staging-* secret'))
        p_flags = {str(k): v for k, v in (p_cfg.get('flags') or {}).items()}
        s_flags = {str(k): v for k, v in (s_cfg.get('flags') or {}).items()}
        for flag in sorted(set(p_flags) | set(s_flags)):
            if p_flags.get(flag) != s_flags.get(flag) and not _allowed(flag, STAGING_FLAG_ALLOWLIST):
                problems.append((service, flag, 'flag differs from prod'))
        if sorted(p_cfg.get('forbidden_env') or []) != sorted(s_cfg.get('forbidden_env') or []):
            problems.append((service, 'forbidden_env', 'differs from prod'))
    return problems


def check_staging_mirrors_prod(ctx: Any) -> list[Any]:
    """Cross-service-contract entry point: one Violation per non-allowlisted staging/prod difference."""
    from scripts.cross_service_contract import Violation

    root = Path(getattr(ctx.source, 'root'))
    return [Violation(INVARIANT, 'staging', f'{scope}/{name}', problem) for scope, name, problem in staging_diff(root)]


def summary(problems: list[tuple[str, str, str]]) -> list[str]:
    """Printable lines: problem kinds with counts and the affected env/flag names (never values)."""
    by_kind: dict[str, list[str]] = {}
    for scope, name, problem in problems:
        by_kind.setdefault(problem, []).append(f'{scope}/{name}')
    lines = [
        f'[{INVARIANT}] {kind}: {len(where)} ({", ".join(sorted(where))})' for kind, where in sorted(by_kind.items())
    ]
    lines.append(f'{len(problems)} difference(s) outside STAGING_DIFF_ALLOWLIST')
    return lines


if __name__ == '__main__':
    found = staging_diff(Path(__file__).resolve().parents[3])
    sys.stdout.write('\n'.join(summary(found)) + '\n')
    raise SystemExit(1 if found else 0)
