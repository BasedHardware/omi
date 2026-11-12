"""Bounded lifecycle for versions temporarily hidden during store review.

The app-review reader deliberately remains unaware of the metadata written here:
only ``hidden_versions`` is part of its serving contract. Metadata records who
owns each temporary hide and when it expires. A submission adopts a matching
pre-existing hide, and live or expired leases remove that exact version while
unmatched legacy hides remain untouched.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import google.auth
import jwt
import requests
from google.auth.transport.requests import AuthorizedSession
from google.cloud import firestore

from database._client import db, run_transactional
from database.announcements import compare_versions
from database.cache import get_memory_cache
from utils.metrics import (
    OMI_APP_REVIEW_CONFIG_ALERT_TOTAL,
    OMI_APP_REVIEW_CONFIG_LAST_ALERT_TIMESTAMP,
    OMI_APP_REVIEW_CONFIG_LAST_SWEEP_TIMESTAMP,
    OMI_APP_REVIEW_CONFIG_SWEEP_TOTAL,
)
from utils.observability.reasons import (
    AppReviewConfigOutcome,
    AppReviewConfigReason,
    ReasonFamily,
    reason_label,
)

logger = logging.getLogger(__name__)

PROJECT_ID = 'based-hardware'
APPLE_APP_ID = '6502156163'
ANDROID_PACKAGE = 'com.friend.ios'
APPLE_API = 'https://api.appstoreconnect.apple.com/v1'
PLAY_API = 'https://androidpublisher.googleapis.com/androidpublisher/v3/applications'
APPLE_REVIEW_STATES = frozenset({'WAITING_FOR_REVIEW', 'IN_REVIEW'})
APPLE_CLEAR_STATES = frozenset({'PENDING_DEVELOPER_RELEASE', 'READY_FOR_SALE', 'REJECTED'})
DEFAULT_TTL = timedelta(days=14)
SECRET_NAMES = {
    'submission': 'APP_REVIEW_CONFIG_SUBMISSION_TOKEN',
    'apple': 'APP_REVIEW_ASC_API_KEY_JSON',
    'play': 'APP_REVIEW_PLAY_SERVICE_ACCOUNT_JSON',
}
PLATFORMS = ('ios', 'android')
_CACHE_KEY_PREFIX = 'app_review_config:'
_VISIBLE_VERSION_PATTERN = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:\+[0-9]+)?$")
_PLAY_RELEASE_NAME_VERSION_PATTERN = re.compile(
    r"^\s*v?((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))(?=$|[\s(\[+])"
)
SUBMISSION_SECRET_CACHE_TTL_SECONDS = 60
_submission_secret_cache_lock = threading.Lock()
_submission_secret_cache: tuple[str | None, float] | None = None


class StoreCredentialsUnavailable(RuntimeError):
    """A configured read-only store credential could not be loaded."""


class SubmissionConfigConflict(RuntimeError):
    """The submission receipt could not be associated with an active lease."""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def is_recent_submission_timestamp(value: datetime, *, now: datetime | None = None) -> bool:
    if value.tzinfo is None or value.utcoffset() is None:
        return False
    age = (now or _now_utc()) - value.astimezone(timezone.utc)
    return timedelta(minutes=-5) <= age <= timedelta(minutes=15)


def _entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    raw = config.get('review_submission_entries')
    return [dict(row) for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []


def _hidden(config: dict[str, Any]) -> list[Any]:
    raw = config.get('hidden_versions')
    return list(raw) if isinstance(raw, list) else []


def _same_visible_version(candidate: object, version: str) -> bool:
    """Match hidden versions exactly as the serving reader matches builds."""
    if not isinstance(candidate, str):
        return False
    candidate = candidate.strip()
    version = version.strip()
    if candidate == version:
        return True
    if not _VISIBLE_VERSION_PATTERN.fullmatch(candidate) or not _VISIBLE_VERSION_PATTERN.fullmatch(version):
        return False
    return compare_versions(candidate, version) == 0


def _append_hidden(hidden: list[Any], version: str) -> bool:
    if any(_same_visible_version(item, version) for item in hidden):
        return False
    hidden.append(version)
    return True


def _remove_review_hidden(hidden: list[Any], entry: dict[str, Any]) -> bool:
    version = entry.get('version')
    if not isinstance(version, str):
        return False
    before = len(hidden)
    hidden[:] = [item for item in hidden if not _same_visible_version(item, version)]
    return len(hidden) != before


def record_submission_config(
    config: dict[str, Any],
    *,
    platform: str,
    version: str,
    version_code: str | None,
    now: datetime,
) -> dict[str, Any]:
    """Add/refresh one temporary hide while preserving all unrelated fields."""
    hidden = _hidden(config)
    entries = _entries(config)
    previous = next(
        (
            entry
            for entry in reversed(entries)
            if entry.get('platform') == platform and entry.get('version') == version and entry.get('state') == 'active'
        ),
        None,
    )
    if previous is not None:
        previous_deadline = _parse_time(previous.get('expires_at'))
        if previous_deadline is None or previous_deadline <= now:
            # A fresh, authenticated receipt can race the expiry sweep. Do not
            # adopt an already-dead lease: the next sweep would tombstone it
            # again and the expired tombstone would suppress reconciliation.
            previous = None
    # A recorded submission adopts an already-hidden version. This lets the
    # lease expiry and store-terminal paths release legacy/manual hides too.
    _append_hidden(hidden, version)
    entries = [
        entry for entry in entries if not (entry.get('platform') == platform and entry.get('version') == version)
    ]
    row: dict[str, Any] = (
        dict(previous)
        if previous is not None
        else {
            'platform': platform,
            'version': version,
            'submitted_at': _iso(now),
            'expires_at': _iso(now + DEFAULT_TTL),
            'state': 'active',
            'source': 'submission',
        }
    )
    # Replayed receipts for an active lease must not extend its deadline.
    row["owns_hidden_version"] = True
    if version_code is not None:
        row['version_code'] = version_code
    entries.append(row)
    result = dict(config)
    result['hidden_versions'] = hidden
    result['review_submission_entries'] = entries
    return result


def expire_config_entries(config: dict[str, Any], *, now: datetime) -> tuple[dict[str, Any], int]:
    """Expire active TTLs; keep tombstones to prevent L4 re-hiding a long review."""
    hidden = _hidden(config)
    entries = _entries(config)
    expired = 0
    for entry in entries:
        if entry.get('state') != 'active':
            continue
        deadline = _parse_time(entry.get('expires_at'))
        if deadline is not None and deadline > now:
            continue
        _remove_review_hidden(hidden, entry)
        entry['state'] = 'expired'
        expired += 1
    if not expired:
        return config, 0
    result = dict(config)
    result['hidden_versions'] = hidden
    result['review_submission_entries'] = entries
    return result, expired


def reconcile_ios_config(
    config: dict[str, Any], *, version_states: dict[str, str], now: datetime
) -> tuple[dict[str, Any], int, int]:
    """Apply ASC state and repair missing review hides. Returns config, repairs, clears."""
    result = dict(config)
    hidden = _hidden(config)
    entries = _entries(config)
    repairs = 0
    clears = 0

    for version, state in version_states.items():
        matching = [entry for entry in entries if entry.get('platform') == 'ios' and entry.get('version') == version]
        if state in APPLE_CLEAR_STATES:
            before_hidden = any(_same_visible_version(item, version) for item in hidden)
            hidden[:] = [item for item in hidden if not _same_visible_version(item, version)]
            kept = []
            for entry in entries:
                if entry.get('platform') == 'ios' and entry.get('version') == version:
                    continue
                kept.append(entry)
            entries = kept
            if before_hidden:
                clears += 1
            continue

        if state not in APPLE_REVIEW_STATES:
            continue
        active = next((entry for entry in matching if entry.get('state') == 'active'), None)
        tombstone = any(entry.get('state') == 'expired' for entry in matching)
        if active is not None:
            active["owns_hidden_version"] = True
            if _append_hidden(hidden, version):
                repairs += 1
            continue
        if tombstone:
            continue

        _append_hidden(hidden, version)
        entries.append(
            {
                'platform': 'ios',
                'version': version,
                'submitted_at': _iso(now),
                'expires_at': _iso(now + DEFAULT_TTL),
                'state': 'active',
                'owns_hidden_version': True,
                'source': 'reconciliation',
            }
        )
        repairs += 1

    if hidden != _hidden(config) or entries != _entries(config):
        result['hidden_versions'] = hidden
        result['review_submission_entries'] = entries
    return result, repairs, clears


def reconcile_android_config(
    config: dict[str, Any],
    *,
    production_codes: set[str],
    pending_versions_by_code: dict[str, str] | None = None,
    now: datetime | None = None,
) -> tuple[dict[str, Any], int, int]:
    """Create first-sight hides and clear entries once production is completed."""
    hidden = _hidden(config)
    entries = _entries(config)
    repaired = 0
    clears = 0

    # A missing receipt must not leave a held/draft/in-progress production
    # release visible. Create a bounded lease once, while preserving expired
    # tombstones so a sweep cannot silently re-arm a version after its lease.
    for code, version in (pending_versions_by_code or {}).items():
        same_version = [
            entry
            for entry in entries
            if entry.get('platform') == 'android'
            and isinstance(entry.get('version'), str)
            and _same_visible_version(entry['version'], version)
        ]
        if any(entry.get('state') == 'active' for entry in same_version):
            continue
        if any(entry.get('state') == 'expired' for entry in same_version):
            continue
        _append_hidden(hidden, version)
        current = now or _now_utc()
        entries.append(
            {
                'platform': 'android',
                'version': version,
                'version_code': code,
                'submitted_at': _iso(current),
                'expires_at': _iso(current + DEFAULT_TTL),
                'state': 'active',
                'owns_hidden_version': True,
                'source': 'reconciliation',
            }
        )
        repaired += 1

    kept: list[dict[str, Any]] = []
    for entry in entries:
        code = entry.get('version_code')
        if entry.get('platform') == 'android' and isinstance(code, str) and code in production_codes:
            version = entry.get('version')
            was_hidden = isinstance(version, str) and any(_same_visible_version(item, version) for item in hidden)
            if isinstance(version, str):
                hidden[:] = [item for item in hidden if not _same_visible_version(item, version)]
            if was_hidden and isinstance(version, str):
                clears += 1
            continue
        # L1 records are authoritative for a submitted version even if an
        # operator removed its visible hide field before the next sweep.
        if entry.get('platform') == 'android' and entry.get('state') == 'active':
            version = entry.get('version')
            if isinstance(version, str):
                entry["owns_hidden_version"] = True
                if _append_hidden(hidden, version):
                    repaired += 1
        kept.append(entry)

    if hidden != _hidden(config) or kept != _entries(config):
        result = dict(config)
        result['hidden_versions'] = hidden
        result['review_submission_entries'] = kept
        return result, repaired, clears
    return config, 0, 0


def report_lifecycle_alert(platform: str, reason: str, message: str) -> None:
    OMI_APP_REVIEW_CONFIG_ALERT_TOTAL.labels(
        platform=platform,
        reason=reason_label(ReasonFamily.APP_REVIEW_CONFIG, reason, AppReviewConfigReason),
    ).inc()
    OMI_APP_REVIEW_CONFIG_LAST_ALERT_TIMESTAMP.labels(
        platform=platform,
        reason=reason_label(ReasonFamily.APP_REVIEW_CONFIG, reason, AppReviewConfigReason),
    ).set(time.time())
    logger.error('app_review_config alert platform=%s reason=%s %s', platform, reason, message)


def _firestore_config(platform: str) -> dict[str, Any]:
    snapshot = db.collection('app_review_config').document(platform).get()
    if not getattr(snapshot, 'exists', False):
        return {}
    raw = snapshot.to_dict()
    return raw if isinstance(raw, dict) else {}


def _update_config(platform: str, transform: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    reference = db.collection('app_review_config').document(platform)

    @firestore.transactional
    def update(transaction: Any) -> dict[str, Any]:
        snapshot = reference.get(transaction=transaction)
        current = snapshot.to_dict() if getattr(snapshot, 'exists', False) else {}
        current = current if isinstance(current, dict) else {}
        updated = transform(current)
        if updated != current:
            transaction.set(reference, updated, merge=True)
        return updated

    updated = run_transactional(db, update, transient=True)
    get_memory_cache().delete(f"{_CACHE_KEY_PREFIX}{platform}")
    return updated


def load_secret(secret_name: str) -> str:
    """Read a Secret Manager value through the runtime identity; never log payloads."""
    try:
        credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        session = AuthorizedSession(credentials)
        url = (
            f"https://secretmanager.googleapis.com/v1/projects/{PROJECT_ID}/secrets/"
            f"{secret_name}/versions/latest:access"
        )
        response = session.get(url, timeout=10)
        if response.status_code == 404:
            raise StoreCredentialsUnavailable(f"secret {secret_name} is not configured")
        response.raise_for_status()
        payload = response.json().get('payload', {}).get('data')
        if not isinstance(payload, str):
            raise StoreCredentialsUnavailable(f"secret {secret_name} has no payload")
        value = base64.b64decode(payload, validate=True).decode('utf-8').strip()
        if not value:
            raise StoreCredentialsUnavailable(f"secret {secret_name} is empty")
        return value
    except StoreCredentialsUnavailable:
        raise
    except Exception as exc:
        raise StoreCredentialsUnavailable(f"secret {secret_name} could not be read") from exc


def load_submission_token() -> str:
    """Cache the Codemagic token briefly to bound unauthenticated Secret Manager reads."""
    global _submission_secret_cache
    with _submission_secret_cache_lock:
        now = time.monotonic()
        if _submission_secret_cache is not None and _submission_secret_cache[1] > now:
            value = _submission_secret_cache[0]
            if value is None:
                raise StoreCredentialsUnavailable("submission token is unavailable")
            return value
        try:
            value = load_secret(SECRET_NAMES["submission"])
        except StoreCredentialsUnavailable:
            _submission_secret_cache = (None, now + SUBMISSION_SECRET_CACHE_TTL_SECONDS)
            raise
        _submission_secret_cache = (value, now + SUBMISSION_SECRET_CACHE_TTL_SECONDS)
        return value


def _apple_versions() -> dict[str, str]:
    try:
        raw = json.loads(load_secret(SECRET_NAMES['apple']))
        issuer = raw['issuer_id']
        key_id = raw['key_id']
        private_key = raw['private_key']
        now = int(time.time())
        bearer = jwt.encode(
            {'iss': issuer, 'iat': now, 'exp': now + 900, 'aud': 'appstoreconnect-v1'},
            private_key,
            algorithm='ES256',
            headers={'kid': key_id, 'typ': 'JWT'},
        )
        headers = {'Authorization': f"Bearer {bearer}", 'Accept': 'application/json'}
        url = f"{APPLE_API}/apps/{APPLE_APP_ID}/appStoreVersions"
        params = {
            'filter[platform]': 'IOS',
            'limit': '200',
            'fields[appStoreVersions]': 'versionString,appStoreState',
        }
        states: dict[str, str] = {}
        while url:
            if not url.startswith(f"{APPLE_API}/"):
                raise ValueError('ASC pagination URL escaped the API origin')
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            rows = data.get('data', [])
            if not isinstance(rows, list):
                raise ValueError('ASC versions response is invalid')
            for row in rows:
                attributes = row.get('attributes', {}) if isinstance(row, dict) else {}
                version = attributes.get('versionString') if isinstance(attributes, dict) else None
                state = attributes.get('appStoreState') if isinstance(attributes, dict) else None
                if isinstance(version, str) and isinstance(state, str):
                    states[version] = state
            links = data.get('links', {})
            next_url = links.get('next') if isinstance(links, dict) else None
            url = next_url if isinstance(next_url, str) else ''
            params = None
        return states
    except StoreCredentialsUnavailable:
        raise
    except Exception as exc:
        raise RuntimeError('App Store Connect state read failed') from exc


def _play_release_version(name: object) -> str | None:
    if not isinstance(name, str):
        return None
    match = _PLAY_RELEASE_NAME_VERSION_PATTERN.match(name)
    return match.group(1) if match else None


def _play_production_state() -> tuple[set[str], dict[str, str]]:
    edit_id: str | None = None
    session: Any = None
    try:
        raw = json.loads(load_secret(SECRET_NAMES['play']))
        from google.oauth2.service_account import Credentials

        credentials = Credentials.from_service_account_info(
            raw, scopes=['https://www.googleapis.com/auth/androidpublisher']
        )
        session = AuthorizedSession(credentials)
        app_url = f"{PLAY_API}/{ANDROID_PACKAGE}/edits"
        created = None
        for attempt in range(5):
            created = session.post(app_url, json={}, timeout=15)
            if created.status_code != 409 or attempt == 4:
                break
            # Play allows one open edit per app. Exponential backoff absorbs
            # short collisions with the train, rollout watcher, or brake while
            # remaining well inside the scheduler's 300-second attempt limit.
            time.sleep(2**attempt)
        if created is None:
            raise RuntimeError("Play edit creation returned no response")
        created.raise_for_status()
        edit = created.json()
        edit_id = edit.get('id') if isinstance(edit, dict) else None
        if not isinstance(edit_id, str) or not edit_id:
            raise ValueError('Play edit response is invalid')
        track_url = f"{app_url}/{edit_id}/tracks/production"
        response = session.get(track_url, timeout=15)
        response.raise_for_status()
        track = response.json()
        releases = track.get('releases', []) if isinstance(track, dict) else []
        if not isinstance(releases, list):
            raise ValueError('Play production track response is invalid')
        completed_codes: set[str] = set()
        pending_versions_by_code: dict[str, str] = {}
        for release in releases:
            if not isinstance(release, dict):
                continue
            raw_codes = release.get('versionCodes', [])
            if not isinstance(raw_codes, list):
                continue
            codes = {str(code) for code in raw_codes}
            if release.get('status') == 'completed':
                completed_codes.update(codes)
            elif isinstance(release.get('status'), str):
                version = _play_release_version(release.get('name'))
                if version is not None:
                    pending_versions_by_code.update({code: version for code in codes})
        return completed_codes, pending_versions_by_code
    except StoreCredentialsUnavailable:
        raise
    except Exception as exc:
        raise RuntimeError('Google Play production state read failed') from exc
    finally:
        if edit_id is not None and session is not None:
            try:
                response = session.delete(f"{PLAY_API}/{ANDROID_PACKAGE}/edits/{edit_id}", timeout=15)
                response.raise_for_status()
            except Exception as exc:
                # A failed uncommitted-edit cleanup makes this polling tick
                # unhealthy; do not silently claim a successful read.
                logger.error('app_review_config Play temporary edit cleanup failed')
                raise RuntimeError('Google Play temporary edit cleanup failed') from exc


def submit_review_version(platform: str, version: str, version_code: str | None) -> dict[str, Any]:
    now = _now_utc()
    updated = _update_config(
        platform,
        lambda config: record_submission_config(
            config,
            platform=platform,
            version=version,
            version_code=version_code,
            now=now,
        ),
    )
    active = next(
        (
            row
            for row in reversed(_entries(updated))
            if row.get('platform') == platform and row.get('version') == version and row.get('state') == 'active'
        ),
        None,
    )
    deadline = active.get("expires_at") if active is not None else None
    if not isinstance(deadline, str):
        raise SubmissionConfigConflict("submission lease was not retained")
    return {'accepted': True, 'expires_at': deadline}


def run_app_review_config_sweep(*, now: datetime | None = None) -> dict[str, int]:
    """Run TTL first, then reconcile each platform independently and fail open."""
    current = now or _now_utc()
    summary = {'expired': 0, 'repaired': 0, 'cleared': 0, 'store_errors': 0}

    for platform in PLATFORMS:
        before = _firestore_config(platform)
        _, newly_expired = expire_config_entries(before, now=current)
        _update_config(platform, lambda config: expire_config_entries(config, now=current)[0])
        summary['expired'] += newly_expired

    for platform in PLATFORMS:
        try:
            if platform == 'ios':
                states = _apple_versions()
                before = _firestore_config(platform)
                _, repairs, clears = reconcile_ios_config(before, version_states=states, now=current)
                _update_config(
                    platform,
                    lambda config: reconcile_ios_config(config, version_states=states, now=current)[0],
                )
            else:
                codes, pending_versions = _play_production_state()
                before = _firestore_config(platform)
                updated, repairs, clears = reconcile_android_config(
                    before,
                    production_codes=codes,
                    pending_versions_by_code=pending_versions,
                    now=current,
                )
                if updated != before:
                    _update_config(
                        platform,
                        lambda config: reconcile_android_config(
                            config,
                            production_codes=codes,
                            pending_versions_by_code=pending_versions,
                            now=current,
                        )[0],
                    )
            summary['repaired'] += repairs
            summary['cleared'] += clears
            if repairs:
                report_lifecycle_alert(platform, 'reconciliation_repair', f"count={repairs}")
            if clears:
                report_lifecycle_alert(platform, 'live_hide_cleared', f"count={clears}")
        except StoreCredentialsUnavailable:
            summary['store_errors'] += 1
            report_lifecycle_alert(
                platform,
                'credentials_unavailable',
                'using TTL-only cleanup for this platform',
            )
            logger.warning(
                'app_review_config store credentials unavailable platform=%s; TTL continues',
                platform,
            )
        except Exception:
            summary['store_errors'] += 1
            report_lifecycle_alert(platform, 'store_api_error', 'using TTL-only cleanup for this platform')
            logger.exception(
                'app_review_config store read failed platform=%s; TTL continues',
                platform,
            )

    OMI_APP_REVIEW_CONFIG_LAST_SWEEP_TIMESTAMP.set(time.time())
    outcome = (
        AppReviewConfigOutcome.OK
        if summary['store_errors'] == 0
        else (
            AppReviewConfigOutcome.ERROR
            if summary["store_errors"] == len(PLATFORMS)
            else AppReviewConfigOutcome.PARTIAL
        )
    )
    OMI_APP_REVIEW_CONFIG_SWEEP_TOTAL.labels(
        outcome=reason_label(ReasonFamily.APP_REVIEW_CONFIG, outcome, AppReviewConfigOutcome)
    ).inc()
    return summary
