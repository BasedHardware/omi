"""Bounded, encrypted vector-only enrollment from explicit speaker receipts.

No IO. The database layer owns consent, source/deletion fences and atomic writes.
Only newly measured, segment-bound Omi-v2 evidence can enter this pool.
"""

import base64
import hashlib
import json
import math
import os
import struct
from datetime import datetime, timezone
from typing import Any, Mapping

import numpy as np
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from utils import encryption

from utils.speaker_learning_policy import authorized_teaching_segments, segment_group, winning_receipt_decision

POOL_FIELD = 'speaker_auto_enroll_pool'
AUTHORITY_FIELD = 'speaker_auto_enroll_authority'
REVOKED_FIELD = 'speaker_auto_enroll_revoked'
MAX_PEOPLE = 400
MODEL = 'wespeaker-voxceleb-resnet34-LM:v2'
DIM = 256
MAX_CONTRIBUTIONS = 5
MAX_AGE_SECONDS = 90 * 86400
HALF_LIFE_SECONDS = 30 * 86400
MIN_SECONDS = 10.0
MAX_DISTANCE = 0.35
OWNER_DISTANCE = 0.50


def enabled() -> bool:
    return os.getenv('SPEAKER_AUTO_ENROLL_ENABLED', 'true').lower() not in {'0', 'false', 'off', 'no'}


def retained(user: Mapping[str, Any]) -> bool:
    return (
        bool(user)
        and user.get('private_cloud_sync_enabled', True) is True
        and user.get('save_other_voice_profiles', True) is True
    )


def audio_allowed(user: Mapping, embedding: Any, expected_privacy_version: Any) -> bool:
    """The verified-audio fallback enforces the same owner/retention authority."""
    owner, incoming = unit(user.get('speaker_embedding')), unit(embedding)
    return (
        retained(user)
        and user.get('speaker_auto_enroll_privacy_version', 0) == expected_privacy_version
        and owner is not None
        and incoming is not None
        and 1 - owner @ incoming > OWNER_DISTANCE
    )


def owner_safe(embedding: Any, owner: Any) -> bool:
    incoming, reference = unit(embedding), unit(owner)
    return incoming is not None and reference is not None and 1 - incoming @ reference > OWNER_DISTANCE


def explicit_segments(conversation: Mapping, person_id: str) -> list:
    receipt = conversation.get('manual_speaker_assignments') or {}
    return [
        s
        for s in authorized_teaching_segments(conversation, person_id)
        if (winning_receipt_decision(receipt, s) or {}).get('source') != 'carried'
    ]


def unit(value: Any) -> Any:
    try:
        v = np.asarray(value, dtype=np.float64)
        if v.shape != (DIM,) or not np.isfinite(v).all() or np.linalg.norm(v) < 1e-8:
            return None
        return v / np.linalg.norm(v)
    except (ValueError, TypeError):
        return None


def pool_token(blob: Any) -> Any:
    return hashlib.sha256(blob.encode()).hexdigest() if isinstance(blob, str) and 0 < len(blob) <= 128 * 1024 else None


def authority_after(owner: Mapping, pools: Mapping) -> dict:
    authority = owner.get(AUTHORITY_FIELD) or {}
    if not isinstance(authority, dict):
        raise ValueError('Invalid speaker enrollment authority')
    authority = dict(authority)
    for pid, blob in pools.items():
        token = pool_token(blob)
        if token is None:
            authority.pop(pid, None)
        else:
            authority[pid] = token
    if len(authority) > MAX_PEOPLE:
        raise ValueError('Speaker enrollment authority exceeds person bound')
    return {AUTHORITY_FIELD: authority}


def cache_authority(uid: str, person: Mapping, context: Mapping) -> dict:
    entries = active(
        open_pool(uid, person.get('id') or '', person.get(POOL_FIELD)), datetime.now(timezone.utc).timestamp()
    )
    return {
        'enrollment_privacy_version': context.get('speaker_auto_enroll_privacy_version', 0),
        'enrollment_token': pool_token(person.get(POOL_FIELD)),
        'enrollment_expires_at': min((e['at'] + MAX_AGE_SECONDS for e in entries), default=0),
    }


def cached_authorized(person_id: str, cached: Mapping, context: Mapping, *, now: Any = None) -> bool:
    authority = context.get(AUTHORITY_FIELD)
    token = cached.get('enrollment_token')
    expires = cached.get('enrollment_expires_at')
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    return (
        enabled()
        and retained(context)
        and isinstance(authority, Mapping)
        and isinstance(token, str)
        and len(token) == 64
        and authority.get(person_id) == token
        and isinstance(expires, (int, float))
        and math.isfinite(expires)
        and now < expires
        and cached.get('enrollment_privacy_version') == context.get('speaker_auto_enroll_privacy_version', 0)
        and owner_safe(cached.get('embedding'), context.get('speaker_embedding'))
    )


def binding(segment: Mapping[str, Any]) -> str:
    # Identity labels change when a user tags; acoustic coordinates must not.
    # Resolution rewrites speaker scopes after embedding. The immutable segment
    # id and acoustic coordinates survive that rewrite; identity scope does not.
    fields = ('id', 'start', 'end', 'audio_capture_start', 'audio_capture_end')
    return hashlib.sha256(json.dumps([segment.get(k) for k in fields], separators=(',', ':')).encode()).hexdigest()


def evidence_bindings(segments: Any, keys: Mapping, placements: Mapping, measured: Mapping, prior: Mapping) -> dict:
    result = {}
    for segment in segments:
        data = segment.model_dump(mode='json')
        placement = placements.get(segment.id)
        if segment.id in keys and placement is not None and placement.window is not None:
            key = keys[segment.id]
            previous = prior.get(key, {})
            window = measured.get(segment.id)
            if (
                window is None
                and previous.get('binding') == binding(data)
                and previous.get('placement') == list(placement.window)
            ):
                window = previous.get('window')
            if window is not None:
                result[key] = {'binding': binding(data), 'window': list(window), 'placement': list(placement.window)}
    return result


def accepted_bindings(bindings: Mapping, cache: Mapping, before: Mapping, prior: Mapping) -> dict:
    """Do not retroactively grant enrollment authority to an old measured cache."""
    return {
        key: value
        for key, value in bindings.items()
        if key in cache
        and (
            cache[key] is not before.get(key)
            or (
                prior.get(key, {}).get('binding') == value['binding']
                and prior.get(key, {}).get('window') == value['window']
                and prior.get(key, {}).get('placement') == value.get('placement')
            )
        )
    }


def decode_evidence(data: bytes | None) -> dict:
    """Read only bounded, model-stamped evidence; old unbound caches abstain."""
    if not data or len(data) > 2 * 1024 * 1024 or len(data) < 4:
        return {}
    try:
        size = struct.unpack('>I', data[:4])[0]
        if size > 512 * 1024:
            return {}
        h = json.loads(data[4 : 4 + size])
        ids = h['ids']
        if (
            h.get('v') != 1
            or h.get('enrollment_model') != MODEL
            or h.get('enrollment_binding_version') != 2
            or h['dim'] != DIM
            or len(ids) > 2000
        ):
            return {}
        vectors = np.frombuffer(data[4 + size :], dtype='<f2').reshape(len(ids), DIM)
        return {
            key: {**h['enrollment_bindings'][key], 'seconds': h['evidence_seconds'][key], 'vector': vectors[i]}
            for i, key in enumerate(ids)
            if key in h.get('enrollment_bindings', {}) and key in h.get('evidence_seconds', {})
        }
    except (ValueError, TypeError, KeyError, AttributeError, struct.error):
        return {}


def candidate(conversation: Mapping, person_id: str, requested: Any, evidence: Mapping, owner: Any) -> Any:
    """One explicit acoustic voice, disjoint measured speech and owner exclusion."""
    owner = unit(owner)
    if owner is None:
        return None
    all_segments = conversation.get('transcript_segments') or []
    authorized = explicit_segments(conversation, person_id)
    groups = {segment_group(s) for s in authorized if s.get('id') in set(requested or [])}
    if len(groups) != 1:
        return None
    selected = [s for s in authorized if segment_group(s) in groups]
    authorized_ids = {s.get('id') for s in authorized}
    rows = []
    for segment in selected:
        matches = [e for e in evidence.values() if e.get('binding') == binding(segment)]
        if len(matches) != 1:
            continue
        e = matches[0]
        try:
            low, high = (float(x) for x in e['window'])
            seconds = float(e['seconds'])
            start, end = float(segment['start']), float(segment['end'])
            if not all(math.isfinite(x) for x in (low, high, seconds, start, end)):
                continue
            # A partial/nominal duration cannot stand in for a full measured clip.
            if high <= low or high - low > 15.01 or seconds < high - low - 0.02 or seconds > 15.01:
                continue
            if any(
                (segment_group(other) != segment_group(segment) or other.get('id') not in authorized_ids)
                and other.get('speaker_id_scope') == segment.get('speaker_id_scope')
                and float(other.get('start', 0)) < end
                and float(other.get('end', 0)) > start
                for other in all_segments
            ):
                continue
            v = unit(e['vector'])
            if v is None or 1 - v @ owner <= OWNER_DISTANCE:
                return None
            rows.append((low, high, segment['id'], v))
        except (ValueError, TypeError, KeyError):
            continue
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    vectors, ids, weights = [], [], []
    covered_end = -math.inf
    for low, high, sid, vector in rows:
        # Do not fractionally reuse a vector whose PCM overlaps an earlier clip.
        if low < covered_end:
            continue
        if sum(weights) + high - low > 30.01:
            continue
        covered_end = high
        vectors.append(vector)
        ids.append(sid)
        weights.append(high - low)
        if sum(weights) >= 30:
            break
    if sum(weights) < MIN_SECONDS:
        return None
    if any(1 - a @ b > MAX_DISTANCE for i, a in enumerate(vectors) for b in vectors[i + 1 :]):
        return None
    pooled = unit(np.average(vectors, axis=0, weights=weights))
    if not owner_safe(pooled, owner):
        return None
    return {'vector': pooled.tolist(), 'segment_ids': ids, 'seconds': sum(weights), 'model': MODEL}


def _aad(uid: str, person_id: str) -> bytes:
    return json.dumps(['speaker-auto-enroll', 1, uid, person_id], separators=(',', ':')).encode()


def seal(uid: str, person_id: str, entries: list) -> str:
    nonce = os.urandom(12)
    payload = json.dumps({'v': 1, 'model': MODEL, 'entries': entries}, separators=(',', ':'), allow_nan=False).encode()
    return base64.b64encode(
        nonce + AESGCM(encryption.derive_key(uid)).encrypt(nonce, payload, _aad(uid, person_id))
    ).decode()


def _open_pool(uid: str, person_id: str, blob: Any) -> list | None:
    if not isinstance(blob, str) or len(blob) > 128 * 1024:
        return None
    try:
        raw = base64.b64decode(blob, validate=True)
        value = json.loads(AESGCM(encryption.derive_key(uid)).decrypt(raw[:12], raw[12:], _aad(uid, person_id)))
        if (
            value.get('v') != 1
            or value.get('model') != MODEL
            or not isinstance(value.get('entries'), list)
            or len(value['entries']) > MAX_CONTRIBUTIONS
            or not all(isinstance(e, dict) for e in value['entries'])
        ):
            return None
        return value['entries']
    except Exception:
        # Authentication failure never returns ciphertext or a partial profile.
        return None


def open_pool(uid: str, person_id: str, blob: Any) -> list:
    return _open_pool(uid, person_id, blob) or []


def active(entries: list, now: float) -> list:
    return [
        e
        for e in entries
        if isinstance(e, dict)
        and isinstance(e.get('at'), (int, float))
        and 0 <= now - e['at'] <= MAX_AGE_SECONDS
        and unit(e.get('vector')) is not None
    ]


def vector(entries: list, now: float, owner: Any) -> Any:
    entries = active(entries, now)
    if not entries:
        return None
    v = unit(
        np.average(
            [unit(e['vector']) for e in entries],
            axis=0,
            weights=[2 ** (-(now - e['at']) / HALF_LIFE_SECONDS) for e in entries],
        )
    )
    return v.tolist() if owner_safe(v, owner) else None


def refresh(entries: list, contribution: dict, now: float) -> Any:
    entries = active(entries, now)
    incoming = unit(contribution.get('vector'))
    if incoming is None or any(1 - incoming @ unit(e['vector']) > MAX_DISTANCE for e in entries):
        return None
    # Retry does not extend the source's lifetime or amplify its vote.
    existing = next((e for e in entries if e.get('conversation_id') == contribution['conversation_id']), None)
    at = existing['at'] if existing else now
    kept = [e for e in entries if e.get('conversation_id') != contribution['conversation_id']]
    return sorted([*kept, {**contribution, 'at': at}], key=lambda e: e['at'])[-MAX_CONTRIBUTIONS:]


def retract(uid: str, pid: str, blob: Any, conversations: Any, segments: Any = None) -> dict:
    entries = _open_pool(uid, pid, blob)
    if entries is None:
        # Never let a temporary key/codec failure preserve opaque source data
        # that would reappear after a successful deletion when decoding recovers.
        return {POOL_FIELD: None} if blob else {}
    kept = [
        e
        for e in entries
        if e.get('conversation_id') not in conversations
        or (segments is not None and not set(segments).intersection(e.get('segment_ids') or []))
    ]
    return {POOL_FIELD: seal(uid, pid, kept) if kept else None} if kept != entries else {}


def legacy_voiceprint(person: Mapping) -> Any:
    embedding, version = person.get('speaker_embedding'), person.get('speech_samples_version')
    if embedding and person.get('speech_samples') and isinstance(version, int) and version >= 3:
        return embedding
    return None


def usable(uid: str, person: Mapping, allowed: Any) -> Any:
    if (
        not isinstance(allowed, Mapping)
        or not retained(allowed)
        or not enabled()
        or person.get('is_dismissed')
        or person.get(REVOKED_FIELD)
    ):
        return None
    authority = allowed.get(AUTHORITY_FIELD)
    token = pool_token(person.get(POOL_FIELD))
    if token is None or not isinstance(authority, Mapping) or authority.get(person.get('id')) != token:
        return None
    enrolled = vector(
        open_pool(uid, person.get('id') or '', person.get(POOL_FIELD)),
        datetime.now(timezone.utc).timestamp(),
        allowed.get('speaker_embedding'),
    )
    legacy = legacy_voiceprint(person)
    if enrolled is not None and legacy is not None:
        trusted = unit(legacy)
        if trusted is None or 1 - trusted @ unit(enrolled) > MAX_DISTANCE:
            return None  # A later independent audio enrollment must not be shadowed by stale vectors.
    return enrolled
