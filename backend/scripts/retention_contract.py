"""Audio-bucket retention contract: floors (holds) and ceilings, from storage-lifecycle/retention_contract.json.

Pure functions over bucket metadata; no cloud access. The release prerequisite
(check_sync_staging_lifecycle.py) and the workspace drift/retention tools read the
same JSON, so a threshold changes in one reviewed place.

Floor: every lifecycle Delete that can reach a protected prefix has
age >= max(hold days) + margin_days. A hold with days=null, a pending ruling,
or a bound that depends on a control not yet verified (control_verified false)
is unbounded: no age Delete may reach that prefix. Deletes that only remove
noncurrent generations keep the live object and are allowed.

Ceiling: soft delete, versioning, noncurrent cleanup and cache max ages a
bucket may not exceed. A ceiling whose ruling is pending reports with a
`:pending` suffix.
"""

import json
from pathlib import Path
from typing import Any

CONTRACT_PATH = Path(__file__).resolve().parents[1] / 'deploy' / 'storage-lifecycle' / 'retention_contract.json'


def load(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def _pending(hold: dict[str, Any], accept_pending: bool = False) -> bool:
    """Not yet a bound: the hold names a control that is not explicitly verified (missing or null fails closed), or
    the ruling is pending. accept_pending asks "would a pending ruling fit?"; it never waives an unverified control."""
    unverified = ('control' in hold or 'control_verified' in hold) and hold.get('control_verified') is not True
    return unverified or (hold.get('ruling') == 'pending' and not accept_pending)


def required_days(contract: dict[str, Any], bucket: str, accept_pending: bool = False) -> float | None:
    holds = [contract['holds'][name] for name in contract['buckets'][bucket]['holds']]
    if any(h['days'] is None or _pending(h, accept_pending) for h in holds):
        return None
    return max(h['days'] for h in holds) + contract['margin_days']


def _rules(lifecycle: Any) -> list[dict[str, Any]]:
    rules = (lifecycle or {}).get('rule') or [] if isinstance(lifecycle, dict) else []
    return [r for r in rules if isinstance(r, dict) and isinstance(r.get('action'), dict)]


def _noncurrent_only(condition: dict[str, Any]) -> bool:
    """True only for conditions GCS can never match on a live object. A live object has zero newer versions, so
    numNewerVersions counts only when >= 1; daysSinceNoncurrentTime and noncurrentTimeBefore apply to noncurrent
    generations only."""
    newer = condition.get('numNewerVersions')
    return (
        condition.get('isLive') is False
        or (isinstance(newer, int) and not isinstance(newer, bool) and newer >= 1)
        or 'daysSinceNoncurrentTime' in condition
        or 'noncurrentTimeBefore' in condition
    )


# A cache max-age rule covers a prefix only when nothing else narrows it: GCS requires every condition to match.
_COVERING_KEYS = frozenset({'age', 'matchesPrefix'})


def _reaches(rule_prefixes: list[str], prefixes: list[str]) -> bool:
    """No rule prefix matches every object; otherwise prefixes overlap when one starts with the other."""
    return not rule_prefixes or any(p.startswith(q) or q.startswith(p) for p in rule_prefixes for q in prefixes)


def floor_violations(
    contract: dict[str, Any], bucket: str, lifecycle: Any, accept_pending: bool = False
) -> list[dict[str, Any]]:
    """Live-object Delete rules that can reach a protected prefix sooner than the longest hold allows."""
    need = required_days(contract, bucket, accept_pending)
    spec = contract['buckets'][bucket]
    pending = [h for h in spec['holds'] if _pending(contract['holds'][h], accept_pending)]
    out = []
    for rule in _rules(lifecycle):
        condition = rule.get('condition') or {}
        if rule['action'].get('type') != 'Delete' or _noncurrent_only(condition):
            continue
        if not _reaches(condition.get('matchesPrefix') or [], spec['protected_prefixes']):
            continue
        age = condition.get('age')
        if need is None:
            out.append({'age': age, 'required': None, 'pending': pending})
        elif not isinstance(age, (int, float)) or age < need:
            out.append({'age': age, 'required': need, 'pending': []})
    return out


def ceiling_findings(contract: dict[str, Any], bucket: str, metadata: dict[str, Any]) -> list[str]:
    """Reason codes (no prefixes or names) where live policy exceeds the bucket's ceiling."""
    ceiling = contract['buckets'][bucket].get('ceiling') or {}
    suffix = ':pending' if ceiling.get('ruling') == 'pending' else ''
    rules = _rules(metadata.get('lifecycle'))
    out = []
    soft = metadata.get('soft_delete_seconds')
    if 'soft_delete_seconds_max' in ceiling:
        if soft is None:
            out.append('ceiling_soft_delete_unknown' + suffix)
        elif int(soft) > ceiling['soft_delete_seconds_max']:
            out.append('ceiling_soft_delete' + suffix)
    versioning = metadata.get('versioning')
    if ceiling.get('versioning') is False and versioning:
        out.append('ceiling_versioning' + suffix)
    if (
        ceiling.get('noncurrent_cleanup')
        and versioning
        and not any(r['action'].get('type') == 'Delete' and _noncurrent_only(r.get('condition') or {}) for r in rules)
    ):
        out.append('ceiling_noncurrent_unbounded' + suffix)
    # A retention ceiling must not invent an expiry for live voice of an active
    # account. A lifecycle rule cannot distinguish active from deleted accounts;
    # explicit user/account erasure is handled by the reviewed deletion path.
    retained = ceiling.get('retain_until_user_deletes') or []
    if retained and any(
        r['action'].get('type') == 'Delete'
        and not _noncurrent_only(r.get('condition') or {})
        and _reaches((r.get('condition') or {}).get('matchesPrefix') or [], retained)
        for r in rules
    ):
        # This ratified rule is independent of older pending ceilings on the bucket.
        out.append('ceiling_user_content_expiry')
    for prefix, max_age in (ceiling.get('max_age_days') or {}).items():
        covered = any(
            r['action'].get('type') == 'Delete'
            and set(r.get('condition') or {}) <= _COVERING_KEYS
            and isinstance((r.get('condition') or {}).get('age'), (int, float))
            and r['condition']['age'] <= max_age
            and (
                not (r['condition'].get('matchesPrefix') or [])
                or any(prefix.startswith(p) for p in r['condition']['matchesPrefix'])
            )
            for r in rules
        )
        if not covered:
            out.append('ceiling_max_age' + suffix)
    return out
