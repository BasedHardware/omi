"""Git environment isolation for tests that create disposable repositories."""

from __future__ import annotations

import os
import subprocess


def clean_git_env() -> dict[str, str]:
    """Keep ordinary settings while dropping the caller's repository selection."""
    local_vars = subprocess.check_output(["git", "rev-parse", "--local-env-vars"], text=True).split()
    env = os.environ.copy()
    for name in [*local_vars, "GIT_NAMESPACE"]:
        env.pop(name, None)
    return env
