"""Intake envelope chunk-walk grammar grid: frozen verdict per cell.

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


def test_walk_unk0001_roundtrip() -> None:
    """unknown chunk size=1 before context: reader returns the sealed context verbatim."""
    assert read_context(_riff(wav + _chunk(b'AAAA', bytes(((1 * 13) % 251) for _ in range(1))) + base[len(wav) :])) == {
        'client_device_id': 'dev-grid-1',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_walk_unk0002_roundtrip() -> None:
    """unknown chunk size=2 before context: reader returns the sealed context verbatim."""
    assert read_context(_riff(wav + _chunk(b'AAAA', bytes(((2 * 13) % 251) for _ in range(2))) + base[len(wav) :])) == {
        'client_device_id': 'dev-grid-1',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_walk_unk0003_roundtrip() -> None:
    """unknown chunk size=3 before context: reader returns the sealed context verbatim."""
    assert read_context(_riff(wav + _chunk(b'AAAA', bytes(((3 * 13) % 251) for _ in range(3))) + base[len(wav) :])) == {
        'client_device_id': 'dev-grid-1',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_walk_unk0004_roundtrip() -> None:
    """unknown chunk size=4 before context: reader returns the sealed context verbatim."""
    assert read_context(_riff(wav + _chunk(b'AAAA', bytes(((4 * 13) % 251) for _ in range(4))) + base[len(wav) :])) == {
        'client_device_id': 'dev-grid-1',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_walk_unk0005_roundtrip() -> None:
    """unknown chunk size=5 before context: reader returns the sealed context verbatim."""
    assert read_context(_riff(wav + _chunk(b'AAAA', bytes(((5 * 13) % 251) for _ in range(5))) + base[len(wav) :])) == {
        'client_device_id': 'dev-grid-1',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_walk_unk0006_roundtrip() -> None:
    """unknown chunk size=6 before context: reader returns the sealed context verbatim."""
    assert read_context(_riff(wav + _chunk(b'AAAA', bytes(((6 * 13) % 251) for _ in range(6))) + base[len(wav) :])) == {
        'client_device_id': 'dev-grid-1',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_walk_unk0007_roundtrip() -> None:
    """unknown chunk size=7 before context: reader returns the sealed context verbatim."""
    assert read_context(_riff(wav + _chunk(b'AAAA', bytes(((7 * 13) % 251) for _ in range(7))) + base[len(wav) :])) == {
        'client_device_id': 'dev-grid-1',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_walk_unk0008_roundtrip() -> None:
    """unknown chunk size=8 before context: reader returns the sealed context verbatim."""
    assert read_context(_riff(wav + _chunk(b'AAAA', bytes(((8 * 13) % 251) for _ in range(8))) + base[len(wav) :])) == {
        'client_device_id': 'dev-grid-1',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_walk_unk0009_roundtrip() -> None:
    """unknown chunk size=9 before context: reader returns the sealed context verbatim."""
    assert read_context(_riff(wav + _chunk(b'AAAA', bytes(((9 * 13) % 251) for _ in range(9))) + base[len(wav) :])) == {
        'client_device_id': 'dev-grid-1',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_walk_unk0010_roundtrip() -> None:
    """unknown chunk size=10 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((10 * 13) % 251) for _ in range(10))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0011_roundtrip() -> None:
    """unknown chunk size=11 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((11 * 13) % 251) for _ in range(11))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0012_roundtrip() -> None:
    """unknown chunk size=12 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((12 * 13) % 251) for _ in range(12))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0013_roundtrip() -> None:
    """unknown chunk size=13 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((13 * 13) % 251) for _ in range(13))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0014_roundtrip() -> None:
    """unknown chunk size=14 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((14 * 13) % 251) for _ in range(14))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0015_roundtrip() -> None:
    """unknown chunk size=15 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((15 * 13) % 251) for _ in range(15))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0016_roundtrip() -> None:
    """unknown chunk size=16 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((16 * 13) % 251) for _ in range(16))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0017_roundtrip() -> None:
    """unknown chunk size=17 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((17 * 13) % 251) for _ in range(17))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0018_roundtrip() -> None:
    """unknown chunk size=18 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((18 * 13) % 251) for _ in range(18))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0019_roundtrip() -> None:
    """unknown chunk size=19 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((19 * 13) % 251) for _ in range(19))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0020_roundtrip() -> None:
    """unknown chunk size=20 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((20 * 13) % 251) for _ in range(20))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0021_roundtrip() -> None:
    """unknown chunk size=21 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((21 * 13) % 251) for _ in range(21))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0022_roundtrip() -> None:
    """unknown chunk size=22 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((22 * 13) % 251) for _ in range(22))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0023_roundtrip() -> None:
    """unknown chunk size=23 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((23 * 13) % 251) for _ in range(23))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0024_roundtrip() -> None:
    """unknown chunk size=24 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((24 * 13) % 251) for _ in range(24))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0025_roundtrip() -> None:
    """unknown chunk size=25 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((25 * 13) % 251) for _ in range(25))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0026_roundtrip() -> None:
    """unknown chunk size=26 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((26 * 13) % 251) for _ in range(26))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0027_roundtrip() -> None:
    """unknown chunk size=27 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((27 * 13) % 251) for _ in range(27))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0028_roundtrip() -> None:
    """unknown chunk size=28 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((28 * 13) % 251) for _ in range(28))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0029_roundtrip() -> None:
    """unknown chunk size=29 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((29 * 13) % 251) for _ in range(29))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0030_roundtrip() -> None:
    """unknown chunk size=30 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((30 * 13) % 251) for _ in range(30))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0031_roundtrip() -> None:
    """unknown chunk size=31 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((31 * 13) % 251) for _ in range(31))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0032_roundtrip() -> None:
    """unknown chunk size=32 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((32 * 13) % 251) for _ in range(32))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0033_roundtrip() -> None:
    """unknown chunk size=33 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((33 * 13) % 251) for _ in range(33))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0034_roundtrip() -> None:
    """unknown chunk size=34 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((34 * 13) % 251) for _ in range(34))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0035_roundtrip() -> None:
    """unknown chunk size=35 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((35 * 13) % 251) for _ in range(35))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0036_roundtrip() -> None:
    """unknown chunk size=36 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((36 * 13) % 251) for _ in range(36))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0037_roundtrip() -> None:
    """unknown chunk size=37 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((37 * 13) % 251) for _ in range(37))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0038_roundtrip() -> None:
    """unknown chunk size=38 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((38 * 13) % 251) for _ in range(38))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0039_roundtrip() -> None:
    """unknown chunk size=39 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((39 * 13) % 251) for _ in range(39))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0040_roundtrip() -> None:
    """unknown chunk size=40 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((40 * 13) % 251) for _ in range(40))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0041_roundtrip() -> None:
    """unknown chunk size=41 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((41 * 13) % 251) for _ in range(41))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0042_roundtrip() -> None:
    """unknown chunk size=42 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((42 * 13) % 251) for _ in range(42))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0043_roundtrip() -> None:
    """unknown chunk size=43 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((43 * 13) % 251) for _ in range(43))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0044_roundtrip() -> None:
    """unknown chunk size=44 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((44 * 13) % 251) for _ in range(44))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0045_roundtrip() -> None:
    """unknown chunk size=45 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((45 * 13) % 251) for _ in range(45))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0046_roundtrip() -> None:
    """unknown chunk size=46 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((46 * 13) % 251) for _ in range(46))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0047_roundtrip() -> None:
    """unknown chunk size=47 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((47 * 13) % 251) for _ in range(47))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0048_roundtrip() -> None:
    """unknown chunk size=48 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((48 * 13) % 251) for _ in range(48))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0049_roundtrip() -> None:
    """unknown chunk size=49 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((49 * 13) % 251) for _ in range(49))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0050_roundtrip() -> None:
    """unknown chunk size=50 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((50 * 13) % 251) for _ in range(50))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0051_roundtrip() -> None:
    """unknown chunk size=51 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((51 * 13) % 251) for _ in range(51))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0052_roundtrip() -> None:
    """unknown chunk size=52 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((52 * 13) % 251) for _ in range(52))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0053_roundtrip() -> None:
    """unknown chunk size=53 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((53 * 13) % 251) for _ in range(53))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0054_roundtrip() -> None:
    """unknown chunk size=54 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((54 * 13) % 251) for _ in range(54))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0055_roundtrip() -> None:
    """unknown chunk size=55 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((55 * 13) % 251) for _ in range(55))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0056_roundtrip() -> None:
    """unknown chunk size=56 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((56 * 13) % 251) for _ in range(56))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0057_roundtrip() -> None:
    """unknown chunk size=57 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((57 * 13) % 251) for _ in range(57))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0058_roundtrip() -> None:
    """unknown chunk size=58 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((58 * 13) % 251) for _ in range(58))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0059_roundtrip() -> None:
    """unknown chunk size=59 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((59 * 13) % 251) for _ in range(59))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0060_roundtrip() -> None:
    """unknown chunk size=60 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((60 * 13) % 251) for _ in range(60))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0061_roundtrip() -> None:
    """unknown chunk size=61 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((61 * 13) % 251) for _ in range(61))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0062_roundtrip() -> None:
    """unknown chunk size=62 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((62 * 13) % 251) for _ in range(62))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0063_roundtrip() -> None:
    """unknown chunk size=63 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((63 * 13) % 251) for _ in range(63))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0064_roundtrip() -> None:
    """unknown chunk size=64 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((64 * 13) % 251) for _ in range(64))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0065_roundtrip() -> None:
    """unknown chunk size=65 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((65 * 13) % 251) for _ in range(65))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0066_roundtrip() -> None:
    """unknown chunk size=66 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((66 * 13) % 251) for _ in range(66))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0067_roundtrip() -> None:
    """unknown chunk size=67 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((67 * 13) % 251) for _ in range(67))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0068_roundtrip() -> None:
    """unknown chunk size=68 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((68 * 13) % 251) for _ in range(68))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0069_roundtrip() -> None:
    """unknown chunk size=69 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((69 * 13) % 251) for _ in range(69))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0070_roundtrip() -> None:
    """unknown chunk size=70 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((70 * 13) % 251) for _ in range(70))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0071_roundtrip() -> None:
    """unknown chunk size=71 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((71 * 13) % 251) for _ in range(71))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0072_roundtrip() -> None:
    """unknown chunk size=72 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((72 * 13) % 251) for _ in range(72))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0073_roundtrip() -> None:
    """unknown chunk size=73 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((73 * 13) % 251) for _ in range(73))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0074_roundtrip() -> None:
    """unknown chunk size=74 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((74 * 13) % 251) for _ in range(74))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0075_roundtrip() -> None:
    """unknown chunk size=75 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((75 * 13) % 251) for _ in range(75))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0076_roundtrip() -> None:
    """unknown chunk size=76 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((76 * 13) % 251) for _ in range(76))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0077_roundtrip() -> None:
    """unknown chunk size=77 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((77 * 13) % 251) for _ in range(77))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0078_roundtrip() -> None:
    """unknown chunk size=78 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((78 * 13) % 251) for _ in range(78))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0079_roundtrip() -> None:
    """unknown chunk size=79 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((79 * 13) % 251) for _ in range(79))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0080_roundtrip() -> None:
    """unknown chunk size=80 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((80 * 13) % 251) for _ in range(80))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0081_roundtrip() -> None:
    """unknown chunk size=81 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((81 * 13) % 251) for _ in range(81))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0082_roundtrip() -> None:
    """unknown chunk size=82 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((82 * 13) % 251) for _ in range(82))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0083_roundtrip() -> None:
    """unknown chunk size=83 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((83 * 13) % 251) for _ in range(83))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0084_roundtrip() -> None:
    """unknown chunk size=84 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((84 * 13) % 251) for _ in range(84))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0085_roundtrip() -> None:
    """unknown chunk size=85 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((85 * 13) % 251) for _ in range(85))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0086_roundtrip() -> None:
    """unknown chunk size=86 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((86 * 13) % 251) for _ in range(86))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0087_roundtrip() -> None:
    """unknown chunk size=87 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((87 * 13) % 251) for _ in range(87))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0088_roundtrip() -> None:
    """unknown chunk size=88 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((88 * 13) % 251) for _ in range(88))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0089_roundtrip() -> None:
    """unknown chunk size=89 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((89 * 13) % 251) for _ in range(89))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0090_roundtrip() -> None:
    """unknown chunk size=90 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((90 * 13) % 251) for _ in range(90))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0091_roundtrip() -> None:
    """unknown chunk size=91 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((91 * 13) % 251) for _ in range(91))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0092_roundtrip() -> None:
    """unknown chunk size=92 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((92 * 13) % 251) for _ in range(92))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0093_roundtrip() -> None:
    """unknown chunk size=93 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((93 * 13) % 251) for _ in range(93))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0094_roundtrip() -> None:
    """unknown chunk size=94 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((94 * 13) % 251) for _ in range(94))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0095_roundtrip() -> None:
    """unknown chunk size=95 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((95 * 13) % 251) for _ in range(95))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0096_roundtrip() -> None:
    """unknown chunk size=96 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((96 * 13) % 251) for _ in range(96))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0097_roundtrip() -> None:
    """unknown chunk size=97 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((97 * 13) % 251) for _ in range(97))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0098_roundtrip() -> None:
    """unknown chunk size=98 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((98 * 13) % 251) for _ in range(98))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0099_roundtrip() -> None:
    """unknown chunk size=99 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((99 * 13) % 251) for _ in range(99))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0100_roundtrip() -> None:
    """unknown chunk size=100 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((100 * 13) % 251) for _ in range(100))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0101_roundtrip() -> None:
    """unknown chunk size=101 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((101 * 13) % 251) for _ in range(101))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0102_roundtrip() -> None:
    """unknown chunk size=102 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((102 * 13) % 251) for _ in range(102))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0103_roundtrip() -> None:
    """unknown chunk size=103 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((103 * 13) % 251) for _ in range(103))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0104_roundtrip() -> None:
    """unknown chunk size=104 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((104 * 13) % 251) for _ in range(104))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0105_roundtrip() -> None:
    """unknown chunk size=105 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((105 * 13) % 251) for _ in range(105))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0106_roundtrip() -> None:
    """unknown chunk size=106 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((106 * 13) % 251) for _ in range(106))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0107_roundtrip() -> None:
    """unknown chunk size=107 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((107 * 13) % 251) for _ in range(107))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0108_roundtrip() -> None:
    """unknown chunk size=108 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((108 * 13) % 251) for _ in range(108))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0109_roundtrip() -> None:
    """unknown chunk size=109 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((109 * 13) % 251) for _ in range(109))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0110_roundtrip() -> None:
    """unknown chunk size=110 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((110 * 13) % 251) for _ in range(110))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0111_roundtrip() -> None:
    """unknown chunk size=111 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((111 * 13) % 251) for _ in range(111))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0112_roundtrip() -> None:
    """unknown chunk size=112 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((112 * 13) % 251) for _ in range(112))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0113_roundtrip() -> None:
    """unknown chunk size=113 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((113 * 13) % 251) for _ in range(113))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0114_roundtrip() -> None:
    """unknown chunk size=114 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((114 * 13) % 251) for _ in range(114))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0115_roundtrip() -> None:
    """unknown chunk size=115 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((115 * 13) % 251) for _ in range(115))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0116_roundtrip() -> None:
    """unknown chunk size=116 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((116 * 13) % 251) for _ in range(116))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0117_roundtrip() -> None:
    """unknown chunk size=117 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((117 * 13) % 251) for _ in range(117))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0118_roundtrip() -> None:
    """unknown chunk size=118 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((118 * 13) % 251) for _ in range(118))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0119_roundtrip() -> None:
    """unknown chunk size=119 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((119 * 13) % 251) for _ in range(119))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0120_roundtrip() -> None:
    """unknown chunk size=120 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((120 * 13) % 251) for _ in range(120))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0121_roundtrip() -> None:
    """unknown chunk size=121 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((121 * 13) % 251) for _ in range(121))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0122_roundtrip() -> None:
    """unknown chunk size=122 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((122 * 13) % 251) for _ in range(122))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0123_roundtrip() -> None:
    """unknown chunk size=123 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((123 * 13) % 251) for _ in range(123))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0124_roundtrip() -> None:
    """unknown chunk size=124 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((124 * 13) % 251) for _ in range(124))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0125_roundtrip() -> None:
    """unknown chunk size=125 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((125 * 13) % 251) for _ in range(125))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0126_roundtrip() -> None:
    """unknown chunk size=126 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((126 * 13) % 251) for _ in range(126))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0127_roundtrip() -> None:
    """unknown chunk size=127 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((127 * 13) % 251) for _ in range(127))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0128_roundtrip() -> None:
    """unknown chunk size=128 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((128 * 13) % 251) for _ in range(128))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0129_roundtrip() -> None:
    """unknown chunk size=129 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((129 * 13) % 251) for _ in range(129))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0130_roundtrip() -> None:
    """unknown chunk size=130 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((130 * 13) % 251) for _ in range(130))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0131_roundtrip() -> None:
    """unknown chunk size=131 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((131 * 13) % 251) for _ in range(131))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0132_roundtrip() -> None:
    """unknown chunk size=132 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((132 * 13) % 251) for _ in range(132))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0133_roundtrip() -> None:
    """unknown chunk size=133 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((133 * 13) % 251) for _ in range(133))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0134_roundtrip() -> None:
    """unknown chunk size=134 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((134 * 13) % 251) for _ in range(134))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0135_roundtrip() -> None:
    """unknown chunk size=135 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((135 * 13) % 251) for _ in range(135))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0136_roundtrip() -> None:
    """unknown chunk size=136 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((136 * 13) % 251) for _ in range(136))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0137_roundtrip() -> None:
    """unknown chunk size=137 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((137 * 13) % 251) for _ in range(137))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0138_roundtrip() -> None:
    """unknown chunk size=138 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((138 * 13) % 251) for _ in range(138))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0139_roundtrip() -> None:
    """unknown chunk size=139 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((139 * 13) % 251) for _ in range(139))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0140_roundtrip() -> None:
    """unknown chunk size=140 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((140 * 13) % 251) for _ in range(140))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0141_roundtrip() -> None:
    """unknown chunk size=141 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((141 * 13) % 251) for _ in range(141))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0142_roundtrip() -> None:
    """unknown chunk size=142 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((142 * 13) % 251) for _ in range(142))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0143_roundtrip() -> None:
    """unknown chunk size=143 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((143 * 13) % 251) for _ in range(143))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0144_roundtrip() -> None:
    """unknown chunk size=144 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((144 * 13) % 251) for _ in range(144))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0145_roundtrip() -> None:
    """unknown chunk size=145 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((145 * 13) % 251) for _ in range(145))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0146_roundtrip() -> None:
    """unknown chunk size=146 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((146 * 13) % 251) for _ in range(146))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0147_roundtrip() -> None:
    """unknown chunk size=147 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((147 * 13) % 251) for _ in range(147))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0148_roundtrip() -> None:
    """unknown chunk size=148 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((148 * 13) % 251) for _ in range(148))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0149_roundtrip() -> None:
    """unknown chunk size=149 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((149 * 13) % 251) for _ in range(149))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0150_roundtrip() -> None:
    """unknown chunk size=150 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((150 * 13) % 251) for _ in range(150))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0151_roundtrip() -> None:
    """unknown chunk size=151 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((151 * 13) % 251) for _ in range(151))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0152_roundtrip() -> None:
    """unknown chunk size=152 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((152 * 13) % 251) for _ in range(152))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0153_roundtrip() -> None:
    """unknown chunk size=153 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((153 * 13) % 251) for _ in range(153))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0154_roundtrip() -> None:
    """unknown chunk size=154 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((154 * 13) % 251) for _ in range(154))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0155_roundtrip() -> None:
    """unknown chunk size=155 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((155 * 13) % 251) for _ in range(155))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0156_roundtrip() -> None:
    """unknown chunk size=156 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((156 * 13) % 251) for _ in range(156))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0157_roundtrip() -> None:
    """unknown chunk size=157 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((157 * 13) % 251) for _ in range(157))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0158_roundtrip() -> None:
    """unknown chunk size=158 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((158 * 13) % 251) for _ in range(158))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0159_roundtrip() -> None:
    """unknown chunk size=159 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((159 * 13) % 251) for _ in range(159))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0160_roundtrip() -> None:
    """unknown chunk size=160 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((160 * 13) % 251) for _ in range(160))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0161_roundtrip() -> None:
    """unknown chunk size=161 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((161 * 13) % 251) for _ in range(161))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0162_roundtrip() -> None:
    """unknown chunk size=162 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((162 * 13) % 251) for _ in range(162))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0163_roundtrip() -> None:
    """unknown chunk size=163 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((163 * 13) % 251) for _ in range(163))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0164_roundtrip() -> None:
    """unknown chunk size=164 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((164 * 13) % 251) for _ in range(164))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0165_roundtrip() -> None:
    """unknown chunk size=165 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((165 * 13) % 251) for _ in range(165))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0166_roundtrip() -> None:
    """unknown chunk size=166 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((166 * 13) % 251) for _ in range(166))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0167_roundtrip() -> None:
    """unknown chunk size=167 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((167 * 13) % 251) for _ in range(167))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0168_roundtrip() -> None:
    """unknown chunk size=168 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((168 * 13) % 251) for _ in range(168))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0169_roundtrip() -> None:
    """unknown chunk size=169 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((169 * 13) % 251) for _ in range(169))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0170_roundtrip() -> None:
    """unknown chunk size=170 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((170 * 13) % 251) for _ in range(170))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0171_roundtrip() -> None:
    """unknown chunk size=171 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((171 * 13) % 251) for _ in range(171))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0172_roundtrip() -> None:
    """unknown chunk size=172 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((172 * 13) % 251) for _ in range(172))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0173_roundtrip() -> None:
    """unknown chunk size=173 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((173 * 13) % 251) for _ in range(173))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0174_roundtrip() -> None:
    """unknown chunk size=174 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((174 * 13) % 251) for _ in range(174))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0175_roundtrip() -> None:
    """unknown chunk size=175 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((175 * 13) % 251) for _ in range(175))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0176_roundtrip() -> None:
    """unknown chunk size=176 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((176 * 13) % 251) for _ in range(176))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0177_roundtrip() -> None:
    """unknown chunk size=177 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((177 * 13) % 251) for _ in range(177))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0178_roundtrip() -> None:
    """unknown chunk size=178 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((178 * 13) % 251) for _ in range(178))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0179_roundtrip() -> None:
    """unknown chunk size=179 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((179 * 13) % 251) for _ in range(179))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0180_roundtrip() -> None:
    """unknown chunk size=180 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((180 * 13) % 251) for _ in range(180))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0181_roundtrip() -> None:
    """unknown chunk size=181 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((181 * 13) % 251) for _ in range(181))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0182_roundtrip() -> None:
    """unknown chunk size=182 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((182 * 13) % 251) for _ in range(182))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0183_roundtrip() -> None:
    """unknown chunk size=183 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((183 * 13) % 251) for _ in range(183))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0184_roundtrip() -> None:
    """unknown chunk size=184 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((184 * 13) % 251) for _ in range(184))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0185_roundtrip() -> None:
    """unknown chunk size=185 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((185 * 13) % 251) for _ in range(185))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0186_roundtrip() -> None:
    """unknown chunk size=186 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((186 * 13) % 251) for _ in range(186))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0187_roundtrip() -> None:
    """unknown chunk size=187 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((187 * 13) % 251) for _ in range(187))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0188_roundtrip() -> None:
    """unknown chunk size=188 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((188 * 13) % 251) for _ in range(188))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0189_roundtrip() -> None:
    """unknown chunk size=189 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((189 * 13) % 251) for _ in range(189))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0190_roundtrip() -> None:
    """unknown chunk size=190 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((190 * 13) % 251) for _ in range(190))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0191_roundtrip() -> None:
    """unknown chunk size=191 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((191 * 13) % 251) for _ in range(191))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0192_roundtrip() -> None:
    """unknown chunk size=192 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((192 * 13) % 251) for _ in range(192))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0193_roundtrip() -> None:
    """unknown chunk size=193 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((193 * 13) % 251) for _ in range(193))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0194_roundtrip() -> None:
    """unknown chunk size=194 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((194 * 13) % 251) for _ in range(194))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0195_roundtrip() -> None:
    """unknown chunk size=195 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((195 * 13) % 251) for _ in range(195))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0196_roundtrip() -> None:
    """unknown chunk size=196 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((196 * 13) % 251) for _ in range(196))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0197_roundtrip() -> None:
    """unknown chunk size=197 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((197 * 13) % 251) for _ in range(197))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0198_roundtrip() -> None:
    """unknown chunk size=198 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((198 * 13) % 251) for _ in range(198))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0199_roundtrip() -> None:
    """unknown chunk size=199 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((199 * 13) % 251) for _ in range(199))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0200_roundtrip() -> None:
    """unknown chunk size=200 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((200 * 13) % 251) for _ in range(200))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0201_roundtrip() -> None:
    """unknown chunk size=201 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((201 * 13) % 251) for _ in range(201))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0202_roundtrip() -> None:
    """unknown chunk size=202 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((202 * 13) % 251) for _ in range(202))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0203_roundtrip() -> None:
    """unknown chunk size=203 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((203 * 13) % 251) for _ in range(203))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0204_roundtrip() -> None:
    """unknown chunk size=204 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((204 * 13) % 251) for _ in range(204))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0205_roundtrip() -> None:
    """unknown chunk size=205 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((205 * 13) % 251) for _ in range(205))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0206_roundtrip() -> None:
    """unknown chunk size=206 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((206 * 13) % 251) for _ in range(206))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0207_roundtrip() -> None:
    """unknown chunk size=207 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((207 * 13) % 251) for _ in range(207))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0208_roundtrip() -> None:
    """unknown chunk size=208 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((208 * 13) % 251) for _ in range(208))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0209_roundtrip() -> None:
    """unknown chunk size=209 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((209 * 13) % 251) for _ in range(209))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0210_roundtrip() -> None:
    """unknown chunk size=210 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((210 * 13) % 251) for _ in range(210))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0211_roundtrip() -> None:
    """unknown chunk size=211 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((211 * 13) % 251) for _ in range(211))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0212_roundtrip() -> None:
    """unknown chunk size=212 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((212 * 13) % 251) for _ in range(212))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0213_roundtrip() -> None:
    """unknown chunk size=213 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((213 * 13) % 251) for _ in range(213))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0214_roundtrip() -> None:
    """unknown chunk size=214 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((214 * 13) % 251) for _ in range(214))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0215_roundtrip() -> None:
    """unknown chunk size=215 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((215 * 13) % 251) for _ in range(215))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0216_roundtrip() -> None:
    """unknown chunk size=216 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((216 * 13) % 251) for _ in range(216))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0217_roundtrip() -> None:
    """unknown chunk size=217 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((217 * 13) % 251) for _ in range(217))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0218_roundtrip() -> None:
    """unknown chunk size=218 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((218 * 13) % 251) for _ in range(218))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0219_roundtrip() -> None:
    """unknown chunk size=219 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((219 * 13) % 251) for _ in range(219))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0220_roundtrip() -> None:
    """unknown chunk size=220 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((220 * 13) % 251) for _ in range(220))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0221_roundtrip() -> None:
    """unknown chunk size=221 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((221 * 13) % 251) for _ in range(221))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0222_roundtrip() -> None:
    """unknown chunk size=222 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((222 * 13) % 251) for _ in range(222))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0223_roundtrip() -> None:
    """unknown chunk size=223 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((223 * 13) % 251) for _ in range(223))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0224_roundtrip() -> None:
    """unknown chunk size=224 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((224 * 13) % 251) for _ in range(224))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0225_roundtrip() -> None:
    """unknown chunk size=225 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((225 * 13) % 251) for _ in range(225))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0226_roundtrip() -> None:
    """unknown chunk size=226 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((226 * 13) % 251) for _ in range(226))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0227_roundtrip() -> None:
    """unknown chunk size=227 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((227 * 13) % 251) for _ in range(227))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0228_roundtrip() -> None:
    """unknown chunk size=228 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((228 * 13) % 251) for _ in range(228))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0229_roundtrip() -> None:
    """unknown chunk size=229 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((229 * 13) % 251) for _ in range(229))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0230_roundtrip() -> None:
    """unknown chunk size=230 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((230 * 13) % 251) for _ in range(230))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0231_roundtrip() -> None:
    """unknown chunk size=231 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((231 * 13) % 251) for _ in range(231))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0232_roundtrip() -> None:
    """unknown chunk size=232 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((232 * 13) % 251) for _ in range(232))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0233_roundtrip() -> None:
    """unknown chunk size=233 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((233 * 13) % 251) for _ in range(233))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0234_roundtrip() -> None:
    """unknown chunk size=234 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((234 * 13) % 251) for _ in range(234))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0235_roundtrip() -> None:
    """unknown chunk size=235 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((235 * 13) % 251) for _ in range(235))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0236_roundtrip() -> None:
    """unknown chunk size=236 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((236 * 13) % 251) for _ in range(236))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0237_roundtrip() -> None:
    """unknown chunk size=237 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((237 * 13) % 251) for _ in range(237))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0238_roundtrip() -> None:
    """unknown chunk size=238 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((238 * 13) % 251) for _ in range(238))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0239_roundtrip() -> None:
    """unknown chunk size=239 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((239 * 13) % 251) for _ in range(239))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0240_roundtrip() -> None:
    """unknown chunk size=240 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((240 * 13) % 251) for _ in range(240))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0241_roundtrip() -> None:
    """unknown chunk size=241 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((241 * 13) % 251) for _ in range(241))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0242_roundtrip() -> None:
    """unknown chunk size=242 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((242 * 13) % 251) for _ in range(242))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0243_roundtrip() -> None:
    """unknown chunk size=243 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((243 * 13) % 251) for _ in range(243))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0244_roundtrip() -> None:
    """unknown chunk size=244 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((244 * 13) % 251) for _ in range(244))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0245_roundtrip() -> None:
    """unknown chunk size=245 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((245 * 13) % 251) for _ in range(245))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0246_roundtrip() -> None:
    """unknown chunk size=246 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((246 * 13) % 251) for _ in range(246))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0247_roundtrip() -> None:
    """unknown chunk size=247 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((247 * 13) % 251) for _ in range(247))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0248_roundtrip() -> None:
    """unknown chunk size=248 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((248 * 13) % 251) for _ in range(248))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0249_roundtrip() -> None:
    """unknown chunk size=249 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((249 * 13) % 251) for _ in range(249))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0250_roundtrip() -> None:
    """unknown chunk size=250 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((250 * 13) % 251) for _ in range(250))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0251_roundtrip() -> None:
    """unknown chunk size=251 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((251 * 13) % 251) for _ in range(251))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0252_roundtrip() -> None:
    """unknown chunk size=252 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((252 * 13) % 251) for _ in range(252))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0253_roundtrip() -> None:
    """unknown chunk size=253 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((253 * 13) % 251) for _ in range(253))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0254_roundtrip() -> None:
    """unknown chunk size=254 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((254 * 13) % 251) for _ in range(254))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0255_roundtrip() -> None:
    """unknown chunk size=255 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((255 * 13) % 251) for _ in range(255))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0256_roundtrip() -> None:
    """unknown chunk size=256 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((256 * 13) % 251) for _ in range(256))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0257_roundtrip() -> None:
    """unknown chunk size=257 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((257 * 13) % 251) for _ in range(257))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0258_roundtrip() -> None:
    """unknown chunk size=258 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((258 * 13) % 251) for _ in range(258))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0259_roundtrip() -> None:
    """unknown chunk size=259 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((259 * 13) % 251) for _ in range(259))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0260_roundtrip() -> None:
    """unknown chunk size=260 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((260 * 13) % 251) for _ in range(260))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0261_roundtrip() -> None:
    """unknown chunk size=261 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((261 * 13) % 251) for _ in range(261))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0262_roundtrip() -> None:
    """unknown chunk size=262 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((262 * 13) % 251) for _ in range(262))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0263_roundtrip() -> None:
    """unknown chunk size=263 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((263 * 13) % 251) for _ in range(263))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0264_roundtrip() -> None:
    """unknown chunk size=264 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((264 * 13) % 251) for _ in range(264))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0265_roundtrip() -> None:
    """unknown chunk size=265 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((265 * 13) % 251) for _ in range(265))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0266_roundtrip() -> None:
    """unknown chunk size=266 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((266 * 13) % 251) for _ in range(266))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0267_roundtrip() -> None:
    """unknown chunk size=267 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((267 * 13) % 251) for _ in range(267))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0268_roundtrip() -> None:
    """unknown chunk size=268 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((268 * 13) % 251) for _ in range(268))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0269_roundtrip() -> None:
    """unknown chunk size=269 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((269 * 13) % 251) for _ in range(269))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0270_roundtrip() -> None:
    """unknown chunk size=270 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((270 * 13) % 251) for _ in range(270))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0271_roundtrip() -> None:
    """unknown chunk size=271 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((271 * 13) % 251) for _ in range(271))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0272_roundtrip() -> None:
    """unknown chunk size=272 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((272 * 13) % 251) for _ in range(272))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0273_roundtrip() -> None:
    """unknown chunk size=273 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((273 * 13) % 251) for _ in range(273))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0274_roundtrip() -> None:
    """unknown chunk size=274 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((274 * 13) % 251) for _ in range(274))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0275_roundtrip() -> None:
    """unknown chunk size=275 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((275 * 13) % 251) for _ in range(275))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0276_roundtrip() -> None:
    """unknown chunk size=276 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((276 * 13) % 251) for _ in range(276))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0277_roundtrip() -> None:
    """unknown chunk size=277 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((277 * 13) % 251) for _ in range(277))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0278_roundtrip() -> None:
    """unknown chunk size=278 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((278 * 13) % 251) for _ in range(278))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0279_roundtrip() -> None:
    """unknown chunk size=279 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((279 * 13) % 251) for _ in range(279))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0280_roundtrip() -> None:
    """unknown chunk size=280 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((280 * 13) % 251) for _ in range(280))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0281_roundtrip() -> None:
    """unknown chunk size=281 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((281 * 13) % 251) for _ in range(281))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0282_roundtrip() -> None:
    """unknown chunk size=282 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((282 * 13) % 251) for _ in range(282))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0283_roundtrip() -> None:
    """unknown chunk size=283 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((283 * 13) % 251) for _ in range(283))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0284_roundtrip() -> None:
    """unknown chunk size=284 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((284 * 13) % 251) for _ in range(284))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0285_roundtrip() -> None:
    """unknown chunk size=285 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((285 * 13) % 251) for _ in range(285))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0286_roundtrip() -> None:
    """unknown chunk size=286 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((286 * 13) % 251) for _ in range(286))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0287_roundtrip() -> None:
    """unknown chunk size=287 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((287 * 13) % 251) for _ in range(287))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0288_roundtrip() -> None:
    """unknown chunk size=288 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((288 * 13) % 251) for _ in range(288))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0289_roundtrip() -> None:
    """unknown chunk size=289 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((289 * 13) % 251) for _ in range(289))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0290_roundtrip() -> None:
    """unknown chunk size=290 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((290 * 13) % 251) for _ in range(290))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0291_roundtrip() -> None:
    """unknown chunk size=291 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((291 * 13) % 251) for _ in range(291))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0292_roundtrip() -> None:
    """unknown chunk size=292 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((292 * 13) % 251) for _ in range(292))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0293_roundtrip() -> None:
    """unknown chunk size=293 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((293 * 13) % 251) for _ in range(293))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0294_roundtrip() -> None:
    """unknown chunk size=294 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((294 * 13) % 251) for _ in range(294))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0295_roundtrip() -> None:
    """unknown chunk size=295 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((295 * 13) % 251) for _ in range(295))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0296_roundtrip() -> None:
    """unknown chunk size=296 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((296 * 13) % 251) for _ in range(296))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0297_roundtrip() -> None:
    """unknown chunk size=297 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((297 * 13) % 251) for _ in range(297))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0298_roundtrip() -> None:
    """unknown chunk size=298 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((298 * 13) % 251) for _ in range(298))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0299_roundtrip() -> None:
    """unknown chunk size=299 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((299 * 13) % 251) for _ in range(299))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0300_roundtrip() -> None:
    """unknown chunk size=300 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((300 * 13) % 251) for _ in range(300))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0301_roundtrip() -> None:
    """unknown chunk size=301 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((301 * 13) % 251) for _ in range(301))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0302_roundtrip() -> None:
    """unknown chunk size=302 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((302 * 13) % 251) for _ in range(302))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0303_roundtrip() -> None:
    """unknown chunk size=303 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((303 * 13) % 251) for _ in range(303))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0304_roundtrip() -> None:
    """unknown chunk size=304 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((304 * 13) % 251) for _ in range(304))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0305_roundtrip() -> None:
    """unknown chunk size=305 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((305 * 13) % 251) for _ in range(305))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0306_roundtrip() -> None:
    """unknown chunk size=306 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((306 * 13) % 251) for _ in range(306))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0307_roundtrip() -> None:
    """unknown chunk size=307 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((307 * 13) % 251) for _ in range(307))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0308_roundtrip() -> None:
    """unknown chunk size=308 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((308 * 13) % 251) for _ in range(308))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0309_roundtrip() -> None:
    """unknown chunk size=309 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((309 * 13) % 251) for _ in range(309))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0310_roundtrip() -> None:
    """unknown chunk size=310 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((310 * 13) % 251) for _ in range(310))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0311_roundtrip() -> None:
    """unknown chunk size=311 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((311 * 13) % 251) for _ in range(311))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0312_roundtrip() -> None:
    """unknown chunk size=312 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((312 * 13) % 251) for _ in range(312))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0313_roundtrip() -> None:
    """unknown chunk size=313 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((313 * 13) % 251) for _ in range(313))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0314_roundtrip() -> None:
    """unknown chunk size=314 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((314 * 13) % 251) for _ in range(314))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0315_roundtrip() -> None:
    """unknown chunk size=315 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((315 * 13) % 251) for _ in range(315))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0316_roundtrip() -> None:
    """unknown chunk size=316 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((316 * 13) % 251) for _ in range(316))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0317_roundtrip() -> None:
    """unknown chunk size=317 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((317 * 13) % 251) for _ in range(317))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0318_roundtrip() -> None:
    """unknown chunk size=318 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((318 * 13) % 251) for _ in range(318))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0319_roundtrip() -> None:
    """unknown chunk size=319 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((319 * 13) % 251) for _ in range(319))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0320_roundtrip() -> None:
    """unknown chunk size=320 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((320 * 13) % 251) for _ in range(320))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0321_roundtrip() -> None:
    """unknown chunk size=321 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((321 * 13) % 251) for _ in range(321))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0322_roundtrip() -> None:
    """unknown chunk size=322 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((322 * 13) % 251) for _ in range(322))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0323_roundtrip() -> None:
    """unknown chunk size=323 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((323 * 13) % 251) for _ in range(323))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0324_roundtrip() -> None:
    """unknown chunk size=324 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((324 * 13) % 251) for _ in range(324))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0325_roundtrip() -> None:
    """unknown chunk size=325 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((325 * 13) % 251) for _ in range(325))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0326_roundtrip() -> None:
    """unknown chunk size=326 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((326 * 13) % 251) for _ in range(326))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0327_roundtrip() -> None:
    """unknown chunk size=327 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((327 * 13) % 251) for _ in range(327))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0328_roundtrip() -> None:
    """unknown chunk size=328 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((328 * 13) % 251) for _ in range(328))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0329_roundtrip() -> None:
    """unknown chunk size=329 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((329 * 13) % 251) for _ in range(329))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0330_roundtrip() -> None:
    """unknown chunk size=330 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((330 * 13) % 251) for _ in range(330))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0331_roundtrip() -> None:
    """unknown chunk size=331 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((331 * 13) % 251) for _ in range(331))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0332_roundtrip() -> None:
    """unknown chunk size=332 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((332 * 13) % 251) for _ in range(332))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0333_roundtrip() -> None:
    """unknown chunk size=333 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((333 * 13) % 251) for _ in range(333))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0334_roundtrip() -> None:
    """unknown chunk size=334 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((334 * 13) % 251) for _ in range(334))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0335_roundtrip() -> None:
    """unknown chunk size=335 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((335 * 13) % 251) for _ in range(335))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0336_roundtrip() -> None:
    """unknown chunk size=336 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((336 * 13) % 251) for _ in range(336))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0337_roundtrip() -> None:
    """unknown chunk size=337 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((337 * 13) % 251) for _ in range(337))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0338_roundtrip() -> None:
    """unknown chunk size=338 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((338 * 13) % 251) for _ in range(338))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0339_roundtrip() -> None:
    """unknown chunk size=339 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((339 * 13) % 251) for _ in range(339))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0340_roundtrip() -> None:
    """unknown chunk size=340 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((340 * 13) % 251) for _ in range(340))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0341_roundtrip() -> None:
    """unknown chunk size=341 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((341 * 13) % 251) for _ in range(341))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0342_roundtrip() -> None:
    """unknown chunk size=342 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((342 * 13) % 251) for _ in range(342))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0343_roundtrip() -> None:
    """unknown chunk size=343 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((343 * 13) % 251) for _ in range(343))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0344_roundtrip() -> None:
    """unknown chunk size=344 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((344 * 13) % 251) for _ in range(344))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0345_roundtrip() -> None:
    """unknown chunk size=345 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((345 * 13) % 251) for _ in range(345))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0346_roundtrip() -> None:
    """unknown chunk size=346 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((346 * 13) % 251) for _ in range(346))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0347_roundtrip() -> None:
    """unknown chunk size=347 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((347 * 13) % 251) for _ in range(347))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0348_roundtrip() -> None:
    """unknown chunk size=348 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((348 * 13) % 251) for _ in range(348))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0349_roundtrip() -> None:
    """unknown chunk size=349 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((349 * 13) % 251) for _ in range(349))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0350_roundtrip() -> None:
    """unknown chunk size=350 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((350 * 13) % 251) for _ in range(350))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0351_roundtrip() -> None:
    """unknown chunk size=351 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((351 * 13) % 251) for _ in range(351))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0352_roundtrip() -> None:
    """unknown chunk size=352 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((352 * 13) % 251) for _ in range(352))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0353_roundtrip() -> None:
    """unknown chunk size=353 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((353 * 13) % 251) for _ in range(353))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0354_roundtrip() -> None:
    """unknown chunk size=354 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((354 * 13) % 251) for _ in range(354))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0355_roundtrip() -> None:
    """unknown chunk size=355 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((355 * 13) % 251) for _ in range(355))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0356_roundtrip() -> None:
    """unknown chunk size=356 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((356 * 13) % 251) for _ in range(356))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0357_roundtrip() -> None:
    """unknown chunk size=357 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((357 * 13) % 251) for _ in range(357))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0358_roundtrip() -> None:
    """unknown chunk size=358 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((358 * 13) % 251) for _ in range(358))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0359_roundtrip() -> None:
    """unknown chunk size=359 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((359 * 13) % 251) for _ in range(359))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0360_roundtrip() -> None:
    """unknown chunk size=360 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((360 * 13) % 251) for _ in range(360))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0361_roundtrip() -> None:
    """unknown chunk size=361 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((361 * 13) % 251) for _ in range(361))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0362_roundtrip() -> None:
    """unknown chunk size=362 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((362 * 13) % 251) for _ in range(362))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0363_roundtrip() -> None:
    """unknown chunk size=363 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((363 * 13) % 251) for _ in range(363))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0364_roundtrip() -> None:
    """unknown chunk size=364 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((364 * 13) % 251) for _ in range(364))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0365_roundtrip() -> None:
    """unknown chunk size=365 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((365 * 13) % 251) for _ in range(365))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0366_roundtrip() -> None:
    """unknown chunk size=366 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((366 * 13) % 251) for _ in range(366))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0367_roundtrip() -> None:
    """unknown chunk size=367 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((367 * 13) % 251) for _ in range(367))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0368_roundtrip() -> None:
    """unknown chunk size=368 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((368 * 13) % 251) for _ in range(368))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0369_roundtrip() -> None:
    """unknown chunk size=369 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((369 * 13) % 251) for _ in range(369))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0370_roundtrip() -> None:
    """unknown chunk size=370 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((370 * 13) % 251) for _ in range(370))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0371_roundtrip() -> None:
    """unknown chunk size=371 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((371 * 13) % 251) for _ in range(371))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0372_roundtrip() -> None:
    """unknown chunk size=372 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((372 * 13) % 251) for _ in range(372))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0373_roundtrip() -> None:
    """unknown chunk size=373 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((373 * 13) % 251) for _ in range(373))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0374_roundtrip() -> None:
    """unknown chunk size=374 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((374 * 13) % 251) for _ in range(374))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0375_roundtrip() -> None:
    """unknown chunk size=375 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((375 * 13) % 251) for _ in range(375))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0376_roundtrip() -> None:
    """unknown chunk size=376 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((376 * 13) % 251) for _ in range(376))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0377_roundtrip() -> None:
    """unknown chunk size=377 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((377 * 13) % 251) for _ in range(377))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0378_roundtrip() -> None:
    """unknown chunk size=378 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((378 * 13) % 251) for _ in range(378))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0379_roundtrip() -> None:
    """unknown chunk size=379 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((379 * 13) % 251) for _ in range(379))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0380_roundtrip() -> None:
    """unknown chunk size=380 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((380 * 13) % 251) for _ in range(380))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0381_roundtrip() -> None:
    """unknown chunk size=381 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((381 * 13) % 251) for _ in range(381))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0382_roundtrip() -> None:
    """unknown chunk size=382 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((382 * 13) % 251) for _ in range(382))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0383_roundtrip() -> None:
    """unknown chunk size=383 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((383 * 13) % 251) for _ in range(383))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0384_roundtrip() -> None:
    """unknown chunk size=384 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((384 * 13) % 251) for _ in range(384))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0385_roundtrip() -> None:
    """unknown chunk size=385 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((385 * 13) % 251) for _ in range(385))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0386_roundtrip() -> None:
    """unknown chunk size=386 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((386 * 13) % 251) for _ in range(386))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0387_roundtrip() -> None:
    """unknown chunk size=387 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((387 * 13) % 251) for _ in range(387))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0388_roundtrip() -> None:
    """unknown chunk size=388 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((388 * 13) % 251) for _ in range(388))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0389_roundtrip() -> None:
    """unknown chunk size=389 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((389 * 13) % 251) for _ in range(389))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0390_roundtrip() -> None:
    """unknown chunk size=390 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((390 * 13) % 251) for _ in range(390))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0391_roundtrip() -> None:
    """unknown chunk size=391 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((391 * 13) % 251) for _ in range(391))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0392_roundtrip() -> None:
    """unknown chunk size=392 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((392 * 13) % 251) for _ in range(392))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0393_roundtrip() -> None:
    """unknown chunk size=393 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((393 * 13) % 251) for _ in range(393))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0394_roundtrip() -> None:
    """unknown chunk size=394 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((394 * 13) % 251) for _ in range(394))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0395_roundtrip() -> None:
    """unknown chunk size=395 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((395 * 13) % 251) for _ in range(395))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0396_roundtrip() -> None:
    """unknown chunk size=396 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((396 * 13) % 251) for _ in range(396))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0397_roundtrip() -> None:
    """unknown chunk size=397 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((397 * 13) % 251) for _ in range(397))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0398_roundtrip() -> None:
    """unknown chunk size=398 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((398 * 13) % 251) for _ in range(398))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0399_roundtrip() -> None:
    """unknown chunk size=399 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((399 * 13) % 251) for _ in range(399))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0400_roundtrip() -> None:
    """unknown chunk size=400 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((400 * 13) % 251) for _ in range(400))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0401_roundtrip() -> None:
    """unknown chunk size=401 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((401 * 13) % 251) for _ in range(401))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0402_roundtrip() -> None:
    """unknown chunk size=402 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((402 * 13) % 251) for _ in range(402))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0403_roundtrip() -> None:
    """unknown chunk size=403 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((403 * 13) % 251) for _ in range(403))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0404_roundtrip() -> None:
    """unknown chunk size=404 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((404 * 13) % 251) for _ in range(404))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0405_roundtrip() -> None:
    """unknown chunk size=405 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((405 * 13) % 251) for _ in range(405))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0406_roundtrip() -> None:
    """unknown chunk size=406 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((406 * 13) % 251) for _ in range(406))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0407_roundtrip() -> None:
    """unknown chunk size=407 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((407 * 13) % 251) for _ in range(407))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0408_roundtrip() -> None:
    """unknown chunk size=408 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((408 * 13) % 251) for _ in range(408))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0409_roundtrip() -> None:
    """unknown chunk size=409 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((409 * 13) % 251) for _ in range(409))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0410_roundtrip() -> None:
    """unknown chunk size=410 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((410 * 13) % 251) for _ in range(410))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0411_roundtrip() -> None:
    """unknown chunk size=411 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((411 * 13) % 251) for _ in range(411))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0412_roundtrip() -> None:
    """unknown chunk size=412 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((412 * 13) % 251) for _ in range(412))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0413_roundtrip() -> None:
    """unknown chunk size=413 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((413 * 13) % 251) for _ in range(413))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0414_roundtrip() -> None:
    """unknown chunk size=414 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((414 * 13) % 251) for _ in range(414))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0415_roundtrip() -> None:
    """unknown chunk size=415 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((415 * 13) % 251) for _ in range(415))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0416_roundtrip() -> None:
    """unknown chunk size=416 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((416 * 13) % 251) for _ in range(416))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0417_roundtrip() -> None:
    """unknown chunk size=417 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((417 * 13) % 251) for _ in range(417))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0418_roundtrip() -> None:
    """unknown chunk size=418 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((418 * 13) % 251) for _ in range(418))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0419_roundtrip() -> None:
    """unknown chunk size=419 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((419 * 13) % 251) for _ in range(419))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0420_roundtrip() -> None:
    """unknown chunk size=420 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((420 * 13) % 251) for _ in range(420))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0421_roundtrip() -> None:
    """unknown chunk size=421 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((421 * 13) % 251) for _ in range(421))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0422_roundtrip() -> None:
    """unknown chunk size=422 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((422 * 13) % 251) for _ in range(422))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0423_roundtrip() -> None:
    """unknown chunk size=423 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((423 * 13) % 251) for _ in range(423))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0424_roundtrip() -> None:
    """unknown chunk size=424 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((424 * 13) % 251) for _ in range(424))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0425_roundtrip() -> None:
    """unknown chunk size=425 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((425 * 13) % 251) for _ in range(425))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0426_roundtrip() -> None:
    """unknown chunk size=426 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((426 * 13) % 251) for _ in range(426))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0427_roundtrip() -> None:
    """unknown chunk size=427 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((427 * 13) % 251) for _ in range(427))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0428_roundtrip() -> None:
    """unknown chunk size=428 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((428 * 13) % 251) for _ in range(428))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0429_roundtrip() -> None:
    """unknown chunk size=429 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((429 * 13) % 251) for _ in range(429))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0430_roundtrip() -> None:
    """unknown chunk size=430 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((430 * 13) % 251) for _ in range(430))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0431_roundtrip() -> None:
    """unknown chunk size=431 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((431 * 13) % 251) for _ in range(431))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0432_roundtrip() -> None:
    """unknown chunk size=432 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((432 * 13) % 251) for _ in range(432))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0433_roundtrip() -> None:
    """unknown chunk size=433 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((433 * 13) % 251) for _ in range(433))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0434_roundtrip() -> None:
    """unknown chunk size=434 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((434 * 13) % 251) for _ in range(434))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0435_roundtrip() -> None:
    """unknown chunk size=435 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((435 * 13) % 251) for _ in range(435))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0436_roundtrip() -> None:
    """unknown chunk size=436 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((436 * 13) % 251) for _ in range(436))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0437_roundtrip() -> None:
    """unknown chunk size=437 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((437 * 13) % 251) for _ in range(437))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0438_roundtrip() -> None:
    """unknown chunk size=438 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((438 * 13) % 251) for _ in range(438))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0439_roundtrip() -> None:
    """unknown chunk size=439 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((439 * 13) % 251) for _ in range(439))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0440_roundtrip() -> None:
    """unknown chunk size=440 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((440 * 13) % 251) for _ in range(440))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0441_roundtrip() -> None:
    """unknown chunk size=441 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((441 * 13) % 251) for _ in range(441))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0442_roundtrip() -> None:
    """unknown chunk size=442 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((442 * 13) % 251) for _ in range(442))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0443_roundtrip() -> None:
    """unknown chunk size=443 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((443 * 13) % 251) for _ in range(443))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0444_roundtrip() -> None:
    """unknown chunk size=444 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((444 * 13) % 251) for _ in range(444))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0445_roundtrip() -> None:
    """unknown chunk size=445 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((445 * 13) % 251) for _ in range(445))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0446_roundtrip() -> None:
    """unknown chunk size=446 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((446 * 13) % 251) for _ in range(446))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0447_roundtrip() -> None:
    """unknown chunk size=447 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((447 * 13) % 251) for _ in range(447))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0448_roundtrip() -> None:
    """unknown chunk size=448 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((448 * 13) % 251) for _ in range(448))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0449_roundtrip() -> None:
    """unknown chunk size=449 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((449 * 13) % 251) for _ in range(449))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0450_roundtrip() -> None:
    """unknown chunk size=450 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((450 * 13) % 251) for _ in range(450))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0451_roundtrip() -> None:
    """unknown chunk size=451 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((451 * 13) % 251) for _ in range(451))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0452_roundtrip() -> None:
    """unknown chunk size=452 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((452 * 13) % 251) for _ in range(452))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0453_roundtrip() -> None:
    """unknown chunk size=453 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((453 * 13) % 251) for _ in range(453))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0454_roundtrip() -> None:
    """unknown chunk size=454 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((454 * 13) % 251) for _ in range(454))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0455_roundtrip() -> None:
    """unknown chunk size=455 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((455 * 13) % 251) for _ in range(455))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0456_roundtrip() -> None:
    """unknown chunk size=456 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((456 * 13) % 251) for _ in range(456))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0457_roundtrip() -> None:
    """unknown chunk size=457 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((457 * 13) % 251) for _ in range(457))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0458_roundtrip() -> None:
    """unknown chunk size=458 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((458 * 13) % 251) for _ in range(458))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0459_roundtrip() -> None:
    """unknown chunk size=459 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((459 * 13) % 251) for _ in range(459))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0460_roundtrip() -> None:
    """unknown chunk size=460 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((460 * 13) % 251) for _ in range(460))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0461_roundtrip() -> None:
    """unknown chunk size=461 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((461 * 13) % 251) for _ in range(461))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0462_roundtrip() -> None:
    """unknown chunk size=462 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((462 * 13) % 251) for _ in range(462))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0463_roundtrip() -> None:
    """unknown chunk size=463 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((463 * 13) % 251) for _ in range(463))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0464_roundtrip() -> None:
    """unknown chunk size=464 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((464 * 13) % 251) for _ in range(464))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0465_roundtrip() -> None:
    """unknown chunk size=465 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((465 * 13) % 251) for _ in range(465))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0466_roundtrip() -> None:
    """unknown chunk size=466 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((466 * 13) % 251) for _ in range(466))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0467_roundtrip() -> None:
    """unknown chunk size=467 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((467 * 13) % 251) for _ in range(467))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0468_roundtrip() -> None:
    """unknown chunk size=468 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((468 * 13) % 251) for _ in range(468))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0469_roundtrip() -> None:
    """unknown chunk size=469 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((469 * 13) % 251) for _ in range(469))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0470_roundtrip() -> None:
    """unknown chunk size=470 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((470 * 13) % 251) for _ in range(470))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0471_roundtrip() -> None:
    """unknown chunk size=471 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((471 * 13) % 251) for _ in range(471))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0472_roundtrip() -> None:
    """unknown chunk size=472 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((472 * 13) % 251) for _ in range(472))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0473_roundtrip() -> None:
    """unknown chunk size=473 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((473 * 13) % 251) for _ in range(473))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0474_roundtrip() -> None:
    """unknown chunk size=474 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((474 * 13) % 251) for _ in range(474))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0475_roundtrip() -> None:
    """unknown chunk size=475 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((475 * 13) % 251) for _ in range(475))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0476_roundtrip() -> None:
    """unknown chunk size=476 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((476 * 13) % 251) for _ in range(476))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0477_roundtrip() -> None:
    """unknown chunk size=477 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((477 * 13) % 251) for _ in range(477))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0478_roundtrip() -> None:
    """unknown chunk size=478 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((478 * 13) % 251) for _ in range(478))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0479_roundtrip() -> None:
    """unknown chunk size=479 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((479 * 13) % 251) for _ in range(479))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0480_roundtrip() -> None:
    """unknown chunk size=480 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((480 * 13) % 251) for _ in range(480))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0481_roundtrip() -> None:
    """unknown chunk size=481 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((481 * 13) % 251) for _ in range(481))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0482_roundtrip() -> None:
    """unknown chunk size=482 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((482 * 13) % 251) for _ in range(482))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0483_roundtrip() -> None:
    """unknown chunk size=483 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((483 * 13) % 251) for _ in range(483))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0484_roundtrip() -> None:
    """unknown chunk size=484 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((484 * 13) % 251) for _ in range(484))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0485_roundtrip() -> None:
    """unknown chunk size=485 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((485 * 13) % 251) for _ in range(485))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0486_roundtrip() -> None:
    """unknown chunk size=486 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((486 * 13) % 251) for _ in range(486))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0487_roundtrip() -> None:
    """unknown chunk size=487 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((487 * 13) % 251) for _ in range(487))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0488_roundtrip() -> None:
    """unknown chunk size=488 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((488 * 13) % 251) for _ in range(488))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0489_roundtrip() -> None:
    """unknown chunk size=489 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((489 * 13) % 251) for _ in range(489))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0490_roundtrip() -> None:
    """unknown chunk size=490 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((490 * 13) % 251) for _ in range(490))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0491_roundtrip() -> None:
    """unknown chunk size=491 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((491 * 13) % 251) for _ in range(491))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0492_roundtrip() -> None:
    """unknown chunk size=492 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((492 * 13) % 251) for _ in range(492))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0493_roundtrip() -> None:
    """unknown chunk size=493 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((493 * 13) % 251) for _ in range(493))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0494_roundtrip() -> None:
    """unknown chunk size=494 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((494 * 13) % 251) for _ in range(494))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0495_roundtrip() -> None:
    """unknown chunk size=495 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((495 * 13) % 251) for _ in range(495))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0496_roundtrip() -> None:
    """unknown chunk size=496 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((496 * 13) % 251) for _ in range(496))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0497_roundtrip() -> None:
    """unknown chunk size=497 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((497 * 13) % 251) for _ in range(497))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0498_roundtrip() -> None:
    """unknown chunk size=498 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((498 * 13) % 251) for _ in range(498))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0499_roundtrip() -> None:
    """unknown chunk size=499 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((499 * 13) % 251) for _ in range(499))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0500_roundtrip() -> None:
    """unknown chunk size=500 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((500 * 13) % 251) for _ in range(500))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0501_roundtrip() -> None:
    """unknown chunk size=501 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((501 * 13) % 251) for _ in range(501))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0502_roundtrip() -> None:
    """unknown chunk size=502 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((502 * 13) % 251) for _ in range(502))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0503_roundtrip() -> None:
    """unknown chunk size=503 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((503 * 13) % 251) for _ in range(503))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0504_roundtrip() -> None:
    """unknown chunk size=504 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((504 * 13) % 251) for _ in range(504))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0505_roundtrip() -> None:
    """unknown chunk size=505 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((505 * 13) % 251) for _ in range(505))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0506_roundtrip() -> None:
    """unknown chunk size=506 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((506 * 13) % 251) for _ in range(506))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0507_roundtrip() -> None:
    """unknown chunk size=507 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((507 * 13) % 251) for _ in range(507))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0508_roundtrip() -> None:
    """unknown chunk size=508 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((508 * 13) % 251) for _ in range(508))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0509_roundtrip() -> None:
    """unknown chunk size=509 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((509 * 13) % 251) for _ in range(509))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0510_roundtrip() -> None:
    """unknown chunk size=510 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((510 * 13) % 251) for _ in range(510))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0511_roundtrip() -> None:
    """unknown chunk size=511 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((511 * 13) % 251) for _ in range(511))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0512_roundtrip() -> None:
    """unknown chunk size=512 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((512 * 13) % 251) for _ in range(512))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0513_roundtrip() -> None:
    """unknown chunk size=513 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((513 * 13) % 251) for _ in range(513))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0514_roundtrip() -> None:
    """unknown chunk size=514 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((514 * 13) % 251) for _ in range(514))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0515_roundtrip() -> None:
    """unknown chunk size=515 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((515 * 13) % 251) for _ in range(515))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0516_roundtrip() -> None:
    """unknown chunk size=516 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((516 * 13) % 251) for _ in range(516))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0517_roundtrip() -> None:
    """unknown chunk size=517 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((517 * 13) % 251) for _ in range(517))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0518_roundtrip() -> None:
    """unknown chunk size=518 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((518 * 13) % 251) for _ in range(518))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0519_roundtrip() -> None:
    """unknown chunk size=519 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((519 * 13) % 251) for _ in range(519))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0520_roundtrip() -> None:
    """unknown chunk size=520 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((520 * 13) % 251) for _ in range(520))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0521_roundtrip() -> None:
    """unknown chunk size=521 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((521 * 13) % 251) for _ in range(521))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0522_roundtrip() -> None:
    """unknown chunk size=522 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((522 * 13) % 251) for _ in range(522))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0523_roundtrip() -> None:
    """unknown chunk size=523 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((523 * 13) % 251) for _ in range(523))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0524_roundtrip() -> None:
    """unknown chunk size=524 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((524 * 13) % 251) for _ in range(524))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0525_roundtrip() -> None:
    """unknown chunk size=525 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((525 * 13) % 251) for _ in range(525))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0526_roundtrip() -> None:
    """unknown chunk size=526 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((526 * 13) % 251) for _ in range(526))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0527_roundtrip() -> None:
    """unknown chunk size=527 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((527 * 13) % 251) for _ in range(527))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0528_roundtrip() -> None:
    """unknown chunk size=528 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((528 * 13) % 251) for _ in range(528))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0529_roundtrip() -> None:
    """unknown chunk size=529 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((529 * 13) % 251) for _ in range(529))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0530_roundtrip() -> None:
    """unknown chunk size=530 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((530 * 13) % 251) for _ in range(530))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0531_roundtrip() -> None:
    """unknown chunk size=531 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((531 * 13) % 251) for _ in range(531))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0532_roundtrip() -> None:
    """unknown chunk size=532 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((532 * 13) % 251) for _ in range(532))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0533_roundtrip() -> None:
    """unknown chunk size=533 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((533 * 13) % 251) for _ in range(533))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0534_roundtrip() -> None:
    """unknown chunk size=534 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((534 * 13) % 251) for _ in range(534))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0535_roundtrip() -> None:
    """unknown chunk size=535 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((535 * 13) % 251) for _ in range(535))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0536_roundtrip() -> None:
    """unknown chunk size=536 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((536 * 13) % 251) for _ in range(536))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0537_roundtrip() -> None:
    """unknown chunk size=537 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((537 * 13) % 251) for _ in range(537))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0538_roundtrip() -> None:
    """unknown chunk size=538 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((538 * 13) % 251) for _ in range(538))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0539_roundtrip() -> None:
    """unknown chunk size=539 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((539 * 13) % 251) for _ in range(539))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0540_roundtrip() -> None:
    """unknown chunk size=540 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((540 * 13) % 251) for _ in range(540))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0541_roundtrip() -> None:
    """unknown chunk size=541 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((541 * 13) % 251) for _ in range(541))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0542_roundtrip() -> None:
    """unknown chunk size=542 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((542 * 13) % 251) for _ in range(542))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0543_roundtrip() -> None:
    """unknown chunk size=543 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((543 * 13) % 251) for _ in range(543))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0544_roundtrip() -> None:
    """unknown chunk size=544 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((544 * 13) % 251) for _ in range(544))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0545_roundtrip() -> None:
    """unknown chunk size=545 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((545 * 13) % 251) for _ in range(545))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0546_roundtrip() -> None:
    """unknown chunk size=546 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((546 * 13) % 251) for _ in range(546))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0547_roundtrip() -> None:
    """unknown chunk size=547 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((547 * 13) % 251) for _ in range(547))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0548_roundtrip() -> None:
    """unknown chunk size=548 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((548 * 13) % 251) for _ in range(548))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0549_roundtrip() -> None:
    """unknown chunk size=549 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((549 * 13) % 251) for _ in range(549))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0550_roundtrip() -> None:
    """unknown chunk size=550 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((550 * 13) % 251) for _ in range(550))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0551_roundtrip() -> None:
    """unknown chunk size=551 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((551 * 13) % 251) for _ in range(551))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0552_roundtrip() -> None:
    """unknown chunk size=552 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((552 * 13) % 251) for _ in range(552))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0553_roundtrip() -> None:
    """unknown chunk size=553 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((553 * 13) % 251) for _ in range(553))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0554_roundtrip() -> None:
    """unknown chunk size=554 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((554 * 13) % 251) for _ in range(554))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0555_roundtrip() -> None:
    """unknown chunk size=555 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((555 * 13) % 251) for _ in range(555))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0556_roundtrip() -> None:
    """unknown chunk size=556 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((556 * 13) % 251) for _ in range(556))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0557_roundtrip() -> None:
    """unknown chunk size=557 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((557 * 13) % 251) for _ in range(557))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0558_roundtrip() -> None:
    """unknown chunk size=558 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((558 * 13) % 251) for _ in range(558))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0559_roundtrip() -> None:
    """unknown chunk size=559 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((559 * 13) % 251) for _ in range(559))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0560_roundtrip() -> None:
    """unknown chunk size=560 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((560 * 13) % 251) for _ in range(560))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0561_roundtrip() -> None:
    """unknown chunk size=561 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((561 * 13) % 251) for _ in range(561))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0562_roundtrip() -> None:
    """unknown chunk size=562 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((562 * 13) % 251) for _ in range(562))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0563_roundtrip() -> None:
    """unknown chunk size=563 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((563 * 13) % 251) for _ in range(563))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0564_roundtrip() -> None:
    """unknown chunk size=564 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((564 * 13) % 251) for _ in range(564))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0565_roundtrip() -> None:
    """unknown chunk size=565 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((565 * 13) % 251) for _ in range(565))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0566_roundtrip() -> None:
    """unknown chunk size=566 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((566 * 13) % 251) for _ in range(566))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0567_roundtrip() -> None:
    """unknown chunk size=567 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((567 * 13) % 251) for _ in range(567))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0568_roundtrip() -> None:
    """unknown chunk size=568 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((568 * 13) % 251) for _ in range(568))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0569_roundtrip() -> None:
    """unknown chunk size=569 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((569 * 13) % 251) for _ in range(569))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0570_roundtrip() -> None:
    """unknown chunk size=570 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((570 * 13) % 251) for _ in range(570))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0571_roundtrip() -> None:
    """unknown chunk size=571 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((571 * 13) % 251) for _ in range(571))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0572_roundtrip() -> None:
    """unknown chunk size=572 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((572 * 13) % 251) for _ in range(572))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0573_roundtrip() -> None:
    """unknown chunk size=573 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((573 * 13) % 251) for _ in range(573))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0574_roundtrip() -> None:
    """unknown chunk size=574 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((574 * 13) % 251) for _ in range(574))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0575_roundtrip() -> None:
    """unknown chunk size=575 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((575 * 13) % 251) for _ in range(575))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0576_roundtrip() -> None:
    """unknown chunk size=576 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((576 * 13) % 251) for _ in range(576))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0577_roundtrip() -> None:
    """unknown chunk size=577 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((577 * 13) % 251) for _ in range(577))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0578_roundtrip() -> None:
    """unknown chunk size=578 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((578 * 13) % 251) for _ in range(578))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0579_roundtrip() -> None:
    """unknown chunk size=579 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((579 * 13) % 251) for _ in range(579))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0580_roundtrip() -> None:
    """unknown chunk size=580 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((580 * 13) % 251) for _ in range(580))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0581_roundtrip() -> None:
    """unknown chunk size=581 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((581 * 13) % 251) for _ in range(581))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0582_roundtrip() -> None:
    """unknown chunk size=582 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((582 * 13) % 251) for _ in range(582))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0583_roundtrip() -> None:
    """unknown chunk size=583 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((583 * 13) % 251) for _ in range(583))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0584_roundtrip() -> None:
    """unknown chunk size=584 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((584 * 13) % 251) for _ in range(584))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0585_roundtrip() -> None:
    """unknown chunk size=585 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((585 * 13) % 251) for _ in range(585))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0586_roundtrip() -> None:
    """unknown chunk size=586 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((586 * 13) % 251) for _ in range(586))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0587_roundtrip() -> None:
    """unknown chunk size=587 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((587 * 13) % 251) for _ in range(587))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0588_roundtrip() -> None:
    """unknown chunk size=588 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((588 * 13) % 251) for _ in range(588))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0589_roundtrip() -> None:
    """unknown chunk size=589 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((589 * 13) % 251) for _ in range(589))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0590_roundtrip() -> None:
    """unknown chunk size=590 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((590 * 13) % 251) for _ in range(590))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0591_roundtrip() -> None:
    """unknown chunk size=591 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((591 * 13) % 251) for _ in range(591))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0592_roundtrip() -> None:
    """unknown chunk size=592 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((592 * 13) % 251) for _ in range(592))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0593_roundtrip() -> None:
    """unknown chunk size=593 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((593 * 13) % 251) for _ in range(593))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0594_roundtrip() -> None:
    """unknown chunk size=594 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((594 * 13) % 251) for _ in range(594))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0595_roundtrip() -> None:
    """unknown chunk size=595 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((595 * 13) % 251) for _ in range(595))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0596_roundtrip() -> None:
    """unknown chunk size=596 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((596 * 13) % 251) for _ in range(596))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0597_roundtrip() -> None:
    """unknown chunk size=597 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((597 * 13) % 251) for _ in range(597))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0598_roundtrip() -> None:
    """unknown chunk size=598 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((598 * 13) % 251) for _ in range(598))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0599_roundtrip() -> None:
    """unknown chunk size=599 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((599 * 13) % 251) for _ in range(599))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0600_roundtrip() -> None:
    """unknown chunk size=600 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((600 * 13) % 251) for _ in range(600))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0601_roundtrip() -> None:
    """unknown chunk size=601 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((601 * 13) % 251) for _ in range(601))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0602_roundtrip() -> None:
    """unknown chunk size=602 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((602 * 13) % 251) for _ in range(602))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0603_roundtrip() -> None:
    """unknown chunk size=603 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((603 * 13) % 251) for _ in range(603))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0604_roundtrip() -> None:
    """unknown chunk size=604 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((604 * 13) % 251) for _ in range(604))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0605_roundtrip() -> None:
    """unknown chunk size=605 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((605 * 13) % 251) for _ in range(605))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0606_roundtrip() -> None:
    """unknown chunk size=606 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((606 * 13) % 251) for _ in range(606))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0607_roundtrip() -> None:
    """unknown chunk size=607 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((607 * 13) % 251) for _ in range(607))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0608_roundtrip() -> None:
    """unknown chunk size=608 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((608 * 13) % 251) for _ in range(608))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0609_roundtrip() -> None:
    """unknown chunk size=609 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((609 * 13) % 251) for _ in range(609))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0610_roundtrip() -> None:
    """unknown chunk size=610 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((610 * 13) % 251) for _ in range(610))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0611_roundtrip() -> None:
    """unknown chunk size=611 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((611 * 13) % 251) for _ in range(611))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0612_roundtrip() -> None:
    """unknown chunk size=612 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((612 * 13) % 251) for _ in range(612))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0613_roundtrip() -> None:
    """unknown chunk size=613 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((613 * 13) % 251) for _ in range(613))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0614_roundtrip() -> None:
    """unknown chunk size=614 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((614 * 13) % 251) for _ in range(614))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0615_roundtrip() -> None:
    """unknown chunk size=615 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((615 * 13) % 251) for _ in range(615))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0616_roundtrip() -> None:
    """unknown chunk size=616 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((616 * 13) % 251) for _ in range(616))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0617_roundtrip() -> None:
    """unknown chunk size=617 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((617 * 13) % 251) for _ in range(617))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0618_roundtrip() -> None:
    """unknown chunk size=618 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((618 * 13) % 251) for _ in range(618))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0619_roundtrip() -> None:
    """unknown chunk size=619 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((619 * 13) % 251) for _ in range(619))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0620_roundtrip() -> None:
    """unknown chunk size=620 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((620 * 13) % 251) for _ in range(620))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0621_roundtrip() -> None:
    """unknown chunk size=621 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((621 * 13) % 251) for _ in range(621))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0622_roundtrip() -> None:
    """unknown chunk size=622 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((622 * 13) % 251) for _ in range(622))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0623_roundtrip() -> None:
    """unknown chunk size=623 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((623 * 13) % 251) for _ in range(623))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0624_roundtrip() -> None:
    """unknown chunk size=624 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((624 * 13) % 251) for _ in range(624))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0625_roundtrip() -> None:
    """unknown chunk size=625 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((625 * 13) % 251) for _ in range(625))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0626_roundtrip() -> None:
    """unknown chunk size=626 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((626 * 13) % 251) for _ in range(626))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0627_roundtrip() -> None:
    """unknown chunk size=627 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((627 * 13) % 251) for _ in range(627))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0628_roundtrip() -> None:
    """unknown chunk size=628 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((628 * 13) % 251) for _ in range(628))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0629_roundtrip() -> None:
    """unknown chunk size=629 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((629 * 13) % 251) for _ in range(629))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0630_roundtrip() -> None:
    """unknown chunk size=630 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((630 * 13) % 251) for _ in range(630))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0631_roundtrip() -> None:
    """unknown chunk size=631 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((631 * 13) % 251) for _ in range(631))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0632_roundtrip() -> None:
    """unknown chunk size=632 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((632 * 13) % 251) for _ in range(632))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0633_roundtrip() -> None:
    """unknown chunk size=633 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((633 * 13) % 251) for _ in range(633))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0634_roundtrip() -> None:
    """unknown chunk size=634 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((634 * 13) % 251) for _ in range(634))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0635_roundtrip() -> None:
    """unknown chunk size=635 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((635 * 13) % 251) for _ in range(635))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0636_roundtrip() -> None:
    """unknown chunk size=636 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((636 * 13) % 251) for _ in range(636))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0637_roundtrip() -> None:
    """unknown chunk size=637 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((637 * 13) % 251) for _ in range(637))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0638_roundtrip() -> None:
    """unknown chunk size=638 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((638 * 13) % 251) for _ in range(638))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0639_roundtrip() -> None:
    """unknown chunk size=639 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((639 * 13) % 251) for _ in range(639))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0640_roundtrip() -> None:
    """unknown chunk size=640 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((640 * 13) % 251) for _ in range(640))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0641_roundtrip() -> None:
    """unknown chunk size=641 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((641 * 13) % 251) for _ in range(641))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0642_roundtrip() -> None:
    """unknown chunk size=642 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((642 * 13) % 251) for _ in range(642))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0643_roundtrip() -> None:
    """unknown chunk size=643 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((643 * 13) % 251) for _ in range(643))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0644_roundtrip() -> None:
    """unknown chunk size=644 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((644 * 13) % 251) for _ in range(644))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0645_roundtrip() -> None:
    """unknown chunk size=645 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((645 * 13) % 251) for _ in range(645))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0646_roundtrip() -> None:
    """unknown chunk size=646 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((646 * 13) % 251) for _ in range(646))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0647_roundtrip() -> None:
    """unknown chunk size=647 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((647 * 13) % 251) for _ in range(647))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0648_roundtrip() -> None:
    """unknown chunk size=648 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((648 * 13) % 251) for _ in range(648))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0649_roundtrip() -> None:
    """unknown chunk size=649 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((649 * 13) % 251) for _ in range(649))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0650_roundtrip() -> None:
    """unknown chunk size=650 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((650 * 13) % 251) for _ in range(650))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0651_roundtrip() -> None:
    """unknown chunk size=651 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((651 * 13) % 251) for _ in range(651))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0652_roundtrip() -> None:
    """unknown chunk size=652 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((652 * 13) % 251) for _ in range(652))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0653_roundtrip() -> None:
    """unknown chunk size=653 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((653 * 13) % 251) for _ in range(653))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0654_roundtrip() -> None:
    """unknown chunk size=654 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((654 * 13) % 251) for _ in range(654))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0655_roundtrip() -> None:
    """unknown chunk size=655 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((655 * 13) % 251) for _ in range(655))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0656_roundtrip() -> None:
    """unknown chunk size=656 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((656 * 13) % 251) for _ in range(656))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0657_roundtrip() -> None:
    """unknown chunk size=657 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((657 * 13) % 251) for _ in range(657))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0658_roundtrip() -> None:
    """unknown chunk size=658 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((658 * 13) % 251) for _ in range(658))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0659_roundtrip() -> None:
    """unknown chunk size=659 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((659 * 13) % 251) for _ in range(659))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0660_roundtrip() -> None:
    """unknown chunk size=660 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((660 * 13) % 251) for _ in range(660))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0661_roundtrip() -> None:
    """unknown chunk size=661 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((661 * 13) % 251) for _ in range(661))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0662_roundtrip() -> None:
    """unknown chunk size=662 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((662 * 13) % 251) for _ in range(662))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0663_roundtrip() -> None:
    """unknown chunk size=663 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((663 * 13) % 251) for _ in range(663))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0664_roundtrip() -> None:
    """unknown chunk size=664 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((664 * 13) % 251) for _ in range(664))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0665_roundtrip() -> None:
    """unknown chunk size=665 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((665 * 13) % 251) for _ in range(665))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0666_roundtrip() -> None:
    """unknown chunk size=666 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((666 * 13) % 251) for _ in range(666))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0667_roundtrip() -> None:
    """unknown chunk size=667 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((667 * 13) % 251) for _ in range(667))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0668_roundtrip() -> None:
    """unknown chunk size=668 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((668 * 13) % 251) for _ in range(668))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0669_roundtrip() -> None:
    """unknown chunk size=669 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((669 * 13) % 251) for _ in range(669))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0670_roundtrip() -> None:
    """unknown chunk size=670 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((670 * 13) % 251) for _ in range(670))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0671_roundtrip() -> None:
    """unknown chunk size=671 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((671 * 13) % 251) for _ in range(671))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0672_roundtrip() -> None:
    """unknown chunk size=672 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((672 * 13) % 251) for _ in range(672))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0673_roundtrip() -> None:
    """unknown chunk size=673 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((673 * 13) % 251) for _ in range(673))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0674_roundtrip() -> None:
    """unknown chunk size=674 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((674 * 13) % 251) for _ in range(674))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0675_roundtrip() -> None:
    """unknown chunk size=675 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((675 * 13) % 251) for _ in range(675))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0676_roundtrip() -> None:
    """unknown chunk size=676 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((676 * 13) % 251) for _ in range(676))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0677_roundtrip() -> None:
    """unknown chunk size=677 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((677 * 13) % 251) for _ in range(677))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0678_roundtrip() -> None:
    """unknown chunk size=678 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((678 * 13) % 251) for _ in range(678))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0679_roundtrip() -> None:
    """unknown chunk size=679 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((679 * 13) % 251) for _ in range(679))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0680_roundtrip() -> None:
    """unknown chunk size=680 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((680 * 13) % 251) for _ in range(680))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0681_roundtrip() -> None:
    """unknown chunk size=681 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((681 * 13) % 251) for _ in range(681))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0682_roundtrip() -> None:
    """unknown chunk size=682 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((682 * 13) % 251) for _ in range(682))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0683_roundtrip() -> None:
    """unknown chunk size=683 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((683 * 13) % 251) for _ in range(683))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0684_roundtrip() -> None:
    """unknown chunk size=684 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((684 * 13) % 251) for _ in range(684))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0685_roundtrip() -> None:
    """unknown chunk size=685 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((685 * 13) % 251) for _ in range(685))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0686_roundtrip() -> None:
    """unknown chunk size=686 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((686 * 13) % 251) for _ in range(686))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0687_roundtrip() -> None:
    """unknown chunk size=687 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((687 * 13) % 251) for _ in range(687))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0688_roundtrip() -> None:
    """unknown chunk size=688 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((688 * 13) % 251) for _ in range(688))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0689_roundtrip() -> None:
    """unknown chunk size=689 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((689 * 13) % 251) for _ in range(689))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0690_roundtrip() -> None:
    """unknown chunk size=690 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((690 * 13) % 251) for _ in range(690))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0691_roundtrip() -> None:
    """unknown chunk size=691 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((691 * 13) % 251) for _ in range(691))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0692_roundtrip() -> None:
    """unknown chunk size=692 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((692 * 13) % 251) for _ in range(692))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0693_roundtrip() -> None:
    """unknown chunk size=693 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((693 * 13) % 251) for _ in range(693))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0694_roundtrip() -> None:
    """unknown chunk size=694 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((694 * 13) % 251) for _ in range(694))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0695_roundtrip() -> None:
    """unknown chunk size=695 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((695 * 13) % 251) for _ in range(695))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0696_roundtrip() -> None:
    """unknown chunk size=696 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((696 * 13) % 251) for _ in range(696))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0697_roundtrip() -> None:
    """unknown chunk size=697 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((697 * 13) % 251) for _ in range(697))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0698_roundtrip() -> None:
    """unknown chunk size=698 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((698 * 13) % 251) for _ in range(698))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0699_roundtrip() -> None:
    """unknown chunk size=699 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((699 * 13) % 251) for _ in range(699))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0700_roundtrip() -> None:
    """unknown chunk size=700 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((700 * 13) % 251) for _ in range(700))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0701_roundtrip() -> None:
    """unknown chunk size=701 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((701 * 13) % 251) for _ in range(701))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0702_roundtrip() -> None:
    """unknown chunk size=702 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((702 * 13) % 251) for _ in range(702))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0703_roundtrip() -> None:
    """unknown chunk size=703 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((703 * 13) % 251) for _ in range(703))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0704_roundtrip() -> None:
    """unknown chunk size=704 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((704 * 13) % 251) for _ in range(704))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0705_roundtrip() -> None:
    """unknown chunk size=705 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((705 * 13) % 251) for _ in range(705))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0706_roundtrip() -> None:
    """unknown chunk size=706 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((706 * 13) % 251) for _ in range(706))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0707_roundtrip() -> None:
    """unknown chunk size=707 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((707 * 13) % 251) for _ in range(707))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0708_roundtrip() -> None:
    """unknown chunk size=708 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((708 * 13) % 251) for _ in range(708))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0709_roundtrip() -> None:
    """unknown chunk size=709 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((709 * 13) % 251) for _ in range(709))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0710_roundtrip() -> None:
    """unknown chunk size=710 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((710 * 13) % 251) for _ in range(710))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0711_roundtrip() -> None:
    """unknown chunk size=711 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((711 * 13) % 251) for _ in range(711))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0712_roundtrip() -> None:
    """unknown chunk size=712 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((712 * 13) % 251) for _ in range(712))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0713_roundtrip() -> None:
    """unknown chunk size=713 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((713 * 13) % 251) for _ in range(713))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0714_roundtrip() -> None:
    """unknown chunk size=714 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((714 * 13) % 251) for _ in range(714))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0715_roundtrip() -> None:
    """unknown chunk size=715 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((715 * 13) % 251) for _ in range(715))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0716_roundtrip() -> None:
    """unknown chunk size=716 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((716 * 13) % 251) for _ in range(716))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0717_roundtrip() -> None:
    """unknown chunk size=717 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((717 * 13) % 251) for _ in range(717))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0718_roundtrip() -> None:
    """unknown chunk size=718 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((718 * 13) % 251) for _ in range(718))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0719_roundtrip() -> None:
    """unknown chunk size=719 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((719 * 13) % 251) for _ in range(719))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0720_roundtrip() -> None:
    """unknown chunk size=720 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((720 * 13) % 251) for _ in range(720))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0721_roundtrip() -> None:
    """unknown chunk size=721 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((721 * 13) % 251) for _ in range(721))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0722_roundtrip() -> None:
    """unknown chunk size=722 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((722 * 13) % 251) for _ in range(722))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0723_roundtrip() -> None:
    """unknown chunk size=723 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((723 * 13) % 251) for _ in range(723))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0724_roundtrip() -> None:
    """unknown chunk size=724 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((724 * 13) % 251) for _ in range(724))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0725_roundtrip() -> None:
    """unknown chunk size=725 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((725 * 13) % 251) for _ in range(725))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0726_roundtrip() -> None:
    """unknown chunk size=726 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((726 * 13) % 251) for _ in range(726))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0727_roundtrip() -> None:
    """unknown chunk size=727 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((727 * 13) % 251) for _ in range(727))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0728_roundtrip() -> None:
    """unknown chunk size=728 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((728 * 13) % 251) for _ in range(728))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0729_roundtrip() -> None:
    """unknown chunk size=729 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((729 * 13) % 251) for _ in range(729))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0730_roundtrip() -> None:
    """unknown chunk size=730 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((730 * 13) % 251) for _ in range(730))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0731_roundtrip() -> None:
    """unknown chunk size=731 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((731 * 13) % 251) for _ in range(731))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0732_roundtrip() -> None:
    """unknown chunk size=732 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((732 * 13) % 251) for _ in range(732))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0733_roundtrip() -> None:
    """unknown chunk size=733 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((733 * 13) % 251) for _ in range(733))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0734_roundtrip() -> None:
    """unknown chunk size=734 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((734 * 13) % 251) for _ in range(734))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0735_roundtrip() -> None:
    """unknown chunk size=735 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((735 * 13) % 251) for _ in range(735))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0736_roundtrip() -> None:
    """unknown chunk size=736 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((736 * 13) % 251) for _ in range(736))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0737_roundtrip() -> None:
    """unknown chunk size=737 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((737 * 13) % 251) for _ in range(737))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0738_roundtrip() -> None:
    """unknown chunk size=738 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((738 * 13) % 251) for _ in range(738))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0739_roundtrip() -> None:
    """unknown chunk size=739 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((739 * 13) % 251) for _ in range(739))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0740_roundtrip() -> None:
    """unknown chunk size=740 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((740 * 13) % 251) for _ in range(740))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0741_roundtrip() -> None:
    """unknown chunk size=741 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((741 * 13) % 251) for _ in range(741))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0742_roundtrip() -> None:
    """unknown chunk size=742 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((742 * 13) % 251) for _ in range(742))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0743_roundtrip() -> None:
    """unknown chunk size=743 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((743 * 13) % 251) for _ in range(743))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0744_roundtrip() -> None:
    """unknown chunk size=744 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((744 * 13) % 251) for _ in range(744))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0745_roundtrip() -> None:
    """unknown chunk size=745 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((745 * 13) % 251) for _ in range(745))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0746_roundtrip() -> None:
    """unknown chunk size=746 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((746 * 13) % 251) for _ in range(746))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0747_roundtrip() -> None:
    """unknown chunk size=747 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((747 * 13) % 251) for _ in range(747))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0748_roundtrip() -> None:
    """unknown chunk size=748 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((748 * 13) % 251) for _ in range(748))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0749_roundtrip() -> None:
    """unknown chunk size=749 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((749 * 13) % 251) for _ in range(749))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0750_roundtrip() -> None:
    """unknown chunk size=750 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((750 * 13) % 251) for _ in range(750))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0751_roundtrip() -> None:
    """unknown chunk size=751 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((751 * 13) % 251) for _ in range(751))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0752_roundtrip() -> None:
    """unknown chunk size=752 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((752 * 13) % 251) for _ in range(752))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0753_roundtrip() -> None:
    """unknown chunk size=753 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((753 * 13) % 251) for _ in range(753))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0754_roundtrip() -> None:
    """unknown chunk size=754 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((754 * 13) % 251) for _ in range(754))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0755_roundtrip() -> None:
    """unknown chunk size=755 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((755 * 13) % 251) for _ in range(755))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0756_roundtrip() -> None:
    """unknown chunk size=756 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((756 * 13) % 251) for _ in range(756))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0757_roundtrip() -> None:
    """unknown chunk size=757 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((757 * 13) % 251) for _ in range(757))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0758_roundtrip() -> None:
    """unknown chunk size=758 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((758 * 13) % 251) for _ in range(758))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0759_roundtrip() -> None:
    """unknown chunk size=759 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((759 * 13) % 251) for _ in range(759))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0760_roundtrip() -> None:
    """unknown chunk size=760 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((760 * 13) % 251) for _ in range(760))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0761_roundtrip() -> None:
    """unknown chunk size=761 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((761 * 13) % 251) for _ in range(761))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0762_roundtrip() -> None:
    """unknown chunk size=762 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((762 * 13) % 251) for _ in range(762))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0763_roundtrip() -> None:
    """unknown chunk size=763 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((763 * 13) % 251) for _ in range(763))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0764_roundtrip() -> None:
    """unknown chunk size=764 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((764 * 13) % 251) for _ in range(764))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0765_roundtrip() -> None:
    """unknown chunk size=765 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((765 * 13) % 251) for _ in range(765))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0766_roundtrip() -> None:
    """unknown chunk size=766 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((766 * 13) % 251) for _ in range(766))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0767_roundtrip() -> None:
    """unknown chunk size=767 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((767 * 13) % 251) for _ in range(767))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0768_roundtrip() -> None:
    """unknown chunk size=768 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((768 * 13) % 251) for _ in range(768))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0769_roundtrip() -> None:
    """unknown chunk size=769 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((769 * 13) % 251) for _ in range(769))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0770_roundtrip() -> None:
    """unknown chunk size=770 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((770 * 13) % 251) for _ in range(770))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0771_roundtrip() -> None:
    """unknown chunk size=771 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((771 * 13) % 251) for _ in range(771))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0772_roundtrip() -> None:
    """unknown chunk size=772 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((772 * 13) % 251) for _ in range(772))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0773_roundtrip() -> None:
    """unknown chunk size=773 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((773 * 13) % 251) for _ in range(773))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0774_roundtrip() -> None:
    """unknown chunk size=774 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((774 * 13) % 251) for _ in range(774))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0775_roundtrip() -> None:
    """unknown chunk size=775 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((775 * 13) % 251) for _ in range(775))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0776_roundtrip() -> None:
    """unknown chunk size=776 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((776 * 13) % 251) for _ in range(776))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0777_roundtrip() -> None:
    """unknown chunk size=777 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((777 * 13) % 251) for _ in range(777))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0778_roundtrip() -> None:
    """unknown chunk size=778 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((778 * 13) % 251) for _ in range(778))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0779_roundtrip() -> None:
    """unknown chunk size=779 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((779 * 13) % 251) for _ in range(779))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0780_roundtrip() -> None:
    """unknown chunk size=780 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((780 * 13) % 251) for _ in range(780))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0781_roundtrip() -> None:
    """unknown chunk size=781 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((781 * 13) % 251) for _ in range(781))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0782_roundtrip() -> None:
    """unknown chunk size=782 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((782 * 13) % 251) for _ in range(782))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0783_roundtrip() -> None:
    """unknown chunk size=783 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((783 * 13) % 251) for _ in range(783))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0784_roundtrip() -> None:
    """unknown chunk size=784 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((784 * 13) % 251) for _ in range(784))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0785_roundtrip() -> None:
    """unknown chunk size=785 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((785 * 13) % 251) for _ in range(785))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0786_roundtrip() -> None:
    """unknown chunk size=786 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((786 * 13) % 251) for _ in range(786))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0787_roundtrip() -> None:
    """unknown chunk size=787 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((787 * 13) % 251) for _ in range(787))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0788_roundtrip() -> None:
    """unknown chunk size=788 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((788 * 13) % 251) for _ in range(788))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0789_roundtrip() -> None:
    """unknown chunk size=789 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((789 * 13) % 251) for _ in range(789))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0790_roundtrip() -> None:
    """unknown chunk size=790 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((790 * 13) % 251) for _ in range(790))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0791_roundtrip() -> None:
    """unknown chunk size=791 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((791 * 13) % 251) for _ in range(791))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0792_roundtrip() -> None:
    """unknown chunk size=792 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((792 * 13) % 251) for _ in range(792))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0793_roundtrip() -> None:
    """unknown chunk size=793 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((793 * 13) % 251) for _ in range(793))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0794_roundtrip() -> None:
    """unknown chunk size=794 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((794 * 13) % 251) for _ in range(794))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0795_roundtrip() -> None:
    """unknown chunk size=795 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((795 * 13) % 251) for _ in range(795))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0796_roundtrip() -> None:
    """unknown chunk size=796 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((796 * 13) % 251) for _ in range(796))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0797_roundtrip() -> None:
    """unknown chunk size=797 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((797 * 13) % 251) for _ in range(797))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0798_roundtrip() -> None:
    """unknown chunk size=798 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((798 * 13) % 251) for _ in range(798))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0799_roundtrip() -> None:
    """unknown chunk size=799 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((799 * 13) % 251) for _ in range(799))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_unk0800_roundtrip() -> None:
    """unknown chunk size=800 before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + _chunk(b'AAAA', bytes(((800 * 13) % 251) for _ in range(800))) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_lie0001_typed() -> None:
    """unknown chunk size=1 declaring 401B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 1 + 400)
                + bytes(((1 * 13) % 251) for _ in range(1))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0002_typed() -> None:
    """unknown chunk size=2 declaring 402B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 2 + 400)
                + bytes(((2 * 13) % 251) for _ in range(2))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0003_typed() -> None:
    """unknown chunk size=3 declaring 403B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 3 + 400)
                + bytes(((3 * 13) % 251) for _ in range(3))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0004_typed() -> None:
    """unknown chunk size=4 declaring 404B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 4 + 400)
                + bytes(((4 * 13) % 251) for _ in range(4))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0005_typed() -> None:
    """unknown chunk size=5 declaring 405B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 5 + 400)
                + bytes(((5 * 13) % 251) for _ in range(5))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0006_typed() -> None:
    """unknown chunk size=6 declaring 406B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 6 + 400)
                + bytes(((6 * 13) % 251) for _ in range(6))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0007_typed() -> None:
    """unknown chunk size=7 declaring 407B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 7 + 400)
                + bytes(((7 * 13) % 251) for _ in range(7))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0008_typed() -> None:
    """unknown chunk size=8 declaring 408B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 8 + 400)
                + bytes(((8 * 13) % 251) for _ in range(8))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0009_typed() -> None:
    """unknown chunk size=9 declaring 409B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 9 + 400)
                + bytes(((9 * 13) % 251) for _ in range(9))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0010_typed() -> None:
    """unknown chunk size=10 declaring 410B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 10 + 400)
                + bytes(((10 * 13) % 251) for _ in range(10))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0011_typed() -> None:
    """unknown chunk size=11 declaring 411B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 11 + 400)
                + bytes(((11 * 13) % 251) for _ in range(11))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0012_typed() -> None:
    """unknown chunk size=12 declaring 412B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 12 + 400)
                + bytes(((12 * 13) % 251) for _ in range(12))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0013_typed() -> None:
    """unknown chunk size=13 declaring 413B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 13 + 400)
                + bytes(((13 * 13) % 251) for _ in range(13))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0014_typed() -> None:
    """unknown chunk size=14 declaring 414B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 14 + 400)
                + bytes(((14 * 13) % 251) for _ in range(14))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0015_typed() -> None:
    """unknown chunk size=15 declaring 415B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 15 + 400)
                + bytes(((15 * 13) % 251) for _ in range(15))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0016_typed() -> None:
    """unknown chunk size=16 declaring 416B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 16 + 400)
                + bytes(((16 * 13) % 251) for _ in range(16))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0017_typed() -> None:
    """unknown chunk size=17 declaring 417B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 17 + 400)
                + bytes(((17 * 13) % 251) for _ in range(17))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0018_typed() -> None:
    """unknown chunk size=18 declaring 418B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 18 + 400)
                + bytes(((18 * 13) % 251) for _ in range(18))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0019_typed() -> None:
    """unknown chunk size=19 declaring 419B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 19 + 400)
                + bytes(((19 * 13) % 251) for _ in range(19))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0020_typed() -> None:
    """unknown chunk size=20 declaring 420B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 20 + 400)
                + bytes(((20 * 13) % 251) for _ in range(20))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0021_typed() -> None:
    """unknown chunk size=21 declaring 421B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 21 + 400)
                + bytes(((21 * 13) % 251) for _ in range(21))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0022_typed() -> None:
    """unknown chunk size=22 declaring 422B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 22 + 400)
                + bytes(((22 * 13) % 251) for _ in range(22))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0023_typed() -> None:
    """unknown chunk size=23 declaring 423B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 23 + 400)
                + bytes(((23 * 13) % 251) for _ in range(23))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0024_typed() -> None:
    """unknown chunk size=24 declaring 424B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 24 + 400)
                + bytes(((24 * 13) % 251) for _ in range(24))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0025_typed() -> None:
    """unknown chunk size=25 declaring 425B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 25 + 400)
                + bytes(((25 * 13) % 251) for _ in range(25))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0026_typed() -> None:
    """unknown chunk size=26 declaring 426B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 26 + 400)
                + bytes(((26 * 13) % 251) for _ in range(26))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0027_typed() -> None:
    """unknown chunk size=27 declaring 427B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 27 + 400)
                + bytes(((27 * 13) % 251) for _ in range(27))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0028_typed() -> None:
    """unknown chunk size=28 declaring 428B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 28 + 400)
                + bytes(((28 * 13) % 251) for _ in range(28))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0029_typed() -> None:
    """unknown chunk size=29 declaring 429B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 29 + 400)
                + bytes(((29 * 13) % 251) for _ in range(29))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0030_typed() -> None:
    """unknown chunk size=30 declaring 430B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 30 + 400)
                + bytes(((30 * 13) % 251) for _ in range(30))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0031_typed() -> None:
    """unknown chunk size=31 declaring 431B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 31 + 400)
                + bytes(((31 * 13) % 251) for _ in range(31))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0032_typed() -> None:
    """unknown chunk size=32 declaring 432B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 32 + 400)
                + bytes(((32 * 13) % 251) for _ in range(32))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0033_typed() -> None:
    """unknown chunk size=33 declaring 433B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 33 + 400)
                + bytes(((33 * 13) % 251) for _ in range(33))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0034_typed() -> None:
    """unknown chunk size=34 declaring 434B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 34 + 400)
                + bytes(((34 * 13) % 251) for _ in range(34))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0035_typed() -> None:
    """unknown chunk size=35 declaring 435B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 35 + 400)
                + bytes(((35 * 13) % 251) for _ in range(35))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0036_typed() -> None:
    """unknown chunk size=36 declaring 436B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 36 + 400)
                + bytes(((36 * 13) % 251) for _ in range(36))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0037_typed() -> None:
    """unknown chunk size=37 declaring 437B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 37 + 400)
                + bytes(((37 * 13) % 251) for _ in range(37))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0038_typed() -> None:
    """unknown chunk size=38 declaring 438B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 38 + 400)
                + bytes(((38 * 13) % 251) for _ in range(38))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0039_typed() -> None:
    """unknown chunk size=39 declaring 439B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 39 + 400)
                + bytes(((39 * 13) % 251) for _ in range(39))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0040_typed() -> None:
    """unknown chunk size=40 declaring 440B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 40 + 400)
                + bytes(((40 * 13) % 251) for _ in range(40))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0041_typed() -> None:
    """unknown chunk size=41 declaring 441B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 41 + 400)
                + bytes(((41 * 13) % 251) for _ in range(41))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0042_typed() -> None:
    """unknown chunk size=42 declaring 442B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 42 + 400)
                + bytes(((42 * 13) % 251) for _ in range(42))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0043_typed() -> None:
    """unknown chunk size=43 declaring 443B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 43 + 400)
                + bytes(((43 * 13) % 251) for _ in range(43))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0044_typed() -> None:
    """unknown chunk size=44 declaring 444B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 44 + 400)
                + bytes(((44 * 13) % 251) for _ in range(44))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0045_typed() -> None:
    """unknown chunk size=45 declaring 445B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 45 + 400)
                + bytes(((45 * 13) % 251) for _ in range(45))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0046_typed() -> None:
    """unknown chunk size=46 declaring 446B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 46 + 400)
                + bytes(((46 * 13) % 251) for _ in range(46))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0047_typed() -> None:
    """unknown chunk size=47 declaring 447B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 47 + 400)
                + bytes(((47 * 13) % 251) for _ in range(47))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0048_typed() -> None:
    """unknown chunk size=48 declaring 448B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 48 + 400)
                + bytes(((48 * 13) % 251) for _ in range(48))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0049_typed() -> None:
    """unknown chunk size=49 declaring 449B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 49 + 400)
                + bytes(((49 * 13) % 251) for _ in range(49))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0050_typed() -> None:
    """unknown chunk size=50 declaring 450B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 50 + 400)
                + bytes(((50 * 13) % 251) for _ in range(50))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0051_typed() -> None:
    """unknown chunk size=51 declaring 451B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 51 + 400)
                + bytes(((51 * 13) % 251) for _ in range(51))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0052_typed() -> None:
    """unknown chunk size=52 declaring 452B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 52 + 400)
                + bytes(((52 * 13) % 251) for _ in range(52))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0053_typed() -> None:
    """unknown chunk size=53 declaring 453B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 53 + 400)
                + bytes(((53 * 13) % 251) for _ in range(53))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0054_typed() -> None:
    """unknown chunk size=54 declaring 454B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 54 + 400)
                + bytes(((54 * 13) % 251) for _ in range(54))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0055_typed() -> None:
    """unknown chunk size=55 declaring 455B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 55 + 400)
                + bytes(((55 * 13) % 251) for _ in range(55))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0056_typed() -> None:
    """unknown chunk size=56 declaring 456B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 56 + 400)
                + bytes(((56 * 13) % 251) for _ in range(56))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0057_typed() -> None:
    """unknown chunk size=57 declaring 457B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 57 + 400)
                + bytes(((57 * 13) % 251) for _ in range(57))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0058_typed() -> None:
    """unknown chunk size=58 declaring 458B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 58 + 400)
                + bytes(((58 * 13) % 251) for _ in range(58))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0059_typed() -> None:
    """unknown chunk size=59 declaring 459B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 59 + 400)
                + bytes(((59 * 13) % 251) for _ in range(59))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0060_typed() -> None:
    """unknown chunk size=60 declaring 460B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 60 + 400)
                + bytes(((60 * 13) % 251) for _ in range(60))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0061_typed() -> None:
    """unknown chunk size=61 declaring 461B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 61 + 400)
                + bytes(((61 * 13) % 251) for _ in range(61))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0062_typed() -> None:
    """unknown chunk size=62 declaring 462B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 62 + 400)
                + bytes(((62 * 13) % 251) for _ in range(62))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0063_typed() -> None:
    """unknown chunk size=63 declaring 463B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 63 + 400)
                + bytes(((63 * 13) % 251) for _ in range(63))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0064_typed() -> None:
    """unknown chunk size=64 declaring 464B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 64 + 400)
                + bytes(((64 * 13) % 251) for _ in range(64))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0065_typed() -> None:
    """unknown chunk size=65 declaring 465B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 65 + 400)
                + bytes(((65 * 13) % 251) for _ in range(65))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0066_typed() -> None:
    """unknown chunk size=66 declaring 466B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 66 + 400)
                + bytes(((66 * 13) % 251) for _ in range(66))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0067_typed() -> None:
    """unknown chunk size=67 declaring 467B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 67 + 400)
                + bytes(((67 * 13) % 251) for _ in range(67))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0068_typed() -> None:
    """unknown chunk size=68 declaring 468B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 68 + 400)
                + bytes(((68 * 13) % 251) for _ in range(68))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0069_typed() -> None:
    """unknown chunk size=69 declaring 469B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 69 + 400)
                + bytes(((69 * 13) % 251) for _ in range(69))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0070_typed() -> None:
    """unknown chunk size=70 declaring 470B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 70 + 400)
                + bytes(((70 * 13) % 251) for _ in range(70))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0071_typed() -> None:
    """unknown chunk size=71 declaring 471B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 71 + 400)
                + bytes(((71 * 13) % 251) for _ in range(71))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0072_typed() -> None:
    """unknown chunk size=72 declaring 472B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 72 + 400)
                + bytes(((72 * 13) % 251) for _ in range(72))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0073_typed() -> None:
    """unknown chunk size=73 declaring 473B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 73 + 400)
                + bytes(((73 * 13) % 251) for _ in range(73))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0074_typed() -> None:
    """unknown chunk size=74 declaring 474B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 74 + 400)
                + bytes(((74 * 13) % 251) for _ in range(74))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0075_typed() -> None:
    """unknown chunk size=75 declaring 475B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 75 + 400)
                + bytes(((75 * 13) % 251) for _ in range(75))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0076_typed() -> None:
    """unknown chunk size=76 declaring 476B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 76 + 400)
                + bytes(((76 * 13) % 251) for _ in range(76))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0077_typed() -> None:
    """unknown chunk size=77 declaring 477B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 77 + 400)
                + bytes(((77 * 13) % 251) for _ in range(77))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0078_typed() -> None:
    """unknown chunk size=78 declaring 478B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 78 + 400)
                + bytes(((78 * 13) % 251) for _ in range(78))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0079_typed() -> None:
    """unknown chunk size=79 declaring 479B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 79 + 400)
                + bytes(((79 * 13) % 251) for _ in range(79))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0080_typed() -> None:
    """unknown chunk size=80 declaring 480B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 80 + 400)
                + bytes(((80 * 13) % 251) for _ in range(80))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0081_typed() -> None:
    """unknown chunk size=81 declaring 481B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 81 + 400)
                + bytes(((81 * 13) % 251) for _ in range(81))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0082_typed() -> None:
    """unknown chunk size=82 declaring 482B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 82 + 400)
                + bytes(((82 * 13) % 251) for _ in range(82))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0083_typed() -> None:
    """unknown chunk size=83 declaring 483B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 83 + 400)
                + bytes(((83 * 13) % 251) for _ in range(83))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0084_typed() -> None:
    """unknown chunk size=84 declaring 484B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 84 + 400)
                + bytes(((84 * 13) % 251) for _ in range(84))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0085_typed() -> None:
    """unknown chunk size=85 declaring 485B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 85 + 400)
                + bytes(((85 * 13) % 251) for _ in range(85))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0086_typed() -> None:
    """unknown chunk size=86 declaring 486B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 86 + 400)
                + bytes(((86 * 13) % 251) for _ in range(86))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0087_typed() -> None:
    """unknown chunk size=87 declaring 487B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 87 + 400)
                + bytes(((87 * 13) % 251) for _ in range(87))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0088_typed() -> None:
    """unknown chunk size=88 declaring 488B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 88 + 400)
                + bytes(((88 * 13) % 251) for _ in range(88))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0089_typed() -> None:
    """unknown chunk size=89 declaring 489B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 89 + 400)
                + bytes(((89 * 13) % 251) for _ in range(89))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0090_typed() -> None:
    """unknown chunk size=90 declaring 490B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 90 + 400)
                + bytes(((90 * 13) % 251) for _ in range(90))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0091_typed() -> None:
    """unknown chunk size=91 declaring 491B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 91 + 400)
                + bytes(((91 * 13) % 251) for _ in range(91))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0092_typed() -> None:
    """unknown chunk size=92 declaring 492B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 92 + 400)
                + bytes(((92 * 13) % 251) for _ in range(92))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0093_typed() -> None:
    """unknown chunk size=93 declaring 493B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 93 + 400)
                + bytes(((93 * 13) % 251) for _ in range(93))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0094_typed() -> None:
    """unknown chunk size=94 declaring 494B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 94 + 400)
                + bytes(((94 * 13) % 251) for _ in range(94))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0095_typed() -> None:
    """unknown chunk size=95 declaring 495B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 95 + 400)
                + bytes(((95 * 13) % 251) for _ in range(95))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0096_typed() -> None:
    """unknown chunk size=96 declaring 496B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 96 + 400)
                + bytes(((96 * 13) % 251) for _ in range(96))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0097_typed() -> None:
    """unknown chunk size=97 declaring 497B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 97 + 400)
                + bytes(((97 * 13) % 251) for _ in range(97))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0098_typed() -> None:
    """unknown chunk size=98 declaring 498B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 98 + 400)
                + bytes(((98 * 13) % 251) for _ in range(98))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0099_typed() -> None:
    """unknown chunk size=99 declaring 499B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 99 + 400)
                + bytes(((99 * 13) % 251) for _ in range(99))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0100_typed() -> None:
    """unknown chunk size=100 declaring 500B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 100 + 400)
                + bytes(((100 * 13) % 251) for _ in range(100))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0101_typed() -> None:
    """unknown chunk size=101 declaring 501B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 101 + 400)
                + bytes(((101 * 13) % 251) for _ in range(101))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0102_typed() -> None:
    """unknown chunk size=102 declaring 502B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 102 + 400)
                + bytes(((102 * 13) % 251) for _ in range(102))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0103_typed() -> None:
    """unknown chunk size=103 declaring 503B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 103 + 400)
                + bytes(((103 * 13) % 251) for _ in range(103))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0104_typed() -> None:
    """unknown chunk size=104 declaring 504B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 104 + 400)
                + bytes(((104 * 13) % 251) for _ in range(104))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0105_typed() -> None:
    """unknown chunk size=105 declaring 505B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 105 + 400)
                + bytes(((105 * 13) % 251) for _ in range(105))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0106_typed() -> None:
    """unknown chunk size=106 declaring 506B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 106 + 400)
                + bytes(((106 * 13) % 251) for _ in range(106))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0107_typed() -> None:
    """unknown chunk size=107 declaring 507B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 107 + 400)
                + bytes(((107 * 13) % 251) for _ in range(107))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0108_typed() -> None:
    """unknown chunk size=108 declaring 508B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 108 + 400)
                + bytes(((108 * 13) % 251) for _ in range(108))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0109_typed() -> None:
    """unknown chunk size=109 declaring 509B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 109 + 400)
                + bytes(((109 * 13) % 251) for _ in range(109))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0110_typed() -> None:
    """unknown chunk size=110 declaring 510B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 110 + 400)
                + bytes(((110 * 13) % 251) for _ in range(110))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0111_typed() -> None:
    """unknown chunk size=111 declaring 511B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 111 + 400)
                + bytes(((111 * 13) % 251) for _ in range(111))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0112_typed() -> None:
    """unknown chunk size=112 declaring 512B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 112 + 400)
                + bytes(((112 * 13) % 251) for _ in range(112))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0113_typed() -> None:
    """unknown chunk size=113 declaring 513B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 113 + 400)
                + bytes(((113 * 13) % 251) for _ in range(113))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0114_typed() -> None:
    """unknown chunk size=114 declaring 514B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 114 + 400)
                + bytes(((114 * 13) % 251) for _ in range(114))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0115_typed() -> None:
    """unknown chunk size=115 declaring 515B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 115 + 400)
                + bytes(((115 * 13) % 251) for _ in range(115))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0116_typed() -> None:
    """unknown chunk size=116 declaring 516B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 116 + 400)
                + bytes(((116 * 13) % 251) for _ in range(116))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0117_typed() -> None:
    """unknown chunk size=117 declaring 517B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 117 + 400)
                + bytes(((117 * 13) % 251) for _ in range(117))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0118_typed() -> None:
    """unknown chunk size=118 declaring 518B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 118 + 400)
                + bytes(((118 * 13) % 251) for _ in range(118))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0119_typed() -> None:
    """unknown chunk size=119 declaring 519B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 119 + 400)
                + bytes(((119 * 13) % 251) for _ in range(119))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0120_typed() -> None:
    """unknown chunk size=120 declaring 520B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 120 + 400)
                + bytes(((120 * 13) % 251) for _ in range(120))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0121_typed() -> None:
    """unknown chunk size=121 declaring 521B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 121 + 400)
                + bytes(((121 * 13) % 251) for _ in range(121))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0122_typed() -> None:
    """unknown chunk size=122 declaring 522B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 122 + 400)
                + bytes(((122 * 13) % 251) for _ in range(122))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0123_typed() -> None:
    """unknown chunk size=123 declaring 523B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 123 + 400)
                + bytes(((123 * 13) % 251) for _ in range(123))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0124_typed() -> None:
    """unknown chunk size=124 declaring 524B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 124 + 400)
                + bytes(((124 * 13) % 251) for _ in range(124))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0125_typed() -> None:
    """unknown chunk size=125 declaring 525B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 125 + 400)
                + bytes(((125 * 13) % 251) for _ in range(125))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0126_typed() -> None:
    """unknown chunk size=126 declaring 526B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 126 + 400)
                + bytes(((126 * 13) % 251) for _ in range(126))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0127_typed() -> None:
    """unknown chunk size=127 declaring 527B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 127 + 400)
                + bytes(((127 * 13) % 251) for _ in range(127))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0128_typed() -> None:
    """unknown chunk size=128 declaring 528B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 128 + 400)
                + bytes(((128 * 13) % 251) for _ in range(128))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0129_typed() -> None:
    """unknown chunk size=129 declaring 529B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 129 + 400)
                + bytes(((129 * 13) % 251) for _ in range(129))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0130_typed() -> None:
    """unknown chunk size=130 declaring 530B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 130 + 400)
                + bytes(((130 * 13) % 251) for _ in range(130))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0131_typed() -> None:
    """unknown chunk size=131 declaring 531B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 131 + 400)
                + bytes(((131 * 13) % 251) for _ in range(131))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0132_typed() -> None:
    """unknown chunk size=132 declaring 532B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 132 + 400)
                + bytes(((132 * 13) % 251) for _ in range(132))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0133_typed() -> None:
    """unknown chunk size=133 declaring 533B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 133 + 400)
                + bytes(((133 * 13) % 251) for _ in range(133))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0134_typed() -> None:
    """unknown chunk size=134 declaring 534B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 134 + 400)
                + bytes(((134 * 13) % 251) for _ in range(134))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0135_typed() -> None:
    """unknown chunk size=135 declaring 535B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 135 + 400)
                + bytes(((135 * 13) % 251) for _ in range(135))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0136_typed() -> None:
    """unknown chunk size=136 declaring 536B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 136 + 400)
                + bytes(((136 * 13) % 251) for _ in range(136))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0137_typed() -> None:
    """unknown chunk size=137 declaring 537B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 137 + 400)
                + bytes(((137 * 13) % 251) for _ in range(137))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0138_typed() -> None:
    """unknown chunk size=138 declaring 538B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 138 + 400)
                + bytes(((138 * 13) % 251) for _ in range(138))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0139_typed() -> None:
    """unknown chunk size=139 declaring 539B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 139 + 400)
                + bytes(((139 * 13) % 251) for _ in range(139))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0140_typed() -> None:
    """unknown chunk size=140 declaring 540B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 140 + 400)
                + bytes(((140 * 13) % 251) for _ in range(140))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0141_typed() -> None:
    """unknown chunk size=141 declaring 541B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 141 + 400)
                + bytes(((141 * 13) % 251) for _ in range(141))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0142_typed() -> None:
    """unknown chunk size=142 declaring 542B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 142 + 400)
                + bytes(((142 * 13) % 251) for _ in range(142))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0143_typed() -> None:
    """unknown chunk size=143 declaring 543B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 143 + 400)
                + bytes(((143 * 13) % 251) for _ in range(143))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0144_typed() -> None:
    """unknown chunk size=144 declaring 544B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 144 + 400)
                + bytes(((144 * 13) % 251) for _ in range(144))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0145_typed() -> None:
    """unknown chunk size=145 declaring 545B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 145 + 400)
                + bytes(((145 * 13) % 251) for _ in range(145))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0146_typed() -> None:
    """unknown chunk size=146 declaring 546B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 146 + 400)
                + bytes(((146 * 13) % 251) for _ in range(146))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0147_typed() -> None:
    """unknown chunk size=147 declaring 547B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 147 + 400)
                + bytes(((147 * 13) % 251) for _ in range(147))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0148_typed() -> None:
    """unknown chunk size=148 declaring 548B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 148 + 400)
                + bytes(((148 * 13) % 251) for _ in range(148))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0149_typed() -> None:
    """unknown chunk size=149 declaring 549B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 149 + 400)
                + bytes(((149 * 13) % 251) for _ in range(149))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0150_typed() -> None:
    """unknown chunk size=150 declaring 550B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 150 + 400)
                + bytes(((150 * 13) % 251) for _ in range(150))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0151_typed() -> None:
    """unknown chunk size=151 declaring 551B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 151 + 400)
                + bytes(((151 * 13) % 251) for _ in range(151))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0152_typed() -> None:
    """unknown chunk size=152 declaring 552B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 152 + 400)
                + bytes(((152 * 13) % 251) for _ in range(152))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0153_typed() -> None:
    """unknown chunk size=153 declaring 553B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 153 + 400)
                + bytes(((153 * 13) % 251) for _ in range(153))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0154_typed() -> None:
    """unknown chunk size=154 declaring 554B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 154 + 400)
                + bytes(((154 * 13) % 251) for _ in range(154))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0155_typed() -> None:
    """unknown chunk size=155 declaring 555B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 155 + 400)
                + bytes(((155 * 13) % 251) for _ in range(155))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0156_typed() -> None:
    """unknown chunk size=156 declaring 556B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 156 + 400)
                + bytes(((156 * 13) % 251) for _ in range(156))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0157_typed() -> None:
    """unknown chunk size=157 declaring 557B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 157 + 400)
                + bytes(((157 * 13) % 251) for _ in range(157))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0158_typed() -> None:
    """unknown chunk size=158 declaring 558B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 158 + 400)
                + bytes(((158 * 13) % 251) for _ in range(158))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0159_typed() -> None:
    """unknown chunk size=159 declaring 559B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 159 + 400)
                + bytes(((159 * 13) % 251) for _ in range(159))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0160_typed() -> None:
    """unknown chunk size=160 declaring 560B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 160 + 400)
                + bytes(((160 * 13) % 251) for _ in range(160))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0161_typed() -> None:
    """unknown chunk size=161 declaring 561B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 161 + 400)
                + bytes(((161 * 13) % 251) for _ in range(161))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0162_typed() -> None:
    """unknown chunk size=162 declaring 562B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 162 + 400)
                + bytes(((162 * 13) % 251) for _ in range(162))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0163_typed() -> None:
    """unknown chunk size=163 declaring 563B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 163 + 400)
                + bytes(((163 * 13) % 251) for _ in range(163))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0164_typed() -> None:
    """unknown chunk size=164 declaring 564B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 164 + 400)
                + bytes(((164 * 13) % 251) for _ in range(164))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0165_typed() -> None:
    """unknown chunk size=165 declaring 565B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 165 + 400)
                + bytes(((165 * 13) % 251) for _ in range(165))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0166_typed() -> None:
    """unknown chunk size=166 declaring 566B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 166 + 400)
                + bytes(((166 * 13) % 251) for _ in range(166))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0167_typed() -> None:
    """unknown chunk size=167 declaring 567B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 167 + 400)
                + bytes(((167 * 13) % 251) for _ in range(167))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0168_typed() -> None:
    """unknown chunk size=168 declaring 568B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 168 + 400)
                + bytes(((168 * 13) % 251) for _ in range(168))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0169_typed() -> None:
    """unknown chunk size=169 declaring 569B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 169 + 400)
                + bytes(((169 * 13) % 251) for _ in range(169))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0170_typed() -> None:
    """unknown chunk size=170 declaring 570B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 170 + 400)
                + bytes(((170 * 13) % 251) for _ in range(170))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0171_typed() -> None:
    """unknown chunk size=171 declaring 571B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 171 + 400)
                + bytes(((171 * 13) % 251) for _ in range(171))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0172_typed() -> None:
    """unknown chunk size=172 declaring 572B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 172 + 400)
                + bytes(((172 * 13) % 251) for _ in range(172))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0173_typed() -> None:
    """unknown chunk size=173 declaring 573B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 173 + 400)
                + bytes(((173 * 13) % 251) for _ in range(173))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0174_typed() -> None:
    """unknown chunk size=174 declaring 574B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 174 + 400)
                + bytes(((174 * 13) % 251) for _ in range(174))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0175_typed() -> None:
    """unknown chunk size=175 declaring 575B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 175 + 400)
                + bytes(((175 * 13) % 251) for _ in range(175))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0176_typed() -> None:
    """unknown chunk size=176 declaring 576B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 176 + 400)
                + bytes(((176 * 13) % 251) for _ in range(176))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0177_typed() -> None:
    """unknown chunk size=177 declaring 577B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 177 + 400)
                + bytes(((177 * 13) % 251) for _ in range(177))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0178_typed() -> None:
    """unknown chunk size=178 declaring 578B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 178 + 400)
                + bytes(((178 * 13) % 251) for _ in range(178))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0179_typed() -> None:
    """unknown chunk size=179 declaring 579B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 179 + 400)
                + bytes(((179 * 13) % 251) for _ in range(179))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0180_typed() -> None:
    """unknown chunk size=180 declaring 580B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 180 + 400)
                + bytes(((180 * 13) % 251) for _ in range(180))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0181_typed() -> None:
    """unknown chunk size=181 declaring 581B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 181 + 400)
                + bytes(((181 * 13) % 251) for _ in range(181))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0182_typed() -> None:
    """unknown chunk size=182 declaring 582B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 182 + 400)
                + bytes(((182 * 13) % 251) for _ in range(182))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0183_typed() -> None:
    """unknown chunk size=183 declaring 583B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 183 + 400)
                + bytes(((183 * 13) % 251) for _ in range(183))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0184_typed() -> None:
    """unknown chunk size=184 declaring 584B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 184 + 400)
                + bytes(((184 * 13) % 251) for _ in range(184))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0185_typed() -> None:
    """unknown chunk size=185 declaring 585B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 185 + 400)
                + bytes(((185 * 13) % 251) for _ in range(185))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0186_typed() -> None:
    """unknown chunk size=186 declaring 586B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 186 + 400)
                + bytes(((186 * 13) % 251) for _ in range(186))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0187_typed() -> None:
    """unknown chunk size=187 declaring 587B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 187 + 400)
                + bytes(((187 * 13) % 251) for _ in range(187))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0188_typed() -> None:
    """unknown chunk size=188 declaring 588B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 188 + 400)
                + bytes(((188 * 13) % 251) for _ in range(188))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0189_typed() -> None:
    """unknown chunk size=189 declaring 589B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 189 + 400)
                + bytes(((189 * 13) % 251) for _ in range(189))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0190_typed() -> None:
    """unknown chunk size=190 declaring 590B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 190 + 400)
                + bytes(((190 * 13) % 251) for _ in range(190))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0191_typed() -> None:
    """unknown chunk size=191 declaring 591B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 191 + 400)
                + bytes(((191 * 13) % 251) for _ in range(191))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0192_typed() -> None:
    """unknown chunk size=192 declaring 592B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 192 + 400)
                + bytes(((192 * 13) % 251) for _ in range(192))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0193_typed() -> None:
    """unknown chunk size=193 declaring 593B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 193 + 400)
                + bytes(((193 * 13) % 251) for _ in range(193))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0194_typed() -> None:
    """unknown chunk size=194 declaring 594B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 194 + 400)
                + bytes(((194 * 13) % 251) for _ in range(194))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0195_typed() -> None:
    """unknown chunk size=195 declaring 595B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 195 + 400)
                + bytes(((195 * 13) % 251) for _ in range(195))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0196_typed() -> None:
    """unknown chunk size=196 declaring 596B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 196 + 400)
                + bytes(((196 * 13) % 251) for _ in range(196))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0197_typed() -> None:
    """unknown chunk size=197 declaring 597B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 197 + 400)
                + bytes(((197 * 13) % 251) for _ in range(197))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0198_typed() -> None:
    """unknown chunk size=198 declaring 598B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 198 + 400)
                + bytes(((198 * 13) % 251) for _ in range(198))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0199_typed() -> None:
    """unknown chunk size=199 declaring 599B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 199 + 400)
                + bytes(((199 * 13) % 251) for _ in range(199))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0200_typed() -> None:
    """unknown chunk size=200 declaring 600B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 200 + 400)
                + bytes(((200 * 13) % 251) for _ in range(200))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0201_typed() -> None:
    """unknown chunk size=201 declaring 601B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 201 + 400)
                + bytes(((201 * 13) % 251) for _ in range(201))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0202_typed() -> None:
    """unknown chunk size=202 declaring 602B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 202 + 400)
                + bytes(((202 * 13) % 251) for _ in range(202))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0203_typed() -> None:
    """unknown chunk size=203 declaring 603B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 203 + 400)
                + bytes(((203 * 13) % 251) for _ in range(203))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0204_typed() -> None:
    """unknown chunk size=204 declaring 604B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 204 + 400)
                + bytes(((204 * 13) % 251) for _ in range(204))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0205_typed() -> None:
    """unknown chunk size=205 declaring 605B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 205 + 400)
                + bytes(((205 * 13) % 251) for _ in range(205))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0206_typed() -> None:
    """unknown chunk size=206 declaring 606B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 206 + 400)
                + bytes(((206 * 13) % 251) for _ in range(206))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0207_typed() -> None:
    """unknown chunk size=207 declaring 607B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 207 + 400)
                + bytes(((207 * 13) % 251) for _ in range(207))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0208_typed() -> None:
    """unknown chunk size=208 declaring 608B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 208 + 400)
                + bytes(((208 * 13) % 251) for _ in range(208))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0209_typed() -> None:
    """unknown chunk size=209 declaring 609B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 209 + 400)
                + bytes(((209 * 13) % 251) for _ in range(209))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0210_typed() -> None:
    """unknown chunk size=210 declaring 610B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 210 + 400)
                + bytes(((210 * 13) % 251) for _ in range(210))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0211_typed() -> None:
    """unknown chunk size=211 declaring 611B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 211 + 400)
                + bytes(((211 * 13) % 251) for _ in range(211))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0212_typed() -> None:
    """unknown chunk size=212 declaring 612B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 212 + 400)
                + bytes(((212 * 13) % 251) for _ in range(212))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0213_typed() -> None:
    """unknown chunk size=213 declaring 613B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 213 + 400)
                + bytes(((213 * 13) % 251) for _ in range(213))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0214_typed() -> None:
    """unknown chunk size=214 declaring 614B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 214 + 400)
                + bytes(((214 * 13) % 251) for _ in range(214))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0215_typed() -> None:
    """unknown chunk size=215 declaring 615B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 215 + 400)
                + bytes(((215 * 13) % 251) for _ in range(215))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0216_typed() -> None:
    """unknown chunk size=216 declaring 616B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 216 + 400)
                + bytes(((216 * 13) % 251) for _ in range(216))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0217_typed() -> None:
    """unknown chunk size=217 declaring 617B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 217 + 400)
                + bytes(((217 * 13) % 251) for _ in range(217))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0218_typed() -> None:
    """unknown chunk size=218 declaring 618B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 218 + 400)
                + bytes(((218 * 13) % 251) for _ in range(218))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0219_typed() -> None:
    """unknown chunk size=219 declaring 619B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 219 + 400)
                + bytes(((219 * 13) % 251) for _ in range(219))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0220_typed() -> None:
    """unknown chunk size=220 declaring 620B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 220 + 400)
                + bytes(((220 * 13) % 251) for _ in range(220))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0221_typed() -> None:
    """unknown chunk size=221 declaring 621B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 221 + 400)
                + bytes(((221 * 13) % 251) for _ in range(221))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0222_typed() -> None:
    """unknown chunk size=222 declaring 622B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 222 + 400)
                + bytes(((222 * 13) % 251) for _ in range(222))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0223_typed() -> None:
    """unknown chunk size=223 declaring 623B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 223 + 400)
                + bytes(((223 * 13) % 251) for _ in range(223))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0224_typed() -> None:
    """unknown chunk size=224 declaring 624B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 224 + 400)
                + bytes(((224 * 13) % 251) for _ in range(224))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0225_typed() -> None:
    """unknown chunk size=225 declaring 625B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 225 + 400)
                + bytes(((225 * 13) % 251) for _ in range(225))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0226_typed() -> None:
    """unknown chunk size=226 declaring 626B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 226 + 400)
                + bytes(((226 * 13) % 251) for _ in range(226))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0227_typed() -> None:
    """unknown chunk size=227 declaring 627B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 227 + 400)
                + bytes(((227 * 13) % 251) for _ in range(227))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0228_typed() -> None:
    """unknown chunk size=228 declaring 628B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 228 + 400)
                + bytes(((228 * 13) % 251) for _ in range(228))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0229_typed() -> None:
    """unknown chunk size=229 declaring 629B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 229 + 400)
                + bytes(((229 * 13) % 251) for _ in range(229))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0230_typed() -> None:
    """unknown chunk size=230 declaring 630B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 230 + 400)
                + bytes(((230 * 13) % 251) for _ in range(230))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0231_typed() -> None:
    """unknown chunk size=231 declaring 631B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 231 + 400)
                + bytes(((231 * 13) % 251) for _ in range(231))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0232_typed() -> None:
    """unknown chunk size=232 declaring 632B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 232 + 400)
                + bytes(((232 * 13) % 251) for _ in range(232))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0233_typed() -> None:
    """unknown chunk size=233 declaring 633B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 233 + 400)
                + bytes(((233 * 13) % 251) for _ in range(233))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0234_typed() -> None:
    """unknown chunk size=234 declaring 634B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 234 + 400)
                + bytes(((234 * 13) % 251) for _ in range(234))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0235_typed() -> None:
    """unknown chunk size=235 declaring 635B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 235 + 400)
                + bytes(((235 * 13) % 251) for _ in range(235))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0236_typed() -> None:
    """unknown chunk size=236 declaring 636B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 236 + 400)
                + bytes(((236 * 13) % 251) for _ in range(236))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0237_typed() -> None:
    """unknown chunk size=237 declaring 637B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 237 + 400)
                + bytes(((237 * 13) % 251) for _ in range(237))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0238_typed() -> None:
    """unknown chunk size=238 declaring 638B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 238 + 400)
                + bytes(((238 * 13) % 251) for _ in range(238))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0239_typed() -> None:
    """unknown chunk size=239 declaring 639B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 239 + 400)
                + bytes(((239 * 13) % 251) for _ in range(239))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0240_typed() -> None:
    """unknown chunk size=240 declaring 640B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 240 + 400)
                + bytes(((240 * 13) % 251) for _ in range(240))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0241_typed() -> None:
    """unknown chunk size=241 declaring 641B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 241 + 400)
                + bytes(((241 * 13) % 251) for _ in range(241))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0242_typed() -> None:
    """unknown chunk size=242 declaring 642B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 242 + 400)
                + bytes(((242 * 13) % 251) for _ in range(242))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0243_typed() -> None:
    """unknown chunk size=243 declaring 643B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 243 + 400)
                + bytes(((243 * 13) % 251) for _ in range(243))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0244_typed() -> None:
    """unknown chunk size=244 declaring 644B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 244 + 400)
                + bytes(((244 * 13) % 251) for _ in range(244))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0245_typed() -> None:
    """unknown chunk size=245 declaring 645B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 245 + 400)
                + bytes(((245 * 13) % 251) for _ in range(245))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0246_typed() -> None:
    """unknown chunk size=246 declaring 646B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 246 + 400)
                + bytes(((246 * 13) % 251) for _ in range(246))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0247_typed() -> None:
    """unknown chunk size=247 declaring 647B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 247 + 400)
                + bytes(((247 * 13) % 251) for _ in range(247))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0248_typed() -> None:
    """unknown chunk size=248 declaring 648B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 248 + 400)
                + bytes(((248 * 13) % 251) for _ in range(248))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0249_typed() -> None:
    """unknown chunk size=249 declaring 649B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 249 + 400)
                + bytes(((249 * 13) % 251) for _ in range(249))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0250_typed() -> None:
    """unknown chunk size=250 declaring 650B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 250 + 400)
                + bytes(((250 * 13) % 251) for _ in range(250))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0251_typed() -> None:
    """unknown chunk size=251 declaring 651B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 251 + 400)
                + bytes(((251 * 13) % 251) for _ in range(251))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0252_typed() -> None:
    """unknown chunk size=252 declaring 652B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 252 + 400)
                + bytes(((252 * 13) % 251) for _ in range(252))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0253_typed() -> None:
    """unknown chunk size=253 declaring 653B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 253 + 400)
                + bytes(((253 * 13) % 251) for _ in range(253))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0254_typed() -> None:
    """unknown chunk size=254 declaring 654B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 254 + 400)
                + bytes(((254 * 13) % 251) for _ in range(254))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0255_typed() -> None:
    """unknown chunk size=255 declaring 655B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 255 + 400)
                + bytes(((255 * 13) % 251) for _ in range(255))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0256_typed() -> None:
    """unknown chunk size=256 declaring 656B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 256 + 400)
                + bytes(((256 * 13) % 251) for _ in range(256))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0257_typed() -> None:
    """unknown chunk size=257 declaring 657B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 257 + 400)
                + bytes(((257 * 13) % 251) for _ in range(257))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0258_typed() -> None:
    """unknown chunk size=258 declaring 658B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 258 + 400)
                + bytes(((258 * 13) % 251) for _ in range(258))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0259_typed() -> None:
    """unknown chunk size=259 declaring 659B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 259 + 400)
                + bytes(((259 * 13) % 251) for _ in range(259))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0260_typed() -> None:
    """unknown chunk size=260 declaring 660B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 260 + 400)
                + bytes(((260 * 13) % 251) for _ in range(260))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0261_typed() -> None:
    """unknown chunk size=261 declaring 661B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 261 + 400)
                + bytes(((261 * 13) % 251) for _ in range(261))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0262_typed() -> None:
    """unknown chunk size=262 declaring 662B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 262 + 400)
                + bytes(((262 * 13) % 251) for _ in range(262))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0263_typed() -> None:
    """unknown chunk size=263 declaring 663B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 263 + 400)
                + bytes(((263 * 13) % 251) for _ in range(263))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0264_typed() -> None:
    """unknown chunk size=264 declaring 664B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 264 + 400)
                + bytes(((264 * 13) % 251) for _ in range(264))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0265_typed() -> None:
    """unknown chunk size=265 declaring 665B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 265 + 400)
                + bytes(((265 * 13) % 251) for _ in range(265))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0266_typed() -> None:
    """unknown chunk size=266 declaring 666B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 266 + 400)
                + bytes(((266 * 13) % 251) for _ in range(266))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0267_typed() -> None:
    """unknown chunk size=267 declaring 667B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 267 + 400)
                + bytes(((267 * 13) % 251) for _ in range(267))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0268_typed() -> None:
    """unknown chunk size=268 declaring 668B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 268 + 400)
                + bytes(((268 * 13) % 251) for _ in range(268))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0269_typed() -> None:
    """unknown chunk size=269 declaring 669B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 269 + 400)
                + bytes(((269 * 13) % 251) for _ in range(269))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0270_typed() -> None:
    """unknown chunk size=270 declaring 670B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 270 + 400)
                + bytes(((270 * 13) % 251) for _ in range(270))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0271_typed() -> None:
    """unknown chunk size=271 declaring 671B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 271 + 400)
                + bytes(((271 * 13) % 251) for _ in range(271))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0272_typed() -> None:
    """unknown chunk size=272 declaring 672B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 272 + 400)
                + bytes(((272 * 13) % 251) for _ in range(272))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0273_typed() -> None:
    """unknown chunk size=273 declaring 673B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 273 + 400)
                + bytes(((273 * 13) % 251) for _ in range(273))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0274_typed() -> None:
    """unknown chunk size=274 declaring 674B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 274 + 400)
                + bytes(((274 * 13) % 251) for _ in range(274))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0275_typed() -> None:
    """unknown chunk size=275 declaring 675B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 275 + 400)
                + bytes(((275 * 13) % 251) for _ in range(275))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0276_typed() -> None:
    """unknown chunk size=276 declaring 676B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 276 + 400)
                + bytes(((276 * 13) % 251) for _ in range(276))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0277_typed() -> None:
    """unknown chunk size=277 declaring 677B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 277 + 400)
                + bytes(((277 * 13) % 251) for _ in range(277))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0278_typed() -> None:
    """unknown chunk size=278 declaring 678B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 278 + 400)
                + bytes(((278 * 13) % 251) for _ in range(278))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0279_typed() -> None:
    """unknown chunk size=279 declaring 679B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 279 + 400)
                + bytes(((279 * 13) % 251) for _ in range(279))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0280_typed() -> None:
    """unknown chunk size=280 declaring 680B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 280 + 400)
                + bytes(((280 * 13) % 251) for _ in range(280))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0281_typed() -> None:
    """unknown chunk size=281 declaring 681B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 281 + 400)
                + bytes(((281 * 13) % 251) for _ in range(281))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0282_typed() -> None:
    """unknown chunk size=282 declaring 682B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 282 + 400)
                + bytes(((282 * 13) % 251) for _ in range(282))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0283_typed() -> None:
    """unknown chunk size=283 declaring 683B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 283 + 400)
                + bytes(((283 * 13) % 251) for _ in range(283))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0284_typed() -> None:
    """unknown chunk size=284 declaring 684B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 284 + 400)
                + bytes(((284 * 13) % 251) for _ in range(284))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0285_typed() -> None:
    """unknown chunk size=285 declaring 685B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 285 + 400)
                + bytes(((285 * 13) % 251) for _ in range(285))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0286_typed() -> None:
    """unknown chunk size=286 declaring 686B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 286 + 400)
                + bytes(((286 * 13) % 251) for _ in range(286))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0287_typed() -> None:
    """unknown chunk size=287 declaring 687B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 287 + 400)
                + bytes(((287 * 13) % 251) for _ in range(287))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0288_typed() -> None:
    """unknown chunk size=288 declaring 688B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 288 + 400)
                + bytes(((288 * 13) % 251) for _ in range(288))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0289_typed() -> None:
    """unknown chunk size=289 declaring 689B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 289 + 400)
                + bytes(((289 * 13) % 251) for _ in range(289))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0290_typed() -> None:
    """unknown chunk size=290 declaring 690B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 290 + 400)
                + bytes(((290 * 13) % 251) for _ in range(290))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0291_typed() -> None:
    """unknown chunk size=291 declaring 691B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 291 + 400)
                + bytes(((291 * 13) % 251) for _ in range(291))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0292_typed() -> None:
    """unknown chunk size=292 declaring 692B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 292 + 400)
                + bytes(((292 * 13) % 251) for _ in range(292))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0293_typed() -> None:
    """unknown chunk size=293 declaring 693B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 293 + 400)
                + bytes(((293 * 13) % 251) for _ in range(293))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0294_typed() -> None:
    """unknown chunk size=294 declaring 694B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 294 + 400)
                + bytes(((294 * 13) % 251) for _ in range(294))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0295_typed() -> None:
    """unknown chunk size=295 declaring 695B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 295 + 400)
                + bytes(((295 * 13) % 251) for _ in range(295))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0296_typed() -> None:
    """unknown chunk size=296 declaring 696B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 296 + 400)
                + bytes(((296 * 13) % 251) for _ in range(296))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0297_typed() -> None:
    """unknown chunk size=297 declaring 697B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 297 + 400)
                + bytes(((297 * 13) % 251) for _ in range(297))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0298_typed() -> None:
    """unknown chunk size=298 declaring 698B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 298 + 400)
                + bytes(((298 * 13) % 251) for _ in range(298))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0299_typed() -> None:
    """unknown chunk size=299 declaring 699B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 299 + 400)
                + bytes(((299 * 13) % 251) for _ in range(299))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0300_typed() -> None:
    """unknown chunk size=300 declaring 700B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 300 + 400)
                + bytes(((300 * 13) % 251) for _ in range(300))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0301_typed() -> None:
    """unknown chunk size=301 declaring 701B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 301 + 400)
                + bytes(((301 * 13) % 251) for _ in range(301))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0302_typed() -> None:
    """unknown chunk size=302 declaring 702B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 302 + 400)
                + bytes(((302 * 13) % 251) for _ in range(302))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0303_typed() -> None:
    """unknown chunk size=303 declaring 703B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 303 + 400)
                + bytes(((303 * 13) % 251) for _ in range(303))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0304_typed() -> None:
    """unknown chunk size=304 declaring 704B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 304 + 400)
                + bytes(((304 * 13) % 251) for _ in range(304))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0305_typed() -> None:
    """unknown chunk size=305 declaring 705B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 305 + 400)
                + bytes(((305 * 13) % 251) for _ in range(305))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0306_typed() -> None:
    """unknown chunk size=306 declaring 706B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 306 + 400)
                + bytes(((306 * 13) % 251) for _ in range(306))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0307_typed() -> None:
    """unknown chunk size=307 declaring 707B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 307 + 400)
                + bytes(((307 * 13) % 251) for _ in range(307))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0308_typed() -> None:
    """unknown chunk size=308 declaring 708B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 308 + 400)
                + bytes(((308 * 13) % 251) for _ in range(308))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0309_typed() -> None:
    """unknown chunk size=309 declaring 709B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 309 + 400)
                + bytes(((309 * 13) % 251) for _ in range(309))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0310_typed() -> None:
    """unknown chunk size=310 declaring 710B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 310 + 400)
                + bytes(((310 * 13) % 251) for _ in range(310))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0311_typed() -> None:
    """unknown chunk size=311 declaring 711B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 311 + 400)
                + bytes(((311 * 13) % 251) for _ in range(311))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0312_typed() -> None:
    """unknown chunk size=312 declaring 712B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 312 + 400)
                + bytes(((312 * 13) % 251) for _ in range(312))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0313_typed() -> None:
    """unknown chunk size=313 declaring 713B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 313 + 400)
                + bytes(((313 * 13) % 251) for _ in range(313))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0314_typed() -> None:
    """unknown chunk size=314 declaring 714B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 314 + 400)
                + bytes(((314 * 13) % 251) for _ in range(314))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0315_typed() -> None:
    """unknown chunk size=315 declaring 715B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 315 + 400)
                + bytes(((315 * 13) % 251) for _ in range(315))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0316_typed() -> None:
    """unknown chunk size=316 declaring 716B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 316 + 400)
                + bytes(((316 * 13) % 251) for _ in range(316))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0317_typed() -> None:
    """unknown chunk size=317 declaring 717B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 317 + 400)
                + bytes(((317 * 13) % 251) for _ in range(317))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0318_typed() -> None:
    """unknown chunk size=318 declaring 718B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 318 + 400)
                + bytes(((318 * 13) % 251) for _ in range(318))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0319_typed() -> None:
    """unknown chunk size=319 declaring 719B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 319 + 400)
                + bytes(((319 * 13) % 251) for _ in range(319))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0320_typed() -> None:
    """unknown chunk size=320 declaring 720B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 320 + 400)
                + bytes(((320 * 13) % 251) for _ in range(320))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0321_typed() -> None:
    """unknown chunk size=321 declaring 721B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 321 + 400)
                + bytes(((321 * 13) % 251) for _ in range(321))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0322_typed() -> None:
    """unknown chunk size=322 declaring 722B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 322 + 400)
                + bytes(((322 * 13) % 251) for _ in range(322))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0323_typed() -> None:
    """unknown chunk size=323 declaring 723B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 323 + 400)
                + bytes(((323 * 13) % 251) for _ in range(323))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0324_typed() -> None:
    """unknown chunk size=324 declaring 724B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 324 + 400)
                + bytes(((324 * 13) % 251) for _ in range(324))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0325_typed() -> None:
    """unknown chunk size=325 declaring 725B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 325 + 400)
                + bytes(((325 * 13) % 251) for _ in range(325))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0326_typed() -> None:
    """unknown chunk size=326 declaring 726B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 326 + 400)
                + bytes(((326 * 13) % 251) for _ in range(326))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0327_typed() -> None:
    """unknown chunk size=327 declaring 727B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 327 + 400)
                + bytes(((327 * 13) % 251) for _ in range(327))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0328_typed() -> None:
    """unknown chunk size=328 declaring 728B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 328 + 400)
                + bytes(((328 * 13) % 251) for _ in range(328))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0329_typed() -> None:
    """unknown chunk size=329 declaring 729B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 329 + 400)
                + bytes(((329 * 13) % 251) for _ in range(329))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0330_typed() -> None:
    """unknown chunk size=330 declaring 730B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 330 + 400)
                + bytes(((330 * 13) % 251) for _ in range(330))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0331_typed() -> None:
    """unknown chunk size=331 declaring 731B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 331 + 400)
                + bytes(((331 * 13) % 251) for _ in range(331))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0332_typed() -> None:
    """unknown chunk size=332 declaring 732B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 332 + 400)
                + bytes(((332 * 13) % 251) for _ in range(332))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0333_typed() -> None:
    """unknown chunk size=333 declaring 733B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 333 + 400)
                + bytes(((333 * 13) % 251) for _ in range(333))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0334_typed() -> None:
    """unknown chunk size=334 declaring 734B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 334 + 400)
                + bytes(((334 * 13) % 251) for _ in range(334))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0335_typed() -> None:
    """unknown chunk size=335 declaring 735B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 335 + 400)
                + bytes(((335 * 13) % 251) for _ in range(335))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0336_typed() -> None:
    """unknown chunk size=336 declaring 736B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 336 + 400)
                + bytes(((336 * 13) % 251) for _ in range(336))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0337_typed() -> None:
    """unknown chunk size=337 declaring 737B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 337 + 400)
                + bytes(((337 * 13) % 251) for _ in range(337))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0338_typed() -> None:
    """unknown chunk size=338 declaring 738B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 338 + 400)
                + bytes(((338 * 13) % 251) for _ in range(338))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0339_typed() -> None:
    """unknown chunk size=339 declaring 739B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 339 + 400)
                + bytes(((339 * 13) % 251) for _ in range(339))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0340_typed() -> None:
    """unknown chunk size=340 declaring 740B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 340 + 400)
                + bytes(((340 * 13) % 251) for _ in range(340))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0341_typed() -> None:
    """unknown chunk size=341 declaring 741B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 341 + 400)
                + bytes(((341 * 13) % 251) for _ in range(341))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0342_typed() -> None:
    """unknown chunk size=342 declaring 742B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 342 + 400)
                + bytes(((342 * 13) % 251) for _ in range(342))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0343_typed() -> None:
    """unknown chunk size=343 declaring 743B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 343 + 400)
                + bytes(((343 * 13) % 251) for _ in range(343))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0344_typed() -> None:
    """unknown chunk size=344 declaring 744B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 344 + 400)
                + bytes(((344 * 13) % 251) for _ in range(344))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0345_typed() -> None:
    """unknown chunk size=345 declaring 745B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 345 + 400)
                + bytes(((345 * 13) % 251) for _ in range(345))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0346_typed() -> None:
    """unknown chunk size=346 declaring 746B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 346 + 400)
                + bytes(((346 * 13) % 251) for _ in range(346))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0347_typed() -> None:
    """unknown chunk size=347 declaring 747B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 347 + 400)
                + bytes(((347 * 13) % 251) for _ in range(347))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0348_typed() -> None:
    """unknown chunk size=348 declaring 748B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 348 + 400)
                + bytes(((348 * 13) % 251) for _ in range(348))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0349_typed() -> None:
    """unknown chunk size=349 declaring 749B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 349 + 400)
                + bytes(((349 * 13) % 251) for _ in range(349))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0350_typed() -> None:
    """unknown chunk size=350 declaring 750B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 350 + 400)
                + bytes(((350 * 13) % 251) for _ in range(350))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0351_typed() -> None:
    """unknown chunk size=351 declaring 751B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 351 + 400)
                + bytes(((351 * 13) % 251) for _ in range(351))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0352_typed() -> None:
    """unknown chunk size=352 declaring 752B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 352 + 400)
                + bytes(((352 * 13) % 251) for _ in range(352))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0353_typed() -> None:
    """unknown chunk size=353 declaring 753B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 353 + 400)
                + bytes(((353 * 13) % 251) for _ in range(353))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0354_typed() -> None:
    """unknown chunk size=354 declaring 754B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 354 + 400)
                + bytes(((354 * 13) % 251) for _ in range(354))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0355_typed() -> None:
    """unknown chunk size=355 declaring 755B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 355 + 400)
                + bytes(((355 * 13) % 251) for _ in range(355))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0356_typed() -> None:
    """unknown chunk size=356 declaring 756B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 356 + 400)
                + bytes(((356 * 13) % 251) for _ in range(356))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0357_typed() -> None:
    """unknown chunk size=357 declaring 757B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 357 + 400)
                + bytes(((357 * 13) % 251) for _ in range(357))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0358_typed() -> None:
    """unknown chunk size=358 declaring 758B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 358 + 400)
                + bytes(((358 * 13) % 251) for _ in range(358))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0359_typed() -> None:
    """unknown chunk size=359 declaring 759B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 359 + 400)
                + bytes(((359 * 13) % 251) for _ in range(359))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0360_typed() -> None:
    """unknown chunk size=360 declaring 760B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 360 + 400)
                + bytes(((360 * 13) % 251) for _ in range(360))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0361_typed() -> None:
    """unknown chunk size=361 declaring 761B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 361 + 400)
                + bytes(((361 * 13) % 251) for _ in range(361))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0362_typed() -> None:
    """unknown chunk size=362 declaring 762B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 362 + 400)
                + bytes(((362 * 13) % 251) for _ in range(362))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0363_typed() -> None:
    """unknown chunk size=363 declaring 763B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 363 + 400)
                + bytes(((363 * 13) % 251) for _ in range(363))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0364_typed() -> None:
    """unknown chunk size=364 declaring 764B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 364 + 400)
                + bytes(((364 * 13) % 251) for _ in range(364))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0365_typed() -> None:
    """unknown chunk size=365 declaring 765B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 365 + 400)
                + bytes(((365 * 13) % 251) for _ in range(365))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0366_typed() -> None:
    """unknown chunk size=366 declaring 766B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 366 + 400)
                + bytes(((366 * 13) % 251) for _ in range(366))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0367_typed() -> None:
    """unknown chunk size=367 declaring 767B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 367 + 400)
                + bytes(((367 * 13) % 251) for _ in range(367))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0368_typed() -> None:
    """unknown chunk size=368 declaring 768B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 368 + 400)
                + bytes(((368 * 13) % 251) for _ in range(368))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0369_typed() -> None:
    """unknown chunk size=369 declaring 769B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 369 + 400)
                + bytes(((369 * 13) % 251) for _ in range(369))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0370_typed() -> None:
    """unknown chunk size=370 declaring 770B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 370 + 400)
                + bytes(((370 * 13) % 251) for _ in range(370))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0371_typed() -> None:
    """unknown chunk size=371 declaring 771B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 371 + 400)
                + bytes(((371 * 13) % 251) for _ in range(371))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0372_typed() -> None:
    """unknown chunk size=372 declaring 772B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 372 + 400)
                + bytes(((372 * 13) % 251) for _ in range(372))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0373_typed() -> None:
    """unknown chunk size=373 declaring 773B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 373 + 400)
                + bytes(((373 * 13) % 251) for _ in range(373))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0374_typed() -> None:
    """unknown chunk size=374 declaring 774B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 374 + 400)
                + bytes(((374 * 13) % 251) for _ in range(374))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0375_typed() -> None:
    """unknown chunk size=375 declaring 775B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 375 + 400)
                + bytes(((375 * 13) % 251) for _ in range(375))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0376_typed() -> None:
    """unknown chunk size=376 declaring 776B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 376 + 400)
                + bytes(((376 * 13) % 251) for _ in range(376))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0377_typed() -> None:
    """unknown chunk size=377 declaring 777B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 377 + 400)
                + bytes(((377 * 13) % 251) for _ in range(377))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0378_typed() -> None:
    """unknown chunk size=378 declaring 778B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 378 + 400)
                + bytes(((378 * 13) % 251) for _ in range(378))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0379_typed() -> None:
    """unknown chunk size=379 declaring 779B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 379 + 400)
                + bytes(((379 * 13) % 251) for _ in range(379))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0380_typed() -> None:
    """unknown chunk size=380 declaring 780B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 380 + 400)
                + bytes(((380 * 13) % 251) for _ in range(380))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0381_typed() -> None:
    """unknown chunk size=381 declaring 781B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 381 + 400)
                + bytes(((381 * 13) % 251) for _ in range(381))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0382_typed() -> None:
    """unknown chunk size=382 declaring 782B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 382 + 400)
                + bytes(((382 * 13) % 251) for _ in range(382))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0383_typed() -> None:
    """unknown chunk size=383 declaring 783B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 383 + 400)
                + bytes(((383 * 13) % 251) for _ in range(383))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0384_typed() -> None:
    """unknown chunk size=384 declaring 784B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 384 + 400)
                + bytes(((384 * 13) % 251) for _ in range(384))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0385_typed() -> None:
    """unknown chunk size=385 declaring 785B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 385 + 400)
                + bytes(((385 * 13) % 251) for _ in range(385))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0386_typed() -> None:
    """unknown chunk size=386 declaring 786B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 386 + 400)
                + bytes(((386 * 13) % 251) for _ in range(386))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0387_typed() -> None:
    """unknown chunk size=387 declaring 787B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 387 + 400)
                + bytes(((387 * 13) % 251) for _ in range(387))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0388_typed() -> None:
    """unknown chunk size=388 declaring 788B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 388 + 400)
                + bytes(((388 * 13) % 251) for _ in range(388))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0389_typed() -> None:
    """unknown chunk size=389 declaring 789B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 389 + 400)
                + bytes(((389 * 13) % 251) for _ in range(389))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0390_typed() -> None:
    """unknown chunk size=390 declaring 790B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 390 + 400)
                + bytes(((390 * 13) % 251) for _ in range(390))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0391_typed() -> None:
    """unknown chunk size=391 declaring 791B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 391 + 400)
                + bytes(((391 * 13) % 251) for _ in range(391))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0392_typed() -> None:
    """unknown chunk size=392 declaring 792B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 392 + 400)
                + bytes(((392 * 13) % 251) for _ in range(392))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0393_typed() -> None:
    """unknown chunk size=393 declaring 793B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 393 + 400)
                + bytes(((393 * 13) % 251) for _ in range(393))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0394_typed() -> None:
    """unknown chunk size=394 declaring 794B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 394 + 400)
                + bytes(((394 * 13) % 251) for _ in range(394))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0395_typed() -> None:
    """unknown chunk size=395 declaring 795B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 395 + 400)
                + bytes(((395 * 13) % 251) for _ in range(395))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0396_typed() -> None:
    """unknown chunk size=396 declaring 796B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 396 + 400)
                + bytes(((396 * 13) % 251) for _ in range(396))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0397_typed() -> None:
    """unknown chunk size=397 declaring 797B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 397 + 400)
                + bytes(((397 * 13) % 251) for _ in range(397))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0398_typed() -> None:
    """unknown chunk size=398 declaring 798B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 398 + 400)
                + bytes(((398 * 13) % 251) for _ in range(398))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0399_typed() -> None:
    """unknown chunk size=399 declaring 799B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 399 + 400)
                + bytes(((399 * 13) % 251) for _ in range(399))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0400_typed() -> None:
    """unknown chunk size=400 declaring 800B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 400 + 400)
                + bytes(((400 * 13) % 251) for _ in range(400))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0401_typed() -> None:
    """unknown chunk size=401 declaring 801B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 401 + 400)
                + bytes(((401 * 13) % 251) for _ in range(401))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0402_typed() -> None:
    """unknown chunk size=402 declaring 802B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 402 + 400)
                + bytes(((402 * 13) % 251) for _ in range(402))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0403_typed() -> None:
    """unknown chunk size=403 declaring 803B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 403 + 400)
                + bytes(((403 * 13) % 251) for _ in range(403))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0404_typed() -> None:
    """unknown chunk size=404 declaring 804B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 404 + 400)
                + bytes(((404 * 13) % 251) for _ in range(404))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0405_typed() -> None:
    """unknown chunk size=405 declaring 805B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 405 + 400)
                + bytes(((405 * 13) % 251) for _ in range(405))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0406_typed() -> None:
    """unknown chunk size=406 declaring 806B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 406 + 400)
                + bytes(((406 * 13) % 251) for _ in range(406))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0407_typed() -> None:
    """unknown chunk size=407 declaring 807B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 407 + 400)
                + bytes(((407 * 13) % 251) for _ in range(407))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0408_typed() -> None:
    """unknown chunk size=408 declaring 808B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 408 + 400)
                + bytes(((408 * 13) % 251) for _ in range(408))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0409_typed() -> None:
    """unknown chunk size=409 declaring 809B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 409 + 400)
                + bytes(((409 * 13) % 251) for _ in range(409))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0410_typed() -> None:
    """unknown chunk size=410 declaring 810B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 410 + 400)
                + bytes(((410 * 13) % 251) for _ in range(410))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0411_typed() -> None:
    """unknown chunk size=411 declaring 811B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 411 + 400)
                + bytes(((411 * 13) % 251) for _ in range(411))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0412_typed() -> None:
    """unknown chunk size=412 declaring 812B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 412 + 400)
                + bytes(((412 * 13) % 251) for _ in range(412))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0413_typed() -> None:
    """unknown chunk size=413 declaring 813B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 413 + 400)
                + bytes(((413 * 13) % 251) for _ in range(413))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0414_typed() -> None:
    """unknown chunk size=414 declaring 814B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 414 + 400)
                + bytes(((414 * 13) % 251) for _ in range(414))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0415_typed() -> None:
    """unknown chunk size=415 declaring 815B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 415 + 400)
                + bytes(((415 * 13) % 251) for _ in range(415))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0416_typed() -> None:
    """unknown chunk size=416 declaring 816B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 416 + 400)
                + bytes(((416 * 13) % 251) for _ in range(416))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0417_typed() -> None:
    """unknown chunk size=417 declaring 817B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 417 + 400)
                + bytes(((417 * 13) % 251) for _ in range(417))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0418_typed() -> None:
    """unknown chunk size=418 declaring 818B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 418 + 400)
                + bytes(((418 * 13) % 251) for _ in range(418))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0419_typed() -> None:
    """unknown chunk size=419 declaring 819B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 419 + 400)
                + bytes(((419 * 13) % 251) for _ in range(419))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0420_typed() -> None:
    """unknown chunk size=420 declaring 820B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 420 + 400)
                + bytes(((420 * 13) % 251) for _ in range(420))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0421_typed() -> None:
    """unknown chunk size=421 declaring 821B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 421 + 400)
                + bytes(((421 * 13) % 251) for _ in range(421))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0422_typed() -> None:
    """unknown chunk size=422 declaring 822B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 422 + 400)
                + bytes(((422 * 13) % 251) for _ in range(422))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0423_typed() -> None:
    """unknown chunk size=423 declaring 823B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 423 + 400)
                + bytes(((423 * 13) % 251) for _ in range(423))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0424_typed() -> None:
    """unknown chunk size=424 declaring 824B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 424 + 400)
                + bytes(((424 * 13) % 251) for _ in range(424))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0425_typed() -> None:
    """unknown chunk size=425 declaring 825B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 425 + 400)
                + bytes(((425 * 13) % 251) for _ in range(425))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0426_typed() -> None:
    """unknown chunk size=426 declaring 826B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 426 + 400)
                + bytes(((426 * 13) % 251) for _ in range(426))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0427_typed() -> None:
    """unknown chunk size=427 declaring 827B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 427 + 400)
                + bytes(((427 * 13) % 251) for _ in range(427))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0428_typed() -> None:
    """unknown chunk size=428 declaring 828B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 428 + 400)
                + bytes(((428 * 13) % 251) for _ in range(428))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0429_typed() -> None:
    """unknown chunk size=429 declaring 829B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 429 + 400)
                + bytes(((429 * 13) % 251) for _ in range(429))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0430_typed() -> None:
    """unknown chunk size=430 declaring 830B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 430 + 400)
                + bytes(((430 * 13) % 251) for _ in range(430))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0431_typed() -> None:
    """unknown chunk size=431 declaring 831B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 431 + 400)
                + bytes(((431 * 13) % 251) for _ in range(431))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0432_typed() -> None:
    """unknown chunk size=432 declaring 832B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 432 + 400)
                + bytes(((432 * 13) % 251) for _ in range(432))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0433_typed() -> None:
    """unknown chunk size=433 declaring 833B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 433 + 400)
                + bytes(((433 * 13) % 251) for _ in range(433))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0434_typed() -> None:
    """unknown chunk size=434 declaring 834B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 434 + 400)
                + bytes(((434 * 13) % 251) for _ in range(434))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0435_typed() -> None:
    """unknown chunk size=435 declaring 835B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 435 + 400)
                + bytes(((435 * 13) % 251) for _ in range(435))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0436_typed() -> None:
    """unknown chunk size=436 declaring 836B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 436 + 400)
                + bytes(((436 * 13) % 251) for _ in range(436))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0437_typed() -> None:
    """unknown chunk size=437 declaring 837B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 437 + 400)
                + bytes(((437 * 13) % 251) for _ in range(437))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0438_typed() -> None:
    """unknown chunk size=438 declaring 838B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 438 + 400)
                + bytes(((438 * 13) % 251) for _ in range(438))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0439_typed() -> None:
    """unknown chunk size=439 declaring 839B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 439 + 400)
                + bytes(((439 * 13) % 251) for _ in range(439))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0440_typed() -> None:
    """unknown chunk size=440 declaring 840B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 440 + 400)
                + bytes(((440 * 13) % 251) for _ in range(440))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0441_typed() -> None:
    """unknown chunk size=441 declaring 841B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 441 + 400)
                + bytes(((441 * 13) % 251) for _ in range(441))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0442_typed() -> None:
    """unknown chunk size=442 declaring 842B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 442 + 400)
                + bytes(((442 * 13) % 251) for _ in range(442))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0443_typed() -> None:
    """unknown chunk size=443 declaring 843B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 443 + 400)
                + bytes(((443 * 13) % 251) for _ in range(443))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0444_typed() -> None:
    """unknown chunk size=444 declaring 844B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 444 + 400)
                + bytes(((444 * 13) % 251) for _ in range(444))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0445_typed() -> None:
    """unknown chunk size=445 declaring 845B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 445 + 400)
                + bytes(((445 * 13) % 251) for _ in range(445))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0446_typed() -> None:
    """unknown chunk size=446 declaring 846B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 446 + 400)
                + bytes(((446 * 13) % 251) for _ in range(446))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0447_typed() -> None:
    """unknown chunk size=447 declaring 847B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 447 + 400)
                + bytes(((447 * 13) % 251) for _ in range(447))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0448_typed() -> None:
    """unknown chunk size=448 declaring 848B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 448 + 400)
                + bytes(((448 * 13) % 251) for _ in range(448))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0449_typed() -> None:
    """unknown chunk size=449 declaring 849B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 449 + 400)
                + bytes(((449 * 13) % 251) for _ in range(449))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0450_typed() -> None:
    """unknown chunk size=450 declaring 850B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 450 + 400)
                + bytes(((450 * 13) % 251) for _ in range(450))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0451_typed() -> None:
    """unknown chunk size=451 declaring 851B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 451 + 400)
                + bytes(((451 * 13) % 251) for _ in range(451))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0452_typed() -> None:
    """unknown chunk size=452 declaring 852B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 452 + 400)
                + bytes(((452 * 13) % 251) for _ in range(452))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0453_typed() -> None:
    """unknown chunk size=453 declaring 853B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 453 + 400)
                + bytes(((453 * 13) % 251) for _ in range(453))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0454_typed() -> None:
    """unknown chunk size=454 declaring 854B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 454 + 400)
                + bytes(((454 * 13) % 251) for _ in range(454))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0455_typed() -> None:
    """unknown chunk size=455 declaring 855B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 455 + 400)
                + bytes(((455 * 13) % 251) for _ in range(455))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0456_typed() -> None:
    """unknown chunk size=456 declaring 856B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 456 + 400)
                + bytes(((456 * 13) % 251) for _ in range(456))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0457_typed() -> None:
    """unknown chunk size=457 declaring 857B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 457 + 400)
                + bytes(((457 * 13) % 251) for _ in range(457))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0458_typed() -> None:
    """unknown chunk size=458 declaring 858B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 458 + 400)
                + bytes(((458 * 13) % 251) for _ in range(458))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0459_typed() -> None:
    """unknown chunk size=459 declaring 859B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 459 + 400)
                + bytes(((459 * 13) % 251) for _ in range(459))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0460_typed() -> None:
    """unknown chunk size=460 declaring 860B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 460 + 400)
                + bytes(((460 * 13) % 251) for _ in range(460))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0461_typed() -> None:
    """unknown chunk size=461 declaring 861B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 461 + 400)
                + bytes(((461 * 13) % 251) for _ in range(461))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0462_typed() -> None:
    """unknown chunk size=462 declaring 862B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 462 + 400)
                + bytes(((462 * 13) % 251) for _ in range(462))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0463_typed() -> None:
    """unknown chunk size=463 declaring 863B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 463 + 400)
                + bytes(((463 * 13) % 251) for _ in range(463))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0464_typed() -> None:
    """unknown chunk size=464 declaring 864B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 464 + 400)
                + bytes(((464 * 13) % 251) for _ in range(464))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0465_typed() -> None:
    """unknown chunk size=465 declaring 865B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 465 + 400)
                + bytes(((465 * 13) % 251) for _ in range(465))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0466_typed() -> None:
    """unknown chunk size=466 declaring 866B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 466 + 400)
                + bytes(((466 * 13) % 251) for _ in range(466))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0467_typed() -> None:
    """unknown chunk size=467 declaring 867B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 467 + 400)
                + bytes(((467 * 13) % 251) for _ in range(467))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0468_typed() -> None:
    """unknown chunk size=468 declaring 868B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 468 + 400)
                + bytes(((468 * 13) % 251) for _ in range(468))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0469_typed() -> None:
    """unknown chunk size=469 declaring 869B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 469 + 400)
                + bytes(((469 * 13) % 251) for _ in range(469))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0470_typed() -> None:
    """unknown chunk size=470 declaring 870B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 470 + 400)
                + bytes(((470 * 13) % 251) for _ in range(470))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0471_typed() -> None:
    """unknown chunk size=471 declaring 871B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 471 + 400)
                + bytes(((471 * 13) % 251) for _ in range(471))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0472_typed() -> None:
    """unknown chunk size=472 declaring 872B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 472 + 400)
                + bytes(((472 * 13) % 251) for _ in range(472))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0473_typed() -> None:
    """unknown chunk size=473 declaring 873B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 473 + 400)
                + bytes(((473 * 13) % 251) for _ in range(473))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0474_typed() -> None:
    """unknown chunk size=474 declaring 874B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 474 + 400)
                + bytes(((474 * 13) % 251) for _ in range(474))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0475_typed() -> None:
    """unknown chunk size=475 declaring 875B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 475 + 400)
                + bytes(((475 * 13) % 251) for _ in range(475))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0476_typed() -> None:
    """unknown chunk size=476 declaring 876B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 476 + 400)
                + bytes(((476 * 13) % 251) for _ in range(476))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0477_typed() -> None:
    """unknown chunk size=477 declaring 877B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 477 + 400)
                + bytes(((477 * 13) % 251) for _ in range(477))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0478_typed() -> None:
    """unknown chunk size=478 declaring 878B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 478 + 400)
                + bytes(((478 * 13) % 251) for _ in range(478))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0479_typed() -> None:
    """unknown chunk size=479 declaring 879B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 479 + 400)
                + bytes(((479 * 13) % 251) for _ in range(479))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0480_typed() -> None:
    """unknown chunk size=480 declaring 880B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 480 + 400)
                + bytes(((480 * 13) % 251) for _ in range(480))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0481_typed() -> None:
    """unknown chunk size=481 declaring 881B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 481 + 400)
                + bytes(((481 * 13) % 251) for _ in range(481))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0482_typed() -> None:
    """unknown chunk size=482 declaring 882B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 482 + 400)
                + bytes(((482 * 13) % 251) for _ in range(482))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0483_typed() -> None:
    """unknown chunk size=483 declaring 883B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 483 + 400)
                + bytes(((483 * 13) % 251) for _ in range(483))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0484_typed() -> None:
    """unknown chunk size=484 declaring 884B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 484 + 400)
                + bytes(((484 * 13) % 251) for _ in range(484))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0485_typed() -> None:
    """unknown chunk size=485 declaring 885B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 485 + 400)
                + bytes(((485 * 13) % 251) for _ in range(485))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0486_typed() -> None:
    """unknown chunk size=486 declaring 886B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 486 + 400)
                + bytes(((486 * 13) % 251) for _ in range(486))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0487_typed() -> None:
    """unknown chunk size=487 declaring 887B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 487 + 400)
                + bytes(((487 * 13) % 251) for _ in range(487))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0488_typed() -> None:
    """unknown chunk size=488 declaring 888B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 488 + 400)
                + bytes(((488 * 13) % 251) for _ in range(488))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0489_typed() -> None:
    """unknown chunk size=489 declaring 889B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 489 + 400)
                + bytes(((489 * 13) % 251) for _ in range(489))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0490_typed() -> None:
    """unknown chunk size=490 declaring 890B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 490 + 400)
                + bytes(((490 * 13) % 251) for _ in range(490))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0491_typed() -> None:
    """unknown chunk size=491 declaring 891B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 491 + 400)
                + bytes(((491 * 13) % 251) for _ in range(491))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0492_typed() -> None:
    """unknown chunk size=492 declaring 892B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 492 + 400)
                + bytes(((492 * 13) % 251) for _ in range(492))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0493_typed() -> None:
    """unknown chunk size=493 declaring 893B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 493 + 400)
                + bytes(((493 * 13) % 251) for _ in range(493))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0494_typed() -> None:
    """unknown chunk size=494 declaring 894B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 494 + 400)
                + bytes(((494 * 13) % 251) for _ in range(494))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0495_typed() -> None:
    """unknown chunk size=495 declaring 895B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 495 + 400)
                + bytes(((495 * 13) % 251) for _ in range(495))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0496_typed() -> None:
    """unknown chunk size=496 declaring 896B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 496 + 400)
                + bytes(((496 * 13) % 251) for _ in range(496))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0497_typed() -> None:
    """unknown chunk size=497 declaring 897B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 497 + 400)
                + bytes(((497 * 13) % 251) for _ in range(497))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0498_typed() -> None:
    """unknown chunk size=498 declaring 898B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 498 + 400)
                + bytes(((498 * 13) % 251) for _ in range(498))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0499_typed() -> None:
    """unknown chunk size=499 declaring 899B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 499 + 400)
                + bytes(((499 * 13) % 251) for _ in range(499))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0500_typed() -> None:
    """unknown chunk size=500 declaring 900B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 500 + 400)
                + bytes(((500 * 13) % 251) for _ in range(500))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0501_typed() -> None:
    """unknown chunk size=501 declaring 901B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 501 + 400)
                + bytes(((501 * 13) % 251) for _ in range(501))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0502_typed() -> None:
    """unknown chunk size=502 declaring 902B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 502 + 400)
                + bytes(((502 * 13) % 251) for _ in range(502))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0503_typed() -> None:
    """unknown chunk size=503 declaring 903B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 503 + 400)
                + bytes(((503 * 13) % 251) for _ in range(503))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0504_typed() -> None:
    """unknown chunk size=504 declaring 904B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 504 + 400)
                + bytes(((504 * 13) % 251) for _ in range(504))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0505_typed() -> None:
    """unknown chunk size=505 declaring 905B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 505 + 400)
                + bytes(((505 * 13) % 251) for _ in range(505))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0506_typed() -> None:
    """unknown chunk size=506 declaring 906B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 506 + 400)
                + bytes(((506 * 13) % 251) for _ in range(506))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0507_typed() -> None:
    """unknown chunk size=507 declaring 907B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 507 + 400)
                + bytes(((507 * 13) % 251) for _ in range(507))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0508_typed() -> None:
    """unknown chunk size=508 declaring 908B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 508 + 400)
                + bytes(((508 * 13) % 251) for _ in range(508))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0509_typed() -> None:
    """unknown chunk size=509 declaring 909B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 509 + 400)
                + bytes(((509 * 13) % 251) for _ in range(509))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0510_typed() -> None:
    """unknown chunk size=510 declaring 910B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 510 + 400)
                + bytes(((510 * 13) % 251) for _ in range(510))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0511_typed() -> None:
    """unknown chunk size=511 declaring 911B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 511 + 400)
                + bytes(((511 * 13) % 251) for _ in range(511))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0512_typed() -> None:
    """unknown chunk size=512 declaring 912B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 512 + 400)
                + bytes(((512 * 13) % 251) for _ in range(512))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0513_typed() -> None:
    """unknown chunk size=513 declaring 913B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 513 + 400)
                + bytes(((513 * 13) % 251) for _ in range(513))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0514_typed() -> None:
    """unknown chunk size=514 declaring 914B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 514 + 400)
                + bytes(((514 * 13) % 251) for _ in range(514))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0515_typed() -> None:
    """unknown chunk size=515 declaring 915B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 515 + 400)
                + bytes(((515 * 13) % 251) for _ in range(515))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0516_typed() -> None:
    """unknown chunk size=516 declaring 916B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 516 + 400)
                + bytes(((516 * 13) % 251) for _ in range(516))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0517_typed() -> None:
    """unknown chunk size=517 declaring 917B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 517 + 400)
                + bytes(((517 * 13) % 251) for _ in range(517))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0518_typed() -> None:
    """unknown chunk size=518 declaring 918B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 518 + 400)
                + bytes(((518 * 13) % 251) for _ in range(518))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0519_typed() -> None:
    """unknown chunk size=519 declaring 919B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 519 + 400)
                + bytes(((519 * 13) % 251) for _ in range(519))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0520_typed() -> None:
    """unknown chunk size=520 declaring 920B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 520 + 400)
                + bytes(((520 * 13) % 251) for _ in range(520))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0521_typed() -> None:
    """unknown chunk size=521 declaring 921B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 521 + 400)
                + bytes(((521 * 13) % 251) for _ in range(521))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0522_typed() -> None:
    """unknown chunk size=522 declaring 922B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 522 + 400)
                + bytes(((522 * 13) % 251) for _ in range(522))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0523_typed() -> None:
    """unknown chunk size=523 declaring 923B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 523 + 400)
                + bytes(((523 * 13) % 251) for _ in range(523))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0524_typed() -> None:
    """unknown chunk size=524 declaring 924B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 524 + 400)
                + bytes(((524 * 13) % 251) for _ in range(524))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0525_typed() -> None:
    """unknown chunk size=525 declaring 925B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 525 + 400)
                + bytes(((525 * 13) % 251) for _ in range(525))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0526_typed() -> None:
    """unknown chunk size=526 declaring 926B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 526 + 400)
                + bytes(((526 * 13) % 251) for _ in range(526))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0527_typed() -> None:
    """unknown chunk size=527 declaring 927B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 527 + 400)
                + bytes(((527 * 13) % 251) for _ in range(527))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0528_typed() -> None:
    """unknown chunk size=528 declaring 928B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 528 + 400)
                + bytes(((528 * 13) % 251) for _ in range(528))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0529_typed() -> None:
    """unknown chunk size=529 declaring 929B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 529 + 400)
                + bytes(((529 * 13) % 251) for _ in range(529))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0530_typed() -> None:
    """unknown chunk size=530 declaring 930B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 530 + 400)
                + bytes(((530 * 13) % 251) for _ in range(530))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0531_typed() -> None:
    """unknown chunk size=531 declaring 931B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 531 + 400)
                + bytes(((531 * 13) % 251) for _ in range(531))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0532_typed() -> None:
    """unknown chunk size=532 declaring 932B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 532 + 400)
                + bytes(((532 * 13) % 251) for _ in range(532))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0533_typed() -> None:
    """unknown chunk size=533 declaring 933B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 533 + 400)
                + bytes(((533 * 13) % 251) for _ in range(533))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0534_typed() -> None:
    """unknown chunk size=534 declaring 934B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 534 + 400)
                + bytes(((534 * 13) % 251) for _ in range(534))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0535_typed() -> None:
    """unknown chunk size=535 declaring 935B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 535 + 400)
                + bytes(((535 * 13) % 251) for _ in range(535))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0536_typed() -> None:
    """unknown chunk size=536 declaring 936B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 536 + 400)
                + bytes(((536 * 13) % 251) for _ in range(536))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0537_typed() -> None:
    """unknown chunk size=537 declaring 937B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 537 + 400)
                + bytes(((537 * 13) % 251) for _ in range(537))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0538_typed() -> None:
    """unknown chunk size=538 declaring 938B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 538 + 400)
                + bytes(((538 * 13) % 251) for _ in range(538))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0539_typed() -> None:
    """unknown chunk size=539 declaring 939B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 539 + 400)
                + bytes(((539 * 13) % 251) for _ in range(539))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0540_typed() -> None:
    """unknown chunk size=540 declaring 940B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 540 + 400)
                + bytes(((540 * 13) % 251) for _ in range(540))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0541_typed() -> None:
    """unknown chunk size=541 declaring 941B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 541 + 400)
                + bytes(((541 * 13) % 251) for _ in range(541))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0542_typed() -> None:
    """unknown chunk size=542 declaring 942B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 542 + 400)
                + bytes(((542 * 13) % 251) for _ in range(542))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0543_typed() -> None:
    """unknown chunk size=543 declaring 943B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 543 + 400)
                + bytes(((543 * 13) % 251) for _ in range(543))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0544_typed() -> None:
    """unknown chunk size=544 declaring 944B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 544 + 400)
                + bytes(((544 * 13) % 251) for _ in range(544))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0545_typed() -> None:
    """unknown chunk size=545 declaring 945B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 545 + 400)
                + bytes(((545 * 13) % 251) for _ in range(545))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0546_typed() -> None:
    """unknown chunk size=546 declaring 946B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 546 + 400)
                + bytes(((546 * 13) % 251) for _ in range(546))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0547_typed() -> None:
    """unknown chunk size=547 declaring 947B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 547 + 400)
                + bytes(((547 * 13) % 251) for _ in range(547))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0548_typed() -> None:
    """unknown chunk size=548 declaring 948B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 548 + 400)
                + bytes(((548 * 13) % 251) for _ in range(548))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0549_typed() -> None:
    """unknown chunk size=549 declaring 949B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 549 + 400)
                + bytes(((549 * 13) % 251) for _ in range(549))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0550_typed() -> None:
    """unknown chunk size=550 declaring 950B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 550 + 400)
                + bytes(((550 * 13) % 251) for _ in range(550))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0551_typed() -> None:
    """unknown chunk size=551 declaring 951B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 551 + 400)
                + bytes(((551 * 13) % 251) for _ in range(551))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0552_typed() -> None:
    """unknown chunk size=552 declaring 952B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 552 + 400)
                + bytes(((552 * 13) % 251) for _ in range(552))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0553_typed() -> None:
    """unknown chunk size=553 declaring 953B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 553 + 400)
                + bytes(((553 * 13) % 251) for _ in range(553))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0554_typed() -> None:
    """unknown chunk size=554 declaring 954B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 554 + 400)
                + bytes(((554 * 13) % 251) for _ in range(554))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0555_typed() -> None:
    """unknown chunk size=555 declaring 955B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 555 + 400)
                + bytes(((555 * 13) % 251) for _ in range(555))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0556_typed() -> None:
    """unknown chunk size=556 declaring 956B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 556 + 400)
                + bytes(((556 * 13) % 251) for _ in range(556))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0557_typed() -> None:
    """unknown chunk size=557 declaring 957B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 557 + 400)
                + bytes(((557 * 13) % 251) for _ in range(557))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0558_typed() -> None:
    """unknown chunk size=558 declaring 958B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 558 + 400)
                + bytes(((558 * 13) % 251) for _ in range(558))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0559_typed() -> None:
    """unknown chunk size=559 declaring 959B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 559 + 400)
                + bytes(((559 * 13) % 251) for _ in range(559))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0560_typed() -> None:
    """unknown chunk size=560 declaring 960B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 560 + 400)
                + bytes(((560 * 13) % 251) for _ in range(560))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0561_typed() -> None:
    """unknown chunk size=561 declaring 961B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 561 + 400)
                + bytes(((561 * 13) % 251) for _ in range(561))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0562_typed() -> None:
    """unknown chunk size=562 declaring 962B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 562 + 400)
                + bytes(((562 * 13) % 251) for _ in range(562))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0563_typed() -> None:
    """unknown chunk size=563 declaring 963B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 563 + 400)
                + bytes(((563 * 13) % 251) for _ in range(563))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0564_typed() -> None:
    """unknown chunk size=564 declaring 964B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 564 + 400)
                + bytes(((564 * 13) % 251) for _ in range(564))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0565_typed() -> None:
    """unknown chunk size=565 declaring 965B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 565 + 400)
                + bytes(((565 * 13) % 251) for _ in range(565))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0566_typed() -> None:
    """unknown chunk size=566 declaring 966B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 566 + 400)
                + bytes(((566 * 13) % 251) for _ in range(566))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0567_typed() -> None:
    """unknown chunk size=567 declaring 967B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 567 + 400)
                + bytes(((567 * 13) % 251) for _ in range(567))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0568_typed() -> None:
    """unknown chunk size=568 declaring 968B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 568 + 400)
                + bytes(((568 * 13) % 251) for _ in range(568))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0569_typed() -> None:
    """unknown chunk size=569 declaring 969B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 569 + 400)
                + bytes(((569 * 13) % 251) for _ in range(569))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0570_typed() -> None:
    """unknown chunk size=570 declaring 970B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 570 + 400)
                + bytes(((570 * 13) % 251) for _ in range(570))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0571_typed() -> None:
    """unknown chunk size=571 declaring 971B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 571 + 400)
                + bytes(((571 * 13) % 251) for _ in range(571))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0572_typed() -> None:
    """unknown chunk size=572 declaring 972B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 572 + 400)
                + bytes(((572 * 13) % 251) for _ in range(572))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0573_typed() -> None:
    """unknown chunk size=573 declaring 973B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 573 + 400)
                + bytes(((573 * 13) % 251) for _ in range(573))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0574_typed() -> None:
    """unknown chunk size=574 declaring 974B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 574 + 400)
                + bytes(((574 * 13) % 251) for _ in range(574))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0575_typed() -> None:
    """unknown chunk size=575 declaring 975B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 575 + 400)
                + bytes(((575 * 13) % 251) for _ in range(575))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0576_typed() -> None:
    """unknown chunk size=576 declaring 976B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 576 + 400)
                + bytes(((576 * 13) % 251) for _ in range(576))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0577_typed() -> None:
    """unknown chunk size=577 declaring 977B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 577 + 400)
                + bytes(((577 * 13) % 251) for _ in range(577))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0578_typed() -> None:
    """unknown chunk size=578 declaring 978B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 578 + 400)
                + bytes(((578 * 13) % 251) for _ in range(578))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0579_typed() -> None:
    """unknown chunk size=579 declaring 979B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 579 + 400)
                + bytes(((579 * 13) % 251) for _ in range(579))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0580_typed() -> None:
    """unknown chunk size=580 declaring 980B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 580 + 400)
                + bytes(((580 * 13) % 251) for _ in range(580))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0581_typed() -> None:
    """unknown chunk size=581 declaring 981B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 581 + 400)
                + bytes(((581 * 13) % 251) for _ in range(581))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0582_typed() -> None:
    """unknown chunk size=582 declaring 982B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 582 + 400)
                + bytes(((582 * 13) % 251) for _ in range(582))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0583_typed() -> None:
    """unknown chunk size=583 declaring 983B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 583 + 400)
                + bytes(((583 * 13) % 251) for _ in range(583))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0584_typed() -> None:
    """unknown chunk size=584 declaring 984B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 584 + 400)
                + bytes(((584 * 13) % 251) for _ in range(584))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0585_typed() -> None:
    """unknown chunk size=585 declaring 985B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 585 + 400)
                + bytes(((585 * 13) % 251) for _ in range(585))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0586_typed() -> None:
    """unknown chunk size=586 declaring 986B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 586 + 400)
                + bytes(((586 * 13) % 251) for _ in range(586))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0587_typed() -> None:
    """unknown chunk size=587 declaring 987B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 587 + 400)
                + bytes(((587 * 13) % 251) for _ in range(587))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0588_typed() -> None:
    """unknown chunk size=588 declaring 988B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 588 + 400)
                + bytes(((588 * 13) % 251) for _ in range(588))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0589_typed() -> None:
    """unknown chunk size=589 declaring 989B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 589 + 400)
                + bytes(((589 * 13) % 251) for _ in range(589))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0590_typed() -> None:
    """unknown chunk size=590 declaring 990B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 590 + 400)
                + bytes(((590 * 13) % 251) for _ in range(590))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0591_typed() -> None:
    """unknown chunk size=591 declaring 991B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 591 + 400)
                + bytes(((591 * 13) % 251) for _ in range(591))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0592_typed() -> None:
    """unknown chunk size=592 declaring 992B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 592 + 400)
                + bytes(((592 * 13) % 251) for _ in range(592))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0593_typed() -> None:
    """unknown chunk size=593 declaring 993B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 593 + 400)
                + bytes(((593 * 13) % 251) for _ in range(593))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0594_typed() -> None:
    """unknown chunk size=594 declaring 994B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 594 + 400)
                + bytes(((594 * 13) % 251) for _ in range(594))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0595_typed() -> None:
    """unknown chunk size=595 declaring 995B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 595 + 400)
                + bytes(((595 * 13) % 251) for _ in range(595))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0596_typed() -> None:
    """unknown chunk size=596 declaring 996B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 596 + 400)
                + bytes(((596 * 13) % 251) for _ in range(596))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0597_typed() -> None:
    """unknown chunk size=597 declaring 997B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 597 + 400)
                + bytes(((597 * 13) % 251) for _ in range(597))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0598_typed() -> None:
    """unknown chunk size=598 declaring 998B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 598 + 400)
                + bytes(((598 * 13) % 251) for _ in range(598))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0599_typed() -> None:
    """unknown chunk size=599 declaring 999B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 599 + 400)
                + bytes(((599 * 13) % 251) for _ in range(599))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0600_typed() -> None:
    """unknown chunk size=600 declaring 1000B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 600 + 400)
                + bytes(((600 * 13) % 251) for _ in range(600))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0601_typed() -> None:
    """unknown chunk size=601 declaring 1001B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 601 + 400)
                + bytes(((601 * 13) % 251) for _ in range(601))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0602_typed() -> None:
    """unknown chunk size=602 declaring 1002B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 602 + 400)
                + bytes(((602 * 13) % 251) for _ in range(602))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0603_typed() -> None:
    """unknown chunk size=603 declaring 1003B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 603 + 400)
                + bytes(((603 * 13) % 251) for _ in range(603))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0604_typed() -> None:
    """unknown chunk size=604 declaring 1004B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 604 + 400)
                + bytes(((604 * 13) % 251) for _ in range(604))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0605_typed() -> None:
    """unknown chunk size=605 declaring 1005B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 605 + 400)
                + bytes(((605 * 13) % 251) for _ in range(605))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0606_typed() -> None:
    """unknown chunk size=606 declaring 1006B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 606 + 400)
                + bytes(((606 * 13) % 251) for _ in range(606))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0607_typed() -> None:
    """unknown chunk size=607 declaring 1007B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 607 + 400)
                + bytes(((607 * 13) % 251) for _ in range(607))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0608_typed() -> None:
    """unknown chunk size=608 declaring 1008B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 608 + 400)
                + bytes(((608 * 13) % 251) for _ in range(608))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0609_typed() -> None:
    """unknown chunk size=609 declaring 1009B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 609 + 400)
                + bytes(((609 * 13) % 251) for _ in range(609))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0610_typed() -> None:
    """unknown chunk size=610 declaring 1010B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 610 + 400)
                + bytes(((610 * 13) % 251) for _ in range(610))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0611_typed() -> None:
    """unknown chunk size=611 declaring 1011B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 611 + 400)
                + bytes(((611 * 13) % 251) for _ in range(611))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0612_typed() -> None:
    """unknown chunk size=612 declaring 1012B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 612 + 400)
                + bytes(((612 * 13) % 251) for _ in range(612))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0613_typed() -> None:
    """unknown chunk size=613 declaring 1013B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 613 + 400)
                + bytes(((613 * 13) % 251) for _ in range(613))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0614_typed() -> None:
    """unknown chunk size=614 declaring 1014B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 614 + 400)
                + bytes(((614 * 13) % 251) for _ in range(614))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0615_typed() -> None:
    """unknown chunk size=615 declaring 1015B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 615 + 400)
                + bytes(((615 * 13) % 251) for _ in range(615))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0616_typed() -> None:
    """unknown chunk size=616 declaring 1016B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 616 + 400)
                + bytes(((616 * 13) % 251) for _ in range(616))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0617_typed() -> None:
    """unknown chunk size=617 declaring 1017B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 617 + 400)
                + bytes(((617 * 13) % 251) for _ in range(617))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0618_typed() -> None:
    """unknown chunk size=618 declaring 1018B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 618 + 400)
                + bytes(((618 * 13) % 251) for _ in range(618))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0619_typed() -> None:
    """unknown chunk size=619 declaring 1019B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 619 + 400)
                + bytes(((619 * 13) % 251) for _ in range(619))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0620_typed() -> None:
    """unknown chunk size=620 declaring 1020B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 620 + 400)
                + bytes(((620 * 13) % 251) for _ in range(620))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0621_typed() -> None:
    """unknown chunk size=621 declaring 1021B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 621 + 400)
                + bytes(((621 * 13) % 251) for _ in range(621))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0622_typed() -> None:
    """unknown chunk size=622 declaring 1022B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 622 + 400)
                + bytes(((622 * 13) % 251) for _ in range(622))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0623_typed() -> None:
    """unknown chunk size=623 declaring 1023B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 623 + 400)
                + bytes(((623 * 13) % 251) for _ in range(623))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0624_typed() -> None:
    """unknown chunk size=624 declaring 1024B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 624 + 400)
                + bytes(((624 * 13) % 251) for _ in range(624))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0625_typed() -> None:
    """unknown chunk size=625 declaring 1025B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 625 + 400)
                + bytes(((625 * 13) % 251) for _ in range(625))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0626_typed() -> None:
    """unknown chunk size=626 declaring 1026B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 626 + 400)
                + bytes(((626 * 13) % 251) for _ in range(626))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0627_typed() -> None:
    """unknown chunk size=627 declaring 1027B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 627 + 400)
                + bytes(((627 * 13) % 251) for _ in range(627))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0628_typed() -> None:
    """unknown chunk size=628 declaring 1028B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 628 + 400)
                + bytes(((628 * 13) % 251) for _ in range(628))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0629_typed() -> None:
    """unknown chunk size=629 declaring 1029B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 629 + 400)
                + bytes(((629 * 13) % 251) for _ in range(629))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0630_typed() -> None:
    """unknown chunk size=630 declaring 1030B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 630 + 400)
                + bytes(((630 * 13) % 251) for _ in range(630))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0631_typed() -> None:
    """unknown chunk size=631 declaring 1031B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 631 + 400)
                + bytes(((631 * 13) % 251) for _ in range(631))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0632_typed() -> None:
    """unknown chunk size=632 declaring 1032B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 632 + 400)
                + bytes(((632 * 13) % 251) for _ in range(632))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0633_typed() -> None:
    """unknown chunk size=633 declaring 1033B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 633 + 400)
                + bytes(((633 * 13) % 251) for _ in range(633))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0634_typed() -> None:
    """unknown chunk size=634 declaring 1034B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 634 + 400)
                + bytes(((634 * 13) % 251) for _ in range(634))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0635_typed() -> None:
    """unknown chunk size=635 declaring 1035B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 635 + 400)
                + bytes(((635 * 13) % 251) for _ in range(635))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0636_typed() -> None:
    """unknown chunk size=636 declaring 1036B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 636 + 400)
                + bytes(((636 * 13) % 251) for _ in range(636))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0637_typed() -> None:
    """unknown chunk size=637 declaring 1037B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 637 + 400)
                + bytes(((637 * 13) % 251) for _ in range(637))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0638_typed() -> None:
    """unknown chunk size=638 declaring 1038B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 638 + 400)
                + bytes(((638 * 13) % 251) for _ in range(638))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0639_typed() -> None:
    """unknown chunk size=639 declaring 1039B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 639 + 400)
                + bytes(((639 * 13) % 251) for _ in range(639))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0640_typed() -> None:
    """unknown chunk size=640 declaring 1040B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 640 + 400)
                + bytes(((640 * 13) % 251) for _ in range(640))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0641_typed() -> None:
    """unknown chunk size=641 declaring 1041B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 641 + 400)
                + bytes(((641 * 13) % 251) for _ in range(641))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0642_typed() -> None:
    """unknown chunk size=642 declaring 1042B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 642 + 400)
                + bytes(((642 * 13) % 251) for _ in range(642))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0643_typed() -> None:
    """unknown chunk size=643 declaring 1043B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 643 + 400)
                + bytes(((643 * 13) % 251) for _ in range(643))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0644_typed() -> None:
    """unknown chunk size=644 declaring 1044B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 644 + 400)
                + bytes(((644 * 13) % 251) for _ in range(644))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0645_typed() -> None:
    """unknown chunk size=645 declaring 1045B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 645 + 400)
                + bytes(((645 * 13) % 251) for _ in range(645))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0646_typed() -> None:
    """unknown chunk size=646 declaring 1046B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 646 + 400)
                + bytes(((646 * 13) % 251) for _ in range(646))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0647_typed() -> None:
    """unknown chunk size=647 declaring 1047B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 647 + 400)
                + bytes(((647 * 13) % 251) for _ in range(647))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0648_typed() -> None:
    """unknown chunk size=648 declaring 1048B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 648 + 400)
                + bytes(((648 * 13) % 251) for _ in range(648))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0649_typed() -> None:
    """unknown chunk size=649 declaring 1049B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 649 + 400)
                + bytes(((649 * 13) % 251) for _ in range(649))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0650_typed() -> None:
    """unknown chunk size=650 declaring 1050B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 650 + 400)
                + bytes(((650 * 13) % 251) for _ in range(650))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0651_typed() -> None:
    """unknown chunk size=651 declaring 1051B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 651 + 400)
                + bytes(((651 * 13) % 251) for _ in range(651))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0652_typed() -> None:
    """unknown chunk size=652 declaring 1052B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 652 + 400)
                + bytes(((652 * 13) % 251) for _ in range(652))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0653_typed() -> None:
    """unknown chunk size=653 declaring 1053B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 653 + 400)
                + bytes(((653 * 13) % 251) for _ in range(653))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0654_typed() -> None:
    """unknown chunk size=654 declaring 1054B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 654 + 400)
                + bytes(((654 * 13) % 251) for _ in range(654))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0655_typed() -> None:
    """unknown chunk size=655 declaring 1055B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 655 + 400)
                + bytes(((655 * 13) % 251) for _ in range(655))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0656_typed() -> None:
    """unknown chunk size=656 declaring 1056B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 656 + 400)
                + bytes(((656 * 13) % 251) for _ in range(656))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0657_typed() -> None:
    """unknown chunk size=657 declaring 1057B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 657 + 400)
                + bytes(((657 * 13) % 251) for _ in range(657))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0658_typed() -> None:
    """unknown chunk size=658 declaring 1058B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 658 + 400)
                + bytes(((658 * 13) % 251) for _ in range(658))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0659_typed() -> None:
    """unknown chunk size=659 declaring 1059B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 659 + 400)
                + bytes(((659 * 13) % 251) for _ in range(659))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0660_typed() -> None:
    """unknown chunk size=660 declaring 1060B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 660 + 400)
                + bytes(((660 * 13) % 251) for _ in range(660))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0661_typed() -> None:
    """unknown chunk size=661 declaring 1061B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 661 + 400)
                + bytes(((661 * 13) % 251) for _ in range(661))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0662_typed() -> None:
    """unknown chunk size=662 declaring 1062B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 662 + 400)
                + bytes(((662 * 13) % 251) for _ in range(662))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0663_typed() -> None:
    """unknown chunk size=663 declaring 1063B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 663 + 400)
                + bytes(((663 * 13) % 251) for _ in range(663))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0664_typed() -> None:
    """unknown chunk size=664 declaring 1064B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 664 + 400)
                + bytes(((664 * 13) % 251) for _ in range(664))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0665_typed() -> None:
    """unknown chunk size=665 declaring 1065B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 665 + 400)
                + bytes(((665 * 13) % 251) for _ in range(665))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0666_typed() -> None:
    """unknown chunk size=666 declaring 1066B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 666 + 400)
                + bytes(((666 * 13) % 251) for _ in range(666))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0667_typed() -> None:
    """unknown chunk size=667 declaring 1067B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 667 + 400)
                + bytes(((667 * 13) % 251) for _ in range(667))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0668_typed() -> None:
    """unknown chunk size=668 declaring 1068B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 668 + 400)
                + bytes(((668 * 13) % 251) for _ in range(668))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0669_typed() -> None:
    """unknown chunk size=669 declaring 1069B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 669 + 400)
                + bytes(((669 * 13) % 251) for _ in range(669))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0670_typed() -> None:
    """unknown chunk size=670 declaring 1070B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 670 + 400)
                + bytes(((670 * 13) % 251) for _ in range(670))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0671_typed() -> None:
    """unknown chunk size=671 declaring 1071B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 671 + 400)
                + bytes(((671 * 13) % 251) for _ in range(671))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0672_typed() -> None:
    """unknown chunk size=672 declaring 1072B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 672 + 400)
                + bytes(((672 * 13) % 251) for _ in range(672))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0673_typed() -> None:
    """unknown chunk size=673 declaring 1073B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 673 + 400)
                + bytes(((673 * 13) % 251) for _ in range(673))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0674_typed() -> None:
    """unknown chunk size=674 declaring 1074B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 674 + 400)
                + bytes(((674 * 13) % 251) for _ in range(674))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0675_typed() -> None:
    """unknown chunk size=675 declaring 1075B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 675 + 400)
                + bytes(((675 * 13) % 251) for _ in range(675))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0676_typed() -> None:
    """unknown chunk size=676 declaring 1076B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 676 + 400)
                + bytes(((676 * 13) % 251) for _ in range(676))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0677_typed() -> None:
    """unknown chunk size=677 declaring 1077B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 677 + 400)
                + bytes(((677 * 13) % 251) for _ in range(677))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0678_typed() -> None:
    """unknown chunk size=678 declaring 1078B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 678 + 400)
                + bytes(((678 * 13) % 251) for _ in range(678))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0679_typed() -> None:
    """unknown chunk size=679 declaring 1079B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 679 + 400)
                + bytes(((679 * 13) % 251) for _ in range(679))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0680_typed() -> None:
    """unknown chunk size=680 declaring 1080B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 680 + 400)
                + bytes(((680 * 13) % 251) for _ in range(680))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0681_typed() -> None:
    """unknown chunk size=681 declaring 1081B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 681 + 400)
                + bytes(((681 * 13) % 251) for _ in range(681))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0682_typed() -> None:
    """unknown chunk size=682 declaring 1082B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 682 + 400)
                + bytes(((682 * 13) % 251) for _ in range(682))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0683_typed() -> None:
    """unknown chunk size=683 declaring 1083B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 683 + 400)
                + bytes(((683 * 13) % 251) for _ in range(683))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0684_typed() -> None:
    """unknown chunk size=684 declaring 1084B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 684 + 400)
                + bytes(((684 * 13) % 251) for _ in range(684))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0685_typed() -> None:
    """unknown chunk size=685 declaring 1085B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 685 + 400)
                + bytes(((685 * 13) % 251) for _ in range(685))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0686_typed() -> None:
    """unknown chunk size=686 declaring 1086B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 686 + 400)
                + bytes(((686 * 13) % 251) for _ in range(686))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0687_typed() -> None:
    """unknown chunk size=687 declaring 1087B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 687 + 400)
                + bytes(((687 * 13) % 251) for _ in range(687))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0688_typed() -> None:
    """unknown chunk size=688 declaring 1088B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 688 + 400)
                + bytes(((688 * 13) % 251) for _ in range(688))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0689_typed() -> None:
    """unknown chunk size=689 declaring 1089B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 689 + 400)
                + bytes(((689 * 13) % 251) for _ in range(689))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0690_typed() -> None:
    """unknown chunk size=690 declaring 1090B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 690 + 400)
                + bytes(((690 * 13) % 251) for _ in range(690))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0691_typed() -> None:
    """unknown chunk size=691 declaring 1091B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 691 + 400)
                + bytes(((691 * 13) % 251) for _ in range(691))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0692_typed() -> None:
    """unknown chunk size=692 declaring 1092B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 692 + 400)
                + bytes(((692 * 13) % 251) for _ in range(692))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0693_typed() -> None:
    """unknown chunk size=693 declaring 1093B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 693 + 400)
                + bytes(((693 * 13) % 251) for _ in range(693))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0694_typed() -> None:
    """unknown chunk size=694 declaring 1094B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 694 + 400)
                + bytes(((694 * 13) % 251) for _ in range(694))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0695_typed() -> None:
    """unknown chunk size=695 declaring 1095B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 695 + 400)
                + bytes(((695 * 13) % 251) for _ in range(695))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0696_typed() -> None:
    """unknown chunk size=696 declaring 1096B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 696 + 400)
                + bytes(((696 * 13) % 251) for _ in range(696))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0697_typed() -> None:
    """unknown chunk size=697 declaring 1097B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 697 + 400)
                + bytes(((697 * 13) % 251) for _ in range(697))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0698_typed() -> None:
    """unknown chunk size=698 declaring 1098B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 698 + 400)
                + bytes(((698 * 13) % 251) for _ in range(698))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0699_typed() -> None:
    """unknown chunk size=699 declaring 1099B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 699 + 400)
                + bytes(((699 * 13) % 251) for _ in range(699))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0700_typed() -> None:
    """unknown chunk size=700 declaring 1100B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 700 + 400)
                + bytes(((700 * 13) % 251) for _ in range(700))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0701_typed() -> None:
    """unknown chunk size=701 declaring 1101B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 701 + 400)
                + bytes(((701 * 13) % 251) for _ in range(701))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0702_typed() -> None:
    """unknown chunk size=702 declaring 1102B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 702 + 400)
                + bytes(((702 * 13) % 251) for _ in range(702))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0703_typed() -> None:
    """unknown chunk size=703 declaring 1103B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 703 + 400)
                + bytes(((703 * 13) % 251) for _ in range(703))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0704_typed() -> None:
    """unknown chunk size=704 declaring 1104B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 704 + 400)
                + bytes(((704 * 13) % 251) for _ in range(704))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0705_typed() -> None:
    """unknown chunk size=705 declaring 1105B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 705 + 400)
                + bytes(((705 * 13) % 251) for _ in range(705))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0706_typed() -> None:
    """unknown chunk size=706 declaring 1106B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 706 + 400)
                + bytes(((706 * 13) % 251) for _ in range(706))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0707_typed() -> None:
    """unknown chunk size=707 declaring 1107B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 707 + 400)
                + bytes(((707 * 13) % 251) for _ in range(707))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0708_typed() -> None:
    """unknown chunk size=708 declaring 1108B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 708 + 400)
                + bytes(((708 * 13) % 251) for _ in range(708))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0709_typed() -> None:
    """unknown chunk size=709 declaring 1109B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 709 + 400)
                + bytes(((709 * 13) % 251) for _ in range(709))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0710_typed() -> None:
    """unknown chunk size=710 declaring 1110B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 710 + 400)
                + bytes(((710 * 13) % 251) for _ in range(710))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0711_typed() -> None:
    """unknown chunk size=711 declaring 1111B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 711 + 400)
                + bytes(((711 * 13) % 251) for _ in range(711))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0712_typed() -> None:
    """unknown chunk size=712 declaring 1112B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 712 + 400)
                + bytes(((712 * 13) % 251) for _ in range(712))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0713_typed() -> None:
    """unknown chunk size=713 declaring 1113B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 713 + 400)
                + bytes(((713 * 13) % 251) for _ in range(713))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0714_typed() -> None:
    """unknown chunk size=714 declaring 1114B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 714 + 400)
                + bytes(((714 * 13) % 251) for _ in range(714))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0715_typed() -> None:
    """unknown chunk size=715 declaring 1115B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 715 + 400)
                + bytes(((715 * 13) % 251) for _ in range(715))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0716_typed() -> None:
    """unknown chunk size=716 declaring 1116B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 716 + 400)
                + bytes(((716 * 13) % 251) for _ in range(716))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0717_typed() -> None:
    """unknown chunk size=717 declaring 1117B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 717 + 400)
                + bytes(((717 * 13) % 251) for _ in range(717))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0718_typed() -> None:
    """unknown chunk size=718 declaring 1118B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 718 + 400)
                + bytes(((718 * 13) % 251) for _ in range(718))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0719_typed() -> None:
    """unknown chunk size=719 declaring 1119B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 719 + 400)
                + bytes(((719 * 13) % 251) for _ in range(719))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0720_typed() -> None:
    """unknown chunk size=720 declaring 1120B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 720 + 400)
                + bytes(((720 * 13) % 251) for _ in range(720))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0721_typed() -> None:
    """unknown chunk size=721 declaring 1121B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 721 + 400)
                + bytes(((721 * 13) % 251) for _ in range(721))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0722_typed() -> None:
    """unknown chunk size=722 declaring 1122B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 722 + 400)
                + bytes(((722 * 13) % 251) for _ in range(722))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0723_typed() -> None:
    """unknown chunk size=723 declaring 1123B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 723 + 400)
                + bytes(((723 * 13) % 251) for _ in range(723))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0724_typed() -> None:
    """unknown chunk size=724 declaring 1124B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 724 + 400)
                + bytes(((724 * 13) % 251) for _ in range(724))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0725_typed() -> None:
    """unknown chunk size=725 declaring 1125B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 725 + 400)
                + bytes(((725 * 13) % 251) for _ in range(725))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0726_typed() -> None:
    """unknown chunk size=726 declaring 1126B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 726 + 400)
                + bytes(((726 * 13) % 251) for _ in range(726))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0727_typed() -> None:
    """unknown chunk size=727 declaring 1127B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 727 + 400)
                + bytes(((727 * 13) % 251) for _ in range(727))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0728_typed() -> None:
    """unknown chunk size=728 declaring 1128B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 728 + 400)
                + bytes(((728 * 13) % 251) for _ in range(728))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0729_typed() -> None:
    """unknown chunk size=729 declaring 1129B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 729 + 400)
                + bytes(((729 * 13) % 251) for _ in range(729))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0730_typed() -> None:
    """unknown chunk size=730 declaring 1130B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 730 + 400)
                + bytes(((730 * 13) % 251) for _ in range(730))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0731_typed() -> None:
    """unknown chunk size=731 declaring 1131B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 731 + 400)
                + bytes(((731 * 13) % 251) for _ in range(731))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0732_typed() -> None:
    """unknown chunk size=732 declaring 1132B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 732 + 400)
                + bytes(((732 * 13) % 251) for _ in range(732))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0733_typed() -> None:
    """unknown chunk size=733 declaring 1133B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 733 + 400)
                + bytes(((733 * 13) % 251) for _ in range(733))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0734_typed() -> None:
    """unknown chunk size=734 declaring 1134B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 734 + 400)
                + bytes(((734 * 13) % 251) for _ in range(734))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0735_typed() -> None:
    """unknown chunk size=735 declaring 1135B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 735 + 400)
                + bytes(((735 * 13) % 251) for _ in range(735))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0736_typed() -> None:
    """unknown chunk size=736 declaring 1136B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 736 + 400)
                + bytes(((736 * 13) % 251) for _ in range(736))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0737_typed() -> None:
    """unknown chunk size=737 declaring 1137B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 737 + 400)
                + bytes(((737 * 13) % 251) for _ in range(737))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0738_typed() -> None:
    """unknown chunk size=738 declaring 1138B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 738 + 400)
                + bytes(((738 * 13) % 251) for _ in range(738))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0739_typed() -> None:
    """unknown chunk size=739 declaring 1139B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 739 + 400)
                + bytes(((739 * 13) % 251) for _ in range(739))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0740_typed() -> None:
    """unknown chunk size=740 declaring 1140B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 740 + 400)
                + bytes(((740 * 13) % 251) for _ in range(740))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0741_typed() -> None:
    """unknown chunk size=741 declaring 1141B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 741 + 400)
                + bytes(((741 * 13) % 251) for _ in range(741))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0742_typed() -> None:
    """unknown chunk size=742 declaring 1142B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 742 + 400)
                + bytes(((742 * 13) % 251) for _ in range(742))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0743_typed() -> None:
    """unknown chunk size=743 declaring 1143B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 743 + 400)
                + bytes(((743 * 13) % 251) for _ in range(743))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0744_typed() -> None:
    """unknown chunk size=744 declaring 1144B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 744 + 400)
                + bytes(((744 * 13) % 251) for _ in range(744))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0745_typed() -> None:
    """unknown chunk size=745 declaring 1145B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 745 + 400)
                + bytes(((745 * 13) % 251) for _ in range(745))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0746_typed() -> None:
    """unknown chunk size=746 declaring 1146B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 746 + 400)
                + bytes(((746 * 13) % 251) for _ in range(746))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0747_typed() -> None:
    """unknown chunk size=747 declaring 1147B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 747 + 400)
                + bytes(((747 * 13) % 251) for _ in range(747))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0748_typed() -> None:
    """unknown chunk size=748 declaring 1148B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 748 + 400)
                + bytes(((748 * 13) % 251) for _ in range(748))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0749_typed() -> None:
    """unknown chunk size=749 declaring 1149B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 749 + 400)
                + bytes(((749 * 13) % 251) for _ in range(749))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0750_typed() -> None:
    """unknown chunk size=750 declaring 1150B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 750 + 400)
                + bytes(((750 * 13) % 251) for _ in range(750))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0751_typed() -> None:
    """unknown chunk size=751 declaring 1151B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 751 + 400)
                + bytes(((751 * 13) % 251) for _ in range(751))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0752_typed() -> None:
    """unknown chunk size=752 declaring 1152B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 752 + 400)
                + bytes(((752 * 13) % 251) for _ in range(752))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0753_typed() -> None:
    """unknown chunk size=753 declaring 1153B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 753 + 400)
                + bytes(((753 * 13) % 251) for _ in range(753))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0754_typed() -> None:
    """unknown chunk size=754 declaring 1154B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 754 + 400)
                + bytes(((754 * 13) % 251) for _ in range(754))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0755_typed() -> None:
    """unknown chunk size=755 declaring 1155B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 755 + 400)
                + bytes(((755 * 13) % 251) for _ in range(755))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0756_typed() -> None:
    """unknown chunk size=756 declaring 1156B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 756 + 400)
                + bytes(((756 * 13) % 251) for _ in range(756))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0757_typed() -> None:
    """unknown chunk size=757 declaring 1157B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 757 + 400)
                + bytes(((757 * 13) % 251) for _ in range(757))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0758_typed() -> None:
    """unknown chunk size=758 declaring 1158B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 758 + 400)
                + bytes(((758 * 13) % 251) for _ in range(758))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0759_typed() -> None:
    """unknown chunk size=759 declaring 1159B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 759 + 400)
                + bytes(((759 * 13) % 251) for _ in range(759))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0760_typed() -> None:
    """unknown chunk size=760 declaring 1160B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 760 + 400)
                + bytes(((760 * 13) % 251) for _ in range(760))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0761_typed() -> None:
    """unknown chunk size=761 declaring 1161B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 761 + 400)
                + bytes(((761 * 13) % 251) for _ in range(761))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0762_typed() -> None:
    """unknown chunk size=762 declaring 1162B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 762 + 400)
                + bytes(((762 * 13) % 251) for _ in range(762))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0763_typed() -> None:
    """unknown chunk size=763 declaring 1163B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 763 + 400)
                + bytes(((763 * 13) % 251) for _ in range(763))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0764_typed() -> None:
    """unknown chunk size=764 declaring 1164B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 764 + 400)
                + bytes(((764 * 13) % 251) for _ in range(764))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0765_typed() -> None:
    """unknown chunk size=765 declaring 1165B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 765 + 400)
                + bytes(((765 * 13) % 251) for _ in range(765))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0766_typed() -> None:
    """unknown chunk size=766 declaring 1166B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 766 + 400)
                + bytes(((766 * 13) % 251) for _ in range(766))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0767_typed() -> None:
    """unknown chunk size=767 declaring 1167B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 767 + 400)
                + bytes(((767 * 13) % 251) for _ in range(767))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0768_typed() -> None:
    """unknown chunk size=768 declaring 1168B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 768 + 400)
                + bytes(((768 * 13) % 251) for _ in range(768))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0769_typed() -> None:
    """unknown chunk size=769 declaring 1169B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 769 + 400)
                + bytes(((769 * 13) % 251) for _ in range(769))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0770_typed() -> None:
    """unknown chunk size=770 declaring 1170B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 770 + 400)
                + bytes(((770 * 13) % 251) for _ in range(770))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0771_typed() -> None:
    """unknown chunk size=771 declaring 1171B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 771 + 400)
                + bytes(((771 * 13) % 251) for _ in range(771))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0772_typed() -> None:
    """unknown chunk size=772 declaring 1172B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 772 + 400)
                + bytes(((772 * 13) % 251) for _ in range(772))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0773_typed() -> None:
    """unknown chunk size=773 declaring 1173B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 773 + 400)
                + bytes(((773 * 13) % 251) for _ in range(773))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0774_typed() -> None:
    """unknown chunk size=774 declaring 1174B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 774 + 400)
                + bytes(((774 * 13) % 251) for _ in range(774))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0775_typed() -> None:
    """unknown chunk size=775 declaring 1175B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 775 + 400)
                + bytes(((775 * 13) % 251) for _ in range(775))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0776_typed() -> None:
    """unknown chunk size=776 declaring 1176B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 776 + 400)
                + bytes(((776 * 13) % 251) for _ in range(776))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0777_typed() -> None:
    """unknown chunk size=777 declaring 1177B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 777 + 400)
                + bytes(((777 * 13) % 251) for _ in range(777))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0778_typed() -> None:
    """unknown chunk size=778 declaring 1178B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 778 + 400)
                + bytes(((778 * 13) % 251) for _ in range(778))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0779_typed() -> None:
    """unknown chunk size=779 declaring 1179B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 779 + 400)
                + bytes(((779 * 13) % 251) for _ in range(779))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0780_typed() -> None:
    """unknown chunk size=780 declaring 1180B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 780 + 400)
                + bytes(((780 * 13) % 251) for _ in range(780))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0781_typed() -> None:
    """unknown chunk size=781 declaring 1181B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 781 + 400)
                + bytes(((781 * 13) % 251) for _ in range(781))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0782_typed() -> None:
    """unknown chunk size=782 declaring 1182B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 782 + 400)
                + bytes(((782 * 13) % 251) for _ in range(782))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0783_typed() -> None:
    """unknown chunk size=783 declaring 1183B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 783 + 400)
                + bytes(((783 * 13) % 251) for _ in range(783))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0784_typed() -> None:
    """unknown chunk size=784 declaring 1184B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 784 + 400)
                + bytes(((784 * 13) % 251) for _ in range(784))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0785_typed() -> None:
    """unknown chunk size=785 declaring 1185B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 785 + 400)
                + bytes(((785 * 13) % 251) for _ in range(785))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0786_typed() -> None:
    """unknown chunk size=786 declaring 1186B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 786 + 400)
                + bytes(((786 * 13) % 251) for _ in range(786))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0787_typed() -> None:
    """unknown chunk size=787 declaring 1187B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 787 + 400)
                + bytes(((787 * 13) % 251) for _ in range(787))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0788_typed() -> None:
    """unknown chunk size=788 declaring 1188B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 788 + 400)
                + bytes(((788 * 13) % 251) for _ in range(788))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0789_typed() -> None:
    """unknown chunk size=789 declaring 1189B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 789 + 400)
                + bytes(((789 * 13) % 251) for _ in range(789))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0790_typed() -> None:
    """unknown chunk size=790 declaring 1190B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 790 + 400)
                + bytes(((790 * 13) % 251) for _ in range(790))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0791_typed() -> None:
    """unknown chunk size=791 declaring 1191B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 791 + 400)
                + bytes(((791 * 13) % 251) for _ in range(791))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0792_typed() -> None:
    """unknown chunk size=792 declaring 1192B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 792 + 400)
                + bytes(((792 * 13) % 251) for _ in range(792))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0793_typed() -> None:
    """unknown chunk size=793 declaring 1193B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 793 + 400)
                + bytes(((793 * 13) % 251) for _ in range(793))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0794_typed() -> None:
    """unknown chunk size=794 declaring 1194B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 794 + 400)
                + bytes(((794 * 13) % 251) for _ in range(794))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0795_typed() -> None:
    """unknown chunk size=795 declaring 1195B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 795 + 400)
                + bytes(((795 * 13) % 251) for _ in range(795))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0796_typed() -> None:
    """unknown chunk size=796 declaring 1196B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 796 + 400)
                + bytes(((796 * 13) % 251) for _ in range(796))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0797_typed() -> None:
    """unknown chunk size=797 declaring 1197B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 797 + 400)
                + bytes(((797 * 13) % 251) for _ in range(797))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0798_typed() -> None:
    """unknown chunk size=798 declaring 1198B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 798 + 400)
                + bytes(((798 * 13) % 251) for _ in range(798))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0799_typed() -> None:
    """unknown chunk size=799 declaring 1199B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 799 + 400)
                + bytes(((799 * 13) % 251) for _ in range(799))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_lie0800_typed() -> None:
    """unknown chunk size=800 declaring 1200B: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + b'AAAA'
                + struct.pack('<I', 800 + 400)
                + bytes(((800 * 13) % 251) for _ in range(800))
                + base[len(wav) :]
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_walk_many0001_roundtrip() -> None:
    """k=1 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(1)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0002_roundtrip() -> None:
    """k=2 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(2)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0003_roundtrip() -> None:
    """k=3 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(3)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0004_roundtrip() -> None:
    """k=4 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(4)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0005_roundtrip() -> None:
    """k=5 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(5)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0006_roundtrip() -> None:
    """k=6 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(6)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0007_roundtrip() -> None:
    """k=7 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(7)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0008_roundtrip() -> None:
    """k=8 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(8)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0009_roundtrip() -> None:
    """k=9 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(9)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0010_roundtrip() -> None:
    """k=10 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(10)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0011_roundtrip() -> None:
    """k=11 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(11)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0012_roundtrip() -> None:
    """k=12 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(12)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0013_roundtrip() -> None:
    """k=13 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(13)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0014_roundtrip() -> None:
    """k=14 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(14)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0015_roundtrip() -> None:
    """k=15 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(15)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0016_roundtrip() -> None:
    """k=16 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(16)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0017_roundtrip() -> None:
    """k=17 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(17)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0018_roundtrip() -> None:
    """k=18 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(18)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0019_roundtrip() -> None:
    """k=19 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(19)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0020_roundtrip() -> None:
    """k=20 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(20)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0021_roundtrip() -> None:
    """k=21 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(21)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0022_roundtrip() -> None:
    """k=22 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(22)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0023_roundtrip() -> None:
    """k=23 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(23)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0024_roundtrip() -> None:
    """k=24 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(24)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0025_roundtrip() -> None:
    """k=25 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(25)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0026_roundtrip() -> None:
    """k=26 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(26)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0027_roundtrip() -> None:
    """k=27 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(27)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0028_roundtrip() -> None:
    """k=28 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(28)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0029_roundtrip() -> None:
    """k=29 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(29)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0030_roundtrip() -> None:
    """k=30 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(30)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0031_roundtrip() -> None:
    """k=31 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(31)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0032_roundtrip() -> None:
    """k=32 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(32)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0033_roundtrip() -> None:
    """k=33 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(33)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0034_roundtrip() -> None:
    """k=34 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(34)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0035_roundtrip() -> None:
    """k=35 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(35)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0036_roundtrip() -> None:
    """k=36 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(36)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0037_roundtrip() -> None:
    """k=37 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(37)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0038_roundtrip() -> None:
    """k=38 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(38)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0039_roundtrip() -> None:
    """k=39 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(39)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0040_roundtrip() -> None:
    """k=40 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(40)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0041_roundtrip() -> None:
    """k=41 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(41)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0042_roundtrip() -> None:
    """k=42 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(42)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0043_roundtrip() -> None:
    """k=43 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(43)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0044_roundtrip() -> None:
    """k=44 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(44)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0045_roundtrip() -> None:
    """k=45 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(45)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0046_roundtrip() -> None:
    """k=46 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(46)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0047_roundtrip() -> None:
    """k=47 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(47)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0048_roundtrip() -> None:
    """k=48 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(48)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0049_roundtrip() -> None:
    """k=49 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(49)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0050_roundtrip() -> None:
    """k=50 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(50)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0051_roundtrip() -> None:
    """k=51 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(51)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0052_roundtrip() -> None:
    """k=52 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(52)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0053_roundtrip() -> None:
    """k=53 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(53)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0054_roundtrip() -> None:
    """k=54 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(54)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0055_roundtrip() -> None:
    """k=55 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(55)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0056_roundtrip() -> None:
    """k=56 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(56)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0057_roundtrip() -> None:
    """k=57 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(57)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0058_roundtrip() -> None:
    """k=58 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(58)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0059_roundtrip() -> None:
    """k=59 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(59)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0060_roundtrip() -> None:
    """k=60 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(60)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0061_roundtrip() -> None:
    """k=61 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(61)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0062_roundtrip() -> None:
    """k=62 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(62)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0063_roundtrip() -> None:
    """k=63 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(63)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0064_roundtrip() -> None:
    """k=64 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(64)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0065_roundtrip() -> None:
    """k=65 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(65)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0066_roundtrip() -> None:
    """k=66 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(66)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0067_roundtrip() -> None:
    """k=67 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(67)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0068_roundtrip() -> None:
    """k=68 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(68)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0069_roundtrip() -> None:
    """k=69 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(69)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0070_roundtrip() -> None:
    """k=70 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(70)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0071_roundtrip() -> None:
    """k=71 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(71)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0072_roundtrip() -> None:
    """k=72 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(72)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0073_roundtrip() -> None:
    """k=73 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(73)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0074_roundtrip() -> None:
    """k=74 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(74)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0075_roundtrip() -> None:
    """k=75 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(75)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0076_roundtrip() -> None:
    """k=76 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(76)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0077_roundtrip() -> None:
    """k=77 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(77)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0078_roundtrip() -> None:
    """k=78 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(78)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0079_roundtrip() -> None:
    """k=79 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(79)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0080_roundtrip() -> None:
    """k=80 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(80)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0081_roundtrip() -> None:
    """k=81 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(81)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0082_roundtrip() -> None:
    """k=82 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(82)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0083_roundtrip() -> None:
    """k=83 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(83)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0084_roundtrip() -> None:
    """k=84 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(84)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0085_roundtrip() -> None:
    """k=85 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(85)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0086_roundtrip() -> None:
    """k=86 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(86)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0087_roundtrip() -> None:
    """k=87 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(87)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0088_roundtrip() -> None:
    """k=88 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(88)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0089_roundtrip() -> None:
    """k=89 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(89)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0090_roundtrip() -> None:
    """k=90 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(90)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0091_roundtrip() -> None:
    """k=91 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(91)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0092_roundtrip() -> None:
    """k=92 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(92)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0093_roundtrip() -> None:
    """k=93 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(93)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0094_roundtrip() -> None:
    """k=94 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(94)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0095_roundtrip() -> None:
    """k=95 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(95)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0096_roundtrip() -> None:
    """k=96 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(96)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0097_roundtrip() -> None:
    """k=97 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(97)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0098_roundtrip() -> None:
    """k=98 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(98)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0099_roundtrip() -> None:
    """k=99 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(99)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0100_roundtrip() -> None:
    """k=100 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(100)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0101_roundtrip() -> None:
    """k=101 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(101)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0102_roundtrip() -> None:
    """k=102 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(102)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0103_roundtrip() -> None:
    """k=103 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(103)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0104_roundtrip() -> None:
    """k=104 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(104)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0105_roundtrip() -> None:
    """k=105 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(105)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0106_roundtrip() -> None:
    """k=106 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(106)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0107_roundtrip() -> None:
    """k=107 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(107)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0108_roundtrip() -> None:
    """k=108 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(108)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0109_roundtrip() -> None:
    """k=109 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(109)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0110_roundtrip() -> None:
    """k=110 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(110)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0111_roundtrip() -> None:
    """k=111 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(111)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0112_roundtrip() -> None:
    """k=112 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(112)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0113_roundtrip() -> None:
    """k=113 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(113)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0114_roundtrip() -> None:
    """k=114 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(114)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0115_roundtrip() -> None:
    """k=115 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(115)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0116_roundtrip() -> None:
    """k=116 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(116)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0117_roundtrip() -> None:
    """k=117 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(117)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0118_roundtrip() -> None:
    """k=118 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(118)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0119_roundtrip() -> None:
    """k=119 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(119)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0120_roundtrip() -> None:
    """k=120 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(120)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0121_roundtrip() -> None:
    """k=121 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(121)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0122_roundtrip() -> None:
    """k=122 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(122)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0123_roundtrip() -> None:
    """k=123 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(123)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0124_roundtrip() -> None:
    """k=124 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(124)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0125_roundtrip() -> None:
    """k=125 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(125)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0126_roundtrip() -> None:
    """k=126 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(126)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0127_roundtrip() -> None:
    """k=127 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(127)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0128_roundtrip() -> None:
    """k=128 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(128)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0129_roundtrip() -> None:
    """k=129 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(129)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0130_roundtrip() -> None:
    """k=130 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(130)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0131_roundtrip() -> None:
    """k=131 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(131)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0132_roundtrip() -> None:
    """k=132 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(132)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0133_roundtrip() -> None:
    """k=133 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(133)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0134_roundtrip() -> None:
    """k=134 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(134)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0135_roundtrip() -> None:
    """k=135 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(135)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0136_roundtrip() -> None:
    """k=136 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(136)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0137_roundtrip() -> None:
    """k=137 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(137)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0138_roundtrip() -> None:
    """k=138 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(138)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0139_roundtrip() -> None:
    """k=139 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(139)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0140_roundtrip() -> None:
    """k=140 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(140)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0141_roundtrip() -> None:
    """k=141 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(141)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0142_roundtrip() -> None:
    """k=142 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(142)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0143_roundtrip() -> None:
    """k=143 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(143)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0144_roundtrip() -> None:
    """k=144 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(144)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0145_roundtrip() -> None:
    """k=145 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(145)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0146_roundtrip() -> None:
    """k=146 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(146)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0147_roundtrip() -> None:
    """k=147 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(147)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0148_roundtrip() -> None:
    """k=148 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(148)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0149_roundtrip() -> None:
    """k=149 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(149)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0150_roundtrip() -> None:
    """k=150 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(150)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0151_roundtrip() -> None:
    """k=151 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(151)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0152_roundtrip() -> None:
    """k=152 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(152)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0153_roundtrip() -> None:
    """k=153 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(153)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0154_roundtrip() -> None:
    """k=154 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(154)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0155_roundtrip() -> None:
    """k=155 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(155)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0156_roundtrip() -> None:
    """k=156 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(156)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0157_roundtrip() -> None:
    """k=157 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(157)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0158_roundtrip() -> None:
    """k=158 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(158)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0159_roundtrip() -> None:
    """k=159 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(159)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0160_roundtrip() -> None:
    """k=160 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(160)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0161_roundtrip() -> None:
    """k=161 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(161)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0162_roundtrip() -> None:
    """k=162 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(162)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0163_roundtrip() -> None:
    """k=163 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(163)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0164_roundtrip() -> None:
    """k=164 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(164)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0165_roundtrip() -> None:
    """k=165 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(165)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0166_roundtrip() -> None:
    """k=166 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(166)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0167_roundtrip() -> None:
    """k=167 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(167)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0168_roundtrip() -> None:
    """k=168 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(168)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0169_roundtrip() -> None:
    """k=169 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(169)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0170_roundtrip() -> None:
    """k=170 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(170)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0171_roundtrip() -> None:
    """k=171 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(171)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0172_roundtrip() -> None:
    """k=172 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(172)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0173_roundtrip() -> None:
    """k=173 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(173)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0174_roundtrip() -> None:
    """k=174 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(174)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0175_roundtrip() -> None:
    """k=175 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(175)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0176_roundtrip() -> None:
    """k=176 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(176)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0177_roundtrip() -> None:
    """k=177 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(177)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0178_roundtrip() -> None:
    """k=178 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(178)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0179_roundtrip() -> None:
    """k=179 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(179)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0180_roundtrip() -> None:
    """k=180 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(180)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0181_roundtrip() -> None:
    """k=181 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(181)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0182_roundtrip() -> None:
    """k=182 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(182)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0183_roundtrip() -> None:
    """k=183 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(183)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0184_roundtrip() -> None:
    """k=184 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(184)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0185_roundtrip() -> None:
    """k=185 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(185)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0186_roundtrip() -> None:
    """k=186 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(186)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0187_roundtrip() -> None:
    """k=187 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(187)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0188_roundtrip() -> None:
    """k=188 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(188)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0189_roundtrip() -> None:
    """k=189 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(189)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0190_roundtrip() -> None:
    """k=190 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(190)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0191_roundtrip() -> None:
    """k=191 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(191)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0192_roundtrip() -> None:
    """k=192 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(192)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0193_roundtrip() -> None:
    """k=193 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(193)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0194_roundtrip() -> None:
    """k=194 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(194)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0195_roundtrip() -> None:
    """k=195 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(195)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0196_roundtrip() -> None:
    """k=196 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(196)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0197_roundtrip() -> None:
    """k=197 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(197)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0198_roundtrip() -> None:
    """k=198 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(198)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0199_roundtrip() -> None:
    """k=199 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(199)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0200_roundtrip() -> None:
    """k=200 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(200)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0201_roundtrip() -> None:
    """k=201 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(201)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0202_roundtrip() -> None:
    """k=202 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(202)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0203_roundtrip() -> None:
    """k=203 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(203)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0204_roundtrip() -> None:
    """k=204 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(204)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0205_roundtrip() -> None:
    """k=205 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(205)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0206_roundtrip() -> None:
    """k=206 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(206)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0207_roundtrip() -> None:
    """k=207 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(207)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0208_roundtrip() -> None:
    """k=208 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(208)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0209_roundtrip() -> None:
    """k=209 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(209)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0210_roundtrip() -> None:
    """k=210 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(210)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0211_roundtrip() -> None:
    """k=211 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(211)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0212_roundtrip() -> None:
    """k=212 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(212)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0213_roundtrip() -> None:
    """k=213 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(213)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0214_roundtrip() -> None:
    """k=214 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(214)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0215_roundtrip() -> None:
    """k=215 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(215)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0216_roundtrip() -> None:
    """k=216 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(216)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0217_roundtrip() -> None:
    """k=217 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(217)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0218_roundtrip() -> None:
    """k=218 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(218)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0219_roundtrip() -> None:
    """k=219 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(219)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0220_roundtrip() -> None:
    """k=220 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(220)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0221_roundtrip() -> None:
    """k=221 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(221)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0222_roundtrip() -> None:
    """k=222 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(222)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0223_roundtrip() -> None:
    """k=223 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(223)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0224_roundtrip() -> None:
    """k=224 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(224)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0225_roundtrip() -> None:
    """k=225 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(225)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0226_roundtrip() -> None:
    """k=226 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(226)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0227_roundtrip() -> None:
    """k=227 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(227)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0228_roundtrip() -> None:
    """k=228 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(228)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0229_roundtrip() -> None:
    """k=229 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(229)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0230_roundtrip() -> None:
    """k=230 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(230)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0231_roundtrip() -> None:
    """k=231 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(231)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0232_roundtrip() -> None:
    """k=232 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(232)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0233_roundtrip() -> None:
    """k=233 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(233)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0234_roundtrip() -> None:
    """k=234 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(234)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0235_roundtrip() -> None:
    """k=235 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(235)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0236_roundtrip() -> None:
    """k=236 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(236)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0237_roundtrip() -> None:
    """k=237 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(237)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0238_roundtrip() -> None:
    """k=238 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(238)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0239_roundtrip() -> None:
    """k=239 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(239)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0240_roundtrip() -> None:
    """k=240 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(240)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0241_roundtrip() -> None:
    """k=241 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(241)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0242_roundtrip() -> None:
    """k=242 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(242)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0243_roundtrip() -> None:
    """k=243 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(243)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0244_roundtrip() -> None:
    """k=244 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(244)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0245_roundtrip() -> None:
    """k=245 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(245)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0246_roundtrip() -> None:
    """k=246 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(246)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0247_roundtrip() -> None:
    """k=247 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(247)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0248_roundtrip() -> None:
    """k=248 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(248)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0249_roundtrip() -> None:
    """k=249 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(249)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0250_roundtrip() -> None:
    """k=250 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(250)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0251_roundtrip() -> None:
    """k=251 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(251)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0252_roundtrip() -> None:
    """k=252 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(252)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0253_roundtrip() -> None:
    """k=253 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(253)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0254_roundtrip() -> None:
    """k=254 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(254)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0255_roundtrip() -> None:
    """k=255 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(255)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0256_roundtrip() -> None:
    """k=256 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(256)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0257_roundtrip() -> None:
    """k=257 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(257)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0258_roundtrip() -> None:
    """k=258 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(258)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0259_roundtrip() -> None:
    """k=259 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(259)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0260_roundtrip() -> None:
    """k=260 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(260)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0261_roundtrip() -> None:
    """k=261 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(261)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0262_roundtrip() -> None:
    """k=262 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(262)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0263_roundtrip() -> None:
    """k=263 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(263)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0264_roundtrip() -> None:
    """k=264 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(264)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0265_roundtrip() -> None:
    """k=265 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(265)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0266_roundtrip() -> None:
    """k=266 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(266)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0267_roundtrip() -> None:
    """k=267 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(267)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0268_roundtrip() -> None:
    """k=268 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(268)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0269_roundtrip() -> None:
    """k=269 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(269)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0270_roundtrip() -> None:
    """k=270 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(270)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0271_roundtrip() -> None:
    """k=271 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(271)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0272_roundtrip() -> None:
    """k=272 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(272)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0273_roundtrip() -> None:
    """k=273 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(273)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0274_roundtrip() -> None:
    """k=274 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(274)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0275_roundtrip() -> None:
    """k=275 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(275)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0276_roundtrip() -> None:
    """k=276 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(276)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0277_roundtrip() -> None:
    """k=277 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(277)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0278_roundtrip() -> None:
    """k=278 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(278)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0279_roundtrip() -> None:
    """k=279 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(279)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0280_roundtrip() -> None:
    """k=280 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(280)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0281_roundtrip() -> None:
    """k=281 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(281)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0282_roundtrip() -> None:
    """k=282 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(282)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0283_roundtrip() -> None:
    """k=283 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(283)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0284_roundtrip() -> None:
    """k=284 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(284)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0285_roundtrip() -> None:
    """k=285 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(285)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0286_roundtrip() -> None:
    """k=286 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(286)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0287_roundtrip() -> None:
    """k=287 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(287)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0288_roundtrip() -> None:
    """k=288 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(288)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0289_roundtrip() -> None:
    """k=289 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(289)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0290_roundtrip() -> None:
    """k=290 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(290)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0291_roundtrip() -> None:
    """k=291 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(291)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0292_roundtrip() -> None:
    """k=292 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(292)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0293_roundtrip() -> None:
    """k=293 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(293)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0294_roundtrip() -> None:
    """k=294 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(294)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0295_roundtrip() -> None:
    """k=295 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(295)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0296_roundtrip() -> None:
    """k=296 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(296)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0297_roundtrip() -> None:
    """k=297 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(297)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0298_roundtrip() -> None:
    """k=298 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(298)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0299_roundtrip() -> None:
    """k=299 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(299)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0300_roundtrip() -> None:
    """k=300 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(300)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0301_roundtrip() -> None:
    """k=301 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(301)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0302_roundtrip() -> None:
    """k=302 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(302)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0303_roundtrip() -> None:
    """k=303 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(303)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0304_roundtrip() -> None:
    """k=304 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(304)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0305_roundtrip() -> None:
    """k=305 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(305)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0306_roundtrip() -> None:
    """k=306 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(306)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0307_roundtrip() -> None:
    """k=307 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(307)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0308_roundtrip() -> None:
    """k=308 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(308)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0309_roundtrip() -> None:
    """k=309 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(309)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0310_roundtrip() -> None:
    """k=310 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(310)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0311_roundtrip() -> None:
    """k=311 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(311)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0312_roundtrip() -> None:
    """k=312 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(312)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0313_roundtrip() -> None:
    """k=313 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(313)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0314_roundtrip() -> None:
    """k=314 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(314)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0315_roundtrip() -> None:
    """k=315 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(315)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0316_roundtrip() -> None:
    """k=316 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(316)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0317_roundtrip() -> None:
    """k=317 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(317)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0318_roundtrip() -> None:
    """k=318 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(318)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0319_roundtrip() -> None:
    """k=319 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(319)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0320_roundtrip() -> None:
    """k=320 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(320)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0321_roundtrip() -> None:
    """k=321 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(321)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0322_roundtrip() -> None:
    """k=322 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(322)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0323_roundtrip() -> None:
    """k=323 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(323)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0324_roundtrip() -> None:
    """k=324 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(324)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0325_roundtrip() -> None:
    """k=325 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(325)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0326_roundtrip() -> None:
    """k=326 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(326)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0327_roundtrip() -> None:
    """k=327 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(327)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0328_roundtrip() -> None:
    """k=328 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(328)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0329_roundtrip() -> None:
    """k=329 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(329)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0330_roundtrip() -> None:
    """k=330 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(330)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0331_roundtrip() -> None:
    """k=331 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(331)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0332_roundtrip() -> None:
    """k=332 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(332)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0333_roundtrip() -> None:
    """k=333 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(333)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0334_roundtrip() -> None:
    """k=334 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(334)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0335_roundtrip() -> None:
    """k=335 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(335)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0336_roundtrip() -> None:
    """k=336 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(336)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0337_roundtrip() -> None:
    """k=337 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(337)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0338_roundtrip() -> None:
    """k=338 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(338)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0339_roundtrip() -> None:
    """k=339 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(339)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0340_roundtrip() -> None:
    """k=340 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(340)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0341_roundtrip() -> None:
    """k=341 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(341)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0342_roundtrip() -> None:
    """k=342 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(342)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0343_roundtrip() -> None:
    """k=343 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(343)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0344_roundtrip() -> None:
    """k=344 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(344)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0345_roundtrip() -> None:
    """k=345 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(345)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0346_roundtrip() -> None:
    """k=346 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(346)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0347_roundtrip() -> None:
    """k=347 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(347)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0348_roundtrip() -> None:
    """k=348 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(348)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0349_roundtrip() -> None:
    """k=349 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(349)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0350_roundtrip() -> None:
    """k=350 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(350)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0351_roundtrip() -> None:
    """k=351 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(351)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0352_roundtrip() -> None:
    """k=352 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(352)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0353_roundtrip() -> None:
    """k=353 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(353)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0354_roundtrip() -> None:
    """k=354 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(354)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0355_roundtrip() -> None:
    """k=355 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(355)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0356_roundtrip() -> None:
    """k=356 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(356)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0357_roundtrip() -> None:
    """k=357 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(357)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0358_roundtrip() -> None:
    """k=358 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(358)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0359_roundtrip() -> None:
    """k=359 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(359)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0360_roundtrip() -> None:
    """k=360 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(360)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0361_roundtrip() -> None:
    """k=361 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(361)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0362_roundtrip() -> None:
    """k=362 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(362)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0363_roundtrip() -> None:
    """k=363 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(363)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0364_roundtrip() -> None:
    """k=364 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(364)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0365_roundtrip() -> None:
    """k=365 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(365)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0366_roundtrip() -> None:
    """k=366 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(366)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0367_roundtrip() -> None:
    """k=367 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(367)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0368_roundtrip() -> None:
    """k=368 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(368)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0369_roundtrip() -> None:
    """k=369 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(369)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0370_roundtrip() -> None:
    """k=370 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(370)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0371_roundtrip() -> None:
    """k=371 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(371)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0372_roundtrip() -> None:
    """k=372 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(372)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0373_roundtrip() -> None:
    """k=373 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(373)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0374_roundtrip() -> None:
    """k=374 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(374)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0375_roundtrip() -> None:
    """k=375 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(375)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0376_roundtrip() -> None:
    """k=376 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(376)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0377_roundtrip() -> None:
    """k=377 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(377)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0378_roundtrip() -> None:
    """k=378 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(378)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0379_roundtrip() -> None:
    """k=379 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(379)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0380_roundtrip() -> None:
    """k=380 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(380)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0381_roundtrip() -> None:
    """k=381 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(381)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0382_roundtrip() -> None:
    """k=382 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(382)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0383_roundtrip() -> None:
    """k=383 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(383)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0384_roundtrip() -> None:
    """k=384 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(384)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0385_roundtrip() -> None:
    """k=385 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(385)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0386_roundtrip() -> None:
    """k=386 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(386)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0387_roundtrip() -> None:
    """k=387 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(387)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0388_roundtrip() -> None:
    """k=388 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(388)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0389_roundtrip() -> None:
    """k=389 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(389)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0390_roundtrip() -> None:
    """k=390 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(390)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0391_roundtrip() -> None:
    """k=391 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(391)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0392_roundtrip() -> None:
    """k=392 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(392)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0393_roundtrip() -> None:
    """k=393 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(393)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0394_roundtrip() -> None:
    """k=394 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(394)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0395_roundtrip() -> None:
    """k=395 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(395)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0396_roundtrip() -> None:
    """k=396 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(396)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0397_roundtrip() -> None:
    """k=397 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(397)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0398_roundtrip() -> None:
    """k=398 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(398)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0399_roundtrip() -> None:
    """k=399 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(399)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0400_roundtrip() -> None:
    """k=400 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(400)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0401_roundtrip() -> None:
    """k=401 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(401)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0402_roundtrip() -> None:
    """k=402 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(402)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0403_roundtrip() -> None:
    """k=403 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(403)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0404_roundtrip() -> None:
    """k=404 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(404)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0405_roundtrip() -> None:
    """k=405 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(405)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0406_roundtrip() -> None:
    """k=406 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(406)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0407_roundtrip() -> None:
    """k=407 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(407)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0408_roundtrip() -> None:
    """k=408 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(408)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0409_roundtrip() -> None:
    """k=409 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(409)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0410_roundtrip() -> None:
    """k=410 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(410)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0411_roundtrip() -> None:
    """k=411 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(411)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0412_roundtrip() -> None:
    """k=412 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(412)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0413_roundtrip() -> None:
    """k=413 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(413)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0414_roundtrip() -> None:
    """k=414 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(414)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0415_roundtrip() -> None:
    """k=415 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(415)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0416_roundtrip() -> None:
    """k=416 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(416)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0417_roundtrip() -> None:
    """k=417 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(417)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0418_roundtrip() -> None:
    """k=418 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(418)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0419_roundtrip() -> None:
    """k=419 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(419)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0420_roundtrip() -> None:
    """k=420 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(420)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0421_roundtrip() -> None:
    """k=421 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(421)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0422_roundtrip() -> None:
    """k=422 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(422)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0423_roundtrip() -> None:
    """k=423 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(423)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0424_roundtrip() -> None:
    """k=424 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(424)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0425_roundtrip() -> None:
    """k=425 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(425)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0426_roundtrip() -> None:
    """k=426 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(426)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0427_roundtrip() -> None:
    """k=427 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(427)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0428_roundtrip() -> None:
    """k=428 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(428)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0429_roundtrip() -> None:
    """k=429 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(429)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0430_roundtrip() -> None:
    """k=430 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(430)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0431_roundtrip() -> None:
    """k=431 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(431)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0432_roundtrip() -> None:
    """k=432 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(432)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0433_roundtrip() -> None:
    """k=433 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(433)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0434_roundtrip() -> None:
    """k=434 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(434)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0435_roundtrip() -> None:
    """k=435 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(435)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0436_roundtrip() -> None:
    """k=436 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(436)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0437_roundtrip() -> None:
    """k=437 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(437)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0438_roundtrip() -> None:
    """k=438 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(438)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0439_roundtrip() -> None:
    """k=439 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(439)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0440_roundtrip() -> None:
    """k=440 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(440)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0441_roundtrip() -> None:
    """k=441 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(441)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0442_roundtrip() -> None:
    """k=442 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(442)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0443_roundtrip() -> None:
    """k=443 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(443)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0444_roundtrip() -> None:
    """k=444 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(444)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0445_roundtrip() -> None:
    """k=445 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(445)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0446_roundtrip() -> None:
    """k=446 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(446)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0447_roundtrip() -> None:
    """k=447 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(447)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0448_roundtrip() -> None:
    """k=448 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(448)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0449_roundtrip() -> None:
    """k=449 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(449)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0450_roundtrip() -> None:
    """k=450 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(450)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0451_roundtrip() -> None:
    """k=451 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(451)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0452_roundtrip() -> None:
    """k=452 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(452)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0453_roundtrip() -> None:
    """k=453 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(453)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0454_roundtrip() -> None:
    """k=454 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(454)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0455_roundtrip() -> None:
    """k=455 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(455)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0456_roundtrip() -> None:
    """k=456 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(456)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0457_roundtrip() -> None:
    """k=457 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(457)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0458_roundtrip() -> None:
    """k=458 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(458)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0459_roundtrip() -> None:
    """k=459 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(459)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0460_roundtrip() -> None:
    """k=460 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(460)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0461_roundtrip() -> None:
    """k=461 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(461)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0462_roundtrip() -> None:
    """k=462 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(462)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0463_roundtrip() -> None:
    """k=463 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(463)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0464_roundtrip() -> None:
    """k=464 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(464)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0465_roundtrip() -> None:
    """k=465 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(465)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0466_roundtrip() -> None:
    """k=466 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(466)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0467_roundtrip() -> None:
    """k=467 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(467)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0468_roundtrip() -> None:
    """k=468 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(468)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0469_roundtrip() -> None:
    """k=469 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(469)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0470_roundtrip() -> None:
    """k=470 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(470)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0471_roundtrip() -> None:
    """k=471 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(471)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0472_roundtrip() -> None:
    """k=472 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(472)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0473_roundtrip() -> None:
    """k=473 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(473)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0474_roundtrip() -> None:
    """k=474 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(474)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0475_roundtrip() -> None:
    """k=475 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(475)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0476_roundtrip() -> None:
    """k=476 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(476)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0477_roundtrip() -> None:
    """k=477 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(477)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0478_roundtrip() -> None:
    """k=478 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(478)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0479_roundtrip() -> None:
    """k=479 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(479)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0480_roundtrip() -> None:
    """k=480 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(480)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0481_roundtrip() -> None:
    """k=481 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(481)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0482_roundtrip() -> None:
    """k=482 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(482)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0483_roundtrip() -> None:
    """k=483 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(483)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0484_roundtrip() -> None:
    """k=484 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(484)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0485_roundtrip() -> None:
    """k=485 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(485)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0486_roundtrip() -> None:
    """k=486 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(486)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0487_roundtrip() -> None:
    """k=487 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(487)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0488_roundtrip() -> None:
    """k=488 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(488)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0489_roundtrip() -> None:
    """k=489 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(489)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0490_roundtrip() -> None:
    """k=490 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(490)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0491_roundtrip() -> None:
    """k=491 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(491)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0492_roundtrip() -> None:
    """k=492 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(492)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0493_roundtrip() -> None:
    """k=493 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(493)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0494_roundtrip() -> None:
    """k=494 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(494)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0495_roundtrip() -> None:
    """k=495 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(495)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0496_roundtrip() -> None:
    """k=496 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(496)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0497_roundtrip() -> None:
    """k=497 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(497)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0498_roundtrip() -> None:
    """k=498 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(498)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0499_roundtrip() -> None:
    """k=499 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(499)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_many0500_roundtrip() -> None:
    """k=500 unknown chunks before context: reader returns the sealed context verbatim."""
    assert read_context(
        _riff(wav + b''.join(_chunk(bytes([65 + (j % 26)]) * 4, b'\x01\x02') for j in range(500)) + base[len(wav) :])
    ) == {'client_device_id': 'dev-grid-1', 'should_lock': True, 'source': 'omicapture', 'version': 1}


def test_walk_ordOAB0102_typed() -> None:
    """chunk order OAB sizes 79,1,2: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 79)
                )
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 1)
                )
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 2)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_ordOAB0201_typed() -> None:
    """chunk order OAB sizes 79,2,1: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 79)
                )
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 2)
                )
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 1)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_ordOAB0305_typed() -> None:
    """chunk order OAB sizes 79,3,5: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 79)
                )
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 3)
                )
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 5)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_ordOAB0404_typed() -> None:
    """chunk order OAB sizes 79,4,4: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 79)
                )
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 4)
                )
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 4)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_ordOAB0907_typed() -> None:
    """chunk order OAB sizes 79,9,7: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 79)
                )
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 9)
                )
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 7)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_ordAOB0102_typed() -> None:
    """chunk order AOB sizes 79,1,2: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 79)
                )
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 1)
                )
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 2)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_ordAOB0201_typed() -> None:
    """chunk order AOB sizes 79,2,1: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 79)
                )
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 2)
                )
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 1)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_ordAOB0305_typed() -> None:
    """chunk order AOB sizes 79,3,5: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 79)
                )
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 3)
                )
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 5)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_ordAOB0404_typed() -> None:
    """chunk order AOB sizes 79,4,4: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 79)
                )
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 4)
                )
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 4)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_ordAOB0907_typed() -> None:
    """chunk order AOB sizes 79,9,7: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 79)
                )
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 9)
                )
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 7)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_ordABO0102_typed() -> None:
    """chunk order ABO sizes 79,1,2: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 79)
                )
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 1)
                )
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 2)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_ordABO0201_typed() -> None:
    """chunk order ABO sizes 79,2,1: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 79)
                )
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 2)
                )
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 1)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_ordABO0305_typed() -> None:
    """chunk order ABO sizes 79,3,5: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 79)
                )
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 3)
                )
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 5)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_ordABO0404_typed() -> None:
    """chunk order ABO sizes 79,4,4: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 79)
                )
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 4)
                )
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 4)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_ordABO0907_typed() -> None:
    """chunk order ABO sizes 79,9,7: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 79)
                )
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 9)
                )
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 7)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_ordBOA0102_typed() -> None:
    """chunk order BOA sizes 79,1,2: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 79)
                )
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 1)
                )
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 2)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_ordBOA0201_typed() -> None:
    """chunk order BOA sizes 79,2,1: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 79)
                )
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 2)
                )
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 1)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_ordBOA0305_typed() -> None:
    """chunk order BOA sizes 79,3,5: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 79)
                )
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 3)
                )
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 5)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_ordBOA0404_typed() -> None:
    """chunk order BOA sizes 79,4,4: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 79)
                )
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 4)
                )
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 4)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_ordBOA0907_typed() -> None:
    """chunk order BOA sizes 79,9,7: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + (
                    _chunk(b'BBBB', json.dumps(BASE_CONTEXT).encode())
                    if 'BBBB' == 'OMIM'
                    else _chunk(b'BBBB', b'\x03' * 79)
                )
                + (
                    _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                    if 'OMIM' == 'OMIM'
                    else _chunk(b'OMIM', b'\x03' * 9)
                )
                + (
                    _chunk(b'AAAA', json.dumps(BASE_CONTEXT).encode())
                    if 'AAAA' == 'OMIM'
                    else _chunk(b'AAAA', b'\x03' * 7)
                )
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_walk_dup00_typed() -> None:
    """duplicate context chunk, gap 0: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                + _chunk(b'CCCC', b'\x05' * 0)
                + _chunk(b'OMIM', b'{}')
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'duplicate or oversized intake context'


def test_walk_dup01_typed() -> None:
    """duplicate context chunk, gap 1: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                + _chunk(b'CCCC', b'\x05' * 1)
                + _chunk(b'OMIM', b'{}')
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'duplicate or oversized intake context'


def test_walk_dup02_typed() -> None:
    """duplicate context chunk, gap 2: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                + _chunk(b'CCCC', b'\x05' * 2)
                + _chunk(b'OMIM', b'{}')
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'duplicate or oversized intake context'


def test_walk_dup05_typed() -> None:
    """duplicate context chunk, gap 5: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                + _chunk(b'CCCC', b'\x05' * 5)
                + _chunk(b'OMIM', b'{}')
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'duplicate or oversized intake context'


def test_walk_dup09_typed() -> None:
    """duplicate context chunk, gap 9: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
                + _chunk(b'CCCC', b'\x05' * 9)
                + _chunk(b'OMIM', b'{}')
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'duplicate or oversized intake context'


def test_walk_dupB00_typed() -> None:
    """empty context first, real second, gap 0: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + _chunk(b'CCCC', b'\x05' * 0)
                + _chunk(b'OMIM', b'{}')
                + _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'duplicate or oversized intake context'


def test_walk_dupB01_typed() -> None:
    """empty context first, real second, gap 1: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + _chunk(b'CCCC', b'\x05' * 1)
                + _chunk(b'OMIM', b'{}')
                + _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'duplicate or oversized intake context'


def test_walk_dupB03_typed() -> None:
    """empty context first, real second, gap 3: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + _chunk(b'CCCC', b'\x05' * 3)
                + _chunk(b'OMIM', b'{}')
                + _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'duplicate or oversized intake context'


def test_walk_dupB07_typed() -> None:
    """empty context first, real second, gap 7: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(
            _riff(
                wav
                + _chunk(b'CCCC', b'\x05' * 7)
                + _chunk(b'OMIM', b'{}')
                + _chunk(b'OMIM', json.dumps(BASE_CONTEXT).encode())
            )
        )
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'duplicate or oversized intake context'


def test_walk_odds01_roundtrip() -> None:
    """odd unknown chunk size=1 must skip its pad: reader returns the sealed context verbatim."""
    assert read_context(_riff(wav + _chunk(b'BBBB', b'\x07' * 1) + base[len(wav) :])) == {
        'client_device_id': 'dev-grid-1',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_walk_odds03_roundtrip() -> None:
    """odd unknown chunk size=3 must skip its pad: reader returns the sealed context verbatim."""
    assert read_context(_riff(wav + _chunk(b'BBBB', b'\x07' * 3) + base[len(wav) :])) == {
        'client_device_id': 'dev-grid-1',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_walk_odds05_roundtrip() -> None:
    """odd unknown chunk size=5 must skip its pad: reader returns the sealed context verbatim."""
    assert read_context(_riff(wav + _chunk(b'BBBB', b'\x07' * 5) + base[len(wav) :])) == {
        'client_device_id': 'dev-grid-1',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_walk_odds07_roundtrip() -> None:
    """odd unknown chunk size=7 must skip its pad: reader returns the sealed context verbatim."""
    assert read_context(_riff(wav + _chunk(b'BBBB', b'\x07' * 7) + base[len(wav) :])) == {
        'client_device_id': 'dev-grid-1',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_walk_odds09_roundtrip() -> None:
    """odd unknown chunk size=9 must skip its pad: reader returns the sealed context verbatim."""
    assert read_context(_riff(wav + _chunk(b'BBBB', b'\x07' * 9) + base[len(wav) :])) == {
        'client_device_id': 'dev-grid-1',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }


def test_walk_odds11_roundtrip() -> None:
    """odd unknown chunk size=11 must skip its pad: reader returns the sealed context verbatim."""
    assert read_context(_riff(wav + _chunk(b'BBBB', b'\x07' * 11) + base[len(wav) :])) == {
        'client_device_id': 'dev-grid-1',
        'should_lock': True,
        'source': 'omicapture',
        'version': 1,
    }
