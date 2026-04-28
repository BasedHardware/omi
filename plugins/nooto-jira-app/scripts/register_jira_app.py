#!/usr/bin/env python3
"""Register or update the Nooto Jira plugin against the Nooto backend.

Idempotent: probes ``GET /v1/apps/{id}`` first; PATCHes if the app already
exists in Firestore, otherwise POSTs a new registration.

Usage:
    NOOTO_ADMIN_TOKEN=<firebase-id-token> \\
        python3 scripts/register_jira_app.py --env staging

Notes
-----
* The backend's ``POST /v1/apps`` (``backend/routers/apps.py:481``) overwrites
  ``id`` with a fresh ULID. To get a stable ``nooto-jira`` document id we PATCH
  whenever the app already exists. First-time registration produces a ULID id;
  re-run after manually renaming the doc to ``nooto-jira`` (or accept the
  ULID; downstream wiring keys on whatever id the backend returns).
* All ``external_integration`` field names are verified against
  ``backend/models/app.py:64-82``.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests  # script context: requests is fine here

ENV_URLS = {
    "staging": "https://nooto-dev.togodynamics.com",
    "prod": "https://nooto.togodynamics.com",
}
PUBLIC_URLS = {
    # Single Coolify deployment serves both backends. If a dedicated staging
    # plugin is ever provisioned, split the staging value to its own hostname.
    "staging": "https://nooto-jira.togodynamics.com",
    "prod": "https://nooto-jira.togodynamics.com",
}
# `nooto-jira` is our preferred id, but the backend overrides it with a ULID on
# first POST. Subsequent PATCHes need the actual stored id — pass via env var
# `NOOTO_JIRA_APP_ID` to override (or rely on find_existing's list scan).
APP_ID = os.environ.get("NOOTO_JIRA_APP_ID", "nooto-jira")
LOGO = Path(__file__).resolve().parents[2] / "logos" / "nooto-jira.png"
TIMEOUT = 30


def build_payload(env: str) -> dict:
    """Build the ``app_data`` JSON body.

    Field names verified against ``backend/models/app.py``:
    - ``ExternalIntegration`` (lines 64-82): triggers_on, webhook_url,
      setup_completed_url, app_home_url, chat_tools_manifest_url,
      auth_steps, actions
    - ``AuthStep`` (lines 47-49): name, url
    - ``AppCreate`` (lines 232-258): id, name, category, author, email,
      description, image, capabilities, private, approved, status, is_paid
    """
    pub = PUBLIC_URLS[env]
    return {
        "id": APP_ID,
        "name": "Jira",
        "category": "productivity",
        "author": "Togo Dynamics",
        "email": "matheus@togodynamics.com",
        "description": ("Create, update and search Jira issues from your Nooto conversations."),
        "image": "",
        "capabilities": ["external_integration"],
        "private": False,
        "approved": False,
        "status": "under-review",
        "is_paid": False,
        "external_integration": {
            "triggers_on": "memory_creation",
            "webhook_url": f"{pub}/memory_created",
            "setup_completed_url": f"{pub}/setup/jira",
            # `app_home_url` MUST be the bare plugin origin — the backend
            # derives `chat_tools[].endpoint` URLs by joining this with
            # `/tools/<name>`. Pointing it at `/auth/jira` (the OAuth
            # entry, which lives in `auth_steps[0].url` instead) used to
            # produce 404s on every tool call. The desktop client's OAuth
            # handoff prefers `auth_steps[0].url` over `app_home_url`, so
            # this split is safe.
            "app_home_url": pub,
            "chat_tools_manifest_url": f"{pub}/.well-known/omi-tools.json",
            "auth_steps": [{"name": "Connect Jira", "url": f"{pub}/auth/jira"}],
            "actions": [],
        },
    }


def find_existing(base: str, headers: dict) -> dict | None:
    """Return existing app dict if registered, else None.

    Tries ``GET /v1/apps/{id}`` first (cheap, exact). Falls back to scanning
    ``GET /v1/apps`` since the list endpoint does not currently filter by id.
    """
    direct = requests.get(f"{base}/v1/apps/{APP_ID}", headers=headers, timeout=TIMEOUT)
    if direct.status_code == 200:
        return direct.json()
    if direct.status_code not in (404, 403):
        # Unexpected — surface for debugging, then fall back to list scan.
        print(f"[warn] GET /v1/apps/{APP_ID} -> {direct.status_code}: {direct.text[:200]}")

    listing = requests.get(f"{base}/v1/apps", headers=headers, timeout=TIMEOUT)
    if listing.status_code != 200:
        print(f"[warn] GET /v1/apps -> {listing.status_code}: {listing.text[:200]}")
        return None
    body = listing.json()
    items = body if isinstance(body, list) else body.get("apps", [])
    for item in items:
        if item.get("id") == APP_ID:
            return item
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=list(ENV_URLS), required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the payload + target URL without sending the request.",
    )
    args = parser.parse_args()

    token = os.environ.get("NOOTO_ADMIN_TOKEN")
    if not token:
        print("error: NOOTO_ADMIN_TOKEN env var is required (Firebase ID token).", file=sys.stderr)
        return 1
    if not LOGO.exists():
        print(f"error: logo missing at {LOGO}", file=sys.stderr)
        return 1

    base = ENV_URLS[args.env]
    payload = build_payload(args.env)
    headers = {"Authorization": f"Bearer {token}"}

    if args.dry_run:
        print(f"[dry-run] backend = {base}")
        print(f"[dry-run] logo    = {LOGO} ({LOGO.stat().st_size} bytes)")
        print("[dry-run] app_data:")
        print(json.dumps(payload, indent=2))
        return 0

    existing = find_existing(base, headers)
    if existing:
        url = f"{base}/v1/apps/{existing.get('id', APP_ID)}"
        method = "PATCH"
    else:
        url = f"{base}/v1/apps"
        method = "POST"

    files = {"file": (LOGO.name, LOGO.read_bytes(), "image/png")}
    data = {"app_data": json.dumps(payload)}
    print(f"[info] {method} {url}")
    resp = requests.request(method, url, data=data, files=files, headers=headers, timeout=60)
    print(f"[info] status={resp.status_code}")
    print(resp.text)
    return 0 if resp.ok else 1


if __name__ == "__main__":
    sys.exit(main())
