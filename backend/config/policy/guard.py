"""E1 env boundary guard for the 2026-10-18 policy-window incident.

Run directly with stdlib Python. Unit tests exercise the same scanner; the
checks manifest supplies identical blocking local and CI invocations.
"""

import ast
import json
from pathlib import Path
import sys

# Explicit E1b/process-control exceptions. An existing key may be read only in
# its owning files; adding a new batch env read requires an explicit decision.
DEFERRED_READS = {
    'config/batch_pipeline.py': {
        'BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED',
        'BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED',
        'BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED',
        'BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED',
        'BATCH_PIPELINE_READ_ONLY_METRICS_ENABLED',
        'BATCH_PIPELINE_SERVING_ENABLED',
        'BATCH_PIPELINE_RECOVERY_DISPATCH_BATCH_SIZE',
        'BATCH_PIPELINE_WORKER_IO_CONCURRENCY',
    },
    # #22358 landed on main while E1 was in flight; its GPU worker controls are E1b.
    'config/batch_pipeline_gpu_skip.py': {
        'BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED',
        'BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED',
    },
    'config/batch_pipeline_providers.py': {
        'BATCH_PIPELINE_CONTEXT_SECONDS',
        'BATCH_PIPELINE_DIARIZER',
        'BATCH_PIPELINE_MODEL_BATCH_SIZE',
        'BATCH_PIPELINE_PADDED_SECONDS',
        'BATCH_PIPELINE_POOL_KIND',
        'BATCH_PIPELINE_REUSE_LIVE_ENABLED',
        'BATCH_PIPELINE_UNIT_SECONDS',
        'BATCH_PIPELINE_WINDOW_SECONDS',
        'BATCH_PIPELINE_WORDS_PROVIDER',
    },
    'utils/batch_pipeline/compute_client.py': {'BATCH_PIPELINE_API_URL', 'BATCH_PIPELINE_WORKER_AUDIENCE'},
    'utils/batch_pipeline/correctness_metrics.py': {'BATCH_PIPELINE_CORRECTNESS_METRICS_ENABLED'},
    'utils/batch_pipeline/quarantine_recovery.py': {
        'BATCH_PIPELINE_RECOVERY_TASKS_QUEUE',
        'BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE',
    },
    'utils/batch_pipeline/serving.py': {'BATCH_PIPELINE_SERVING_ENABLED'},
    'utils/conversations/summary_delivery.py': {'BATCH_PIPELINE_WORKER_ENABLED'},
    'routers/batch_pipeline.py': {
        'BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE',
        'BATCH_PIPELINE_WORKER_AUDIENCE',
        'BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT',
    },
    'diarizer/batch_pipeline_runtime.py': {
        'BATCH_PIPELINE_WORKER_ENABLED',
        'BATCH_PIPELINE_WORKER_RELEASE',
        'BATCH_PIPELINE_NAMESPACE',
    },
    'diarizer/batch_pipeline_startup.py': {'BATCH_PIPELINE_MODEL_BATCH_SIZE'},
}


# E1b pending: GPU batching / worker series #22368 owns these reads, newly
# merged while E1 was in flight. Keep each key tied to its exact owning file;
# neither another key in that file nor the same key elsewhere is exempt.
E1B_PENDING_READS = {
    'config/batch_pipeline_providers.py': {
        'BATCH_PIPELINE_FLIGHT_BATCH_SECONDS': 'GPU batching / worker series #22368',
        'BATCH_PIPELINE_FLIGHT_BATCHING_ENABLED': 'GPU batching / worker series #22368',
    },
    'diarizer/batch_pipeline_flight_qualify.py': {
        'BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED': 'GPU batching / worker series #22368',
        'BATCH_PIPELINE_MODEL_BATCH_SIZE': 'GPU batching / worker series #22368',
    },
}


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
        if (
            isinstance(node, ast.Call)
            and name(node.func) in {'os.getenv', 'os.environ.get', 'os.environ.__getitem__'}
            and node.args
        ):
            key = node.args[0]
        elif isinstance(node, ast.Subscript) and name(node.value) == 'os.environ':
            key = node.slice
        if isinstance(key, ast.Constant):
            yield key.value
        elif isinstance(key, ast.Name) and key.id in constants:
            yield constants[key.id]


# Positive resolution edges: admission or a CAS owner may resolve; every other
# imported resolver/getter call is rejected, regardless of its directory.
RESOLUTION_EDGES = {
    'config/batch_pipeline.py': {'*'},  # Legacy/E1b facade; in-tree unit callers use parts.
    'config/batch_live_preview.py': {'*'},  # E2 pre-unit routing.
    'database/batch_pipeline_policy.py': {'admission_fallback', 'stage_in_transaction'},
    'database/batch_pipeline_intake.py': {'admit'},
    'database/sync_jobs.py': {'create_sync_job', '_pin_legacy_job_policy'},
    'utils/batch_pipeline/intake.py': {'accept_upload'},
    'utils/batch_pipeline/live.py': {'register_recording'},
    'utils/batch_pipeline/live_upload.py': {'registered_record_response'},
    'utils/batch_pipeline/scheduler.py': {'enqueue_in_transaction'},
    'utils/conversations/transcription_shadow.py': {'_run_shadow', '_claim_shadow_owner'},
    'utils/sync/reprocess.py': {'update', 'claim'},  # First-summary outbox CAS callbacks.
    'routers/sync.py': {'sync_local_files_v2'},
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
        if called in {'resolve_batch_policy', 'resolve_stage_policy'} and target.startswith('config.policy'):
            allowed = RESOLUTION_EDGES.get(relative, set())
            owners = [f for f in functions if f.lineno <= node.lineno <= (f.end_lineno or f.lineno)]
            owner = min(owners, key=lambda f: (f.end_lineno or f.lineno) - f.lineno) if owners else None
            if '*' not in allowed and (owner is None or owner.name not in allowed):
                out.append(f'{relative}:{node.lineno}: {called} must use the recorded policy')
    return out


def violations(root: Path):
    out = []
    backend = root / 'backend'
    for directory in ('config', 'database', 'utils', 'routers', 'diarizer', 'scripts'):
        for path in (backend / directory).rglob('*.py'):
            relative = path.relative_to(backend).as_posix()
            if relative.startswith('config/policy/'):
                continue
            source = path.read_text()
            out.extend(stage_policy_reads(source, relative))
            for key in env_reads(source):
                if isinstance(key, str) and (
                    key.startswith('BATCH_PIPELINE_') or key == 'BATCH_LIVE_STT_RETIRE_PERCENT'
                ):
                    if key not in DEFERRED_READS.get(relative, set()) and key not in E1B_PENDING_READS.get(
                        relative, {}
                    ):
                        out.append(f'{relative}: {key} must be resolved in config/policy/')
    return out


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
    errors = violations(root) + registry_violations(root)
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print('Batch policy env boundary and live-switch registry: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
