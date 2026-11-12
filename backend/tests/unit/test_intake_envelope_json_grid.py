"""Intake envelope payload JSON parse grid: frozen verdict per cell.

``read_context`` is the intake envelope's strict reader. This grid pins its
verdict surface one cell at a time: each cell's expected verdict was computed
by an independent restatement of the documented chunk grammar (sealed RIFF
size, chunk walk with pad-byte skip, single bounded ``OMIM`` chunk,
authenticated versioned JSON object), cross-checked against the reader, and
frozen here as literals. A cell that fails means the reader drifted from the
documented grammar.

Every deterministic fault carries ``StagedAudioInvalid`` -- the family type
the fetch_decode boundary reads -- and stays a ``ValueError`` subclass so
every legacy ``except ValueError`` caller keeps catching it.

Failure-Class: FC-sync-decode-fault-anonymous-at-typed-boundaries
"""

import json
import struct

import pytest

from utils.batch_pipeline.audio import RATE, StagedAudioInvalid, audio_unit, read_context, with_context
from utils.batch_pipeline.contracts import INTAKE_CONTEXT_CHUNK, INTAKE_CONTEXT_LIMIT, INTAKE_CONTEXT_VERSION

_BASE_CONTEXT = {'source': 'omicapture', 'client_device_id': 'dev-grid-1', 'should_lock': True}

BASE_CONTEXT = _BASE_CONTEXT


def _pcm16_wav(frames: int = 160) -> bytes:
    return audio_unit(1700000000.0, bytes((index % 31) for index in range(frames * 2))).wav


def _riff(body: bytes) -> bytes:
    return body[:4] + struct.pack('<I', len(body) - 8) + body[8:]


def _chunk(name: bytes, payload: bytes) -> bytes:
    return name + struct.pack('<I', len(payload)) + payload + (b'\0' if len(payload) % 2 else b'')


def _omim_start(body: bytes) -> int:
    return body.index(INTAKE_CONTEXT_CHUNK) + 8


def _payload(body: bytes) -> bytes:
    start = _omim_start(body)
    size = struct.unpack('<I', body[start - 4 : start])[0]
    return body[start : start + size]


def _rewrite(body: bytes, payload: bytes) -> bytes:
    start = _omim_start(body)
    size = struct.unpack('<I', body[start - 4 : start])[0]
    tail = body[start + size + (size % 2) :]
    rebuilt = (
        body[: start - 4] + struct.pack('<I', len(payload)) + payload + (b'\0' if len(payload) % 2 else b'') + tail
    )
    return _riff(rebuilt)


def _flip(index: int, mask: int) -> bytes:
    payload = _payload(_LONG)
    return payload[:index] + bytes([payload[index] ^ mask]) + payload[index + 1 :]


def _bset(body: bytes, index: int, value: int) -> bytes:
    mutated = bytearray(body)
    mutated[index] = value
    return bytes(mutated)


def _resize(body: bytes, delta: int) -> bytes:
    return body[:4] + struct.pack('<I', (len(body) - 8 + delta) & 0xFFFFFFFF) + body[8:]


def _deep_context(depth: int) -> dict:
    node = {'leaf': True}
    for _ in range(depth):
        node = {'in': node}
    return node


_BASE = with_context(_pcm16_wav(), _BASE_CONTEXT)
_LONG = with_context(
    _pcm16_wav(),
    {
        'source': 'omicapture',
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'should_lock': True,
        'note': 'x' * 300,
    },
)
_LONG_BASE = with_context(_pcm16_wav(3200), _BASE_CONTEXT)
_WAV = _pcm16_wav()
base = _BASE
long = _LONG
longbase = _LONG_BASE
wav = _WAV


def test_json_flip000x01_typed() -> None:
    """context payload byte 0 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(0, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip000x20_typed() -> None:
    """context payload byte 0 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(0, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip000x80_typed() -> None:
    """context payload byte 0 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(0, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip001x01_typed() -> None:
    """context payload byte 1 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(1, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip001x20_typed() -> None:
    """context payload byte 1 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(1, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip001x80_typed() -> None:
    """context payload byte 1 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(1, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip002x01_roundtrip() -> None:
    """context payload byte 2 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(2, 0x01))) == {
        'blient_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip002x20_roundtrip() -> None:
    """context payload byte 2 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(2, 0x20))) == {
        'Client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip002x80_typed() -> None:
    """context payload byte 2 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(2, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip003x01_roundtrip() -> None:
    """context payload byte 3 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(3, 0x01))) == {
        'cmient_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip003x20_roundtrip() -> None:
    """context payload byte 3 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(3, 0x20))) == {
        'cLient_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip003x80_typed() -> None:
    """context payload byte 3 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(3, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip004x01_roundtrip() -> None:
    """context payload byte 4 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(4, 0x01))) == {
        'clhent_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip004x20_roundtrip() -> None:
    """context payload byte 4 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(4, 0x20))) == {
        'clIent_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip004x80_typed() -> None:
    """context payload byte 4 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(4, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip005x01_roundtrip() -> None:
    """context payload byte 5 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(5, 0x01))) == {
        'clidnt_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip005x20_roundtrip() -> None:
    """context payload byte 5 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(5, 0x20))) == {
        'cliEnt_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip005x80_typed() -> None:
    """context payload byte 5 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(5, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip006x01_roundtrip() -> None:
    """context payload byte 6 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(6, 0x01))) == {
        'clieot_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip006x20_roundtrip() -> None:
    """context payload byte 6 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(6, 0x20))) == {
        'clieNt_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip006x80_typed() -> None:
    """context payload byte 6 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(6, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip007x01_roundtrip() -> None:
    """context payload byte 7 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(7, 0x01))) == {
        'clienu_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip007x20_roundtrip() -> None:
    """context payload byte 7 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(7, 0x20))) == {
        'clienT_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip007x80_typed() -> None:
    """context payload byte 7 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(7, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip008x01_roundtrip() -> None:
    """context payload byte 8 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(8, 0x01))) == {
        'client^device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip008x20_roundtrip() -> None:
    """context payload byte 8 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(8, 0x20))) == {
        'client\x7fdevice_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip008x80_typed() -> None:
    """context payload byte 8 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(8, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip009x01_roundtrip() -> None:
    """context payload byte 9 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(9, 0x01))) == {
        'client_eevice_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip009x20_roundtrip() -> None:
    """context payload byte 9 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(9, 0x20))) == {
        'client_Device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip009x80_typed() -> None:
    """context payload byte 9 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(9, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip010x01_roundtrip() -> None:
    """context payload byte 10 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(10, 0x01))) == {
        'client_ddvice_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip010x20_roundtrip() -> None:
    """context payload byte 10 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(10, 0x20))) == {
        'client_dEvice_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip010x80_typed() -> None:
    """context payload byte 10 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(10, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip011x01_roundtrip() -> None:
    """context payload byte 11 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(11, 0x01))) == {
        'client_dewice_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip011x20_roundtrip() -> None:
    """context payload byte 11 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(11, 0x20))) == {
        'client_deVice_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip011x80_typed() -> None:
    """context payload byte 11 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(11, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip012x01_roundtrip() -> None:
    """context payload byte 12 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(12, 0x01))) == {
        'client_devhce_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip012x20_roundtrip() -> None:
    """context payload byte 12 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(12, 0x20))) == {
        'client_devIce_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip012x80_typed() -> None:
    """context payload byte 12 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(12, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip013x01_roundtrip() -> None:
    """context payload byte 13 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(13, 0x01))) == {
        'client_devibe_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip013x20_roundtrip() -> None:
    """context payload byte 13 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(13, 0x20))) == {
        'client_deviCe_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip013x80_typed() -> None:
    """context payload byte 13 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(13, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip014x01_roundtrip() -> None:
    """context payload byte 14 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(14, 0x01))) == {
        'client_devicd_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip014x20_roundtrip() -> None:
    """context payload byte 14 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(14, 0x20))) == {
        'client_devicE_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip014x80_typed() -> None:
    """context payload byte 14 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(14, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip015x01_roundtrip() -> None:
    """context payload byte 15 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(15, 0x01))) == {
        'client_device^id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip015x20_roundtrip() -> None:
    """context payload byte 15 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(15, 0x20))) == {
        'client_device\x7fid': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip015x80_typed() -> None:
    """context payload byte 15 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(15, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip016x01_roundtrip() -> None:
    """context payload byte 16 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(16, 0x01))) == {
        'client_device_hd': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip016x20_roundtrip() -> None:
    """context payload byte 16 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(16, 0x20))) == {
        'client_device_Id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip016x80_typed() -> None:
    """context payload byte 16 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(16, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip017x01_roundtrip() -> None:
    """context payload byte 17 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(17, 0x01))) == {
        'client_device_ie': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip017x20_roundtrip() -> None:
    """context payload byte 17 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(17, 0x20))) == {
        'client_device_iD': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip017x80_typed() -> None:
    """context payload byte 17 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(17, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip018x01_typed() -> None:
    """context payload byte 18 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(18, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip018x20_typed() -> None:
    """context payload byte 18 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(18, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip018x80_typed() -> None:
    """context payload byte 18 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(18, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip019x01_typed() -> None:
    """context payload byte 19 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(19, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip019x20_typed() -> None:
    """context payload byte 19 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(19, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip019x80_typed() -> None:
    """context payload byte 19 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(19, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip020x01_typed() -> None:
    """context payload byte 20 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(20, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip020x20_typed() -> None:
    """context payload byte 20 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(20, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip020x80_typed() -> None:
    """context payload byte 20 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(20, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip021x01_roundtrip() -> None:
    """context payload byte 21 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(21, 0x01))) == {
        'client_device_id': 'eevice-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip021x20_roundtrip() -> None:
    """context payload byte 21 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(21, 0x20))) == {
        'client_device_id': 'Device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip021x80_typed() -> None:
    """context payload byte 21 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(21, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip022x01_roundtrip() -> None:
    """context payload byte 22 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(22, 0x01))) == {
        'client_device_id': 'ddvice-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip022x20_roundtrip() -> None:
    """context payload byte 22 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(22, 0x20))) == {
        'client_device_id': 'dEvice-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip022x80_typed() -> None:
    """context payload byte 22 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(22, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip023x01_roundtrip() -> None:
    """context payload byte 23 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(23, 0x01))) == {
        'client_device_id': 'dewice-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip023x20_roundtrip() -> None:
    """context payload byte 23 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(23, 0x20))) == {
        'client_device_id': 'deVice-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip023x80_typed() -> None:
    """context payload byte 23 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(23, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip024x01_roundtrip() -> None:
    """context payload byte 24 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(24, 0x01))) == {
        'client_device_id': 'devhce-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip024x20_roundtrip() -> None:
    """context payload byte 24 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(24, 0x20))) == {
        'client_device_id': 'devIce-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip024x80_typed() -> None:
    """context payload byte 24 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(24, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip025x01_roundtrip() -> None:
    """context payload byte 25 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(25, 0x01))) == {
        'client_device_id': 'devibe-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip025x20_roundtrip() -> None:
    """context payload byte 25 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(25, 0x20))) == {
        'client_device_id': 'deviCe-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip025x80_typed() -> None:
    """context payload byte 25 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(25, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip026x01_roundtrip() -> None:
    """context payload byte 26 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(26, 0x01))) == {
        'client_device_id': 'devicd-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip026x20_roundtrip() -> None:
    """context payload byte 26 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(26, 0x20))) == {
        'client_device_id': 'devicE-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip026x80_typed() -> None:
    """context payload byte 26 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(26, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip027x01_roundtrip() -> None:
    """context payload byte 27 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(27, 0x01))) == {
        'client_device_id': 'device,with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip027x20_typed() -> None:
    """context payload byte 27 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(27, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip027x80_typed() -> None:
    """context payload byte 27 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(27, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip028x01_roundtrip() -> None:
    """context payload byte 28 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(28, 0x01))) == {
        'client_device_id': 'device-vith-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip028x20_roundtrip() -> None:
    """context payload byte 28 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(28, 0x20))) == {
        'client_device_id': 'device-With-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip028x80_typed() -> None:
    """context payload byte 28 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(28, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip029x01_roundtrip() -> None:
    """context payload byte 29 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(29, 0x01))) == {
        'client_device_id': 'device-whth-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip029x20_roundtrip() -> None:
    """context payload byte 29 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(29, 0x20))) == {
        'client_device_id': 'device-wIth-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip029x80_typed() -> None:
    """context payload byte 29 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(29, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip030x01_roundtrip() -> None:
    """context payload byte 30 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(30, 0x01))) == {
        'client_device_id': 'device-wiuh-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip030x20_roundtrip() -> None:
    """context payload byte 30 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(30, 0x20))) == {
        'client_device_id': 'device-wiTh-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip030x80_typed() -> None:
    """context payload byte 30 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(30, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip031x01_roundtrip() -> None:
    """context payload byte 31 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(31, 0x01))) == {
        'client_device_id': 'device-witi-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip031x20_roundtrip() -> None:
    """context payload byte 31 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(31, 0x20))) == {
        'client_device_id': 'device-witH-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip031x80_typed() -> None:
    """context payload byte 31 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(31, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip032x01_roundtrip() -> None:
    """context payload byte 32 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(32, 0x01))) == {
        'client_device_id': 'device-with,a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip032x20_typed() -> None:
    """context payload byte 32 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(32, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip032x80_typed() -> None:
    """context payload byte 32 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(32, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip033x01_roundtrip() -> None:
    """context payload byte 33 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(33, 0x01))) == {
        'client_device_id': 'device-with-`-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip033x20_roundtrip() -> None:
    """context payload byte 33 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(33, 0x20))) == {
        'client_device_id': 'device-with-A-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip033x80_typed() -> None:
    """context payload byte 33 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(33, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip034x01_roundtrip() -> None:
    """context payload byte 34 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(34, 0x01))) == {
        'client_device_id': 'device-with-a,fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip034x20_typed() -> None:
    """context payload byte 34 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(34, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip034x80_typed() -> None:
    """context payload byte 34 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(34, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip035x01_roundtrip() -> None:
    """context payload byte 35 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(35, 0x01))) == {
        'client_device_id': 'device-with-a-gairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip035x20_roundtrip() -> None:
    """context payload byte 35 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(35, 0x20))) == {
        'client_device_id': 'device-with-a-Fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip035x80_typed() -> None:
    """context payload byte 35 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(35, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip036x01_roundtrip() -> None:
    """context payload byte 36 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(36, 0x01))) == {
        'client_device_id': 'device-with-a-f`irly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip036x20_roundtrip() -> None:
    """context payload byte 36 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(36, 0x20))) == {
        'client_device_id': 'device-with-a-fAirly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip036x80_typed() -> None:
    """context payload byte 36 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(36, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip037x01_roundtrip() -> None:
    """context payload byte 37 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(37, 0x01))) == {
        'client_device_id': 'device-with-a-fahrly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip037x20_roundtrip() -> None:
    """context payload byte 37 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(37, 0x20))) == {
        'client_device_id': 'device-with-a-faIrly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip037x80_typed() -> None:
    """context payload byte 37 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(37, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip038x01_roundtrip() -> None:
    """context payload byte 38 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(38, 0x01))) == {
        'client_device_id': 'device-with-a-faisly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip038x20_roundtrip() -> None:
    """context payload byte 38 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(38, 0x20))) == {
        'client_device_id': 'device-with-a-faiRly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip038x80_typed() -> None:
    """context payload byte 38 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(38, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip039x01_roundtrip() -> None:
    """context payload byte 39 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(39, 0x01))) == {
        'client_device_id': 'device-with-a-fairmy-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip039x20_roundtrip() -> None:
    """context payload byte 39 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(39, 0x20))) == {
        'client_device_id': 'device-with-a-fairLy-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip039x80_typed() -> None:
    """context payload byte 39 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(39, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip040x01_roundtrip() -> None:
    """context payload byte 40 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(40, 0x01))) == {
        'client_device_id': 'device-with-a-fairlx-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip040x20_roundtrip() -> None:
    """context payload byte 40 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(40, 0x20))) == {
        'client_device_id': 'device-with-a-fairlY-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip040x80_typed() -> None:
    """context payload byte 40 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(40, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip041x01_roundtrip() -> None:
    """context payload byte 41 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(41, 0x01))) == {
        'client_device_id': 'device-with-a-fairly,long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip041x20_typed() -> None:
    """context payload byte 41 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(41, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip041x80_typed() -> None:
    """context payload byte 41 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(41, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip042x01_roundtrip() -> None:
    """context payload byte 42 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(42, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-mong-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip042x20_roundtrip() -> None:
    """context payload byte 42 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(42, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-Long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip042x80_typed() -> None:
    """context payload byte 42 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(42, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip043x01_roundtrip() -> None:
    """context payload byte 43 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(43, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-lnng-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip043x20_roundtrip() -> None:
    """context payload byte 43 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(43, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-lOng-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip043x80_typed() -> None:
    """context payload byte 43 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(43, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip044x01_roundtrip() -> None:
    """context payload byte 44 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(44, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-loog-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip044x20_roundtrip() -> None:
    """context payload byte 44 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(44, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-loNg-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip044x80_typed() -> None:
    """context payload byte 44 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(44, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip045x01_roundtrip() -> None:
    """context payload byte 45 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(45, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-lonf-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip045x20_roundtrip() -> None:
    """context payload byte 45 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(45, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-lonG-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip045x80_typed() -> None:
    """context payload byte 45 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(45, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip046x01_roundtrip() -> None:
    """context payload byte 46 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(46, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long,identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip046x20_typed() -> None:
    """context payload byte 46 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(46, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip046x80_typed() -> None:
    """context payload byte 46 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(46, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip047x01_roundtrip() -> None:
    """context payload byte 47 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(47, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-hdentifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip047x20_roundtrip() -> None:
    """context payload byte 47 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(47, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-Identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip047x80_typed() -> None:
    """context payload byte 47 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(47, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip048x01_roundtrip() -> None:
    """context payload byte 48 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(48, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-ieentifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip048x20_roundtrip() -> None:
    """context payload byte 48 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(48, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-iDentifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip048x80_typed() -> None:
    """context payload byte 48 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(48, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip049x01_roundtrip() -> None:
    """context payload byte 49 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(49, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-iddntifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip049x20_roundtrip() -> None:
    """context payload byte 49 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(49, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-idEntifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip049x80_typed() -> None:
    """context payload byte 49 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(49, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip050x01_roundtrip() -> None:
    """context payload byte 50 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(50, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-ideotifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip050x20_roundtrip() -> None:
    """context payload byte 50 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(50, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-ideNtifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip050x80_typed() -> None:
    """context payload byte 50 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(50, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip051x01_roundtrip() -> None:
    """context payload byte 51 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(51, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-idenuifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip051x20_roundtrip() -> None:
    """context payload byte 51 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(51, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-idenTifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip051x80_typed() -> None:
    """context payload byte 51 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(51, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip052x01_roundtrip() -> None:
    """context payload byte 52 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(52, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identhfier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip052x20_roundtrip() -> None:
    """context payload byte 52 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(52, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identIfier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip052x80_typed() -> None:
    """context payload byte 52 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(52, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip053x01_roundtrip() -> None:
    """context payload byte 53 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(53, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identigier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip053x20_roundtrip() -> None:
    """context payload byte 53 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(53, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identiFier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip053x80_typed() -> None:
    """context payload byte 53 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(53, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip054x01_roundtrip() -> None:
    """context payload byte 54 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(54, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifher-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip054x20_roundtrip() -> None:
    """context payload byte 54 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(54, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifIer-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip054x80_typed() -> None:
    """context payload byte 54 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(54, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip055x01_roundtrip() -> None:
    """context payload byte 55 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(55, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifidr-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip055x20_roundtrip() -> None:
    """context payload byte 55 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(55, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifiEr-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip055x80_typed() -> None:
    """context payload byte 55 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(55, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip056x01_roundtrip() -> None:
    """context payload byte 56 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(56, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifies-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip056x20_roundtrip() -> None:
    """context payload byte 56 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(56, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifieR-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip056x80_typed() -> None:
    """context payload byte 56 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(56, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip057x01_roundtrip() -> None:
    """context payload byte 57 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(57, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier,string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip057x20_typed() -> None:
    """context payload byte 57 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(57, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip057x80_typed() -> None:
    """context payload byte 57 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(57, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip058x01_roundtrip() -> None:
    """context payload byte 58 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(58, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-rtring-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip058x20_roundtrip() -> None:
    """context payload byte 58 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(58, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-String-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip058x80_typed() -> None:
    """context payload byte 58 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(58, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip059x01_roundtrip() -> None:
    """context payload byte 59 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(59, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-suring-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip059x20_roundtrip() -> None:
    """context payload byte 59 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(59, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-sTring-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip059x80_typed() -> None:
    """context payload byte 59 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(59, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip060x01_roundtrip() -> None:
    """context payload byte 60 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(60, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-stsing-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip060x20_roundtrip() -> None:
    """context payload byte 60 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(60, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-stRing-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip060x80_typed() -> None:
    """context payload byte 60 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(60, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip061x01_roundtrip() -> None:
    """context payload byte 61 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(61, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-strhng-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip061x20_roundtrip() -> None:
    """context payload byte 61 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(61, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-strIng-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip061x80_typed() -> None:
    """context payload byte 61 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(61, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip062x01_roundtrip() -> None:
    """context payload byte 62 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(62, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-striog-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip062x20_roundtrip() -> None:
    """context payload byte 62 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(62, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-striNg-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip062x80_typed() -> None:
    """context payload byte 62 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(62, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip063x01_roundtrip() -> None:
    """context payload byte 63 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(63, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-strinf-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip063x20_roundtrip() -> None:
    """context payload byte 63 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(63, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-strinG-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip063x80_typed() -> None:
    """context payload byte 63 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(63, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip064x01_roundtrip() -> None:
    """context payload byte 64 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(64, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string,0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip064x20_typed() -> None:
    """context payload byte 64 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(64, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip064x80_typed() -> None:
    """context payload byte 64 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(64, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip065x01_roundtrip() -> None:
    """context payload byte 65 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(65, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-1001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip065x20_typed() -> None:
    """context payload byte 65 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(65, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip065x80_typed() -> None:
    """context payload byte 65 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(65, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip066x01_roundtrip() -> None:
    """context payload byte 66 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(66, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0101',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip066x20_typed() -> None:
    """context payload byte 66 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(66, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip066x80_typed() -> None:
    """context payload byte 66 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(66, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip067x01_roundtrip() -> None:
    """context payload byte 67 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(67, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0011',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip067x20_typed() -> None:
    """context payload byte 67 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(67, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip067x80_typed() -> None:
    """context payload byte 67 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(67, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip068x01_roundtrip() -> None:
    """context payload byte 68 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(68, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0000',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip068x20_typed() -> None:
    """context payload byte 68 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(68, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip068x80_typed() -> None:
    """context payload byte 68 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(68, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip069x01_typed() -> None:
    """context payload byte 69 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(69, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip069x20_typed() -> None:
    """context payload byte 69 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(69, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip069x80_typed() -> None:
    """context payload byte 69 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(69, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip070x01_typed() -> None:
    """context payload byte 70 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(70, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip070x20_typed() -> None:
    """context payload byte 70 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(70, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip070x80_typed() -> None:
    """context payload byte 70 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(70, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip071x01_typed() -> None:
    """context payload byte 71 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(71, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip071x20_typed() -> None:
    """context payload byte 71 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(71, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip071x80_typed() -> None:
    """context payload byte 71 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(71, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip072x01_roundtrip() -> None:
    """context payload byte 72 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(72, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'oote': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip072x20_roundtrip() -> None:
    """context payload byte 72 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(72, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'Note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip072x80_typed() -> None:
    """context payload byte 72 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(72, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip073x01_roundtrip() -> None:
    """context payload byte 73 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(73, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'nnte': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip073x20_roundtrip() -> None:
    """context payload byte 73 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(73, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'nOte': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip073x80_typed() -> None:
    """context payload byte 73 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(73, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip074x01_roundtrip() -> None:
    """context payload byte 74 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(74, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'noue': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip074x20_roundtrip() -> None:
    """context payload byte 74 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(74, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'noTe': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip074x80_typed() -> None:
    """context payload byte 74 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(74, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip075x01_roundtrip() -> None:
    """context payload byte 75 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(75, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'notd': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip075x20_roundtrip() -> None:
    """context payload byte 75 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(75, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'notE': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip075x80_typed() -> None:
    """context payload byte 75 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(75, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip076x01_typed() -> None:
    """context payload byte 76 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(76, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip076x20_typed() -> None:
    """context payload byte 76 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(76, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip076x80_typed() -> None:
    """context payload byte 76 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(76, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip077x01_typed() -> None:
    """context payload byte 77 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(77, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip077x20_typed() -> None:
    """context payload byte 77 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(77, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip077x80_typed() -> None:
    """context payload byte 77 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(77, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip078x01_typed() -> None:
    """context payload byte 78 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(78, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip078x20_typed() -> None:
    """context payload byte 78 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(78, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip078x80_typed() -> None:
    """context payload byte 78 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(78, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip079x01_roundtrip() -> None:
    """context payload byte 79 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(79, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'yxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip079x20_roundtrip() -> None:
    """context payload byte 79 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(79, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'Xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip079x80_typed() -> None:
    """context payload byte 79 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(79, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip080x01_roundtrip() -> None:
    """context payload byte 80 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(80, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip080x20_roundtrip() -> None:
    """context payload byte 80 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(80, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip080x80_typed() -> None:
    """context payload byte 80 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(80, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip081x01_roundtrip() -> None:
    """context payload byte 81 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(81, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip081x20_roundtrip() -> None:
    """context payload byte 81 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(81, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip081x80_typed() -> None:
    """context payload byte 81 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(81, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip082x01_roundtrip() -> None:
    """context payload byte 82 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(82, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip082x20_roundtrip() -> None:
    """context payload byte 82 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(82, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip082x80_typed() -> None:
    """context payload byte 82 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(82, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip083x01_roundtrip() -> None:
    """context payload byte 83 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(83, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip083x20_roundtrip() -> None:
    """context payload byte 83 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(83, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip083x80_typed() -> None:
    """context payload byte 83 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(83, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip084x01_roundtrip() -> None:
    """context payload byte 84 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(84, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip084x20_roundtrip() -> None:
    """context payload byte 84 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(84, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip084x80_typed() -> None:
    """context payload byte 84 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(84, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip085x01_roundtrip() -> None:
    """context payload byte 85 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(85, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip085x20_roundtrip() -> None:
    """context payload byte 85 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(85, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip085x80_typed() -> None:
    """context payload byte 85 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(85, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip086x01_roundtrip() -> None:
    """context payload byte 86 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(86, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip086x20_roundtrip() -> None:
    """context payload byte 86 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(86, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip086x80_typed() -> None:
    """context payload byte 86 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(86, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip087x01_roundtrip() -> None:
    """context payload byte 87 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(87, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip087x20_roundtrip() -> None:
    """context payload byte 87 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(87, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip087x80_typed() -> None:
    """context payload byte 87 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(87, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip088x01_roundtrip() -> None:
    """context payload byte 88 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(88, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip088x20_roundtrip() -> None:
    """context payload byte 88 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(88, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip088x80_typed() -> None:
    """context payload byte 88 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(88, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip089x01_roundtrip() -> None:
    """context payload byte 89 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(89, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip089x20_roundtrip() -> None:
    """context payload byte 89 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(89, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip089x80_typed() -> None:
    """context payload byte 89 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(89, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip090x01_roundtrip() -> None:
    """context payload byte 90 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(90, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip090x20_roundtrip() -> None:
    """context payload byte 90 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(90, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip090x80_typed() -> None:
    """context payload byte 90 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(90, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip091x01_roundtrip() -> None:
    """context payload byte 91 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(91, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip091x20_roundtrip() -> None:
    """context payload byte 91 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(91, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip091x80_typed() -> None:
    """context payload byte 91 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(91, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip092x01_roundtrip() -> None:
    """context payload byte 92 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(92, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip092x20_roundtrip() -> None:
    """context payload byte 92 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(92, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip092x80_typed() -> None:
    """context payload byte 92 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(92, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip093x01_roundtrip() -> None:
    """context payload byte 93 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(93, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip093x20_roundtrip() -> None:
    """context payload byte 93 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(93, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip093x80_typed() -> None:
    """context payload byte 93 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(93, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip094x01_roundtrip() -> None:
    """context payload byte 94 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(94, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip094x20_roundtrip() -> None:
    """context payload byte 94 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(94, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip094x80_typed() -> None:
    """context payload byte 94 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(94, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip095x01_roundtrip() -> None:
    """context payload byte 95 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(95, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip095x20_roundtrip() -> None:
    """context payload byte 95 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(95, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip095x80_typed() -> None:
    """context payload byte 95 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(95, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip096x01_roundtrip() -> None:
    """context payload byte 96 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(96, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip096x20_roundtrip() -> None:
    """context payload byte 96 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(96, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip096x80_typed() -> None:
    """context payload byte 96 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(96, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip097x01_roundtrip() -> None:
    """context payload byte 97 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(97, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip097x20_roundtrip() -> None:
    """context payload byte 97 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(97, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip097x80_typed() -> None:
    """context payload byte 97 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(97, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip098x01_roundtrip() -> None:
    """context payload byte 98 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(98, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip098x20_roundtrip() -> None:
    """context payload byte 98 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(98, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip098x80_typed() -> None:
    """context payload byte 98 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(98, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip099x01_roundtrip() -> None:
    """context payload byte 99 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(99, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip099x20_roundtrip() -> None:
    """context payload byte 99 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(99, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip099x80_typed() -> None:
    """context payload byte 99 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(99, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip100x01_roundtrip() -> None:
    """context payload byte 100 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(100, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip100x20_roundtrip() -> None:
    """context payload byte 100 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(100, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip100x80_typed() -> None:
    """context payload byte 100 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(100, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip101x01_roundtrip() -> None:
    """context payload byte 101 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(101, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip101x20_roundtrip() -> None:
    """context payload byte 101 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(101, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip101x80_typed() -> None:
    """context payload byte 101 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(101, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip102x01_roundtrip() -> None:
    """context payload byte 102 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(102, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip102x20_roundtrip() -> None:
    """context payload byte 102 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(102, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip102x80_typed() -> None:
    """context payload byte 102 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(102, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip103x01_roundtrip() -> None:
    """context payload byte 103 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(103, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip103x20_roundtrip() -> None:
    """context payload byte 103 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(103, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip103x80_typed() -> None:
    """context payload byte 103 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(103, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip104x01_roundtrip() -> None:
    """context payload byte 104 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(104, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip104x20_roundtrip() -> None:
    """context payload byte 104 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(104, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip104x80_typed() -> None:
    """context payload byte 104 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(104, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip105x01_roundtrip() -> None:
    """context payload byte 105 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(105, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip105x20_roundtrip() -> None:
    """context payload byte 105 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(105, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip105x80_typed() -> None:
    """context payload byte 105 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(105, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip106x01_roundtrip() -> None:
    """context payload byte 106 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(106, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip106x20_roundtrip() -> None:
    """context payload byte 106 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(106, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip106x80_typed() -> None:
    """context payload byte 106 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(106, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip107x01_roundtrip() -> None:
    """context payload byte 107 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(107, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip107x20_roundtrip() -> None:
    """context payload byte 107 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(107, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip107x80_typed() -> None:
    """context payload byte 107 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(107, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip108x01_roundtrip() -> None:
    """context payload byte 108 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(108, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip108x20_roundtrip() -> None:
    """context payload byte 108 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(108, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip108x80_typed() -> None:
    """context payload byte 108 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(108, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip109x01_roundtrip() -> None:
    """context payload byte 109 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(109, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip109x20_roundtrip() -> None:
    """context payload byte 109 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(109, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip109x80_typed() -> None:
    """context payload byte 109 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(109, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip110x01_roundtrip() -> None:
    """context payload byte 110 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(110, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip110x20_roundtrip() -> None:
    """context payload byte 110 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(110, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip110x80_typed() -> None:
    """context payload byte 110 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(110, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip111x01_roundtrip() -> None:
    """context payload byte 111 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(111, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip111x20_roundtrip() -> None:
    """context payload byte 111 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(111, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip111x80_typed() -> None:
    """context payload byte 111 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(111, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip112x01_roundtrip() -> None:
    """context payload byte 112 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(112, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip112x20_roundtrip() -> None:
    """context payload byte 112 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(112, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip112x80_typed() -> None:
    """context payload byte 112 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(112, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip113x01_roundtrip() -> None:
    """context payload byte 113 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(113, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip113x20_roundtrip() -> None:
    """context payload byte 113 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(113, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip113x80_typed() -> None:
    """context payload byte 113 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(113, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip114x01_roundtrip() -> None:
    """context payload byte 114 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(114, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip114x20_roundtrip() -> None:
    """context payload byte 114 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(114, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip114x80_typed() -> None:
    """context payload byte 114 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(114, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip115x01_roundtrip() -> None:
    """context payload byte 115 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(115, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip115x20_roundtrip() -> None:
    """context payload byte 115 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(115, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip115x80_typed() -> None:
    """context payload byte 115 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(115, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip116x01_roundtrip() -> None:
    """context payload byte 116 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(116, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip116x20_roundtrip() -> None:
    """context payload byte 116 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(116, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip116x80_typed() -> None:
    """context payload byte 116 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(116, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip117x01_roundtrip() -> None:
    """context payload byte 117 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(117, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip117x20_roundtrip() -> None:
    """context payload byte 117 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(117, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip117x80_typed() -> None:
    """context payload byte 117 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(117, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip118x01_roundtrip() -> None:
    """context payload byte 118 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(118, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip118x20_roundtrip() -> None:
    """context payload byte 118 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(118, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip118x80_typed() -> None:
    """context payload byte 118 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(118, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip119x01_roundtrip() -> None:
    """context payload byte 119 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(119, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip119x20_roundtrip() -> None:
    """context payload byte 119 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(119, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip119x80_typed() -> None:
    """context payload byte 119 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(119, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip120x01_roundtrip() -> None:
    """context payload byte 120 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(120, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip120x20_roundtrip() -> None:
    """context payload byte 120 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(120, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip120x80_typed() -> None:
    """context payload byte 120 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(120, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip121x01_roundtrip() -> None:
    """context payload byte 121 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(121, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip121x20_roundtrip() -> None:
    """context payload byte 121 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(121, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip121x80_typed() -> None:
    """context payload byte 121 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(121, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip122x01_roundtrip() -> None:
    """context payload byte 122 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(122, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip122x20_roundtrip() -> None:
    """context payload byte 122 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(122, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip122x80_typed() -> None:
    """context payload byte 122 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(122, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip123x01_roundtrip() -> None:
    """context payload byte 123 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(123, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip123x20_roundtrip() -> None:
    """context payload byte 123 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(123, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip123x80_typed() -> None:
    """context payload byte 123 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(123, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip124x01_roundtrip() -> None:
    """context payload byte 124 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(124, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip124x20_roundtrip() -> None:
    """context payload byte 124 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(124, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip124x80_typed() -> None:
    """context payload byte 124 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(124, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip125x01_roundtrip() -> None:
    """context payload byte 125 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(125, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip125x20_roundtrip() -> None:
    """context payload byte 125 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(125, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip125x80_typed() -> None:
    """context payload byte 125 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(125, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip126x01_roundtrip() -> None:
    """context payload byte 126 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(126, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip126x20_roundtrip() -> None:
    """context payload byte 126 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(126, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip126x80_typed() -> None:
    """context payload byte 126 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(126, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip127x01_roundtrip() -> None:
    """context payload byte 127 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(127, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip127x20_roundtrip() -> None:
    """context payload byte 127 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(127, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip127x80_typed() -> None:
    """context payload byte 127 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(127, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip128x01_roundtrip() -> None:
    """context payload byte 128 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(128, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip128x20_roundtrip() -> None:
    """context payload byte 128 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(128, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip128x80_typed() -> None:
    """context payload byte 128 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(128, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip129x01_roundtrip() -> None:
    """context payload byte 129 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(129, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip129x20_roundtrip() -> None:
    """context payload byte 129 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(129, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip129x80_typed() -> None:
    """context payload byte 129 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(129, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip130x01_roundtrip() -> None:
    """context payload byte 130 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(130, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip130x20_roundtrip() -> None:
    """context payload byte 130 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(130, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip130x80_typed() -> None:
    """context payload byte 130 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(130, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip131x01_roundtrip() -> None:
    """context payload byte 131 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(131, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip131x20_roundtrip() -> None:
    """context payload byte 131 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(131, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip131x80_typed() -> None:
    """context payload byte 131 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(131, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip132x01_roundtrip() -> None:
    """context payload byte 132 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(132, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip132x20_roundtrip() -> None:
    """context payload byte 132 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(132, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip132x80_typed() -> None:
    """context payload byte 132 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(132, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip133x01_roundtrip() -> None:
    """context payload byte 133 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(133, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip133x20_roundtrip() -> None:
    """context payload byte 133 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(133, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip133x80_typed() -> None:
    """context payload byte 133 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(133, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip134x01_roundtrip() -> None:
    """context payload byte 134 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(134, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip134x20_roundtrip() -> None:
    """context payload byte 134 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(134, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip134x80_typed() -> None:
    """context payload byte 134 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(134, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip135x01_roundtrip() -> None:
    """context payload byte 135 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(135, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip135x20_roundtrip() -> None:
    """context payload byte 135 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(135, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip135x80_typed() -> None:
    """context payload byte 135 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(135, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip136x01_roundtrip() -> None:
    """context payload byte 136 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(136, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip136x20_roundtrip() -> None:
    """context payload byte 136 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(136, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip136x80_typed() -> None:
    """context payload byte 136 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(136, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip137x01_roundtrip() -> None:
    """context payload byte 137 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(137, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip137x20_roundtrip() -> None:
    """context payload byte 137 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(137, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip137x80_typed() -> None:
    """context payload byte 137 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(137, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip138x01_roundtrip() -> None:
    """context payload byte 138 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(138, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip138x20_roundtrip() -> None:
    """context payload byte 138 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(138, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip138x80_typed() -> None:
    """context payload byte 138 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(138, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip139x01_roundtrip() -> None:
    """context payload byte 139 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(139, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip139x20_roundtrip() -> None:
    """context payload byte 139 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(139, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip139x80_typed() -> None:
    """context payload byte 139 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(139, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip140x01_roundtrip() -> None:
    """context payload byte 140 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(140, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip140x20_roundtrip() -> None:
    """context payload byte 140 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(140, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip140x80_typed() -> None:
    """context payload byte 140 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(140, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip141x01_roundtrip() -> None:
    """context payload byte 141 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(141, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip141x20_roundtrip() -> None:
    """context payload byte 141 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(141, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip141x80_typed() -> None:
    """context payload byte 141 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(141, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip142x01_roundtrip() -> None:
    """context payload byte 142 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(142, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip142x20_roundtrip() -> None:
    """context payload byte 142 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(142, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip142x80_typed() -> None:
    """context payload byte 142 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(142, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip143x01_roundtrip() -> None:
    """context payload byte 143 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(143, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip143x20_roundtrip() -> None:
    """context payload byte 143 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(143, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip143x80_typed() -> None:
    """context payload byte 143 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(143, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip144x01_roundtrip() -> None:
    """context payload byte 144 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(144, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip144x20_roundtrip() -> None:
    """context payload byte 144 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(144, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip144x80_typed() -> None:
    """context payload byte 144 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(144, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip145x01_roundtrip() -> None:
    """context payload byte 145 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(145, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip145x20_roundtrip() -> None:
    """context payload byte 145 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(145, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip145x80_typed() -> None:
    """context payload byte 145 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(145, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip146x01_roundtrip() -> None:
    """context payload byte 146 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(146, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip146x20_roundtrip() -> None:
    """context payload byte 146 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(146, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip146x80_typed() -> None:
    """context payload byte 146 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(146, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip147x01_roundtrip() -> None:
    """context payload byte 147 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(147, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip147x20_roundtrip() -> None:
    """context payload byte 147 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(147, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip147x80_typed() -> None:
    """context payload byte 147 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(147, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip148x01_roundtrip() -> None:
    """context payload byte 148 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(148, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip148x20_roundtrip() -> None:
    """context payload byte 148 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(148, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip148x80_typed() -> None:
    """context payload byte 148 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(148, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip149x01_roundtrip() -> None:
    """context payload byte 149 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(149, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip149x20_roundtrip() -> None:
    """context payload byte 149 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(149, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip149x80_typed() -> None:
    """context payload byte 149 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(149, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip150x01_roundtrip() -> None:
    """context payload byte 150 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(150, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip150x20_roundtrip() -> None:
    """context payload byte 150 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(150, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip150x80_typed() -> None:
    """context payload byte 150 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(150, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip151x01_roundtrip() -> None:
    """context payload byte 151 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(151, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip151x20_roundtrip() -> None:
    """context payload byte 151 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(151, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip151x80_typed() -> None:
    """context payload byte 151 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(151, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip152x01_roundtrip() -> None:
    """context payload byte 152 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(152, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip152x20_roundtrip() -> None:
    """context payload byte 152 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(152, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip152x80_typed() -> None:
    """context payload byte 152 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(152, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip153x01_roundtrip() -> None:
    """context payload byte 153 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(153, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip153x20_roundtrip() -> None:
    """context payload byte 153 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(153, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip153x80_typed() -> None:
    """context payload byte 153 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(153, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip154x01_roundtrip() -> None:
    """context payload byte 154 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(154, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip154x20_roundtrip() -> None:
    """context payload byte 154 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(154, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip154x80_typed() -> None:
    """context payload byte 154 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(154, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip155x01_roundtrip() -> None:
    """context payload byte 155 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(155, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip155x20_roundtrip() -> None:
    """context payload byte 155 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(155, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip155x80_typed() -> None:
    """context payload byte 155 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(155, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip156x01_roundtrip() -> None:
    """context payload byte 156 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(156, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip156x20_roundtrip() -> None:
    """context payload byte 156 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(156, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip156x80_typed() -> None:
    """context payload byte 156 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(156, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip157x01_roundtrip() -> None:
    """context payload byte 157 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(157, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip157x20_roundtrip() -> None:
    """context payload byte 157 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(157, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip157x80_typed() -> None:
    """context payload byte 157 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(157, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip158x01_roundtrip() -> None:
    """context payload byte 158 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(158, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip158x20_roundtrip() -> None:
    """context payload byte 158 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(158, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip158x80_typed() -> None:
    """context payload byte 158 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(158, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip159x01_roundtrip() -> None:
    """context payload byte 159 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(159, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip159x20_roundtrip() -> None:
    """context payload byte 159 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(159, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip159x80_typed() -> None:
    """context payload byte 159 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(159, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip160x01_roundtrip() -> None:
    """context payload byte 160 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(160, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip160x20_roundtrip() -> None:
    """context payload byte 160 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(160, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip160x80_typed() -> None:
    """context payload byte 160 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(160, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip161x01_roundtrip() -> None:
    """context payload byte 161 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(161, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip161x20_roundtrip() -> None:
    """context payload byte 161 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(161, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip161x80_typed() -> None:
    """context payload byte 161 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(161, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip162x01_roundtrip() -> None:
    """context payload byte 162 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(162, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip162x20_roundtrip() -> None:
    """context payload byte 162 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(162, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip162x80_typed() -> None:
    """context payload byte 162 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(162, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip163x01_roundtrip() -> None:
    """context payload byte 163 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(163, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip163x20_roundtrip() -> None:
    """context payload byte 163 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(163, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip163x80_typed() -> None:
    """context payload byte 163 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(163, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip164x01_roundtrip() -> None:
    """context payload byte 164 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(164, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip164x20_roundtrip() -> None:
    """context payload byte 164 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(164, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip164x80_typed() -> None:
    """context payload byte 164 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(164, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip165x01_roundtrip() -> None:
    """context payload byte 165 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(165, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip165x20_roundtrip() -> None:
    """context payload byte 165 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(165, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip165x80_typed() -> None:
    """context payload byte 165 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(165, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip166x01_roundtrip() -> None:
    """context payload byte 166 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(166, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip166x20_roundtrip() -> None:
    """context payload byte 166 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(166, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip166x80_typed() -> None:
    """context payload byte 166 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(166, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip167x01_roundtrip() -> None:
    """context payload byte 167 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(167, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip167x20_roundtrip() -> None:
    """context payload byte 167 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(167, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip167x80_typed() -> None:
    """context payload byte 167 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(167, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip168x01_roundtrip() -> None:
    """context payload byte 168 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(168, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip168x20_roundtrip() -> None:
    """context payload byte 168 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(168, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip168x80_typed() -> None:
    """context payload byte 168 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(168, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip169x01_roundtrip() -> None:
    """context payload byte 169 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(169, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip169x20_roundtrip() -> None:
    """context payload byte 169 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(169, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip169x80_typed() -> None:
    """context payload byte 169 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(169, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip170x01_roundtrip() -> None:
    """context payload byte 170 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(170, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip170x20_roundtrip() -> None:
    """context payload byte 170 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(170, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip170x80_typed() -> None:
    """context payload byte 170 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(170, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip171x01_roundtrip() -> None:
    """context payload byte 171 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(171, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip171x20_roundtrip() -> None:
    """context payload byte 171 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(171, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip171x80_typed() -> None:
    """context payload byte 171 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(171, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip172x01_roundtrip() -> None:
    """context payload byte 172 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(172, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip172x20_roundtrip() -> None:
    """context payload byte 172 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(172, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip172x80_typed() -> None:
    """context payload byte 172 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(172, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip173x01_roundtrip() -> None:
    """context payload byte 173 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(173, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip173x20_roundtrip() -> None:
    """context payload byte 173 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(173, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip173x80_typed() -> None:
    """context payload byte 173 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(173, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip174x01_roundtrip() -> None:
    """context payload byte 174 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(174, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip174x20_roundtrip() -> None:
    """context payload byte 174 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(174, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip174x80_typed() -> None:
    """context payload byte 174 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(174, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip175x01_roundtrip() -> None:
    """context payload byte 175 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(175, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip175x20_roundtrip() -> None:
    """context payload byte 175 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(175, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip175x80_typed() -> None:
    """context payload byte 175 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(175, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip176x01_roundtrip() -> None:
    """context payload byte 176 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(176, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip176x20_roundtrip() -> None:
    """context payload byte 176 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(176, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip176x80_typed() -> None:
    """context payload byte 176 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(176, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip177x01_roundtrip() -> None:
    """context payload byte 177 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(177, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip177x20_roundtrip() -> None:
    """context payload byte 177 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(177, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip177x80_typed() -> None:
    """context payload byte 177 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(177, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip178x01_roundtrip() -> None:
    """context payload byte 178 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(178, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip178x20_roundtrip() -> None:
    """context payload byte 178 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(178, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip178x80_typed() -> None:
    """context payload byte 178 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(178, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip179x01_roundtrip() -> None:
    """context payload byte 179 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(179, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip179x20_roundtrip() -> None:
    """context payload byte 179 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(179, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip179x80_typed() -> None:
    """context payload byte 179 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(179, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip180x01_roundtrip() -> None:
    """context payload byte 180 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(180, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip180x20_roundtrip() -> None:
    """context payload byte 180 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(180, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip180x80_typed() -> None:
    """context payload byte 180 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(180, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip181x01_roundtrip() -> None:
    """context payload byte 181 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(181, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip181x20_roundtrip() -> None:
    """context payload byte 181 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(181, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip181x80_typed() -> None:
    """context payload byte 181 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(181, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip182x01_roundtrip() -> None:
    """context payload byte 182 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(182, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip182x20_roundtrip() -> None:
    """context payload byte 182 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(182, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip182x80_typed() -> None:
    """context payload byte 182 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(182, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip183x01_roundtrip() -> None:
    """context payload byte 183 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(183, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip183x20_roundtrip() -> None:
    """context payload byte 183 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(183, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip183x80_typed() -> None:
    """context payload byte 183 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(183, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip184x01_roundtrip() -> None:
    """context payload byte 184 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(184, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip184x20_roundtrip() -> None:
    """context payload byte 184 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(184, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip184x80_typed() -> None:
    """context payload byte 184 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(184, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip185x01_roundtrip() -> None:
    """context payload byte 185 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(185, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip185x20_roundtrip() -> None:
    """context payload byte 185 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(185, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip185x80_typed() -> None:
    """context payload byte 185 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(185, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip186x01_roundtrip() -> None:
    """context payload byte 186 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(186, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip186x20_roundtrip() -> None:
    """context payload byte 186 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(186, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip186x80_typed() -> None:
    """context payload byte 186 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(186, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip187x01_roundtrip() -> None:
    """context payload byte 187 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(187, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip187x20_roundtrip() -> None:
    """context payload byte 187 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(187, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip187x80_typed() -> None:
    """context payload byte 187 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(187, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip188x01_roundtrip() -> None:
    """context payload byte 188 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(188, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip188x20_roundtrip() -> None:
    """context payload byte 188 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(188, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip188x80_typed() -> None:
    """context payload byte 188 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(188, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip189x01_roundtrip() -> None:
    """context payload byte 189 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(189, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip189x20_roundtrip() -> None:
    """context payload byte 189 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(189, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip189x80_typed() -> None:
    """context payload byte 189 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(189, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip190x01_roundtrip() -> None:
    """context payload byte 190 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(190, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip190x20_roundtrip() -> None:
    """context payload byte 190 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(190, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip190x80_typed() -> None:
    """context payload byte 190 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(190, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip191x01_roundtrip() -> None:
    """context payload byte 191 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(191, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip191x20_roundtrip() -> None:
    """context payload byte 191 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(191, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip191x80_typed() -> None:
    """context payload byte 191 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(191, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip192x01_roundtrip() -> None:
    """context payload byte 192 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(192, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip192x20_roundtrip() -> None:
    """context payload byte 192 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(192, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip192x80_typed() -> None:
    """context payload byte 192 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(192, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip193x01_roundtrip() -> None:
    """context payload byte 193 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(193, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip193x20_roundtrip() -> None:
    """context payload byte 193 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(193, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip193x80_typed() -> None:
    """context payload byte 193 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(193, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip194x01_roundtrip() -> None:
    """context payload byte 194 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(194, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip194x20_roundtrip() -> None:
    """context payload byte 194 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(194, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip194x80_typed() -> None:
    """context payload byte 194 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(194, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip195x01_roundtrip() -> None:
    """context payload byte 195 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(195, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip195x20_roundtrip() -> None:
    """context payload byte 195 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(195, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip195x80_typed() -> None:
    """context payload byte 195 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(195, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip196x01_roundtrip() -> None:
    """context payload byte 196 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(196, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip196x20_roundtrip() -> None:
    """context payload byte 196 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(196, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip196x80_typed() -> None:
    """context payload byte 196 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(196, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip197x01_roundtrip() -> None:
    """context payload byte 197 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(197, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip197x20_roundtrip() -> None:
    """context payload byte 197 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(197, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip197x80_typed() -> None:
    """context payload byte 197 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(197, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip198x01_roundtrip() -> None:
    """context payload byte 198 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(198, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip198x20_roundtrip() -> None:
    """context payload byte 198 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(198, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip198x80_typed() -> None:
    """context payload byte 198 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(198, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip199x01_roundtrip() -> None:
    """context payload byte 199 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(199, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip199x20_roundtrip() -> None:
    """context payload byte 199 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(199, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip199x80_typed() -> None:
    """context payload byte 199 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(199, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip200x01_roundtrip() -> None:
    """context payload byte 200 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(200, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip200x20_roundtrip() -> None:
    """context payload byte 200 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(200, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip200x80_typed() -> None:
    """context payload byte 200 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(200, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip201x01_roundtrip() -> None:
    """context payload byte 201 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(201, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip201x20_roundtrip() -> None:
    """context payload byte 201 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(201, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip201x80_typed() -> None:
    """context payload byte 201 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(201, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip202x01_roundtrip() -> None:
    """context payload byte 202 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(202, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip202x20_roundtrip() -> None:
    """context payload byte 202 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(202, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip202x80_typed() -> None:
    """context payload byte 202 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(202, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip203x01_roundtrip() -> None:
    """context payload byte 203 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(203, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip203x20_roundtrip() -> None:
    """context payload byte 203 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(203, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip203x80_typed() -> None:
    """context payload byte 203 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(203, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip204x01_roundtrip() -> None:
    """context payload byte 204 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(204, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip204x20_roundtrip() -> None:
    """context payload byte 204 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(204, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip204x80_typed() -> None:
    """context payload byte 204 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(204, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip205x01_roundtrip() -> None:
    """context payload byte 205 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(205, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip205x20_roundtrip() -> None:
    """context payload byte 205 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(205, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip205x80_typed() -> None:
    """context payload byte 205 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(205, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip206x01_roundtrip() -> None:
    """context payload byte 206 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(206, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip206x20_roundtrip() -> None:
    """context payload byte 206 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(206, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip206x80_typed() -> None:
    """context payload byte 206 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(206, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip207x01_roundtrip() -> None:
    """context payload byte 207 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(207, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip207x20_roundtrip() -> None:
    """context payload byte 207 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(207, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip207x80_typed() -> None:
    """context payload byte 207 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(207, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip208x01_roundtrip() -> None:
    """context payload byte 208 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(208, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip208x20_roundtrip() -> None:
    """context payload byte 208 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(208, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip208x80_typed() -> None:
    """context payload byte 208 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(208, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip209x01_roundtrip() -> None:
    """context payload byte 209 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(209, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip209x20_roundtrip() -> None:
    """context payload byte 209 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(209, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip209x80_typed() -> None:
    """context payload byte 209 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(209, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip210x01_roundtrip() -> None:
    """context payload byte 210 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(210, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip210x20_roundtrip() -> None:
    """context payload byte 210 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(210, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip210x80_typed() -> None:
    """context payload byte 210 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(210, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip211x01_roundtrip() -> None:
    """context payload byte 211 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(211, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip211x20_roundtrip() -> None:
    """context payload byte 211 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(211, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip211x80_typed() -> None:
    """context payload byte 211 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(211, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip212x01_roundtrip() -> None:
    """context payload byte 212 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(212, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip212x20_roundtrip() -> None:
    """context payload byte 212 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(212, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip212x80_typed() -> None:
    """context payload byte 212 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(212, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip213x01_roundtrip() -> None:
    """context payload byte 213 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(213, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip213x20_roundtrip() -> None:
    """context payload byte 213 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(213, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip213x80_typed() -> None:
    """context payload byte 213 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(213, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip214x01_roundtrip() -> None:
    """context payload byte 214 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(214, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip214x20_roundtrip() -> None:
    """context payload byte 214 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(214, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip214x80_typed() -> None:
    """context payload byte 214 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(214, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip215x01_roundtrip() -> None:
    """context payload byte 215 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(215, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip215x20_roundtrip() -> None:
    """context payload byte 215 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(215, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip215x80_typed() -> None:
    """context payload byte 215 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(215, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip216x01_roundtrip() -> None:
    """context payload byte 216 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(216, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip216x20_roundtrip() -> None:
    """context payload byte 216 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(216, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip216x80_typed() -> None:
    """context payload byte 216 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(216, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip217x01_roundtrip() -> None:
    """context payload byte 217 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(217, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip217x20_roundtrip() -> None:
    """context payload byte 217 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(217, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip217x80_typed() -> None:
    """context payload byte 217 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(217, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip218x01_roundtrip() -> None:
    """context payload byte 218 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(218, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip218x20_roundtrip() -> None:
    """context payload byte 218 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(218, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip218x80_typed() -> None:
    """context payload byte 218 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(218, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip219x01_roundtrip() -> None:
    """context payload byte 219 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(219, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip219x20_roundtrip() -> None:
    """context payload byte 219 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(219, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip219x80_typed() -> None:
    """context payload byte 219 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(219, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip220x01_roundtrip() -> None:
    """context payload byte 220 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(220, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip220x20_roundtrip() -> None:
    """context payload byte 220 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(220, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip220x80_typed() -> None:
    """context payload byte 220 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(220, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip221x01_roundtrip() -> None:
    """context payload byte 221 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(221, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip221x20_roundtrip() -> None:
    """context payload byte 221 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(221, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip221x80_typed() -> None:
    """context payload byte 221 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(221, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip222x01_roundtrip() -> None:
    """context payload byte 222 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(222, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip222x20_roundtrip() -> None:
    """context payload byte 222 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(222, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip222x80_typed() -> None:
    """context payload byte 222 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(222, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip223x01_roundtrip() -> None:
    """context payload byte 223 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(223, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip223x20_roundtrip() -> None:
    """context payload byte 223 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(223, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip223x80_typed() -> None:
    """context payload byte 223 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(223, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip224x01_roundtrip() -> None:
    """context payload byte 224 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(224, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip224x20_roundtrip() -> None:
    """context payload byte 224 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(224, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip224x80_typed() -> None:
    """context payload byte 224 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(224, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip225x01_roundtrip() -> None:
    """context payload byte 225 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(225, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip225x20_roundtrip() -> None:
    """context payload byte 225 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(225, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip225x80_typed() -> None:
    """context payload byte 225 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(225, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip226x01_roundtrip() -> None:
    """context payload byte 226 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(226, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip226x20_roundtrip() -> None:
    """context payload byte 226 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(226, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip226x80_typed() -> None:
    """context payload byte 226 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(226, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip227x01_roundtrip() -> None:
    """context payload byte 227 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(227, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip227x20_roundtrip() -> None:
    """context payload byte 227 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(227, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip227x80_typed() -> None:
    """context payload byte 227 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(227, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip228x01_roundtrip() -> None:
    """context payload byte 228 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(228, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip228x20_roundtrip() -> None:
    """context payload byte 228 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(228, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip228x80_typed() -> None:
    """context payload byte 228 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(228, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip229x01_roundtrip() -> None:
    """context payload byte 229 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(229, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip229x20_roundtrip() -> None:
    """context payload byte 229 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(229, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip229x80_typed() -> None:
    """context payload byte 229 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(229, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip230x01_roundtrip() -> None:
    """context payload byte 230 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(230, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip230x20_roundtrip() -> None:
    """context payload byte 230 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(230, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip230x80_typed() -> None:
    """context payload byte 230 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(230, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip231x01_roundtrip() -> None:
    """context payload byte 231 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(231, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip231x20_roundtrip() -> None:
    """context payload byte 231 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(231, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip231x80_typed() -> None:
    """context payload byte 231 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(231, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip232x01_roundtrip() -> None:
    """context payload byte 232 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(232, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip232x20_roundtrip() -> None:
    """context payload byte 232 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(232, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip232x80_typed() -> None:
    """context payload byte 232 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(232, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip233x01_roundtrip() -> None:
    """context payload byte 233 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(233, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip233x20_roundtrip() -> None:
    """context payload byte 233 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(233, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip233x80_typed() -> None:
    """context payload byte 233 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(233, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip234x01_roundtrip() -> None:
    """context payload byte 234 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(234, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip234x20_roundtrip() -> None:
    """context payload byte 234 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(234, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip234x80_typed() -> None:
    """context payload byte 234 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(234, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip235x01_roundtrip() -> None:
    """context payload byte 235 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(235, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip235x20_roundtrip() -> None:
    """context payload byte 235 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(235, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip235x80_typed() -> None:
    """context payload byte 235 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(235, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip236x01_roundtrip() -> None:
    """context payload byte 236 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(236, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip236x20_roundtrip() -> None:
    """context payload byte 236 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(236, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip236x80_typed() -> None:
    """context payload byte 236 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(236, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip237x01_roundtrip() -> None:
    """context payload byte 237 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(237, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip237x20_roundtrip() -> None:
    """context payload byte 237 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(237, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip237x80_typed() -> None:
    """context payload byte 237 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(237, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip238x01_roundtrip() -> None:
    """context payload byte 238 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(238, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip238x20_roundtrip() -> None:
    """context payload byte 238 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(238, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip238x80_typed() -> None:
    """context payload byte 238 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(238, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip239x01_roundtrip() -> None:
    """context payload byte 239 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(239, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip239x20_roundtrip() -> None:
    """context payload byte 239 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(239, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip239x80_typed() -> None:
    """context payload byte 239 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(239, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip240x01_roundtrip() -> None:
    """context payload byte 240 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(240, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip240x20_roundtrip() -> None:
    """context payload byte 240 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(240, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip240x80_typed() -> None:
    """context payload byte 240 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(240, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip241x01_roundtrip() -> None:
    """context payload byte 241 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(241, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip241x20_roundtrip() -> None:
    """context payload byte 241 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(241, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip241x80_typed() -> None:
    """context payload byte 241 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(241, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip242x01_roundtrip() -> None:
    """context payload byte 242 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(242, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip242x20_roundtrip() -> None:
    """context payload byte 242 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(242, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip242x80_typed() -> None:
    """context payload byte 242 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(242, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip243x01_roundtrip() -> None:
    """context payload byte 243 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(243, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip243x20_roundtrip() -> None:
    """context payload byte 243 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(243, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip243x80_typed() -> None:
    """context payload byte 243 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(243, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip244x01_roundtrip() -> None:
    """context payload byte 244 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(244, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip244x20_roundtrip() -> None:
    """context payload byte 244 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(244, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip244x80_typed() -> None:
    """context payload byte 244 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(244, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip245x01_roundtrip() -> None:
    """context payload byte 245 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(245, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip245x20_roundtrip() -> None:
    """context payload byte 245 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(245, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip245x80_typed() -> None:
    """context payload byte 245 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(245, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip246x01_roundtrip() -> None:
    """context payload byte 246 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(246, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip246x20_roundtrip() -> None:
    """context payload byte 246 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(246, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip246x80_typed() -> None:
    """context payload byte 246 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(246, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip247x01_roundtrip() -> None:
    """context payload byte 247 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(247, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip247x20_roundtrip() -> None:
    """context payload byte 247 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(247, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip247x80_typed() -> None:
    """context payload byte 247 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(247, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip248x01_roundtrip() -> None:
    """context payload byte 248 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(248, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip248x20_roundtrip() -> None:
    """context payload byte 248 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(248, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip248x80_typed() -> None:
    """context payload byte 248 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(248, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip249x01_roundtrip() -> None:
    """context payload byte 249 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(249, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip249x20_roundtrip() -> None:
    """context payload byte 249 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(249, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip249x80_typed() -> None:
    """context payload byte 249 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(249, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip250x01_roundtrip() -> None:
    """context payload byte 250 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(250, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip250x20_roundtrip() -> None:
    """context payload byte 250 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(250, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip250x80_typed() -> None:
    """context payload byte 250 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(250, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip251x01_roundtrip() -> None:
    """context payload byte 251 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(251, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip251x20_roundtrip() -> None:
    """context payload byte 251 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(251, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip251x80_typed() -> None:
    """context payload byte 251 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(251, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip252x01_roundtrip() -> None:
    """context payload byte 252 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(252, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip252x20_roundtrip() -> None:
    """context payload byte 252 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(252, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip252x80_typed() -> None:
    """context payload byte 252 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(252, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip253x01_roundtrip() -> None:
    """context payload byte 253 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(253, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip253x20_roundtrip() -> None:
    """context payload byte 253 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(253, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip253x80_typed() -> None:
    """context payload byte 253 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(253, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip254x01_roundtrip() -> None:
    """context payload byte 254 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(254, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip254x20_roundtrip() -> None:
    """context payload byte 254 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(254, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip254x80_typed() -> None:
    """context payload byte 254 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(254, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip255x01_roundtrip() -> None:
    """context payload byte 255 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(255, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip255x20_roundtrip() -> None:
    """context payload byte 255 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(255, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip255x80_typed() -> None:
    """context payload byte 255 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(255, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip256x01_roundtrip() -> None:
    """context payload byte 256 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(256, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip256x20_roundtrip() -> None:
    """context payload byte 256 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(256, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip256x80_typed() -> None:
    """context payload byte 256 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(256, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip257x01_roundtrip() -> None:
    """context payload byte 257 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(257, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip257x20_roundtrip() -> None:
    """context payload byte 257 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(257, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip257x80_typed() -> None:
    """context payload byte 257 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(257, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip258x01_roundtrip() -> None:
    """context payload byte 258 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(258, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip258x20_roundtrip() -> None:
    """context payload byte 258 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(258, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip258x80_typed() -> None:
    """context payload byte 258 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(258, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip259x01_roundtrip() -> None:
    """context payload byte 259 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(259, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip259x20_roundtrip() -> None:
    """context payload byte 259 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(259, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip259x80_typed() -> None:
    """context payload byte 259 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(259, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip260x01_roundtrip() -> None:
    """context payload byte 260 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(260, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip260x20_roundtrip() -> None:
    """context payload byte 260 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(260, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip260x80_typed() -> None:
    """context payload byte 260 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(260, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip261x01_roundtrip() -> None:
    """context payload byte 261 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(261, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip261x20_roundtrip() -> None:
    """context payload byte 261 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(261, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip261x80_typed() -> None:
    """context payload byte 261 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(261, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip262x01_roundtrip() -> None:
    """context payload byte 262 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(262, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip262x20_roundtrip() -> None:
    """context payload byte 262 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(262, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip262x80_typed() -> None:
    """context payload byte 262 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(262, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip263x01_roundtrip() -> None:
    """context payload byte 263 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(263, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip263x20_roundtrip() -> None:
    """context payload byte 263 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(263, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip263x80_typed() -> None:
    """context payload byte 263 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(263, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip264x01_roundtrip() -> None:
    """context payload byte 264 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(264, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip264x20_roundtrip() -> None:
    """context payload byte 264 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(264, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip264x80_typed() -> None:
    """context payload byte 264 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(264, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip265x01_roundtrip() -> None:
    """context payload byte 265 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(265, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip265x20_roundtrip() -> None:
    """context payload byte 265 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(265, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip265x80_typed() -> None:
    """context payload byte 265 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(265, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip266x01_roundtrip() -> None:
    """context payload byte 266 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(266, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip266x20_roundtrip() -> None:
    """context payload byte 266 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(266, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip266x80_typed() -> None:
    """context payload byte 266 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(266, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip267x01_roundtrip() -> None:
    """context payload byte 267 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(267, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip267x20_roundtrip() -> None:
    """context payload byte 267 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(267, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip267x80_typed() -> None:
    """context payload byte 267 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(267, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip268x01_roundtrip() -> None:
    """context payload byte 268 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(268, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip268x20_roundtrip() -> None:
    """context payload byte 268 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(268, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip268x80_typed() -> None:
    """context payload byte 268 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(268, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip269x01_roundtrip() -> None:
    """context payload byte 269 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(269, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip269x20_roundtrip() -> None:
    """context payload byte 269 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(269, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip269x80_typed() -> None:
    """context payload byte 269 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(269, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip270x01_roundtrip() -> None:
    """context payload byte 270 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(270, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip270x20_roundtrip() -> None:
    """context payload byte 270 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(270, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip270x80_typed() -> None:
    """context payload byte 270 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(270, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip271x01_roundtrip() -> None:
    """context payload byte 271 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(271, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip271x20_roundtrip() -> None:
    """context payload byte 271 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(271, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip271x80_typed() -> None:
    """context payload byte 271 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(271, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip272x01_roundtrip() -> None:
    """context payload byte 272 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(272, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip272x20_roundtrip() -> None:
    """context payload byte 272 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(272, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip272x80_typed() -> None:
    """context payload byte 272 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(272, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip273x01_roundtrip() -> None:
    """context payload byte 273 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(273, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip273x20_roundtrip() -> None:
    """context payload byte 273 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(273, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip273x80_typed() -> None:
    """context payload byte 273 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(273, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip274x01_roundtrip() -> None:
    """context payload byte 274 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(274, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip274x20_roundtrip() -> None:
    """context payload byte 274 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(274, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip274x80_typed() -> None:
    """context payload byte 274 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(274, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip275x01_roundtrip() -> None:
    """context payload byte 275 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(275, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip275x20_roundtrip() -> None:
    """context payload byte 275 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(275, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip275x80_typed() -> None:
    """context payload byte 275 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(275, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip276x01_roundtrip() -> None:
    """context payload byte 276 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(276, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip276x20_roundtrip() -> None:
    """context payload byte 276 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(276, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip276x80_typed() -> None:
    """context payload byte 276 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(276, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip277x01_roundtrip() -> None:
    """context payload byte 277 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(277, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip277x20_roundtrip() -> None:
    """context payload byte 277 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(277, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip277x80_typed() -> None:
    """context payload byte 277 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(277, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip278x01_roundtrip() -> None:
    """context payload byte 278 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(278, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip278x20_roundtrip() -> None:
    """context payload byte 278 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(278, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip278x80_typed() -> None:
    """context payload byte 278 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(278, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip279x01_roundtrip() -> None:
    """context payload byte 279 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(279, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip279x20_roundtrip() -> None:
    """context payload byte 279 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(279, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip279x80_typed() -> None:
    """context payload byte 279 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(279, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip280x01_roundtrip() -> None:
    """context payload byte 280 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(280, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip280x20_roundtrip() -> None:
    """context payload byte 280 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(280, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip280x80_typed() -> None:
    """context payload byte 280 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(280, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip281x01_roundtrip() -> None:
    """context payload byte 281 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(281, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip281x20_roundtrip() -> None:
    """context payload byte 281 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(281, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip281x80_typed() -> None:
    """context payload byte 281 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(281, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip282x01_roundtrip() -> None:
    """context payload byte 282 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(282, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip282x20_roundtrip() -> None:
    """context payload byte 282 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(282, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip282x80_typed() -> None:
    """context payload byte 282 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(282, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip283x01_roundtrip() -> None:
    """context payload byte 283 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(283, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip283x20_roundtrip() -> None:
    """context payload byte 283 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(283, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip283x80_typed() -> None:
    """context payload byte 283 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(283, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip284x01_roundtrip() -> None:
    """context payload byte 284 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(284, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip284x20_roundtrip() -> None:
    """context payload byte 284 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(284, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip284x80_typed() -> None:
    """context payload byte 284 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(284, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip285x01_roundtrip() -> None:
    """context payload byte 285 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(285, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip285x20_roundtrip() -> None:
    """context payload byte 285 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(285, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip285x80_typed() -> None:
    """context payload byte 285 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(285, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip286x01_roundtrip() -> None:
    """context payload byte 286 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(286, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip286x20_roundtrip() -> None:
    """context payload byte 286 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(286, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip286x80_typed() -> None:
    """context payload byte 286 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(286, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip287x01_roundtrip() -> None:
    """context payload byte 287 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(287, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip287x20_roundtrip() -> None:
    """context payload byte 287 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(287, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip287x80_typed() -> None:
    """context payload byte 287 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(287, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip288x01_roundtrip() -> None:
    """context payload byte 288 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(288, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip288x20_roundtrip() -> None:
    """context payload byte 288 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(288, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip288x80_typed() -> None:
    """context payload byte 288 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(288, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip289x01_roundtrip() -> None:
    """context payload byte 289 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(289, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip289x20_roundtrip() -> None:
    """context payload byte 289 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(289, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip289x80_typed() -> None:
    """context payload byte 289 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(289, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip290x01_roundtrip() -> None:
    """context payload byte 290 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(290, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip290x20_roundtrip() -> None:
    """context payload byte 290 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(290, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip290x80_typed() -> None:
    """context payload byte 290 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(290, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip291x01_roundtrip() -> None:
    """context payload byte 291 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(291, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip291x20_roundtrip() -> None:
    """context payload byte 291 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(291, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip291x80_typed() -> None:
    """context payload byte 291 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(291, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip292x01_roundtrip() -> None:
    """context payload byte 292 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(292, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip292x20_roundtrip() -> None:
    """context payload byte 292 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(292, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip292x80_typed() -> None:
    """context payload byte 292 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(292, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip293x01_roundtrip() -> None:
    """context payload byte 293 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(293, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip293x20_roundtrip() -> None:
    """context payload byte 293 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(293, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip293x80_typed() -> None:
    """context payload byte 293 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(293, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip294x01_roundtrip() -> None:
    """context payload byte 294 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(294, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip294x20_roundtrip() -> None:
    """context payload byte 294 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(294, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip294x80_typed() -> None:
    """context payload byte 294 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(294, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip295x01_roundtrip() -> None:
    """context payload byte 295 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(295, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip295x20_roundtrip() -> None:
    """context payload byte 295 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(295, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip295x80_typed() -> None:
    """context payload byte 295 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(295, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip296x01_roundtrip() -> None:
    """context payload byte 296 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(296, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip296x20_roundtrip() -> None:
    """context payload byte 296 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(296, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip296x80_typed() -> None:
    """context payload byte 296 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(296, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip297x01_roundtrip() -> None:
    """context payload byte 297 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(297, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip297x20_roundtrip() -> None:
    """context payload byte 297 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(297, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip297x80_typed() -> None:
    """context payload byte 297 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(297, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip298x01_roundtrip() -> None:
    """context payload byte 298 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(298, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip298x20_roundtrip() -> None:
    """context payload byte 298 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(298, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip298x80_typed() -> None:
    """context payload byte 298 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(298, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip299x01_roundtrip() -> None:
    """context payload byte 299 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(299, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip299x20_roundtrip() -> None:
    """context payload byte 299 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(299, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip299x80_typed() -> None:
    """context payload byte 299 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(299, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip300x01_roundtrip() -> None:
    """context payload byte 300 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(300, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip300x20_roundtrip() -> None:
    """context payload byte 300 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(300, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip300x80_typed() -> None:
    """context payload byte 300 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(300, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip301x01_roundtrip() -> None:
    """context payload byte 301 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(301, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip301x20_roundtrip() -> None:
    """context payload byte 301 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(301, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip301x80_typed() -> None:
    """context payload byte 301 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(301, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip302x01_roundtrip() -> None:
    """context payload byte 302 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(302, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip302x20_roundtrip() -> None:
    """context payload byte 302 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(302, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip302x80_typed() -> None:
    """context payload byte 302 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(302, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip303x01_roundtrip() -> None:
    """context payload byte 303 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(303, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip303x20_roundtrip() -> None:
    """context payload byte 303 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(303, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip303x80_typed() -> None:
    """context payload byte 303 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(303, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip304x01_roundtrip() -> None:
    """context payload byte 304 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(304, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip304x20_roundtrip() -> None:
    """context payload byte 304 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(304, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip304x80_typed() -> None:
    """context payload byte 304 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(304, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip305x01_roundtrip() -> None:
    """context payload byte 305 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(305, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip305x20_roundtrip() -> None:
    """context payload byte 305 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(305, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip305x80_typed() -> None:
    """context payload byte 305 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(305, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip306x01_roundtrip() -> None:
    """context payload byte 306 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(306, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip306x20_roundtrip() -> None:
    """context payload byte 306 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(306, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip306x80_typed() -> None:
    """context payload byte 306 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(306, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip307x01_roundtrip() -> None:
    """context payload byte 307 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(307, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip307x20_roundtrip() -> None:
    """context payload byte 307 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(307, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip307x80_typed() -> None:
    """context payload byte 307 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(307, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip308x01_roundtrip() -> None:
    """context payload byte 308 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(308, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip308x20_roundtrip() -> None:
    """context payload byte 308 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(308, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip308x80_typed() -> None:
    """context payload byte 308 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(308, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip309x01_roundtrip() -> None:
    """context payload byte 309 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(309, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip309x20_roundtrip() -> None:
    """context payload byte 309 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(309, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip309x80_typed() -> None:
    """context payload byte 309 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(309, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip310x01_roundtrip() -> None:
    """context payload byte 310 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(310, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip310x20_roundtrip() -> None:
    """context payload byte 310 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(310, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip310x80_typed() -> None:
    """context payload byte 310 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(310, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip311x01_roundtrip() -> None:
    """context payload byte 311 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(311, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip311x20_roundtrip() -> None:
    """context payload byte 311 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(311, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip311x80_typed() -> None:
    """context payload byte 311 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(311, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip312x01_roundtrip() -> None:
    """context payload byte 312 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(312, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip312x20_roundtrip() -> None:
    """context payload byte 312 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(312, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip312x80_typed() -> None:
    """context payload byte 312 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(312, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip313x01_roundtrip() -> None:
    """context payload byte 313 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(313, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip313x20_roundtrip() -> None:
    """context payload byte 313 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(313, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip313x80_typed() -> None:
    """context payload byte 313 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(313, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip314x01_roundtrip() -> None:
    """context payload byte 314 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(314, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip314x20_roundtrip() -> None:
    """context payload byte 314 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(314, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip314x80_typed() -> None:
    """context payload byte 314 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(314, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip315x01_roundtrip() -> None:
    """context payload byte 315 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(315, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip315x20_roundtrip() -> None:
    """context payload byte 315 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(315, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip315x80_typed() -> None:
    """context payload byte 315 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(315, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip316x01_roundtrip() -> None:
    """context payload byte 316 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(316, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip316x20_roundtrip() -> None:
    """context payload byte 316 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(316, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip316x80_typed() -> None:
    """context payload byte 316 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(316, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip317x01_roundtrip() -> None:
    """context payload byte 317 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(317, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip317x20_roundtrip() -> None:
    """context payload byte 317 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(317, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip317x80_typed() -> None:
    """context payload byte 317 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(317, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip318x01_roundtrip() -> None:
    """context payload byte 318 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(318, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip318x20_roundtrip() -> None:
    """context payload byte 318 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(318, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip318x80_typed() -> None:
    """context payload byte 318 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(318, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip319x01_roundtrip() -> None:
    """context payload byte 319 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(319, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip319x20_roundtrip() -> None:
    """context payload byte 319 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(319, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip319x80_typed() -> None:
    """context payload byte 319 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(319, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip320x01_roundtrip() -> None:
    """context payload byte 320 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(320, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip320x20_roundtrip() -> None:
    """context payload byte 320 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(320, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip320x80_typed() -> None:
    """context payload byte 320 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(320, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip321x01_roundtrip() -> None:
    """context payload byte 321 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(321, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip321x20_roundtrip() -> None:
    """context payload byte 321 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(321, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip321x80_typed() -> None:
    """context payload byte 321 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(321, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip322x01_roundtrip() -> None:
    """context payload byte 322 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(322, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip322x20_roundtrip() -> None:
    """context payload byte 322 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(322, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip322x80_typed() -> None:
    """context payload byte 322 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(322, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip323x01_roundtrip() -> None:
    """context payload byte 323 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(323, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip323x20_roundtrip() -> None:
    """context payload byte 323 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(323, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip323x80_typed() -> None:
    """context payload byte 323 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(323, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip324x01_roundtrip() -> None:
    """context payload byte 324 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(324, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip324x20_roundtrip() -> None:
    """context payload byte 324 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(324, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip324x80_typed() -> None:
    """context payload byte 324 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(324, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip325x01_roundtrip() -> None:
    """context payload byte 325 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(325, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip325x20_roundtrip() -> None:
    """context payload byte 325 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(325, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip325x80_typed() -> None:
    """context payload byte 325 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(325, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip326x01_roundtrip() -> None:
    """context payload byte 326 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(326, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip326x20_roundtrip() -> None:
    """context payload byte 326 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(326, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip326x80_typed() -> None:
    """context payload byte 326 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(326, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip327x01_roundtrip() -> None:
    """context payload byte 327 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(327, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip327x20_roundtrip() -> None:
    """context payload byte 327 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(327, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip327x80_typed() -> None:
    """context payload byte 327 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(327, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip328x01_roundtrip() -> None:
    """context payload byte 328 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(328, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip328x20_roundtrip() -> None:
    """context payload byte 328 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(328, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip328x80_typed() -> None:
    """context payload byte 328 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(328, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip329x01_roundtrip() -> None:
    """context payload byte 329 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(329, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip329x20_roundtrip() -> None:
    """context payload byte 329 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(329, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip329x80_typed() -> None:
    """context payload byte 329 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(329, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip330x01_roundtrip() -> None:
    """context payload byte 330 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(330, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip330x20_roundtrip() -> None:
    """context payload byte 330 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(330, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip330x80_typed() -> None:
    """context payload byte 330 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(330, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip331x01_roundtrip() -> None:
    """context payload byte 331 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(331, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip331x20_roundtrip() -> None:
    """context payload byte 331 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(331, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip331x80_typed() -> None:
    """context payload byte 331 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(331, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip332x01_roundtrip() -> None:
    """context payload byte 332 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(332, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip332x20_roundtrip() -> None:
    """context payload byte 332 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(332, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip332x80_typed() -> None:
    """context payload byte 332 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(332, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip333x01_roundtrip() -> None:
    """context payload byte 333 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(333, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip333x20_roundtrip() -> None:
    """context payload byte 333 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(333, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip333x80_typed() -> None:
    """context payload byte 333 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(333, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip334x01_roundtrip() -> None:
    """context payload byte 334 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(334, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip334x20_roundtrip() -> None:
    """context payload byte 334 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(334, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip334x80_typed() -> None:
    """context payload byte 334 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(334, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip335x01_roundtrip() -> None:
    """context payload byte 335 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(335, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip335x20_roundtrip() -> None:
    """context payload byte 335 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(335, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip335x80_typed() -> None:
    """context payload byte 335 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(335, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip336x01_roundtrip() -> None:
    """context payload byte 336 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(336, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip336x20_roundtrip() -> None:
    """context payload byte 336 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(336, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip336x80_typed() -> None:
    """context payload byte 336 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(336, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip337x01_roundtrip() -> None:
    """context payload byte 337 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(337, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip337x20_roundtrip() -> None:
    """context payload byte 337 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(337, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip337x80_typed() -> None:
    """context payload byte 337 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(337, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip338x01_roundtrip() -> None:
    """context payload byte 338 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(338, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip338x20_roundtrip() -> None:
    """context payload byte 338 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(338, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip338x80_typed() -> None:
    """context payload byte 338 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(338, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip339x01_roundtrip() -> None:
    """context payload byte 339 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(339, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip339x20_roundtrip() -> None:
    """context payload byte 339 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(339, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip339x80_typed() -> None:
    """context payload byte 339 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(339, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip340x01_roundtrip() -> None:
    """context payload byte 340 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(340, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip340x20_roundtrip() -> None:
    """context payload byte 340 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(340, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip340x80_typed() -> None:
    """context payload byte 340 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(340, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip341x01_roundtrip() -> None:
    """context payload byte 341 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(341, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip341x20_roundtrip() -> None:
    """context payload byte 341 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(341, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip341x80_typed() -> None:
    """context payload byte 341 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(341, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip342x01_roundtrip() -> None:
    """context payload byte 342 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(342, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip342x20_roundtrip() -> None:
    """context payload byte 342 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(342, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip342x80_typed() -> None:
    """context payload byte 342 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(342, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip343x01_roundtrip() -> None:
    """context payload byte 343 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(343, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip343x20_roundtrip() -> None:
    """context payload byte 343 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(343, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip343x80_typed() -> None:
    """context payload byte 343 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(343, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip344x01_roundtrip() -> None:
    """context payload byte 344 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(344, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip344x20_roundtrip() -> None:
    """context payload byte 344 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(344, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip344x80_typed() -> None:
    """context payload byte 344 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(344, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip345x01_roundtrip() -> None:
    """context payload byte 345 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(345, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip345x20_roundtrip() -> None:
    """context payload byte 345 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(345, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip345x80_typed() -> None:
    """context payload byte 345 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(345, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip346x01_roundtrip() -> None:
    """context payload byte 346 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(346, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip346x20_roundtrip() -> None:
    """context payload byte 346 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(346, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip346x80_typed() -> None:
    """context payload byte 346 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(346, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip347x01_roundtrip() -> None:
    """context payload byte 347 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(347, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip347x20_roundtrip() -> None:
    """context payload byte 347 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(347, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip347x80_typed() -> None:
    """context payload byte 347 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(347, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip348x01_roundtrip() -> None:
    """context payload byte 348 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(348, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip348x20_roundtrip() -> None:
    """context payload byte 348 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(348, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip348x80_typed() -> None:
    """context payload byte 348 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(348, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip349x01_roundtrip() -> None:
    """context payload byte 349 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(349, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip349x20_roundtrip() -> None:
    """context payload byte 349 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(349, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip349x80_typed() -> None:
    """context payload byte 349 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(349, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip350x01_roundtrip() -> None:
    """context payload byte 350 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(350, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip350x20_roundtrip() -> None:
    """context payload byte 350 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(350, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip350x80_typed() -> None:
    """context payload byte 350 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(350, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip351x01_roundtrip() -> None:
    """context payload byte 351 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(351, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip351x20_roundtrip() -> None:
    """context payload byte 351 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(351, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip351x80_typed() -> None:
    """context payload byte 351 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(351, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip352x01_roundtrip() -> None:
    """context payload byte 352 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(352, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip352x20_roundtrip() -> None:
    """context payload byte 352 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(352, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip352x80_typed() -> None:
    """context payload byte 352 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(352, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip353x01_roundtrip() -> None:
    """context payload byte 353 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(353, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip353x20_roundtrip() -> None:
    """context payload byte 353 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(353, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip353x80_typed() -> None:
    """context payload byte 353 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(353, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip354x01_roundtrip() -> None:
    """context payload byte 354 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(354, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip354x20_roundtrip() -> None:
    """context payload byte 354 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(354, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip354x80_typed() -> None:
    """context payload byte 354 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(354, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip355x01_roundtrip() -> None:
    """context payload byte 355 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(355, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip355x20_roundtrip() -> None:
    """context payload byte 355 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(355, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip355x80_typed() -> None:
    """context payload byte 355 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(355, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip356x01_roundtrip() -> None:
    """context payload byte 356 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(356, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip356x20_roundtrip() -> None:
    """context payload byte 356 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(356, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip356x80_typed() -> None:
    """context payload byte 356 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(356, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip357x01_roundtrip() -> None:
    """context payload byte 357 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(357, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip357x20_roundtrip() -> None:
    """context payload byte 357 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(357, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip357x80_typed() -> None:
    """context payload byte 357 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(357, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip358x01_roundtrip() -> None:
    """context payload byte 358 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(358, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip358x20_roundtrip() -> None:
    """context payload byte 358 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(358, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip358x80_typed() -> None:
    """context payload byte 358 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(358, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip359x01_roundtrip() -> None:
    """context payload byte 359 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(359, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip359x20_roundtrip() -> None:
    """context payload byte 359 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(359, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip359x80_typed() -> None:
    """context payload byte 359 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(359, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip360x01_roundtrip() -> None:
    """context payload byte 360 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(360, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip360x20_roundtrip() -> None:
    """context payload byte 360 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(360, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip360x80_typed() -> None:
    """context payload byte 360 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(360, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip361x01_roundtrip() -> None:
    """context payload byte 361 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(361, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip361x20_roundtrip() -> None:
    """context payload byte 361 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(361, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip361x80_typed() -> None:
    """context payload byte 361 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(361, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip362x01_roundtrip() -> None:
    """context payload byte 362 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(362, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip362x20_roundtrip() -> None:
    """context payload byte 362 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(362, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip362x80_typed() -> None:
    """context payload byte 362 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(362, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip363x01_roundtrip() -> None:
    """context payload byte 363 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(363, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip363x20_roundtrip() -> None:
    """context payload byte 363 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(363, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip363x80_typed() -> None:
    """context payload byte 363 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(363, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip364x01_roundtrip() -> None:
    """context payload byte 364 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(364, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip364x20_roundtrip() -> None:
    """context payload byte 364 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(364, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip364x80_typed() -> None:
    """context payload byte 364 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(364, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip365x01_roundtrip() -> None:
    """context payload byte 365 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(365, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip365x20_roundtrip() -> None:
    """context payload byte 365 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(365, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip365x80_typed() -> None:
    """context payload byte 365 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(365, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip366x01_roundtrip() -> None:
    """context payload byte 366 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(366, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip366x20_roundtrip() -> None:
    """context payload byte 366 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(366, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip366x80_typed() -> None:
    """context payload byte 366 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(366, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip367x01_roundtrip() -> None:
    """context payload byte 367 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(367, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip367x20_roundtrip() -> None:
    """context payload byte 367 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(367, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip367x80_typed() -> None:
    """context payload byte 367 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(367, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip368x01_roundtrip() -> None:
    """context payload byte 368 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(368, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip368x20_roundtrip() -> None:
    """context payload byte 368 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(368, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip368x80_typed() -> None:
    """context payload byte 368 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(368, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip369x01_roundtrip() -> None:
    """context payload byte 369 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(369, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip369x20_roundtrip() -> None:
    """context payload byte 369 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(369, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip369x80_typed() -> None:
    """context payload byte 369 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(369, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip370x01_roundtrip() -> None:
    """context payload byte 370 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(370, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip370x20_roundtrip() -> None:
    """context payload byte 370 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(370, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip370x80_typed() -> None:
    """context payload byte 370 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(370, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip371x01_roundtrip() -> None:
    """context payload byte 371 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(371, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip371x20_roundtrip() -> None:
    """context payload byte 371 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(371, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip371x80_typed() -> None:
    """context payload byte 371 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(371, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip372x01_roundtrip() -> None:
    """context payload byte 372 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(372, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip372x20_roundtrip() -> None:
    """context payload byte 372 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(372, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip372x80_typed() -> None:
    """context payload byte 372 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(372, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip373x01_roundtrip() -> None:
    """context payload byte 373 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(373, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip373x20_roundtrip() -> None:
    """context payload byte 373 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(373, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip373x80_typed() -> None:
    """context payload byte 373 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(373, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip374x01_roundtrip() -> None:
    """context payload byte 374 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(374, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip374x20_roundtrip() -> None:
    """context payload byte 374 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(374, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip374x80_typed() -> None:
    """context payload byte 374 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(374, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip375x01_roundtrip() -> None:
    """context payload byte 375 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(375, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip375x20_roundtrip() -> None:
    """context payload byte 375 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(375, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip375x80_typed() -> None:
    """context payload byte 375 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(375, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip376x01_roundtrip() -> None:
    """context payload byte 376 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(376, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip376x20_roundtrip() -> None:
    """context payload byte 376 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(376, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXxx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip376x80_typed() -> None:
    """context payload byte 376 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(376, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip377x01_roundtrip() -> None:
    """context payload byte 377 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(377, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip377x20_roundtrip() -> None:
    """context payload byte 377 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(377, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXx',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip377x80_typed() -> None:
    """context payload byte 377 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(377, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip378x01_roundtrip() -> None:
    """context payload byte 378 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(378, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxy',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip378x20_roundtrip() -> None:
    """context payload byte 378 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(378, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxX',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip378x80_typed() -> None:
    """context payload byte 378 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(378, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip379x01_typed() -> None:
    """context payload byte 379 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(379, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip379x20_typed() -> None:
    """context payload byte 379 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(379, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip379x80_typed() -> None:
    """context payload byte 379 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(379, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip380x01_typed() -> None:
    """context payload byte 380 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(380, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip380x20_typed() -> None:
    """context payload byte 380 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(380, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip380x80_typed() -> None:
    """context payload byte 380 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(380, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip381x01_typed() -> None:
    """context payload byte 381 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(381, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip381x20_typed() -> None:
    """context payload byte 381 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(381, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip381x80_typed() -> None:
    """context payload byte 381 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(381, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip382x01_roundtrip() -> None:
    """context payload byte 382 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(382, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'rhould_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip382x20_roundtrip() -> None:
    """context payload byte 382 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(382, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'Should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip382x80_typed() -> None:
    """context payload byte 382 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(382, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip383x01_roundtrip() -> None:
    """context payload byte 383 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(383, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'siould_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip383x20_roundtrip() -> None:
    """context payload byte 383 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(383, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'sHould_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip383x80_typed() -> None:
    """context payload byte 383 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(383, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip384x01_roundtrip() -> None:
    """context payload byte 384 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(384, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'shnuld_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip384x20_roundtrip() -> None:
    """context payload byte 384 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(384, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'shOuld_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip384x80_typed() -> None:
    """context payload byte 384 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(384, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip385x01_roundtrip() -> None:
    """context payload byte 385 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(385, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'shotld_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip385x20_roundtrip() -> None:
    """context payload byte 385 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(385, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'shoUld_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip385x80_typed() -> None:
    """context payload byte 385 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(385, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip386x01_roundtrip() -> None:
    """context payload byte 386 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(386, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'shoumd_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip386x20_roundtrip() -> None:
    """context payload byte 386 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(386, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'shouLd_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip386x80_typed() -> None:
    """context payload byte 386 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(386, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip387x01_roundtrip() -> None:
    """context payload byte 387 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(387, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'shoule_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip387x20_roundtrip() -> None:
    """context payload byte 387 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(387, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'shoulD_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip387x80_typed() -> None:
    """context payload byte 387 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(387, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip388x01_roundtrip() -> None:
    """context payload byte 388 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(388, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should^lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip388x20_roundtrip() -> None:
    """context payload byte 388 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(388, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should\x7flock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip388x80_typed() -> None:
    """context payload byte 388 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(388, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip389x01_roundtrip() -> None:
    """context payload byte 389 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(389, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_mock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip389x20_roundtrip() -> None:
    """context payload byte 389 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(389, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_Lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip389x80_typed() -> None:
    """context payload byte 389 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(389, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip390x01_roundtrip() -> None:
    """context payload byte 390 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(390, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lnck': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip390x20_roundtrip() -> None:
    """context payload byte 390 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(390, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lOck': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip390x80_typed() -> None:
    """context payload byte 390 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(390, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip391x01_roundtrip() -> None:
    """context payload byte 391 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(391, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lobk': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip391x20_roundtrip() -> None:
    """context payload byte 391 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(391, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_loCk': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip391x80_typed() -> None:
    """context payload byte 391 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(391, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip392x01_roundtrip() -> None:
    """context payload byte 392 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(392, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_locj': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip392x20_roundtrip() -> None:
    """context payload byte 392 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(392, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_locK': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_json_flip392x80_typed() -> None:
    """context payload byte 392 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(392, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip393x01_typed() -> None:
    """context payload byte 393 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(393, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip393x20_typed() -> None:
    """context payload byte 393 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(393, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip393x80_typed() -> None:
    """context payload byte 393 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(393, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip394x01_typed() -> None:
    """context payload byte 394 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(394, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip394x20_typed() -> None:
    """context payload byte 394 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(394, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip394x80_typed() -> None:
    """context payload byte 394 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(394, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip395x01_typed() -> None:
    """context payload byte 395 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(395, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip395x20_typed() -> None:
    """context payload byte 395 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(395, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip395x80_typed() -> None:
    """context payload byte 395 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(395, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip396x01_typed() -> None:
    """context payload byte 396 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(396, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip396x20_typed() -> None:
    """context payload byte 396 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(396, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip396x80_typed() -> None:
    """context payload byte 396 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(396, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip397x01_typed() -> None:
    """context payload byte 397 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(397, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip397x20_typed() -> None:
    """context payload byte 397 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(397, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip397x80_typed() -> None:
    """context payload byte 397 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(397, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip398x01_typed() -> None:
    """context payload byte 398 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(398, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip398x20_typed() -> None:
    """context payload byte 398 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(398, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip398x80_typed() -> None:
    """context payload byte 398 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(398, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip399x01_typed() -> None:
    """context payload byte 399 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(399, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip399x20_typed() -> None:
    """context payload byte 399 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(399, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip399x80_typed() -> None:
    """context payload byte 399 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(399, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip400x01_typed() -> None:
    """context payload byte 400 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(400, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip400x20_typed() -> None:
    """context payload byte 400 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(400, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip400x80_typed() -> None:
    """context payload byte 400 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(400, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip401x01_roundtrip() -> None:
    """context payload byte 401 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(401, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'rource': 'omicapture',
        'version': 1,
    }


def test_json_flip401x20_roundtrip() -> None:
    """context payload byte 401 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(401, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'Source': 'omicapture',
        'version': 1,
    }


def test_json_flip401x80_typed() -> None:
    """context payload byte 401 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(401, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip402x01_roundtrip() -> None:
    """context payload byte 402 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(402, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'snurce': 'omicapture',
        'version': 1,
    }


def test_json_flip402x20_roundtrip() -> None:
    """context payload byte 402 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(402, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'sOurce': 'omicapture',
        'version': 1,
    }


def test_json_flip402x80_typed() -> None:
    """context payload byte 402 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(402, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip403x01_roundtrip() -> None:
    """context payload byte 403 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(403, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'sotrce': 'omicapture',
        'version': 1,
    }


def test_json_flip403x20_roundtrip() -> None:
    """context payload byte 403 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(403, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'soUrce': 'omicapture',
        'version': 1,
    }


def test_json_flip403x80_typed() -> None:
    """context payload byte 403 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(403, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip404x01_roundtrip() -> None:
    """context payload byte 404 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(404, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'sousce': 'omicapture',
        'version': 1,
    }


def test_json_flip404x20_roundtrip() -> None:
    """context payload byte 404 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(404, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'souRce': 'omicapture',
        'version': 1,
    }


def test_json_flip404x80_typed() -> None:
    """context payload byte 404 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(404, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip405x01_roundtrip() -> None:
    """context payload byte 405 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(405, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'sourbe': 'omicapture',
        'version': 1,
    }


def test_json_flip405x20_roundtrip() -> None:
    """context payload byte 405 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(405, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'sourCe': 'omicapture',
        'version': 1,
    }


def test_json_flip405x80_typed() -> None:
    """context payload byte 405 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(405, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip406x01_roundtrip() -> None:
    """context payload byte 406 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(406, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'sourcd': 'omicapture',
        'version': 1,
    }


def test_json_flip406x20_roundtrip() -> None:
    """context payload byte 406 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(406, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'sourcE': 'omicapture',
        'version': 1,
    }


def test_json_flip406x80_typed() -> None:
    """context payload byte 406 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(406, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip407x01_typed() -> None:
    """context payload byte 407 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(407, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip407x20_typed() -> None:
    """context payload byte 407 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(407, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip407x80_typed() -> None:
    """context payload byte 407 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(407, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip408x01_typed() -> None:
    """context payload byte 408 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(408, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip408x20_typed() -> None:
    """context payload byte 408 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(408, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip408x80_typed() -> None:
    """context payload byte 408 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(408, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip409x01_typed() -> None:
    """context payload byte 409 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(409, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip409x20_typed() -> None:
    """context payload byte 409 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(409, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip409x80_typed() -> None:
    """context payload byte 409 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(409, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip410x01_roundtrip() -> None:
    """context payload byte 410 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(410, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'nmicapture',
        'version': 1,
    }


def test_json_flip410x20_roundtrip() -> None:
    """context payload byte 410 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(410, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'Omicapture',
        'version': 1,
    }


def test_json_flip410x80_typed() -> None:
    """context payload byte 410 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(410, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip411x01_roundtrip() -> None:
    """context payload byte 411 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(411, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'olicapture',
        'version': 1,
    }


def test_json_flip411x20_roundtrip() -> None:
    """context payload byte 411 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(411, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'oMicapture',
        'version': 1,
    }


def test_json_flip411x80_typed() -> None:
    """context payload byte 411 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(411, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip412x01_roundtrip() -> None:
    """context payload byte 412 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(412, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omhcapture',
        'version': 1,
    }


def test_json_flip412x20_roundtrip() -> None:
    """context payload byte 412 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(412, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omIcapture',
        'version': 1,
    }


def test_json_flip412x80_typed() -> None:
    """context payload byte 412 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(412, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip413x01_roundtrip() -> None:
    """context payload byte 413 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(413, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omibapture',
        'version': 1,
    }


def test_json_flip413x20_roundtrip() -> None:
    """context payload byte 413 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(413, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omiCapture',
        'version': 1,
    }


def test_json_flip413x80_typed() -> None:
    """context payload byte 413 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(413, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip414x01_roundtrip() -> None:
    """context payload byte 414 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(414, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omic`pture',
        'version': 1,
    }


def test_json_flip414x20_roundtrip() -> None:
    """context payload byte 414 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(414, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicApture',
        'version': 1,
    }


def test_json_flip414x80_typed() -> None:
    """context payload byte 414 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(414, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip415x01_roundtrip() -> None:
    """context payload byte 415 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(415, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicaqture',
        'version': 1,
    }


def test_json_flip415x20_roundtrip() -> None:
    """context payload byte 415 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(415, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicaPture',
        'version': 1,
    }


def test_json_flip415x80_typed() -> None:
    """context payload byte 415 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(415, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip416x01_roundtrip() -> None:
    """context payload byte 416 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(416, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapuure',
        'version': 1,
    }


def test_json_flip416x20_roundtrip() -> None:
    """context payload byte 416 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(416, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapTure',
        'version': 1,
    }


def test_json_flip416x80_typed() -> None:
    """context payload byte 416 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(416, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip417x01_roundtrip() -> None:
    """context payload byte 417 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(417, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapttre',
        'version': 1,
    }


def test_json_flip417x20_roundtrip() -> None:
    """context payload byte 417 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(417, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicaptUre',
        'version': 1,
    }


def test_json_flip417x80_typed() -> None:
    """context payload byte 417 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(417, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip418x01_roundtrip() -> None:
    """context payload byte 418 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(418, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicaptuse',
        'version': 1,
    }


def test_json_flip418x20_roundtrip() -> None:
    """context payload byte 418 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(418, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicaptuRe',
        'version': 1,
    }


def test_json_flip418x80_typed() -> None:
    """context payload byte 418 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(418, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip419x01_roundtrip() -> None:
    """context payload byte 419 ^= 0x01: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(419, 0x01))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapturd',
        'version': 1,
    }


def test_json_flip419x20_roundtrip() -> None:
    """context payload byte 419 ^= 0x20: reader returns the sealed context verbatim."""
    assert read_context(_rewrite(long, _flip(419, 0x20))) == {
        'client_device_id': 'device-with-a-fairly-long-identifier-string-0001',
        'note': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'should_lock': True,
        'source': 'omicapturE',
        'version': 1,
    }


def test_json_flip419x80_typed() -> None:
    """context payload byte 419 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(419, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip420x01_typed() -> None:
    """context payload byte 420 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(420, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip420x20_typed() -> None:
    """context payload byte 420 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(420, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip420x80_typed() -> None:
    """context payload byte 420 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(420, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip421x01_typed() -> None:
    """context payload byte 421 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(421, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip421x20_typed() -> None:
    """context payload byte 421 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(421, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip421x80_typed() -> None:
    """context payload byte 421 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(421, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip422x01_typed() -> None:
    """context payload byte 422 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(422, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip422x20_typed() -> None:
    """context payload byte 422 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(422, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip422x80_typed() -> None:
    """context payload byte 422 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(422, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip423x01_typed() -> None:
    """context payload byte 423 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(423, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip423x20_typed() -> None:
    """context payload byte 423 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(423, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip423x80_typed() -> None:
    """context payload byte 423 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(423, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip424x01_typed() -> None:
    """context payload byte 424 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(424, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip424x20_typed() -> None:
    """context payload byte 424 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(424, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip424x80_typed() -> None:
    """context payload byte 424 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(424, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip425x01_typed() -> None:
    """context payload byte 425 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(425, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip425x20_typed() -> None:
    """context payload byte 425 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(425, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip425x80_typed() -> None:
    """context payload byte 425 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(425, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip426x01_typed() -> None:
    """context payload byte 426 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(426, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip426x20_typed() -> None:
    """context payload byte 426 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(426, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip426x80_typed() -> None:
    """context payload byte 426 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(426, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip427x01_typed() -> None:
    """context payload byte 427 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(427, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip427x20_typed() -> None:
    """context payload byte 427 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(427, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip427x80_typed() -> None:
    """context payload byte 427 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(427, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip428x01_typed() -> None:
    """context payload byte 428 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(428, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip428x20_typed() -> None:
    """context payload byte 428 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(428, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip428x80_typed() -> None:
    """context payload byte 428 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(428, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip429x01_typed() -> None:
    """context payload byte 429 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(429, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip429x20_typed() -> None:
    """context payload byte 429 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(429, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip429x80_typed() -> None:
    """context payload byte 429 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(429, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip430x01_typed() -> None:
    """context payload byte 430 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(430, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip430x20_typed() -> None:
    """context payload byte 430 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(430, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip430x80_typed() -> None:
    """context payload byte 430 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(430, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip431x01_typed() -> None:
    """context payload byte 431 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(431, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip431x20_typed() -> None:
    """context payload byte 431 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(431, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip431x80_typed() -> None:
    """context payload byte 431 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(431, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip432x01_typed() -> None:
    """context payload byte 432 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(432, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip432x20_typed() -> None:
    """context payload byte 432 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(432, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip432x80_typed() -> None:
    """context payload byte 432 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(432, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip433x01_typed() -> None:
    """context payload byte 433 ^= 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(433, 0x01)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip433x20_typed() -> None:
    """context payload byte 433 ^= 0x20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(433, 0x20)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_flip433x80_typed() -> None:
    """context payload byte 433 ^= 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _flip(433, 0x80)))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut001_typed() -> None:
    """context payload cut to 1B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:1]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut002_typed() -> None:
    """context payload cut to 2B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:2]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut003_typed() -> None:
    """context payload cut to 3B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:3]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut004_typed() -> None:
    """context payload cut to 4B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:4]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut005_typed() -> None:
    """context payload cut to 5B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:5]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut006_typed() -> None:
    """context payload cut to 6B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:6]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut007_typed() -> None:
    """context payload cut to 7B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:7]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut008_typed() -> None:
    """context payload cut to 8B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:8]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut009_typed() -> None:
    """context payload cut to 9B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:9]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut010_typed() -> None:
    """context payload cut to 10B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:10]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut011_typed() -> None:
    """context payload cut to 11B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:11]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut012_typed() -> None:
    """context payload cut to 12B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:12]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut013_typed() -> None:
    """context payload cut to 13B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:13]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut014_typed() -> None:
    """context payload cut to 14B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:14]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut015_typed() -> None:
    """context payload cut to 15B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:15]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut016_typed() -> None:
    """context payload cut to 16B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:16]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut017_typed() -> None:
    """context payload cut to 17B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:17]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut018_typed() -> None:
    """context payload cut to 18B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:18]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut019_typed() -> None:
    """context payload cut to 19B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:19]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut020_typed() -> None:
    """context payload cut to 20B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:20]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut021_typed() -> None:
    """context payload cut to 21B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:21]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut022_typed() -> None:
    """context payload cut to 22B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:22]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut023_typed() -> None:
    """context payload cut to 23B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:23]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut024_typed() -> None:
    """context payload cut to 24B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:24]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut025_typed() -> None:
    """context payload cut to 25B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:25]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut026_typed() -> None:
    """context payload cut to 26B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:26]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut027_typed() -> None:
    """context payload cut to 27B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:27]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut028_typed() -> None:
    """context payload cut to 28B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:28]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut029_typed() -> None:
    """context payload cut to 29B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:29]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut030_typed() -> None:
    """context payload cut to 30B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:30]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut031_typed() -> None:
    """context payload cut to 31B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:31]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut032_typed() -> None:
    """context payload cut to 32B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:32]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut033_typed() -> None:
    """context payload cut to 33B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:33]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut034_typed() -> None:
    """context payload cut to 34B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:34]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut035_typed() -> None:
    """context payload cut to 35B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:35]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut036_typed() -> None:
    """context payload cut to 36B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:36]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut037_typed() -> None:
    """context payload cut to 37B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:37]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut038_typed() -> None:
    """context payload cut to 38B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:38]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut039_typed() -> None:
    """context payload cut to 39B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:39]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut040_typed() -> None:
    """context payload cut to 40B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:40]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut041_typed() -> None:
    """context payload cut to 41B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:41]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut042_typed() -> None:
    """context payload cut to 42B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:42]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut043_typed() -> None:
    """context payload cut to 43B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:43]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut044_typed() -> None:
    """context payload cut to 44B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:44]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut045_typed() -> None:
    """context payload cut to 45B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:45]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut046_typed() -> None:
    """context payload cut to 46B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:46]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut047_typed() -> None:
    """context payload cut to 47B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:47]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut048_typed() -> None:
    """context payload cut to 48B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:48]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut049_typed() -> None:
    """context payload cut to 49B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:49]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut050_typed() -> None:
    """context payload cut to 50B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:50]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut051_typed() -> None:
    """context payload cut to 51B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:51]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut052_typed() -> None:
    """context payload cut to 52B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:52]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut053_typed() -> None:
    """context payload cut to 53B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:53]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut054_typed() -> None:
    """context payload cut to 54B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:54]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut055_typed() -> None:
    """context payload cut to 55B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:55]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut056_typed() -> None:
    """context payload cut to 56B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:56]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut057_typed() -> None:
    """context payload cut to 57B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:57]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut058_typed() -> None:
    """context payload cut to 58B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:58]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut059_typed() -> None:
    """context payload cut to 59B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:59]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut060_typed() -> None:
    """context payload cut to 60B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:60]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut061_typed() -> None:
    """context payload cut to 61B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:61]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut062_typed() -> None:
    """context payload cut to 62B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:62]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut063_typed() -> None:
    """context payload cut to 63B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:63]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut064_typed() -> None:
    """context payload cut to 64B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:64]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut065_typed() -> None:
    """context payload cut to 65B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:65]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut066_typed() -> None:
    """context payload cut to 66B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:66]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut067_typed() -> None:
    """context payload cut to 67B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:67]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut068_typed() -> None:
    """context payload cut to 68B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:68]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut069_typed() -> None:
    """context payload cut to 69B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:69]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut070_typed() -> None:
    """context payload cut to 70B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:70]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut071_typed() -> None:
    """context payload cut to 71B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:71]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut072_typed() -> None:
    """context payload cut to 72B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:72]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut073_typed() -> None:
    """context payload cut to 73B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:73]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut074_typed() -> None:
    """context payload cut to 74B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:74]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut075_typed() -> None:
    """context payload cut to 75B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:75]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut076_typed() -> None:
    """context payload cut to 76B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:76]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut077_typed() -> None:
    """context payload cut to 77B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:77]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut078_typed() -> None:
    """context payload cut to 78B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:78]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut079_typed() -> None:
    """context payload cut to 79B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:79]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut080_typed() -> None:
    """context payload cut to 80B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:80]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut081_typed() -> None:
    """context payload cut to 81B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:81]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut082_typed() -> None:
    """context payload cut to 82B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:82]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut083_typed() -> None:
    """context payload cut to 83B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:83]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut084_typed() -> None:
    """context payload cut to 84B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:84]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut085_typed() -> None:
    """context payload cut to 85B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:85]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut086_typed() -> None:
    """context payload cut to 86B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:86]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut087_typed() -> None:
    """context payload cut to 87B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:87]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut088_typed() -> None:
    """context payload cut to 88B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:88]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut089_typed() -> None:
    """context payload cut to 89B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:89]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut090_typed() -> None:
    """context payload cut to 90B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:90]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut091_typed() -> None:
    """context payload cut to 91B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:91]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut092_typed() -> None:
    """context payload cut to 92B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:92]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut093_typed() -> None:
    """context payload cut to 93B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:93]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut094_typed() -> None:
    """context payload cut to 94B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:94]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut095_typed() -> None:
    """context payload cut to 95B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:95]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut096_typed() -> None:
    """context payload cut to 96B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:96]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut097_typed() -> None:
    """context payload cut to 97B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:97]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut098_typed() -> None:
    """context payload cut to 98B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:98]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut099_typed() -> None:
    """context payload cut to 99B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:99]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut100_typed() -> None:
    """context payload cut to 100B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:100]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut101_typed() -> None:
    """context payload cut to 101B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:101]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut102_typed() -> None:
    """context payload cut to 102B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:102]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut103_typed() -> None:
    """context payload cut to 103B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:103]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut104_typed() -> None:
    """context payload cut to 104B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:104]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut105_typed() -> None:
    """context payload cut to 105B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:105]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut106_typed() -> None:
    """context payload cut to 106B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:106]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut107_typed() -> None:
    """context payload cut to 107B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:107]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut108_typed() -> None:
    """context payload cut to 108B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:108]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut109_typed() -> None:
    """context payload cut to 109B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:109]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut110_typed() -> None:
    """context payload cut to 110B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:110]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut111_typed() -> None:
    """context payload cut to 111B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:111]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut112_typed() -> None:
    """context payload cut to 112B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:112]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut113_typed() -> None:
    """context payload cut to 113B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:113]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut114_typed() -> None:
    """context payload cut to 114B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:114]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut115_typed() -> None:
    """context payload cut to 115B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:115]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut116_typed() -> None:
    """context payload cut to 116B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:116]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut117_typed() -> None:
    """context payload cut to 117B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:117]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut118_typed() -> None:
    """context payload cut to 118B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:118]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut119_typed() -> None:
    """context payload cut to 119B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:119]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut120_typed() -> None:
    """context payload cut to 120B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:120]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut121_typed() -> None:
    """context payload cut to 121B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:121]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut122_typed() -> None:
    """context payload cut to 122B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:122]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut123_typed() -> None:
    """context payload cut to 123B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:123]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut124_typed() -> None:
    """context payload cut to 124B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:124]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut125_typed() -> None:
    """context payload cut to 125B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:125]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut126_typed() -> None:
    """context payload cut to 126B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:126]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut127_typed() -> None:
    """context payload cut to 127B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:127]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut128_typed() -> None:
    """context payload cut to 128B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:128]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut129_typed() -> None:
    """context payload cut to 129B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:129]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut130_typed() -> None:
    """context payload cut to 130B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:130]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut131_typed() -> None:
    """context payload cut to 131B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:131]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut132_typed() -> None:
    """context payload cut to 132B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:132]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut133_typed() -> None:
    """context payload cut to 133B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:133]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut134_typed() -> None:
    """context payload cut to 134B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:134]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut135_typed() -> None:
    """context payload cut to 135B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:135]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut136_typed() -> None:
    """context payload cut to 136B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:136]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut137_typed() -> None:
    """context payload cut to 137B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:137]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut138_typed() -> None:
    """context payload cut to 138B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:138]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut139_typed() -> None:
    """context payload cut to 139B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:139]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut140_typed() -> None:
    """context payload cut to 140B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:140]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut141_typed() -> None:
    """context payload cut to 141B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:141]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut142_typed() -> None:
    """context payload cut to 142B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:142]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut143_typed() -> None:
    """context payload cut to 143B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:143]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut144_typed() -> None:
    """context payload cut to 144B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:144]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut145_typed() -> None:
    """context payload cut to 145B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:145]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut146_typed() -> None:
    """context payload cut to 146B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:146]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut147_typed() -> None:
    """context payload cut to 147B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:147]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut148_typed() -> None:
    """context payload cut to 148B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:148]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut149_typed() -> None:
    """context payload cut to 149B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:149]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut150_typed() -> None:
    """context payload cut to 150B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:150]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut151_typed() -> None:
    """context payload cut to 151B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:151]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut152_typed() -> None:
    """context payload cut to 152B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:152]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut153_typed() -> None:
    """context payload cut to 153B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:153]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut154_typed() -> None:
    """context payload cut to 154B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:154]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut155_typed() -> None:
    """context payload cut to 155B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:155]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut156_typed() -> None:
    """context payload cut to 156B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:156]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut157_typed() -> None:
    """context payload cut to 157B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:157]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut158_typed() -> None:
    """context payload cut to 158B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:158]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut159_typed() -> None:
    """context payload cut to 159B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:159]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut160_typed() -> None:
    """context payload cut to 160B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:160]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut161_typed() -> None:
    """context payload cut to 161B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:161]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut162_typed() -> None:
    """context payload cut to 162B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:162]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut163_typed() -> None:
    """context payload cut to 163B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:163]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut164_typed() -> None:
    """context payload cut to 164B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:164]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut165_typed() -> None:
    """context payload cut to 165B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:165]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut166_typed() -> None:
    """context payload cut to 166B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:166]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut167_typed() -> None:
    """context payload cut to 167B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:167]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut168_typed() -> None:
    """context payload cut to 168B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:168]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut169_typed() -> None:
    """context payload cut to 169B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:169]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut170_typed() -> None:
    """context payload cut to 170B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:170]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut171_typed() -> None:
    """context payload cut to 171B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:171]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut172_typed() -> None:
    """context payload cut to 172B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:172]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut173_typed() -> None:
    """context payload cut to 173B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:173]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut174_typed() -> None:
    """context payload cut to 174B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:174]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut175_typed() -> None:
    """context payload cut to 175B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:175]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut176_typed() -> None:
    """context payload cut to 176B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:176]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut177_typed() -> None:
    """context payload cut to 177B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:177]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut178_typed() -> None:
    """context payload cut to 178B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:178]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut179_typed() -> None:
    """context payload cut to 179B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:179]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut180_typed() -> None:
    """context payload cut to 180B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:180]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut181_typed() -> None:
    """context payload cut to 181B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:181]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut182_typed() -> None:
    """context payload cut to 182B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:182]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut183_typed() -> None:
    """context payload cut to 183B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:183]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut184_typed() -> None:
    """context payload cut to 184B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:184]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut185_typed() -> None:
    """context payload cut to 185B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:185]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut186_typed() -> None:
    """context payload cut to 186B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:186]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut187_typed() -> None:
    """context payload cut to 187B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:187]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut188_typed() -> None:
    """context payload cut to 188B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:188]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut189_typed() -> None:
    """context payload cut to 189B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:189]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut190_typed() -> None:
    """context payload cut to 190B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:190]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut191_typed() -> None:
    """context payload cut to 191B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:191]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut192_typed() -> None:
    """context payload cut to 192B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:192]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut193_typed() -> None:
    """context payload cut to 193B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:193]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut194_typed() -> None:
    """context payload cut to 194B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:194]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut195_typed() -> None:
    """context payload cut to 195B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:195]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut196_typed() -> None:
    """context payload cut to 196B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:196]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut197_typed() -> None:
    """context payload cut to 197B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:197]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut198_typed() -> None:
    """context payload cut to 198B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:198]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut199_typed() -> None:
    """context payload cut to 199B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:199]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut200_typed() -> None:
    """context payload cut to 200B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:200]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut201_typed() -> None:
    """context payload cut to 201B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:201]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut202_typed() -> None:
    """context payload cut to 202B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:202]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut203_typed() -> None:
    """context payload cut to 203B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:203]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut204_typed() -> None:
    """context payload cut to 204B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:204]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut205_typed() -> None:
    """context payload cut to 205B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:205]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut206_typed() -> None:
    """context payload cut to 206B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:206]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut207_typed() -> None:
    """context payload cut to 207B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:207]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut208_typed() -> None:
    """context payload cut to 208B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:208]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut209_typed() -> None:
    """context payload cut to 209B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:209]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut210_typed() -> None:
    """context payload cut to 210B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:210]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut211_typed() -> None:
    """context payload cut to 211B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:211]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut212_typed() -> None:
    """context payload cut to 212B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:212]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut213_typed() -> None:
    """context payload cut to 213B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:213]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut214_typed() -> None:
    """context payload cut to 214B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:214]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut215_typed() -> None:
    """context payload cut to 215B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:215]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut216_typed() -> None:
    """context payload cut to 216B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:216]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut217_typed() -> None:
    """context payload cut to 217B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:217]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut218_typed() -> None:
    """context payload cut to 218B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:218]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut219_typed() -> None:
    """context payload cut to 219B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:219]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut220_typed() -> None:
    """context payload cut to 220B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:220]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut221_typed() -> None:
    """context payload cut to 221B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:221]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut222_typed() -> None:
    """context payload cut to 222B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:222]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut223_typed() -> None:
    """context payload cut to 223B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:223]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut224_typed() -> None:
    """context payload cut to 224B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:224]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut225_typed() -> None:
    """context payload cut to 225B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:225]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut226_typed() -> None:
    """context payload cut to 226B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:226]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut227_typed() -> None:
    """context payload cut to 227B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:227]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut228_typed() -> None:
    """context payload cut to 228B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:228]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut229_typed() -> None:
    """context payload cut to 229B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:229]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut230_typed() -> None:
    """context payload cut to 230B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:230]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut231_typed() -> None:
    """context payload cut to 231B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:231]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut232_typed() -> None:
    """context payload cut to 232B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:232]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut233_typed() -> None:
    """context payload cut to 233B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:233]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut234_typed() -> None:
    """context payload cut to 234B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:234]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut235_typed() -> None:
    """context payload cut to 235B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:235]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut236_typed() -> None:
    """context payload cut to 236B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:236]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut237_typed() -> None:
    """context payload cut to 237B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:237]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut238_typed() -> None:
    """context payload cut to 238B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:238]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut239_typed() -> None:
    """context payload cut to 239B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:239]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut240_typed() -> None:
    """context payload cut to 240B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:240]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut241_typed() -> None:
    """context payload cut to 241B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:241]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut242_typed() -> None:
    """context payload cut to 242B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:242]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut243_typed() -> None:
    """context payload cut to 243B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:243]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut244_typed() -> None:
    """context payload cut to 244B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:244]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut245_typed() -> None:
    """context payload cut to 245B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:245]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut246_typed() -> None:
    """context payload cut to 246B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:246]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut247_typed() -> None:
    """context payload cut to 247B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:247]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut248_typed() -> None:
    """context payload cut to 248B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:248]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut249_typed() -> None:
    """context payload cut to 249B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:249]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut250_typed() -> None:
    """context payload cut to 250B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:250]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut251_typed() -> None:
    """context payload cut to 251B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:251]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut252_typed() -> None:
    """context payload cut to 252B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:252]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut253_typed() -> None:
    """context payload cut to 253B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:253]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut254_typed() -> None:
    """context payload cut to 254B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:254]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut255_typed() -> None:
    """context payload cut to 255B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:255]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut256_typed() -> None:
    """context payload cut to 256B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:256]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut257_typed() -> None:
    """context payload cut to 257B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:257]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut258_typed() -> None:
    """context payload cut to 258B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:258]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut259_typed() -> None:
    """context payload cut to 259B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:259]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut260_typed() -> None:
    """context payload cut to 260B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:260]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut261_typed() -> None:
    """context payload cut to 261B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:261]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut262_typed() -> None:
    """context payload cut to 262B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:262]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut263_typed() -> None:
    """context payload cut to 263B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:263]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut264_typed() -> None:
    """context payload cut to 264B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:264]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut265_typed() -> None:
    """context payload cut to 265B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:265]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut266_typed() -> None:
    """context payload cut to 266B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:266]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut267_typed() -> None:
    """context payload cut to 267B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:267]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut268_typed() -> None:
    """context payload cut to 268B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:268]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut269_typed() -> None:
    """context payload cut to 269B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:269]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut270_typed() -> None:
    """context payload cut to 270B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:270]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut271_typed() -> None:
    """context payload cut to 271B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:271]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut272_typed() -> None:
    """context payload cut to 272B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:272]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut273_typed() -> None:
    """context payload cut to 273B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:273]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut274_typed() -> None:
    """context payload cut to 274B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:274]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut275_typed() -> None:
    """context payload cut to 275B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:275]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut276_typed() -> None:
    """context payload cut to 276B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:276]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut277_typed() -> None:
    """context payload cut to 277B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:277]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut278_typed() -> None:
    """context payload cut to 278B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:278]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut279_typed() -> None:
    """context payload cut to 279B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:279]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut280_typed() -> None:
    """context payload cut to 280B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:280]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut281_typed() -> None:
    """context payload cut to 281B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:281]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut282_typed() -> None:
    """context payload cut to 282B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:282]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut283_typed() -> None:
    """context payload cut to 283B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:283]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut284_typed() -> None:
    """context payload cut to 284B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:284]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut285_typed() -> None:
    """context payload cut to 285B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:285]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut286_typed() -> None:
    """context payload cut to 286B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:286]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut287_typed() -> None:
    """context payload cut to 287B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:287]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut288_typed() -> None:
    """context payload cut to 288B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:288]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut289_typed() -> None:
    """context payload cut to 289B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:289]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut290_typed() -> None:
    """context payload cut to 290B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:290]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut291_typed() -> None:
    """context payload cut to 291B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:291]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut292_typed() -> None:
    """context payload cut to 292B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:292]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut293_typed() -> None:
    """context payload cut to 293B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:293]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut294_typed() -> None:
    """context payload cut to 294B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:294]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut295_typed() -> None:
    """context payload cut to 295B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:295]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut296_typed() -> None:
    """context payload cut to 296B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:296]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut297_typed() -> None:
    """context payload cut to 297B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:297]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut298_typed() -> None:
    """context payload cut to 298B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:298]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut299_typed() -> None:
    """context payload cut to 299B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:299]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut300_typed() -> None:
    """context payload cut to 300B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:300]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut301_typed() -> None:
    """context payload cut to 301B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:301]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut302_typed() -> None:
    """context payload cut to 302B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:302]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut303_typed() -> None:
    """context payload cut to 303B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:303]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut304_typed() -> None:
    """context payload cut to 304B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:304]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut305_typed() -> None:
    """context payload cut to 305B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:305]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut306_typed() -> None:
    """context payload cut to 306B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:306]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut307_typed() -> None:
    """context payload cut to 307B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:307]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut308_typed() -> None:
    """context payload cut to 308B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:308]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut309_typed() -> None:
    """context payload cut to 309B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:309]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut310_typed() -> None:
    """context payload cut to 310B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:310]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut311_typed() -> None:
    """context payload cut to 311B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:311]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut312_typed() -> None:
    """context payload cut to 312B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:312]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut313_typed() -> None:
    """context payload cut to 313B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:313]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut314_typed() -> None:
    """context payload cut to 314B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:314]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut315_typed() -> None:
    """context payload cut to 315B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:315]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut316_typed() -> None:
    """context payload cut to 316B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:316]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut317_typed() -> None:
    """context payload cut to 317B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:317]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut318_typed() -> None:
    """context payload cut to 318B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:318]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut319_typed() -> None:
    """context payload cut to 319B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:319]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut320_typed() -> None:
    """context payload cut to 320B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:320]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut321_typed() -> None:
    """context payload cut to 321B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:321]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut322_typed() -> None:
    """context payload cut to 322B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:322]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut323_typed() -> None:
    """context payload cut to 323B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:323]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut324_typed() -> None:
    """context payload cut to 324B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:324]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut325_typed() -> None:
    """context payload cut to 325B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:325]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut326_typed() -> None:
    """context payload cut to 326B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:326]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut327_typed() -> None:
    """context payload cut to 327B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:327]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut328_typed() -> None:
    """context payload cut to 328B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:328]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut329_typed() -> None:
    """context payload cut to 329B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:329]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut330_typed() -> None:
    """context payload cut to 330B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:330]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut331_typed() -> None:
    """context payload cut to 331B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:331]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut332_typed() -> None:
    """context payload cut to 332B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:332]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut333_typed() -> None:
    """context payload cut to 333B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:333]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut334_typed() -> None:
    """context payload cut to 334B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:334]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut335_typed() -> None:
    """context payload cut to 335B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:335]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut336_typed() -> None:
    """context payload cut to 336B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:336]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut337_typed() -> None:
    """context payload cut to 337B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:337]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut338_typed() -> None:
    """context payload cut to 338B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:338]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut339_typed() -> None:
    """context payload cut to 339B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:339]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut340_typed() -> None:
    """context payload cut to 340B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:340]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut341_typed() -> None:
    """context payload cut to 341B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:341]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut342_typed() -> None:
    """context payload cut to 342B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:342]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut343_typed() -> None:
    """context payload cut to 343B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:343]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut344_typed() -> None:
    """context payload cut to 344B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:344]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut345_typed() -> None:
    """context payload cut to 345B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:345]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut346_typed() -> None:
    """context payload cut to 346B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:346]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut347_typed() -> None:
    """context payload cut to 347B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:347]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut348_typed() -> None:
    """context payload cut to 348B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:348]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut349_typed() -> None:
    """context payload cut to 349B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:349]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut350_typed() -> None:
    """context payload cut to 350B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:350]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut351_typed() -> None:
    """context payload cut to 351B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:351]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut352_typed() -> None:
    """context payload cut to 352B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:352]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut353_typed() -> None:
    """context payload cut to 353B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:353]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut354_typed() -> None:
    """context payload cut to 354B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:354]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut355_typed() -> None:
    """context payload cut to 355B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:355]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut356_typed() -> None:
    """context payload cut to 356B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:356]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut357_typed() -> None:
    """context payload cut to 357B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:357]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut358_typed() -> None:
    """context payload cut to 358B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:358]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut359_typed() -> None:
    """context payload cut to 359B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:359]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut360_typed() -> None:
    """context payload cut to 360B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:360]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut361_typed() -> None:
    """context payload cut to 361B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:361]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut362_typed() -> None:
    """context payload cut to 362B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:362]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut363_typed() -> None:
    """context payload cut to 363B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:363]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut364_typed() -> None:
    """context payload cut to 364B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:364]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut365_typed() -> None:
    """context payload cut to 365B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:365]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut366_typed() -> None:
    """context payload cut to 366B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:366]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut367_typed() -> None:
    """context payload cut to 367B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:367]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut368_typed() -> None:
    """context payload cut to 368B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:368]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut369_typed() -> None:
    """context payload cut to 369B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:369]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut370_typed() -> None:
    """context payload cut to 370B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:370]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut371_typed() -> None:
    """context payload cut to 371B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:371]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut372_typed() -> None:
    """context payload cut to 372B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:372]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut373_typed() -> None:
    """context payload cut to 373B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:373]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut374_typed() -> None:
    """context payload cut to 374B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:374]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut375_typed() -> None:
    """context payload cut to 375B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:375]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut376_typed() -> None:
    """context payload cut to 376B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:376]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut377_typed() -> None:
    """context payload cut to 377B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:377]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut378_typed() -> None:
    """context payload cut to 378B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:378]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut379_typed() -> None:
    """context payload cut to 379B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:379]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut380_typed() -> None:
    """context payload cut to 380B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:380]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut381_typed() -> None:
    """context payload cut to 381B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:381]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut382_typed() -> None:
    """context payload cut to 382B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:382]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut383_typed() -> None:
    """context payload cut to 383B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:383]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut384_typed() -> None:
    """context payload cut to 384B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:384]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut385_typed() -> None:
    """context payload cut to 385B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:385]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut386_typed() -> None:
    """context payload cut to 386B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:386]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut387_typed() -> None:
    """context payload cut to 387B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:387]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut388_typed() -> None:
    """context payload cut to 388B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:388]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut389_typed() -> None:
    """context payload cut to 389B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:389]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut390_typed() -> None:
    """context payload cut to 390B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:390]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut391_typed() -> None:
    """context payload cut to 391B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:391]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut392_typed() -> None:
    """context payload cut to 392B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:392]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut393_typed() -> None:
    """context payload cut to 393B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:393]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut394_typed() -> None:
    """context payload cut to 394B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:394]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut395_typed() -> None:
    """context payload cut to 395B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:395]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut396_typed() -> None:
    """context payload cut to 396B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:396]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut397_typed() -> None:
    """context payload cut to 397B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:397]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut398_typed() -> None:
    """context payload cut to 398B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:398]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut399_typed() -> None:
    """context payload cut to 399B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:399]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut400_typed() -> None:
    """context payload cut to 400B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:400]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut401_typed() -> None:
    """context payload cut to 401B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:401]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut402_typed() -> None:
    """context payload cut to 402B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:402]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut403_typed() -> None:
    """context payload cut to 403B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:403]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut404_typed() -> None:
    """context payload cut to 404B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:404]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut405_typed() -> None:
    """context payload cut to 405B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:405]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut406_typed() -> None:
    """context payload cut to 406B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:406]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut407_typed() -> None:
    """context payload cut to 407B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:407]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut408_typed() -> None:
    """context payload cut to 408B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:408]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut409_typed() -> None:
    """context payload cut to 409B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:409]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut410_typed() -> None:
    """context payload cut to 410B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:410]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut411_typed() -> None:
    """context payload cut to 411B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:411]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut412_typed() -> None:
    """context payload cut to 412B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:412]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut413_typed() -> None:
    """context payload cut to 413B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:413]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut414_typed() -> None:
    """context payload cut to 414B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:414]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut415_typed() -> None:
    """context payload cut to 415B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:415]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut416_typed() -> None:
    """context payload cut to 416B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:416]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut417_typed() -> None:
    """context payload cut to 417B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:417]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut418_typed() -> None:
    """context payload cut to 418B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:418]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut419_typed() -> None:
    """context payload cut to 419B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:419]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut420_typed() -> None:
    """context payload cut to 420B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:420]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut421_typed() -> None:
    """context payload cut to 421B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:421]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut422_typed() -> None:
    """context payload cut to 422B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:422]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut423_typed() -> None:
    """context payload cut to 423B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:423]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut424_typed() -> None:
    """context payload cut to 424B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:424]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut425_typed() -> None:
    """context payload cut to 425B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:425]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut426_typed() -> None:
    """context payload cut to 426B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:426]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut427_typed() -> None:
    """context payload cut to 427B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:427]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut428_typed() -> None:
    """context payload cut to 428B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:428]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut429_typed() -> None:
    """context payload cut to 429B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:429]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut430_typed() -> None:
    """context payload cut to 430B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:430]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut431_typed() -> None:
    """context payload cut to 431B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:431]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut432_typed() -> None:
    """context payload cut to 432B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:432]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_json_cut433_typed() -> None:
    """context payload cut to 433B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_rewrite(long, _payload(long)[:433]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'
