"""Shared native-app / loopback redirect-URI validation (RFC 8252 style).

Originally lived only in routers/auth.py, guarding the OAuth authorization-code flow.
Extracted here so any other endpoint that hands a user-supplied "come back to this URL"
value to an untrusted redirect target (custom app deep links, webview callbacks, ...) can
reuse the same allow/deny policy instead of re-implementing it with different edge cases.
"""

from urllib.parse import urlparse

from fastapi import HTTPException

# Loopback hosts permitted for CLI/native-app OAuth flows per RFC 8252 §7.3.
LOOPBACK_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}

# Schemes that must NOT receive a sensitive redirect (OAuth code, session token, etc.):
#   - ``https``: would leak the value to an arbitrary remote host. (Loopback OAuth
#     is HTTP, not HTTPS, per RFC 8252.)
#   - ``javascript``, ``data``, ``vbscript``: browser-executable URLs. A value leaked
#     into one of these would be exfiltrated by the rendered page (also closes the
#     door on reflected-script injection via the redirect target itself).
#   - ``file``: local file URL — could end up read by another process.
#   - ``blob``, ``filesystem``, ``about``: browser-internal pseudo-schemes.
FORBIDDEN_REDIRECT_SCHEMES = {
    "https",
    "javascript",
    "data",
    "vbscript",
    "file",
    "blob",
    "filesystem",
    "about",
}

_ASCII_LETTERS = frozenset("abcdefghijklmnopqrstuvwxyz")
_ASCII_ALNUM = _ASCII_LETTERS | frozenset("0123456789")


def is_valid_scheme(scheme: str) -> bool:
    """RFC 3986 scheme validity check: ASCII ALPHA, then ASCII ALPHA/DIGIT/+/-/.

    We deliberately use explicit ASCII sets instead of ``str.isalpha`` /
    ``str.isalnum`` — those are Unicode-aware and would happily accept
    non-ASCII letters (``ñ``, ``й``, etc.) that RFC 3986 forbids in scheme names.
    """
    if not scheme:
        return False
    lowered = scheme.lower()
    if lowered[0] not in _ASCII_LETTERS:
        return False
    return all(c in _ASCII_ALNUM or c in "+-." for c in lowered)


def validate_redirect_uri(redirect_uri: str) -> None:
    """Reject redirect URIs that could deliver a sensitive value to an attacker.

    Allow:

    * **Custom app schemes** (``omi://``, ``omi-computer://``,
      ``omi-computer-dev://``, ``omi-fix-rewind://``, ``com.omi.app://``,
      etc.). The Omi mobile app, the macOS desktop app, and per-bundle
      developer test builds register their own URL schemes with the OS
      via ``CFBundleURLSchemes`` / Android intent filters; this is the
      standard native-app OAuth callback mechanism per RFC 8252.

    * **HTTP loopback** (``http://localhost[:PORT]/...``,
      ``http://127.0.0.1[:PORT]/...``, ``http://[::1][:PORT]/...``) for the
      CLI's loopback callback server.

    Reject:

    * **https://** and any other web-fetchable scheme — they could exfiltrate
      the value off-device.
    * **http://** to anything other than loopback.
    * Browser-executable schemes (``javascript:``, ``data:``, etc.).
    * Empty / unparseable input.

    Raises ``fastapi.HTTPException(400)`` on rejection.
    """
    if not redirect_uri:
        raise HTTPException(status_code=400, detail="redirect_uri is required")

    parsed = urlparse(redirect_uri)
    scheme = (parsed.scheme or "").strip().lower()

    if not scheme:
        raise HTTPException(status_code=400, detail="redirect_uri must include a scheme")

    if scheme == "http":
        hostname = (parsed.hostname or "").strip().lower()
        if hostname not in LOOPBACK_HOSTNAMES:
            raise HTTPException(
                status_code=400,
                detail="HTTP redirect_uri must point at loopback (localhost, 127.0.0.1, or ::1)",
            )
        return

    if scheme in FORBIDDEN_REDIRECT_SCHEMES:
        raise HTTPException(
            status_code=400,
            detail=f"redirect_uri scheme '{scheme}' is not permitted",
        )

    # Custom app scheme. Per RFC 3986, a scheme is
    # ``ALPHA *( ALPHA / DIGIT / "+" / "-" / "." )``. Be a little stricter
    # than urllib here — require the scheme to start with a letter and contain
    # only the RFC-allowed characters, so we don't accept garbage like ``://x``.
    if not is_valid_scheme(scheme):
        raise HTTPException(
            status_code=400,
            detail=f"redirect_uri scheme '{scheme}' is malformed",
        )

    return
