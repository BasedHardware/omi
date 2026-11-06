import os
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts import check_route_policy_baseline as route_policy

ROOT = Path(__file__).resolve().parents[3]
OPENAPI_RUNNER = ROOT / 'backend/scripts/openapi_runner.sh'


def _bash_path(path: Path) -> str:
    if os.name != 'nt':
        return path.as_posix()
    return subprocess.check_output(
        route_policy.bash_command('-lc', 'cygpath -u "$1"', 'bash', path),
        text=True,
    ).strip()


def test_windows_bash_command_uses_active_git_installation(tmp_path):
    git_root = tmp_path / 'Git'
    git_exec_path = git_root / 'mingw64/libexec/git-core'
    git_exec_path.mkdir(parents=True)
    git_bash = git_root / 'bin/bash.exe'
    git_bash.parent.mkdir()
    git_bash.touch()

    command = route_policy.bash_command(
        'scripts/probe.sh',
        'argument',
        platform_name='nt',
        git_exec_path=git_exec_path,
    )

    assert command == [str(git_bash), 'scripts/probe.sh', 'argument']


def test_windows_bash_command_ignores_git_exec_path_override(tmp_path, monkeypatch):
    git_root = tmp_path / 'Git'
    git_exec_path = git_root / 'mingw64/libexec/git-core'
    git_exec_path.mkdir(parents=True)
    git_bash = git_root / 'bin/bash.exe'
    git_bash.parent.mkdir()
    git_bash.touch()
    monkeypatch.setenv('GIT_EXEC_PATH', str(tmp_path / 'untrusted'))

    def fake_check_output(command, **kwargs):
        assert command == ['git', '--exec-path']
        assert 'GIT_EXEC_PATH' not in kwargs['env']
        return str(git_exec_path)

    monkeypatch.setattr(route_policy.subprocess, 'check_output', fake_check_output)

    assert route_policy.bash_command('probe.sh', platform_name='nt') == [str(git_bash), 'probe.sh']


def test_git_bash_search_does_not_escape_git_installation(tmp_path):
    git_exec_path = tmp_path / 'nested/Git/mingw64/libexec/git-core'
    git_exec_path.mkdir(parents=True)
    unrelated_bash = tmp_path / 'bin/bash.exe'
    unrelated_bash.parent.mkdir()
    unrelated_bash.touch()

    with pytest.raises(FileNotFoundError):
        route_policy.find_git_bash(git_exec_path)


def test_openapi_runner_accepts_windows_venv_layout(tmp_path):
    venv_dir = tmp_path / 'venv'
    venv_python = venv_dir / 'Scripts/python.exe'
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text(
        '#!/usr/bin/env bash\n'
        'case "${1:-}" in\n'
        "  -c) printf '3.11\\n' ;;\n"
        '  -) cat >/dev/null ;;\n'
        "  *) printf 'ok' > \"$2\" ;;\n"
        'esac\n',
        encoding='utf-8',
    )
    venv_python.chmod(0o755)

    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    fake_uv = fake_bin / 'uv'
    fake_uv.write_text('#!/usr/bin/env bash\nexit 0\n', encoding='utf-8')
    fake_uv.chmod(0o755)

    marker = tmp_path / 'probe-ran.txt'
    env = {
        **os.environ,
        'OPENAPI_RUNNER_VENV': _bash_path(venv_dir),
        'PATH': (
            f'{_bash_path(fake_bin)}:/usr/bin:/bin'
            if os.name == 'nt'
            else f'{fake_bin}{os.pathsep}{os.environ["PATH"]}'
        ),
    }

    result = subprocess.run(
        route_policy.bash_command(OPENAPI_RUNNER, 'probe.py', _bash_path(marker)),
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert marker.read_text(encoding='utf-8') == 'ok'


def test_openapi_runner_does_not_delete_mismatched_custom_venv(tmp_path):
    venv_dir = tmp_path / 'venv'
    venv_python = venv_dir / 'Scripts/python.exe'
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("#!/usr/bin/env bash\nprintf '3.10\\n'\n", encoding='utf-8')
    venv_python.chmod(0o755)
    sentinel = venv_dir / 'keep.txt'
    sentinel.write_text('keep', encoding='utf-8')

    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    fake_uv = fake_bin / 'uv'
    fake_uv.write_text('#!/usr/bin/env bash\nexit 0\n', encoding='utf-8')
    fake_uv.chmod(0o755)
    env = {
        **os.environ,
        'OPENAPI_RUNNER_VENV': _bash_path(venv_dir),
        'PATH': (
            f'{_bash_path(fake_bin)}:/usr/bin:/bin'
            if os.name == 'nt'
            else f'{fake_bin}{os.pathsep}{os.environ["PATH"]}'
        ),
    }

    result = subprocess.run(
        route_policy.bash_command(OPENAPI_RUNNER, 'probe.py'),
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert 'custom OpenAPI runner venv' in result.stderr
    assert sentinel.read_text(encoding='utf-8') == 'keep'


@pytest.mark.parametrize(
    ('override', 'created_minor', 'expected_status'),
    [(None, '3.11', 0), ('/explicit/python3.11', '3.11', 0), (None, '3.14', 1), ('python3.14', '3.14', 1)],
)
def test_openapi_runner_creates_pinned_venv_via_uv(tmp_path, override, created_minor, expected_status):
    backend = tmp_path / 'backend'
    scripts = backend / 'scripts'
    scripts.mkdir(parents=True)
    runner = scripts / 'openapi_runner.sh'
    shutil.copyfile(OPENAPI_RUNNER, runner)
    (backend / '.python-version').write_text('3.11.15\n', encoding='utf-8')
    (backend / 'openapi-requirements.txt').touch()

    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    # Keep host Python installations out of discovery. A fallback to the
    # runner image's python3 must fail, even if it could create a venv.
    fake_python = fake_bin / 'python3'
    fake_python.write_text('#!/usr/bin/env bash\necho unexpected-python3 >&2\nexit 99\n', encoding='utf-8')
    fake_python.chmod(0o755)
    fake_uv = fake_bin / 'uv'
    fake_uv.write_text(
        '#!/usr/bin/env bash\n'
        'set -eu\n'
        'printf "%s\\n" "$*" >> "$UV_LOG"\n'
        'if [ "$1" = venv ]; then\n'
        '  [ "$2" = --python ] && [ "$3" = "$EXPECTED_PYTHON" ]\n'
        '  mkdir -p "$4/bin"\n'
        '  cat > "$4/bin/python" <<\'PYTHON\'\n'
        '#!/usr/bin/env bash\n'
        'case "${1:-}" in\n'
        '  -c) printf "%s\\n" "$CREATED_MINOR" ;;\n'
        '  -) cat >/dev/null ;;\n'
        '  *) printf ok > "$2" ;;\n'
        'esac\n'
        'PYTHON\n'
        '  chmod +x "$4/bin/python"\n'
        'fi\n',
        encoding='utf-8',
    )
    fake_uv.chmod(0o755)
    log = tmp_path / 'uv.log'
    marker = tmp_path / 'probe.txt'
    env = {
        **os.environ,
        'PATH': f'{_bash_path(fake_bin)}:/usr/bin:/bin',
        'UV_LOG': _bash_path(log),
        'EXPECTED_PYTHON': override or '3.11',
        'CREATED_MINOR': created_minor,
    }
    env.pop('OPENAPI_RUNNER_PYTHON', None)
    env.pop('OPENAPI_RUNNER_VENV', None)
    if override:
        env['OPENAPI_RUNNER_PYTHON'] = override

    result = subprocess.run(
        route_policy.bash_command(runner, 'probe.py', _bash_path(marker)),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == expected_status, result.stdout + result.stderr
    calls = log.read_text(encoding='utf-8').splitlines()
    assert calls[0] == f'venv --python {override or "3.11"} {_bash_path(backend)}/.openapi-venv'
    if expected_status == 0:
        assert calls[1].startswith('pip sync --python ')
        assert marker.read_text(encoding='utf-8') == 'ok'
    else:
        assert 'uses Python 3.14; expected 3.11' in result.stderr
        assert len(calls) == 1
        assert not marker.exists()
