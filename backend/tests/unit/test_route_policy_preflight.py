import os
from pathlib import Path
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
