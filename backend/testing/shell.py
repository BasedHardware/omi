from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import TypeAlias

ShellArgument: TypeAlias = str | os.PathLike[str]
GIT_LAYOUT_PARENT_LIMIT = 3


def find_git_bash(git_exec_path: Path) -> Path:
    """Find bash.exe in the Git for Windows installation that owns git."""
    for parent in tuple(git_exec_path.parents)[:GIT_LAYOUT_PARENT_LIMIT]:
        for relative_path in ('bin/bash.exe', 'usr/bin/bash.exe'):
            candidate = parent / relative_path
            if candidate.is_file():
                return candidate
    raise FileNotFoundError(f'Git Bash was not found above {git_exec_path}')


def bash_executable(
    *,
    cwd: Path | None = None,
    platform_name: str | None = None,
    git_exec_path: Path | None = None,
) -> str:
    if (platform_name or os.name) != 'nt':
        return 'bash'

    if git_exec_path is None:
        environment = os.environ.copy()
        environment.pop('GIT_EXEC_PATH', None)
        git_exec_path = Path(
            subprocess.check_output(
                ['git', '--exec-path'],
                cwd=cwd,
                env=environment,
                text=True,
            ).strip()
        )
    return str(find_git_bash(git_exec_path))


def bash_command(
    *args: ShellArgument,
    cwd: Path | None = None,
    platform_name: str | None = None,
    git_exec_path: Path | None = None,
) -> list[str]:
    return [
        bash_executable(cwd=cwd, platform_name=platform_name, git_exec_path=git_exec_path),
        *(os.fspath(arg) for arg in args),
    ]


def bash_path(path: Path, *, cwd: Path | None = None) -> str:
    if os.name != 'nt':
        return str(path)
    return subprocess.check_output(
        bash_command('-c', 'cygpath -u "$1"', 'bash', path, cwd=cwd),
        cwd=cwd,
        text=True,
    ).strip()
