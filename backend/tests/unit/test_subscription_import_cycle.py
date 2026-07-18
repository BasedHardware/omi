"""Regression: utils.subscription must be importable on its own.

utils/subscription.py imports database.users, and database/users.py imported
get_default_basic_subscription back from utils.subscription at module scope. That pair formed a
cycle, so whichever of the two was imported first decided whether it worked: importing
utils.subscription first raised

    ImportError: cannot import name 'get_default_basic_subscription' from partially initialized
    module 'utils.subscription' (most likely due to a circular import)

while importing database.users first happened to succeed. The order-dependence is the bug, which
is why it surfaces intermittently as unrelated test files change what gets imported first. The
database -> utils edge is also the reverse of the documented backend layering
(database/ -> utils/ -> routers/ -> main.py).

A fresh interpreter is the only honest seam here: once pytest has imported either module, the
order is already decided for the whole session, so an in-process assertion would pass either way.
"""

import os
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _import_first_in_fresh_interpreter(module: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.setdefault("ENCRYPTION_SECRET", "test_secret_for_ci_only_0123456789")
    env.setdefault("OPENAI_API_KEY", "sk-fake")
    env.setdefault("PINECONE_API_KEY", "fake")
    return subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=str(BACKEND_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_utils_subscription_imports_standalone():
    result = _import_first_in_fresh_interpreter("utils.subscription")

    assert result.returncode == 0, f"utils.subscription is not importable on its own:\n{result.stderr}"


def test_database_users_imports_standalone():
    # The other side of the pair must keep working too.
    result = _import_first_in_fresh_interpreter("database.users")

    assert result.returncode == 0, f"database.users is not importable on its own:\n{result.stderr}"
