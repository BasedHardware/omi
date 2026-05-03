"""HTTP client for the Omi developer API.

This is the single surface every command goes through. It owns:

* Bearer-token injection from the active :class:`omi_cli.config.Profile`.
* Retry/backoff for ``429`` and ``5xx`` responses, honoring ``Retry-After`` when
  the server provides one.
* Translating non-2xx responses into the :mod:`omi_cli.errors` hierarchy so the
  call sites just see a clean exception.
* Sniffing the rate-limit policy from the response body so the user gets a
  useful message instead of a bare ``429``.

The client is sync (httpx ``Client``, not ``AsyncClient``) — Typer commands run
synchronously and the I/O is one request at a time. The complexity of an event
loop here would buy nothing.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterator, Mapping, Optional

import httpx
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from omi_cli import __version__
from omi_cli.config import Profile
from omi_cli.errors import CliError, RateLimitError, ServerError, from_status

USER_AGENT = f"omi-cli/{__version__} (+https://github.com/BasedHardware/omi)"
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
MAX_RETRY_ATTEMPTS = 4
# Cap on how long we'll honor a server-supplied Retry-After hint. Without this,
# a misconfigured upstream could pin the CLI for hours; agents will get a
# RateLimitError they can act on much sooner.
MAX_RETRY_AFTER_SECONDS = 60.0

# Backend rate-limit policies surfaced to users on 429 (see
# ``backend/utils/rate_limit_config.py``).
KNOWN_RATE_LIMIT_POLICIES = {
    "dev:conversations": "25/hr",
    "dev:memories": "120/hr",
    "dev:memories_batch": "15/hr",
}


class OmiClient:
    """Thin wrapper around :class:`httpx.Client`. One per CLI invocation."""

    def __init__(self, profile: Profile, *, timeout: Optional[httpx.Timeout] = None, verbose: bool = False) -> None:
        # Pre-flight: if this is an OAuth profile and the cached Firebase ID
        # token is expired (or close to it), refresh before we build the bearer
        # header so the very first request goes out with a fresh token.
        # ``omi_cli.auth.oauth`` is imported lazily because it pulls in
        # ``http.server`` / ``socketserver`` which we don't need for the more
        # common API-key path.
        if profile.auth_method == "oauth":
            from omi_cli.auth import oauth as oauth_auth  # local to avoid import cost on api_key path

            if oauth_auth.needs_refresh(profile):
                new_id_token = oauth_auth.refresh_id_token(profile.name)
                # Mutate the in-memory profile so _build_headers picks up the
                # new token without re-reading the config file.
                profile.id_token = new_id_token

        self._profile = profile
        self._verbose = verbose
        self._http = httpx.Client(
            base_url=profile.api_base.rstrip("/"),
            headers=self._build_headers(profile),
            timeout=timeout or DEFAULT_TIMEOUT,
            follow_redirects=False,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "OmiClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Verb shims
    # ------------------------------------------------------------------

    def get(self, path: str, *, params: Optional[Mapping[str, Any]] = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, *, json_body: Optional[Mapping[str, Any]] = None) -> Any:
        return self._request("POST", path, json_body=json_body)

    def patch(
        self,
        path: str,
        *,
        json_body: Optional[Mapping[str, Any]] = None,
        params: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        return self._request("PATCH", path, json_body=json_body, params=params)

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json_body: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        """Execute an HTTP request with retry, returning the parsed JSON body (or None for 204)."""
        # Filter ``None`` out of params so callers can pass optional fields
        # without sentinel checks.
        cleaned_params = {k: v for k, v in (params or {}).items() if v is not None} or None

        retrying = Retrying(
            reraise=True,
            stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
            # Honor server-supplied Retry-After when present, otherwise fall
            # back to exponential jitter. See ``_retry_wait`` for the logic.
            wait=_retry_wait,
            retry=retry_if_exception_type((httpx.TransportError, _RetryableHttp)),
        )

        try:
            for attempt in retrying:
                with attempt:
                    response = self._http.request(method, path, params=cleaned_params, json=json_body)
                    self._maybe_log(method, path, response)
                    if response.status_code >= 500:
                        raise _RetryableHttp(response, retry_after=None)
                    if response.status_code == 429:
                        # Surface the structured RateLimitError so callers can show
                        # a useful message; tenacity treats this as retryable.
                        raise _RetryableHttp(
                            response,
                            retry_after=_parse_retry_after(response.headers.get("Retry-After")),
                        )
                    return self._handle_response(response)
        except _RetryableHttp as exc:
            # We exhausted retries — convert to the proper CliError now.
            raise self._error_from_response(exc.response)
        # Unreachable — Retrying always either returns or raises — but the type
        # checker doesn't know that.
        raise RuntimeError("unreachable")

    def _handle_response(self, response: httpx.Response) -> Any:
        if response.status_code == 204 or not response.content:
            return None
        if 200 <= response.status_code < 300:
            return _safe_parse_json(response)
        raise self._error_from_response(response)

    def _error_from_response(self, response: httpx.Response) -> CliError:
        detail = _extract_detail(response)
        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        policy = _detect_rate_limit_policy(detail)
        # Server errors and rate limit errors get the richer formatters below.
        if response.status_code == 429:
            policy_label = KNOWN_RATE_LIMIT_POLICIES.get(policy, policy) if policy else None
            label = f"{policy} ({policy_label})" if policy_label else policy
            return RateLimitError(
                message="Rate limited" if not label else f"Rate limited: {label}",
                detail=_format_rate_limit_detail(retry_after, detail),
                retry_after_seconds=retry_after,
                policy=policy,
            )
        if 500 <= response.status_code < 600:
            return ServerError(
                message=f"Server error ({response.status_code})",
                detail=detail or "The Omi API returned an error. Try again, then check status.omi.me.",
            )
        return from_status(response.status_code, detail=detail, retry_after=retry_after, policy=policy)

    def _maybe_log(self, method: str, path: str, response: httpx.Response) -> None:
        if not self._verbose:
            return
        # Use stderr via direct sys.stderr.write to avoid pulling Renderer in here.
        import sys

        sys.stderr.write(
            f"[debug] {method} {path} → {response.status_code} ({response.elapsed.total_seconds():.2f}s)\n"
        )

    @staticmethod
    def _build_headers(profile: Profile) -> dict[str, str]:
        if not profile.is_authenticated():
            raise CliError(
                message="Not authenticated",
                detail="Run `omi auth login` and paste your dev API key. (See `omi auth login --help`.)",
                exit_code=2,
            )
        if profile.auth_method == "api_key":
            assert profile.api_key  # narrowed by is_authenticated
            token = profile.api_key
        else:
            assert profile.id_token
            token = profile.id_token
        return {
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _RetryableHttp(Exception):
    """Internal sentinel: a retryable HTTP response (5xx or 429).

    ``retry_after`` is populated for 429s when the server sent a ``Retry-After``
    header — the wait function reads it to honor the server's hint.
    """

    def __init__(self, response: httpx.Response, *, retry_after: Optional[float] = None) -> None:
        super().__init__(f"retryable HTTP {response.status_code}")
        self.response = response
        self.retry_after = retry_after


# Module-level wait function so tenacity's introspection (and tests) can find it.
_jittered_backoff = wait_exponential_jitter(initial=0.5, max=8.0)


def _retry_wait(retry_state: RetryCallState) -> float:
    """Wait strategy: server-supplied Retry-After when available, jitter otherwise.

    A 429 that includes ``Retry-After`` ends up here as a ``_RetryableHttp``
    with ``retry_after`` populated. We honor it but cap to
    :data:`MAX_RETRY_AFTER_SECONDS` so a pathological upstream can't pin the
    CLI for an unbounded time. For 5xx (no ``Retry-After`` from this backend)
    and transport errors we fall back to exponential jitter — same behavior
    the client had before this fix.
    """
    outcome = retry_state.outcome
    exc = outcome.exception() if outcome is not None and outcome.failed else None
    if isinstance(exc, _RetryableHttp) and exc.retry_after is not None and exc.retry_after > 0:
        return min(exc.retry_after, MAX_RETRY_AFTER_SECONDS)
    return float(_jittered_backoff(retry_state))


def _safe_parse_json(response: httpx.Response) -> Any:
    """Parse JSON, falling back to raw text if the body isn't valid JSON.

    This handles edge cases where the backend returns a plain-text error body
    despite a 2xx status (rare, but real for some endpoints).
    """
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError):
        return response.text


def _extract_detail(response: httpx.Response) -> Optional[str]:
    """Pull a human-readable error string out of a response body.

    FastAPI conventionally returns ``{"detail": "..."}`` — handle that, while
    tolerating arbitrary body shapes.
    """
    try:
        body = response.json()
    except (json.JSONDecodeError, ValueError):
        text = response.text.strip()
        return text[:500] if text else None
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, list):
            # FastAPI validation errors come back as a list of dicts.
            return "; ".join(_format_validation_error(e) for e in detail)
        if detail is not None:
            return json.dumps(detail)
        msg = body.get("message")
        if isinstance(msg, str):
            return msg
    return None


def _format_validation_error(entry: Any) -> str:
    if not isinstance(entry, dict):
        return str(entry)
    loc = entry.get("loc")
    msg = entry.get("msg") or entry.get("message")
    if loc and msg:
        return f"{'.'.join(str(p) for p in loc)}: {msg}"
    return str(msg or entry)


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    """Parse the Retry-After header. Supports the seconds form only — that's what FastAPI emits."""
    if not value:
        return None
    try:
        return max(0.0, float(value.strip()))
    except ValueError:
        return None


_POLICY_RE = re.compile(r"(dev:[a-zA-Z_]+)")


def _detect_rate_limit_policy(detail: Optional[str]) -> Optional[str]:
    if not detail:
        return None
    match = _POLICY_RE.search(detail)
    return match.group(1) if match else None


def _format_rate_limit_detail(retry_after: Optional[float], detail: Optional[str]) -> str:
    parts = []
    if retry_after is not None and retry_after > 0:
        parts.append(f"Retry in {retry_after:.0f}s.")
    if detail:
        parts.append(detail)
    return " ".join(parts) if parts else "Slow down and retry shortly."


def chunked(seq: list[Any], size: int) -> Iterator[list[Any]]:
    """Yield successive chunks of ``size`` items from ``seq``. Used by batch commands."""
    if size <= 0:
        raise ValueError("size must be positive")
    for i in range(0, len(seq), size):
        yield seq[i : i + size]
