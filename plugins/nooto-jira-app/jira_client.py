"""Atlassian Jira Cloud REST API v3 helpers.

Slice C owns this file. Base URL pattern:

    https://api.atlassian.com/ex/jira/{cloudid}/rest/api/3/...

Every public function takes (cloudid, token, *, ...) so callers fetch the
cloud_id from db.get_jira_tokens(uid)["default_cloud_id"] and the token from
db.get_valid_access_token(uid).

HTTP wrapper raises:
    JiraAuthError  on 401  -> chat tool re-auth handler
    JiraNotFound   on 404  -> "issue/project not found"
    JiraRateLimit  on 429 after retries (exponential backoff 0.5s, 1s, 2 retries)
"""

import json
import logging
import re
import time
from typing import Any, Optional

import httpx

import db

log = logging.getLogger("nooto-jira-app.jira_client")


class JiraAuthError(Exception):
    pass


class JiraNotFound(Exception):
    pass


class JiraRateLimit(Exception):
    pass


# ── Redis cache (optional) ─────────────────────────────────────────────────


def _cache_get(key: str) -> Optional[Any]:
    r = db.get_redis()
    if not r:
        return None
    try:
        raw = r.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        log.warning("cache_get failed for %s: %s", key, e)
        return None


def _cache_set(key: str, value: Any, ttl: int) -> None:
    r = db.get_redis()
    if not r:
        return
    try:
        r.setex(key, ttl, json.dumps(value))
    except Exception as e:
        log.warning("cache_set failed for %s: %s", key, e)


# ── Constants ──────────────────────────────────────────────────────────────

_API_BASE = "https://api.atlassian.com/ex/jira/{cloudid}/rest/api/3"
_ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")


def _base(cloudid: str) -> str:
    return _API_BASE.format(cloudid=cloudid)


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _request(
    method: str,
    url: str,
    token: str,
    *,
    json_body: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
) -> httpx.Response:
    """HTTP wrapper with 401/404/429 mapping and exponential backoff on 429."""
    backoffs = [0.5, 1.0]
    last_429: Optional[httpx.Response] = None
    client = db.get_http_client()
    for attempt in range(len(backoffs) + 1):
        try:
            resp = client.request(method, url, headers=_headers(token), json=json_body, params=params)
        except httpx.RequestError as e:
            log.warning("Jira HTTP error %s %s: %s", method, url, e)
            raise

        if resp.status_code == 401:
            raise JiraAuthError(f"Jira 401 on {method} {url}")
        if resp.status_code == 404:
            raise JiraNotFound(f"Jira 404 on {method} {url}")
        if resp.status_code == 429:
            last_429 = resp
            if attempt < len(backoffs):
                time.sleep(backoffs[attempt])
                continue
            raise JiraRateLimit(f"Jira 429 on {method} {url} after {len(backoffs)} retries")

        if resp.status_code >= 400:
            resp.raise_for_status()

        return resp

    # Should not reach here, but for type completeness
    if last_429 is not None:
        raise JiraRateLimit(f"Jira 429 on {method} {url}")
    raise RuntimeError("unreachable")


# ── Helpers ────────────────────────────────────────────────────────────────


def text_to_adf(text: str) -> dict[str, Any]:
    """Convert plain text to minimal Atlassian Document Format. Splits on \\n."""
    paragraphs = [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": line}] if line else [],
        }
        for line in (text or "").split("\n")
    ]
    if not paragraphs:
        paragraphs = [{"type": "paragraph", "content": []}]
    return {"version": 1, "type": "doc", "content": paragraphs}


_JQL_RESERVED = {"and", "or", "not", "empty", "null", "order", "by"}


def jql_escape(s: str) -> str:
    """Sanitize free-text for the JQL `text ~ "..."` operator.

    - Collapses whitespace, escapes \\\\ and \\\".
    - Drops reserved JQL words (and, or, not, empty, null, order, by).
    - Caps at 200 chars.
    """
    s = (s or "").replace("\\", "\\\\").replace('"', '\\"')
    s = re.sub(r"[\r\n\t]+", " ", s).strip()
    tokens = [t for t in s.split() if t.lower() not in _JQL_RESERVED]
    return " ".join(tokens)[:200]


def _validate_issue_key(key: str) -> str:
    if not key or not _ISSUE_KEY_RE.match(key):
        raise ValueError(f"Invalid Jira issue key: {key!r}")
    return key


# ── REST endpoints ─────────────────────────────────────────────────────────


def create_issue(
    cloudid: str,
    token: str,
    *,
    project_key: str,
    summary: str,
    description_adf: dict[str, Any],
    issue_type: str = "Task",
    priority: Optional[str] = None,
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "project": {"key": project_key},
        "summary": summary,
        "description": description_adf,
        "issuetype": {"name": issue_type},
    }
    if priority:
        fields["priority"] = {"name": priority}

    resp = _request("POST", f"{_base(cloudid)}/issue", token, json_body={"fields": fields})
    return resp.json()


def search_jql(
    cloudid: str,
    token: str,
    *,
    jql: str,
    fields: list[str],
    max_results: int = 20,
) -> dict[str, Any]:
    body = {"jql": jql, "fields": fields, "maxResults": max_results}
    resp = _request("POST", f"{_base(cloudid)}/search/jql", token, json_body=body)
    return resp.json()


def get_issue(
    cloudid: str,
    token: str,
    *,
    key: str,
    fields: Optional[list[str]] = None,
) -> dict[str, Any]:
    _validate_issue_key(key)
    params: Optional[dict[str, Any]] = None
    if fields:
        params = {"fields": ",".join(fields)}
    resp = _request("GET", f"{_base(cloudid)}/issue/{key}", token, params=params)
    return resp.json()


def list_transitions(
    cloudid: str,
    token: str,
    *,
    key: str,
    _cache_uid: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Cached 5m per (uid, key)."""
    _validate_issue_key(key)
    cache_key = f"jira:transitions:{_cache_uid}:{key}" if _cache_uid else None
    if cache_key:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    resp = _request("GET", f"{_base(cloudid)}/issue/{key}/transitions", token)
    transitions = resp.json().get("transitions", []) or []
    if cache_key:
        _cache_set(cache_key, transitions, 300)
    return transitions


def transition_issue(
    cloudid: str,
    token: str,
    *,
    key: str,
    transition_id: str,
    _cache_uid: Optional[str] = None,
) -> None:
    _validate_issue_key(key)
    _request(
        "POST",
        f"{_base(cloudid)}/issue/{key}/transitions",
        token,
        json_body={"transition": {"id": transition_id}},
    )
    # Invalidate the single-key transitions cache when we know the uid.
    if _cache_uid:
        r = db.get_redis()
        if r:
            try:
                r.delete(f"jira:transitions:{_cache_uid}:{key}")
            except Exception:
                pass


def add_comment(cloudid: str, token: str, *, key: str, body_adf: dict[str, Any]) -> dict[str, Any]:
    _validate_issue_key(key)
    resp = _request(
        "POST",
        f"{_base(cloudid)}/issue/{key}/comment",
        token,
        json_body={"body": body_adf},
    )
    return resp.json()


def list_projects(
    cloudid: str,
    token: str,
    *,
    query: Optional[str] = None,
    _cache_uid: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Cached 1h per uid (only when no `query` is provided)."""
    cache_key = None
    if _cache_uid and not query:
        cache_key = f"jira:projects:{_cache_uid}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    params: dict[str, Any] = {"maxResults": 50}
    if query:
        params["query"] = query

    resp = _request("GET", f"{_base(cloudid)}/project/search", token, params=params)
    values = resp.json().get("values", []) or []
    if cache_key:
        _cache_set(cache_key, values, 3600)
    return values


def current_user(
    cloudid: str,
    token: str,
    *,
    _cache_uid: Optional[str] = None,
) -> dict[str, Any]:
    """Cached 30m per uid."""
    cache_key = f"jira:myself:{_cache_uid}" if _cache_uid else None
    if cache_key:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    resp = _request("GET", f"{_base(cloudid)}/myself", token)
    user = resp.json()
    if cache_key:
        _cache_set(cache_key, user, 1800)
    return user


def transition_to_named_status(
    cloudid: str,
    token: str,
    key: str,
    target_name: str,
) -> tuple[bool, list[str]]:
    """Resolve transition by name (case-insensitive on `name` and `to.name`).

    Returns (True, []) on success, (False, [available_transition_names]) on miss.
    """
    _validate_issue_key(key)
    transitions = list_transitions(cloudid, token, key=key)
    target_lc = (target_name or "").strip().lower()
    available: list[str] = []
    for tr in transitions:
        name = (tr.get("name") or "").strip()
        to_name = ((tr.get("to") or {}).get("name") or "").strip()
        # Prefer the destination state name as the user-facing label.
        label = to_name or name
        if label:
            available.append(label)
        if name.lower() == target_lc or to_name.lower() == target_lc:
            tr_id = tr.get("id")
            if tr_id:
                transition_issue(cloudid, token, key=key, transition_id=str(tr_id))
                return True, []
    return False, available
