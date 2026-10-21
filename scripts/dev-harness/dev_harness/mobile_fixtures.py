"""Deterministic synthetic-auth fixtures for isolated mobile sessions.

Reuses the local-dev sign-in contract from open PR #11784 (do not open a
competing endpoint): the session backend exposes
``POST /v1/auth/local-dev/custom-token`` which mints a Firebase custom token
against the local Auth emulator, structurally gated by
``FIREBASE_AUTH_EMULATOR_HOST``. This module seeds a *fixture* user through
that endpoint and records a receipt that never contains the minted token.

Egress is fail-closed: the endpoint URL is validated as loopback HTTP *before*
any request is attempted, and the production hosts are denied by name.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .session_evidence import EvidenceError, utc_now, validate_local_http_url

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "mobile"
CURRENT_FIXTURE_VERSION = "v1"
LOCAL_DEV_CUSTOM_TOKEN_PATH = "/v1/auth/local-dev/custom-token"
_REQUEST_TIMEOUT_SECONDS = 10.0
_RECEIPT_SECRET_KEY_RE = re.compile(r"(custom_token|token_value|secret|password|credential)", re.IGNORECASE)


class FixtureError(RuntimeError):
    """Raised when a fixture is missing/malformed or seeding fails closed."""


@dataclass(frozen=True)
class FixtureUser:
    uid: str
    email: str
    display_name: str
    email_verified: bool


@dataclass(frozen=True)
class MobileFixture:
    version: str
    users: tuple[FixtureUser, ...]
    default_user_index: int

    @property
    def default_user(self) -> FixtureUser:
        return self.users[self.default_user_index]


def fixture_path(version: str = CURRENT_FIXTURE_VERSION) -> Path:
    return FIXTURES_DIR / f"{version}.json"


def load_fixture(version: str = CURRENT_FIXTURE_VERSION) -> MobileFixture:
    path = fixture_path(version)
    if not path.is_file():
        available = sorted(p.stem for p in FIXTURES_DIR.glob("v*.json")) if FIXTURES_DIR.is_dir() else []
        raise FixtureError(f"mobile fixture {version!r} not found at {path}; available: {available}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("fixture_version") != version:
        raise FixtureError(
            f"fixture file {path} declares version {data.get('fixture_version')!r}, expected {version!r}"
        )
    auth = data.get("auth")
    if not isinstance(auth, dict) or not isinstance(auth.get("users"), list) or not auth["users"]:
        raise FixtureError(f"fixture {path} must define auth.users as a non-empty list")
    users = []
    for index, raw in enumerate(auth["users"]):
        if not isinstance(raw, dict):
            raise FixtureError(f"fixture {path} user #{index} must be an object")
        uid = raw.get("uid")
        email = raw.get("email")
        if not isinstance(uid, str) or not uid.strip() or "@" in uid or ":" in uid:
            raise FixtureError(f"fixture {path} user #{index} has an invalid uid {uid!r}")
        if not isinstance(email, str) or "@" not in email:
            raise FixtureError(f"fixture {path} user #{index} has an invalid email {email!r}")
        if not email.lower().endswith("@local.test"):
            # Synthetic-only guarantee: fixture identities are RFC-reserved and
            # can never collide with a real account.
            raise FixtureError(f"fixture {path} user #{index} email must end in @local.test, got {email!r}")
        users.append(
            FixtureUser(
                uid=uid,
                email=email,
                display_name=str(raw.get("display_name") or uid),
                email_verified=bool(raw.get("email_verified", True)),
            )
        )
    index = auth.get("default_user_index", 0)
    if not isinstance(index, int) or not 0 <= index < len(users):
        raise FixtureError(f"fixture {path} default_user_index {index!r} out of range")
    return MobileFixture(version=version, users=tuple(users), default_user_index=index)


# ---------------------------------------------------------------------------
# Seeding (fail-closed egress; receipts never contain the minted token)
# ---------------------------------------------------------------------------


def backend_endpoint(backend_base_url: str, path: str = LOCAL_DEV_CUSTOM_TOKEN_PATH) -> str:
    base = backend_base_url.rstrip("/")
    url = f"{base}{path}"
    validate_local_http_url(url, what="session backend")
    return url


def seed_synthetic_user(
    backend_base_url: str,
    fixture: MobileFixture,
    *,
    user: FixtureUser | None = None,
    post: Callable[[str, Mapping[str, str]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Seed the fixture user through the #11784 local-dev token endpoint.

    ``post`` is injectable for tests; the production implementation performs
    one form-encoded POST and never persists the returned token.
    """

    target_user = user or fixture.default_user
    url = backend_endpoint(backend_base_url)
    if post is None:
        post = _form_post
    try:
        response = post(url, {"uid": target_user.uid, "email": target_user.email})
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise FixtureError(
                "session backend has no local-dev sign-in endpoint (404): it is only registered when the "
                "backend runs against a Firebase Auth emulator — start the session services first"
            ) from exc
        raise FixtureError(f"local-dev sign-in failed: HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise FixtureError(
            f"session backend at {url} is unreachable: {exc} — the session harness services must be running"
        ) from exc

    custom_token = response.get("custom_token")
    if not isinstance(custom_token, str) or not custom_token:
        raise FixtureError("local-dev sign-in returned no custom_token")
    returned_uid = response.get("uid")
    if returned_uid is not None and returned_uid != target_user.uid:
        raise FixtureError(f"local-dev sign-in minted a token for uid {returned_uid!r}, requested {target_user.uid!r}")

    # Receipt: identity and outcome only. The token itself is deliberately not
    # recorded anywhere — evidence documents must stay credential-free.
    return {
        "schema_version": 1,
        "fixture_version": fixture.version,
        "uid": target_user.uid,
        "email": target_user.email,
        "provider": "local_dev",
        "endpoint": url,
        "token_minted": True,
        "token_retained": False,
        "seeded_at": utc_now(),
    }


def _form_post(url: str, form: Mapping[str, str]) -> Mapping[str, Any]:
    from urllib.parse import urlencode

    request = urllib.request.Request(
        url,
        data=urlencode(dict(form)).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not isinstance(body, dict):
        raise FixtureError(f"{url} returned a non-object response")
    return body


def write_seed_receipt(path: Path, receipt: Mapping[str, Any]) -> Path:
    # Receipts are evidence: identity and outcome only — never credential-shaped
    # keys and never the minted token itself.
    for key in receipt:
        if _RECEIPT_SECRET_KEY_RE.search(str(key)):
            raise EvidenceError(f"seed receipt key {key!r} looks like a credential; receipts stay credential-free")
    if "custom_token" in receipt or "token" in receipt:
        raise EvidenceError("seed receipt must not contain the minted token")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def read_seed_receipt(path: Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise FixtureError(f"{path}: seed receipt must be a JSON object")
    return data
