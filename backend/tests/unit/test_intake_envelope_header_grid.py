"""Intake envelope header gate grid: frozen verdict per cell.

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


def test_header_sizep0001_typed() -> None:
    """declared RIFF size +1: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 1))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0001_typed() -> None:
    """declared RIFF size -1: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -1))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0002_typed() -> None:
    """declared RIFF size +2: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 2))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0002_typed() -> None:
    """declared RIFF size -2: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -2))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0003_typed() -> None:
    """declared RIFF size +3: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 3))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0003_typed() -> None:
    """declared RIFF size -3: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -3))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0004_typed() -> None:
    """declared RIFF size +4: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 4))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0004_typed() -> None:
    """declared RIFF size -4: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -4))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0005_typed() -> None:
    """declared RIFF size +5: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 5))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0005_typed() -> None:
    """declared RIFF size -5: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -5))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0006_typed() -> None:
    """declared RIFF size +6: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 6))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0006_typed() -> None:
    """declared RIFF size -6: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -6))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0007_typed() -> None:
    """declared RIFF size +7: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 7))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0007_typed() -> None:
    """declared RIFF size -7: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -7))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0008_typed() -> None:
    """declared RIFF size +8: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 8))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0008_typed() -> None:
    """declared RIFF size -8: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -8))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0009_typed() -> None:
    """declared RIFF size +9: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 9))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0009_typed() -> None:
    """declared RIFF size -9: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -9))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0010_typed() -> None:
    """declared RIFF size +10: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 10))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0010_typed() -> None:
    """declared RIFF size -10: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -10))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0011_typed() -> None:
    """declared RIFF size +11: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 11))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0011_typed() -> None:
    """declared RIFF size -11: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -11))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0012_typed() -> None:
    """declared RIFF size +12: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 12))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0012_typed() -> None:
    """declared RIFF size -12: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -12))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0013_typed() -> None:
    """declared RIFF size +13: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 13))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0013_typed() -> None:
    """declared RIFF size -13: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -13))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0014_typed() -> None:
    """declared RIFF size +14: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 14))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0014_typed() -> None:
    """declared RIFF size -14: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -14))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0015_typed() -> None:
    """declared RIFF size +15: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 15))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0015_typed() -> None:
    """declared RIFF size -15: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -15))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0016_typed() -> None:
    """declared RIFF size +16: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 16))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0016_typed() -> None:
    """declared RIFF size -16: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -16))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0017_typed() -> None:
    """declared RIFF size +17: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 17))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0017_typed() -> None:
    """declared RIFF size -17: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -17))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0018_typed() -> None:
    """declared RIFF size +18: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 18))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0018_typed() -> None:
    """declared RIFF size -18: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -18))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0019_typed() -> None:
    """declared RIFF size +19: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 19))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0019_typed() -> None:
    """declared RIFF size -19: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -19))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0020_typed() -> None:
    """declared RIFF size +20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 20))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0020_typed() -> None:
    """declared RIFF size -20: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -20))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0021_typed() -> None:
    """declared RIFF size +21: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 21))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0021_typed() -> None:
    """declared RIFF size -21: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -21))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0022_typed() -> None:
    """declared RIFF size +22: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 22))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0022_typed() -> None:
    """declared RIFF size -22: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -22))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0023_typed() -> None:
    """declared RIFF size +23: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 23))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0023_typed() -> None:
    """declared RIFF size -23: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -23))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0024_typed() -> None:
    """declared RIFF size +24: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 24))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0024_typed() -> None:
    """declared RIFF size -24: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -24))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0025_typed() -> None:
    """declared RIFF size +25: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 25))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0025_typed() -> None:
    """declared RIFF size -25: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -25))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0026_typed() -> None:
    """declared RIFF size +26: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 26))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0026_typed() -> None:
    """declared RIFF size -26: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -26))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0027_typed() -> None:
    """declared RIFF size +27: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 27))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0027_typed() -> None:
    """declared RIFF size -27: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -27))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0028_typed() -> None:
    """declared RIFF size +28: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 28))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0028_typed() -> None:
    """declared RIFF size -28: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -28))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0029_typed() -> None:
    """declared RIFF size +29: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 29))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0029_typed() -> None:
    """declared RIFF size -29: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -29))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0030_typed() -> None:
    """declared RIFF size +30: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 30))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0030_typed() -> None:
    """declared RIFF size -30: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -30))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0031_typed() -> None:
    """declared RIFF size +31: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 31))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0031_typed() -> None:
    """declared RIFF size -31: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -31))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0032_typed() -> None:
    """declared RIFF size +32: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 32))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0032_typed() -> None:
    """declared RIFF size -32: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -32))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0033_typed() -> None:
    """declared RIFF size +33: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 33))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0033_typed() -> None:
    """declared RIFF size -33: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -33))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0034_typed() -> None:
    """declared RIFF size +34: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 34))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0034_typed() -> None:
    """declared RIFF size -34: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -34))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0035_typed() -> None:
    """declared RIFF size +35: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 35))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0035_typed() -> None:
    """declared RIFF size -35: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -35))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0036_typed() -> None:
    """declared RIFF size +36: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 36))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0036_typed() -> None:
    """declared RIFF size -36: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -36))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0037_typed() -> None:
    """declared RIFF size +37: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 37))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0037_typed() -> None:
    """declared RIFF size -37: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -37))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0038_typed() -> None:
    """declared RIFF size +38: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 38))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0038_typed() -> None:
    """declared RIFF size -38: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -38))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0039_typed() -> None:
    """declared RIFF size +39: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 39))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0039_typed() -> None:
    """declared RIFF size -39: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -39))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0040_typed() -> None:
    """declared RIFF size +40: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 40))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0040_typed() -> None:
    """declared RIFF size -40: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -40))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0041_typed() -> None:
    """declared RIFF size +41: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 41))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0041_typed() -> None:
    """declared RIFF size -41: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -41))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0042_typed() -> None:
    """declared RIFF size +42: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 42))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0042_typed() -> None:
    """declared RIFF size -42: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -42))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0043_typed() -> None:
    """declared RIFF size +43: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 43))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0043_typed() -> None:
    """declared RIFF size -43: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -43))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0044_typed() -> None:
    """declared RIFF size +44: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 44))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0044_typed() -> None:
    """declared RIFF size -44: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -44))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0045_typed() -> None:
    """declared RIFF size +45: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 45))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0045_typed() -> None:
    """declared RIFF size -45: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -45))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0046_typed() -> None:
    """declared RIFF size +46: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 46))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0046_typed() -> None:
    """declared RIFF size -46: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -46))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0047_typed() -> None:
    """declared RIFF size +47: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 47))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0047_typed() -> None:
    """declared RIFF size -47: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -47))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0048_typed() -> None:
    """declared RIFF size +48: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 48))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0048_typed() -> None:
    """declared RIFF size -48: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -48))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0049_typed() -> None:
    """declared RIFF size +49: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 49))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0049_typed() -> None:
    """declared RIFF size -49: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -49))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0050_typed() -> None:
    """declared RIFF size +50: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 50))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0050_typed() -> None:
    """declared RIFF size -50: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -50))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0051_typed() -> None:
    """declared RIFF size +51: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 51))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0051_typed() -> None:
    """declared RIFF size -51: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -51))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0052_typed() -> None:
    """declared RIFF size +52: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 52))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0052_typed() -> None:
    """declared RIFF size -52: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -52))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0053_typed() -> None:
    """declared RIFF size +53: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 53))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0053_typed() -> None:
    """declared RIFF size -53: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -53))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0054_typed() -> None:
    """declared RIFF size +54: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 54))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0054_typed() -> None:
    """declared RIFF size -54: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -54))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0055_typed() -> None:
    """declared RIFF size +55: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 55))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0055_typed() -> None:
    """declared RIFF size -55: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -55))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0056_typed() -> None:
    """declared RIFF size +56: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 56))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0056_typed() -> None:
    """declared RIFF size -56: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -56))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0057_typed() -> None:
    """declared RIFF size +57: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 57))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0057_typed() -> None:
    """declared RIFF size -57: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -57))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0058_typed() -> None:
    """declared RIFF size +58: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 58))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0058_typed() -> None:
    """declared RIFF size -58: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -58))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0059_typed() -> None:
    """declared RIFF size +59: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 59))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0059_typed() -> None:
    """declared RIFF size -59: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -59))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0060_typed() -> None:
    """declared RIFF size +60: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 60))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0060_typed() -> None:
    """declared RIFF size -60: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -60))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0061_typed() -> None:
    """declared RIFF size +61: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 61))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0061_typed() -> None:
    """declared RIFF size -61: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -61))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0062_typed() -> None:
    """declared RIFF size +62: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 62))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0062_typed() -> None:
    """declared RIFF size -62: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -62))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0063_typed() -> None:
    """declared RIFF size +63: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 63))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0063_typed() -> None:
    """declared RIFF size -63: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -63))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0064_typed() -> None:
    """declared RIFF size +64: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 64))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0064_typed() -> None:
    """declared RIFF size -64: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -64))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0065_typed() -> None:
    """declared RIFF size +65: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 65))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0065_typed() -> None:
    """declared RIFF size -65: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -65))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0066_typed() -> None:
    """declared RIFF size +66: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 66))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0066_typed() -> None:
    """declared RIFF size -66: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -66))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0067_typed() -> None:
    """declared RIFF size +67: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 67))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0067_typed() -> None:
    """declared RIFF size -67: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -67))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0068_typed() -> None:
    """declared RIFF size +68: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 68))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0068_typed() -> None:
    """declared RIFF size -68: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -68))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0069_typed() -> None:
    """declared RIFF size +69: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 69))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0069_typed() -> None:
    """declared RIFF size -69: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -69))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0070_typed() -> None:
    """declared RIFF size +70: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 70))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0070_typed() -> None:
    """declared RIFF size -70: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -70))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0071_typed() -> None:
    """declared RIFF size +71: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 71))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0071_typed() -> None:
    """declared RIFF size -71: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -71))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0072_typed() -> None:
    """declared RIFF size +72: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 72))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0072_typed() -> None:
    """declared RIFF size -72: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -72))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0073_typed() -> None:
    """declared RIFF size +73: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 73))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0073_typed() -> None:
    """declared RIFF size -73: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -73))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0074_typed() -> None:
    """declared RIFF size +74: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 74))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0074_typed() -> None:
    """declared RIFF size -74: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -74))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0075_typed() -> None:
    """declared RIFF size +75: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 75))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0075_typed() -> None:
    """declared RIFF size -75: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -75))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0076_typed() -> None:
    """declared RIFF size +76: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 76))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0076_typed() -> None:
    """declared RIFF size -76: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -76))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0077_typed() -> None:
    """declared RIFF size +77: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 77))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0077_typed() -> None:
    """declared RIFF size -77: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -77))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0078_typed() -> None:
    """declared RIFF size +78: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 78))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0078_typed() -> None:
    """declared RIFF size -78: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -78))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0079_typed() -> None:
    """declared RIFF size +79: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 79))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0079_typed() -> None:
    """declared RIFF size -79: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -79))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0080_typed() -> None:
    """declared RIFF size +80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 80))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0080_typed() -> None:
    """declared RIFF size -80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -80))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0081_typed() -> None:
    """declared RIFF size +81: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 81))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0081_typed() -> None:
    """declared RIFF size -81: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -81))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0082_typed() -> None:
    """declared RIFF size +82: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 82))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0082_typed() -> None:
    """declared RIFF size -82: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -82))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0083_typed() -> None:
    """declared RIFF size +83: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 83))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0083_typed() -> None:
    """declared RIFF size -83: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -83))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0084_typed() -> None:
    """declared RIFF size +84: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 84))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0084_typed() -> None:
    """declared RIFF size -84: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -84))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0085_typed() -> None:
    """declared RIFF size +85: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 85))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0085_typed() -> None:
    """declared RIFF size -85: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -85))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0086_typed() -> None:
    """declared RIFF size +86: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 86))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0086_typed() -> None:
    """declared RIFF size -86: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -86))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0087_typed() -> None:
    """declared RIFF size +87: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 87))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0087_typed() -> None:
    """declared RIFF size -87: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -87))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0088_typed() -> None:
    """declared RIFF size +88: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 88))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0088_typed() -> None:
    """declared RIFF size -88: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -88))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0089_typed() -> None:
    """declared RIFF size +89: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 89))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0089_typed() -> None:
    """declared RIFF size -89: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -89))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0090_typed() -> None:
    """declared RIFF size +90: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 90))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0090_typed() -> None:
    """declared RIFF size -90: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -90))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0091_typed() -> None:
    """declared RIFF size +91: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 91))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0091_typed() -> None:
    """declared RIFF size -91: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -91))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0092_typed() -> None:
    """declared RIFF size +92: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 92))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0092_typed() -> None:
    """declared RIFF size -92: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -92))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0093_typed() -> None:
    """declared RIFF size +93: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 93))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0093_typed() -> None:
    """declared RIFF size -93: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -93))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0094_typed() -> None:
    """declared RIFF size +94: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 94))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0094_typed() -> None:
    """declared RIFF size -94: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -94))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0095_typed() -> None:
    """declared RIFF size +95: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 95))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0095_typed() -> None:
    """declared RIFF size -95: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -95))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0096_typed() -> None:
    """declared RIFF size +96: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 96))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0096_typed() -> None:
    """declared RIFF size -96: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -96))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0097_typed() -> None:
    """declared RIFF size +97: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 97))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0097_typed() -> None:
    """declared RIFF size -97: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -97))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0098_typed() -> None:
    """declared RIFF size +98: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 98))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0098_typed() -> None:
    """declared RIFF size -98: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -98))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0099_typed() -> None:
    """declared RIFF size +99: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 99))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0099_typed() -> None:
    """declared RIFF size -99: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -99))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0100_typed() -> None:
    """declared RIFF size +100: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 100))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0100_typed() -> None:
    """declared RIFF size -100: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -100))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0101_typed() -> None:
    """declared RIFF size +101: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 101))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0101_typed() -> None:
    """declared RIFF size -101: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -101))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0102_typed() -> None:
    """declared RIFF size +102: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 102))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0102_typed() -> None:
    """declared RIFF size -102: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -102))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0103_typed() -> None:
    """declared RIFF size +103: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 103))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0103_typed() -> None:
    """declared RIFF size -103: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -103))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0104_typed() -> None:
    """declared RIFF size +104: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 104))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0104_typed() -> None:
    """declared RIFF size -104: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -104))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0105_typed() -> None:
    """declared RIFF size +105: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 105))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0105_typed() -> None:
    """declared RIFF size -105: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -105))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0106_typed() -> None:
    """declared RIFF size +106: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 106))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0106_typed() -> None:
    """declared RIFF size -106: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -106))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0107_typed() -> None:
    """declared RIFF size +107: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 107))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0107_typed() -> None:
    """declared RIFF size -107: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -107))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0108_typed() -> None:
    """declared RIFF size +108: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 108))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0108_typed() -> None:
    """declared RIFF size -108: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -108))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0109_typed() -> None:
    """declared RIFF size +109: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 109))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0109_typed() -> None:
    """declared RIFF size -109: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -109))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0110_typed() -> None:
    """declared RIFF size +110: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 110))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0110_typed() -> None:
    """declared RIFF size -110: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -110))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0111_typed() -> None:
    """declared RIFF size +111: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 111))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0111_typed() -> None:
    """declared RIFF size -111: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -111))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0112_typed() -> None:
    """declared RIFF size +112: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 112))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0112_typed() -> None:
    """declared RIFF size -112: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -112))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0113_typed() -> None:
    """declared RIFF size +113: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 113))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0113_typed() -> None:
    """declared RIFF size -113: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -113))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0114_typed() -> None:
    """declared RIFF size +114: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 114))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0114_typed() -> None:
    """declared RIFF size -114: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -114))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0115_typed() -> None:
    """declared RIFF size +115: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 115))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0115_typed() -> None:
    """declared RIFF size -115: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -115))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0116_typed() -> None:
    """declared RIFF size +116: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 116))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0116_typed() -> None:
    """declared RIFF size -116: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -116))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0117_typed() -> None:
    """declared RIFF size +117: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 117))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0117_typed() -> None:
    """declared RIFF size -117: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -117))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0118_typed() -> None:
    """declared RIFF size +118: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 118))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0118_typed() -> None:
    """declared RIFF size -118: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -118))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0119_typed() -> None:
    """declared RIFF size +119: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 119))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0119_typed() -> None:
    """declared RIFF size -119: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -119))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0120_typed() -> None:
    """declared RIFF size +120: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 120))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0120_typed() -> None:
    """declared RIFF size -120: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -120))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0121_typed() -> None:
    """declared RIFF size +121: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 121))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0121_typed() -> None:
    """declared RIFF size -121: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -121))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0122_typed() -> None:
    """declared RIFF size +122: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 122))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0122_typed() -> None:
    """declared RIFF size -122: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -122))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0123_typed() -> None:
    """declared RIFF size +123: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 123))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0123_typed() -> None:
    """declared RIFF size -123: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -123))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0124_typed() -> None:
    """declared RIFF size +124: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 124))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0124_typed() -> None:
    """declared RIFF size -124: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -124))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0125_typed() -> None:
    """declared RIFF size +125: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 125))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0125_typed() -> None:
    """declared RIFF size -125: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -125))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0126_typed() -> None:
    """declared RIFF size +126: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 126))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0126_typed() -> None:
    """declared RIFF size -126: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -126))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0127_typed() -> None:
    """declared RIFF size +127: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 127))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0127_typed() -> None:
    """declared RIFF size -127: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -127))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0128_typed() -> None:
    """declared RIFF size +128: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 128))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0128_typed() -> None:
    """declared RIFF size -128: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -128))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0129_typed() -> None:
    """declared RIFF size +129: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 129))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0129_typed() -> None:
    """declared RIFF size -129: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -129))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0130_typed() -> None:
    """declared RIFF size +130: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 130))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0130_typed() -> None:
    """declared RIFF size -130: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -130))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0131_typed() -> None:
    """declared RIFF size +131: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 131))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0131_typed() -> None:
    """declared RIFF size -131: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -131))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0132_typed() -> None:
    """declared RIFF size +132: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 132))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0132_typed() -> None:
    """declared RIFF size -132: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -132))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0133_typed() -> None:
    """declared RIFF size +133: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 133))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0133_typed() -> None:
    """declared RIFF size -133: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -133))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0134_typed() -> None:
    """declared RIFF size +134: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 134))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0134_typed() -> None:
    """declared RIFF size -134: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -134))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0135_typed() -> None:
    """declared RIFF size +135: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 135))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0135_typed() -> None:
    """declared RIFF size -135: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -135))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0136_typed() -> None:
    """declared RIFF size +136: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 136))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0136_typed() -> None:
    """declared RIFF size -136: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -136))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0137_typed() -> None:
    """declared RIFF size +137: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 137))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0137_typed() -> None:
    """declared RIFF size -137: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -137))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0138_typed() -> None:
    """declared RIFF size +138: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 138))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0138_typed() -> None:
    """declared RIFF size -138: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -138))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0139_typed() -> None:
    """declared RIFF size +139: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 139))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0139_typed() -> None:
    """declared RIFF size -139: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -139))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0140_typed() -> None:
    """declared RIFF size +140: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 140))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0140_typed() -> None:
    """declared RIFF size -140: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -140))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0141_typed() -> None:
    """declared RIFF size +141: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 141))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0141_typed() -> None:
    """declared RIFF size -141: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -141))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0142_typed() -> None:
    """declared RIFF size +142: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 142))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0142_typed() -> None:
    """declared RIFF size -142: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -142))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0143_typed() -> None:
    """declared RIFF size +143: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 143))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0143_typed() -> None:
    """declared RIFF size -143: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -143))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0144_typed() -> None:
    """declared RIFF size +144: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 144))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0144_typed() -> None:
    """declared RIFF size -144: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -144))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0145_typed() -> None:
    """declared RIFF size +145: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 145))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0145_typed() -> None:
    """declared RIFF size -145: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -145))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0146_typed() -> None:
    """declared RIFF size +146: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 146))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0146_typed() -> None:
    """declared RIFF size -146: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -146))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0147_typed() -> None:
    """declared RIFF size +147: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 147))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0147_typed() -> None:
    """declared RIFF size -147: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -147))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0148_typed() -> None:
    """declared RIFF size +148: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 148))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0148_typed() -> None:
    """declared RIFF size -148: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -148))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0149_typed() -> None:
    """declared RIFF size +149: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 149))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0149_typed() -> None:
    """declared RIFF size -149: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -149))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0150_typed() -> None:
    """declared RIFF size +150: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 150))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0150_typed() -> None:
    """declared RIFF size -150: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -150))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0151_typed() -> None:
    """declared RIFF size +151: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 151))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0151_typed() -> None:
    """declared RIFF size -151: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -151))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0152_typed() -> None:
    """declared RIFF size +152: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 152))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0152_typed() -> None:
    """declared RIFF size -152: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -152))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0153_typed() -> None:
    """declared RIFF size +153: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 153))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0153_typed() -> None:
    """declared RIFF size -153: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -153))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0154_typed() -> None:
    """declared RIFF size +154: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 154))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0154_typed() -> None:
    """declared RIFF size -154: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -154))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0155_typed() -> None:
    """declared RIFF size +155: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 155))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0155_typed() -> None:
    """declared RIFF size -155: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -155))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0156_typed() -> None:
    """declared RIFF size +156: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 156))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0156_typed() -> None:
    """declared RIFF size -156: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -156))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0157_typed() -> None:
    """declared RIFF size +157: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 157))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0157_typed() -> None:
    """declared RIFF size -157: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -157))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0158_typed() -> None:
    """declared RIFF size +158: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 158))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0158_typed() -> None:
    """declared RIFF size -158: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -158))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0159_typed() -> None:
    """declared RIFF size +159: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 159))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0159_typed() -> None:
    """declared RIFF size -159: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -159))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0160_typed() -> None:
    """declared RIFF size +160: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 160))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0160_typed() -> None:
    """declared RIFF size -160: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -160))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0161_typed() -> None:
    """declared RIFF size +161: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 161))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0161_typed() -> None:
    """declared RIFF size -161: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -161))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0162_typed() -> None:
    """declared RIFF size +162: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 162))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0162_typed() -> None:
    """declared RIFF size -162: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -162))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0163_typed() -> None:
    """declared RIFF size +163: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 163))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0163_typed() -> None:
    """declared RIFF size -163: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -163))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0164_typed() -> None:
    """declared RIFF size +164: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 164))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0164_typed() -> None:
    """declared RIFF size -164: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -164))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0165_typed() -> None:
    """declared RIFF size +165: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 165))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0165_typed() -> None:
    """declared RIFF size -165: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -165))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0166_typed() -> None:
    """declared RIFF size +166: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 166))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0166_typed() -> None:
    """declared RIFF size -166: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -166))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0167_typed() -> None:
    """declared RIFF size +167: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 167))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0167_typed() -> None:
    """declared RIFF size -167: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -167))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0168_typed() -> None:
    """declared RIFF size +168: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 168))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0168_typed() -> None:
    """declared RIFF size -168: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -168))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0169_typed() -> None:
    """declared RIFF size +169: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 169))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0169_typed() -> None:
    """declared RIFF size -169: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -169))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0170_typed() -> None:
    """declared RIFF size +170: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 170))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0170_typed() -> None:
    """declared RIFF size -170: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -170))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0171_typed() -> None:
    """declared RIFF size +171: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 171))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0171_typed() -> None:
    """declared RIFF size -171: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -171))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0172_typed() -> None:
    """declared RIFF size +172: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 172))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0172_typed() -> None:
    """declared RIFF size -172: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -172))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0173_typed() -> None:
    """declared RIFF size +173: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 173))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0173_typed() -> None:
    """declared RIFF size -173: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -173))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0174_typed() -> None:
    """declared RIFF size +174: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 174))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0174_typed() -> None:
    """declared RIFF size -174: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -174))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0175_typed() -> None:
    """declared RIFF size +175: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 175))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0175_typed() -> None:
    """declared RIFF size -175: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -175))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0176_typed() -> None:
    """declared RIFF size +176: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 176))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0176_typed() -> None:
    """declared RIFF size -176: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -176))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0177_typed() -> None:
    """declared RIFF size +177: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 177))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0177_typed() -> None:
    """declared RIFF size -177: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -177))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0178_typed() -> None:
    """declared RIFF size +178: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 178))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0178_typed() -> None:
    """declared RIFF size -178: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -178))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0179_typed() -> None:
    """declared RIFF size +179: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 179))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0179_typed() -> None:
    """declared RIFF size -179: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -179))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0180_typed() -> None:
    """declared RIFF size +180: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 180))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0180_typed() -> None:
    """declared RIFF size -180: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -180))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0181_typed() -> None:
    """declared RIFF size +181: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 181))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0181_typed() -> None:
    """declared RIFF size -181: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -181))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0182_typed() -> None:
    """declared RIFF size +182: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 182))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0182_typed() -> None:
    """declared RIFF size -182: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -182))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0183_typed() -> None:
    """declared RIFF size +183: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 183))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0183_typed() -> None:
    """declared RIFF size -183: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -183))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0184_typed() -> None:
    """declared RIFF size +184: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 184))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0184_typed() -> None:
    """declared RIFF size -184: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -184))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0185_typed() -> None:
    """declared RIFF size +185: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 185))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0185_typed() -> None:
    """declared RIFF size -185: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -185))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0186_typed() -> None:
    """declared RIFF size +186: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 186))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0186_typed() -> None:
    """declared RIFF size -186: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -186))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0187_typed() -> None:
    """declared RIFF size +187: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 187))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0187_typed() -> None:
    """declared RIFF size -187: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -187))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0188_typed() -> None:
    """declared RIFF size +188: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 188))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0188_typed() -> None:
    """declared RIFF size -188: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -188))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0189_typed() -> None:
    """declared RIFF size +189: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 189))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0189_typed() -> None:
    """declared RIFF size -189: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -189))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0190_typed() -> None:
    """declared RIFF size +190: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 190))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0190_typed() -> None:
    """declared RIFF size -190: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -190))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0191_typed() -> None:
    """declared RIFF size +191: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 191))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0191_typed() -> None:
    """declared RIFF size -191: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -191))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0192_typed() -> None:
    """declared RIFF size +192: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 192))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0192_typed() -> None:
    """declared RIFF size -192: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -192))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0193_typed() -> None:
    """declared RIFF size +193: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 193))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0193_typed() -> None:
    """declared RIFF size -193: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -193))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0194_typed() -> None:
    """declared RIFF size +194: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 194))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0194_typed() -> None:
    """declared RIFF size -194: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -194))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0195_typed() -> None:
    """declared RIFF size +195: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 195))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0195_typed() -> None:
    """declared RIFF size -195: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -195))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0196_typed() -> None:
    """declared RIFF size +196: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 196))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0196_typed() -> None:
    """declared RIFF size -196: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -196))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0197_typed() -> None:
    """declared RIFF size +197: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 197))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0197_typed() -> None:
    """declared RIFF size -197: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -197))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0198_typed() -> None:
    """declared RIFF size +198: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 198))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0198_typed() -> None:
    """declared RIFF size -198: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -198))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0199_typed() -> None:
    """declared RIFF size +199: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 199))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0199_typed() -> None:
    """declared RIFF size -199: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -199))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0200_typed() -> None:
    """declared RIFF size +200: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 200))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0200_typed() -> None:
    """declared RIFF size -200: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -200))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0201_typed() -> None:
    """declared RIFF size +201: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 201))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0201_typed() -> None:
    """declared RIFF size -201: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -201))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0202_typed() -> None:
    """declared RIFF size +202: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 202))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0202_typed() -> None:
    """declared RIFF size -202: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -202))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0203_typed() -> None:
    """declared RIFF size +203: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 203))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0203_typed() -> None:
    """declared RIFF size -203: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -203))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0204_typed() -> None:
    """declared RIFF size +204: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 204))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0204_typed() -> None:
    """declared RIFF size -204: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -204))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0205_typed() -> None:
    """declared RIFF size +205: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 205))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0205_typed() -> None:
    """declared RIFF size -205: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -205))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0206_typed() -> None:
    """declared RIFF size +206: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 206))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0206_typed() -> None:
    """declared RIFF size -206: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -206))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0207_typed() -> None:
    """declared RIFF size +207: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 207))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0207_typed() -> None:
    """declared RIFF size -207: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -207))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0208_typed() -> None:
    """declared RIFF size +208: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 208))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0208_typed() -> None:
    """declared RIFF size -208: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -208))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0209_typed() -> None:
    """declared RIFF size +209: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 209))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0209_typed() -> None:
    """declared RIFF size -209: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -209))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0210_typed() -> None:
    """declared RIFF size +210: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 210))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0210_typed() -> None:
    """declared RIFF size -210: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -210))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0211_typed() -> None:
    """declared RIFF size +211: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 211))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0211_typed() -> None:
    """declared RIFF size -211: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -211))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0212_typed() -> None:
    """declared RIFF size +212: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 212))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0212_typed() -> None:
    """declared RIFF size -212: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -212))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0213_typed() -> None:
    """declared RIFF size +213: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 213))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0213_typed() -> None:
    """declared RIFF size -213: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -213))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0214_typed() -> None:
    """declared RIFF size +214: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 214))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0214_typed() -> None:
    """declared RIFF size -214: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -214))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0215_typed() -> None:
    """declared RIFF size +215: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 215))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0215_typed() -> None:
    """declared RIFF size -215: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -215))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0216_typed() -> None:
    """declared RIFF size +216: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 216))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0216_typed() -> None:
    """declared RIFF size -216: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -216))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0217_typed() -> None:
    """declared RIFF size +217: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 217))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0217_typed() -> None:
    """declared RIFF size -217: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -217))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0218_typed() -> None:
    """declared RIFF size +218: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 218))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0218_typed() -> None:
    """declared RIFF size -218: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -218))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0219_typed() -> None:
    """declared RIFF size +219: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 219))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0219_typed() -> None:
    """declared RIFF size -219: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -219))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0220_typed() -> None:
    """declared RIFF size +220: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 220))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0220_typed() -> None:
    """declared RIFF size -220: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -220))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0221_typed() -> None:
    """declared RIFF size +221: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 221))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0221_typed() -> None:
    """declared RIFF size -221: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -221))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0222_typed() -> None:
    """declared RIFF size +222: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 222))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0222_typed() -> None:
    """declared RIFF size -222: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -222))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0223_typed() -> None:
    """declared RIFF size +223: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 223))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0223_typed() -> None:
    """declared RIFF size -223: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -223))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0224_typed() -> None:
    """declared RIFF size +224: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 224))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0224_typed() -> None:
    """declared RIFF size -224: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -224))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0225_typed() -> None:
    """declared RIFF size +225: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 225))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0225_typed() -> None:
    """declared RIFF size -225: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -225))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0226_typed() -> None:
    """declared RIFF size +226: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 226))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0226_typed() -> None:
    """declared RIFF size -226: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -226))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0227_typed() -> None:
    """declared RIFF size +227: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 227))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0227_typed() -> None:
    """declared RIFF size -227: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -227))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0228_typed() -> None:
    """declared RIFF size +228: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 228))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0228_typed() -> None:
    """declared RIFF size -228: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -228))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0229_typed() -> None:
    """declared RIFF size +229: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 229))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0229_typed() -> None:
    """declared RIFF size -229: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -229))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0230_typed() -> None:
    """declared RIFF size +230: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 230))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0230_typed() -> None:
    """declared RIFF size -230: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -230))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0231_typed() -> None:
    """declared RIFF size +231: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 231))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0231_typed() -> None:
    """declared RIFF size -231: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -231))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0232_typed() -> None:
    """declared RIFF size +232: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 232))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0232_typed() -> None:
    """declared RIFF size -232: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -232))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0233_typed() -> None:
    """declared RIFF size +233: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 233))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0233_typed() -> None:
    """declared RIFF size -233: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -233))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0234_typed() -> None:
    """declared RIFF size +234: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 234))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0234_typed() -> None:
    """declared RIFF size -234: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -234))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0235_typed() -> None:
    """declared RIFF size +235: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 235))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0235_typed() -> None:
    """declared RIFF size -235: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -235))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0236_typed() -> None:
    """declared RIFF size +236: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 236))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0236_typed() -> None:
    """declared RIFF size -236: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -236))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0237_typed() -> None:
    """declared RIFF size +237: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 237))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0237_typed() -> None:
    """declared RIFF size -237: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -237))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0238_typed() -> None:
    """declared RIFF size +238: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 238))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0238_typed() -> None:
    """declared RIFF size -238: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -238))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0239_typed() -> None:
    """declared RIFF size +239: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 239))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0239_typed() -> None:
    """declared RIFF size -239: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -239))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0240_typed() -> None:
    """declared RIFF size +240: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 240))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0240_typed() -> None:
    """declared RIFF size -240: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -240))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0241_typed() -> None:
    """declared RIFF size +241: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 241))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0241_typed() -> None:
    """declared RIFF size -241: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -241))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0242_typed() -> None:
    """declared RIFF size +242: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 242))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0242_typed() -> None:
    """declared RIFF size -242: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -242))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0243_typed() -> None:
    """declared RIFF size +243: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 243))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0243_typed() -> None:
    """declared RIFF size -243: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -243))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0244_typed() -> None:
    """declared RIFF size +244: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 244))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0244_typed() -> None:
    """declared RIFF size -244: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -244))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0245_typed() -> None:
    """declared RIFF size +245: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 245))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0245_typed() -> None:
    """declared RIFF size -245: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -245))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0246_typed() -> None:
    """declared RIFF size +246: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 246))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0246_typed() -> None:
    """declared RIFF size -246: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -246))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0247_typed() -> None:
    """declared RIFF size +247: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 247))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0247_typed() -> None:
    """declared RIFF size -247: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -247))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0248_typed() -> None:
    """declared RIFF size +248: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 248))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0248_typed() -> None:
    """declared RIFF size -248: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -248))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0249_typed() -> None:
    """declared RIFF size +249: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 249))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0249_typed() -> None:
    """declared RIFF size -249: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -249))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0250_typed() -> None:
    """declared RIFF size +250: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 250))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0250_typed() -> None:
    """declared RIFF size -250: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -250))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0251_typed() -> None:
    """declared RIFF size +251: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 251))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0251_typed() -> None:
    """declared RIFF size -251: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -251))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0252_typed() -> None:
    """declared RIFF size +252: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 252))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0252_typed() -> None:
    """declared RIFF size -252: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -252))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0253_typed() -> None:
    """declared RIFF size +253: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 253))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0253_typed() -> None:
    """declared RIFF size -253: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -253))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0254_typed() -> None:
    """declared RIFF size +254: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 254))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0254_typed() -> None:
    """declared RIFF size -254: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -254))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0255_typed() -> None:
    """declared RIFF size +255: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 255))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0255_typed() -> None:
    """declared RIFF size -255: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -255))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0256_typed() -> None:
    """declared RIFF size +256: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 256))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0256_typed() -> None:
    """declared RIFF size -256: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -256))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0257_typed() -> None:
    """declared RIFF size +257: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 257))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0257_typed() -> None:
    """declared RIFF size -257: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -257))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0258_typed() -> None:
    """declared RIFF size +258: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 258))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0258_typed() -> None:
    """declared RIFF size -258: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -258))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0259_typed() -> None:
    """declared RIFF size +259: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 259))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0259_typed() -> None:
    """declared RIFF size -259: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -259))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0260_typed() -> None:
    """declared RIFF size +260: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 260))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0260_typed() -> None:
    """declared RIFF size -260: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -260))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0261_typed() -> None:
    """declared RIFF size +261: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 261))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0261_typed() -> None:
    """declared RIFF size -261: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -261))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0262_typed() -> None:
    """declared RIFF size +262: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 262))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0262_typed() -> None:
    """declared RIFF size -262: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -262))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0263_typed() -> None:
    """declared RIFF size +263: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 263))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0263_typed() -> None:
    """declared RIFF size -263: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -263))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0264_typed() -> None:
    """declared RIFF size +264: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 264))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0264_typed() -> None:
    """declared RIFF size -264: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -264))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0265_typed() -> None:
    """declared RIFF size +265: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 265))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0265_typed() -> None:
    """declared RIFF size -265: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -265))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0266_typed() -> None:
    """declared RIFF size +266: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 266))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0266_typed() -> None:
    """declared RIFF size -266: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -266))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0267_typed() -> None:
    """declared RIFF size +267: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 267))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0267_typed() -> None:
    """declared RIFF size -267: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -267))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0268_typed() -> None:
    """declared RIFF size +268: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 268))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0268_typed() -> None:
    """declared RIFF size -268: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -268))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0269_typed() -> None:
    """declared RIFF size +269: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 269))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0269_typed() -> None:
    """declared RIFF size -269: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -269))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0270_typed() -> None:
    """declared RIFF size +270: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 270))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0270_typed() -> None:
    """declared RIFF size -270: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -270))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0271_typed() -> None:
    """declared RIFF size +271: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 271))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0271_typed() -> None:
    """declared RIFF size -271: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -271))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0272_typed() -> None:
    """declared RIFF size +272: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 272))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0272_typed() -> None:
    """declared RIFF size -272: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -272))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0273_typed() -> None:
    """declared RIFF size +273: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 273))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0273_typed() -> None:
    """declared RIFF size -273: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -273))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0274_typed() -> None:
    """declared RIFF size +274: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 274))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0274_typed() -> None:
    """declared RIFF size -274: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -274))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0275_typed() -> None:
    """declared RIFF size +275: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 275))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0275_typed() -> None:
    """declared RIFF size -275: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -275))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0276_typed() -> None:
    """declared RIFF size +276: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 276))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0276_typed() -> None:
    """declared RIFF size -276: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -276))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0277_typed() -> None:
    """declared RIFF size +277: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 277))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0277_typed() -> None:
    """declared RIFF size -277: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -277))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0278_typed() -> None:
    """declared RIFF size +278: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 278))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0278_typed() -> None:
    """declared RIFF size -278: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -278))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0279_typed() -> None:
    """declared RIFF size +279: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 279))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0279_typed() -> None:
    """declared RIFF size -279: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -279))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0280_typed() -> None:
    """declared RIFF size +280: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 280))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0280_typed() -> None:
    """declared RIFF size -280: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -280))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0281_typed() -> None:
    """declared RIFF size +281: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 281))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0281_typed() -> None:
    """declared RIFF size -281: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -281))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0282_typed() -> None:
    """declared RIFF size +282: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 282))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0282_typed() -> None:
    """declared RIFF size -282: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -282))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0283_typed() -> None:
    """declared RIFF size +283: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 283))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0283_typed() -> None:
    """declared RIFF size -283: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -283))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0284_typed() -> None:
    """declared RIFF size +284: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 284))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0284_typed() -> None:
    """declared RIFF size -284: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -284))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0285_typed() -> None:
    """declared RIFF size +285: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 285))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0285_typed() -> None:
    """declared RIFF size -285: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -285))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0286_typed() -> None:
    """declared RIFF size +286: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 286))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0286_typed() -> None:
    """declared RIFF size -286: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -286))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0287_typed() -> None:
    """declared RIFF size +287: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 287))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0287_typed() -> None:
    """declared RIFF size -287: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -287))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0288_typed() -> None:
    """declared RIFF size +288: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 288))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0288_typed() -> None:
    """declared RIFF size -288: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -288))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0289_typed() -> None:
    """declared RIFF size +289: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 289))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0289_typed() -> None:
    """declared RIFF size -289: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -289))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0290_typed() -> None:
    """declared RIFF size +290: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 290))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0290_typed() -> None:
    """declared RIFF size -290: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -290))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0291_typed() -> None:
    """declared RIFF size +291: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 291))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0291_typed() -> None:
    """declared RIFF size -291: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -291))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0292_typed() -> None:
    """declared RIFF size +292: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 292))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0292_typed() -> None:
    """declared RIFF size -292: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -292))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0293_typed() -> None:
    """declared RIFF size +293: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 293))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0293_typed() -> None:
    """declared RIFF size -293: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -293))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0294_typed() -> None:
    """declared RIFF size +294: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 294))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0294_typed() -> None:
    """declared RIFF size -294: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -294))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0295_typed() -> None:
    """declared RIFF size +295: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 295))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0295_typed() -> None:
    """declared RIFF size -295: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -295))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0296_typed() -> None:
    """declared RIFF size +296: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 296))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0296_typed() -> None:
    """declared RIFF size -296: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -296))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0297_typed() -> None:
    """declared RIFF size +297: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 297))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0297_typed() -> None:
    """declared RIFF size -297: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -297))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0298_typed() -> None:
    """declared RIFF size +298: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 298))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0298_typed() -> None:
    """declared RIFF size -298: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -298))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0299_typed() -> None:
    """declared RIFF size +299: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 299))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0299_typed() -> None:
    """declared RIFF size -299: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -299))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0300_typed() -> None:
    """declared RIFF size +300: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 300))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0300_typed() -> None:
    """declared RIFF size -300: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -300))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0301_typed() -> None:
    """declared RIFF size +301: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 301))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0301_typed() -> None:
    """declared RIFF size -301: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -301))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0302_typed() -> None:
    """declared RIFF size +302: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 302))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0302_typed() -> None:
    """declared RIFF size -302: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -302))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0303_typed() -> None:
    """declared RIFF size +303: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 303))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0303_typed() -> None:
    """declared RIFF size -303: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -303))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0304_typed() -> None:
    """declared RIFF size +304: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 304))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0304_typed() -> None:
    """declared RIFF size -304: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -304))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0305_typed() -> None:
    """declared RIFF size +305: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 305))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0305_typed() -> None:
    """declared RIFF size -305: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -305))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0306_typed() -> None:
    """declared RIFF size +306: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 306))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0306_typed() -> None:
    """declared RIFF size -306: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -306))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0307_typed() -> None:
    """declared RIFF size +307: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 307))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0307_typed() -> None:
    """declared RIFF size -307: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -307))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0308_typed() -> None:
    """declared RIFF size +308: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 308))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0308_typed() -> None:
    """declared RIFF size -308: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -308))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0309_typed() -> None:
    """declared RIFF size +309: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 309))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0309_typed() -> None:
    """declared RIFF size -309: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -309))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0310_typed() -> None:
    """declared RIFF size +310: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 310))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0310_typed() -> None:
    """declared RIFF size -310: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -310))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0311_typed() -> None:
    """declared RIFF size +311: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 311))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0311_typed() -> None:
    """declared RIFF size -311: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -311))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0312_typed() -> None:
    """declared RIFF size +312: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 312))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0312_typed() -> None:
    """declared RIFF size -312: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -312))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0313_typed() -> None:
    """declared RIFF size +313: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 313))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0313_typed() -> None:
    """declared RIFF size -313: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -313))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0314_typed() -> None:
    """declared RIFF size +314: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 314))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0314_typed() -> None:
    """declared RIFF size -314: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -314))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0315_typed() -> None:
    """declared RIFF size +315: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 315))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0315_typed() -> None:
    """declared RIFF size -315: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -315))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0316_typed() -> None:
    """declared RIFF size +316: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 316))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0316_typed() -> None:
    """declared RIFF size -316: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -316))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0317_typed() -> None:
    """declared RIFF size +317: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 317))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0317_typed() -> None:
    """declared RIFF size -317: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -317))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0318_typed() -> None:
    """declared RIFF size +318: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 318))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0318_typed() -> None:
    """declared RIFF size -318: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -318))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0319_typed() -> None:
    """declared RIFF size +319: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 319))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0319_typed() -> None:
    """declared RIFF size -319: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -319))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0320_typed() -> None:
    """declared RIFF size +320: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 320))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0320_typed() -> None:
    """declared RIFF size -320: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -320))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0321_typed() -> None:
    """declared RIFF size +321: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 321))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0321_typed() -> None:
    """declared RIFF size -321: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -321))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0322_typed() -> None:
    """declared RIFF size +322: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 322))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0322_typed() -> None:
    """declared RIFF size -322: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -322))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0323_typed() -> None:
    """declared RIFF size +323: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 323))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0323_typed() -> None:
    """declared RIFF size -323: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -323))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0324_typed() -> None:
    """declared RIFF size +324: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 324))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0324_typed() -> None:
    """declared RIFF size -324: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -324))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0325_typed() -> None:
    """declared RIFF size +325: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 325))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0325_typed() -> None:
    """declared RIFF size -325: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -325))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0326_typed() -> None:
    """declared RIFF size +326: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 326))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0326_typed() -> None:
    """declared RIFF size -326: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -326))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0327_typed() -> None:
    """declared RIFF size +327: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 327))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0327_typed() -> None:
    """declared RIFF size -327: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -327))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0328_typed() -> None:
    """declared RIFF size +328: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 328))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0328_typed() -> None:
    """declared RIFF size -328: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -328))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0329_typed() -> None:
    """declared RIFF size +329: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 329))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0329_typed() -> None:
    """declared RIFF size -329: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -329))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0330_typed() -> None:
    """declared RIFF size +330: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 330))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0330_typed() -> None:
    """declared RIFF size -330: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -330))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0331_typed() -> None:
    """declared RIFF size +331: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 331))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0331_typed() -> None:
    """declared RIFF size -331: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -331))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0332_typed() -> None:
    """declared RIFF size +332: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 332))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0332_typed() -> None:
    """declared RIFF size -332: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -332))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0333_typed() -> None:
    """declared RIFF size +333: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 333))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0333_typed() -> None:
    """declared RIFF size -333: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -333))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0334_typed() -> None:
    """declared RIFF size +334: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 334))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0334_typed() -> None:
    """declared RIFF size -334: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -334))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0335_typed() -> None:
    """declared RIFF size +335: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 335))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0335_typed() -> None:
    """declared RIFF size -335: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -335))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0336_typed() -> None:
    """declared RIFF size +336: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 336))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0336_typed() -> None:
    """declared RIFF size -336: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -336))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0337_typed() -> None:
    """declared RIFF size +337: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 337))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0337_typed() -> None:
    """declared RIFF size -337: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -337))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0338_typed() -> None:
    """declared RIFF size +338: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 338))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0338_typed() -> None:
    """declared RIFF size -338: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -338))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0339_typed() -> None:
    """declared RIFF size +339: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 339))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0339_typed() -> None:
    """declared RIFF size -339: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -339))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0340_typed() -> None:
    """declared RIFF size +340: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 340))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0340_typed() -> None:
    """declared RIFF size -340: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -340))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0341_typed() -> None:
    """declared RIFF size +341: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 341))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0341_typed() -> None:
    """declared RIFF size -341: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -341))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0342_typed() -> None:
    """declared RIFF size +342: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 342))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0342_typed() -> None:
    """declared RIFF size -342: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -342))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0343_typed() -> None:
    """declared RIFF size +343: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 343))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0343_typed() -> None:
    """declared RIFF size -343: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -343))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0344_typed() -> None:
    """declared RIFF size +344: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 344))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0344_typed() -> None:
    """declared RIFF size -344: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -344))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0345_typed() -> None:
    """declared RIFF size +345: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 345))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0345_typed() -> None:
    """declared RIFF size -345: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -345))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0346_typed() -> None:
    """declared RIFF size +346: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 346))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0346_typed() -> None:
    """declared RIFF size -346: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -346))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0347_typed() -> None:
    """declared RIFF size +347: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 347))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0347_typed() -> None:
    """declared RIFF size -347: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -347))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0348_typed() -> None:
    """declared RIFF size +348: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 348))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0348_typed() -> None:
    """declared RIFF size -348: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -348))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0349_typed() -> None:
    """declared RIFF size +349: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 349))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0349_typed() -> None:
    """declared RIFF size -349: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -349))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0350_typed() -> None:
    """declared RIFF size +350: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 350))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0350_typed() -> None:
    """declared RIFF size -350: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -350))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0351_typed() -> None:
    """declared RIFF size +351: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 351))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0351_typed() -> None:
    """declared RIFF size -351: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -351))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0352_typed() -> None:
    """declared RIFF size +352: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 352))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0352_typed() -> None:
    """declared RIFF size -352: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -352))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0353_typed() -> None:
    """declared RIFF size +353: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 353))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0353_typed() -> None:
    """declared RIFF size -353: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -353))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0354_typed() -> None:
    """declared RIFF size +354: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 354))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0354_typed() -> None:
    """declared RIFF size -354: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -354))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0355_typed() -> None:
    """declared RIFF size +355: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 355))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0355_typed() -> None:
    """declared RIFF size -355: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -355))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0356_typed() -> None:
    """declared RIFF size +356: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 356))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0356_typed() -> None:
    """declared RIFF size -356: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -356))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0357_typed() -> None:
    """declared RIFF size +357: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 357))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0357_typed() -> None:
    """declared RIFF size -357: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -357))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0358_typed() -> None:
    """declared RIFF size +358: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 358))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0358_typed() -> None:
    """declared RIFF size -358: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -358))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0359_typed() -> None:
    """declared RIFF size +359: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 359))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0359_typed() -> None:
    """declared RIFF size -359: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -359))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0360_typed() -> None:
    """declared RIFF size +360: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 360))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0360_typed() -> None:
    """declared RIFF size -360: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -360))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0361_typed() -> None:
    """declared RIFF size +361: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 361))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0361_typed() -> None:
    """declared RIFF size -361: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -361))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0362_typed() -> None:
    """declared RIFF size +362: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 362))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0362_typed() -> None:
    """declared RIFF size -362: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -362))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0363_typed() -> None:
    """declared RIFF size +363: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 363))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0363_typed() -> None:
    """declared RIFF size -363: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -363))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0364_typed() -> None:
    """declared RIFF size +364: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 364))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0364_typed() -> None:
    """declared RIFF size -364: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -364))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0365_typed() -> None:
    """declared RIFF size +365: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 365))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0365_typed() -> None:
    """declared RIFF size -365: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -365))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0366_typed() -> None:
    """declared RIFF size +366: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 366))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0366_typed() -> None:
    """declared RIFF size -366: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -366))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0367_typed() -> None:
    """declared RIFF size +367: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 367))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0367_typed() -> None:
    """declared RIFF size -367: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -367))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0368_typed() -> None:
    """declared RIFF size +368: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 368))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0368_typed() -> None:
    """declared RIFF size -368: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -368))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0369_typed() -> None:
    """declared RIFF size +369: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 369))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0369_typed() -> None:
    """declared RIFF size -369: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -369))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0370_typed() -> None:
    """declared RIFF size +370: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 370))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0370_typed() -> None:
    """declared RIFF size -370: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -370))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0371_typed() -> None:
    """declared RIFF size +371: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 371))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0371_typed() -> None:
    """declared RIFF size -371: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -371))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0372_typed() -> None:
    """declared RIFF size +372: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 372))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0372_typed() -> None:
    """declared RIFF size -372: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -372))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0373_typed() -> None:
    """declared RIFF size +373: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 373))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0373_typed() -> None:
    """declared RIFF size -373: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -373))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0374_typed() -> None:
    """declared RIFF size +374: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 374))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0374_typed() -> None:
    """declared RIFF size -374: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -374))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0375_typed() -> None:
    """declared RIFF size +375: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 375))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0375_typed() -> None:
    """declared RIFF size -375: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -375))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0376_typed() -> None:
    """declared RIFF size +376: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 376))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0376_typed() -> None:
    """declared RIFF size -376: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -376))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0377_typed() -> None:
    """declared RIFF size +377: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 377))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0377_typed() -> None:
    """declared RIFF size -377: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -377))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0378_typed() -> None:
    """declared RIFF size +378: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 378))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0378_typed() -> None:
    """declared RIFF size -378: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -378))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0379_typed() -> None:
    """declared RIFF size +379: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 379))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0379_typed() -> None:
    """declared RIFF size -379: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -379))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0380_typed() -> None:
    """declared RIFF size +380: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 380))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0380_typed() -> None:
    """declared RIFF size -380: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -380))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0381_typed() -> None:
    """declared RIFF size +381: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 381))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0381_typed() -> None:
    """declared RIFF size -381: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -381))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0382_typed() -> None:
    """declared RIFF size +382: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 382))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0382_typed() -> None:
    """declared RIFF size -382: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -382))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0383_typed() -> None:
    """declared RIFF size +383: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 383))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0383_typed() -> None:
    """declared RIFF size -383: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -383))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0384_typed() -> None:
    """declared RIFF size +384: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 384))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0384_typed() -> None:
    """declared RIFF size -384: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -384))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0385_typed() -> None:
    """declared RIFF size +385: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 385))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0385_typed() -> None:
    """declared RIFF size -385: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -385))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0386_typed() -> None:
    """declared RIFF size +386: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 386))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0386_typed() -> None:
    """declared RIFF size -386: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -386))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0387_typed() -> None:
    """declared RIFF size +387: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 387))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0387_typed() -> None:
    """declared RIFF size -387: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -387))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0388_typed() -> None:
    """declared RIFF size +388: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 388))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0388_typed() -> None:
    """declared RIFF size -388: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -388))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0389_typed() -> None:
    """declared RIFF size +389: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 389))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0389_typed() -> None:
    """declared RIFF size -389: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -389))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0390_typed() -> None:
    """declared RIFF size +390: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 390))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0390_typed() -> None:
    """declared RIFF size -390: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -390))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0391_typed() -> None:
    """declared RIFF size +391: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 391))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0391_typed() -> None:
    """declared RIFF size -391: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -391))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0392_typed() -> None:
    """declared RIFF size +392: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 392))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0392_typed() -> None:
    """declared RIFF size -392: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -392))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0393_typed() -> None:
    """declared RIFF size +393: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 393))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0393_typed() -> None:
    """declared RIFF size -393: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -393))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0394_typed() -> None:
    """declared RIFF size +394: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 394))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0394_typed() -> None:
    """declared RIFF size -394: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -394))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0395_typed() -> None:
    """declared RIFF size +395: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 395))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0395_typed() -> None:
    """declared RIFF size -395: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -395))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0396_typed() -> None:
    """declared RIFF size +396: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 396))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0396_typed() -> None:
    """declared RIFF size -396: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -396))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0397_typed() -> None:
    """declared RIFF size +397: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 397))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0397_typed() -> None:
    """declared RIFF size -397: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -397))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0398_typed() -> None:
    """declared RIFF size +398: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 398))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0398_typed() -> None:
    """declared RIFF size -398: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -398))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0399_typed() -> None:
    """declared RIFF size +399: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 399))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0399_typed() -> None:
    """declared RIFF size -399: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -399))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0400_typed() -> None:
    """declared RIFF size +400: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 400))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0400_typed() -> None:
    """declared RIFF size -400: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -400))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0401_typed() -> None:
    """declared RIFF size +401: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 401))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0401_typed() -> None:
    """declared RIFF size -401: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -401))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0402_typed() -> None:
    """declared RIFF size +402: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 402))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0402_typed() -> None:
    """declared RIFF size -402: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -402))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0403_typed() -> None:
    """declared RIFF size +403: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 403))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0403_typed() -> None:
    """declared RIFF size -403: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -403))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0404_typed() -> None:
    """declared RIFF size +404: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 404))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0404_typed() -> None:
    """declared RIFF size -404: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -404))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0405_typed() -> None:
    """declared RIFF size +405: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 405))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0405_typed() -> None:
    """declared RIFF size -405: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -405))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0406_typed() -> None:
    """declared RIFF size +406: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 406))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0406_typed() -> None:
    """declared RIFF size -406: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -406))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0407_typed() -> None:
    """declared RIFF size +407: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 407))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0407_typed() -> None:
    """declared RIFF size -407: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -407))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0408_typed() -> None:
    """declared RIFF size +408: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 408))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0408_typed() -> None:
    """declared RIFF size -408: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -408))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0409_typed() -> None:
    """declared RIFF size +409: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 409))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0409_typed() -> None:
    """declared RIFF size -409: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -409))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0410_typed() -> None:
    """declared RIFF size +410: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 410))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0410_typed() -> None:
    """declared RIFF size -410: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -410))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0411_typed() -> None:
    """declared RIFF size +411: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 411))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0411_typed() -> None:
    """declared RIFF size -411: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -411))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0412_typed() -> None:
    """declared RIFF size +412: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 412))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0412_typed() -> None:
    """declared RIFF size -412: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -412))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0413_typed() -> None:
    """declared RIFF size +413: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 413))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0413_typed() -> None:
    """declared RIFF size -413: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -413))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0414_typed() -> None:
    """declared RIFF size +414: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 414))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0414_typed() -> None:
    """declared RIFF size -414: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -414))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0415_typed() -> None:
    """declared RIFF size +415: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 415))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0415_typed() -> None:
    """declared RIFF size -415: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -415))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0416_typed() -> None:
    """declared RIFF size +416: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 416))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0416_typed() -> None:
    """declared RIFF size -416: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -416))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0417_typed() -> None:
    """declared RIFF size +417: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 417))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0417_typed() -> None:
    """declared RIFF size -417: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -417))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0418_typed() -> None:
    """declared RIFF size +418: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 418))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0418_typed() -> None:
    """declared RIFF size -418: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -418))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0419_typed() -> None:
    """declared RIFF size +419: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 419))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0419_typed() -> None:
    """declared RIFF size -419: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -419))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0420_typed() -> None:
    """declared RIFF size +420: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 420))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0420_typed() -> None:
    """declared RIFF size -420: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -420))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0421_typed() -> None:
    """declared RIFF size +421: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 421))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0421_typed() -> None:
    """declared RIFF size -421: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -421))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0422_typed() -> None:
    """declared RIFF size +422: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 422))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0422_typed() -> None:
    """declared RIFF size -422: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -422))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0423_typed() -> None:
    """declared RIFF size +423: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 423))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0423_typed() -> None:
    """declared RIFF size -423: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -423))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0424_typed() -> None:
    """declared RIFF size +424: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 424))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0424_typed() -> None:
    """declared RIFF size -424: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -424))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0425_typed() -> None:
    """declared RIFF size +425: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 425))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0425_typed() -> None:
    """declared RIFF size -425: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -425))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0426_typed() -> None:
    """declared RIFF size +426: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 426))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0426_typed() -> None:
    """declared RIFF size -426: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -426))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0427_typed() -> None:
    """declared RIFF size +427: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 427))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0427_typed() -> None:
    """declared RIFF size -427: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -427))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0428_typed() -> None:
    """declared RIFF size +428: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 428))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0428_typed() -> None:
    """declared RIFF size -428: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -428))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0429_typed() -> None:
    """declared RIFF size +429: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 429))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0429_typed() -> None:
    """declared RIFF size -429: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -429))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0430_typed() -> None:
    """declared RIFF size +430: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 430))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0430_typed() -> None:
    """declared RIFF size -430: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -430))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0431_typed() -> None:
    """declared RIFF size +431: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 431))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0431_typed() -> None:
    """declared RIFF size -431: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -431))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0432_typed() -> None:
    """declared RIFF size +432: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 432))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0432_typed() -> None:
    """declared RIFF size -432: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -432))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0433_typed() -> None:
    """declared RIFF size +433: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 433))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0433_typed() -> None:
    """declared RIFF size -433: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -433))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0434_typed() -> None:
    """declared RIFF size +434: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 434))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0434_typed() -> None:
    """declared RIFF size -434: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -434))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0435_typed() -> None:
    """declared RIFF size +435: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 435))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0435_typed() -> None:
    """declared RIFF size -435: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -435))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0436_typed() -> None:
    """declared RIFF size +436: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 436))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0436_typed() -> None:
    """declared RIFF size -436: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -436))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0437_typed() -> None:
    """declared RIFF size +437: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 437))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0437_typed() -> None:
    """declared RIFF size -437: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -437))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0438_typed() -> None:
    """declared RIFF size +438: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 438))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0438_typed() -> None:
    """declared RIFF size -438: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -438))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0439_typed() -> None:
    """declared RIFF size +439: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 439))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0439_typed() -> None:
    """declared RIFF size -439: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -439))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0440_typed() -> None:
    """declared RIFF size +440: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 440))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0440_typed() -> None:
    """declared RIFF size -440: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -440))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0441_typed() -> None:
    """declared RIFF size +441: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 441))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0441_typed() -> None:
    """declared RIFF size -441: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -441))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0442_typed() -> None:
    """declared RIFF size +442: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 442))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0442_typed() -> None:
    """declared RIFF size -442: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -442))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0443_typed() -> None:
    """declared RIFF size +443: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 443))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0443_typed() -> None:
    """declared RIFF size -443: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -443))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0444_typed() -> None:
    """declared RIFF size +444: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 444))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0444_typed() -> None:
    """declared RIFF size -444: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -444))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0445_typed() -> None:
    """declared RIFF size +445: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 445))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0445_typed() -> None:
    """declared RIFF size -445: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -445))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0446_typed() -> None:
    """declared RIFF size +446: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 446))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0446_typed() -> None:
    """declared RIFF size -446: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -446))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0447_typed() -> None:
    """declared RIFF size +447: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 447))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0447_typed() -> None:
    """declared RIFF size -447: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -447))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0448_typed() -> None:
    """declared RIFF size +448: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 448))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0448_typed() -> None:
    """declared RIFF size -448: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -448))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0449_typed() -> None:
    """declared RIFF size +449: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 449))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0449_typed() -> None:
    """declared RIFF size -449: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -449))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0450_typed() -> None:
    """declared RIFF size +450: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 450))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0450_typed() -> None:
    """declared RIFF size -450: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -450))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0451_typed() -> None:
    """declared RIFF size +451: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 451))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0451_typed() -> None:
    """declared RIFF size -451: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -451))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0452_typed() -> None:
    """declared RIFF size +452: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 452))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0452_typed() -> None:
    """declared RIFF size -452: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -452))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0453_typed() -> None:
    """declared RIFF size +453: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 453))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0453_typed() -> None:
    """declared RIFF size -453: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -453))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0454_typed() -> None:
    """declared RIFF size +454: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 454))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0454_typed() -> None:
    """declared RIFF size -454: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -454))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0455_typed() -> None:
    """declared RIFF size +455: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 455))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0455_typed() -> None:
    """declared RIFF size -455: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -455))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0456_typed() -> None:
    """declared RIFF size +456: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 456))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0456_typed() -> None:
    """declared RIFF size -456: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -456))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0457_typed() -> None:
    """declared RIFF size +457: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 457))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0457_typed() -> None:
    """declared RIFF size -457: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -457))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0458_typed() -> None:
    """declared RIFF size +458: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 458))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0458_typed() -> None:
    """declared RIFF size -458: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -458))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0459_typed() -> None:
    """declared RIFF size +459: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 459))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0459_typed() -> None:
    """declared RIFF size -459: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -459))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0460_typed() -> None:
    """declared RIFF size +460: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 460))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0460_typed() -> None:
    """declared RIFF size -460: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -460))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0461_typed() -> None:
    """declared RIFF size +461: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 461))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0461_typed() -> None:
    """declared RIFF size -461: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -461))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0462_typed() -> None:
    """declared RIFF size +462: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 462))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0462_typed() -> None:
    """declared RIFF size -462: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -462))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0463_typed() -> None:
    """declared RIFF size +463: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 463))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0463_typed() -> None:
    """declared RIFF size -463: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -463))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0464_typed() -> None:
    """declared RIFF size +464: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 464))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0464_typed() -> None:
    """declared RIFF size -464: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -464))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0465_typed() -> None:
    """declared RIFF size +465: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 465))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0465_typed() -> None:
    """declared RIFF size -465: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -465))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0466_typed() -> None:
    """declared RIFF size +466: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 466))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0466_typed() -> None:
    """declared RIFF size -466: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -466))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0467_typed() -> None:
    """declared RIFF size +467: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 467))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0467_typed() -> None:
    """declared RIFF size -467: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -467))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0468_typed() -> None:
    """declared RIFF size +468: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 468))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0468_typed() -> None:
    """declared RIFF size -468: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -468))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0469_typed() -> None:
    """declared RIFF size +469: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 469))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0469_typed() -> None:
    """declared RIFF size -469: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -469))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0470_typed() -> None:
    """declared RIFF size +470: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 470))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0470_typed() -> None:
    """declared RIFF size -470: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -470))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0471_typed() -> None:
    """declared RIFF size +471: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 471))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0471_typed() -> None:
    """declared RIFF size -471: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -471))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0472_typed() -> None:
    """declared RIFF size +472: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 472))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0472_typed() -> None:
    """declared RIFF size -472: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -472))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0473_typed() -> None:
    """declared RIFF size +473: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 473))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0473_typed() -> None:
    """declared RIFF size -473: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -473))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0474_typed() -> None:
    """declared RIFF size +474: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 474))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0474_typed() -> None:
    """declared RIFF size -474: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -474))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0475_typed() -> None:
    """declared RIFF size +475: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 475))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0475_typed() -> None:
    """declared RIFF size -475: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -475))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0476_typed() -> None:
    """declared RIFF size +476: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 476))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0476_typed() -> None:
    """declared RIFF size -476: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -476))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0477_typed() -> None:
    """declared RIFF size +477: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 477))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0477_typed() -> None:
    """declared RIFF size -477: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -477))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0478_typed() -> None:
    """declared RIFF size +478: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 478))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0478_typed() -> None:
    """declared RIFF size -478: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -478))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0479_typed() -> None:
    """declared RIFF size +479: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 479))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0479_typed() -> None:
    """declared RIFF size -479: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -479))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0480_typed() -> None:
    """declared RIFF size +480: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 480))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0480_typed() -> None:
    """declared RIFF size -480: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -480))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0481_typed() -> None:
    """declared RIFF size +481: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 481))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0481_typed() -> None:
    """declared RIFF size -481: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -481))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0482_typed() -> None:
    """declared RIFF size +482: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 482))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0482_typed() -> None:
    """declared RIFF size -482: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -482))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0483_typed() -> None:
    """declared RIFF size +483: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 483))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0483_typed() -> None:
    """declared RIFF size -483: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -483))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0484_typed() -> None:
    """declared RIFF size +484: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 484))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0484_typed() -> None:
    """declared RIFF size -484: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -484))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0485_typed() -> None:
    """declared RIFF size +485: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 485))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0485_typed() -> None:
    """declared RIFF size -485: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -485))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0486_typed() -> None:
    """declared RIFF size +486: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 486))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0486_typed() -> None:
    """declared RIFF size -486: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -486))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0487_typed() -> None:
    """declared RIFF size +487: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 487))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0487_typed() -> None:
    """declared RIFF size -487: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -487))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0488_typed() -> None:
    """declared RIFF size +488: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 488))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0488_typed() -> None:
    """declared RIFF size -488: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -488))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0489_typed() -> None:
    """declared RIFF size +489: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 489))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0489_typed() -> None:
    """declared RIFF size -489: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -489))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0490_typed() -> None:
    """declared RIFF size +490: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 490))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0490_typed() -> None:
    """declared RIFF size -490: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -490))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0491_typed() -> None:
    """declared RIFF size +491: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 491))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0491_typed() -> None:
    """declared RIFF size -491: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -491))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0492_typed() -> None:
    """declared RIFF size +492: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 492))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0492_typed() -> None:
    """declared RIFF size -492: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -492))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0493_typed() -> None:
    """declared RIFF size +493: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 493))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0493_typed() -> None:
    """declared RIFF size -493: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -493))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0494_typed() -> None:
    """declared RIFF size +494: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 494))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0494_typed() -> None:
    """declared RIFF size -494: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -494))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0495_typed() -> None:
    """declared RIFF size +495: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 495))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0495_typed() -> None:
    """declared RIFF size -495: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -495))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0496_typed() -> None:
    """declared RIFF size +496: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 496))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0496_typed() -> None:
    """declared RIFF size -496: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -496))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0497_typed() -> None:
    """declared RIFF size +497: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 497))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0497_typed() -> None:
    """declared RIFF size -497: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -497))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0498_typed() -> None:
    """declared RIFF size +498: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 498))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0498_typed() -> None:
    """declared RIFF size -498: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -498))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0499_typed() -> None:
    """declared RIFF size +499: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 499))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0499_typed() -> None:
    """declared RIFF size -499: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -499))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0500_typed() -> None:
    """declared RIFF size +500: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 500))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0500_typed() -> None:
    """declared RIFF size -500: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -500))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0501_typed() -> None:
    """declared RIFF size +501: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 501))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0501_typed() -> None:
    """declared RIFF size -501: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -501))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0502_typed() -> None:
    """declared RIFF size +502: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 502))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0502_typed() -> None:
    """declared RIFF size -502: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -502))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0503_typed() -> None:
    """declared RIFF size +503: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 503))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0503_typed() -> None:
    """declared RIFF size -503: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -503))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0504_typed() -> None:
    """declared RIFF size +504: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 504))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0504_typed() -> None:
    """declared RIFF size -504: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -504))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0505_typed() -> None:
    """declared RIFF size +505: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 505))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0505_typed() -> None:
    """declared RIFF size -505: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -505))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0506_typed() -> None:
    """declared RIFF size +506: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 506))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0506_typed() -> None:
    """declared RIFF size -506: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -506))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0507_typed() -> None:
    """declared RIFF size +507: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 507))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0507_typed() -> None:
    """declared RIFF size -507: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -507))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0508_typed() -> None:
    """declared RIFF size +508: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 508))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0508_typed() -> None:
    """declared RIFF size -508: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -508))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0509_typed() -> None:
    """declared RIFF size +509: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 509))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0509_typed() -> None:
    """declared RIFF size -509: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -509))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0510_typed() -> None:
    """declared RIFF size +510: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 510))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0510_typed() -> None:
    """declared RIFF size -510: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -510))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0511_typed() -> None:
    """declared RIFF size +511: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 511))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0511_typed() -> None:
    """declared RIFF size -511: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -511))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0512_typed() -> None:
    """declared RIFF size +512: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 512))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0512_typed() -> None:
    """declared RIFF size -512: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -512))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0513_typed() -> None:
    """declared RIFF size +513: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 513))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0513_typed() -> None:
    """declared RIFF size -513: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -513))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0514_typed() -> None:
    """declared RIFF size +514: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 514))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0514_typed() -> None:
    """declared RIFF size -514: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -514))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0515_typed() -> None:
    """declared RIFF size +515: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 515))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0515_typed() -> None:
    """declared RIFF size -515: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -515))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0516_typed() -> None:
    """declared RIFF size +516: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 516))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0516_typed() -> None:
    """declared RIFF size -516: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -516))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0517_typed() -> None:
    """declared RIFF size +517: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 517))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0517_typed() -> None:
    """declared RIFF size -517: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -517))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0518_typed() -> None:
    """declared RIFF size +518: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 518))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0518_typed() -> None:
    """declared RIFF size -518: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -518))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0519_typed() -> None:
    """declared RIFF size +519: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 519))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0519_typed() -> None:
    """declared RIFF size -519: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -519))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0520_typed() -> None:
    """declared RIFF size +520: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 520))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0520_typed() -> None:
    """declared RIFF size -520: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -520))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0521_typed() -> None:
    """declared RIFF size +521: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 521))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0521_typed() -> None:
    """declared RIFF size -521: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -521))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0522_typed() -> None:
    """declared RIFF size +522: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 522))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0522_typed() -> None:
    """declared RIFF size -522: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -522))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0523_typed() -> None:
    """declared RIFF size +523: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 523))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0523_typed() -> None:
    """declared RIFF size -523: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -523))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0524_typed() -> None:
    """declared RIFF size +524: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 524))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0524_typed() -> None:
    """declared RIFF size -524: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -524))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0525_typed() -> None:
    """declared RIFF size +525: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 525))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0525_typed() -> None:
    """declared RIFF size -525: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -525))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0526_typed() -> None:
    """declared RIFF size +526: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 526))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0526_typed() -> None:
    """declared RIFF size -526: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -526))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0527_typed() -> None:
    """declared RIFF size +527: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 527))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0527_typed() -> None:
    """declared RIFF size -527: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -527))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0528_typed() -> None:
    """declared RIFF size +528: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 528))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0528_typed() -> None:
    """declared RIFF size -528: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -528))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0529_typed() -> None:
    """declared RIFF size +529: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 529))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0529_typed() -> None:
    """declared RIFF size -529: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -529))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0530_typed() -> None:
    """declared RIFF size +530: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 530))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0530_typed() -> None:
    """declared RIFF size -530: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -530))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0531_typed() -> None:
    """declared RIFF size +531: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 531))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0531_typed() -> None:
    """declared RIFF size -531: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -531))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0532_typed() -> None:
    """declared RIFF size +532: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 532))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0532_typed() -> None:
    """declared RIFF size -532: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -532))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0533_typed() -> None:
    """declared RIFF size +533: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 533))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0533_typed() -> None:
    """declared RIFF size -533: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -533))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0534_typed() -> None:
    """declared RIFF size +534: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 534))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0534_typed() -> None:
    """declared RIFF size -534: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -534))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0535_typed() -> None:
    """declared RIFF size +535: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 535))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0535_typed() -> None:
    """declared RIFF size -535: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -535))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0536_typed() -> None:
    """declared RIFF size +536: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 536))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0536_typed() -> None:
    """declared RIFF size -536: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -536))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0537_typed() -> None:
    """declared RIFF size +537: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 537))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0537_typed() -> None:
    """declared RIFF size -537: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -537))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0538_typed() -> None:
    """declared RIFF size +538: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 538))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0538_typed() -> None:
    """declared RIFF size -538: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -538))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0539_typed() -> None:
    """declared RIFF size +539: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 539))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0539_typed() -> None:
    """declared RIFF size -539: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -539))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0540_typed() -> None:
    """declared RIFF size +540: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 540))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0540_typed() -> None:
    """declared RIFF size -540: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -540))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0541_typed() -> None:
    """declared RIFF size +541: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 541))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0541_typed() -> None:
    """declared RIFF size -541: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -541))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0542_typed() -> None:
    """declared RIFF size +542: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 542))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0542_typed() -> None:
    """declared RIFF size -542: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -542))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0543_typed() -> None:
    """declared RIFF size +543: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 543))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0543_typed() -> None:
    """declared RIFF size -543: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -543))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0544_typed() -> None:
    """declared RIFF size +544: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 544))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0544_typed() -> None:
    """declared RIFF size -544: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -544))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0545_typed() -> None:
    """declared RIFF size +545: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 545))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0545_typed() -> None:
    """declared RIFF size -545: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -545))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0546_typed() -> None:
    """declared RIFF size +546: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 546))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0546_typed() -> None:
    """declared RIFF size -546: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -546))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0547_typed() -> None:
    """declared RIFF size +547: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 547))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0547_typed() -> None:
    """declared RIFF size -547: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -547))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0548_typed() -> None:
    """declared RIFF size +548: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 548))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0548_typed() -> None:
    """declared RIFF size -548: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -548))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0549_typed() -> None:
    """declared RIFF size +549: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 549))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0549_typed() -> None:
    """declared RIFF size -549: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -549))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0550_typed() -> None:
    """declared RIFF size +550: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 550))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0550_typed() -> None:
    """declared RIFF size -550: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -550))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0551_typed() -> None:
    """declared RIFF size +551: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 551))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0551_typed() -> None:
    """declared RIFF size -551: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -551))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0552_typed() -> None:
    """declared RIFF size +552: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 552))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0552_typed() -> None:
    """declared RIFF size -552: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -552))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0553_typed() -> None:
    """declared RIFF size +553: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 553))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0553_typed() -> None:
    """declared RIFF size -553: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -553))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0554_typed() -> None:
    """declared RIFF size +554: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 554))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0554_typed() -> None:
    """declared RIFF size -554: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -554))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0555_typed() -> None:
    """declared RIFF size +555: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 555))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0555_typed() -> None:
    """declared RIFF size -555: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -555))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0556_typed() -> None:
    """declared RIFF size +556: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 556))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0556_typed() -> None:
    """declared RIFF size -556: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -556))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0557_typed() -> None:
    """declared RIFF size +557: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 557))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0557_typed() -> None:
    """declared RIFF size -557: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -557))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0558_typed() -> None:
    """declared RIFF size +558: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 558))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0558_typed() -> None:
    """declared RIFF size -558: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -558))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0559_typed() -> None:
    """declared RIFF size +559: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 559))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0559_typed() -> None:
    """declared RIFF size -559: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -559))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0560_typed() -> None:
    """declared RIFF size +560: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 560))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0560_typed() -> None:
    """declared RIFF size -560: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -560))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0561_typed() -> None:
    """declared RIFF size +561: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 561))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0561_typed() -> None:
    """declared RIFF size -561: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -561))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0562_typed() -> None:
    """declared RIFF size +562: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 562))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0562_typed() -> None:
    """declared RIFF size -562: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -562))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0563_typed() -> None:
    """declared RIFF size +563: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 563))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0563_typed() -> None:
    """declared RIFF size -563: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -563))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0564_typed() -> None:
    """declared RIFF size +564: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 564))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0564_typed() -> None:
    """declared RIFF size -564: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -564))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0565_typed() -> None:
    """declared RIFF size +565: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 565))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0565_typed() -> None:
    """declared RIFF size -565: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -565))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0566_typed() -> None:
    """declared RIFF size +566: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 566))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0566_typed() -> None:
    """declared RIFF size -566: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -566))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0567_typed() -> None:
    """declared RIFF size +567: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 567))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0567_typed() -> None:
    """declared RIFF size -567: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -567))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0568_typed() -> None:
    """declared RIFF size +568: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 568))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0568_typed() -> None:
    """declared RIFF size -568: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -568))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0569_typed() -> None:
    """declared RIFF size +569: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 569))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0569_typed() -> None:
    """declared RIFF size -569: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -569))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0570_typed() -> None:
    """declared RIFF size +570: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 570))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0570_typed() -> None:
    """declared RIFF size -570: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -570))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0571_typed() -> None:
    """declared RIFF size +571: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 571))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0571_typed() -> None:
    """declared RIFF size -571: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -571))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0572_typed() -> None:
    """declared RIFF size +572: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 572))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0572_typed() -> None:
    """declared RIFF size -572: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -572))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0573_typed() -> None:
    """declared RIFF size +573: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 573))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0573_typed() -> None:
    """declared RIFF size -573: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -573))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0574_typed() -> None:
    """declared RIFF size +574: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 574))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0574_typed() -> None:
    """declared RIFF size -574: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -574))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0575_typed() -> None:
    """declared RIFF size +575: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 575))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0575_typed() -> None:
    """declared RIFF size -575: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -575))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0576_typed() -> None:
    """declared RIFF size +576: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 576))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0576_typed() -> None:
    """declared RIFF size -576: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -576))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0577_typed() -> None:
    """declared RIFF size +577: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 577))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0577_typed() -> None:
    """declared RIFF size -577: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -577))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0578_typed() -> None:
    """declared RIFF size +578: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 578))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0578_typed() -> None:
    """declared RIFF size -578: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -578))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0579_typed() -> None:
    """declared RIFF size +579: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 579))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0579_typed() -> None:
    """declared RIFF size -579: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -579))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0580_typed() -> None:
    """declared RIFF size +580: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 580))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0580_typed() -> None:
    """declared RIFF size -580: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -580))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0581_typed() -> None:
    """declared RIFF size +581: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 581))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0581_typed() -> None:
    """declared RIFF size -581: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -581))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0582_typed() -> None:
    """declared RIFF size +582: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 582))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0582_typed() -> None:
    """declared RIFF size -582: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -582))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0583_typed() -> None:
    """declared RIFF size +583: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 583))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0583_typed() -> None:
    """declared RIFF size -583: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -583))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0584_typed() -> None:
    """declared RIFF size +584: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 584))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0584_typed() -> None:
    """declared RIFF size -584: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -584))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0585_typed() -> None:
    """declared RIFF size +585: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 585))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0585_typed() -> None:
    """declared RIFF size -585: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -585))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0586_typed() -> None:
    """declared RIFF size +586: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 586))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0586_typed() -> None:
    """declared RIFF size -586: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -586))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0587_typed() -> None:
    """declared RIFF size +587: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 587))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0587_typed() -> None:
    """declared RIFF size -587: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -587))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0588_typed() -> None:
    """declared RIFF size +588: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 588))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0588_typed() -> None:
    """declared RIFF size -588: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -588))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0589_typed() -> None:
    """declared RIFF size +589: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 589))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0589_typed() -> None:
    """declared RIFF size -589: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -589))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0590_typed() -> None:
    """declared RIFF size +590: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 590))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0590_typed() -> None:
    """declared RIFF size -590: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -590))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0591_typed() -> None:
    """declared RIFF size +591: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 591))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0591_typed() -> None:
    """declared RIFF size -591: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -591))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0592_typed() -> None:
    """declared RIFF size +592: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 592))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0592_typed() -> None:
    """declared RIFF size -592: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -592))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0593_typed() -> None:
    """declared RIFF size +593: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 593))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0593_typed() -> None:
    """declared RIFF size -593: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -593))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0594_typed() -> None:
    """declared RIFF size +594: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 594))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0594_typed() -> None:
    """declared RIFF size -594: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -594))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0595_typed() -> None:
    """declared RIFF size +595: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 595))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0595_typed() -> None:
    """declared RIFF size -595: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -595))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0596_typed() -> None:
    """declared RIFF size +596: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 596))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0596_typed() -> None:
    """declared RIFF size -596: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -596))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0597_typed() -> None:
    """declared RIFF size +597: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 597))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0597_typed() -> None:
    """declared RIFF size -597: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -597))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0598_typed() -> None:
    """declared RIFF size +598: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 598))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0598_typed() -> None:
    """declared RIFF size -598: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -598))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0599_typed() -> None:
    """declared RIFF size +599: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 599))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0599_typed() -> None:
    """declared RIFF size -599: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -599))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0600_typed() -> None:
    """declared RIFF size +600: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 600))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0600_typed() -> None:
    """declared RIFF size -600: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -600))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0601_typed() -> None:
    """declared RIFF size +601: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 601))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0601_typed() -> None:
    """declared RIFF size -601: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -601))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0602_typed() -> None:
    """declared RIFF size +602: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 602))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0602_typed() -> None:
    """declared RIFF size -602: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -602))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0603_typed() -> None:
    """declared RIFF size +603: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 603))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0603_typed() -> None:
    """declared RIFF size -603: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -603))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0604_typed() -> None:
    """declared RIFF size +604: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 604))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0604_typed() -> None:
    """declared RIFF size -604: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -604))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0605_typed() -> None:
    """declared RIFF size +605: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 605))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0605_typed() -> None:
    """declared RIFF size -605: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -605))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0606_typed() -> None:
    """declared RIFF size +606: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 606))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0606_typed() -> None:
    """declared RIFF size -606: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -606))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0607_typed() -> None:
    """declared RIFF size +607: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 607))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0607_typed() -> None:
    """declared RIFF size -607: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -607))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0608_typed() -> None:
    """declared RIFF size +608: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 608))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0608_typed() -> None:
    """declared RIFF size -608: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -608))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0609_typed() -> None:
    """declared RIFF size +609: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 609))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0609_typed() -> None:
    """declared RIFF size -609: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -609))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0610_typed() -> None:
    """declared RIFF size +610: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 610))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0610_typed() -> None:
    """declared RIFF size -610: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -610))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0611_typed() -> None:
    """declared RIFF size +611: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 611))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0611_typed() -> None:
    """declared RIFF size -611: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -611))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0612_typed() -> None:
    """declared RIFF size +612: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 612))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0612_typed() -> None:
    """declared RIFF size -612: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -612))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0613_typed() -> None:
    """declared RIFF size +613: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 613))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0613_typed() -> None:
    """declared RIFF size -613: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -613))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0614_typed() -> None:
    """declared RIFF size +614: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 614))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0614_typed() -> None:
    """declared RIFF size -614: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -614))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0615_typed() -> None:
    """declared RIFF size +615: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 615))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0615_typed() -> None:
    """declared RIFF size -615: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -615))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0616_typed() -> None:
    """declared RIFF size +616: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 616))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0616_typed() -> None:
    """declared RIFF size -616: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -616))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0617_typed() -> None:
    """declared RIFF size +617: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 617))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0617_typed() -> None:
    """declared RIFF size -617: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -617))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0618_typed() -> None:
    """declared RIFF size +618: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 618))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0618_typed() -> None:
    """declared RIFF size -618: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -618))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0619_typed() -> None:
    """declared RIFF size +619: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 619))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0619_typed() -> None:
    """declared RIFF size -619: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -619))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0620_typed() -> None:
    """declared RIFF size +620: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 620))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0620_typed() -> None:
    """declared RIFF size -620: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -620))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0621_typed() -> None:
    """declared RIFF size +621: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 621))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0621_typed() -> None:
    """declared RIFF size -621: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -621))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0622_typed() -> None:
    """declared RIFF size +622: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 622))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0622_typed() -> None:
    """declared RIFF size -622: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -622))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0623_typed() -> None:
    """declared RIFF size +623: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 623))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0623_typed() -> None:
    """declared RIFF size -623: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -623))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0624_typed() -> None:
    """declared RIFF size +624: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 624))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0624_typed() -> None:
    """declared RIFF size -624: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -624))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0625_typed() -> None:
    """declared RIFF size +625: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 625))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0625_typed() -> None:
    """declared RIFF size -625: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -625))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0626_typed() -> None:
    """declared RIFF size +626: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 626))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0626_typed() -> None:
    """declared RIFF size -626: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -626))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0627_typed() -> None:
    """declared RIFF size +627: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 627))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0627_typed() -> None:
    """declared RIFF size -627: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -627))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0628_typed() -> None:
    """declared RIFF size +628: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 628))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0628_typed() -> None:
    """declared RIFF size -628: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -628))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0629_typed() -> None:
    """declared RIFF size +629: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 629))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0629_typed() -> None:
    """declared RIFF size -629: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -629))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0630_typed() -> None:
    """declared RIFF size +630: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 630))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0630_typed() -> None:
    """declared RIFF size -630: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -630))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0631_typed() -> None:
    """declared RIFF size +631: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 631))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0631_typed() -> None:
    """declared RIFF size -631: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -631))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0632_typed() -> None:
    """declared RIFF size +632: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 632))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0632_typed() -> None:
    """declared RIFF size -632: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -632))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0633_typed() -> None:
    """declared RIFF size +633: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 633))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0633_typed() -> None:
    """declared RIFF size -633: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -633))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0634_typed() -> None:
    """declared RIFF size +634: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 634))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0634_typed() -> None:
    """declared RIFF size -634: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -634))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0635_typed() -> None:
    """declared RIFF size +635: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 635))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0635_typed() -> None:
    """declared RIFF size -635: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -635))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0636_typed() -> None:
    """declared RIFF size +636: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 636))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0636_typed() -> None:
    """declared RIFF size -636: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -636))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0637_typed() -> None:
    """declared RIFF size +637: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 637))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0637_typed() -> None:
    """declared RIFF size -637: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -637))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0638_typed() -> None:
    """declared RIFF size +638: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 638))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0638_typed() -> None:
    """declared RIFF size -638: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -638))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0639_typed() -> None:
    """declared RIFF size +639: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 639))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0639_typed() -> None:
    """declared RIFF size -639: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -639))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0640_typed() -> None:
    """declared RIFF size +640: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 640))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0640_typed() -> None:
    """declared RIFF size -640: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -640))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0641_typed() -> None:
    """declared RIFF size +641: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 641))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0641_typed() -> None:
    """declared RIFF size -641: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -641))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0642_typed() -> None:
    """declared RIFF size +642: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 642))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0642_typed() -> None:
    """declared RIFF size -642: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -642))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0643_typed() -> None:
    """declared RIFF size +643: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 643))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0643_typed() -> None:
    """declared RIFF size -643: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -643))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0644_typed() -> None:
    """declared RIFF size +644: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 644))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0644_typed() -> None:
    """declared RIFF size -644: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -644))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0645_typed() -> None:
    """declared RIFF size +645: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 645))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0645_typed() -> None:
    """declared RIFF size -645: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -645))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0646_typed() -> None:
    """declared RIFF size +646: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 646))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0646_typed() -> None:
    """declared RIFF size -646: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -646))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0647_typed() -> None:
    """declared RIFF size +647: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 647))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0647_typed() -> None:
    """declared RIFF size -647: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -647))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0648_typed() -> None:
    """declared RIFF size +648: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 648))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0648_typed() -> None:
    """declared RIFF size -648: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -648))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0649_typed() -> None:
    """declared RIFF size +649: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 649))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0649_typed() -> None:
    """declared RIFF size -649: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -649))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0650_typed() -> None:
    """declared RIFF size +650: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 650))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0650_typed() -> None:
    """declared RIFF size -650: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -650))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0651_typed() -> None:
    """declared RIFF size +651: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 651))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0651_typed() -> None:
    """declared RIFF size -651: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -651))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0652_typed() -> None:
    """declared RIFF size +652: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 652))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0652_typed() -> None:
    """declared RIFF size -652: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -652))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0653_typed() -> None:
    """declared RIFF size +653: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 653))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0653_typed() -> None:
    """declared RIFF size -653: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -653))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0654_typed() -> None:
    """declared RIFF size +654: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 654))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0654_typed() -> None:
    """declared RIFF size -654: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -654))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0655_typed() -> None:
    """declared RIFF size +655: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 655))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0655_typed() -> None:
    """declared RIFF size -655: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -655))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0656_typed() -> None:
    """declared RIFF size +656: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 656))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0656_typed() -> None:
    """declared RIFF size -656: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -656))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0657_typed() -> None:
    """declared RIFF size +657: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 657))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0657_typed() -> None:
    """declared RIFF size -657: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -657))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0658_typed() -> None:
    """declared RIFF size +658: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 658))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0658_typed() -> None:
    """declared RIFF size -658: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -658))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0659_typed() -> None:
    """declared RIFF size +659: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 659))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0659_typed() -> None:
    """declared RIFF size -659: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -659))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0660_typed() -> None:
    """declared RIFF size +660: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 660))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0660_typed() -> None:
    """declared RIFF size -660: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -660))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0661_typed() -> None:
    """declared RIFF size +661: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 661))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0661_typed() -> None:
    """declared RIFF size -661: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -661))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0662_typed() -> None:
    """declared RIFF size +662: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 662))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0662_typed() -> None:
    """declared RIFF size -662: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -662))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0663_typed() -> None:
    """declared RIFF size +663: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 663))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0663_typed() -> None:
    """declared RIFF size -663: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -663))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0664_typed() -> None:
    """declared RIFF size +664: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 664))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0664_typed() -> None:
    """declared RIFF size -664: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -664))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0665_typed() -> None:
    """declared RIFF size +665: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 665))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0665_typed() -> None:
    """declared RIFF size -665: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -665))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0666_typed() -> None:
    """declared RIFF size +666: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 666))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0666_typed() -> None:
    """declared RIFF size -666: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -666))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0667_typed() -> None:
    """declared RIFF size +667: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 667))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0667_typed() -> None:
    """declared RIFF size -667: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -667))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0668_typed() -> None:
    """declared RIFF size +668: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 668))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0668_typed() -> None:
    """declared RIFF size -668: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -668))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0669_typed() -> None:
    """declared RIFF size +669: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 669))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0669_typed() -> None:
    """declared RIFF size -669: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -669))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0670_typed() -> None:
    """declared RIFF size +670: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 670))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0670_typed() -> None:
    """declared RIFF size -670: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -670))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0671_typed() -> None:
    """declared RIFF size +671: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 671))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0671_typed() -> None:
    """declared RIFF size -671: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -671))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0672_typed() -> None:
    """declared RIFF size +672: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 672))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0672_typed() -> None:
    """declared RIFF size -672: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -672))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0673_typed() -> None:
    """declared RIFF size +673: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 673))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0673_typed() -> None:
    """declared RIFF size -673: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -673))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0674_typed() -> None:
    """declared RIFF size +674: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 674))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0674_typed() -> None:
    """declared RIFF size -674: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -674))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0675_typed() -> None:
    """declared RIFF size +675: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 675))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0675_typed() -> None:
    """declared RIFF size -675: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -675))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0676_typed() -> None:
    """declared RIFF size +676: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 676))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0676_typed() -> None:
    """declared RIFF size -676: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -676))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0677_typed() -> None:
    """declared RIFF size +677: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 677))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0677_typed() -> None:
    """declared RIFF size -677: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -677))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0678_typed() -> None:
    """declared RIFF size +678: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 678))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0678_typed() -> None:
    """declared RIFF size -678: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -678))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0679_typed() -> None:
    """declared RIFF size +679: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 679))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0679_typed() -> None:
    """declared RIFF size -679: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -679))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0680_typed() -> None:
    """declared RIFF size +680: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 680))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0680_typed() -> None:
    """declared RIFF size -680: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -680))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0681_typed() -> None:
    """declared RIFF size +681: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 681))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0681_typed() -> None:
    """declared RIFF size -681: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -681))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0682_typed() -> None:
    """declared RIFF size +682: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 682))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0682_typed() -> None:
    """declared RIFF size -682: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -682))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0683_typed() -> None:
    """declared RIFF size +683: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 683))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0683_typed() -> None:
    """declared RIFF size -683: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -683))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0684_typed() -> None:
    """declared RIFF size +684: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 684))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0684_typed() -> None:
    """declared RIFF size -684: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -684))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0685_typed() -> None:
    """declared RIFF size +685: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 685))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0685_typed() -> None:
    """declared RIFF size -685: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -685))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0686_typed() -> None:
    """declared RIFF size +686: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 686))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0686_typed() -> None:
    """declared RIFF size -686: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -686))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0687_typed() -> None:
    """declared RIFF size +687: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 687))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0687_typed() -> None:
    """declared RIFF size -687: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -687))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0688_typed() -> None:
    """declared RIFF size +688: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 688))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0688_typed() -> None:
    """declared RIFF size -688: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -688))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0689_typed() -> None:
    """declared RIFF size +689: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 689))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0689_typed() -> None:
    """declared RIFF size -689: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -689))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0690_typed() -> None:
    """declared RIFF size +690: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 690))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0690_typed() -> None:
    """declared RIFF size -690: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -690))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0691_typed() -> None:
    """declared RIFF size +691: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 691))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0691_typed() -> None:
    """declared RIFF size -691: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -691))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0692_typed() -> None:
    """declared RIFF size +692: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 692))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0692_typed() -> None:
    """declared RIFF size -692: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -692))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0693_typed() -> None:
    """declared RIFF size +693: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 693))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0693_typed() -> None:
    """declared RIFF size -693: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -693))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0694_typed() -> None:
    """declared RIFF size +694: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 694))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0694_typed() -> None:
    """declared RIFF size -694: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -694))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0695_typed() -> None:
    """declared RIFF size +695: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 695))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0695_typed() -> None:
    """declared RIFF size -695: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -695))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0696_typed() -> None:
    """declared RIFF size +696: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 696))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0696_typed() -> None:
    """declared RIFF size -696: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -696))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0697_typed() -> None:
    """declared RIFF size +697: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 697))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0697_typed() -> None:
    """declared RIFF size -697: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -697))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0698_typed() -> None:
    """declared RIFF size +698: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 698))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0698_typed() -> None:
    """declared RIFF size -698: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -698))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0699_typed() -> None:
    """declared RIFF size +699: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 699))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0699_typed() -> None:
    """declared RIFF size -699: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -699))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0700_typed() -> None:
    """declared RIFF size +700: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 700))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0700_typed() -> None:
    """declared RIFF size -700: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -700))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0701_typed() -> None:
    """declared RIFF size +701: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 701))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0701_typed() -> None:
    """declared RIFF size -701: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -701))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0702_typed() -> None:
    """declared RIFF size +702: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 702))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0702_typed() -> None:
    """declared RIFF size -702: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -702))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0703_typed() -> None:
    """declared RIFF size +703: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 703))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0703_typed() -> None:
    """declared RIFF size -703: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -703))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0704_typed() -> None:
    """declared RIFF size +704: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 704))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0704_typed() -> None:
    """declared RIFF size -704: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -704))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0705_typed() -> None:
    """declared RIFF size +705: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 705))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0705_typed() -> None:
    """declared RIFF size -705: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -705))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0706_typed() -> None:
    """declared RIFF size +706: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 706))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0706_typed() -> None:
    """declared RIFF size -706: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -706))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0707_typed() -> None:
    """declared RIFF size +707: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 707))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0707_typed() -> None:
    """declared RIFF size -707: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -707))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0708_typed() -> None:
    """declared RIFF size +708: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 708))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0708_typed() -> None:
    """declared RIFF size -708: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -708))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0709_typed() -> None:
    """declared RIFF size +709: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 709))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0709_typed() -> None:
    """declared RIFF size -709: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -709))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0710_typed() -> None:
    """declared RIFF size +710: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 710))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0710_typed() -> None:
    """declared RIFF size -710: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -710))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0711_typed() -> None:
    """declared RIFF size +711: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 711))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0711_typed() -> None:
    """declared RIFF size -711: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -711))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0712_typed() -> None:
    """declared RIFF size +712: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 712))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0712_typed() -> None:
    """declared RIFF size -712: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -712))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0713_typed() -> None:
    """declared RIFF size +713: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 713))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0713_typed() -> None:
    """declared RIFF size -713: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -713))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0714_typed() -> None:
    """declared RIFF size +714: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 714))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0714_typed() -> None:
    """declared RIFF size -714: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -714))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0715_typed() -> None:
    """declared RIFF size +715: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 715))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0715_typed() -> None:
    """declared RIFF size -715: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -715))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0716_typed() -> None:
    """declared RIFF size +716: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 716))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0716_typed() -> None:
    """declared RIFF size -716: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -716))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0717_typed() -> None:
    """declared RIFF size +717: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 717))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0717_typed() -> None:
    """declared RIFF size -717: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -717))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0718_typed() -> None:
    """declared RIFF size +718: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 718))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0718_typed() -> None:
    """declared RIFF size -718: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -718))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0719_typed() -> None:
    """declared RIFF size +719: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 719))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0719_typed() -> None:
    """declared RIFF size -719: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -719))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0720_typed() -> None:
    """declared RIFF size +720: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 720))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0720_typed() -> None:
    """declared RIFF size -720: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -720))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0721_typed() -> None:
    """declared RIFF size +721: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 721))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0721_typed() -> None:
    """declared RIFF size -721: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -721))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0722_typed() -> None:
    """declared RIFF size +722: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 722))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0722_typed() -> None:
    """declared RIFF size -722: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -722))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0723_typed() -> None:
    """declared RIFF size +723: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 723))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0723_typed() -> None:
    """declared RIFF size -723: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -723))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0724_typed() -> None:
    """declared RIFF size +724: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 724))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0724_typed() -> None:
    """declared RIFF size -724: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -724))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0725_typed() -> None:
    """declared RIFF size +725: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 725))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0725_typed() -> None:
    """declared RIFF size -725: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -725))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0726_typed() -> None:
    """declared RIFF size +726: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 726))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0726_typed() -> None:
    """declared RIFF size -726: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -726))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0727_typed() -> None:
    """declared RIFF size +727: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 727))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0727_typed() -> None:
    """declared RIFF size -727: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -727))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0728_typed() -> None:
    """declared RIFF size +728: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 728))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0728_typed() -> None:
    """declared RIFF size -728: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -728))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0729_typed() -> None:
    """declared RIFF size +729: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 729))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0729_typed() -> None:
    """declared RIFF size -729: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -729))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0730_typed() -> None:
    """declared RIFF size +730: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 730))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0730_typed() -> None:
    """declared RIFF size -730: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -730))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0731_typed() -> None:
    """declared RIFF size +731: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 731))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0731_typed() -> None:
    """declared RIFF size -731: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -731))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0732_typed() -> None:
    """declared RIFF size +732: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 732))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0732_typed() -> None:
    """declared RIFF size -732: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -732))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0733_typed() -> None:
    """declared RIFF size +733: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 733))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0733_typed() -> None:
    """declared RIFF size -733: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -733))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0734_typed() -> None:
    """declared RIFF size +734: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 734))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0734_typed() -> None:
    """declared RIFF size -734: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -734))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0735_typed() -> None:
    """declared RIFF size +735: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 735))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0735_typed() -> None:
    """declared RIFF size -735: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -735))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0736_typed() -> None:
    """declared RIFF size +736: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 736))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0736_typed() -> None:
    """declared RIFF size -736: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -736))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0737_typed() -> None:
    """declared RIFF size +737: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 737))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0737_typed() -> None:
    """declared RIFF size -737: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -737))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0738_typed() -> None:
    """declared RIFF size +738: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 738))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0738_typed() -> None:
    """declared RIFF size -738: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -738))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0739_typed() -> None:
    """declared RIFF size +739: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 739))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0739_typed() -> None:
    """declared RIFF size -739: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -739))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0740_typed() -> None:
    """declared RIFF size +740: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 740))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0740_typed() -> None:
    """declared RIFF size -740: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -740))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0741_typed() -> None:
    """declared RIFF size +741: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 741))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0741_typed() -> None:
    """declared RIFF size -741: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -741))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0742_typed() -> None:
    """declared RIFF size +742: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 742))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0742_typed() -> None:
    """declared RIFF size -742: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -742))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0743_typed() -> None:
    """declared RIFF size +743: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 743))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0743_typed() -> None:
    """declared RIFF size -743: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -743))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0744_typed() -> None:
    """declared RIFF size +744: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 744))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0744_typed() -> None:
    """declared RIFF size -744: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -744))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0745_typed() -> None:
    """declared RIFF size +745: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 745))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0745_typed() -> None:
    """declared RIFF size -745: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -745))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0746_typed() -> None:
    """declared RIFF size +746: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 746))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0746_typed() -> None:
    """declared RIFF size -746: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -746))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0747_typed() -> None:
    """declared RIFF size +747: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 747))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0747_typed() -> None:
    """declared RIFF size -747: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -747))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0748_typed() -> None:
    """declared RIFF size +748: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 748))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0748_typed() -> None:
    """declared RIFF size -748: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -748))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0749_typed() -> None:
    """declared RIFF size +749: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 749))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0749_typed() -> None:
    """declared RIFF size -749: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -749))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0750_typed() -> None:
    """declared RIFF size +750: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 750))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0750_typed() -> None:
    """declared RIFF size -750: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -750))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0751_typed() -> None:
    """declared RIFF size +751: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 751))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0751_typed() -> None:
    """declared RIFF size -751: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -751))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0752_typed() -> None:
    """declared RIFF size +752: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 752))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0752_typed() -> None:
    """declared RIFF size -752: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -752))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0753_typed() -> None:
    """declared RIFF size +753: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 753))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0753_typed() -> None:
    """declared RIFF size -753: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -753))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0754_typed() -> None:
    """declared RIFF size +754: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 754))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0754_typed() -> None:
    """declared RIFF size -754: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -754))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0755_typed() -> None:
    """declared RIFF size +755: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 755))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0755_typed() -> None:
    """declared RIFF size -755: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -755))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0756_typed() -> None:
    """declared RIFF size +756: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 756))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0756_typed() -> None:
    """declared RIFF size -756: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -756))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0757_typed() -> None:
    """declared RIFF size +757: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 757))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0757_typed() -> None:
    """declared RIFF size -757: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -757))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0758_typed() -> None:
    """declared RIFF size +758: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 758))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0758_typed() -> None:
    """declared RIFF size -758: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -758))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0759_typed() -> None:
    """declared RIFF size +759: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 759))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0759_typed() -> None:
    """declared RIFF size -759: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -759))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0760_typed() -> None:
    """declared RIFF size +760: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 760))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0760_typed() -> None:
    """declared RIFF size -760: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -760))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0761_typed() -> None:
    """declared RIFF size +761: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 761))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0761_typed() -> None:
    """declared RIFF size -761: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -761))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0762_typed() -> None:
    """declared RIFF size +762: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 762))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0762_typed() -> None:
    """declared RIFF size -762: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -762))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0763_typed() -> None:
    """declared RIFF size +763: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 763))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0763_typed() -> None:
    """declared RIFF size -763: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -763))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0764_typed() -> None:
    """declared RIFF size +764: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 764))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0764_typed() -> None:
    """declared RIFF size -764: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -764))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0765_typed() -> None:
    """declared RIFF size +765: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 765))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0765_typed() -> None:
    """declared RIFF size -765: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -765))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0766_typed() -> None:
    """declared RIFF size +766: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 766))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0766_typed() -> None:
    """declared RIFF size -766: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -766))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0767_typed() -> None:
    """declared RIFF size +767: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 767))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0767_typed() -> None:
    """declared RIFF size -767: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -767))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0768_typed() -> None:
    """declared RIFF size +768: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 768))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0768_typed() -> None:
    """declared RIFF size -768: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -768))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0769_typed() -> None:
    """declared RIFF size +769: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 769))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0769_typed() -> None:
    """declared RIFF size -769: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -769))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0770_typed() -> None:
    """declared RIFF size +770: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 770))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0770_typed() -> None:
    """declared RIFF size -770: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -770))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0771_typed() -> None:
    """declared RIFF size +771: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 771))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0771_typed() -> None:
    """declared RIFF size -771: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -771))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0772_typed() -> None:
    """declared RIFF size +772: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 772))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0772_typed() -> None:
    """declared RIFF size -772: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -772))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0773_typed() -> None:
    """declared RIFF size +773: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 773))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0773_typed() -> None:
    """declared RIFF size -773: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -773))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0774_typed() -> None:
    """declared RIFF size +774: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 774))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0774_typed() -> None:
    """declared RIFF size -774: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -774))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0775_typed() -> None:
    """declared RIFF size +775: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 775))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0775_typed() -> None:
    """declared RIFF size -775: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -775))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0776_typed() -> None:
    """declared RIFF size +776: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 776))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0776_typed() -> None:
    """declared RIFF size -776: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -776))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0777_typed() -> None:
    """declared RIFF size +777: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 777))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0777_typed() -> None:
    """declared RIFF size -777: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -777))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0778_typed() -> None:
    """declared RIFF size +778: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 778))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0778_typed() -> None:
    """declared RIFF size -778: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -778))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0779_typed() -> None:
    """declared RIFF size +779: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 779))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0779_typed() -> None:
    """declared RIFF size -779: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -779))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0780_typed() -> None:
    """declared RIFF size +780: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 780))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0780_typed() -> None:
    """declared RIFF size -780: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -780))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0781_typed() -> None:
    """declared RIFF size +781: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 781))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0781_typed() -> None:
    """declared RIFF size -781: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -781))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0782_typed() -> None:
    """declared RIFF size +782: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 782))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0782_typed() -> None:
    """declared RIFF size -782: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -782))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0783_typed() -> None:
    """declared RIFF size +783: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 783))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0783_typed() -> None:
    """declared RIFF size -783: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -783))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0784_typed() -> None:
    """declared RIFF size +784: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 784))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0784_typed() -> None:
    """declared RIFF size -784: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -784))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0785_typed() -> None:
    """declared RIFF size +785: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 785))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0785_typed() -> None:
    """declared RIFF size -785: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -785))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0786_typed() -> None:
    """declared RIFF size +786: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 786))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0786_typed() -> None:
    """declared RIFF size -786: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -786))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0787_typed() -> None:
    """declared RIFF size +787: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 787))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0787_typed() -> None:
    """declared RIFF size -787: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -787))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0788_typed() -> None:
    """declared RIFF size +788: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 788))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0788_typed() -> None:
    """declared RIFF size -788: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -788))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0789_typed() -> None:
    """declared RIFF size +789: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 789))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0789_typed() -> None:
    """declared RIFF size -789: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -789))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0790_typed() -> None:
    """declared RIFF size +790: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 790))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0790_typed() -> None:
    """declared RIFF size -790: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -790))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0791_typed() -> None:
    """declared RIFF size +791: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 791))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0791_typed() -> None:
    """declared RIFF size -791: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -791))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0792_typed() -> None:
    """declared RIFF size +792: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 792))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0792_typed() -> None:
    """declared RIFF size -792: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -792))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0793_typed() -> None:
    """declared RIFF size +793: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 793))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0793_typed() -> None:
    """declared RIFF size -793: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -793))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0794_typed() -> None:
    """declared RIFF size +794: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 794))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0794_typed() -> None:
    """declared RIFF size -794: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -794))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0795_typed() -> None:
    """declared RIFF size +795: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 795))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0795_typed() -> None:
    """declared RIFF size -795: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -795))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0796_typed() -> None:
    """declared RIFF size +796: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 796))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0796_typed() -> None:
    """declared RIFF size -796: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -796))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0797_typed() -> None:
    """declared RIFF size +797: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 797))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0797_typed() -> None:
    """declared RIFF size -797: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -797))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0798_typed() -> None:
    """declared RIFF size +798: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 798))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0798_typed() -> None:
    """declared RIFF size -798: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -798))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0799_typed() -> None:
    """declared RIFF size +799: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 799))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0799_typed() -> None:
    """declared RIFF size -799: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -799))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizep0800_typed() -> None:
    """declared RIFF size +800: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, 800))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_sizem0800_typed() -> None:
    """declared RIFF size -800: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_resize(base, -800))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr00x00_typed() -> None:
    """header byte 0 <- 0x00: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 0, 0x00))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr00x01_typed() -> None:
    """header byte 0 <- 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 0, 0x01))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr00x41_typed() -> None:
    """header byte 0 <- 0x41: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 0, 0x41))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr00x80_typed() -> None:
    """header byte 0 <- 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 0, 0x80))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr00xFF_typed() -> None:
    """header byte 0 <- 0xFF: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 0, 0xFF))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr01x00_typed() -> None:
    """header byte 1 <- 0x00: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 1, 0x00))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr01x01_typed() -> None:
    """header byte 1 <- 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 1, 0x01))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr01x41_typed() -> None:
    """header byte 1 <- 0x41: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 1, 0x41))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr01x80_typed() -> None:
    """header byte 1 <- 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 1, 0x80))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr01xFF_typed() -> None:
    """header byte 1 <- 0xFF: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 1, 0xFF))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr02x00_typed() -> None:
    """header byte 2 <- 0x00: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 2, 0x00))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr02x01_typed() -> None:
    """header byte 2 <- 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 2, 0x01))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr02x41_typed() -> None:
    """header byte 2 <- 0x41: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 2, 0x41))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr02x80_typed() -> None:
    """header byte 2 <- 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 2, 0x80))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr02xFF_typed() -> None:
    """header byte 2 <- 0xFF: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 2, 0xFF))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr03x00_typed() -> None:
    """header byte 3 <- 0x00: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 3, 0x00))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr03x01_typed() -> None:
    """header byte 3 <- 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 3, 0x01))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr03x41_typed() -> None:
    """header byte 3 <- 0x41: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 3, 0x41))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr03x80_typed() -> None:
    """header byte 3 <- 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 3, 0x80))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr03xFF_typed() -> None:
    """header byte 3 <- 0xFF: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 3, 0xFF))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr04x00_typed() -> None:
    """header byte 4 <- 0x00: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 4, 0x00))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr04x01_typed() -> None:
    """header byte 4 <- 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 4, 0x01))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr04x41_typed() -> None:
    """header byte 4 <- 0x41: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 4, 0x41))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr04x80_typed() -> None:
    """header byte 4 <- 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 4, 0x80))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr04xFF_typed() -> None:
    """header byte 4 <- 0xFF: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 4, 0xFF))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr05x00_typed() -> None:
    """header byte 5 <- 0x00: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 5, 0x00))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr05x01_roundtrip() -> None:
    """header byte 5 <- 0x01: reader returns the sealed context verbatim."""
    assert read_context(_bset(base, 5, 0x01)) == {
        'client_device_id': 'dev-grid-1',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_header_hdr05x41_typed() -> None:
    """header byte 5 <- 0x41: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 5, 0x41))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr05x80_typed() -> None:
    """header byte 5 <- 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 5, 0x80))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr05xFF_typed() -> None:
    """header byte 5 <- 0xFF: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 5, 0xFF))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr06x00_roundtrip() -> None:
    """header byte 6 <- 0x00: reader returns the sealed context verbatim."""
    assert read_context(_bset(base, 6, 0x00)) == {
        'client_device_id': 'dev-grid-1',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_header_hdr06x01_typed() -> None:
    """header byte 6 <- 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 6, 0x01))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr06x41_typed() -> None:
    """header byte 6 <- 0x41: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 6, 0x41))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr06x80_typed() -> None:
    """header byte 6 <- 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 6, 0x80))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr06xFF_typed() -> None:
    """header byte 6 <- 0xFF: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 6, 0xFF))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr07x00_roundtrip() -> None:
    """header byte 7 <- 0x00: reader returns the sealed context verbatim."""
    assert read_context(_bset(base, 7, 0x00)) == {
        'client_device_id': 'dev-grid-1',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_header_hdr07x01_typed() -> None:
    """header byte 7 <- 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 7, 0x01))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr07x41_typed() -> None:
    """header byte 7 <- 0x41: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 7, 0x41))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr07x80_typed() -> None:
    """header byte 7 <- 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 7, 0x80))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr07xFF_typed() -> None:
    """header byte 7 <- 0xFF: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 7, 0xFF))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr08x00_typed() -> None:
    """header byte 8 <- 0x00: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 8, 0x00))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr08x01_typed() -> None:
    """header byte 8 <- 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 8, 0x01))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr08x41_typed() -> None:
    """header byte 8 <- 0x41: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 8, 0x41))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr08x80_typed() -> None:
    """header byte 8 <- 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 8, 0x80))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr08xFF_typed() -> None:
    """header byte 8 <- 0xFF: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 8, 0xFF))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr09x00_typed() -> None:
    """header byte 9 <- 0x00: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 9, 0x00))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr09x01_typed() -> None:
    """header byte 9 <- 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 9, 0x01))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr09x41_roundtrip() -> None:
    """header byte 9 <- 0x41: reader returns the sealed context verbatim."""
    assert read_context(_bset(base, 9, 0x41)) == {
        'client_device_id': 'dev-grid-1',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_header_hdr09x80_typed() -> None:
    """header byte 9 <- 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 9, 0x80))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr09xFF_typed() -> None:
    """header byte 9 <- 0xFF: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 9, 0xFF))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr10x00_typed() -> None:
    """header byte 10 <- 0x00: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 10, 0x00))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr10x01_typed() -> None:
    """header byte 10 <- 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 10, 0x01))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr10x41_typed() -> None:
    """header byte 10 <- 0x41: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 10, 0x41))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr10x80_typed() -> None:
    """header byte 10 <- 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 10, 0x80))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr10xFF_typed() -> None:
    """header byte 10 <- 0xFF: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 10, 0xFF))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr11x00_typed() -> None:
    """header byte 11 <- 0x00: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 11, 0x00))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr11x01_typed() -> None:
    """header byte 11 <- 0x01: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 11, 0x01))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr11x41_typed() -> None:
    """header byte 11 <- 0x41: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 11, 0x41))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr11x80_typed() -> None:
    """header byte 11 <- 0x80: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 11, 0x80))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'


def test_header_hdr11xFF_typed() -> None:
    """header byte 11 <- 0xFF: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_bset(base, 11, 0xFF))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid intake WAV envelope'
