"""E1 env boundary guard for the 2026-10-18 policy-window incident.

Run directly with stdlib Python. Unit tests exercise the same scanner; the
checks manifest supplies identical blocking local and CI invocations.
"""

import ast
import json
from pathlib import Path
import sys


# The E1 boundary follows declared snapshot ownership, not the BATCH_PIPELINE_
# namespace. Worker/process keys belong to E1b and must not block other teams.
# Read declarations with AST so this check remains stdlib-only and import-pure.
def protected_env_keys():
    directory = Path(__file__).resolve().parent
    snapshot = ast.parse((directory / 'batch.py').read_text())
    switches = ast.parse((directory / 'kill_switches.py').read_text())
    owned = next(
        ast.literal_eval(node.value.args[0])
        for node in snapshot.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and any(isinstance(target, ast.Name) and target.id == 'SNAPSHOT_ENV_KEYS' for target in node.targets)
    )
    live = next(
        ast.literal_eval(node.value)
        for node in switches.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'KILL_SWITCHES' for target in node.targets)
    )
    return frozenset(owned) | frozenset(live)


def env_reads(source):
    tree = ast.parse(source)
    aliases = {'os': 'os', 'environ': 'os.environ', 'getenv': 'os.getenv'}
    constants = {}

    def name(node):
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return name(node.value) + '.' + node.attr
        return ''

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name == 'os':
                    aliases[item.asname or item.name] = 'os'
        elif isinstance(node, ast.ImportFrom) and node.module == 'os':
            for item in node.names:
                aliases[item.asname or item.name] = 'os.' + item.name
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if name(node.value) == 'os.environ':
                        aliases[target.id] = 'os.environ'
                    if isinstance(node.value, ast.Constant):
                        constants[target.id] = node.value.value
    for node in ast.walk(tree):
        key = None
        if isinstance(node, ast.Call) and name(node.func) in {'os.getenv', 'os.environ.get', 'os.environ.__getitem__'}:
            # getenv(key=...) and environ.get(key=...) read the same name as the positional form.
            key = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == 'key'), None)
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) and name(node.value) == 'os.environ':
            key = node.slice
        if isinstance(key, ast.Constant):
            yield key.value
        elif isinstance(key, ast.Name) and key.id in constants:
            yield constants[key.id]


# Positive resolution edges: admission or a CAS owner may resolve; every other
# imported resolver/getter call is rejected, regardless of its directory.
RESOLUTION_EDGES = {
    'database/batch_pipeline_shadow.py': {'pin_shadow_recovery'},  # Isolated first-writer shadow recovery CAS.
    'config/batch_pipeline.py': {'*'},  # Legacy/E1b facade; in-tree unit callers use parts.
    'config/batch_live_preview.py': {'*'},  # E2 pre-unit routing.
    'database/batch_pipeline_policy.py': {'admission_fallback', 'stage_in_transaction', 'refresh_disabled_recovery'},
    'database/batch_pipeline_intake.py': {'admit'},
    'database/sync_jobs.py': {'create_sync_job', '_pin_legacy_job_policy'},
    'utils/batch_pipeline/intake.py': {'accept_upload'},
    'utils/batch_pipeline/live.py': {'register_recording', 'reserve_recording'},
    'utils/conversations/lifecycle.py': {'_reserve_batch_live_capture'},
    'utils/batch_pipeline/live_upload.py': {'registered_record_response'},
    'utils/batch_pipeline/scheduler.py': {'enqueue_in_transaction'},
    'utils/conversations/transcription_shadow.py': {'_run_shadow', '_claim_shadow_owner'},
    # First-summary outbox CAS callbacks (moved from utils/sync/reprocess.py by C2; reprocess.py is an alias).
    'utils/enrichment/outbox.py': {'update', 'stamp_claim_policy'},
    'routers/sync.py': {'sync_local_files', 'sync_local_files_v2'},
    'routers/listen/policy.py': {'initialize_session_policy'},
}
SNAPSHOT_GETTERS = {
    'enabled_for',
    'live_record_enabled_for',
    'shared_live_enabled',
    'max_worker_attempts',
    'authoritative_labels_enabled',
    'require_live_target_enabled',
    'recover_all_admitted',
    'recovery_enabled_for',
    'projection_contention_enabled',
    'speech_empty_multilingual_enabled',
    'terminal_empty_disposition_enabled',
    'projection_timing_enabled',
    'head_priority_enabled',
    'async_projection_enabled',
}


def stage_policy_reads(source, relative):
    tree = ast.parse(source)
    aliases = {}
    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == 'config.batch_pipeline' or (node.module or '').startswith('config.policy'):
                aliases.update({item.asname or item.name: f'{node.module}.{item.name}' for item in node.names})
            elif node.module == 'config':
                aliases.update({item.asname or item.name: f'config.{item.name}' for item in node.names})
        elif isinstance(node, ast.Import):
            for item in node.names:
                if item.asname:
                    aliases[item.asname] = item.name

    def qualified(node):
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return qualified(node.value) + '.' + node.attr
        return ''

    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = qualified(node.func)
        called = target.rsplit('.', 1)[-1]
        if target.startswith('config.batch_pipeline.') and called in SNAPSHOT_GETTERS:
            if relative == 'utils/conversations/lifecycle.py' and called == 'live_record_enabled_for':
                continue  # E2's pre-unit live/listen route admission.
            out.append(f'{relative}:{node.lineno}: {called} must use the recorded policy')
            continue
        if called in {'resolve_batch_policy', 'resolve_stage_policy', 'resolve_listen_policy'} and target.startswith(
            'config.policy'
        ):
            allowed = RESOLUTION_EDGES.get(relative, set())
            owners = [f for f in functions if f.lineno <= node.lineno <= (f.end_lineno or f.lineno)]
            owner = min(owners, key=lambda f: (f.end_lineno or f.lineno) - f.lineno) if owners else None
            if '*' not in allowed and (owner is None or owner.name not in allowed):
                out.append(f'{relative}:{node.lineno}: {called} must use the recorded policy')
    return out


def scan(root: Path):
    errors = []
    warnings = set()
    protected = protected_env_keys()
    backend = root / 'backend'
    for directory in ('config', 'database', 'utils', 'routers', 'diarizer', 'scripts'):
        for path in (backend / directory).rglob('*.py'):
            relative = path.relative_to(backend).as_posix()
            if relative.startswith('config/policy/'):
                continue
            source = path.read_text()
            errors.extend(stage_policy_reads(source, relative))
            for key in env_reads(source):
                if key in protected or (
                    isinstance(key, str)
                    and (key.startswith('STT_ROUTING_') or key == 'PARAKEET_WINDOW_ALLOCATION_PERCENT')
                ):
                    errors.append(f'{relative}: {key} must be resolved in config/policy/')
                elif isinstance(key, str) and key.startswith('BATCH_PIPELINE_'):
                    warnings.add(f'{relative}: {key} is outside E1 policy ownership (E1b candidate)')
    return errors, sorted(warnings)


def violations(root: Path):
    return scan(root)[0]


def registry_violations(root: Path):
    rows = {}
    for line in (root / 'config/feature-flags.yaml').read_text().splitlines():
        if line.strip().startswith('- {'):
            row = json.loads(line.strip()[2:])
            rows[row['key']] = row
    switches = ast.parse((root / 'backend/config/policy/kill_switches.py').read_text())
    keys = next(
        ast.literal_eval(n.value)
        for n in switches.body
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'KILL_SWITCHES' for t in n.targets)
    )
    out = [
        f'{key}: live switches require registry lifecycle ops_kill'
        for key in keys
        if rows.get(key, {}).get('lifecycle') != 'ops_kill'
    ]
    if 'nested' not in rows.get('BATCH_LIVE_STT_RETIRE_PERCENT', {}).get('notes', '').lower():
        out.append('BATCH_LIVE_STT_RETIRE_PERCENT: registry must declare the nested batch cohort')
    return out


def main():
    root = Path(__file__).resolve().parents[3]
    errors, warnings = scan(root)
    errors.extend(registry_violations(root))
    for warning in warnings:
        print(f'WARNING: {warning}', file=sys.stderr)
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print('Batch/listen policy env boundary and live-switch registry: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
