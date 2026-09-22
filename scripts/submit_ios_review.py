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
        return json.dumps(payload)[:800]
    parts = []
    for err in errors[:4]:
        line = f"{err.get('status')} {err.get('code')} {err.get('title')}: {err.get('detail')}"
        associated = (err.get("meta") or {}).get("associatedErrors") or {}
        if associated:
            line += " associated=" + json.dumps(associated)[:800]
        parts.append(line)
    return " | ".join(parts)


def ok(code: int) -> bool:
    return code in (200, 201, 204)


def previous_live_version(token: str, app_id: str, current_id: str) -> dict | None:
    query = urllib.parse.urlencode({"filter[platform]": "IOS", "limit": "20"})
    code, payload = call(token, "GET", f"/v1/apps/{app_id}/appStoreVersions?{query}")
    if code != 200:
        print(f"previous version lookup {code} {apple_error(payload)}")
        return None
    live = [
        item
        for item in payload.get("data") or []
        if item.get("id") != current_id
        and (item.get("attributes") or {}).get("appStoreState") == "READY_FOR_SALE"
    ]
    return live[0] if live else None


def copy_localizations(token: str, source_id: str, dest_id: str) -> None:
    code, source = call(token, "GET", f"/v1/appStoreVersions/{source_id}/appStoreVersionLocalizations?limit=20")
    if not ok(code):
        print(f"source localizations {code} {apple_error(source)}")
        return
    code, dest = call(token, "GET", f"/v1/appStoreVersions/{dest_id}/appStoreVersionLocalizations?limit=20")
    if not ok(code):
        print(f"dest localizations {code} {apple_error(dest)}")
        return
    existing = {
        (item.get("attributes") or {}).get("locale"): item
        for item in dest.get("data") or []
    }
    fields = ("description", "keywords", "marketingUrl", "promotionalText", "supportUrl", "whatsNew")
    for item in source.get("data") or []:
        attrs = item.get("attributes") or {}
        locale = attrs.get("locale")
        copied = {key: attrs.get(key) for key in fields if attrs.get(key)}
        copied["whatsNew"] = copied.get("whatsNew") or "Bug fixes and improvements."
        if locale in existing:
            code, patched = call(
                token,
                "PATCH",
                f"/v1/appStoreVersionLocalizations/{existing[locale]['id']}",
                {"data": {"type": "appStoreVersionLocalizations", "id": existing[locale]["id"], "attributes": copied}},
            )
        else:
            code, patched = call(
                token,
                "POST",
                "/v1/appStoreVersionLocalizations",
                {
                    "data": {
                        "type": "appStoreVersionLocalizations",
                        "attributes": {"locale": locale, **copied},
                        "relationships": {
                            "appStoreVersion": {"data": {"type": "appStoreVersions", "id": dest_id}}
                        },
                    }
                },
            )
        print(f"localization {locale} {code}")
        if not ok(code):
            print(apple_error(patched))


def copy_review_detail(token: str, source_id: str, dest_id: str) -> None:
    code, current = call(token, "GET", f"/v1/appStoreVersions/{dest_id}/appStoreReviewDetail")
    if ok(code) and current.get("data"):
        print("review detail already present")
        return
    code, source = call(token, "GET", f"/v1/appStoreVersions/{source_id}/appStoreReviewDetail")
    if not ok(code) or not source.get("data"):
        print(f"source review detail {code} {apple_error(source)}")
        return
    attrs = dict((source.get("data") or {}).get("attributes") or {})
    attrs.pop("appStoreReviewAttachments", None)
    code, created = call(
        token,
        "POST",
        "/v1/appStoreReviewDetails",
        {
            "data": {
                "type": "appStoreReviewDetails",
                "attributes": attrs,
                "relationships": {
                    "appStoreVersion": {"data": {"type": "appStoreVersions", "id": dest_id}}
                },
            }
        },
    )
    print(f"review detail copy {code}")
    if not ok(code):
        print(apple_error(created))


def mark_encryption(token: str, build_id: str) -> None:
    code, build = call(token, "GET", f"/v1/builds/{build_id}")
    if not ok(code):
        print(f"build read {code} {apple_error(build)}")
        return
    current = (build.get("data") or {}).get("attributes") or {}
    if current.get("usesNonExemptEncryption") is not None:
        print(f"encryption already set {current.get('usesNonExemptEncryption')}")
        return
    code, patched = call(
        token,
        "PATCH",
        f"/v1/builds/{build_id}",
        {
            "data": {
                "type": "builds",
                "id": build_id,
                "attributes": {"usesNonExemptEncryption": False},
            }
        },
    )
    print(f"encryption patch {code}")
    if not ok(code):
        print(apple_error(patched))


def prepare_version(token: str, app_id: str, version_id: str, build_id: str) -> None:
    code, version = call(token, "GET", f"/v1/appStoreVersions/{version_id}")
    state = ((version.get("data") or {}).get("attributes") or {}).get("appStoreState")
    print(f"version state before prepare {state}")
    previous = previous_live_version(token, app_id, version_id)
    if previous:
        print(f"copying metadata from {(previous.get('attributes') or {}).get('versionString')}")
        copy_localizations(token, previous["id"], version_id)
        copy_review_detail(token, previous["id"], version_id)
    else:
        print("no live version to copy")
    mark_encryption(token, build_id)
    code, version = call(token, "GET", f"/v1/appStoreVersions/{version_id}")
    state = ((version.get("data") or {}).get("attributes") or {}).get("appStoreState")
    print(f"version state after prepare {state}")


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

    prepare_version(token, app_id, version_id, build["id"])

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
