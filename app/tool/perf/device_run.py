#!/usr/bin/env python3
"""Run one owned, bounded physical-device benchmark, including Aqua signing."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import select
import shlex
import signal
import subprocess
import sys
import threading
import time

APP = Path(__file__).resolve().parents[2]
REPO = APP.parent
ENV_KEYS = ('PATH', 'OMI_WORKSPACE_ROOT', 'OMI_ROLLOUT_BIN', 'OMI_HEAVY_BIN',
            'ANDROID_HOME', 'ANDROID_SDK_ROOT', 'JAVA_HOME', 'FLUTTER_ROOT', 'AGENT_HEARTBEAT_KEY')


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')


def choose_ios(devices):
    candidates = [d['id'] for d in devices if d.get('targetPlatform') == 'ios'
                  and d.get('emulator') is False and d.get('isSupported') is not False]
    if len(candidates) != 1:
        raise ValueError(f'expected exactly one supported physical iPhone; found {len(candidates)}; pass --device')
    return candidates[0]


def detect(platform):
    if platform == 'ios':
        result = subprocess.run(['flutter', 'devices', '--machine'], check=True,
                                capture_output=True, text=True, timeout=120)
        return choose_ios(json.loads(result.stdout))
    result = subprocess.run(['adb', 'devices'], check=True, capture_output=True, text=True, timeout=15)
    candidates = []
    for line in result.stdout.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 2 or fields[1] != 'device':
            continue
        qemu = subprocess.run(['adb', '-s', fields[0], 'shell', 'getprop', 'ro.kernel.qemu'],
                              check=True, capture_output=True, text=True, timeout=15)
        if qemu.stdout.strip() != '1':
            candidates.append(fields[0])
    if len(candidates) != 1:
        raise ValueError(f'expected exactly one authorized physical Android device; found {len(candidates)}; pass --device')
    return candidates[0]


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def interrupted(signum, frame):
    raise KeyboardInterrupt


def process_start(pid):
    return subprocess.run(['ps', '-p', str(pid), '-o', 'lstart='], check=True,
                          capture_output=True, text=True, timeout=5,
                          env={**os.environ, 'LC_ALL': 'C', 'TZ': 'UTC'}).stdout.strip()


def worker(spec_path):
    spec = json.loads(Path(spec_path).read_text())
    out = Path(spec['out'])
    try:
        (out / 'worker-claim').mkdir()
    except FileExistsError:
        # A timed-out AppleEvent may arrive after the command-file fallback.
        # Only the first worker may write PID/result files or touch the device.
        return 0
    (out / 'worker-pid.txt').write_text(str(os.getpid()) + '\n')
    os.environ.update(spec['env'])
    signal.signal(signal.SIGTERM, interrupted)
    result = 1
    process = None
    lock = None
    completed = threading.Event()
    try:
        os.kill(spec['parent_pid'], 0)
        if (time.time() > spec['launch_expires_at'] or
                process_start(spec['parent_pid']) != spec['parent_start']):
            raise ValueError('expired launch or original caller no longer owns this process ID')
        if spec['platform'] == 'ios' and sys.platform == 'darwin':
            session = subprocess.run(['launchctl', 'managername'], check=True, capture_output=True,
                                     text=True, timeout=5).stdout.strip()
            (out / 'aqua-session.json').write_text(json.dumps({
                'session': session, 'terminal': os.environ.get('TERM_PROGRAM')}) + '\n')
            if session != 'Aqua':
                raise ValueError('iOS signing requires the approved Aqua session')
        if sys.platform == 'darwin' and spec['parent_pid'] != os.getpid():
            # An Aqua worker must not outlive a killed headless caller.
            queue = select.kqueue()
            queue.control([select.kevent(spec['parent_pid'], filter=select.KQ_FILTER_PROC,
                           flags=select.KQ_EV_ADD | select.KQ_EV_ENABLE,
                           fflags=select.KQ_NOTE_EXIT)], 0, 0)
            def parent_exit():
                try:
                    if queue.control(None, 1, 120 * 60) and not completed.is_set():
                        os.kill(os.getpid(), signal.SIGTERM)
                finally:
                    queue.close()
            threading.Thread(target=parent_exit, daemon=True).start()
        lock_path = APP / '.dart_tool/heavy-profile.lock'
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock = lock_path.open('a')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with (out / 'runner.log').open('w') as log:
            device = spec['device'] or detect(spec['platform'])
            command = [spec['heavy'], 'run', '--', 'nice', '-n', '19', 'bash',
                       str(APP / 'tool/perf_sim_profile.sh'), '--platform', spec['platform'],
                       '--device', device, '--runs', str(spec['runs']), '--out', str(out)]
            if spec['timeline']:
                command.append('--timeline')
            log.write('COMMAND ' + shlex.join(command) + '\n')
            log.flush()
            process = subprocess.Popen(command, cwd=REPO, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            (out / 'child-pgid.txt').write_text(str(process.pid) + '\n')
            result = process.wait(timeout=110 * 60)
            if (out / 'summary.json').is_file():
                compare = [sys.executable, '-I', str(APP / 'tool/perf/compare.py'), str(out),
                           '--artifact-root', spec['artifact_root']]
                if spec['baseline']:
                    compare += ['--baseline', spec['baseline']]
                if spec['accept_baseline']:
                    compare.append('--accept-baseline')
                compared = subprocess.run(compare, cwd=REPO, stdout=log, stderr=subprocess.STDOUT, timeout=60)
                result = result or compared.returncode
    except (Exception, KeyboardInterrupt) as error:
        with (out / 'runner.log').open('a') as log:
            log.write(f'RUNNER_ERROR {type(error).__name__}: {error}\n')
        result = 130 if isinstance(error, KeyboardInterrupt) else 1
    finally:
        if process is not None:
            stop(process)
        if lock is not None:
            lock.close()
        completed.set()
        result = 128 - result if result < 0 else result
        (out / 'runner-done.txt').write_text(f'PERF_DONE exit={result}\n')
    return result


def wait(waiter, path, done, fail, timeout):
    return subprocess.run([str(waiter), str(path), done, fail, timeout], check=False).returncode


def run(args):
    artifact_root = Path(args.artifact_root).expanduser().resolve()
    out = Path(args.out).expanduser().resolve() if args.out else artifact_root / stamp()
    workspace = Path(os.environ.get('OMI_WORKSPACE_ROOT', str(Path.home() / 'workspace/omi')))
    heavy = Path(os.environ.get('OMI_HEAVY_BIN', str(workspace / 'bin/omi-heavy')))
    rollout = Path(os.environ.get('OMI_ROLLOUT_BIN', str(workspace / 'infra/rollout/bin')))
    waiter = Path(os.environ.get('OMI_PERF_WAITER', str(rollout / 'wait_for.sh')))
    spec = dict(out=str(out), artifact_root=str(artifact_root), heavy=str(heavy),
                parent_pid=os.getpid(),
                parent_start=process_start(os.getpid()), launch_expires_at=time.time() + 300,
                device=args.device, platform=args.platform, runs=args.runs, timeline=args.timeline,
                aqua_app=args.aqua_app,
                baseline=str(Path(args.baseline).expanduser().resolve()) if args.baseline else None,
                accept_baseline=args.accept_baseline,
                env={key: os.environ[key] for key in ENV_KEYS if key in os.environ})
    if args.dry_run:
        print(json.dumps({key: value for key, value in spec.items() if key != 'env'}, indent=2))
        return 0
    if args.runs < 3 and not args.timeline:
        raise ValueError('baseline requires at least three runs')
    if not heavy.is_file() or not os.access(heavy, os.X_OK):
        raise ValueError('set OMI_HEAVY_BIN to the workspace omi-heavy executable')
    if out.exists() and any(out.iterdir()):
        raise ValueError('output directory must be new or empty; prior evidence is never overwritten')
    out.mkdir(parents=True, exist_ok=True)
    artifact_root.mkdir(parents=True, exist_ok=True)
    spec_path = out / 'launch.json'
    spec_path.write_text(json.dumps(spec, indent=2) + '\n')
    spec_path.chmod(0o600)
    print(f'Artifacts: {out}', flush=True)
    if args.platform != 'ios' or sys.platform != 'darwin':
        return worker(spec_path)
    session = subprocess.run(['launchctl', 'managername'], check=True, capture_output=True,
                             text=True, timeout=5).stdout.strip()
    terminal_program = {'iTerm': 'iTerm.app', 'Terminal': 'Apple_Terminal'}[args.aqua_app]
    if session == 'Aqua' and os.environ.get('TERM_PROGRAM') == terminal_program:
        return worker(spec_path)
    if not waiter.is_file() or not os.access(waiter, os.X_OK):
        raise ValueError('Aqua launch needs canonical wait_for.sh: set OMI_PERF_WAITER, or run directly in the approved GUI terminal')
    command = shlex.join([sys.executable, '-I', str(Path(__file__).resolve()), '--worker', str(spec_path)])
    try:
        try:
            launch = ('tell application "iTerm" to create window with default profile command (item 1 of argv)'
                      if args.aqua_app == 'iTerm' else
                      'tell application "Terminal" to do script (item 1 of argv)')
            subprocess.run(['osascript', '-e', 'on run argv', '-e',
                            launch, '-e', 'end run',
                            command if args.aqua_app == 'iTerm' else 'exec ' + command], check=True, timeout=30)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            if not (out / 'worker-pid.txt').is_file():
                raise RuntimeError(f'{args.aqua_app} did not acknowledge launch; check Automation permission. '
                                   'Use --aqua-app Terminal only when that fallback is approved.')
        launched = wait(waiter, out / 'worker-pid.txt', '^[0-9]+$', 'LAUNCH_FAILED', '90s')
        if launched:
            raise RuntimeError(f'{args.aqua_app} worker did not acknowledge launch; inspect the approved GUI terminal')
        result = wait(waiter, out / 'runner-done.txt', 'PERF_DONE exit=0', 'PERF_DONE exit=[1-9]', '2h')
        if result in (0, 1):
            return int((out / 'runner-done.txt').read_text().split('=')[1])
        raise RuntimeError(f'device worker wait ended with {result}; cancelling owned worker')
    finally:
        pid_path = out / 'worker-pid.txt'
        if pid_path.is_file() and not (out / 'runner-done.txt').is_file():
            try:
                os.kill(int(pid_path.read_text()), signal.SIGTERM)
            except ProcessLookupError:
                pass
            collected = wait(waiter, out / 'runner-done.txt', 'PERF_DONE exit=[0-9]+', 'IMPOSSIBLE_FAILURE', '90s')
            if collected:
                raise RuntimeError(f'BLOCKER: owned worker did not acknowledge cleanup; collect {out}')


def main():
    signal.signal(signal.SIGTERM, interrupted)
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        return worker(sys.argv[2])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', help='approved physical device; defaults to the sole supported connected device')
    parser.add_argument('--platform', choices=('ios', 'android'), default='ios' if sys.platform == 'darwin' else 'android')
    parser.add_argument('--aqua-app', choices=('iTerm', 'Terminal'), default='Terminal',
                        help='approved GUI terminal; Terminal may need Local Network permission or slow USB fallback')
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--out')
    default_root = os.environ.get('OMI_PERF_ARTIFACT_ROOT')
    if not default_root:
        scratch_roots = [os.environ.get('SCRATCH_ROOT'), '/Volumes/Ephemeral/scratch', '/Volumes/scratch']
        default_root = next((str(Path(root) / 'mobile-heavy-profile') for root in scratch_roots
                             if root and Path(root).is_dir()), None)
    parser.add_argument('--artifact-root', default=default_root)
    parser.add_argument('--baseline', help='accepted baseline directory; otherwise use artifact root last-accepted pointer')
    parser.add_argument('--accept-baseline', action='store_true', help='publish a pointer only after profile variance passes')
    parser.add_argument('--timeline', action='store_true', help='attribution diagnostic; never baseline acceptance')
    parser.add_argument('--dry-run', action='store_true', help='show plan without launching, building or installing')
    try:
        args = parser.parse_args()
        if not args.artifact_root:
            raise ValueError('set --artifact-root or OMI_PERF_ARTIFACT_ROOT to mounted scratch storage')
        return run(args)
    except KeyboardInterrupt:
        return 130
    except (ValueError, RuntimeError, subprocess.SubprocessError, OSError) as error:
        parser.exit(2, f'{error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
