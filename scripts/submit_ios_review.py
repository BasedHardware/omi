#!/usr/bin/env python3
"""Submit an already-uploaded iOS build for App Store review.

Reads ASC credentials from the environment. Never prints them.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BUNDLE = "com.friend-app-with-wearable.ios12"
BASE = "https://api.appstoreconnect.apple.com"


def fail(msg: str, code: int = 3) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def jwt_token(key_id: str, issuer: str, key_path: Path) -> str:
    import jwt

    now = int(time.time())
    return jwt.encode(
        {"iss": issuer, "iat": now, "exp": now + 15 * 60, "aud": "appstoreconnect-v1"},
        key_path.read_text(),
        algorithm="ES256",
        headers={"kid": key_id, "typ": "JWT"},
    )


def call(token: str, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw[:500]}
        return exc.code, parsed


def apple_error(payload: dict) -> str:
    errors = payload.get("errors") or []
    if not errors:
        return json.dumps(payload)[:400]
    parts = []
    for err in errors[:4]:
        parts.append(
            f"{err.get('status')} {err.get('code')} {err.get('title')}: {err.get('detail')}"
        )
    return " | ".join(parts)


def main() -> int:
    if os.environ.get("CONFIRM") != "submit-for-review":
        fail("ABORT: CONFIRM must be submit-for-review")
    if os.environ.get("PLATFORM", "ios") not in ("ios", "both"):
        fail("ABORT: this script submits iOS only")
    version = os.environ["SUBMIT_VERSION"]
    build_no = os.environ["IOS_BUILD"]
    key_id = os.environ["APP_STORE_CONNECT_KEY_IDENTIFIER"]
    issuer = os.environ["APP_STORE_CONNECT_ISSUER_ID"]
    private_key = os.environ["APP_STORE_CONNECT_PRIVATE_KEY"]
    key_path = Path("/tmp/AuthKey.p8")
    key_path.write_text(private_key if private_key.endswith("\n") else private_key + "\n")
    key_path.chmod(0o600)
    token = jwt_token(key_id, issuer, key_path)

    code, apps = call(token, "GET", "/v1/apps?" + urllib.parse.urlencode({"filter[bundleId]": BUNDLE}))
    if code != 200 or not (apps.get("data") or []):
        fail(f"ABORT: app lookup {code} {apple_error(apps)}")
    app_id = apps["data"][0]["id"]
    print(f"app {app_id} bundle {BUNDLE}")

    query = urllib.parse.urlencode(
        {
            "filter[app]": app_id,
            "filter[version]": build_no,
            "limit": "5",
        }
    )
    code, builds = call(token, "GET", "/v1/builds?" + query)
    if code != 200:
        fail(f"ABORT: build lookup {code} {apple_error(builds)}")
    matches = [
        b
        for b in builds.get("data") or []
        if str((b.get("attributes") or {}).get("version")) == build_no
    ]
    if not matches:
        fail(f"ABORT: build {build_no} not found")
    build = matches[0]
    state = (build.get("attributes") or {}).get("processingState")
    print(f"build {build_no} id {build['id']} processing {state}")
    if state != "VALID":
        fail(f"ABORT: build {build_no} is {state}, not VALID")

    query = urllib.parse.urlencode(
        {
            "filter[platform]": "IOS",
            "filter[versionString]": version,
            "limit": "5",
        }
    )
    code, versions = call(token, "GET", f"/v1/apps/{app_id}/appStoreVersions?{query}")
    if code != 200:
        fail(f"ABORT: version lookup {code} {apple_error(versions)}")
    existing = versions.get("data") or []
    if existing:
        ver = existing[0]
        ver_state = (ver.get("attributes") or {}).get("appStoreState")
        print(f"version {version} id {ver['id']} state {ver_state}")
        if ver_state in ("WAITING_FOR_REVIEW", "IN_REVIEW", "PENDING_DEVELOPER_RELEASE", "READY_FOR_SALE"):
            print(f"already {ver_state}; not submitting again")
            return 0
        code, patched = call(
            token,
            "PATCH",
            f"/v1/appStoreVersions/{ver['id']}/relationships/build",
            {"data": {"type": "builds", "id": build["id"]}},
        )
        if code not in (200, 204):
            fail(f"ABORT: attach build {code} {apple_error(patched)}")
        version_id = ver["id"]
    else:
        code, created = call(
            token,
            "POST",
            "/v1/appStoreVersions",
            {
                "data": {
                    "type": "appStoreVersions",
                    "attributes": {
                        "platform": "IOS",
                        "versionString": version,
                        "releaseType": "MANUAL",
                    },
                    "relationships": {
                        "app": {"data": {"type": "apps", "id": app_id}},
                        "build": {"data": {"type": "builds", "id": build["id"]}},
                    },
                }
            },
        )
        if code not in (200, 201):
            fail(f"ABORT: create version {code} {apple_error(created)}")
        version_id = created["data"]["id"]
        print(f"created version {version} id {version_id} releaseType MANUAL")

    code, submission = call(
        token,
        "POST",
        "/v1/reviewSubmissions",
        {
            "data": {
                "type": "reviewSubmissions",
                "attributes": {"platform": "IOS"},
                "relationships": {"app": {"data": {"type": "apps", "id": app_id}}},
            }
        },
    )
    if code not in (200, 201):
        fail(f"ABORT: create review submission {code} {apple_error(submission)}")
    sub_id = submission["data"]["id"]
    print(f"review submission {sub_id}")

    code, item = call(
        token,
        "POST",
        "/v1/reviewSubmissionItems",
        {
            "data": {
                "type": "reviewSubmissionItems",
                "relationships": {
                    "reviewSubmission": {"data": {"type": "reviewSubmissions", "id": sub_id}},
                    "appStoreVersion": {"data": {"type": "appStoreVersions", "id": version_id}},
                },
            }
        },
    )
    if code not in (200, 201):
        fail(f"ABORT: add review item {code} {apple_error(item)}")

    code, submitted = call(
        token,
        "PATCH",
        f"/v1/reviewSubmissions/{sub_id}",
        {
            "data": {
                "type": "reviewSubmissions",
                "id": sub_id,
                "attributes": {"submitted": True},
            }
        },
    )
    if code not in (200, 201):
        fail(f"ABORT: submit review {code} {apple_error(submitted)}")
    final = ((submitted.get("data") or {}).get("attributes") or {}).get("state")
    print(f"submitted review {sub_id} state {final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
