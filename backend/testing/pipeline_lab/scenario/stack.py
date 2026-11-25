"""``python -m testing.pipeline_lab scenario run|check``: bring up the local stack, run each scenario in a
fresh process, print the timeline, the conversations and the checks.

The stack is the smoke's (``stack/run_chain_smoke.sh``): a Firestore emulator (project ``demo-omi-local``)
and a ``redis-server`` on free loopback ports, started here and stopped by the PIDs started here. When
``FIRESTORE_EMULATOR_HOST`` and ``OMI_PIPELINE_LAB_REDIS`` already name loopback peers, those are used and
nothing is started. Scenarios run one at a time; each resets the lab uid first.

Needs ``firebase`` (firebase-tools) and a Java 21 runtime for the emulator, and ``redis-server``. A Homebrew
``openjdk@21`` is put on PATH for the emulator when present.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterator, Optional, Sequence

from testing.pipeline_lab.scenario.checks import OUTCOMES
from testing.pipeline_lab.scenario.spec import ScenarioError, describe_plan, load_scenario

BACKEND = Path(__file__).resolve().parents[3]
SCENARIO_DIR = Path(__file__).resolve().parent / 'scenarios'
JAVA_HOMES = ('/opt/homebrew/opt/openjdk@21/bin', '/usr/local/opt/openjdk@21/bin')
PROJECT = 'demo-omi-local'
DEFAULT_TIMEOUT = 240.0


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def _listening(port: int) -> bool:
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5):
            return True
    except OSError:
        return False


def _stop(process: subprocess.Popen, *, grace: float = 15.0) -> None:
    """Stop a process group this module started (never anything else)."""
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


@contextmanager
def local_stack(work: Path) -> Iterator[dict[str, str]]:
    """``{FIRESTORE_EMULATOR_HOST, OMI_PIPELINE_LAB_REDIS}`` for loopback peers, started here if not given."""
    given = {k: os.environ.get(k, '') for k in ('FIRESTORE_EMULATOR_HOST', 'OMI_PIPELINE_LAB_REDIS')}
    if all(v.startswith(('127.0.0.1:', 'localhost:')) for v in given.values()):
        yield given
        return
    for tool in ('redis-server', 'firebase'):
        if shutil.which(tool) is None:
            raise RuntimeError(f'{tool} not found on PATH (see the pipeline lab README, "Scenarios")')
    fs_port, redis_port = _free_port(), _free_port()
    started: list[subprocess.Popen] = []
    logs = []
    try:
        redis_log = open(work / 'redis.log', 'wb')
        logs.append(redis_log)
        started.append(
            subprocess.Popen(
                ['redis-server', '--port', str(redis_port), '--bind', '127.0.0.1', '--save', '', '--appendonly', 'no'],
                cwd=work,
                stdout=redis_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        )
        (work / 'firebase.json').write_text(
            json.dumps(
                {
                    'emulators': {
                        'firestore': {'host': '127.0.0.1', 'port': fs_port},
                        'ui': {'enabled': False},
                        'singleProjectMode': True,
                    }
                }
            )
        )
        env = dict(os.environ)
        java = next((p for p in JAVA_HOMES if Path(p, 'java').exists()), None)
        if java:
            env['PATH'] = java + os.pathsep + env.get('PATH', '')
        emulator_log = open(work / 'firestore.log', 'wb')
        logs.append(emulator_log)
        started.append(
            subprocess.Popen(
                ['firebase', 'emulators:start', '--only', 'firestore', '--project', PROJECT],
                cwd=work,
                env=env,
                stdout=emulator_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        )
        deadline = time.monotonic() + 120
        while not (_listening(fs_port) and _listening(redis_port)):
            if time.monotonic() > deadline or any(p.poll() is not None for p in started):
                raise RuntimeError(f'local stack did not start; logs in {work}')
            time.sleep(0.25)
        yield {'FIRESTORE_EMULATOR_HOST': f'127.0.0.1:{fs_port}', 'OMI_PIPELINE_LAB_REDIS': f'127.0.0.1:{redis_port}'}
    finally:
        for process in reversed(started):
            _stop(process)
        for handle in logs:
            handle.close()


def resolve(name: str) -> Path:
    """A path, or the name of a committed scenario (``scenarios/<name>.json``)."""
    path = Path(name)
    if path.exists():
        return path
    committed = SCENARIO_DIR / (name if name.endswith('.json') else name + '.json')
    if committed.exists():
        return committed
    raise ScenarioError(f'{name}: no such file or committed scenario')


def run_one(
    path: Path,
    out: Path,
    peers: dict[str, str],
    *,
    timeout: float,
    clock: str = 'frozen',
    stt_args: Sequence[str] = (),
) -> dict[str, Any]:
    env = {**os.environ, **peers}
    command = [sys.executable, '-m', 'testing.pipeline_lab.scenario.run', '--file', str(path), '--out', str(out)]
    command += ['--clock', clock, *stt_args]
    try:
        done = subprocess.run(command, cwd=BACKEND, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {'scenario': path.stem, 'outcome': 'error', 'error': f'timed out after {timeout:g}s'}
    (out / 'stderr.log').write_text(done.stderr or '')
    lines = (done.stdout or '').strip().splitlines()
    try:
        return json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        return {'scenario': path.stem, 'outcome': 'error', 'error': 'no result', 'log': str(out / 'stderr.log')}


# ---- text report ----------------------------------------------------------------------------------

_SKIP_DETAIL = {'t', 'kind', 'ref', 'outcome', 'error', 'where', 'seconds'}


def _detail(row: dict[str, Any]) -> str:
    return ' '.join(f'{k}={v}' for k, v in row.items() if k not in _SKIP_DETAIL and v not in (None, '', {}, []))


def _table(conversations: Sequence[dict[str, Any]], indent: str = '  ') -> list[str]:
    if not conversations:
        return [indent + '(no v3 conversations)']
    out = [
        indent + f'{"conv":<9}{"recordings":<14}{"words":>6}  {"visible":<8}{"hidden_reason":<22}{"manual_end":<11}kind'
    ]
    for c in conversations:
        out.append(
            indent
            + f'{c["handle"]:<9}{"+".join(c["recordings"]) or "-":<14}{c["words"]:>6}  '
            + f'{"yes" if c["visible"] else "no":<8}{str(c["hidden_reason"] or "-"):<22}'
            + f'{"yes" if c["manual_end"] else "no":<11}{c.get("kind") or "-"}'
            + ('  (deleted)' if c.get('deleted') else '')
        )
    return out


def format_report(result: dict[str, Any]) -> str:
    lines = [f'== {result.get("scenario")}: {str(result.get("outcome")).upper()}  ({result.get("seconds", 0):.1f} s)']
    if result.get('error'):
        lines.append(f'  error: {result["error"]}' + (f'  (log: {result["log"]})' if result.get('log') else ''))
    failure = result.get('expected_failure')
    if failure:
        lines.append(f'  expected failure: {failure.get("reason")}')
    if result.get('timeline'):
        lines.append('  timeline (seconds from T0):')
        for row in result['timeline']:
            mark = f'{row["kind"]:<13} {row["ref"]:<10} {row["outcome"]:<12}'
            if row.get('error'):
                mark += f' {row["error"]} at {row.get("where")}'
            lines.append(f'    +{row["t"]:>8.1f}  {mark} {_detail(row)}'.rstrip())
    for key, seen in sorted((result.get('checkpoints') or {}).items()):
        lines.append(f'  conversations at +{seen["t"]:g}s:')
        lines.extend(_table(seen['conversations'], '    '))
    if 'conversations' in result:
        lines.append('  conversations at the end:')
        lines.extend(_table(result['conversations'], '    '))
    if result.get('recordings'):
        lines.append(
            '  recordings: '
            + ', '.join(f'{r["label"]}({r["lane"]}, {r["words"]}w, claims={r["claims"]})' for r in result['recordings'])
        )
    if result.get('fast_finish'):
        lines.append('  fast finish: ' + ', '.join(f'{k}={v}' for k, v in result['fast_finish'].items()))
    for row in (result.get('audio') or {}).get('recordings', []):
        lines.append(
            f'  audio {row["label"]}: {row["audio_file"]} {row["audio_seconds"]:g}s, {row["source"]} cassette '
            f'{row["cassette"]} ({row["provider"]}/{row["model"]}, {row["origin"]}), {row["words"]} words, '
            f'driver {row["driver"]}'
        )
        lines.append('    product: ' + ', '.join(row['product']))
        lines.append('    stand-in: ' + ', '.join(row['simulated']))
    if result.get('stand_ins'):
        lines.append('  stand-ins used: ' + ', '.join(f'{k}x{v}' for k, v in result['stand_ins'].items()))
    if result.get('finish_target') is not None or result.get('checks'):
        lines.append(f'  finish target: {result.get("finish_target")}')
    for check in result.get('checks') or []:
        lines.append(f'  {"PASS" if check["ok"] else "FAIL"}  {check["check"]}  -- {check["detail"]}')
    for warning in result.get('warnings') or []:
        lines.append(f'  warning: {warning}')
    return '\n'.join(lines)


# ---- command --------------------------------------------------------------------------------------


def check_files(names: Sequence[str], *, as_json: bool) -> int:
    """Validate scenario files and print their planned timelines (no stack)."""
    out = []
    for name in names:
        scenario = load_scenario(resolve(name))
        out.append({'scenario': scenario.name, 'plan': describe_plan(scenario)})
    if as_json:
        print(json.dumps(out))
    else:
        for row in out:
            print(f'== {row["scenario"]}: valid')
            print('\n'.join('  ' + line for line in row['plan']))
    return 0


def run_files(
    names: Sequence[str],
    *,
    keep: Optional[str],
    timeout: float,
    as_json: bool,
    clock: str = 'frozen',
    stt: str = 'replay',
    stt_budget_usd: Optional[float] = None,
) -> int:
    stt_args = ['--stt', stt] + (['--stt-budget-usd', str(stt_budget_usd)] if stt_budget_usd is not None else [])
    paths = [resolve(name) for name in names]
    for path in paths:
        load_scenario(path)  # fail fast on a malformed file, before the stack starts
    root = Path(keep).expanduser().resolve() if keep else Path(tempfile.mkdtemp(prefix='plab-scenario-'))
    if any((parent / '.git').exists() for parent in (root, *root.parents)):
        raise ScenarioError('scenario output is written outside every git worktree')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    started = time.perf_counter()
    results = []
    with local_stack(root) as peers:
        stack_seconds = round(time.perf_counter() - started, 1)
        for path in paths:
            out = root / path.stem
            out.mkdir(parents=True, exist_ok=True, mode=0o700)
            result = run_one(path, out, peers, timeout=timeout, clock=clock, stt_args=stt_args)
            results.append(result)
            if not as_json:
                print(format_report(result), flush=True)
    total = round(time.perf_counter() - started, 1)
    code = max((OUTCOMES.get(r.get('outcome', 'error'), 2) for r in results), default=0)
    if as_json:
        print(json.dumps({'results': results, 'root': str(root), 'seconds': total, 'stack_seconds': stack_seconds}))
    else:
        summary = ', '.join(f'{r.get("scenario")}={r.get("outcome")}' for r in results)
        print(f'== {len(results)} scenario(s) in {total:.1f} s (stack up {stack_seconds:.1f} s): {summary}')
        print(f'   output: {root}')
    return code
