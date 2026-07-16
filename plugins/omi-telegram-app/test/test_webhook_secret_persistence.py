"""Regression tests for the webhook-secret persistence fix.

P1 (cubic follow-up on PR #8528): previously, when TELEGRAM_WEBHOOK_SECRET
was unset, main.py generated a fresh random secret on every startup.
Telegram's stored webhook secret (set via setWebhook) then no longer
matched incoming X-Telegram-Bot-Api-Secret-Token headers, and every
webhook delivery got a 401 until the user re-ran /setup.

Fix: resolve the secret in this order:
  1. TELEGRAM_WEBHOOK_SECRET env var
  2. $STORAGE_DIR/webhook_secret (persisted on first run)
  3. secrets.token_urlsafe(32) + write to file (first run)

This file isolates _resolve_webhook_secret() and tests the three paths.
The function is a closure inside main.py; we copy the implementation
here (not import) so a test failure clearly points at the persistence
behavior, not at module-load side effects.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import secrets
import sys
import tempfile
from unittest.mock import patch

import pytest


# Make sure no stale webhook secret leaks from a prior dev session —
# the resolver has a legacy fallback that reads /tmp/omi-tg-e2e/
# webhook_secret and migrates it to the active path. Tests that
# expect a clean state would otherwise pick up the leftover file.
@pytest.fixture(autouse=True)
def _clean_legacy_secret():
    legacy = "/tmp/omi-tg-e2e/webhook_secret"
    existed = os.path.exists(legacy)
    if existed:
        os.remove(legacy)
    yield
    # Don't restore the deleted file — the test produced a fresh one
    # in tmp_path, which is the persistent store going forward.


# ---------------------------------------------------------------------------
# Path setup: load the helper from main.py without going through the
# full module import (which requires httpx, FastAPI, etc.).
# ---------------------------------------------------------------------------
def _load_resolver():
    """Read the _resolve_webhook_secret() + helper functions out of
    main.py and exec them in an isolated namespace. Returns a callable.

    The function is a closure inside main.py (not exported), so we
    can't import it directly. Parsing the source lets us test the
    behavior without spinning up the whole FastAPI app.

    The function calls two helpers (_read_secret_safely,
    _write_secret_atomically) defined later in main.py, so we
    extract ALL THREE in source order.
    """
    import re

    main_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "main.py"
    )
    src = open(main_path).read()

    # Extract _resolve_webhook_secret() first. Stop at the call site
    # ('WEBHOOK_SECRET, _webhook_source = ...') rather than the next
    # function — the function is the LAST thing in the webhook-secret
    # block before the module-level assignment.
    m = re.search(
        r"def _resolve_webhook_secret\(.*?(?=^WEBHOOK_SECRET, _webhook_source)",
        src,
        re.DOTALL | re.MULTILINE,
    )
    assert m, "could not find _resolve_webhook_secret() in main.py"
    resolve_src = m.group(0).rstrip()

    # Extract _read_secret_safely and _write_secret_atomically. Each
    # function is followed by a blank line + the NEXT def OR by the
    # call site at module level. Use the call site as the stop pattern
    # for the last function (avoids matching the whole rest of the file
    # via the \Z end-of-file alternative).
    helpers = []
    for name in ("_read_secret_safely", "_write_secret_atomically"):
        # Stop at the next def OR at the WEBHOOK_SECRET call site
        m = re.search(
            rf"def {name}\(.*?(?=\n\ndef |^WEBHOOK_SECRET, _webhook_source|\Z)",
            src,
            re.DOTALL | re.MULTILINE,
        )
        assert m, f"could not find {name}() in main.py"
        helpers.append(m.group(0).rstrip())

    # Execute in an isolated namespace with the deps the functions use.
    # __file__ is referenced by the default-storage-dir fallback
    # ('os.path.dirname(os.path.abspath(__file__)) + "data"'); without
    # it the resolver NameErrors on first run.
    # Use the same logger name as main.py ('omi-telegram-clone') so
    # caplog captures the warnings the real code emits.
    namespace: dict = {
        "__name__": "_webhook_secret_test",
        "__file__": main_path,
        "os": os,
        "secrets": secrets,
        "errno": __import__("errno"),
        "fcntl": __import__("fcntl"),
        "logger": logging.getLogger("omi-telegram-clone"),
    }
    exec(resolve_src + "\n\n" + "\n\n".join(helpers), namespace)
    return namespace["_resolve_webhook_secret"]


_resolve_webhook_secret = _load_resolver()


class TestWebhookSecretPersistence:
    """Each test sets up its own tmp STORAGE_DIR so the persisted file
    doesn't leak between tests."""

    def test_env_var_takes_precedence_over_persisted_file(self, tmp_path, monkeypatch):
        """If TELEGRAM_WEBHOOK_SECRET is set, use it — even when a
        persisted file exists with a different value."""
        persisted = secrets.token_urlsafe(32)
        secret_path = tmp_path / "webhook_secret"
        secret_path.write_text(persisted)

        env_value = "env-var-secret"
        monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", env_value)
        monkeypatch.setenv("STORAGE_DIR", str(tmp_path))

        result, source = _resolve_webhook_secret()
        assert result == env_value
        assert source == "configured via env"

    def test_loads_from_persisted_file_when_env_unset(self, tmp_path, monkeypatch):
        """On a second startup (env unset, file exists from first
        run), return the persisted value so the webhook secret
        stays in sync with Telegram."""
        persisted = secrets.token_urlsafe(32)
        secret_path = tmp_path / "webhook_secret"
        secret_path.write_text(persisted)

        monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
        monkeypatch.setenv("STORAGE_DIR", str(tmp_path))

        result, source = _resolve_webhook_secret()
        assert result == persisted
        # The source string includes the actual path (more useful for
        # debugging than a literal "$STORAGE_DIR/webhook_secret").
        assert source.startswith("loaded from "), f"unexpected source: {source!r}"
        assert str(secret_path) in source

    def test_first_run_generates_and_persists(self, tmp_path, monkeypatch):
        """No env, no file: generate a random secret AND write it to
        $STORAGE_DIR/webhook_secret. Subsequent calls (within the
        same test) return the persisted value, not a new one."""
        monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
        monkeypatch.setenv("STORAGE_DIR", str(tmp_path))

        # First call: generate
        first, first_source = _resolve_webhook_secret()
        assert first_source.startswith("auto-generated and persisted to "), \
            f"unexpected source: {first_source!r}"
        assert str(tmp_path / "webhook_secret") in first_source
        assert len(first) >= 32  # token_urlsafe(32) is 43 chars but allow tolerance

        # File should exist with mode 0o600 (owner read/write only)
        secret_path = tmp_path / "webhook_secret"
        assert secret_path.exists()
        mode = secret_path.stat().st_mode & 0o777
        assert mode == 0o600, f"webhook secret file must be 0o600, got 0o{mode:o}"

        # Second call: returns the persisted value, NOT a new one
        second, second_source = _resolve_webhook_secret()
        assert second == first, "second call should return the persisted secret, not generate a new one"
        assert second_source.startswith("loaded from ")

    def test_corrupted_persisted_file_falls_back_to_generate(self, tmp_path, monkeypatch):
        """A persisted file with whitespace-only or empty content
        should be treated as missing — fall back to generating a new
        secret. Avoids the failure mode where an operator accidentally
        writes a blank line and locks the plugin out of Telegram."""
        secret_path = tmp_path / "webhook_secret"
        secret_path.write_text("   \n  \n")  # whitespace only

        monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
        monkeypatch.setenv("STORAGE_DIR", str(tmp_path))

        result, source = _resolve_webhook_secret()
        assert result, "generated secret must be non-empty"
        # Whitespace-only content is treated as missing, so the source
        # is 'auto-generated'. (The old code might have treated the
        # whitespace as a 'loaded' value, but the new code strips
        # before returning and returns None on empty.)
        assert source.startswith("auto-generated and persisted to "), \
            f"expected auto-generated, got: {source!r}"

    def test_unreadable_persisted_file_falls_back_to_generate(self, tmp_path, monkeypatch, caplog):
        """If the persisted file exists but can't be read (permission
        denied, etc.), the resolver logs a warning and falls back to
        generating a new secret. Better to risk one more auth failure
        than to crash startup."""
        secret_path = tmp_path / "webhook_secret"
        secret_path.write_text(secrets.token_urlsafe(32))
        # Make the file unreadable. Skip on Windows where chmod is
        # a no-op; the production path runs on Linux/macOS only.
        if hasattr(os, "chmod"):
            try:
                os.chmod(secret_path, 0o000)
            except (PermissionError, OSError):
                pytest.skip("can't make file unreadable on this fs")
            else:
                # If we're running as root, chmod 0o000 won't actually
                # block us. Skip in that case — the test verifies the
                # happy path elsewhere.
                if os.access(secret_path, os.R_OK):
                    pytest.skip("running as root — chmod 0o000 doesn't block reads")

        monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
        monkeypatch.setenv("STORAGE_DIR", str(tmp_path))

        with caplog.at_level(logging.WARNING, logger="omi-telegram-clone"):
            result, source = _resolve_webhook_secret()

        # Should fall back to generating a new secret
        assert result, "fallback secret must be non-empty"
        assert source.startswith("auto-generated and persisted to "), \
            f"expected auto-generated, got: {source!r}"
        # Warning was logged
        assert any("unreadable" in record.message for record in caplog.records), \
            f"expected 'unreadable' warning, got {[r.message for r in caplog.records]}"

    def test_secret_file_persisted_with_0o600_permissions(self, tmp_path, monkeypatch):
        """The persisted file MUST be created with mode 0o600 — the
        secret authenticates inbound Telegram webhooks, so any other
        user on the box being able to read it would be a privilege
        boundary violation."""
        monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
        monkeypatch.setenv("STORAGE_DIR", str(tmp_path))

        _resolve_webhook_secret()

        secret_path = tmp_path / "webhook_secret"
        assert secret_path.exists()
        mode = secret_path.stat().st_mode & 0o777
        assert mode == 0o600, f"webhook secret must be 0o600, got 0o{mode:o}"
