"""The intake-context envelope raises typed deterministic faults.

``read_context`` was the last reader in the staged-audio decode family whose
raise sites stayed anonymous: every envelope fault escaped as a bare
``ValueError``, the same anonymous vocabulary prod books as
``error_class=ValueError stage=fetch_decode`` -- and the only vocabulary in
which Firestore commit contention also surfaces, so an anonymous envelope
fault and an exhausted transaction were separable only by a private
``error_type`` attribute. The family doctrine (``with_context``,
``decode_pcm16_wav``, ``capture_decode``, ``source_audio``) is that a fault
deterministic on the pinned stored bytes carries ``StagedAudioInvalid`` so
every downstream boundary reads the type.

Every fault here reproduces identically on a retry (same stored bytes, same
parse), so each must be exactly ``StagedAudioInvalid``: a ``ValueError``
subclass, so every existing ``except ValueError`` caller keeps catching it,
but never ``type(...) is ValueError``, so the contention discriminator that
matches bare ``ValueError`` exactly cannot misread an envelope fault as
transaction contention.

Failure-Class: FC-sync-decode-fault-anonymous-at-typed-boundaries
"""

import json
import struct

import pytest

from utils.batch_pipeline.audio import RATE, StagedAudioInvalid, audio_unit, read_context, with_context
from utils.batch_pipeline.contracts import INTAKE_CONTEXT_CHUNK, INTAKE_CONTEXT_LIMIT, INTAKE_CONTEXT_VERSION
from diarizer.batch_pipeline_models import StagedAudio


def _pcm16_wav(frames: int = 160) -> bytes:
    return audio_unit(1700000000.0, bytes((index % 31) for index in range(frames * 2))).wav


def _riff(body: bytes) -> bytes:
    """Re-seal the RIFF declared size so the envelope gate passes the walk through."""
    return body[:4] + struct.pack('<I', len(body) - 8) + body[8:]


def _chunk(name: bytes, payload: bytes) -> bytes:
    return name + struct.pack('<I', len(payload)) + payload + (b'\0' if len(payload) % 2 else b'')


def _context_body(context: dict) -> bytes:
    return with_context(_pcm16_wav(), context)


def _omim_start(body: bytes) -> int:
    return body.index(INTAKE_CONTEXT_CHUNK) + 8


def _rewrite_context(body: bytes, payload: bytes) -> bytes:
    start = _omim_start(body)
    size = struct.unpack('<I', body[start - 4 : start])[0]
    tail = body[start + size + (size % 2) :]
    rebuilt = (
        body[: start - 4] + struct.pack('<I', len(payload)) + payload + (b'\0' if len(payload) % 2 else b'') + tail
    )
    return _riff(rebuilt)


# --- read_context: every envelope fault is the typed family. ---


def test_read_context_non_riff_is_typed() -> None:
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(b'JUNK' + b'\0' * 32)
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_read_context_non_wave_is_typed() -> None:
    body = b'RIFF' + struct.pack('<I', 28) + b'JUNK' + b'\0' * 20
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(body)
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_read_context_wrong_riff_size_is_typed() -> None:
    body = bytearray(_pcm16_wav())
    body[4:8] = struct.pack('<I', len(body))
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(bytes(body))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_read_context_truncated_chunk_is_typed() -> None:
    truncated = _riff(_context_body({'source': 'omicapture'})[:-3])
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(truncated)
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_read_context_duplicate_context_is_typed() -> None:
    good = _context_body({'source': 'omicapture'})
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(good + _chunk(INTAKE_CONTEXT_CHUNK, b'null')))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'duplicate or oversized intake context'


def test_read_context_oversized_context_is_typed() -> None:
    oversized = _chunk(INTAKE_CONTEXT_CHUNK, b'"' + b'a' * INTAKE_CONTEXT_LIMIT + b'"')
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(_pcm16_wav() + oversized))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'duplicate or oversized intake context'


def test_read_context_oversized_context_at_limit_plus_one_is_typed() -> None:
    payload = json.dumps({'pad': 'x' * INTAKE_CONTEXT_LIMIT}).encode()
    assert len(payload) > INTAKE_CONTEXT_LIMIT
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(_pcm16_wav() + _chunk(INTAKE_CONTEXT_CHUNK, payload)))
    assert type(caught.value) is StagedAudioInvalid


def test_read_context_missing_context_is_typed() -> None:
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_pcm16_wav())
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_read_context_wrong_version_is_typed() -> None:
    payload = json.dumps({'source': 'omicapture', 'version': INTAKE_CONTEXT_VERSION + 1}).encode()
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(_pcm16_wav() + _chunk(INTAKE_CONTEXT_CHUNK, payload)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_read_context_missing_version_is_typed() -> None:
    payload = json.dumps({'source': 'omicapture'}).encode()
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(_pcm16_wav() + _chunk(INTAKE_CONTEXT_CHUNK, payload)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_read_context_non_dict_context_is_typed() -> None:
    body = _rewrite_context(_context_body({'source': 'x'}), b'[]')
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(body)
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_read_context_scalar_context_is_typed() -> None:
    body = _rewrite_context(_context_body({'source': 'x'}), b'42')
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(body)
    assert type(caught.value) is StagedAudioInvalid


def test_read_context_corrupt_json_is_typed() -> None:
    corrupted = bytearray(_context_body({'source': 'omicapture'}))
    start = _omim_start(corrupted)
    corrupted[start : start + 2] = b'{,'
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(bytes(corrupted))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_read_context_invalid_utf8_json_is_typed() -> None:
    body = _rewrite_context(_context_body({'source': 'x'}), b'{"source": "\xff\xfe"}')
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(body)
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_read_context_deeply_nested_json_is_typed() -> None:
    payload = (b'[' * 20000) + (b']' * 20000)
    body = _rewrite_context(_context_body({'source': 'x'}), payload)
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(body)
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_read_context_trailing_garbage_is_typed() -> None:
    good = _context_body({'source': 'omicapture'})
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(good + b'\x01\x02'))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_read_context_unknown_chunk_is_tolerated() -> None:
    """Unknown chunks skip whole (with their pad byte); the context still reads."""
    context = {'source': 'omicapture', 'client_device_id': 'dev-1'}
    good = _context_body(context)
    prefix = _pcm16_wav() + _chunk(b'AAAA', b'\x01\x02\x03')
    body = _riff(prefix + good[len(_pcm16_wav()) :])
    assert read_context(body) == {**context, 'version': INTAKE_CONTEXT_VERSION}


def test_typed_fault_is_value_error_subclass() -> None:
    assert issubclass(StagedAudioInvalid, ValueError)


def test_typed_fault_is_never_bare_value_error() -> None:
    """Firestore contention surfaces as ``type(e) is ValueError``; envelopes must not."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(b'JUNK' + b'\0' * 32)
    assert type(caught.value) is not ValueError


# --- with_context <-> read_context round trip. ---


def test_round_trip_preserves_context_and_stamps_version() -> None:
    context = {'source': 'omicapture', 'client_device_id': 'dev-1', 'should_lock': True}
    body = with_context(_pcm16_wav(), context)
    assert read_context(body) == {**context, 'version': INTAKE_CONTEXT_VERSION}


def test_round_trip_sorts_keys_deterministically() -> None:
    a = with_context(_pcm16_wav(), {'b': 1, 'a': 2})
    b = with_context(_pcm16_wav(), {'a': 2, 'b': 1})
    assert a == b
    assert read_context(a) == {'a': 2, 'b': 1, 'version': INTAKE_CONTEXT_VERSION}


def test_with_context_nan_is_typed() -> None:
    with pytest.raises(StagedAudioInvalid) as caught:
        with_context(_pcm16_wav(), {'score': float('nan')})
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid bounded intake context or WAV'


def test_with_context_non_riff_is_typed() -> None:
    with pytest.raises(StagedAudioInvalid) as caught:
        with_context(b'JUNK' + b'\0' * 32, {'source': 'x'})
    assert type(caught.value) is StagedAudioInvalid


def test_with_context_oversized_body_is_typed() -> None:
    with pytest.raises(StagedAudioInvalid) as caught:
        with_context(_pcm16_wav(), {'pad': 'x' * INTAKE_CONTEXT_LIMIT})
    assert type(caught.value) is StagedAudioInvalid


# --- StagedAudio._decode: typed envelope faults keep the fail-open context. ---


class _Item:
    """The identity surface StagedAudio reads; conversation units own their stream."""

    unit_kind = 'conversation'
    conversation_id = 'conv-1'
    duration_seconds = 0.01
    owner_id = 'owner'
    segment_id = 'seg'
    shadow = False


def test_decode_fail_open_on_typed_envelope_fault() -> None:
    """A rejected context version degrades identity only; the audio still decodes."""
    item = _Item()
    staged = StagedAudio(lambda it: _context_body({'source': 'omicapture', 'version': 99}))
    samples = staged.decode(item)
    assert len(samples) == 160
    assert staged.language(item) is None
    assert staged.stream(item) == 'conversation:conv-1'


def test_decode_container_fault_is_typed_not_swallowed() -> None:
    staged = StagedAudio(lambda item: b'JUNK' + b'\0' * 32)
    with pytest.raises(StagedAudioInvalid) as caught:
        staged.decode(_Item())
    assert str(caught.value) == 'invalid staged WAV container'


def test_decode_truncated_chunk_still_decodes_audio() -> None:
    good = _context_body({'source': 'omicapture'})
    staged = StagedAudio(lambda item: good[:-3])
    samples = staged.decode(_Item())
    assert len(samples) == 160


def test_decode_valid_context_feeds_stream_identity() -> None:
    context = {'source': 'omicapture', 'client_device_id': 'dev-9', 'should_lock': False}
    item = _Item()
    staged = StagedAudio(lambda it: with_context(_pcm16_wav(), context))
    samples = staged.decode(item)
    assert len(samples) == 160
    assert staged.stream(item) == 'conversation:conv-1'
    assert staged.language(item) is None


def test_pcm16_rate_is_the_family_constant() -> None:
    assert RATE == 16000
