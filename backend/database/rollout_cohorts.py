"""Firestore transport for private cohorts; all clients remain lazy."""

from collections.abc import Iterable, Mapping
import math
import re
from typing import Any

from google.cloud import firestore

from config.rollout_cohorts import COLLECTION, COHORT_ENVS, valid_uid
from database._client import get_data_plane_firestore_client, run_transactional

STT_CAP_DOCUMENT = 'stt-cap-dispatch'
HELD_CONTENT_DOCUMENT = 'held-content'


def read_stt_cap_cohort(*, firestore_client: Any | None = None) -> dict | None:
    """One process-wide control document, separate from private member records.

    None means absent. Existing malformed documents must not look absent.
    Validation and environment fencing belong to the runtime cache.
    """
    client = firestore_client or get_data_plane_firestore_client()
    doc = client.collection(COLLECTION).document(STT_CAP_DOCUMENT).get(timeout=1.0, retry=None)
    return (doc.to_dict() or {}) if doc.exists else None


def read_held_content_cohort(*, firestore_client: Any | None = None) -> dict | None:
    """One process-wide control document. None means absent; malformed stays present."""
    client = firestore_client or get_data_plane_firestore_client()
    doc = client.collection(COLLECTION).document(HELD_CONTENT_DOCUMENT).get(timeout=1.0, retry=None)
    return (doc.to_dict() or {}) if doc.exists else None


def read_memberships(uid: str, *, firestore_client: Any | None = None) -> dict[str, dict[str, bool]]:
    client = firestore_client or get_data_plane_firestore_client()
    doc = client.collection(COLLECTION).document(uid).get(timeout=1.0, retry=None)
    if not doc.exists:
        return {}
    data = doc.to_dict()
    members = data.get('cohorts') if isinstance(data, dict) else None
    if not isinstance(members, dict) or any(
        not isinstance(flags, dict) or any(type(value) is not bool for value in flags.values())
        for flags in members.values()
    ):
        raise ValueError('invalid cohort document')
    return members


def read_cohort_members(name: str, *, firestore_client: Any | None = None) -> tuple[str, ...]:
    client = firestore_client or get_data_plane_firestore_client()
    environment, name = name.split(':', 1)
    if environment not in {'prod', 'dev', 'local', 'offline'} or name not in COHORT_ENVS:
        raise ValueError('invalid cohort discovery scope')
    rows = list(
        client.collection(COLLECTION)
        .where(f'cohorts.{environment}.`{name}`', '==', True)
        .limit(500)
        .stream(timeout=1.0, retry=None)
    )
    if len(rows) >= 500:
        raise ValueError('cohort discovery limit exceeded')
    return tuple(row.id for row in rows if valid_uid(row.id))


# ---------------------------------------------------------------------------
# `_ramp` control document (contract (f)): runtime percents and legacy_sync mode.
# ---------------------------------------------------------------------------

RAMP_DOC_ID = '_ramp'
RAMP_HISTORY_COLLECTION = 'history'
RAMP_SCHEMA_VERSION = 1
RAMP_NAMES = ('batch-pipeline', 'first-summary', 'batch-live-stt-retire')
LEGACY_SYNC_MODES = ('on', 'draining', 'dark')
# Serving reads stay within the runtime's cold-start budget. Operator tools (ramp_set, ramp_controller) build a
# fresh client per process, and a cold channel plus token fetch from an operator host takes over 1s.
SERVING_READ_TIMEOUT_SECONDS = 1.0
OPERATOR_READ_TIMEOUT_SECONDS = 10.0
# rollout_environment() values plus the staging deployment identity (OMI_DEPLOYMENT).
RAMP_ENVS = ('prod', 'staging', 'dev', 'local', 'offline')
_CHANGE_KEYS = frozenset({'percents', 'legacy_sync', 'locked_by'})
_TOKEN_RE = re.compile(r'[a-z][a-z0-9_]{0,39}')
_ACTOR_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:@|-]{0,63}')


class RampDocumentError(ValueError):
    """The `_ramp` document or a proposed change violates the contract schema; content-free message."""


class RampRevisionConflict(RuntimeError):
    """CAS lost: the document revision is not the expected one."""

    def __init__(self, expected: int, actual: int):
        super().__init__(f'ramp revision conflict expected={expected} actual={actual}')
        self.expected = expected
        self.actual = actual


def _percent_value(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RampDocumentError('ramp percent must be a number')
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 100.0:
        raise RampDocumentError('ramp percent out of range')
    return value


def _optional_str(value: Any, field: str, limit: int = 128) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > limit:
        raise RampDocumentError(f'ramp {field} malformed')
    return value


def normalize_ramp_env(raw: Any) -> dict[str, Any]:
    """Validate one `envs.<env>` object. Nesting violations are left to callers (reader clamps, writer refuses)."""
    if not isinstance(raw, dict):
        raise RampDocumentError('ramp env must be a map')
    percents_raw = raw.get('percents', {})
    if not isinstance(percents_raw, dict) or any(name not in RAMP_NAMES for name in percents_raw):
        raise RampDocumentError('ramp percents malformed')
    legacy_sync = raw.get('legacy_sync', 'on')
    if legacy_sync not in LEGACY_SYNC_MODES:
        raise RampDocumentError('ramp legacy_sync malformed')
    return {
        'percents': {name: _percent_value(value) for name, value in percents_raw.items()},
        'legacy_sync': legacy_sync,
        'locked_by': _optional_str(raw.get('locked_by'), 'locked_by'),
        'updated_at': _optional_str(raw.get('updated_at'), 'updated_at', 40),
        'updated_by': _optional_str(raw.get('updated_by'), 'updated_by', 64),
        'reason': _optional_str(raw.get('reason'), 'reason', 40),
    }


def normalize_ramp_document(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get('schema_version') != RAMP_SCHEMA_VERSION:
        raise RampDocumentError('ramp schema_version unsupported')
    revision = raw.get('revision')
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise RampDocumentError('ramp revision malformed')
    envs = raw.get('envs', {})
    if not isinstance(envs, dict) or any(env not in RAMP_ENVS for env in envs):
        raise RampDocumentError('ramp envs malformed')
    return {
        'schema_version': RAMP_SCHEMA_VERSION,
        'revision': revision,
        'envs': {env: normalize_ramp_env(value) for env, value in envs.items()},
    }


def check_ramp_nesting(env_doc: dict[str, Any]) -> None:
    """Writer rule: batch-live-stt-retire never exceeds batch-pipeline (E decision 2)."""
    percents = env_doc['percents']
    retire = percents.get('batch-live-stt-retire')
    if retire is not None and retire > percents.get('batch-pipeline', 0.0):
        raise RampDocumentError('batch-live-stt-retire exceeds batch-pipeline')


def empty_ramp_env() -> dict[str, Any]:
    return {
        'percents': {},
        'legacy_sync': 'on',
        'locked_by': None,
        'updated_at': None,
        'updated_by': None,
        'reason': None,
    }


def _is_mapping(value: object) -> bool:
    return isinstance(value, Mapping)


def _is_token(value: object, pattern: re.Pattern[str]) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _is_revision(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def apply_ramp_change(before: dict[str, Any], change: Mapping[str, Any]) -> dict[str, Any]:
    """Pure merge of an operator/controller change onto one env object; validates the result."""
    if not _is_mapping(change) or not change or any(key not in _CHANGE_KEYS for key in change):
        raise RampDocumentError('ramp change keys unsupported')
    after = {**before, 'percents': dict(before['percents'])}
    if 'percents' in change:
        percents = change['percents']
        if not isinstance(percents, Mapping) or not percents or any(name not in RAMP_NAMES for name in percents):
            raise RampDocumentError('ramp percents change malformed')
        for name, value in percents.items():
            after['percents'][name] = _percent_value(value)
    if 'legacy_sync' in change:
        if change['legacy_sync'] not in LEGACY_SYNC_MODES:
            raise RampDocumentError('ramp legacy_sync change malformed')
        after['legacy_sync'] = change['legacy_sync']
    if 'locked_by' in change:
        after['locked_by'] = _optional_str(change['locked_by'], 'locked_by')
    check_ramp_nesting(after)
    return after


def _ramp_ref(client: Any) -> Any:
    return client.collection(COLLECTION).document(RAMP_DOC_ID)


def read_ramp(
    *, firestore_client: Any | None = None, timeout: float = SERVING_READ_TIMEOUT_SECONDS
) -> dict[str, Any] | None:
    """Point read of the control document (SDK retries off). None when absent; raises on malformed."""
    client = firestore_client or get_data_plane_firestore_client()
    doc = _ramp_ref(client).get(timeout=timeout, retry=None)
    if not doc.exists:
        return None
    return normalize_ramp_document(doc.to_dict())


def read_ramp_history(revisions: Iterable[int], *, firestore_client: Any | None = None) -> list[dict[str, Any]]:
    """Point reads of `_ramp/history/{revision:010d}` rows (no query, no index); absent rows are skipped."""
    client = firestore_client or get_data_plane_firestore_client()
    history = _ramp_ref(client).collection(RAMP_HISTORY_COLLECTION)
    rows = []
    for revision in revisions:
        doc = history.document(f'{revision:010d}').get(timeout=3.0, retry=None)
        if doc.exists:
            data = doc.to_dict()
            if isinstance(data, dict):
                rows.append(data)
    return rows


def write_ramp(
    env: str,
    change: Mapping[str, Any],
    *,
    expected_revision: int,
    actor: str,
    reason: str,
    gate_verdict: Mapping[str, Any] | None = None,
    at: str,
    firestore_client: Any | None = None,
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """CAS on `revision`; the history row is created in the same transaction. Returns (revision, before, after)."""
    if env not in RAMP_ENVS:
        raise RampDocumentError('ramp env unsupported')
    if not _is_token(actor, _ACTOR_RE):
        raise RampDocumentError('ramp actor malformed')
    if not _is_token(reason, _TOKEN_RE):
        raise RampDocumentError('ramp reason malformed')
    if not _is_revision(expected_revision):
        raise RampDocumentError('ramp expected_revision malformed')
    client = firestore_client or get_data_plane_firestore_client()
    ref = _ramp_ref(client)

    @firestore.transactional
    def commit(transaction):
        snapshot = ref.get(transaction=transaction)
        current_revision = 0
        current_envs: dict[str, Any] = {}
        if snapshot.exists:
            current = normalize_ramp_document(snapshot.to_dict())
            current_revision, current_envs = current['revision'], current['envs']
        if current_revision != expected_revision:
            raise RampRevisionConflict(expected_revision, current_revision)
        before: dict[str, Any] = current_envs.get(env) or empty_ramp_env()
        after = apply_ramp_change(before, change)
        after.update(updated_at=at, updated_by=actor, reason=reason)
        revision = expected_revision + 1
        envs = {**current_envs, env: after}
        transaction.set(ref, {'schema_version': RAMP_SCHEMA_VERSION, 'revision': revision, 'envs': envs})
        transaction.create(
            ref.collection(RAMP_HISTORY_COLLECTION).document(f'{revision:010d}'),
            {
                'revision': revision,
                'env': env,
                'before': before,
                'after': after,
                'actor': actor,
                'reason': reason,
                'gate_verdict': dict(gate_verdict) if gate_verdict is not None else None,
                'at': at,
            },
        )
        return revision, before, after

    return run_transactional(client, commit)
