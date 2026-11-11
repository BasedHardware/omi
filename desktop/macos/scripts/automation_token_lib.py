"""Shared automation-bridge bearer token resolution.

The desktop app writes the per-launch token to
``NSTemporaryDirectory()/omi-automation-{port}.token``. On macOS that directory
is ``getconf DARWIN_USER_TEMP_DIR``, which is often *not* the shell's ``$TMPDIR``
(launchd jobs, Actions runners, Multica scratch overrides). Readers must try
Darwin user temp before falling back to ``$TMPDIR`` / ``/tmp``.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


class AutomationTokenError(RuntimeError):
    """Token file exists but cannot be read (permissions/encoding). Fail closed."""


def darwin_user_temp_dir() -> Path | None:
    try:
        completed = subprocess.run(
            ["getconf", "DARWIN_USER_TEMP_DIR"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    raw = (completed.stdout or "").strip()
    if not raw:
        return None
    return Path(raw)


def automation_token_file_candidates(port: int) -> list[Path]:
    """Ordered token-file paths to try for a bridge port."""
    explicit = os.environ.get("OMI_AUTOMATION_TOKEN_FILE", "").strip()
    if explicit:
        return [Path(explicit)]

    candidates: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = str(path)
        if key in seen:
            return
        seen.add(key)
        candidates.append(path)

    darwin = darwin_user_temp_dir()
    if darwin is not None:
        add(darwin / f"omi-automation-{port}.token")

    add(Path(os.environ.get("TMPDIR", "/tmp")) / f"omi-automation-{port}.token")
    return candidates


def automation_token(port: int, *, fail_closed_unreadable: bool = True) -> str | None:
    """Load the per-launch bridge bearer token.

    Missing token file → None.
    Unreadable/corrupt token file → AutomationTokenError when fail_closed_unreadable.
    """
    token = os.environ.get("OMI_AUTOMATION_TOKEN", "").strip()
    if token:
        return token

    last_unreadable: Exception | None = None
    last_path: Path | None = None
    for token_file in automation_token_file_candidates(port):
        try:
            token = token_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            continue
        except (OSError, UnicodeError) as exc:
            if fail_closed_unreadable:
                raise AutomationTokenError(
                    f"automation token file unreadable at {token_file}: {exc}"
                ) from exc
            last_unreadable = exc
            last_path = token_file
            continue
        if token:
            return token
    if last_unreadable is not None and last_path is not None and fail_closed_unreadable:
        raise AutomationTokenError(
            f"automation token file unreadable at {last_path}: {last_unreadable}"
        ) from last_unreadable
    return None


def automation_token_missing_message(port: int) -> str:
    tried = ", ".join(str(path) for path in automation_token_file_candidates(port))
    return (
        f"automation_token_missing for port {port}; "
        f"set OMI_AUTOMATION_TOKEN / OMI_AUTOMATION_TOKEN_FILE or wait for token file "
        f"(tried: {tried})"
    )
