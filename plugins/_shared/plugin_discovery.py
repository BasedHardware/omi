"""Plugin discovery file — the plugin's hello to the desktop.

The desktop needs three things to call the plugin: the URL, the bearer
token, and (for real personas) a dev API key. Without a discovery
mechanism, the user has to copy/paste all three from a terminal session
into the desktop's settings UI — friction that blocks manual verify and
real-world adoption.

This module gives the plugin a one-shot way to advertise its
configuration: at startup, write a JSON file to a well-known location
with the plugin's URL + bearer token (+ optional public URL if a
tunnel is set up). The desktop reads the file on its own init and
auto-fills the AI Clone settings — zero-config for the user.

## File format

`~/.config/omi/ai-clone-plugin.json`:

```json
{
  "version": 1,
  "instance_id": "uuid",
  "started_at": 1234567890,
  "plugin_url": "http://127.0.0.1:18800",
  "public_url": "https://abc.ngrok-free.app",   // optional, if tunneled
  "bearer_token": "the-token",
  "dev_mode": true,
  "plugin_type": "telegram"
}
```

## Security

The file contains a bearer token. Mitigations:
- File is created mode 0o600 (owner read/write only).
- It lives under the user's home dir, so other user processes on the
  same machine can NOT read it (the OS enforces this).
- The file is a bootstrap convenience, NOT the source of truth. The
  desktop reads it once and copies the values into the macOS Keychain
  (where they're encrypted at rest). Subsequent launches read from
  Keychain, not the discovery file.
- If the discovery file disappears, the desktop keeps working (Keychain
  has the values). If the plugin restarts and writes a NEW file, the
  desktop can re-read and update Keychain — this lets the user rotate
  the bearer token by restarting the plugin, with no desktop UI
  interaction.
"""

from __future__ import annotations

import itertools
import json
import os
import time
import uuid
from pathlib import Path

# XDG-style path under the user's home dir. On macOS, $HOME is
# /Users/<user> and the XDG_CONFIG_HOME convention typically points to
# ~/Library/Application Support or ~/.config. We use ~/.config because:
#  - it's the cross-platform Linux-style location
#  - it's readable from any language (Python, Swift) without platform glue
#  - the user can find it in Finder by going to ~/ (Go → "Go to Folder")
DISCOVERY_DIR = Path.home() / ".config" / "omi"

# Per-process monotonic counter used to make tmp filenames unique within
# a single process. P2 from cubic AI review (PR #8682): the previous
# design used `.{os.getpid()}.tmp` which collides if two threads / tasks
# in the same process call write_discovery concurrently (same-process
# concurrent writes, e.g. a plugin reconfiguring itself in a test setup
# or a hot-reload). PID alone is not unique within a process; pairing
# PID with a counter gives every concurrent writer its own tmp path.
_tmp_counter = itertools.count()
# Per-plugin discovery files. cubic P1: a single fixed file path breaks
# concurrent multi-plugin discovery (Telegram + WhatsApp running
# simultaneously). Each plugin gets its own file keyed by plugin_type.
_DISCOVERY_FILES = {}  # plugin_type → Path, populated lazily


def discovery_file(plugin_type: str = "telegram") -> Path:
    """Return the discovery file path for a specific plugin type."""
    if plugin_type not in _DISCOVERY_FILES:
        _DISCOVERY_FILES[plugin_type] = DISCOVERY_DIR / f"ai-clone-plugin-{plugin_type}.json"
    return _DISCOVERY_FILES[plugin_type]


# Backward compat: the default file (for single-plugin dev).
# Desktop reads this as fallback if no per-plugin file is found.
DISCOVERY_FILE = DISCOVERY_DIR / "ai-clone-plugin.json"

# Bump on breaking schema changes. The desktop refuses to read a
# higher version (forward-compat) or a malformed one (graceful skip).
DISCOVERY_VERSION = 1


def write_discovery(
    *,
    plugin_url: str,
    bearer_token: str,
    public_url: str | None = None,
    dev_mode: bool = True,
    plugin_type: str,
    instance_id: str | None = None,
    omi_base_url: str | None = None,
) -> Path:
    """Write the discovery JSON. Atomic via tmp+rename. Returns the path.

    The instance_id parameter is optional — pass it back to
    clear_discovery() to ensure you only delete YOUR file (a leftover
    file from an older plugin instance stays in place).

    `plugin_type` is REQUIRED (no default). The shared module is used
    by multiple plugin flavors (telegram, whatsapp, imessage, ...) and
    a Telegram-biased default would silently mislabel other plugin
    types if a caller omitted the argument. Identified by cubic (P2).
    """
    # The parent dir holds a bearer token (file mode 0o600 below), so
    # the directory itself must also be locked down — otherwise a
    # second local user could read the file via path traversal on a
    # misconfigured share. Best-effort: if chmod on an EXISTING dir
    # fails (Windows, NFS, ACL-only volumes) we still write the file
    # 0o600; on POSIX this narrows the dir to owner-only.
    try:
        DISCOVERY_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Tighten pre-existing dirs that mkdir(exist_ok=True) won't
        # re-chmod. Idempotent — safe to call every startup.
        os.chmod(DISCOVERY_DIR, 0o700)
    except OSError:
        pass

    payload = {
        "version": DISCOVERY_VERSION,
        "instance_id": instance_id or str(uuid.uuid4()),
        "started_at": int(time.time()),
        "plugin_url": plugin_url,
        "bearer_token": bearer_token,
        "public_url": public_url,
        "dev_mode": dev_mode,
        "plugin_type": plugin_type,
        "omi_base_url": omi_base_url,
    }

    # Per-plugin file (cubic P1: concurrent Telegram + WhatsApp
    # plugins must not overwrite each other's discovery file).
    target = discovery_file(plugin_type)
    # Unique tmp filename to avoid race between concurrent writers.
    # P2 (cubic, PR #8682): include a process-unique counter alongside
    # PID so same-process concurrent writers (threads / asyncio tasks
    # racing in a test setup or hot-reload) don't collide on the same
    # tmp path.
    tmp = target.with_suffix(f".{os.getpid()}.{next(_tmp_counter)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2)
            f.flush()
        os.replace(tmp, target)
        return target
    except Exception:
        # Make sure we don't leave the temp file behind with stale
        # bearer material. Unlink errors are swallowed — the next
        # write will overwrite it.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def clear_discovery(plugin_type: str = "telegram", instance_id: str | None = None) -> None:
    """Remove the discovery file.

    If `instance_id` is given, only delete the file when its stored
    instance_id matches — protects against a stale file from a
    previous process being removed by a new process that thinks it
    owns the path.
    """
    target = discovery_file(plugin_type)
    if not target.exists():
        return
    if instance_id:
        try:
            data = json.loads(target.read_text())
            if data.get("instance_id") != instance_id:
                return
        except (OSError, json.JSONDecodeError):
            # File is malformed or unreadable — best effort: try to
            # remove it so a fresh plugin can write a clean one.
            pass
    try:
        target.unlink()
    except FileNotFoundError:
        pass
