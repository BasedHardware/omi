"""Pack prepared Firestore conversation fields without decoding protected content."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from google.cloud.firestore_v1 import _helpers
from google.protobuf.message import DecodeError

from utils.firestore_document_size import FIRESTORE_MAX_DOCUMENT_BYTES, estimate_firestore_document_bytes

PAYLOAD_FIELD = '_conversation_payload'
CHUNK_BYTES = 256 * 1024
# Reserve room for lifecycle fields and commit stamps on a published projection.
PROJECTION_BYTES = FIRESTORE_MAX_DOCUMENT_BYTES - 32 * 1024
_FORMAT_VERSION = 1
_GENERATION = re.compile(r'[0-9a-f]{32}')


class ConversationProjectionTooLarge(ValueError):
    """The projected row needs a consumer migration before this write can fit."""


class InvalidConversationPayload(ValueError):
    """A committed generation is missing, malformed, or incompatible."""


@dataclass(frozen=True)
class ConversationWrite:
    parent: dict[str, Any]
    chunks: tuple[bytes, ...] = ()


def pack_conversation(
    prepared: Mapping[str, Any],
    document_path: str,
    *,
    spill_fields: Collection[str],
    generation: str,
    force_spill: bool = False,
) -> ConversationWrite:
    """Plan a full write from its final prepared values, after applying any patch.

    Only certified whole fields may spill. The caller supplies a generation
    token unique to the fenced publication and owns chunk storage and erasure.
    """
    if PAYLOAD_FIELD in prepared:
        raise ValueError('expected a hydrated conversation')
    parent = dict(prepared)
    if not force_spill and estimate_firestore_document_bytes(parent, document_path) <= PROJECTION_BYTES:
        return ConversationWrite(parent)

    if not _GENERATION.fullmatch(generation):
        raise ValueError('invalid conversation payload generation')
    structured = parent.get('structured')
    keep_indexed_category = (
        'structured' in spill_fields and isinstance(structured, Mapping) and 'category' in structured
    )
    if keep_indexed_category:
        # Conversation filters and counts use this nested Firestore index.
        spill_fields = set(spill_fields) - {'structured'}
    payload = {key: parent.pop(key) for key in spill_fields if key in parent}
    if not payload:
        if keep_indexed_category:
            raise ConversationProjectionTooLarge('conversation category must stay in the indexed parent')
        raise ConversationProjectionTooLarge('conversation has no eligible payload fields')

    from google.cloud.firestore_v1.types import MapValue

    wire_value = MapValue(fields=_helpers.encode_dict(payload))
    wire_bytes = MapValue.pb(wire_value).SerializeToString(deterministic=True)
    parent[PAYLOAD_FIELD] = {
        'version': _FORMAT_VERSION,
        'generation': generation,
        'size': len(wire_bytes),
        'sha256': hashlib.sha256(wire_bytes).digest(),
    }
    if estimate_firestore_document_bytes(parent, document_path) > PROJECTION_BYTES:
        if keep_indexed_category:
            raise ConversationProjectionTooLarge('conversation category must stay in the indexed parent')
        raise ConversationProjectionTooLarge('conversation projection exceeds its byte budget')

    chunks = tuple(wire_bytes[offset : offset + CHUNK_BYTES] for offset in range(0, len(wire_bytes), CHUNK_BYTES))
    return ConversationWrite(parent, chunks)


def hydrate_conversation(
    parent: Mapping[str, Any],
    chunks: Iterable[object] = (),
    *,
    client: Any = None,
) -> dict[str, Any]:
    """Restore an authorized parent from its generation's ordered chunks."""
    result = dict(parent)
    if PAYLOAD_FIELD not in result:
        return result

    _, size, digest = payload_descriptor(result.pop(PAYLOAD_FIELD))

    wire = bytearray()
    for chunk in chunks:
        expected_size = min(CHUNK_BYTES, size - len(wire))
        if expected_size <= 0 or not isinstance(chunk, bytes) or len(chunk) != expected_size:
            raise InvalidConversationPayload('invalid conversation payload chunk')
        wire.extend(chunk)
    if len(wire) != size or hashlib.sha256(wire).digest() != digest:
        raise InvalidConversationPayload('conversation payload failed integrity check')

    from google.cloud.firestore_v1.types import MapValue

    try:
        fields = MapValue.deserialize(bytes(wire)).fields
    except DecodeError as exc:
        raise InvalidConversationPayload('invalid conversation payload encoding') from exc
    if not fields or PAYLOAD_FIELD in fields or result.keys() & fields.keys():
        raise InvalidConversationPayload('payload fields conflict with conversation projection')

    try:
        payload = {key: _helpers.decode_value(value, client) for key, value in fields.items()}
    except (TypeError, ValueError) as exc:
        raise InvalidConversationPayload('invalid conversation payload fields') from exc
    result.update(payload)
    return result


def payload_descriptor(descriptor: Any) -> tuple[str, int, bytes]:
    """Validate metadata before deriving Firestore child paths from it."""
    if not isinstance(descriptor, Mapping):
        raise InvalidConversationPayload('invalid conversation payload descriptor')
    version = descriptor.get('version')
    generation = descriptor.get('generation')
    size = descriptor.get('size')
    digest = descriptor.get('sha256')
    if (
        type(version) is not int
        or version != _FORMAT_VERSION
        or not isinstance(generation, str)
        or not _GENERATION.fullmatch(generation)
        or type(size) is not int
        or size <= 0
        or not isinstance(digest, bytes)
        or len(digest) != hashlib.sha256().digest_size
    ):
        raise InvalidConversationPayload('invalid conversation payload descriptor')

    return generation, size, digest
