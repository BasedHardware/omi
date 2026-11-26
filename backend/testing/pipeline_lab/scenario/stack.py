"""``python -m testing.pipeline_lab scenario run|check|stack``: bring up (or reuse) the local stack, run each
scenario in a fresh process, write the run directory (``scenario/verdict.py``), print the timeline, the
conversations and the checks.

Peers, in order of preference:

1. ``FIRESTORE_EMULATOR_HOST`` and ``OMI_PIPELINE_LAB_REDIS`` naming loopback peers: used, never stopped.
2. The host's shared stack (``scenario stack up``; pid file ``<lab root>/scenario-stack/stack.json``): used,
   never stopped.
3. Otherwise a Firestore emulator and a ``redis-server`` on free loopback ports, started here and stopped by
   the PIDs started here (logs in ``DIR/.stack/``). When only ``OMI_PIPELINE_LAB_REDIS`` names a loopback
   Redis (CI's Redis service container), that Redis is used and only the emulator is started here.

Isolation, so many runs share one emulator and one Redis: every scenario process (each repeat too) gets
a run id, its own Firestore project ``demo-lab-<run id>`` (the emulator runs multi-project), its own Redis
database number held by a lease key in that database (``RedisSlots``; database 0 is never used), its own
blob root under its output directory, and Typesense writes off. The reset clears only that database; after
the run its database is flushed and its project's documents deleted, both only while the lease is held.
The uid stays the synthetic ``local-dev-user`` (task names hash it; a fixed uid keeps runs comparable).

Needs ``firebase`` (firebase-tools) and a Java 21 runtime for the emulator, and ``redis-server``. A Homebrew
``openjdk@21`` is put on PATH for the emulator when present.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Iterator, Optional, Sequence
import urllib.request

from testing.pipeline_lab.scenario import verdict as verdicts
from testing.pipeline_lab.scenario.spec import ScenarioError, describe_plan, load_scenario
from testing.pipeline_lab.store import StoreRefused, private_dir, private_open, private_write_text

BACKEND = Path(__file__).resolve().parents[3]
SCENARIO_DIR = Path(__file__).resolve().parent / 'scenarios'
JAVA_HOMES = ('/opt/homebrew/opt/openjdk@21/bin', '/usr/local/opt/openjdk@21/bin')
# Where ``firebase`` is looked for after PATH: the repo's pinned firebase-tools (``npm ci``), then a user-level
# npm global install. Its ``#!/usr/bin/env node`` still needs ``node`` on PATH.
FIREBASE_FALLBACKS = (
    BACKEND.parent / 'node_modules' / '.bin' / 'firebase',
    Path.home() / '.local' / 'bin' / 'firebase',
)


def firebase_binary() -> Optional[str]:
    found = shutil.which('firebase')
    if found:
        return found
    return next((str(path) for path in FIREBASE_FALLBACKS if path.is_file() and os.access(path, os.X_OK)), None)


PROJECT = 'demo-omi-local'  # the emulator's start project; runs use their own demo-lab-<run id>
RUN_PROJECT_PREFIX = 'demo-lab-'
DEFAULT_TIMEOUT = 240.0
REDIS_DATABASES = 256  # for a redis-server started here; a given one reports its own count
LEASE_GRACE = 120.0  # lease outlives the scenario timeout by this much
PEER_ENV = ('FIRESTORE_EMULATOR_HOST', 'OMI_PIPELINE_LAB_REDIS')
MODULE = 'testing.pipeline_lab.scenario.run'


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


@dataclass(frozen=True)
class Peers:
    firestore: str
    redis: str
    mode: str  # given | shared | started | started-firestore (Redis given)

    def env(self) -> dict[str, str]:
        return {'FIRESTORE_EMULATOR_HOST': self.firestore, 'OMI_PIPELINE_LAB_REDIS': self.redis}


def _private(path: Path, what: str) -> Path:
    """``store.private_dir`` with the refusal as a ScenarioError (the scenario commands' error type)."""
    try:
        return private_dir(path, what)
    except StoreRefused as refused:
        raise ScenarioError(str(refused)) from None


def _port(hostport: str) -> int:
    return int(hostport.rpartition(':')[2])


def _start_peers(work: Path, redis: Optional[str] = None) -> tuple[list[subprocess.Popen], int, int]:
    """Start redis-server (unless ``redis`` names a running one) and the Firestore emulator (multi-project) in
    new sessions; wait until both listen."""
    firebase = firebase_binary()
    missing = [] if redis or shutil.which('redis-server') else ['redis-server']
    missing += [] if firebase else ['firebase']
    for tool in missing:
        raise RuntimeError(f'{tool} not found on PATH (see the pipeline lab README, "Scenarios")')
    work = _private(work, 'stack directory')  # emulator logs and data hold what the runs wrote
    fs_port, redis_port = _free_port(), (_port(redis) if redis else _free_port())
    started: list[subprocess.Popen] = []
    try:
        with private_open(work / 'redis.log') as redis_log:
            if redis:
                redis_log.write(f'redis given: {redis}\n'.encode())
            else:
                started.append(
                    subprocess.Popen(
                        ['redis-server', '--port', str(redis_port), '--bind', '127.0.0.1', '--save', '']
                        + ['--appendonly', 'no', '--databases', str(REDIS_DATABASES)],
                        cwd=work,
                        stdout=redis_log,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                        umask=0o077,  # its files (dumps, logs) are as private as the data it holds
                    )
                )
        private_write_text(
            work / 'firebase.json',
            json.dumps(
                {
                    'emulators': {
                        'firestore': {'host': '127.0.0.1', 'port': fs_port},
                        'ui': {'enabled': False},
                        # Every run writes its own demo-lab-<run id> project.
                        'singleProjectMode': False,
                    }
                }
            ),
        )
        env = dict(os.environ)
        java = next((p for p in JAVA_HOMES if Path(p, 'java').exists()), None)
        if java:
            env['PATH'] = java + os.pathsep + env.get('PATH', '')
        with private_open(work / 'firestore.log') as emulator_log:
            started.append(
                subprocess.Popen(
                    [str(firebase), 'emulators:start', '--only', 'firestore', '--project', PROJECT],
                    cwd=work,
                    env=env,
                    stdout=emulator_log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    umask=0o077,  # firestore-debug.log and its exports hold what the runs wrote
                )
            )
        deadline = time.monotonic() + 120
        while not (_listening(fs_port) and _listening(redis_port)):
            if time.monotonic() > deadline or any(p.poll() is not None for p in started):
                raise RuntimeError(f'local stack did not start; logs in {work}')
            time.sleep(0.25)
    except BaseException:
        for process in reversed(started):
            _stop(process)
        raise
    return started, fs_port, redis_port


def given_peers() -> Optional[Peers]:
    given = {k: os.environ.get(k, '') for k in PEER_ENV}
    if all(v.startswith(('127.0.0.1:', 'localhost:')) for v in given.values()):
        return Peers(given['FIRESTORE_EMULATOR_HOST'], given['OMI_PIPELINE_LAB_REDIS'], 'given')
    return None


@contextmanager
def local_stack(work: Path) -> Iterator[Peers]:
    """Loopback peers: given in the env, else the host's shared stack, else started here (and stopped)."""
    peers = given_peers()
    if peers is None:
        shared = stack_status()
        if shared.get('running'):
            peers = Peers(shared['firestore'], shared['redis'], 'shared')
    if peers is not None:
        yield peers
        return
    redis = os.environ.get('OMI_PIPELINE_LAB_REDIS', '')
    redis = redis if redis.startswith(('127.0.0.1:', 'localhost:')) else None
    started, fs_port, redis_port = _start_peers(work / '.stack', redis=redis)
    try:
        yield Peers(
            f'127.0.0.1:{fs_port}',
            redis or f'127.0.0.1:{redis_port}',
            'started-firestore' if redis else 'started',
        )
    finally:
        for process in reversed(started):
            _stop(process)


# ---- the host's shared stack (scenario stack up|down|status) -------------------------------------


def stack_dir() -> Path:
    from testing.pipeline_lab.scenario.paths import private_lab_root

    return private_lab_root() / 'scenario-stack'


def _pid_command(pid: int) -> str:
    done = subprocess.run(['ps', '-o', 'command=', '-p', str(pid)], capture_output=True, text=True)
    return done.stdout.strip()


# What each recorded pid's command line must contain before it is trusted or signalled.
_STACK_MARKERS = {'redis': 'redis-server', 'firestore': 'emulators:start'}


def _ours(pid: int, role: str) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return _STACK_MARKERS[role] in _pid_command(pid)


def stack_status(root: Optional[Path] = None) -> dict[str, Any]:
    root = root or stack_dir()
    path = root / 'stack.json'
    if not path.exists():
        return {'running': False, 'pid_file': str(path)}
    record = json.loads(path.read_text())
    alive = {role: _ours(int(pid), role) for role, pid in (record.get('pids') or {}).items()}
    listening = _listening(_port(record['firestore'])) and _listening(_port(record['redis']))
    return {
        **record,
        'running': bool(alive) and all(alive.values()) and listening,
        'alive': alive,
        'pid_file': str(path),
    }


@contextmanager
def _stack_lock(root: Path) -> Iterator[None]:
    root = _private(root, 'shared stack directory')
    with private_open(root / 'lock', 'ab') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def stack_up(root: Optional[Path] = None) -> dict[str, Any]:
    """Start the long-lived shared stack unless it is already running. Its processes outlive this one."""
    root = root or stack_dir()
    with _stack_lock(root):
        status = stack_status(root)
        if status.get('running'):
            return {**status, 'started': False}
        if status.get('pids'):
            _stop_recorded(status)  # a half-dead earlier stack: stop what is still ours
        started, fs_port, redis_port = _start_peers(root)
        record = {
            'schema': 1,
            'started_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'firestore': f'127.0.0.1:{fs_port}',
            'redis': f'127.0.0.1:{redis_port}',
            'pids': {'redis': started[0].pid, 'firestore': started[1].pid},
            'logs': str(root),
        }
        private_write_text(root / 'stack.json', json.dumps(record, indent=1) + '\n')
        return {**stack_status(root), 'started': True}


def _stop_recorded(record: dict[str, Any], grace: float = 15.0) -> dict[str, str]:
    stopped = {}
    for role, pid in (record.get('pids') or {}).items():
        pid = int(pid)
        if not _ours(pid, role) or os.getpgid(pid) != pid:
            stopped[role] = 'not running (or not ours)'
            continue
        os.killpg(pid, signal.SIGTERM)
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline and _ours(pid, role):
            time.sleep(0.2)
        if _ours(pid, role):
            os.killpg(pid, signal.SIGKILL)
        stopped[role] = 'stopped'
    return stopped


def stack_down(root: Optional[Path] = None) -> dict[str, Any]:
    """Stop the shared stack by the PIDs in its pid file (each checked to be the process it names)."""
    root = root or stack_dir()
    with _stack_lock(root):
        status = stack_status(root)
        if not status.get('pids'):
            return {'running': False, 'stopped': {}}
        stopped = _stop_recorded(status)
        (root / 'stack.json').unlink(missing_ok=True)
        return {'running': False, 'stopped': stopped}


# ---- per-run isolation -----------------------------------------------------------------------------


def new_run_id() -> str:
    return secrets.token_hex(6)


class RedisSlots:
    """Lease one Redis database number per run on a shared ``redis-server``.

    The lease is ``SET pipeline_lab:lease <run id> NX EX ttl`` inside the database it claims, so claim and
    ownership live together and a crashed run's lease expires by itself. Database 0 is never leased: it is
    a dev stack's, and the product's own default.
    """

    def __init__(self, hostport: str):
        import redis

        host, _, port = hostport.rpartition(':')
        self._redis = redis
        self._host, self._port = host, int(port)
        self._lock = threading.Lock()
        admin = self._client(0)
        try:
            raw = admin.config_get('databases').get('databases')
            self.databases = int(raw or 16)
        except Exception:  # noqa: BLE001 - CONFIG may be disabled; redis' default count
            self.databases = 16
        finally:
            admin.close()

    def _client(self, db: int) -> Any:
        return self._redis.Redis(host=self._host, port=self._port, db=db, socket_timeout=5)

    def claim(self, run_id: str, ttl: float) -> int:
        from testing.pipeline_lab.seed.writer import REDIS_LEASE_KEY

        with self._lock:
            for db in range(1, self.databases):
                client = self._client(db)
                try:
                    if client.set(REDIS_LEASE_KEY, run_id, nx=True, ex=max(1, int(ttl))):
                        return db
                finally:
                    client.close()
        raise RuntimeError(f'no free Redis database on {self._host}:{self._port} ({self.databases - 1} leasable)')

    def release(self, db: int, run_id: str) -> bool:
        """Flush database ``db`` (lease included) only while ``run_id`` still holds it."""
        from testing.pipeline_lab.seed.writer import REDIS_LEASE_KEY

        if db == 0:
            return False
        client = self._client(db)
        try:
            with client.pipeline() as pipe:
                try:
                    pipe.watch(REDIS_LEASE_KEY)
                    holder = pipe.get(REDIS_LEASE_KEY)
                    if (holder.decode() if isinstance(holder, bytes) else holder) != run_id:
                        return False
                    pipe.multi()
                    pipe.flushdb()
                    pipe.execute()
                    return True
                except self._redis.WatchError:
                    return False
        finally:
            client.close()


def delete_project(firestore_host: str, project: str) -> None:
    """Drop every document of one run's emulator project (the emulator's own reset endpoint)."""
    if not project.startswith(RUN_PROJECT_PREFIX):
        raise ScenarioError(f'refusing to clear project {project}: not a per-run demo-lab project')
    url = f'http://{firestore_host}/emulator/v1/projects/{project}/databases/(default)/documents'
    request = urllib.request.Request(url, method='DELETE')
    with urllib.request.urlopen(request, timeout=30):  # noqa: S310 - loopback emulator only
        pass


@dataclass(frozen=True)
class Isolation:
    run_id: str
    project_id: str
    redis_db: int

    def env(self) -> dict[str, str]:
        return {
            'OMI_PIPELINE_LAB_RUN_ID': self.run_id,
            'OMI_PIPELINE_LAB_PROJECT_ID': self.project_id,
            'OMI_PIPELINE_LAB_REDIS_DB': str(self.redis_db),
            'OMI_PIPELINE_LAB_REDIS_LEASE': self.run_id,
            'OMI_PIPELINE_LAB_TYPESENSE': 'off',
        }


@contextmanager
def isolated_run(peers: Peers, slots: RedisSlots, ttl: float) -> Iterator[Isolation]:
    run_id = new_run_id()
    project = RUN_PROJECT_PREFIX + run_id
    db = slots.claim(run_id, ttl)
    try:
        yield Isolation(run_id=run_id, project_id=project, redis_db=db)
    finally:
        try:
            delete_project(peers.firestore, project)
        finally:
            slots.release(db, run_id)


def resolve(name: str) -> Path:
    """A path, or the name of a committed scenario (``scenarios/<name>.json``)."""
    path = Path(name)
    if path.exists():
        return path
    committed = SCENARIO_DIR / (name if name.endswith('.json') else name + '.json')
    if committed.exists():
        return committed
    raise ScenarioError(f'{name}: no such file or committed scenario')


@dataclass(frozen=True)
class Arm:
    """Another backend tree to run the scenarios against (``scenario compare``): the lab package is
    vendored from this checkout into ``vendor``; product code comes only from ``backend``."""

    backend: Path
    vendor: Path


def run_one(
    path: Path,
    out: Path,
    peers: dict[str, str],
    *,
    timeout: float,
    clock: str = 'frozen',
    isolation: Optional[Isolation] = None,
    arm: Optional[Arm] = None,
    stt_args: Sequence[str] = (),
) -> dict[str, Any]:
    child = {**peers, **(isolation.env() if isolation else {})}
    args = ['--file', str(path.resolve()), '--out', str(out), '--clock', clock, *stt_args]
    if arm is None:
        env = {**os.environ, **child}
        command, cwd = [sys.executable, '-m', MODULE, *args], BACKEND
    else:
        from testing.pipeline_lab import worktrees

        env = worktrees.arm_env(child)
        command, cwd = worktrees.arm_command(arm.vendor, arm.backend, MODULE, args), arm.backend
    # Its own process group, so a timeout also ends what the scenario started (a local STT worker on its own
    # interpreter, for one) instead of leaving it running without supervision.
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        umask=0o077,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _stop(process)
        process.communicate()
        return {'scenario': path.stem, 'outcome': 'error', 'error': f'timed out after {timeout:g}s'}
    private_write_text(out / 'stderr.log', stderr or '')  # a traceback can quote transcript text
    lines = (stdout or '').strip().splitlines()
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
    if 'stand_ins' in result or (result.get('audio') or {}).get('recordings'):
        from testing.pipeline_lab.scenario.standins import lines as stand_in_lines

        lines.append('  stand-ins:')
        lines.extend('    ' + line for line in stand_in_lines(result))
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


# A run's own files at the top of its output directory (run_set, scenario compare).
RUN_FILES = ('run.json', 'verdict.json', 'compare.json')


def _fresh_output(root: Path) -> None:
    """Remove an earlier run's output from ``root`` (validated owner-only) before any job starts.

    The runner appends to several artifacts (``v3_tasks.jsonl``, ``decisions.jsonl``, sink logs), so a reused
    ``--keep`` directory would mix executions: a scenario could report an earlier run's Home rows, and repeats
    would differ. Removed: every scenario directory (one holding ``scenario.json``) and the run files. Kept:
    anything else, such as the started stack's ``.stack`` directory. Symlinks are unlinked, never followed."""
    for child in sorted(root.iterdir()):
        if child.is_symlink():
            continue  # never a lab output: a scenario directory is created here, not linked
        if child.is_dir() and (child / 'scenario.json').is_file():
            shutil.rmtree(child)
        elif child.name in RUN_FILES and child.is_file():
            child.unlink()


def output_root(keep: Optional[str], prefix: str = 'plab-scenario-') -> Path:
    """The run's output directory: ``--keep DIR`` (created 0700; an existing one must already be owner-only),
    else a new directory under the private scenario lab root, never the system temp directory. Scenario output
    can hold owner audio transcripts and Home bodies (``audio_file`` recordings), so it is private either way."""
    if keep:
        root = Path(keep).expanduser().resolve()
        if any((parent / '.git').exists() for parent in (root, *root.parents)):
            raise ScenarioError('scenario output is written outside every git worktree')
        return _private(root, '--keep')
    from testing.pipeline_lab.scenario.paths import private_lab_root

    runs = _private(private_lab_root() / 'scenario-runs', 'scenario run directory')
    return Path(tempfile.mkdtemp(prefix=prefix, dir=runs))


def backend_identity(backend: Path = BACKEND) -> dict[str, Any]:
    """``backend_tree`` (git tree of ``backend/`` at HEAD), ``ref`` (branch, else the sha), ``sha``, ``dirty``."""
    from testing.pipeline_lab import worktrees

    repo = backend.parent
    try:
        sha = worktrees.git(repo, 'rev-parse', 'HEAD')
        branch = worktrees.git(repo, 'rev-parse', '--abbrev-ref', 'HEAD')
        return {
            'backend_tree': worktrees.git(repo, 'rev-parse', 'HEAD:backend'),
            'ref': sha if branch == 'HEAD' else branch,
            'sha': sha,
            'dirty': bool(worktrees.git(repo, 'status', '--porcelain', '--untracked-files=no', '--', 'backend')),
        }
    except worktrees.WorktreeError:
        return {'backend_tree': None, 'ref': None, 'sha': None, 'dirty': None}


@dataclass
class _Job:
    path: Path
    name: str
    repeat: int

    def out(self, root: Path) -> Path:
        base = root / self.name
        return base if self.repeat == 1 else base / f'repeat-{self.repeat}'


@dataclass
class RunSet:
    """What :func:`run_set` produced: the verdict, the run metadata and each job's result."""

    root: Path
    verdict: dict[str, Any]
    run: dict[str, Any]
    results: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @property
    def code(self) -> int:
        return verdicts.exit_code([row['outcome'] for row in self.verdict['scenarios']])


def run_set(
    paths: Sequence[Path],
    root: Path,
    peers: Peers,
    *,
    timeout: float,
    clock: str = 'frozen',
    jobs: int = 1,
    repeat: int = 1,
    arm: Optional[Arm] = None,
    identity: Optional[dict[str, Any]] = None,
    report=None,
    stt_args: Sequence[str] = (),
) -> RunSet:
    """Run every scenario ``repeat`` times, ``jobs`` at a time, each isolated; write ``root``'s layout."""
    if jobs < 1 or repeat < 1:
        raise ScenarioError('--jobs and --repeat must be at least 1')
    scenarios = {}
    for path in paths:
        scenario = load_scenario(path)
        if scenario.name in scenarios:
            raise ScenarioError(f'scenario {scenario.name} given twice')
        scenarios[scenario.name] = (path, scenario)
    root = _private(root, 'scenario output')
    _fresh_output(root)
    started_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
    started = time.perf_counter()
    for name, (path, _) in scenarios.items():
        # Reused with --keep: each scenario directory must be owner-only too, not only the root.
        private_write_text(_private(root / name, 'scenario output') / 'scenario.json', path.read_text())
    queued = [_Job(path, name, k) for k in range(1, repeat + 1) for name, (path, _) in scenarios.items()]
    slots = RedisSlots(peers.redis)
    runs: list[dict[str, Any]] = []
    results: dict[tuple[str, int], dict[str, Any]] = {}
    lock = threading.Lock()

    def one(job: _Job) -> None:
        out = _private(job.out(root), 'scenario output')
        with isolated_run(peers, slots, timeout + LEASE_GRACE) as isolation:
            result = run_one(
                job.path,
                out,
                peers.env(),
                timeout=timeout,
                clock=clock,
                isolation=isolation,
                arm=arm,
                stt_args=stt_args,
            )
        with lock:
            results[(job.name, job.repeat)] = result
            runs.append(
                {
                    'scenario': job.name,
                    'repeat': job.repeat,
                    'run_id': isolation.run_id,
                    'project_id': isolation.project_id,
                    'redis_db': isolation.redis_db,
                    'blob_root': str(out / 'lab' / 'stack' / 'storage'),
                }
            )
            if report is not None:
                report(result, job)

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for future in [pool.submit(one, job) for job in queued]:
            future.result()

    rows, by_name = [], {}
    for name, (_, scenario) in scenarios.items():
        repeats = [results[(name, k)] for k in range(1, repeat + 1)]
        by_name[name] = repeats
        row = verdicts.scenario_verdict(name, repeats[0], scenario)
        if repeat > 1:
            differences = verdicts.repeat_differences(
                [_Job(scenarios[name][0], name, k).out(root) for k in range(1, repeat + 1)]
            )
            outcomes = sorted({str(r.get('outcome')) for r in repeats})
            row['repeats'] = repeat
            row['differences'] = differences
            row['seconds'] = max(float(r.get('seconds') or 0) for r in repeats)
            if 'error' in outcomes:
                row['outcome'] = 'error'
            elif differences:
                row['outcome'] = 'nondeterministic'
        rows.append(row)
    verdict = verdicts.verdict(rows)
    run = {
        'schema': verdicts.SCHEMA,
        **(identity or backend_identity()),
        'started_at': started_at,
        'seconds': round(time.perf_counter() - started, 1),
        'scenarios': list(scenarios),
        'jobs': jobs,
        'repeat': repeat,
        'clock': clock,
        'stt': stt_args[1] if len(stt_args) > 1 else 'replay',
        'isolation': {
            'stack': peers.mode,
            'firestore': peers.firestore,
            'redis': peers.redis,
            'redis_databases': slots.databases,
            'typesense': 'off',
            'uid': 'local-dev-user',
            'runs': sorted(runs, key=lambda r: (r['scenario'], r['repeat'])),
        },
    }
    verdicts.write_json(root / 'run.json', run)
    verdicts.write_json(root / 'verdict.json', verdict)
    return RunSet(root=root, verdict=verdict, run=run, results=by_name)


def run_files(
    names: Sequence[str],
    *,
    keep: Optional[str],
    timeout: float,
    as_json: bool,
    clock: str = 'frozen',
    jobs: int = 1,
    repeat: int = 1,
    stt: str = 'replay',
    stt_budget_usd: Optional[float] = None,
    trace_calls: bool = False,
) -> int:
    stt_args = ['--stt', stt] + (['--stt-budget-usd', str(stt_budget_usd)] if stt_budget_usd is not None else [])
    if trace_calls:  # scenario/reach.py: each scenario writes called_files.json
        stt_args.append('--trace-calls')
    names = list(names) or sorted(path.stem for path in SCENARIO_DIR.glob('*.json'))  # default: all committed
    paths = [resolve(name) for name in names]
    for path in paths:
        load_scenario(path)  # fail fast on a malformed file, before the stack starts
    root = output_root(keep)
    started = time.perf_counter()
    printing = threading.Lock()

    def report(result: dict[str, Any], job: _Job) -> None:
        if as_json:
            return
        with printing:
            text = format_report(result)
            if repeat > 1:
                first, _, rest = text.partition('\n')
                text = f'{first}  repeat {job.repeat}/{repeat}' + ('\n' + rest if rest else '')
            print(text, flush=True)

    with local_stack(root) as peers:
        stack_seconds = round(time.perf_counter() - started, 1)
        done = run_set(
            paths, root, peers, timeout=timeout, clock=clock, jobs=jobs, repeat=repeat, report=report, stt_args=stt_args
        )
    total = round(time.perf_counter() - started, 1)
    if as_json:
        print(json.dumps(done.verdict))
    else:
        summary = ', '.join(f'{r["name"]}={r["outcome"]}' for r in done.verdict['scenarios'])
        for row in done.verdict['scenarios']:
            if row.get('differences'):
                shown = ', '.join(row['differences'][:10]) + (', ...' if len(row['differences']) > 10 else '')
                print(f'== {row["name"]}: differs between repeats at: {shown}')
        print(
            f'== {len(done.verdict["scenarios"])} scenario(s) x{repeat} in {total:.1f} s, jobs {jobs} '
            f'(stack {peers.mode}, up {stack_seconds:.1f} s): {summary}'
        )
        print(f'   output: {root}')
    return done.code


def stack_command(action: str, *, as_json: bool) -> int:
    """``scenario stack up|down|status``. ``status`` exits 0 when running, 1 when not."""
    if action == 'up':
        value = stack_up()
    elif action == 'down':
        value = stack_down()
    else:
        value = stack_status()
    if as_json:
        print(json.dumps(value))
    elif value.get('running'):
        verb = 'started' if value.get('started') else 'running'
        print(f'shared stack {verb}: firestore {value["firestore"]}, redis {value["redis"]}, pids {value["pids"]}')
        print(f'   pid file: {value["pid_file"]}')
    elif action == 'down':
        print('shared stack: ' + (', '.join(f'{k} {v}' for k, v in value['stopped'].items()) or 'not running'))
    else:
        print(f'shared stack: not running ({value.get("pid_file")})')
    return 0 if value.get('running') or action == 'down' else 1
