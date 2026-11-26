"""Where scenario commands keep host state (the shared ``scenario stack``, recorded STT cassettes).

``$OMI_PIPELINE_LAB_ROOT`` when set (created if missing), else the lab host's default root
(``stack/config.DEFAULT_LAB_ROOT``) when it exists, else a per-user cache directory:
``$XDG_CACHE_HOME/pipeline-lab`` or ``~/.cache/pipeline-lab``. So a fresh checkout on any machine runs
``python -m testing.pipeline_lab scenario run`` with no environment variables, and the lab host keeps using
its volume. Day replays (``store.py``) do not read this: they keep their own root and its checks. Writers go
through :func:`private_lab_root`, so the root is owner-only however it was chosen.
"""

from __future__ import annotations

import os
from pathlib import Path
import stat
from typing import Mapping, Optional

CACHE_NAME = 'pipeline-lab'


def user_cache_root(environ: Optional[Mapping[str, str]] = None) -> Path:
    env = os.environ if environ is None else environ
    base = (env.get('XDG_CACHE_HOME') or '').strip()
    return (Path(base).expanduser() if base else Path.home() / '.cache') / CACHE_NAME


def scenario_lab_root(environ: Optional[Mapping[str, str]] = None) -> Path:
    from testing.pipeline_lab.stack.config import DEFAULT_LAB_ROOT, LAB_ROOT_ENV

    env = os.environ if environ is None else environ
    configured = (env.get(LAB_ROOT_ENV) or '').strip()
    if configured:
        return Path(configured).expanduser()
    if Path(DEFAULT_LAB_ROOT).is_dir():
        return Path(DEFAULT_LAB_ROOT)
    return user_cache_root(env)


def private_lab_root(environ: Optional[Mapping[str, str]] = None) -> Path:
    """:func:`scenario_lab_root`, created owner-only (0700, missing parents too) and validated with
    ``store.ensure_private_dir``: refused when it is inside a git worktree, foreign, a symlink or group/other
    accessible. Everything a scenario command writes there (the shared stack's logs, recorded cassettes, local
    STT work files, default run output) can hold private data."""
    from testing.pipeline_lab.stack.config import LAB_ROOT_ENV
    from testing.pipeline_lab.store import private_dir

    env = os.environ if environ is None else environ
    root = scenario_lab_root(environ)
    if not (env.get(LAB_ROOT_ENV) or '').strip():
        _tighten_own(root)
    return private_dir(root, 'scenario lab root')


def _tighten_own(root: Path) -> None:
    """The default root is the lab's own directory, and lab versions before the owner-only rule created it with the
    umask's mode: tighten it to 0700 when it is a real directory this user owns. A configured root
    (``$OMI_PIPELINE_LAB_ROOT``) is the operator's choice, so it is refused, never changed."""
    try:
        info = root.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) & 0o077:
        os.chmod(root, 0o700)
