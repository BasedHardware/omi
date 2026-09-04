"""Canonical transcript hash for client-projection and local-memory source binding.

Encoding v5 binds the effective identity together with text. A projection that
says "you approved the transfer" is false if Bob said those words, even when
both turns still carry the diarization slot ``SPEAKER_00``. Two stored segments
that render as "Speaker 0" and "Speaker 7" must also not share a digest: the
numeric ``speaker_id`` is what the reader is shown when there is no person
name. The digest therefore binds five fields per segment: speaker label,
``speaker_id``, ``is_user``, ``person_id``, and text. A re-diarized or
re-identified transcript is EXPECTED to stop verifying — the fail-closed
outcome is a drop to the deterministic minimum, not silent retention of a
stale projection. Timings and ids are ignored.

Hashed value is stored value. The digest is over the identity the storage
boundary persists, not a parallel spelling of the request JSON.
``canonical_segment`` is that identity; ``canonicalize_transcript_segments_for_storage``
writes it onto every segment list that ``database.conversations`` compresses
or encrypts, so assign, sync, live capture, from-segments, and any later
writer cannot store a padded ``person_id`` the hasher would strip. Surrounding
whitespace on ``speaker``, ``person_id``, and ``text`` is stripped once at
that seam — a padded label is not a different speaker, and a transcript is
never rejected because a speaker label carries spaces. Clients reproduce the
digest by applying the same canonicalization to their own JSON, then
hashing. Hashing the raw unstripped JSON of ``person_id`` ``" alice "`` will
miss the server digest of the stored ``"alice"``.

An empty-after-strip *text* segment still contributes its identity frames.
Storage preserves that row, and the production renderer still emits its
speaker (``Speaker 7:`` with no words). Encoding v4 skipped empty text
because the digest bound only words; once it binds attribution, two
transcripts that render differently must not share a digest. The empty
text frame is ASCII ``0\\n``. Whitespace-only text is that same empty frame
after strip, not a skipped segment. Only an empty *list* hashes the empty
byte string. from-segments still 422s empty text
(``stored_transcript_segment`` returns ``None``); that ingest path is not a
reason to omit empty rows other writers already persist. Clients hashing
their JSON must include an empty-text segment's speaker, ``speaker_id``,
``is_user``, and ``person_id`` the same way they include a spoken turn.

``transcript_sha256`` still strips: it is the client-reproducible helper, and
a dict with ``person_id`` ``" alice "`` must hash as ``"alice"``. Binding a
projection to a *stored* row is a different question. Rows written before the
storage-boundary change can still hold ``" alice "``. Hashing those strips
and matches a client digest of ``"alice"``, while rendering looks up
``" alice "`` and shows ``Speaker 0``. ``transcript_sha256_for_binding``
returns ``None`` for a non-canonical stored transcript so the projection is
dropped rather than trusted. Do not use ``transcript_sha256`` at the binding
site.

Speaker normalization: read ``speaker`` (mapping key or attribute). Missing,
``None``, a non-string, or empty-after-strip becomes ``DEFAULT_SPEAKER``
(``SPEAKER_00``) — the same value ``TranscriptSegment`` and the request models
materialize for an omitted speaker. Without that, one logical transcript would
hash two ways: a client hashing its own JSON with no ``speaker`` key would get
the empty string while the server hashed the model default, and EVERY
projection would be dropped for a mismatch with no error anywhere. Case is
preserved and surrounding whitespace is stripped otherwise. Stripping happens
before any later identity is derived from the label, so a padded speaker and
its stripped form materialize identically.

``speaker_id`` is a JSON number. Only an actual ``int`` (not ``bool``, which
is an ``int`` subclass) is a present id; that integer is encoded as its ASCII
decimal in its own length frame. A missing, ``None``, or non-int value is
derived the same way ``TranscriptSegment.__init__`` materializes an omitted
``speaker_id``: parse the trailing decimal of the canonical speaker label
(``SPEAKER_07`` → 7); on parse failure, ``DEFAULT_SPEAKER_ID`` (0). Rendering
uses ``Speaker {speaker_id}`` with the same 0 default, so an omitted id and an
explicit 0 are the same transcript when the label does not itself name a
different slot. ``0`` is the frame ``1\\n0``, never an empty frame.

``is_user`` is a JSON boolean. True encodes as the single ASCII byte ``Y``;
False encodes as ``N``. A missing, ``None``, or non-bool value is ``N`` — the
same ``False`` default ``DevTranscriptSegment`` and
``ConversationItemTranscriptSegment`` materialize for an omitted ``is_user``.
These are tokens in their own length frame, not Python's ``True``/``False``
spellings and not the integers ``1``/``0`` (``bool`` is an ``int`` subclass, so
a numeric token would be ambiguous next to ``person_id`` and ``speaker_id``).
Only an actual ``True`` counts as the user; ``1`` and ``"true"`` are not-user.

``person_id`` normalization: a missing, ``None``, non-string, or
empty-after-strip value encodes as the empty frame (ASCII ``0\\n`` with no
payload) — the same ``None`` default the segment models materialize. A present
id is the stripped UTF-8 string in its own length frame. Empty is reserved for
"no person"; a present id is therefore always at least one byte, so the two
cases cannot collide. ``person_id`` ``"0"`` is the frame ``1\\n0``, not the
empty frame.

The client rule is therefore: strip ``speaker``, ``person_id``, and ``text``;
omitting ``speaker`` means ``SPEAKER_00``; omitting ``speaker_id`` means the
id ``TranscriptSegment`` would materialize from that (already stripped)
speaker (0 for ``SPEAKER_00`` / unparseable labels, 7 for ``SPEAKER_07``);
omitting ``is_user`` means not-user (``N``); omitting ``person_id`` means no
person (empty frame). An empty-after-strip *text* still contributes its
identity frames (empty text frame, not an omitted segment). Hash those
canonical values, not the raw JSON spelling.

Encoding v5 is length-framed so the digest is injective over the sequence of
``(speaker, speaker_id, is_user, person_id, text)`` tuples. Each segment
emits five frames, in that order: the ASCII decimal of the field's UTF-8 byte
length, a newline, that many bytes. Empty-after-strip text is the empty
frame, not an omitted tuple. Empty input (no segments) hashes the empty byte
string.

Length-framing is what keeps the collision fix: a segment whose text contains a
newline cannot imitate a multi-segment transcript, and bytes cannot be moved
between speaker, speaker_id, identity tokens, person_id, and text without
changing a length prefix.

This digest is a wire contract with clients. Bump ``TRANSCRIPT_HASH_ENCODING_VERSION``
when the framing changes. The version names this encoding; it is not mixed
into the digest bytes. The same helper is the source-binding hash S5b will
use for locally-formed memories.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, cast

from models.transcript_segment import TranscriptSegment

TRANSCRIPT_HASH_ENCODING_VERSION = 5

# Must equal the ``speaker`` default on TranscriptSegment and the request segment
# models, so a dict and a parsed model of the same segment hash identically.
DEFAULT_SPEAKER = 'SPEAKER_00'

# Must equal the speaker_id TranscriptSegment materializes when the label does
# not carry a trailing decimal (and the 0 ``seg.get('speaker_id', 0)`` render
# path uses for a missing id).
DEFAULT_SPEAKER_ID = 0

# Wire tokens for the is_user frame. Missing/None/non-bool means not-user, the
# False default the request segment models materialize.
IS_USER_TOKEN = 'Y'
NOT_USER_TOKEN = 'N'


def _segment_field(segment: Any, name: str, default: str = '') -> str:
    if isinstance(segment, Mapping):
        mapping = cast(Mapping[str, Any], segment)
        raw: object = mapping.get(name)
    else:
        raw = getattr(segment, name, None)
    if not isinstance(raw, str) or not raw.strip():
        return default
    return raw.strip()


def _segment_is_user_token(segment: Any) -> str:
    if isinstance(segment, Mapping):
        raw: object = cast(Mapping[str, Any], segment).get('is_user')
    else:
        raw = getattr(segment, 'is_user', None)
    return IS_USER_TOKEN if raw is True else NOT_USER_TOKEN


def _derived_speaker_id(canonical_speaker: str) -> int:
    """Mirror TranscriptSegment.__init__ on a stripped, defaulted speaker label."""
    try:
        return int(canonical_speaker.split('_', 1)[1])
    except (ValueError, IndexError):
        return DEFAULT_SPEAKER_ID


def _segment_speaker_id(segment: Any, canonical_speaker: str) -> int:
    if isinstance(segment, Mapping):
        raw: object = cast(Mapping[str, Any], segment).get('speaker_id')
    else:
        raw = getattr(segment, 'speaker_id', None)
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    return _derived_speaker_id(canonical_speaker)


def _segment_timing(segment: Any, name: str, default: float) -> float:
    if isinstance(segment, Mapping):
        raw: object = cast(Mapping[str, Any], segment).get(name)
    else:
        raw = getattr(segment, name, None)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    return default


@dataclass(frozen=True)
class CanonicalSegment:
    """Identity+text as stored, hashed, and rendered.

    ``person_id`` is ``None`` when the request omitted it or it was blank
    after strip — the same ``None`` the segment models materialize.
    """

    speaker: str
    speaker_id: int
    is_user: bool
    person_id: str | None
    text: str


def canonical_segment(segment: Any) -> CanonicalSegment:
    """Return the identity ingest stores, hashes, and rendering reads.

    Empty-after-strip text is still returned: the empty text frame plus the
    identity the renderer would emit. Clients apply this same
    canonicalization to their JSON before hashing. ``stored_transcript_segment``
    separately returns ``None`` because from-segments 422s empty text.
    """
    text = _segment_field(segment, 'text')
    speaker = _segment_field(segment, 'speaker', DEFAULT_SPEAKER)
    person_id = _segment_field(segment, 'person_id') or None
    return CanonicalSegment(
        speaker=speaker,
        speaker_id=_segment_speaker_id(segment, speaker),
        is_user=_segment_is_user_token(segment) == IS_USER_TOKEN,
        person_id=person_id,
        text=text,
    )


def stored_transcript_segment(segment: Any) -> TranscriptSegment | None:
    """Build the TranscriptSegment from-segments persists.

    Identity fields are ``canonical_segment`` so the stored row is the hashed
    row. Timings are copied through and are not part of the digest.
    """
    kept = canonical_segment(segment)
    if not kept.text:
        return None
    return TranscriptSegment(
        text=kept.text,
        speaker=kept.speaker,
        speaker_id=kept.speaker_id,
        is_user=kept.is_user,
        person_id=kept.person_id,
        start=_segment_timing(segment, 'start', 0.0),
        end=_segment_timing(segment, 'end', 1.0),
    )


def canonicalize_segment_for_storage(segment: Any) -> Any:
    """Rewrite identity onto a segment dict so stored == hashed.

    Extra keys (id, translations, timings, ...) stay put. Missing identity
    keys stay missing: they already hash as the model defaults, and filling
    them in would change the stored JSON shape of writers that omit them.
    Present identity keys are replaced with ``canonical_segment`` so a padded
    ``person_id`` cannot survive the write.
    """
    if not isinstance(segment, Mapping):
        return segment
    out = dict(cast(Mapping[str, Any], segment))
    kept = canonical_segment(segment)
    if isinstance(out.get('text'), str):
        out['text'] = kept.text
    if isinstance(out.get('speaker'), str):
        out['speaker'] = kept.speaker
    if 'person_id' in out and (out['person_id'] is None or isinstance(out['person_id'], str)):
        out['person_id'] = kept.person_id
    if 'speaker_id' in out:
        out['speaker_id'] = kept.speaker_id
    if 'is_user' in out:
        out['is_user'] = kept.is_user
    return out


def canonicalize_transcript_segments_for_storage(segments: list[Any]) -> list[Any]:
    """Canonicalize every segment dict in a list that is about to be stored."""
    return [canonicalize_segment_for_storage(segment) for segment in segments]


_MISSING = object()


def stored_transcript_is_canonical(segments: Iterable[Any]) -> bool:
    """True iff every hashed segment's stored identity already equals canonical.

    Missing / None / blank speaker, speaker_id, is_user, and person_id are
    the model defaults the hasher already applies, so those rows are canonical.
    A present string that still has surrounding whitespace is not: hashing
    would strip it and rendering would not. Empty-after-strip text is still a
    hashed segment, so its stored identity is checked the same way.
    """
    return all(_stored_segment_is_canonical(segment) for segment in segments)


def _raw_field(segment: Any, name: str) -> object:
    if isinstance(segment, Mapping):
        mapping = cast(Mapping[str, Any], segment)
        if name not in mapping:
            return _MISSING
        return mapping[name]
    if not hasattr(segment, name):
        return _MISSING
    return getattr(segment, name)


def _stored_segment_is_canonical(segment: Any) -> bool:
    kept = canonical_segment(segment)
    raw_text = _raw_field(segment, 'text')
    if not isinstance(raw_text, str) or raw_text != kept.text:
        return False
    raw_speaker = _raw_field(segment, 'speaker')
    if isinstance(raw_speaker, str) and raw_speaker != '' and raw_speaker != kept.speaker:
        return False
    raw_person_id = _raw_field(segment, 'person_id')
    if raw_person_id is _MISSING or raw_person_id is None or raw_person_id == '':
        if kept.person_id is not None:
            return False
    elif raw_person_id != kept.person_id:
        return False
    raw_speaker_id = _raw_field(segment, 'speaker_id')
    if raw_speaker_id is not _MISSING and raw_speaker_id is not None:
        if not isinstance(raw_speaker_id, int) or isinstance(raw_speaker_id, bool):
            return False
        if raw_speaker_id != kept.speaker_id:
            return False
    raw_is_user = _raw_field(segment, 'is_user')
    if raw_is_user is not _MISSING and raw_is_user is not None:
        if raw_is_user is not True and raw_is_user is not False:
            return False
        if (raw_is_user is True) != kept.is_user:
            return False
    return True


def transcript_sha256_for_binding(segments: Iterable[Any] | None) -> str | None:
    """Digest to compare with a client projection, or None to drop it.

    ``transcript_sha256`` strips, because clients hash JSON. A stored row with
    ``person_id`` ``" alice "`` would then match a digest of ``"alice"`` while
    still rendering Speaker 0. Binding must refuse that row: equal digests
    may imply identical rendered attribution only when the stored identity
    is already canonical.
    """
    items = list(segments or [])
    if not stored_transcript_is_canonical(items):
        return None
    return transcript_sha256(items)


def _frame(value: str) -> bytes:
    encoded = value.encode('utf-8')
    return f'{len(encoded)}\n'.encode('ascii') + encoded


def _canonical_transcript_bytes(parts: list[tuple[str, str, str, str, str]]) -> bytes:
    """v5 length-framed encoding: speaker, speaker_id, is_user, person_id, text."""
    return b''.join(
        _frame(speaker) + _frame(speaker_id) + _frame(is_user) + _frame(person_id) + _frame(text)
        for speaker, speaker_id, is_user, person_id, text in parts
    )


def _kept_segment_parts(segment: Any) -> tuple[str, str, str, str, str]:
    kept = canonical_segment(segment)
    return (
        kept.speaker,
        str(kept.speaker_id),
        IS_USER_TOKEN if kept.is_user else NOT_USER_TOKEN,
        kept.person_id or '',
        kept.text,
    )


def transcript_sha256(segments: Iterable[Any]) -> str:
    """SHA-256 hex digest over v5 length-framed identity+text tuples.

    Empty-after-strip text still contributes its identity frames. Accepts
    TranscriptSegment, request segment models (any object with ``.text`` /
    ``.speaker`` / ``.speaker_id`` / ``.is_user`` / ``.person_id``), and dicts
    with those keys. Order-sensitive. Identity is bound; timings are ignored.
    A re-identified transcript is expected not to verify. The framed bytes are
    the canonical stored identity, so a client hashing its JSON after the
    same strip/default rules lands on the digest of what the server persists.
    Binding a projection to a stored row must use
    ``transcript_sha256_for_binding``: this helper strips, and a legacy padded
    ``person_id`` would match while rendering Speaker 0.
    """
    parts = [_kept_segment_parts(segment) for segment in segments]
    return sha256(_canonical_transcript_bytes(parts)).hexdigest()
