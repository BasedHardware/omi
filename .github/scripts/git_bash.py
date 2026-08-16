"""Cross-platform Bash discovery and path conversion for repository checks."""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import shutil
import subprocess

Which = Callable[[str], str | None]
Run = Callable[..., subprocess.CompletedProcess[str]]
GIT_LAYOUT_PARENT_LIMIT = 3


def bash_executable(*, platform_name: str | None = None, which: Which = shutil.which) -> str:
    platform = platform_name or os.name
    if platform != "nt":
        bash = which("bash")
        if bash:
            return bash
        raise FileNotFoundError("Bash is required for this repository check")

    git = which("git")
    if git:
        for parent in tuple(Path(git).resolve().parents)[:GIT_LAYOUT_PARENT_LIMIT]:
            for relative_path in (Path("bin/bash.exe"), Path("usr/bin/bash.exe")):
                candidate = parent / relative_path
                if candidate.is_file():
                    return str(candidate)
    raise FileNotFoundError("Git for Windows Bash is required for this repository check")


def _cygpath(value: str, bash: str, mode: str, *, run: Run = subprocess.run) -> str:
    result = run(
        [bash, "-c", f'cygpath {mode} "$1"', "bash", value],
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or "").strip() or (result.stdout or "").strip()
        raise RuntimeError(detail or f"cygpath {mode} failed with status {result.returncode}")
    return result.stdout.strip()


def bash_path(
    value: Path,
    bash: str,
    *,
    platform_name: str | None = None,
    run: Run = subprocess.run,
) -> str:
    if (platform_name or os.name) != "nt":
        return str(value)
    return _cygpath(str(value), bash, "-u", run=run)


def native_path_from_bash(
    value: str,
    bash: str,
    *,
    platform_name: str | None = None,
    run: Run = subprocess.run,
) -> Path:
    if (platform_name or os.name) != "nt":
        return Path(value)
    return Path(_cygpath(value, bash, "-w", run=run))
