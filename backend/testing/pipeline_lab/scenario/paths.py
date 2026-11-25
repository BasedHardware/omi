"""Where scenario commands keep host state (the shared ``scenario stack``, recorded STT cassettes).

``$OMI_PIPELINE_LAB_ROOT`` when set (created if missing), else the lab host's default root
(``stack/config.DEFAULT_LAB_ROOT``) when it exists, else a per-user cache directory:
``$XDG_CACHE_HOME/pipeline-lab`` or ``~/.cache/pipeline-lab``. So a fresh checkout on any machine runs
``python -m testing.pipeline_lab scenario run`` with no environment variables, and the lab host keeps using
its volume. Day replays (``store.py``) do not read this: they keep their own root and its checks.
"""

from __future__ import annotations

import os
from pathlib import Path
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
