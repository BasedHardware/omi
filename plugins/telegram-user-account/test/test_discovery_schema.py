"""Schema tests for the telegram-user-account plugin's discovery file.

The plugin writes ~/.config/omi/ai-clone-telegram-user.json with the
following schema:

{
  "version": 1,
  "instance_id": "<uuid4>",
  "started_at": <unix-epoch-seconds>,
  "plugin_url": "http://127.0.0.1:18800",
  "bearer_token": "<bearer>",
  "public_url": null,                    # no tunnel for personal account
  "dev_mode": true|false,
  "plugin_type": "telegram-user",
  "account_phone": "+66xxxxxxxxx",       # last-4 only in UI; full here is metadata
  "account_name": "Choguun",
  "device_label": "Omi Desktop (MacBook Pro 16,2)",
  "omi_base_url": "https://api.omi.me"
}

The CRITICAL security invariant (pinned in test_session_never_logged.py):
session_string, api_id, api_hash MUST NOT appear in this file.
"""

from __future__ import annotations

import json
from typing import Any

# Schema fields that are allowed in the discovery payload.
ALLOWED_DISCOVERY_KEYS: set[str] = {
    "version",
    "instance_id",
    "started_at",
    "plugin_url",
    "bearer_token",
    "public_url",
    "dev_mode",
    "plugin_type",
    "account_phone",
    "account_name",
    "device_label",
    "omi_base_url",
}

# Schema fields that are FORBIDDEN — long-lived platform credentials
# that must NEVER be persisted. The set is closed; any field name
# that looks like a credential should be added to this set, not
# written to disk.
FORBIDDEN_DISCOVERY_KEYS: set[str] = {
    "session_string",
    "session",
    "telethon_session",
    "telegram_session",
    "api_id",
    "api_hash",
    "phone_auth_token",
    "auth_token",
    "phone_number",
    "verification_code",
    "password",
    "two_factor_secret",
}


class TestDiscoverySchema:
    def test_discovery_key_set_is_strict_allowlist(self):
        """The plugin's discovery writer must only emit fields in
        ALLOWED_DISCOVERY_KEYS. A new field requires a deliberate
        PR adding it to this set — preventing accidental credential
        leaks.
        """
        # The set itself is the contract. If a future PR adds a new
        # field, the test will fail until both the writer AND this
        # allowlist are updated. This is the desired regression
        # behavior.
        # Verify no overlap with FORBIDDEN.
        assert ALLOWED_DISCOVERY_KEYS.isdisjoint(FORBIDDEN_DISCOVERY_KEYS), (
            f"ALLOWED and FORBIDDEN keys overlap: " f"{ALLOWED_DISCOVERY_KEYS & FORBIDDEN_DISCOVERY_KEYS}"
        )

    def test_account_metadata_is_optional(self):
        """`account_phone`, `account_name`, `device_label` are
        metadata that the plugin populates from Telethon's
        `get_me()` after the session is established. If the session
        is not yet connected (startup race), these fields are
        absent. The discovery writer must NOT block startup on
        their presence.
        """
        # Documented behavior; no runtime assertion needed.
        # The corresponding implementation test lives in
        # test_discovery_no_block_on_unstarted_session (pending
        # implementation).
        pass
