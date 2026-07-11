#!/usr/bin/env python3
"""INV-AUTH-1 ratchet: desktop 401 handlers must invalidate or opt out explicitly."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_CLIENT = ROOT / "desktop/macos/Desktop/Sources/APIClient.swift"
AUTH_SERVICE = ROOT / "desktop/macos/Desktop/Sources/AuthService.swift"
OMI_APP = ROOT / "desktop/macos/Desktop/Sources/OmiApp.swift"
CODEMAGIC = ROOT / "codemagic.yaml"
SIGNED_SMOKE = ROOT / "desktop/macos/scripts/smoke-signed-desktop-artifact.sh"

# Handlers that intentionally preserve the session on 401 (document each).
SESSION_PRESERVING_MARKERS = (
    "sessionPreserving",
    "// session-preserving",
)

UNAUTHORIZED_HANDLER = re.compile(r"statusCode\s*==\s*401|\.statusCode\s*==\s*401|http\.statusCode\s*==\s*401")
FUNC_RE = re.compile(
    r"(?:(?:public|private|internal|fileprivate|open)\s+)?(?:func|static\s+func)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:<[^>{}]*>)?\s*\("
)

# Shared helpers that own the session.data + 401 refresh/invalidate contract.
AUTH_OWNING_HELPERS = {
    "performAuthenticatedData",
    "performRealtimeMintRequest",
    "performMemoryListRequest",
}

SHARED_AUTH_PATH_MARKERS = (
    "performAuthenticatedData",
    "performVoidRequest",
    "performRequest",
    "performPatchRequest",
    "authorizedRetryRequest",
    "invalidateSessionAfterUnauthorized",
)


def _function_spans(text: str) -> list[tuple[str, int, int]]:
    """Return (name, start, end) spans for Swift funcs in APIClient."""
    matches = list(FUNC_RE.finditer(text))
    spans: list[tuple[str, int, int]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        spans.append((match.group(1), start, end))
    return spans


def _raw_session_data_bypasses(text: str) -> list[str]:
    """Catch authenticated APIClient methods that call session.data without the shared 401 path.

    The older ratchet only inspected explicit `statusCode == 401` branches, so
    methods that mapped every non-2xx to httpError never triggered it — leaving
    ghost sessions after Firebase death on those routes.
    """
    failures: list[str] = []
    for name, start, end in _function_spans(text):
        if name in AUTH_OWNING_HELPERS:
            continue
        body = text[start:end]
        if "session.data(for:" not in body:
            continue
        # Unauthenticated / external probes are out of INV-AUTH-1 scope.
        if "buildHeaders(requireAuth: true)" not in body and "buildHeaders(requireAuth: requireAuth)" not in body:
            if "buildHeaders(" not in body:
                continue
            if "requireAuth: false" in body and "requireAuth: true" not in body:
                continue
        if any(marker in body for marker in SHARED_AUTH_PATH_MARKERS):
            continue
        if any(marker in body for marker in SESSION_PRESERVING_MARKERS):
            continue
        line = text.count("\n", 0, start) + 1
        failures.append(
            f"authenticated method {name} near line {line} calls session.data without shared 401 recovery"
        )
    return failures


def main() -> int:
    if not API_CLIENT.is_file():
        print(f"check_desktop_auth_session: missing {API_CLIENT}")
        return 1

    text = API_CLIENT.read_text(encoding="utf-8")
    auth_text = AUTH_SERVICE.read_text(encoding="utf-8")
    app_text = OMI_APP.read_text(encoding="utf-8")
    codemagic_text = CODEMAGIC.read_text(encoding="utf-8")
    smoke_text = SIGNED_SMOKE.read_text(encoding="utf-8")
    failures: list[str] = []

    if "invalidateSessionAfterUnauthorized" not in text:
        failures.append("APIClient must define invalidateSessionAfterUnauthorized")

    if "AuthSessionCoordinator.shared.handleHTTPUnauthorized" not in text:
        failures.append("APIClient must route post-refresh 401 to AuthSessionCoordinator")

    if "AuthBackoffTracker" in text:
        failures.append("AuthBackoffTracker must not return — use session invalidation")

    if "self.isSignedIn = savedSignedIn" in app_text:
        failures.append("persisted auth boolean must remain a restore hint, not runtime auth authority")
    if "self.sessionPhase = savedSignedIn ? .restoring : .signedOut" not in app_text:
        failures.append("AuthState must gate saved sessions in restoring until validation")
    if "persistKeychainTokensTransactionally" not in auth_text:
        failures.append("Keychain persistence must use write + exact read-back verification")
    stored_tokens_start = auth_text.find("private func storedTokens()")
    stored_tokens_end = auth_text.find("private var storedIdToken", stored_tokens_start)
    if stored_tokens_start < 0 or stored_tokens_end < 0:
        failures.append("could not locate storedTokens migration implementation")
    elif "clearUserDefaultsTokens()" in auth_text[stored_tokens_start:stored_tokens_end]:
        failures.append("credential migration must not delete its legacy source before refresh commit")
    if "--auth-storage-canary" not in codemagic_text:
        failures.append("Codemagic must run the signed-app Keychain canary before publishing beta")
    if "run_auth_storage_canary" not in smoke_text:
        failures.append("signed artifact smoke must implement the in-app Keychain canary")

    # Each 401 branch must mention invalidation or an explicit session-preserving opt-out nearby.
    for match in UNAUTHORIZED_HANDLER.finditer(text):
        start = max(0, match.start() - 400)
        end = min(len(text), match.end() + 900)
        window = text[start:end]
        if "invalidateSessionAfterUnauthorized" in window:
            continue
        if "authorizedRetryRequest" in window:
            continue
        if any(marker in window for marker in SESSION_PRESERVING_MARKERS):
            continue
        line = text.count("\n", 0, match.start()) + 1
        failures.append(f"401 handler near line {line} lacks invalidation or session-preserving marker")

    failures.extend(_raw_session_data_bypasses(text))

    if failures:
        print("INV-AUTH-1 desktop auth session ratchet failed:")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("INV-AUTH-1 desktop auth session ratchet passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
