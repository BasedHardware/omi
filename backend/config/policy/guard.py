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


STAGE_PATHS = {
    'utils/batch_pipeline/projection.py',
    'utils/batch_pipeline/projection_followup.py',
    'utils/batch_pipeline/scheduler.py',
    'utils/batch_pipeline/quarantine_recovery.py',
    'database/batch_pipeline_projection.py',
    'database/batch_pipeline_projection_session.py',
    'routers/batch_pipeline.py',
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
    if relative not in STAGE_PATHS:
        return []
    tree = ast.parse(source)
    aliases = {}
    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in {'config.batch_pipeline', 'config.policy'}:
            aliases.update({item.asname or item.name: item.name for item in node.names})
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = (
            aliases.get(node.func.id, node.func.id)
            if isinstance(node.func, ast.Name)
            else (node.func.attr if isinstance(node.func, ast.Attribute) else '')
        )
        if called == 'resolve_batch_policy' and relative == 'utils/batch_pipeline/scheduler.py':
            if any(
                f.name == 'enqueue_in_transaction' and f.lineno <= node.lineno <= (f.end_lineno or f.lineno)
                for f in functions
            ):
                continue  # Standalone queue admission is an explicit resolver edge.
        if called in SNAPSHOT_GETTERS or called == 'resolve_batch_policy':
            out.append(f'{relative}:{node.lineno}: {called} must use the recorded policy')
    return out


def violations(root: Path):
    out = []
    backend = root / 'backend'
    for directory in ('config', 'database', 'utils', 'routers', 'diarizer'):
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
                    if key not in DEFERRED_READS.get(relative, set()):
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
