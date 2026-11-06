"""Transcript pointer codec and two-phase Firestore/lake boundary.

The transactional snapshot chooses the content-addressed reference; IO happens
only after an unloaded attempt has aborted. Inline writes can be swapped after
commit using the snapshot's update-time precondition.
"""

from __future__ import annotations

import asyncio
import copy
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import logging
import threading
from typing import Any, Callable, List, Mapping
import zlib

from cachetools import TTLCache

from config import object_lake as config
from database import _client
from utils import encryption
from utils.other import object_lake, space_keys

logger = logging.getLogger(__name__)


class TranscriptPointerError(Exception):
    """A lake transcript cannot be resolved safely."""


class TranscriptPointerFetchError(TranscriptPointerError):
    """Retryable pointer IO failure; never interpret as empty speech."""


class TranscriptBlobAbsent(TranscriptPointerError):
    """Deleted object."""


class TranscriptShredded(TranscriptPointerError):
    """Destroyed space key."""


class TranscriptPointerUnloaded(TranscriptPointerError):
    def __init__(self, uid, pointer):
        super().__init__('Transcript must be preloaded outside the transaction')
        self.uid, self.pointer = uid, dict(pointer)


def _owner():
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    return threading.get_ident(), id(task) if task is not None else None


@dataclass
class _Memo:
    # Context-local, TTL bounded plaintext; copies prevent privacy filters and
    # caller mutations from altering the content fetched for a later attempt.
    owner: tuple = field(default_factory=_owner)
    decoded: TTLCache = field(default_factory=lambda: TTLCache(maxsize=32, ttl=120))
    uploaded: TTLCache = field(default_factory=lambda: TTLCache(maxsize=32, ttl=120))
    deferred: dict = field(default_factory=dict)


_MEMO: ContextVar[_Memo | None] = ContextVar('transcript_pointer_memo', default=None)


def _memo() -> _Memo:
    memo = _MEMO.get()
    if memo is None or memo.owner != _owner():
        memo = _Memo()
        _MEMO.set(memo)
    return memo


def clear_memo() -> None:
    """Release plaintext, including at the end of an owning operation/test."""
    _MEMO.set(None)


def _ref(uid, pointer):
    ref = object_lake.LakeObjectRef.from_pointer_dict(dict(pointer))
    if ref.key.split('/')[2] != uid or ref.data_class != 'transcript':
        raise object_lake.LakeObjectCorrupt('Transcript pointer owner or class mismatch')
    if not config.bucket():
        raise TranscriptPointerFetchError('Transcript lake bucket is not configured')
    if ref.bucket != config.bucket():
        raise object_lake.LakeObjectCorrupt('Transcript pointer bucket mismatch')
    return ref


def _memo_key(uid, ref):
    # Verify the full reference too: equal hashes must not mask an absent blob
    # at another path, a changed key version, or a malformed byte count.
    return uid, ref


def preload_pointer(uid, pointer) -> None:
    if _client.in_transaction_body():
        raise TranscriptPointerUnloaded(uid, pointer)
    if not config.read_enabled():
        raise TranscriptPointerFetchError('Transcript lake resolution is disabled')
    ref = _ref(uid, pointer)
    try:
        plaintext = object_lake.get_space_object(ref)
        value = json.loads(plaintext)
        value = _require_segment_list(value)
    except object_lake.LakeObjectAbsent:
        value = TranscriptBlobAbsent('Transcript object is absent')
    except space_keys.SpaceKeyDestroyed:
        value = TranscriptShredded('Transcript key was destroyed')
    except (object_lake.LakeFetchError, object_lake.ObjectLakeNotConfigured, space_keys.SpaceKeyUnavailable):
        raise TranscriptPointerFetchError('Transcript lake resolution unavailable') from None
    except (object_lake.LakeObjectCorrupt, ValueError, TypeError, RecursionError):
        value = TranscriptSegmentsDecodeError('undecodable transcript pointer')
    _memo().decoded[_memo_key(uid, ref)] = value


def resolve_pointer(uid: str, pointer: Mapping) -> list:
    if not config.read_enabled():
        raise TranscriptPointerFetchError('Transcript lake resolution is disabled')
    ref = _ref(uid, pointer)
    key = _memo_key(uid, ref)
    memo = _memo()
    try:
        value = memo.decoded[key]
    except KeyError:
        if _client.in_transaction_body():
            raise TranscriptPointerUnloaded(uid, pointer)
        preload_pointer(uid, pointer)
        try:
            value = memo.decoded[key]
        except KeyError:
            raise TranscriptPointerFetchError('Transcript preload expired before use') from None
    if isinstance(value, Exception):
        # Cached failures must not accumulate caller tracebacks/plaintext frames.
        raise type(value)(str(value)) from None
    return copy.deepcopy(value)


def _consent_stamp(uid) -> object_lake.ConsentStamp:
    data = _client.get_data_plane_firestore_client().collection('users').document(uid).get().to_dict() or {}
    # users.set_user_training_data_opt_in stores a status/requested_at map,
    # not a boolean. Pending review cannot assert permission to train.
    opt_in = data.get('training_data_opt_in')
    status = opt_in.get('status') if isinstance(opt_in, dict) else None
    requested_at = opt_in.get('requested_at') if isinstance(opt_in, dict) else None
    at = requested_at.isoformat() if isinstance(requested_at, datetime) else requested_at
    return object_lake.ConsentStamp(
        'opt_in' if status == 'approved' else 'opt_out' if status == 'rejected' else 'unknown',
        '',  # The existing consent record has no policy-version field.
        at if isinstance(at, str) else '',
    )


def offload_or_inline(uid, conversation_id, segments: list, protect: Callable) -> bytes | str | dict:
    inline = protect(segments)
    if not segments or not conversation_id or not config.write_admitted(uid):
        return inline
    # Threshold is compressed bytes, including for enhanced (hex + encryption).
    plaintext = json.dumps(segments).encode('utf-8')
    if len(zlib.compress(plaintext)) <= config.inline_max_bytes():
        return inline
    digest = hashlib.sha256(plaintext).hexdigest()
    if _client.in_transaction_body():
        _memo().deferred[(uid, conversation_id)] = digest
        return inline
    memo = _memo()
    key = uid, conversation_id, digest
    try:
        ref = memo.uploaded[key]
    except KeyError:
        ref = object_lake.put_space_object(uid, 'transcript', conversation_id, plaintext, consent=_consent_stamp(uid))
        memo.uploaded[key] = ref
    memo.decoded[_memo_key(uid, ref)] = copy.deepcopy(segments)
    return ref.to_pointer_dict()


def run_preloaded_operation(operation, *args, swap_client=None, **kwargs):
    """Also supports transaction owners (e.g. ledger) with their own runner."""
    if _client.in_transaction_body():
        # The outer owner must abort before any preload or deferred drain.
        return operation(*args, **kwargs)
    memo = _memo()
    result: Any = None
    try:
        preloaded = {}
        content_changes = 0
        # At most 32 cold documents, three changed versions, and one commit
        # attempt. New documents must not consume the content-change allowance.
        for attempt in range(36):
            # Only the successful attempt may schedule a post-commit swap.
            memo.deferred.clear()
            try:
                with _client.transaction_body():
                    result = operation(*args, **kwargs)
            except TranscriptPointerUnloaded as error:
                unloaded = error
                ref = _ref(error.uid, error.pointer)
                document = error.uid, ref.bucket, ref.key.rsplit('/', 1)[0]
                previous = preloaded.get(document)
                if previous is not None:
                    content_changes += 1
                    memo.decoded.pop(_memo_key(error.uid, previous), None)
                elif len(preloaded) >= 32:
                    raise TranscriptPointerFetchError('Transcript exceeds bounded preload document limit') from None
                if content_changes > 3 or attempt == 35:
                    raise TranscriptPointerFetchError('Transcript changed during bounded preload retries') from None
                preloaded[document] = ref
            else:
                break
            preload_pointer(unloaded.uid, unloaded.pointer)
        notes = list(memo.deferred.items())
        memo.deferred.clear()
        if not _client.in_transaction_body():
            for (uid, cid), digest in notes:
                offload_inline_transcript(
                    uid, cid, firestore_client=swap_client or kwargs.get('firestore_client'), expected_sha256=digest
                )
        return result
    finally:
        # A worker thread must not retain plaintext for the next request.
        clear_memo()


def run_preloaded_transactional(client, fn, *args, **kwargs):
    return run_preloaded_operation(_client.run_transactional, client, fn, *args, swap_client=client, **kwargs)


def offload_inline_transcript(uid, conversation_id, *, firestore_client=None, expected_sha256=None) -> bool:
    """C3 primitive: upload first, then swap only the exact version just read.

    Failure leaves a readable inline document. No error here may turn a committed
    domain transaction into a reported failure.
    """
    try:
        if _client.in_transaction_body() or not config.write_admitted(uid):
            return False
        client = firestore_client if firestore_client is not None else _client.get_firestore_client()
        ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)
        snapshot = ref.get()
        data = snapshot.to_dict() or {}
        raw = data.get('transcript_segments')
        if not snapshot.exists or data.get('deleted') or data.get('status') == 'in_progress' or isinstance(raw, dict):
            return False
        segments = decode_stored_transcript(
            uid, raw, bool(data.get('transcript_segments_compressed')), require_decryption=True
        )
        plaintext = json.dumps(segments).encode('utf-8')
        if expected_sha256 is not None and hashlib.sha256(plaintext).hexdigest() != expected_sha256:
            return False
        pointer = offload_or_inline(uid, conversation_id, segments, lambda _: raw)
        if not isinstance(pointer, dict):
            return False
        ref.update(
            {'transcript_segments': pointer, 'transcript_segments_compressed': True},
            option=client.write_option(last_update_time=snapshot.update_time),
        )
        return True
    except Exception as error:
        logger.warning('transcript_offload_swap_skipped exception_type=%s', type(error).__name__)
        return False


class TranscriptSegmentsDecodeError(ValueError):
    """The stored transcript field cannot safely authorize a segment merge."""


def _require_segment_list(parsed: Any) -> List[Any]:
    if not isinstance(parsed, list):
        raise TranscriptSegmentsDecodeError(f'undecodable transcript_segments: parsed {type(parsed).__name__}')
    return parsed


def decode_stored_transcript(
    uid: str, raw_segments: Any, compressed: bool, *, require_decryption: bool = False
) -> List[Any]:
    """Decode a stored ``transcript_segments`` blob, raising when it cannot be read.

    The read path swallows decode failures into an empty list, which is safe for
    rendering but unsafe for a caller deciding whether a conversation is empty
    or whether a client projection may bind to it. Binding is authorization,
    not display: an unreadable blob must not become ``[]``.
    """
    if isinstance(raw_segments, dict):
        try:
            return resolve_pointer(uid, raw_segments)
        except object_lake.LakeObjectCorrupt as error:
            raise TranscriptSegmentsDecodeError('undecodable transcript pointer') from error
    if isinstance(raw_segments, list):
        return raw_segments
    try:
        if isinstance(raw_segments, str):
            payload = encryption.decrypt(raw_segments, uid)
            if require_decryption and payload == raw_segments:
                # A display fallback is not proof of successful decryption.
                raise TranscriptSegmentsDecodeError('undecodable transcript_segments: decryption failed')
            if compressed:
                parsed = json.loads(zlib.decompress(bytes.fromhex(payload)).decode('utf-8'))
            else:
                parsed = json.loads(payload)
            return _require_segment_list(parsed)
        if isinstance(raw_segments, bytes) and compressed:
            return _require_segment_list(json.loads(zlib.decompress(raw_segments).decode('utf-8')))
    except TranscriptSegmentsDecodeError:
        raise
    except (ValueError, TypeError, RecursionError, zlib.error) as error:
        raise TranscriptSegmentsDecodeError('undecodable transcript_segments: invalid encoding') from error
    raise TranscriptSegmentsDecodeError(
        f'undecodable transcript_segments: {type(raw_segments).__name__} compressed={compressed}'
    )
