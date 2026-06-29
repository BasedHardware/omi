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
    plugin_type: str = "telegram",
    instance_id: str | None = None,
) -> Path:
    """Write the discovery JSON. Atomic via tmp+rename. Returns the path.

    The instance_id parameter is optional — pass it back to
    clear_discovery() to ensure you only delete YOUR file (a leftover
    file from an older plugin instance stays in place).
    """
    DISCOVERY_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)

    payload = {
        "version": DISCOVERY_VERSION,
        "instance_id": instance_id or str(uuid.uuid4()),
        "started_at": int(time.time()),
        "plugin_url": plugin_url,
        "bearer_token": bearer_token,
        "public_url": public_url,
        "dev_mode": dev_mode,
        "plugin_type": plugin_type,
    }

    # Atomic write so the desktop never reads a half-flushed file.
    tmp = DISCOVERY_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
    # Mode 0o600 — the bearer token must not be world-readable. On
    # Windows / non-POSIX volumes chmod silently fails; we don't fail
    # the write because the user can still see the file (and on those
    # platforms file permissions work differently anyway).
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, DISCOVERY_FILE)
    return DISCOVERY_FILE


def clear_discovery(instance_id: str | None = None) -> None:
    """Remove the discovery file.

    If `instance_id` is given, only delete the file when its stored
    instance_id matches — protects against a stale file from a
    previous process being removed by a new process that thinks it
    owns the path.
    """
    if not DISCOVERY_FILE.exists():
        return
    if instance_id:
        try:
            data = json.loads(DISCOVERY_FILE.read_text())
            if data.get("instance_id") != instance_id:
                return
        except (OSError, json.JSONDecodeError):
            # File is malformed or unreadable — best effort: try to
            # remove it so a fresh plugin can write a clean one.
            pass
    try:
        DISCOVERY_FILE.unlink()
    except FileNotFoundError:
        pass
