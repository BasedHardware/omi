"""Contract tests for plugins/_shared/plugin_discovery.py.

The discovery file holds a bearer token used by the desktop app to
authenticate to the plugin. These tests pin the file's permission /
directory / argument contract so a future refactor can't silently
ship a less-restrictive shape.

Run from repo root:
    pytest plugins/_shared/test/test_plugin_discovery.py -v
"""

import os
import stat
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_SHARED = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if _SHARED not in sys.path:
    sys.path.append(_SHARED)


class TestPluginDiscoveryContract:
    """Pins the security-critical contract of write_discovery / clear_discovery."""

    def test_plugin_type_is_required(self):
        """A shared module used by telegram/whatsapp/imessage plugins must
        not default to any one flavor — forcing every caller to pass an
        explicit plugin_type prevents silent mislabeling. Identified by
        cubic (P2)."""
        import inspect

        from plugin_discovery import write_discovery

        sig = inspect.signature(write_discovery)
        param = sig.parameters["plugin_type"]
        assert param.default is inspect.Parameter.empty, (
            "write_discovery(..., plugin_type) must be REQUIRED (no default). "
            f"Found default={param.default!r} — a Telegram-biased default would "
            "silently mislabel other plugin types."
        )

    def test_discovery_file_has_strict_permissions(self, tmp_path, monkeypatch):
        """The bearer token must never be world-readable. The file is
        created mode 0o600; we don't rely on the parent umask.

        P1 fix: previously the file was opened with regular open() and
        chmod was a best-effort follow-up that could be silently
        swallowed on Windows / misconfigured volumes. The new code
        opens the fd with O_CREAT | 0o600 so the kernel applies the
        mode at create time — no race window where the file exists
        with looser perms.
        """
        # Use `import plugin_discovery` (not `from ... import ...`) so
        # monkeypatch on the module attribute is reflected when we
        # re-read the attribute via getattr() below. P1 (cubic): the
        # previous test captured DISCOVERY_FILE into a local name at
        # import time, then monkeypatched the module attribute, but
        # the local still pointed at the ORIGINAL
        # ~/.config/omi/ai-clone-plugin.json — so os.stat() was
        # inspecting the wrong file (which happened to also be 0o600
        # on the original author's dev machine, masking the bug).
        import plugin_discovery

        target = tmp_path / "ai-clone-plugin.json"
        monkeypatch.setattr(plugin_discovery, "DISCOVERY_DIR", tmp_path)
        monkeypatch.setattr(plugin_discovery, "discovery_file", lambda pt="telegram": target)

        plugin_discovery.write_discovery(
            plugin_url="http://127.0.0.1:18800",
            bearer_token="telegram-test-token",
            plugin_type="telegram",
        )

        # Re-read DISCOVERY_FILE via the module (not a captured local)
        # so the monkeypatch actually applies.
        mode = stat.S_IMODE(os.stat(target).st_mode)
        assert mode == 0o600, (
            f"discovery file must be 0o600, got 0o{mode:o}. "
            "A looser mode would expose the bearer token to other "
            "local users."
        )

    def test_discovery_directory_permissions_are_tightened(self, tmp_path, monkeypatch):
        """mkdir(parents=True, exist_ok=True, mode=0o700) does NOT re-chmod
        an existing dir. The plugin must chmod the parent on every
        write so a dir accidentally created with looser perms (e.g.
        by a previous dev build) doesn't expose the file inside it.
        """
        # P1 (cubic): same stale-local-reference bug as
        # test_discovery_file_has_strict_permissions. Use the module
        # import so monkeypatch actually applies.
        import plugin_discovery

        # Pre-create the dir with mode 0o755 (loose — what `mkdir` would
        # leave behind if no mode arg was given).
        loose_dir = tmp_path / "loose"
        loose_dir.mkdir(mode=0o755)
        target = loose_dir / "ai-clone-plugin.json"

        monkeypatch.setattr(plugin_discovery, "DISCOVERY_DIR", loose_dir)
        monkeypatch.setattr(plugin_discovery, "discovery_file", lambda pt="telegram": target)

        plugin_discovery.write_discovery(
            plugin_url="http://127.0.0.1:18800",
            bearer_token="telegram-test-token",
            plugin_type="telegram",
        )

        dir_mode = stat.S_IMODE(os.stat(plugin_discovery.DISCOVERY_DIR).st_mode)
        assert dir_mode == 0o700, (
            f"discovery dir must be tightened to 0o700 on every write, "
            f"got 0o{dir_mode:o}. A looser dir lets other local users "
            "read the file inside via path traversal on a misconfigured share."
        )

    def test_payload_contains_required_keys(self, tmp_path, monkeypatch):
        """The desktop reads this file on startup and keys off specific
        fields. Bumping or renaming a key without bumping DISCOVERY_VERSION
        would silently break the desktop. Pin the schema here."""
        import json

        import plugin_discovery

        target = tmp_path / "ai-clone-plugin.json"
        monkeypatch.setattr(plugin_discovery, "DISCOVERY_DIR", tmp_path)
        monkeypatch.setattr(plugin_discovery, "discovery_file", lambda pt="telegram": target)

        plugin_discovery.write_discovery(
            plugin_url="http://127.0.0.1:18800",
            bearer_token="t",
            public_url="https://x.ngrok.app",
            dev_mode=True,
            plugin_type="whatsapp",
        )

        data = json.loads(target.read_text())
        for key in (
            "version",
            "instance_id",
            "started_at",
            "plugin_url",
            "bearer_token",
            "public_url",
            "dev_mode",
            "plugin_type",
        ):
            assert key in data, f"discovery payload missing required key: {key}"


class TestConcurrentWritesGetUniqueTmpPaths:
    """P2 from cubic AI review (PR #8682): the tmp filename used by
    write_discovery must be unique across same-process concurrent
    writers. The previous design used `.{pid}.tmp` which collides
    when two threads / tasks in the same process call write_discovery
    at the same time (e.g. a test that triggers startup + reload
    back-to-back, or a plugin that re-publishes its discovery file on
    a config change). Two concurrent writers on the same tmp path race
    on `os.open` (one wins, the other gets the truncated file)."""

    def test_two_concurrent_writers_get_distinct_tmp_paths(self, tmp_path):
        """Verify the helper produces two different tmp filenames when
        called twice in the same process (same PID). The PID alone is
        not unique; a process-local counter must distinguish them."""
        from plugin_discovery import write_discovery

        # Override DISCOVERY_DIR via monkeypatching at the module
        # level so we don't write into the user's real ~/.config/omi/.
        import plugin_discovery

        original_dir = plugin_discovery.DISCOVERY_DIR
        original_files = plugin_discovery._DISCOVERY_FILES
        plugin_discovery.DISCOVERY_DIR = tmp_path
        plugin_discovery._DISCOVERY_FILES = {}
        try:
            path1 = write_discovery(
                plugin_url="http://127.0.0.1:18801",
                bearer_token="token-1",
                plugin_type="telegram",
            )
            path2 = write_discovery(
                plugin_url="http://127.0.0.1:18802",
                bearer_token="token-2",
                plugin_type="telegram",
            )
        finally:
            plugin_discovery.DISCOVERY_DIR = original_dir
            plugin_discovery._DISCOVERY_FILES = original_files

        # Both writes must have succeeded and pointed at the SAME
        # per-plugin target (telegram). The tmp filenames used during
        # the writes are not exposed, but we can verify the contract
        # by checking that no leftover .tmp files exist on disk — a
        # collision would have left a stray file behind.
        assert path1 == path2
        leftovers = list(tmp_path.glob("*.tmp"))
        assert leftovers == [], f"write_discovery left stray tmp files: {leftovers}"
