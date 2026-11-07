"""Transcript pointer codec and two-phase Firestore/lake boundary.

The transactional snapshot chooses the content-addressed reference; IO happens
only after an unloaded attempt has aborted. Oversized candidates are uploaded
before retrying the entire transaction against a fresh source snapshot.
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
from itertools import chain
import sys
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


class TranscriptUploadRequired(TranscriptPointerError):
    """Abort before writing; the owning boundary uploads outside Firestore."""

    def __init__(self, uid, conversation_id, plaintext, source_digest):
        super().__init__('Transcript candidate must be uploaded outside the transaction')
        self.uid, self.conversation_id, self.plaintext = uid, conversation_id, plaintext
        self.source_digest = source_digest


class TranscriptMemoBudgetExceeded(TranscriptPointerFetchError):
    """Retryable operation memory limit; never evict a required read silently."""


MAX_MEMO_DECODED_BYTES = 64 * 1024 * 1024


def _decoded_bytes(value):
    # Account for decoded Python containers and strings, not compressed bytes.
    # Counting shared objects twice is deliberately conservative and avoids an
    # unbounded auxiliary set while measuring adversarial JSON.
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        for key, item in value.items():
            size += _decoded_bytes(key) + _decoded_bytes(item)
            if size > MAX_MEMO_DECODED_BYTES:
                break
    elif isinstance(value, list):
        for item in value:
            size += _decoded_bytes(item)
            if size > MAX_MEMO_DECODED_BYTES:
                break
    return size


class _DecodedMemo(TTLCache):
    """Both 32 entries and 64 MiB, with the same plaintext TTL."""

    def __init__(self):
        super().__init__(maxsize=MAX_MEMO_DECODED_BYTES, ttl=120, getsizeof=_decoded_bytes)

    def check_budget(self, key, value):
        self.expire()
        previous_bytes = self.getsizeof(self[key]) if key in self else 0
        if self.currsize - previous_bytes + self.getsizeof(value) > self.maxsize:
            raise TranscriptMemoBudgetExceeded('Transcript exceeds bounded decoded memo byte budget')

    def __setitem__(self, key, value):
        self.check_budget(key, value)
        if key not in self and len(self) >= 32:
            self.popitem()
        super().__setitem__(key, value)


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
    decoded: TTLCache = field(default_factory=_DecodedMemo)
    uploaded: TTLCache = field(default_factory=lambda: TTLCache(maxsize=32, ttl=120))
    resolved: set = field(default_factory=set)


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
    if _client.in_transaction_body() and len(memo.resolved) < 32:
        memo.resolved.add(key)
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


def _source_digest(segments):
    try:
        return hashlib.sha256(json.dumps(segments).encode('utf-8')).hexdigest()
    except (TypeError, ValueError, RecursionError):
        pass
    # Optional grouping evidence can be non-JSON or cyclic; its protector drops
    # that evidence while retaining the transcript. Stream a typed identity
    # without repr/address instability or an extra copy of the transcript tree.
    digest = hashlib.sha256(b'non-json:')
    stack: list[tuple[Any, int | None]] = [(iter((segments,)), None)]
    ancestors: set[int] = set()

    def feed(kind, payload):
        digest.update(kind)
        digest.update(len(payload).to_bytes(8, 'big'))
        digest.update(payload)

    while stack:
        iterator, ancestor = stack[-1]
        try:
            value = next(iterator)
        except StopIteration:
            stack.pop()
            if ancestor is not None:
                ancestors.remove(ancestor)
            continue
        if isinstance(value, (dict, list, tuple)):
            kind = b'D' if isinstance(value, dict) else b'L'
            if id(value) in ancestors:
                feed(b'C', kind)
                continue
            feed(kind, str(len(value)).encode('ascii'))
            ancestors.add(id(value))
            children = chain.from_iterable(value.items()) if isinstance(value, dict) else iter(value)
            stack.append((children, id(value)))
        else:
            try:
                payload = json.dumps(value).encode('utf-8')
            except (TypeError, ValueError, RecursionError):
                feed(b'X', f'{type(value).__module__}.{type(value).__qualname__}'.encode('utf-8'))
            else:
                feed(b'V', payload)
    return digest.hexdigest()


def conversation_allows_offload(conversation: Mapping, current: Mapping | None = None) -> bool:
    """Private/unknown visibility, tombstones and locked content stay inline."""
    if current is not None:
        if not conversation_allows_offload(current):
            return False
        conversation = {**current, **conversation}
    return (
        conversation.get('visibility') in ('shared', 'public')
        and not conversation.get('deleted')
        and not conversation.get('is_locked')
    )


def offload_or_inline(
    uid,
    conversation_id,
    segments: list,
    protect: Callable,
    *,
    conversation_state: Mapping,
    current_state: Mapping | None = None,
    prepare_segments: Callable | None = None,
) -> bytes | str | dict:
    admitted = bool(
        segments
        and conversation_id
        and conversation_allows_offload(conversation_state, current_state)
        and config.write_admitted(uid)
    )
    # Retry identity precedes randomized sidecar protection. The reference's
    # own sha256 still authenticates the actual protected JSON in the lake.
    source_digest = _source_digest(segments) if admitted else ''
    if prepare_segments is not None:
        prepare_segments(segments)
    inline = protect(segments)
    # Recheck the kill switch after protection; a newly opened cohort starts
    # on its next encode, while a newly closed cohort stops immediately.
    if not admitted or not segments or not config.write_admitted(uid):
        return inline
    plaintext = json.dumps(segments).encode('utf-8')
    if len(zlib.compress(plaintext)) <= config.inline_max_bytes():
        return inline
    memo = _memo()
    key = uid, conversation_id, source_digest
    try:
        ref = memo.uploaded[key]
    except KeyError:
        if _client.in_transaction_body():
            raise TranscriptUploadRequired(uid, conversation_id, plaintext, source_digest)
        ref = _upload_candidate(uid, conversation_id, plaintext, source_digest, cache_decoded=True)
    return ref.to_pointer_dict()


def _upload_candidate(uid, conversation_id, plaintext, source_digest, *, cache_decoded=False):
    if _client.in_transaction_body():
        raise TranscriptUploadRequired(uid, conversation_id, plaintext, source_digest)
    ref = object_lake.put_space_object(uid, 'transcript', conversation_id, plaintext, consent=_consent_stamp(uid))
    memo = _memo()
    key = _memo_key(uid, ref)
    # Only direct pre-transaction encodes may warm reads. A transaction
    # candidate must not mask a cold read of an existing identical reference.
    # Cache actual upload bytes, never a later encryption of the same source.
    if cache_decoded and key not in memo.decoded and len(memo.decoded) < 32:
        memo.decoded[key] = _require_segment_list(json.loads(plaintext))
    memo.uploaded[(uid, conversation_id, source_digest)] = ref
    return ref


def run_preloaded_operation(operation, *args, **kwargs):
    """Also supports transaction owners (e.g. ledger) with their own runner."""
    if _client.in_transaction_body():
        # The outer owner must abort before any preload or candidate upload.
        return operation(*args, **kwargs)
    memo = _memo()
    result: Any = None
    try:
        preloaded = {}
        uploaded = {}
        upload_changes = 0
        content_changes = 0
        # Each of 32 documents may need both a read preload and a candidate
        # upload, plus the existing three content changes and a final commit.
        for attempt in range(68):
            memo.resolved.clear()
            try:
                with _client.transaction_body():
                    result = operation(*args, **kwargs)
            except TranscriptUploadRequired as error:
                document = error.uid, error.conversation_id
                if document in uploaded:
                    upload_changes += 1
                elif len(uploaded) >= 32:
                    raise TranscriptPointerFetchError('Transcript exceeds bounded upload document limit') from None
                if content_changes + upload_changes > 3 or attempt == 67:
                    raise TranscriptPointerFetchError('Transcript changed during bounded upload retries') from None
                uploaded[document] = error.source_digest
                _upload_candidate(error.uid, error.conversation_id, error.plaintext, error.source_digest)
                continue
            except TranscriptPointerUnloaded as error:
                unloaded = error
                ref = _ref(error.uid, error.pointer)
                document = error.uid, ref.bucket, ref.key.rsplit('/', 1)[0]
                # Undo/merge may intentionally read multiple historical versions
                # of one document. Keep every version used by this attempt;
                # only an unused predecessor can be superseded by a new ref.
                superseded = [
                    key
                    for key in preloaded
                    if (key[0], key[1].bucket, key[1].key.rsplit('/', 1)[0]) == document and key not in memo.resolved
                ]
                if superseded:
                    content_changes += 1
                    for key in superseded:
                        memo.decoded.pop(key, None)
                        preloaded.pop(key)
                elif len(preloaded) >= 32:
                    raise TranscriptPointerFetchError('Transcript exceeds bounded preload document limit') from None
                if content_changes + upload_changes > 3 or attempt == 67:
                    raise TranscriptPointerFetchError('Transcript changed during bounded preload retries') from None
                preloaded[_memo_key(error.uid, ref)] = ref
            else:
                break
            preload_pointer(unloaded.uid, unloaded.pointer)
        return result
    finally:
        # A worker thread must not retain plaintext for the next request.
        clear_memo()


def run_preloaded_transactional(client, fn, *args, **kwargs):
    return run_preloaded_operation(_client.run_transactional, client, fn, *args, **kwargs)


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
        if (
            not snapshot.exists
            or not conversation_allows_offload(data)
            or data.get('status') == 'in_progress'
            or isinstance(raw, dict)
        ):
            return False
        segments = decode_stored_transcript(
            uid, raw, bool(data.get('transcript_segments_compressed')), require_decryption=True
        )
        plaintext = json.dumps(segments).encode('utf-8')
        if expected_sha256 is not None and hashlib.sha256(plaintext).hexdigest() != expected_sha256:
            return False
        pointer = offload_or_inline(uid, conversation_id, segments, lambda _: raw, conversation_state=data)
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
