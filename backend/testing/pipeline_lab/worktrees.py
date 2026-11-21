"""Pinned worktree per ref, backend tree hashes, and the subprocess "arm" runner.

Modelled on owner_lab ``replay_bench``: an arm is a detached checkout pinned to a
full commit sha, verified before every use; each stage driver runs in its own
``python -I`` subprocess whose product code (``utils``, ``database``, ...) comes
only from the arm's ``backend/``, while the lab package itself is vendored from
this (harness) checkout, so every arm runs the same lab code against its own
product code.

Worktrees live under ``$OMI_PIPELINE_LAB_WORKTREES`` (default
``$OMI_WORKTREES/omi`` or ``/Volumes/Ephemeral/scratch/worktrees/omi``) as
``pipeline-lab-<sha12>``. They are never created under ``~/workspace``. Git is
the ``git`` found on PATH (the host's managed wrapper), never a hard-coded binary.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Sequence

WORKTREES_ENV = 'OMI_PIPELINE_LAB_WORKTREES'
DEFAULT_WORKTREES = '/Volumes/Ephemeral/scratch/worktrees/omi'
WORKTREE_PREFIX = 'pipeline-lab-'
LOCK_FILES = ('pylock.toml', 'requirements.txt')

# Credential-shaped keys never reach an arm unless its overlay sets them explicitly.
_SCRUB_EXACT = {'GOOGLE_APPLICATION_CREDENTIALS', 'SERVICE_ACCOUNT_JSON', 'CLOUDSDK_CONFIG', 'PYTHONPATH'}
_SCRUB_SUFFIXES = ('_SERVE_UID_SHA256S',)


class WorktreeError(RuntimeError):
    pass


GIT_ENV = 'OMI_PIPELINE_LAB_GIT'


def git_binary() -> str:
    """``git`` on PATH (the host's managed wrapper). ``$OMI_PIPELINE_LAB_GIT`` overrides it for tests."""
    found = os.environ.get(GIT_ENV) or shutil.which('git')
    if not found:
        raise WorktreeError('git not found on PATH')
    return found


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        [git_binary(), '-C', str(repo), *args],
        capture_output=True,
        text=True,
        env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'},
    )
    if check and result.returncode != 0:
        raise WorktreeError(f'git {args[0]} failed: {result.stderr.strip().splitlines()[-1:] or ["?"]}')
    return result.stdout.strip()


def forbidden_roots() -> list[Path]:
    return [(Path.home() / 'workspace').resolve()]


def worktree_root() -> Path:
    configured = os.environ.get(WORKTREES_ENV)
    if configured:
        root = Path(configured).expanduser()
    elif os.environ.get('OMI_WORKTREES'):
        root = Path(os.environ['OMI_WORKTREES']).expanduser() / 'omi'
    else:
        root = Path(DEFAULT_WORKTREES)
    check_worktree_root(root)
    return root


def check_worktree_root(root: Path) -> None:
    resolved = root.expanduser().resolve()
    for forbidden in forbidden_roots():
        if resolved == forbidden or forbidden in resolved.parents:
            raise WorktreeError('lab worktrees must never be created under ~/workspace')


def resolve_ref(repo: Path, ref: str) -> str:
    """Full commit sha for a branch, tag, PR ref or sha. No fetch: the caller owns freshness."""
    if ref.startswith('-'):
        raise WorktreeError('ref cannot start with "-"')
    return git(repo, 'rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}')


def tree_hash(repo: Path, ref: str, path: str = 'backend') -> str:
    """Git tree hash of ``path`` at ``ref`` (DESIGN L12: refs with identical backend share cache)."""
    sha = resolve_ref(repo, ref)
    return git(repo, 'rev-parse', '--verify', '--quiet', f'{sha}:{path}')


@dataclass(frozen=True)
class Worktree:
    path: Path
    sha: str
    backend_tree: str

    @property
    def backend(self) -> Path:
        return self.path / 'backend'

    def to_json(self) -> dict[str, str]:
        return {'path': str(self.path), 'sha': self.sha, 'backend_tree': self.backend_tree}


def verify_worktree(path: Path, sha: str) -> Worktree:
    """HEAD must equal the pinned sha, tracked files under backend/ must be unmodified, and no untracked
    (not ignored) Python source may sit under backend/."""
    head = git(path, 'rev-parse', 'HEAD')
    if head != sha:
        raise WorktreeError(f'worktree HEAD {head[:12]} does not match the pinned {sha[:12]}')
    dirty = git(path, 'status', '--porcelain', '--untracked-files=no', '--', 'backend')
    if dirty:
        raise WorktreeError('pinned worktree has modified tracked files under backend/')
    # backend/ is on the arm's sys.path, so an untracked module there would run code the pin lacks.
    stray = [
        name
        for name in git(path, 'ls-files', '--others', '--exclude-standard', '--', 'backend').splitlines()
        if name.endswith(('.py', '.pth', '.so'))
    ]
    if stray:
        raise WorktreeError(f'pinned worktree has {len(stray)} untracked source file(s) under backend/: {stray[0]}')
    return Worktree(path=path, sha=sha, backend_tree=git(path, 'rev-parse', f'{sha}:backend'))


def ensure_worktree(repo: Path, ref: str, root: Optional[Path] = None) -> Worktree:
    """Idempotently create (or reuse) a detached worktree pinned to ``ref``'s commit."""
    sha = resolve_ref(repo, ref)
    root = root if root is not None else worktree_root()
    check_worktree_root(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f'{WORKTREE_PREFIX}{sha[:12]}'
    if path.exists():
        return verify_worktree(path, sha)
    git(repo, 'worktree', 'add', '--detach', str(path), sha)
    return verify_worktree(path, sha)


def lock_digest(backend: Path) -> Optional[str]:
    for name in LOCK_FILES:
        candidate = backend / name
        if candidate.exists():
            return name + ':' + hashlib.sha256(candidate.read_bytes()).hexdigest()
    return None


def check_lockfile(harness_backend: Path, arm_backend: Path) -> None:
    """The arm runs on the harness venv; fail closed when its dependency lock differs."""
    if lock_digest(harness_backend) != lock_digest(arm_backend):
        raise WorktreeError(
            'arm backend dependency lock differs from the harness venv; '
            'run `make setup-backend` in the arm worktree and pass its interpreter'
        )


def arm_env(overlay: Mapping[str, str], base: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """The parent env minus credential-shaped keys, plus the overlay (which wins)."""
    env = dict(os.environ if base is None else base)
    for key in list(env):
        if key in _SCRUB_EXACT or key.endswith(_SCRUB_SUFFIXES):
            del env[key]
    env.update({str(k): str(v) for k, v in overlay.items()})
    return env


def harness_package_dir() -> Path:
    return Path(__file__).resolve().parent


def vendor_lab(destination: Path) -> Path:
    """Copy this lab package to ``destination/testing/pipeline_lab``; return ``destination``.

    ``testing`` has no ``__init__`` (a namespace package), so the vendored
    ``testing.pipeline_lab`` resolves first while ``testing.replay_harness`` and
    friends still resolve from the arm's tree.
    """
    target = destination / 'testing' / 'pipeline_lab'
    shutil.copytree(harness_package_dir(), target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    return destination


_BOOT = (
    'import runpy, sys\n'
    'vendor, backend, module = sys.argv[1], sys.argv[2], sys.argv[3]\n'
    'sys.path[:0] = [vendor, backend]\n'
    'sys.argv = [module] + sys.argv[4:]\n'
    'runpy.run_module(module, run_name="__main__", alter_sys=True)\n'
)


@dataclass
class ArmResult:
    returncode: int
    stdout: str
    stderr: str
    command: list[str] = field(default_factory=list)


def arm_command(
    vendor: Path, backend: Path, module: str, args: Sequence[str], python: Optional[str] = None
) -> list[str]:
    return [python or sys.executable, '-I', '-c', _BOOT, str(vendor), str(backend), module, *args]


def run_arm(
    backend: Path,
    module: str,
    args: Sequence[str] = (),
    *,
    overlay: Mapping[str, str] | None = None,
    python: Optional[str] = None,
    timeout: Optional[float] = None,
    base_env: Optional[Mapping[str, str]] = None,
    capture: bool = True,
) -> ArmResult:
    """Run ``python -m <module> <args>`` against ``backend`` (an arm's ``backend/``).

    The lab package is vendored to a temporary directory for the call and removed
    afterwards. cwd is the arm backend; ``-I`` keeps the parent's PYTHONPATH,
    user site and cwd out of ``sys.path``.
    """
    backend = Path(backend).resolve()
    if not backend.is_dir():
        raise WorktreeError('arm backend directory not found')
    with tempfile.TemporaryDirectory(prefix='pipeline-lab-arm-') as tmp:
        vendor = vendor_lab(Path(tmp))
        command = arm_command(vendor, backend, module, args, python)
        result = subprocess.run(
            command,
            cwd=backend,
            env=arm_env(overlay or {}, base_env),
            capture_output=capture,
            text=True,
            timeout=timeout,
        )
    return ArmResult(result.returncode, result.stdout or '', result.stderr or '', command)
