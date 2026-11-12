"""Intake envelope trailing-garbage walk grid: frozen verdict per cell.

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


def test_trail_trail0001_typed() -> None:
    """tail=+1B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1 * 7) % 251) for _ in range(1))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_trail_trail0002_typed() -> None:
    """tail=+2B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((2 * 7) % 251) for _ in range(2))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_trail_trail0003_typed() -> None:
    """tail=+3B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((3 * 7) % 251) for _ in range(3))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_trail_trail0004_typed() -> None:
    """tail=+4B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((4 * 7) % 251) for _ in range(4))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_trail_trail0005_typed() -> None:
    """tail=+5B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((5 * 7) % 251) for _ in range(5))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_trail_trail0006_typed() -> None:
    """tail=+6B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((6 * 7) % 251) for _ in range(6))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_trail_trail0007_typed() -> None:
    """tail=+7B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((7 * 7) % 251) for _ in range(7))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_trail_trail0008_typed() -> None:
    """tail=+8B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((8 * 7) % 251) for _ in range(8))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0009_typed() -> None:
    """tail=+9B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((9 * 7) % 251) for _ in range(9))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0010_typed() -> None:
    """tail=+10B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((10 * 7) % 251) for _ in range(10))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0011_typed() -> None:
    """tail=+11B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((11 * 7) % 251) for _ in range(11))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0012_typed() -> None:
    """tail=+12B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((12 * 7) % 251) for _ in range(12))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0013_typed() -> None:
    """tail=+13B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((13 * 7) % 251) for _ in range(13))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0014_typed() -> None:
    """tail=+14B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((14 * 7) % 251) for _ in range(14))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0015_typed() -> None:
    """tail=+15B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((15 * 7) % 251) for _ in range(15))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0016_typed() -> None:
    """tail=+16B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((16 * 7) % 251) for _ in range(16))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0017_typed() -> None:
    """tail=+17B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((17 * 7) % 251) for _ in range(17))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0018_typed() -> None:
    """tail=+18B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((18 * 7) % 251) for _ in range(18))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0019_typed() -> None:
    """tail=+19B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((19 * 7) % 251) for _ in range(19))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0020_typed() -> None:
    """tail=+20B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((20 * 7) % 251) for _ in range(20))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0021_typed() -> None:
    """tail=+21B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((21 * 7) % 251) for _ in range(21))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0022_typed() -> None:
    """tail=+22B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((22 * 7) % 251) for _ in range(22))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0023_typed() -> None:
    """tail=+23B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((23 * 7) % 251) for _ in range(23))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0024_typed() -> None:
    """tail=+24B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((24 * 7) % 251) for _ in range(24))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0025_typed() -> None:
    """tail=+25B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((25 * 7) % 251) for _ in range(25))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0026_typed() -> None:
    """tail=+26B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((26 * 7) % 251) for _ in range(26))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0027_typed() -> None:
    """tail=+27B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((27 * 7) % 251) for _ in range(27))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0028_typed() -> None:
    """tail=+28B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((28 * 7) % 251) for _ in range(28))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0029_typed() -> None:
    """tail=+29B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((29 * 7) % 251) for _ in range(29))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0030_typed() -> None:
    """tail=+30B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((30 * 7) % 251) for _ in range(30))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0031_typed() -> None:
    """tail=+31B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((31 * 7) % 251) for _ in range(31))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0032_typed() -> None:
    """tail=+32B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((32 * 7) % 251) for _ in range(32))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0033_typed() -> None:
    """tail=+33B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((33 * 7) % 251) for _ in range(33))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0034_typed() -> None:
    """tail=+34B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((34 * 7) % 251) for _ in range(34))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0035_typed() -> None:
    """tail=+35B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((35 * 7) % 251) for _ in range(35))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0036_typed() -> None:
    """tail=+36B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((36 * 7) % 251) for _ in range(36))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0037_typed() -> None:
    """tail=+37B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((37 * 7) % 251) for _ in range(37))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0038_typed() -> None:
    """tail=+38B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((38 * 7) % 251) for _ in range(38))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0039_typed() -> None:
    """tail=+39B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((39 * 7) % 251) for _ in range(39))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0040_typed() -> None:
    """tail=+40B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((40 * 7) % 251) for _ in range(40))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0041_typed() -> None:
    """tail=+41B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((41 * 7) % 251) for _ in range(41))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0042_typed() -> None:
    """tail=+42B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((42 * 7) % 251) for _ in range(42))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0043_typed() -> None:
    """tail=+43B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((43 * 7) % 251) for _ in range(43))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0044_typed() -> None:
    """tail=+44B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((44 * 7) % 251) for _ in range(44))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0045_typed() -> None:
    """tail=+45B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((45 * 7) % 251) for _ in range(45))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0046_typed() -> None:
    """tail=+46B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((46 * 7) % 251) for _ in range(46))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0047_typed() -> None:
    """tail=+47B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((47 * 7) % 251) for _ in range(47))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0048_typed() -> None:
    """tail=+48B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((48 * 7) % 251) for _ in range(48))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0049_typed() -> None:
    """tail=+49B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((49 * 7) % 251) for _ in range(49))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0050_typed() -> None:
    """tail=+50B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((50 * 7) % 251) for _ in range(50))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0051_typed() -> None:
    """tail=+51B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((51 * 7) % 251) for _ in range(51))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0052_typed() -> None:
    """tail=+52B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((52 * 7) % 251) for _ in range(52))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0053_typed() -> None:
    """tail=+53B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((53 * 7) % 251) for _ in range(53))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0054_typed() -> None:
    """tail=+54B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((54 * 7) % 251) for _ in range(54))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0055_typed() -> None:
    """tail=+55B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((55 * 7) % 251) for _ in range(55))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0056_typed() -> None:
    """tail=+56B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((56 * 7) % 251) for _ in range(56))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0057_typed() -> None:
    """tail=+57B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((57 * 7) % 251) for _ in range(57))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0058_typed() -> None:
    """tail=+58B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((58 * 7) % 251) for _ in range(58))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0059_typed() -> None:
    """tail=+59B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((59 * 7) % 251) for _ in range(59))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0060_typed() -> None:
    """tail=+60B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((60 * 7) % 251) for _ in range(60))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0061_typed() -> None:
    """tail=+61B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((61 * 7) % 251) for _ in range(61))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0062_typed() -> None:
    """tail=+62B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((62 * 7) % 251) for _ in range(62))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0063_typed() -> None:
    """tail=+63B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((63 * 7) % 251) for _ in range(63))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0064_typed() -> None:
    """tail=+64B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((64 * 7) % 251) for _ in range(64))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0065_typed() -> None:
    """tail=+65B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((65 * 7) % 251) for _ in range(65))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0066_typed() -> None:
    """tail=+66B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((66 * 7) % 251) for _ in range(66))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0067_typed() -> None:
    """tail=+67B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((67 * 7) % 251) for _ in range(67))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0068_typed() -> None:
    """tail=+68B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((68 * 7) % 251) for _ in range(68))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0069_typed() -> None:
    """tail=+69B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((69 * 7) % 251) for _ in range(69))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0070_typed() -> None:
    """tail=+70B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((70 * 7) % 251) for _ in range(70))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0071_typed() -> None:
    """tail=+71B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((71 * 7) % 251) for _ in range(71))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0072_typed() -> None:
    """tail=+72B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((72 * 7) % 251) for _ in range(72))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0073_typed() -> None:
    """tail=+73B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((73 * 7) % 251) for _ in range(73))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0074_typed() -> None:
    """tail=+74B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((74 * 7) % 251) for _ in range(74))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0075_typed() -> None:
    """tail=+75B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((75 * 7) % 251) for _ in range(75))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0076_typed() -> None:
    """tail=+76B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((76 * 7) % 251) for _ in range(76))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0077_typed() -> None:
    """tail=+77B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((77 * 7) % 251) for _ in range(77))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0078_typed() -> None:
    """tail=+78B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((78 * 7) % 251) for _ in range(78))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0079_typed() -> None:
    """tail=+79B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((79 * 7) % 251) for _ in range(79))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0080_typed() -> None:
    """tail=+80B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((80 * 7) % 251) for _ in range(80))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0081_typed() -> None:
    """tail=+81B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((81 * 7) % 251) for _ in range(81))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0082_typed() -> None:
    """tail=+82B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((82 * 7) % 251) for _ in range(82))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0083_typed() -> None:
    """tail=+83B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((83 * 7) % 251) for _ in range(83))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0084_typed() -> None:
    """tail=+84B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((84 * 7) % 251) for _ in range(84))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0085_typed() -> None:
    """tail=+85B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((85 * 7) % 251) for _ in range(85))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0086_typed() -> None:
    """tail=+86B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((86 * 7) % 251) for _ in range(86))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0087_typed() -> None:
    """tail=+87B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((87 * 7) % 251) for _ in range(87))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0088_typed() -> None:
    """tail=+88B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((88 * 7) % 251) for _ in range(88))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0089_typed() -> None:
    """tail=+89B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((89 * 7) % 251) for _ in range(89))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0090_typed() -> None:
    """tail=+90B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((90 * 7) % 251) for _ in range(90))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0091_typed() -> None:
    """tail=+91B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((91 * 7) % 251) for _ in range(91))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0092_typed() -> None:
    """tail=+92B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((92 * 7) % 251) for _ in range(92))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0093_typed() -> None:
    """tail=+93B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((93 * 7) % 251) for _ in range(93))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0094_typed() -> None:
    """tail=+94B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((94 * 7) % 251) for _ in range(94))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0095_typed() -> None:
    """tail=+95B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((95 * 7) % 251) for _ in range(95))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0096_typed() -> None:
    """tail=+96B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((96 * 7) % 251) for _ in range(96))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0097_typed() -> None:
    """tail=+97B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((97 * 7) % 251) for _ in range(97))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0098_typed() -> None:
    """tail=+98B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((98 * 7) % 251) for _ in range(98))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0099_typed() -> None:
    """tail=+99B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((99 * 7) % 251) for _ in range(99))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0100_typed() -> None:
    """tail=+100B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((100 * 7) % 251) for _ in range(100))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0101_typed() -> None:
    """tail=+101B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((101 * 7) % 251) for _ in range(101))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0102_typed() -> None:
    """tail=+102B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((102 * 7) % 251) for _ in range(102))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0103_typed() -> None:
    """tail=+103B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((103 * 7) % 251) for _ in range(103))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0104_typed() -> None:
    """tail=+104B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((104 * 7) % 251) for _ in range(104))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0105_typed() -> None:
    """tail=+105B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((105 * 7) % 251) for _ in range(105))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0106_typed() -> None:
    """tail=+106B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((106 * 7) % 251) for _ in range(106))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0107_typed() -> None:
    """tail=+107B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((107 * 7) % 251) for _ in range(107))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0108_typed() -> None:
    """tail=+108B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((108 * 7) % 251) for _ in range(108))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0109_typed() -> None:
    """tail=+109B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((109 * 7) % 251) for _ in range(109))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0110_typed() -> None:
    """tail=+110B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((110 * 7) % 251) for _ in range(110))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0111_typed() -> None:
    """tail=+111B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((111 * 7) % 251) for _ in range(111))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0112_typed() -> None:
    """tail=+112B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((112 * 7) % 251) for _ in range(112))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0113_typed() -> None:
    """tail=+113B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((113 * 7) % 251) for _ in range(113))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0114_typed() -> None:
    """tail=+114B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((114 * 7) % 251) for _ in range(114))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0115_typed() -> None:
    """tail=+115B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((115 * 7) % 251) for _ in range(115))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0116_typed() -> None:
    """tail=+116B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((116 * 7) % 251) for _ in range(116))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0117_typed() -> None:
    """tail=+117B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((117 * 7) % 251) for _ in range(117))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0118_typed() -> None:
    """tail=+118B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((118 * 7) % 251) for _ in range(118))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0119_typed() -> None:
    """tail=+119B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((119 * 7) % 251) for _ in range(119))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0120_typed() -> None:
    """tail=+120B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((120 * 7) % 251) for _ in range(120))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0121_typed() -> None:
    """tail=+121B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((121 * 7) % 251) for _ in range(121))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0122_typed() -> None:
    """tail=+122B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((122 * 7) % 251) for _ in range(122))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0123_typed() -> None:
    """tail=+123B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((123 * 7) % 251) for _ in range(123))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0124_typed() -> None:
    """tail=+124B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((124 * 7) % 251) for _ in range(124))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0125_typed() -> None:
    """tail=+125B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((125 * 7) % 251) for _ in range(125))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0126_typed() -> None:
    """tail=+126B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((126 * 7) % 251) for _ in range(126))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0127_typed() -> None:
    """tail=+127B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((127 * 7) % 251) for _ in range(127))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0128_typed() -> None:
    """tail=+128B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((128 * 7) % 251) for _ in range(128))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0129_typed() -> None:
    """tail=+129B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((129 * 7) % 251) for _ in range(129))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0130_typed() -> None:
    """tail=+130B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((130 * 7) % 251) for _ in range(130))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0131_typed() -> None:
    """tail=+131B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((131 * 7) % 251) for _ in range(131))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0132_typed() -> None:
    """tail=+132B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((132 * 7) % 251) for _ in range(132))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0133_typed() -> None:
    """tail=+133B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((133 * 7) % 251) for _ in range(133))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0134_typed() -> None:
    """tail=+134B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((134 * 7) % 251) for _ in range(134))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0135_typed() -> None:
    """tail=+135B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((135 * 7) % 251) for _ in range(135))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0136_typed() -> None:
    """tail=+136B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((136 * 7) % 251) for _ in range(136))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0137_typed() -> None:
    """tail=+137B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((137 * 7) % 251) for _ in range(137))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0138_typed() -> None:
    """tail=+138B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((138 * 7) % 251) for _ in range(138))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0139_typed() -> None:
    """tail=+139B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((139 * 7) % 251) for _ in range(139))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0140_typed() -> None:
    """tail=+140B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((140 * 7) % 251) for _ in range(140))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0141_typed() -> None:
    """tail=+141B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((141 * 7) % 251) for _ in range(141))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0142_typed() -> None:
    """tail=+142B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((142 * 7) % 251) for _ in range(142))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0143_typed() -> None:
    """tail=+143B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((143 * 7) % 251) for _ in range(143))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0144_typed() -> None:
    """tail=+144B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((144 * 7) % 251) for _ in range(144))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0145_typed() -> None:
    """tail=+145B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((145 * 7) % 251) for _ in range(145))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0146_typed() -> None:
    """tail=+146B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((146 * 7) % 251) for _ in range(146))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0147_typed() -> None:
    """tail=+147B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((147 * 7) % 251) for _ in range(147))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0148_typed() -> None:
    """tail=+148B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((148 * 7) % 251) for _ in range(148))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0149_typed() -> None:
    """tail=+149B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((149 * 7) % 251) for _ in range(149))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0150_typed() -> None:
    """tail=+150B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((150 * 7) % 251) for _ in range(150))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0151_typed() -> None:
    """tail=+151B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((151 * 7) % 251) for _ in range(151))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0152_typed() -> None:
    """tail=+152B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((152 * 7) % 251) for _ in range(152))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0153_typed() -> None:
    """tail=+153B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((153 * 7) % 251) for _ in range(153))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0154_typed() -> None:
    """tail=+154B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((154 * 7) % 251) for _ in range(154))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0155_typed() -> None:
    """tail=+155B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((155 * 7) % 251) for _ in range(155))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0156_typed() -> None:
    """tail=+156B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((156 * 7) % 251) for _ in range(156))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0157_typed() -> None:
    """tail=+157B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((157 * 7) % 251) for _ in range(157))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0158_typed() -> None:
    """tail=+158B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((158 * 7) % 251) for _ in range(158))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0159_typed() -> None:
    """tail=+159B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((159 * 7) % 251) for _ in range(159))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0160_typed() -> None:
    """tail=+160B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((160 * 7) % 251) for _ in range(160))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0161_typed() -> None:
    """tail=+161B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((161 * 7) % 251) for _ in range(161))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0162_typed() -> None:
    """tail=+162B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((162 * 7) % 251) for _ in range(162))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0163_typed() -> None:
    """tail=+163B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((163 * 7) % 251) for _ in range(163))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0164_typed() -> None:
    """tail=+164B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((164 * 7) % 251) for _ in range(164))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0165_typed() -> None:
    """tail=+165B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((165 * 7) % 251) for _ in range(165))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0166_typed() -> None:
    """tail=+166B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((166 * 7) % 251) for _ in range(166))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0167_typed() -> None:
    """tail=+167B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((167 * 7) % 251) for _ in range(167))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0168_typed() -> None:
    """tail=+168B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((168 * 7) % 251) for _ in range(168))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0169_typed() -> None:
    """tail=+169B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((169 * 7) % 251) for _ in range(169))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0170_typed() -> None:
    """tail=+170B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((170 * 7) % 251) for _ in range(170))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0171_typed() -> None:
    """tail=+171B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((171 * 7) % 251) for _ in range(171))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0172_typed() -> None:
    """tail=+172B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((172 * 7) % 251) for _ in range(172))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0173_typed() -> None:
    """tail=+173B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((173 * 7) % 251) for _ in range(173))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0174_typed() -> None:
    """tail=+174B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((174 * 7) % 251) for _ in range(174))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0175_typed() -> None:
    """tail=+175B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((175 * 7) % 251) for _ in range(175))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0176_typed() -> None:
    """tail=+176B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((176 * 7) % 251) for _ in range(176))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0177_typed() -> None:
    """tail=+177B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((177 * 7) % 251) for _ in range(177))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0178_typed() -> None:
    """tail=+178B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((178 * 7) % 251) for _ in range(178))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0179_typed() -> None:
    """tail=+179B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((179 * 7) % 251) for _ in range(179))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0180_typed() -> None:
    """tail=+180B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((180 * 7) % 251) for _ in range(180))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0181_typed() -> None:
    """tail=+181B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((181 * 7) % 251) for _ in range(181))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0182_typed() -> None:
    """tail=+182B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((182 * 7) % 251) for _ in range(182))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0183_typed() -> None:
    """tail=+183B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((183 * 7) % 251) for _ in range(183))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0184_typed() -> None:
    """tail=+184B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((184 * 7) % 251) for _ in range(184))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0185_typed() -> None:
    """tail=+185B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((185 * 7) % 251) for _ in range(185))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0186_typed() -> None:
    """tail=+186B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((186 * 7) % 251) for _ in range(186))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0187_typed() -> None:
    """tail=+187B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((187 * 7) % 251) for _ in range(187))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0188_typed() -> None:
    """tail=+188B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((188 * 7) % 251) for _ in range(188))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0189_typed() -> None:
    """tail=+189B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((189 * 7) % 251) for _ in range(189))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0190_typed() -> None:
    """tail=+190B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((190 * 7) % 251) for _ in range(190))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0191_typed() -> None:
    """tail=+191B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((191 * 7) % 251) for _ in range(191))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0192_typed() -> None:
    """tail=+192B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((192 * 7) % 251) for _ in range(192))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0193_typed() -> None:
    """tail=+193B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((193 * 7) % 251) for _ in range(193))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0194_typed() -> None:
    """tail=+194B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((194 * 7) % 251) for _ in range(194))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0195_typed() -> None:
    """tail=+195B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((195 * 7) % 251) for _ in range(195))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0196_typed() -> None:
    """tail=+196B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((196 * 7) % 251) for _ in range(196))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0197_typed() -> None:
    """tail=+197B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((197 * 7) % 251) for _ in range(197))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0198_typed() -> None:
    """tail=+198B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((198 * 7) % 251) for _ in range(198))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0199_typed() -> None:
    """tail=+199B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((199 * 7) % 251) for _ in range(199))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0200_typed() -> None:
    """tail=+200B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((200 * 7) % 251) for _ in range(200))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0201_typed() -> None:
    """tail=+201B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((201 * 7) % 251) for _ in range(201))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0202_typed() -> None:
    """tail=+202B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((202 * 7) % 251) for _ in range(202))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0203_typed() -> None:
    """tail=+203B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((203 * 7) % 251) for _ in range(203))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0204_typed() -> None:
    """tail=+204B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((204 * 7) % 251) for _ in range(204))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0205_typed() -> None:
    """tail=+205B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((205 * 7) % 251) for _ in range(205))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0206_typed() -> None:
    """tail=+206B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((206 * 7) % 251) for _ in range(206))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0207_typed() -> None:
    """tail=+207B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((207 * 7) % 251) for _ in range(207))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0208_typed() -> None:
    """tail=+208B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((208 * 7) % 251) for _ in range(208))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0209_typed() -> None:
    """tail=+209B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((209 * 7) % 251) for _ in range(209))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0210_typed() -> None:
    """tail=+210B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((210 * 7) % 251) for _ in range(210))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0211_typed() -> None:
    """tail=+211B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((211 * 7) % 251) for _ in range(211))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0212_typed() -> None:
    """tail=+212B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((212 * 7) % 251) for _ in range(212))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0213_typed() -> None:
    """tail=+213B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((213 * 7) % 251) for _ in range(213))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0214_typed() -> None:
    """tail=+214B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((214 * 7) % 251) for _ in range(214))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0215_typed() -> None:
    """tail=+215B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((215 * 7) % 251) for _ in range(215))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0216_typed() -> None:
    """tail=+216B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((216 * 7) % 251) for _ in range(216))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0217_typed() -> None:
    """tail=+217B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((217 * 7) % 251) for _ in range(217))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0218_typed() -> None:
    """tail=+218B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((218 * 7) % 251) for _ in range(218))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0219_typed() -> None:
    """tail=+219B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((219 * 7) % 251) for _ in range(219))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0220_typed() -> None:
    """tail=+220B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((220 * 7) % 251) for _ in range(220))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0221_typed() -> None:
    """tail=+221B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((221 * 7) % 251) for _ in range(221))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0222_typed() -> None:
    """tail=+222B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((222 * 7) % 251) for _ in range(222))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0223_typed() -> None:
    """tail=+223B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((223 * 7) % 251) for _ in range(223))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0224_typed() -> None:
    """tail=+224B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((224 * 7) % 251) for _ in range(224))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0225_typed() -> None:
    """tail=+225B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((225 * 7) % 251) for _ in range(225))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0226_typed() -> None:
    """tail=+226B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((226 * 7) % 251) for _ in range(226))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0227_typed() -> None:
    """tail=+227B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((227 * 7) % 251) for _ in range(227))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0228_typed() -> None:
    """tail=+228B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((228 * 7) % 251) for _ in range(228))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0229_typed() -> None:
    """tail=+229B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((229 * 7) % 251) for _ in range(229))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0230_typed() -> None:
    """tail=+230B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((230 * 7) % 251) for _ in range(230))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0231_typed() -> None:
    """tail=+231B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((231 * 7) % 251) for _ in range(231))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0232_typed() -> None:
    """tail=+232B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((232 * 7) % 251) for _ in range(232))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0233_typed() -> None:
    """tail=+233B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((233 * 7) % 251) for _ in range(233))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0234_typed() -> None:
    """tail=+234B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((234 * 7) % 251) for _ in range(234))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0235_typed() -> None:
    """tail=+235B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((235 * 7) % 251) for _ in range(235))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0236_typed() -> None:
    """tail=+236B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((236 * 7) % 251) for _ in range(236))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0237_typed() -> None:
    """tail=+237B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((237 * 7) % 251) for _ in range(237))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0238_typed() -> None:
    """tail=+238B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((238 * 7) % 251) for _ in range(238))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0239_typed() -> None:
    """tail=+239B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((239 * 7) % 251) for _ in range(239))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0240_typed() -> None:
    """tail=+240B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((240 * 7) % 251) for _ in range(240))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0241_typed() -> None:
    """tail=+241B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((241 * 7) % 251) for _ in range(241))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0242_typed() -> None:
    """tail=+242B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((242 * 7) % 251) for _ in range(242))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0243_typed() -> None:
    """tail=+243B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((243 * 7) % 251) for _ in range(243))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0244_typed() -> None:
    """tail=+244B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((244 * 7) % 251) for _ in range(244))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0245_typed() -> None:
    """tail=+245B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((245 * 7) % 251) for _ in range(245))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0246_typed() -> None:
    """tail=+246B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((246 * 7) % 251) for _ in range(246))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0247_typed() -> None:
    """tail=+247B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((247 * 7) % 251) for _ in range(247))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0248_typed() -> None:
    """tail=+248B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((248 * 7) % 251) for _ in range(248))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0249_typed() -> None:
    """tail=+249B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((249 * 7) % 251) for _ in range(249))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0250_typed() -> None:
    """tail=+250B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((250 * 7) % 251) for _ in range(250))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0251_typed() -> None:
    """tail=+251B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((251 * 7) % 251) for _ in range(251))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_trail_trail0252_typed() -> None:
    """tail=+252B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((252 * 7) % 251) for _ in range(252))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0253_typed() -> None:
    """tail=+253B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((253 * 7) % 251) for _ in range(253))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0254_typed() -> None:
    """tail=+254B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((254 * 7) % 251) for _ in range(254))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0255_typed() -> None:
    """tail=+255B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((255 * 7) % 251) for _ in range(255))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0256_typed() -> None:
    """tail=+256B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((256 * 7) % 251) for _ in range(256))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0257_typed() -> None:
    """tail=+257B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((257 * 7) % 251) for _ in range(257))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0258_typed() -> None:
    """tail=+258B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((258 * 7) % 251) for _ in range(258))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0259_typed() -> None:
    """tail=+259B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((259 * 7) % 251) for _ in range(259))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0260_typed() -> None:
    """tail=+260B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((260 * 7) % 251) for _ in range(260))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0261_typed() -> None:
    """tail=+261B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((261 * 7) % 251) for _ in range(261))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0262_typed() -> None:
    """tail=+262B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((262 * 7) % 251) for _ in range(262))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0263_typed() -> None:
    """tail=+263B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((263 * 7) % 251) for _ in range(263))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0264_typed() -> None:
    """tail=+264B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((264 * 7) % 251) for _ in range(264))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0265_typed() -> None:
    """tail=+265B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((265 * 7) % 251) for _ in range(265))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0266_typed() -> None:
    """tail=+266B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((266 * 7) % 251) for _ in range(266))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0267_typed() -> None:
    """tail=+267B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((267 * 7) % 251) for _ in range(267))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0268_typed() -> None:
    """tail=+268B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((268 * 7) % 251) for _ in range(268))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0269_typed() -> None:
    """tail=+269B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((269 * 7) % 251) for _ in range(269))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0270_typed() -> None:
    """tail=+270B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((270 * 7) % 251) for _ in range(270))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0271_typed() -> None:
    """tail=+271B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((271 * 7) % 251) for _ in range(271))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0272_typed() -> None:
    """tail=+272B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((272 * 7) % 251) for _ in range(272))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0273_typed() -> None:
    """tail=+273B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((273 * 7) % 251) for _ in range(273))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0274_typed() -> None:
    """tail=+274B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((274 * 7) % 251) for _ in range(274))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0275_typed() -> None:
    """tail=+275B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((275 * 7) % 251) for _ in range(275))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0276_typed() -> None:
    """tail=+276B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((276 * 7) % 251) for _ in range(276))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0277_typed() -> None:
    """tail=+277B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((277 * 7) % 251) for _ in range(277))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0278_typed() -> None:
    """tail=+278B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((278 * 7) % 251) for _ in range(278))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0279_typed() -> None:
    """tail=+279B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((279 * 7) % 251) for _ in range(279))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0280_typed() -> None:
    """tail=+280B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((280 * 7) % 251) for _ in range(280))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0281_typed() -> None:
    """tail=+281B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((281 * 7) % 251) for _ in range(281))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0282_typed() -> None:
    """tail=+282B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((282 * 7) % 251) for _ in range(282))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0283_typed() -> None:
    """tail=+283B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((283 * 7) % 251) for _ in range(283))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0284_typed() -> None:
    """tail=+284B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((284 * 7) % 251) for _ in range(284))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0285_typed() -> None:
    """tail=+285B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((285 * 7) % 251) for _ in range(285))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0286_typed() -> None:
    """tail=+286B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((286 * 7) % 251) for _ in range(286))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0287_typed() -> None:
    """tail=+287B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((287 * 7) % 251) for _ in range(287))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0288_typed() -> None:
    """tail=+288B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((288 * 7) % 251) for _ in range(288))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0289_typed() -> None:
    """tail=+289B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((289 * 7) % 251) for _ in range(289))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0290_typed() -> None:
    """tail=+290B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((290 * 7) % 251) for _ in range(290))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0291_typed() -> None:
    """tail=+291B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((291 * 7) % 251) for _ in range(291))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0292_typed() -> None:
    """tail=+292B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((292 * 7) % 251) for _ in range(292))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0293_typed() -> None:
    """tail=+293B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((293 * 7) % 251) for _ in range(293))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0294_typed() -> None:
    """tail=+294B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((294 * 7) % 251) for _ in range(294))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0295_typed() -> None:
    """tail=+295B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((295 * 7) % 251) for _ in range(295))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0296_typed() -> None:
    """tail=+296B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((296 * 7) % 251) for _ in range(296))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0297_typed() -> None:
    """tail=+297B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((297 * 7) % 251) for _ in range(297))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0298_typed() -> None:
    """tail=+298B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((298 * 7) % 251) for _ in range(298))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0299_typed() -> None:
    """tail=+299B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((299 * 7) % 251) for _ in range(299))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0300_typed() -> None:
    """tail=+300B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((300 * 7) % 251) for _ in range(300))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0301_typed() -> None:
    """tail=+301B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((301 * 7) % 251) for _ in range(301))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0302_typed() -> None:
    """tail=+302B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((302 * 7) % 251) for _ in range(302))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0303_typed() -> None:
    """tail=+303B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((303 * 7) % 251) for _ in range(303))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0304_typed() -> None:
    """tail=+304B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((304 * 7) % 251) for _ in range(304))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0305_typed() -> None:
    """tail=+305B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((305 * 7) % 251) for _ in range(305))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0306_typed() -> None:
    """tail=+306B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((306 * 7) % 251) for _ in range(306))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0307_typed() -> None:
    """tail=+307B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((307 * 7) % 251) for _ in range(307))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0308_typed() -> None:
    """tail=+308B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((308 * 7) % 251) for _ in range(308))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0309_typed() -> None:
    """tail=+309B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((309 * 7) % 251) for _ in range(309))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0310_typed() -> None:
    """tail=+310B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((310 * 7) % 251) for _ in range(310))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0311_typed() -> None:
    """tail=+311B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((311 * 7) % 251) for _ in range(311))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0312_typed() -> None:
    """tail=+312B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((312 * 7) % 251) for _ in range(312))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0313_typed() -> None:
    """tail=+313B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((313 * 7) % 251) for _ in range(313))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0314_typed() -> None:
    """tail=+314B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((314 * 7) % 251) for _ in range(314))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0315_typed() -> None:
    """tail=+315B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((315 * 7) % 251) for _ in range(315))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0316_typed() -> None:
    """tail=+316B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((316 * 7) % 251) for _ in range(316))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0317_typed() -> None:
    """tail=+317B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((317 * 7) % 251) for _ in range(317))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0318_typed() -> None:
    """tail=+318B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((318 * 7) % 251) for _ in range(318))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0319_typed() -> None:
    """tail=+319B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((319 * 7) % 251) for _ in range(319))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0320_typed() -> None:
    """tail=+320B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((320 * 7) % 251) for _ in range(320))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0321_typed() -> None:
    """tail=+321B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((321 * 7) % 251) for _ in range(321))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0322_typed() -> None:
    """tail=+322B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((322 * 7) % 251) for _ in range(322))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0323_typed() -> None:
    """tail=+323B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((323 * 7) % 251) for _ in range(323))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0324_typed() -> None:
    """tail=+324B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((324 * 7) % 251) for _ in range(324))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0325_typed() -> None:
    """tail=+325B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((325 * 7) % 251) for _ in range(325))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0326_typed() -> None:
    """tail=+326B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((326 * 7) % 251) for _ in range(326))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0327_typed() -> None:
    """tail=+327B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((327 * 7) % 251) for _ in range(327))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0328_typed() -> None:
    """tail=+328B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((328 * 7) % 251) for _ in range(328))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0329_typed() -> None:
    """tail=+329B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((329 * 7) % 251) for _ in range(329))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0330_typed() -> None:
    """tail=+330B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((330 * 7) % 251) for _ in range(330))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0331_typed() -> None:
    """tail=+331B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((331 * 7) % 251) for _ in range(331))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0332_typed() -> None:
    """tail=+332B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((332 * 7) % 251) for _ in range(332))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0333_typed() -> None:
    """tail=+333B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((333 * 7) % 251) for _ in range(333))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0334_typed() -> None:
    """tail=+334B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((334 * 7) % 251) for _ in range(334))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0335_typed() -> None:
    """tail=+335B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((335 * 7) % 251) for _ in range(335))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0336_typed() -> None:
    """tail=+336B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((336 * 7) % 251) for _ in range(336))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0337_typed() -> None:
    """tail=+337B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((337 * 7) % 251) for _ in range(337))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0338_typed() -> None:
    """tail=+338B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((338 * 7) % 251) for _ in range(338))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0339_typed() -> None:
    """tail=+339B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((339 * 7) % 251) for _ in range(339))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0340_typed() -> None:
    """tail=+340B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((340 * 7) % 251) for _ in range(340))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0341_typed() -> None:
    """tail=+341B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((341 * 7) % 251) for _ in range(341))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0342_typed() -> None:
    """tail=+342B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((342 * 7) % 251) for _ in range(342))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0343_typed() -> None:
    """tail=+343B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((343 * 7) % 251) for _ in range(343))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0344_typed() -> None:
    """tail=+344B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((344 * 7) % 251) for _ in range(344))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0345_typed() -> None:
    """tail=+345B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((345 * 7) % 251) for _ in range(345))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0346_typed() -> None:
    """tail=+346B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((346 * 7) % 251) for _ in range(346))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0347_typed() -> None:
    """tail=+347B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((347 * 7) % 251) for _ in range(347))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0348_typed() -> None:
    """tail=+348B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((348 * 7) % 251) for _ in range(348))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0349_typed() -> None:
    """tail=+349B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((349 * 7) % 251) for _ in range(349))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0350_typed() -> None:
    """tail=+350B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((350 * 7) % 251) for _ in range(350))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0351_typed() -> None:
    """tail=+351B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((351 * 7) % 251) for _ in range(351))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0352_typed() -> None:
    """tail=+352B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((352 * 7) % 251) for _ in range(352))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0353_typed() -> None:
    """tail=+353B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((353 * 7) % 251) for _ in range(353))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0354_typed() -> None:
    """tail=+354B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((354 * 7) % 251) for _ in range(354))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0355_typed() -> None:
    """tail=+355B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((355 * 7) % 251) for _ in range(355))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0356_typed() -> None:
    """tail=+356B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((356 * 7) % 251) for _ in range(356))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0357_typed() -> None:
    """tail=+357B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((357 * 7) % 251) for _ in range(357))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0358_typed() -> None:
    """tail=+358B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((358 * 7) % 251) for _ in range(358))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0359_typed() -> None:
    """tail=+359B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((359 * 7) % 251) for _ in range(359))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0360_typed() -> None:
    """tail=+360B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((360 * 7) % 251) for _ in range(360))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0361_typed() -> None:
    """tail=+361B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((361 * 7) % 251) for _ in range(361))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0362_typed() -> None:
    """tail=+362B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((362 * 7) % 251) for _ in range(362))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0363_typed() -> None:
    """tail=+363B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((363 * 7) % 251) for _ in range(363))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0364_typed() -> None:
    """tail=+364B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((364 * 7) % 251) for _ in range(364))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0365_typed() -> None:
    """tail=+365B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((365 * 7) % 251) for _ in range(365))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0366_typed() -> None:
    """tail=+366B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((366 * 7) % 251) for _ in range(366))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0367_typed() -> None:
    """tail=+367B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((367 * 7) % 251) for _ in range(367))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0368_typed() -> None:
    """tail=+368B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((368 * 7) % 251) for _ in range(368))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0369_typed() -> None:
    """tail=+369B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((369 * 7) % 251) for _ in range(369))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0370_typed() -> None:
    """tail=+370B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((370 * 7) % 251) for _ in range(370))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0371_typed() -> None:
    """tail=+371B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((371 * 7) % 251) for _ in range(371))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0372_typed() -> None:
    """tail=+372B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((372 * 7) % 251) for _ in range(372))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0373_typed() -> None:
    """tail=+373B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((373 * 7) % 251) for _ in range(373))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0374_typed() -> None:
    """tail=+374B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((374 * 7) % 251) for _ in range(374))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0375_typed() -> None:
    """tail=+375B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((375 * 7) % 251) for _ in range(375))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0376_typed() -> None:
    """tail=+376B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((376 * 7) % 251) for _ in range(376))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0377_typed() -> None:
    """tail=+377B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((377 * 7) % 251) for _ in range(377))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0378_typed() -> None:
    """tail=+378B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((378 * 7) % 251) for _ in range(378))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0379_typed() -> None:
    """tail=+379B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((379 * 7) % 251) for _ in range(379))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0380_typed() -> None:
    """tail=+380B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((380 * 7) % 251) for _ in range(380))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0381_typed() -> None:
    """tail=+381B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((381 * 7) % 251) for _ in range(381))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0382_typed() -> None:
    """tail=+382B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((382 * 7) % 251) for _ in range(382))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0383_typed() -> None:
    """tail=+383B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((383 * 7) % 251) for _ in range(383))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0384_typed() -> None:
    """tail=+384B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((384 * 7) % 251) for _ in range(384))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0385_typed() -> None:
    """tail=+385B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((385 * 7) % 251) for _ in range(385))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0386_typed() -> None:
    """tail=+386B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((386 * 7) % 251) for _ in range(386))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0387_typed() -> None:
    """tail=+387B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((387 * 7) % 251) for _ in range(387))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0388_typed() -> None:
    """tail=+388B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((388 * 7) % 251) for _ in range(388))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0389_typed() -> None:
    """tail=+389B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((389 * 7) % 251) for _ in range(389))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0390_typed() -> None:
    """tail=+390B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((390 * 7) % 251) for _ in range(390))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0391_typed() -> None:
    """tail=+391B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((391 * 7) % 251) for _ in range(391))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0392_typed() -> None:
    """tail=+392B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((392 * 7) % 251) for _ in range(392))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0393_typed() -> None:
    """tail=+393B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((393 * 7) % 251) for _ in range(393))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0394_typed() -> None:
    """tail=+394B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((394 * 7) % 251) for _ in range(394))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0395_typed() -> None:
    """tail=+395B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((395 * 7) % 251) for _ in range(395))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0396_typed() -> None:
    """tail=+396B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((396 * 7) % 251) for _ in range(396))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0397_typed() -> None:
    """tail=+397B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((397 * 7) % 251) for _ in range(397))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0398_typed() -> None:
    """tail=+398B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((398 * 7) % 251) for _ in range(398))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0399_typed() -> None:
    """tail=+399B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((399 * 7) % 251) for _ in range(399))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0400_typed() -> None:
    """tail=+400B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((400 * 7) % 251) for _ in range(400))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0401_typed() -> None:
    """tail=+401B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((401 * 7) % 251) for _ in range(401))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0402_typed() -> None:
    """tail=+402B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((402 * 7) % 251) for _ in range(402))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0403_typed() -> None:
    """tail=+403B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((403 * 7) % 251) for _ in range(403))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0404_typed() -> None:
    """tail=+404B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((404 * 7) % 251) for _ in range(404))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0405_typed() -> None:
    """tail=+405B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((405 * 7) % 251) for _ in range(405))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0406_typed() -> None:
    """tail=+406B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((406 * 7) % 251) for _ in range(406))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0407_typed() -> None:
    """tail=+407B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((407 * 7) % 251) for _ in range(407))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0408_typed() -> None:
    """tail=+408B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((408 * 7) % 251) for _ in range(408))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0409_typed() -> None:
    """tail=+409B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((409 * 7) % 251) for _ in range(409))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0410_typed() -> None:
    """tail=+410B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((410 * 7) % 251) for _ in range(410))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0411_typed() -> None:
    """tail=+411B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((411 * 7) % 251) for _ in range(411))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0412_typed() -> None:
    """tail=+412B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((412 * 7) % 251) for _ in range(412))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0413_typed() -> None:
    """tail=+413B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((413 * 7) % 251) for _ in range(413))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0414_typed() -> None:
    """tail=+414B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((414 * 7) % 251) for _ in range(414))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0415_typed() -> None:
    """tail=+415B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((415 * 7) % 251) for _ in range(415))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0416_typed() -> None:
    """tail=+416B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((416 * 7) % 251) for _ in range(416))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0417_typed() -> None:
    """tail=+417B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((417 * 7) % 251) for _ in range(417))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0418_typed() -> None:
    """tail=+418B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((418 * 7) % 251) for _ in range(418))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0419_typed() -> None:
    """tail=+419B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((419 * 7) % 251) for _ in range(419))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0420_typed() -> None:
    """tail=+420B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((420 * 7) % 251) for _ in range(420))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0421_typed() -> None:
    """tail=+421B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((421 * 7) % 251) for _ in range(421))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0422_typed() -> None:
    """tail=+422B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((422 * 7) % 251) for _ in range(422))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0423_typed() -> None:
    """tail=+423B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((423 * 7) % 251) for _ in range(423))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0424_typed() -> None:
    """tail=+424B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((424 * 7) % 251) for _ in range(424))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0425_typed() -> None:
    """tail=+425B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((425 * 7) % 251) for _ in range(425))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0426_typed() -> None:
    """tail=+426B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((426 * 7) % 251) for _ in range(426))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0427_typed() -> None:
    """tail=+427B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((427 * 7) % 251) for _ in range(427))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0428_typed() -> None:
    """tail=+428B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((428 * 7) % 251) for _ in range(428))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0429_typed() -> None:
    """tail=+429B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((429 * 7) % 251) for _ in range(429))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0430_typed() -> None:
    """tail=+430B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((430 * 7) % 251) for _ in range(430))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0431_typed() -> None:
    """tail=+431B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((431 * 7) % 251) for _ in range(431))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0432_typed() -> None:
    """tail=+432B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((432 * 7) % 251) for _ in range(432))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0433_typed() -> None:
    """tail=+433B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((433 * 7) % 251) for _ in range(433))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0434_typed() -> None:
    """tail=+434B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((434 * 7) % 251) for _ in range(434))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0435_typed() -> None:
    """tail=+435B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((435 * 7) % 251) for _ in range(435))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0436_typed() -> None:
    """tail=+436B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((436 * 7) % 251) for _ in range(436))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0437_typed() -> None:
    """tail=+437B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((437 * 7) % 251) for _ in range(437))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0438_typed() -> None:
    """tail=+438B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((438 * 7) % 251) for _ in range(438))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0439_typed() -> None:
    """tail=+439B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((439 * 7) % 251) for _ in range(439))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0440_typed() -> None:
    """tail=+440B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((440 * 7) % 251) for _ in range(440))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0441_typed() -> None:
    """tail=+441B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((441 * 7) % 251) for _ in range(441))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0442_typed() -> None:
    """tail=+442B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((442 * 7) % 251) for _ in range(442))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0443_typed() -> None:
    """tail=+443B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((443 * 7) % 251) for _ in range(443))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0444_typed() -> None:
    """tail=+444B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((444 * 7) % 251) for _ in range(444))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0445_typed() -> None:
    """tail=+445B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((445 * 7) % 251) for _ in range(445))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0446_typed() -> None:
    """tail=+446B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((446 * 7) % 251) for _ in range(446))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0447_typed() -> None:
    """tail=+447B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((447 * 7) % 251) for _ in range(447))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0448_typed() -> None:
    """tail=+448B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((448 * 7) % 251) for _ in range(448))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0449_typed() -> None:
    """tail=+449B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((449 * 7) % 251) for _ in range(449))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0450_typed() -> None:
    """tail=+450B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((450 * 7) % 251) for _ in range(450))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0451_typed() -> None:
    """tail=+451B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((451 * 7) % 251) for _ in range(451))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0452_typed() -> None:
    """tail=+452B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((452 * 7) % 251) for _ in range(452))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0453_typed() -> None:
    """tail=+453B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((453 * 7) % 251) for _ in range(453))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0454_typed() -> None:
    """tail=+454B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((454 * 7) % 251) for _ in range(454))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0455_typed() -> None:
    """tail=+455B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((455 * 7) % 251) for _ in range(455))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0456_typed() -> None:
    """tail=+456B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((456 * 7) % 251) for _ in range(456))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0457_typed() -> None:
    """tail=+457B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((457 * 7) % 251) for _ in range(457))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0458_typed() -> None:
    """tail=+458B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((458 * 7) % 251) for _ in range(458))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0459_typed() -> None:
    """tail=+459B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((459 * 7) % 251) for _ in range(459))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0460_typed() -> None:
    """tail=+460B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((460 * 7) % 251) for _ in range(460))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0461_typed() -> None:
    """tail=+461B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((461 * 7) % 251) for _ in range(461))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0462_typed() -> None:
    """tail=+462B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((462 * 7) % 251) for _ in range(462))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0463_typed() -> None:
    """tail=+463B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((463 * 7) % 251) for _ in range(463))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0464_typed() -> None:
    """tail=+464B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((464 * 7) % 251) for _ in range(464))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0465_typed() -> None:
    """tail=+465B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((465 * 7) % 251) for _ in range(465))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0466_typed() -> None:
    """tail=+466B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((466 * 7) % 251) for _ in range(466))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0467_typed() -> None:
    """tail=+467B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((467 * 7) % 251) for _ in range(467))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0468_typed() -> None:
    """tail=+468B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((468 * 7) % 251) for _ in range(468))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0469_typed() -> None:
    """tail=+469B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((469 * 7) % 251) for _ in range(469))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0470_typed() -> None:
    """tail=+470B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((470 * 7) % 251) for _ in range(470))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0471_typed() -> None:
    """tail=+471B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((471 * 7) % 251) for _ in range(471))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0472_typed() -> None:
    """tail=+472B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((472 * 7) % 251) for _ in range(472))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0473_typed() -> None:
    """tail=+473B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((473 * 7) % 251) for _ in range(473))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0474_typed() -> None:
    """tail=+474B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((474 * 7) % 251) for _ in range(474))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0475_typed() -> None:
    """tail=+475B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((475 * 7) % 251) for _ in range(475))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0476_typed() -> None:
    """tail=+476B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((476 * 7) % 251) for _ in range(476))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0477_typed() -> None:
    """tail=+477B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((477 * 7) % 251) for _ in range(477))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0478_typed() -> None:
    """tail=+478B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((478 * 7) % 251) for _ in range(478))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0479_typed() -> None:
    """tail=+479B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((479 * 7) % 251) for _ in range(479))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0480_typed() -> None:
    """tail=+480B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((480 * 7) % 251) for _ in range(480))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0481_typed() -> None:
    """tail=+481B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((481 * 7) % 251) for _ in range(481))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0482_typed() -> None:
    """tail=+482B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((482 * 7) % 251) for _ in range(482))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0483_typed() -> None:
    """tail=+483B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((483 * 7) % 251) for _ in range(483))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0484_typed() -> None:
    """tail=+484B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((484 * 7) % 251) for _ in range(484))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0485_typed() -> None:
    """tail=+485B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((485 * 7) % 251) for _ in range(485))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0486_typed() -> None:
    """tail=+486B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((486 * 7) % 251) for _ in range(486))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0487_typed() -> None:
    """tail=+487B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((487 * 7) % 251) for _ in range(487))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0488_typed() -> None:
    """tail=+488B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((488 * 7) % 251) for _ in range(488))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0489_typed() -> None:
    """tail=+489B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((489 * 7) % 251) for _ in range(489))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0490_typed() -> None:
    """tail=+490B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((490 * 7) % 251) for _ in range(490))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0491_typed() -> None:
    """tail=+491B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((491 * 7) % 251) for _ in range(491))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0492_typed() -> None:
    """tail=+492B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((492 * 7) % 251) for _ in range(492))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0493_typed() -> None:
    """tail=+493B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((493 * 7) % 251) for _ in range(493))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0494_typed() -> None:
    """tail=+494B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((494 * 7) % 251) for _ in range(494))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0495_typed() -> None:
    """tail=+495B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((495 * 7) % 251) for _ in range(495))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0496_typed() -> None:
    """tail=+496B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((496 * 7) % 251) for _ in range(496))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0497_typed() -> None:
    """tail=+497B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((497 * 7) % 251) for _ in range(497))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0498_typed() -> None:
    """tail=+498B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((498 * 7) % 251) for _ in range(498))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0499_typed() -> None:
    """tail=+499B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((499 * 7) % 251) for _ in range(499))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0500_typed() -> None:
    """tail=+500B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((500 * 7) % 251) for _ in range(500))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0501_typed() -> None:
    """tail=+501B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((501 * 7) % 251) for _ in range(501))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0502_typed() -> None:
    """tail=+502B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((502 * 7) % 251) for _ in range(502))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_trail_trail0503_typed() -> None:
    """tail=+503B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((503 * 7) % 251) for _ in range(503))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0504_typed() -> None:
    """tail=+504B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((504 * 7) % 251) for _ in range(504))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0505_typed() -> None:
    """tail=+505B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((505 * 7) % 251) for _ in range(505))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0506_typed() -> None:
    """tail=+506B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((506 * 7) % 251) for _ in range(506))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0507_typed() -> None:
    """tail=+507B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((507 * 7) % 251) for _ in range(507))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0508_typed() -> None:
    """tail=+508B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((508 * 7) % 251) for _ in range(508))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0509_typed() -> None:
    """tail=+509B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((509 * 7) % 251) for _ in range(509))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0510_typed() -> None:
    """tail=+510B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((510 * 7) % 251) for _ in range(510))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0511_typed() -> None:
    """tail=+511B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((511 * 7) % 251) for _ in range(511))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0512_typed() -> None:
    """tail=+512B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((512 * 7) % 251) for _ in range(512))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0513_typed() -> None:
    """tail=+513B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((513 * 7) % 251) for _ in range(513))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0514_typed() -> None:
    """tail=+514B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((514 * 7) % 251) for _ in range(514))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0515_typed() -> None:
    """tail=+515B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((515 * 7) % 251) for _ in range(515))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0516_typed() -> None:
    """tail=+516B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((516 * 7) % 251) for _ in range(516))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0517_typed() -> None:
    """tail=+517B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((517 * 7) % 251) for _ in range(517))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0518_typed() -> None:
    """tail=+518B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((518 * 7) % 251) for _ in range(518))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0519_typed() -> None:
    """tail=+519B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((519 * 7) % 251) for _ in range(519))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0520_typed() -> None:
    """tail=+520B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((520 * 7) % 251) for _ in range(520))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0521_typed() -> None:
    """tail=+521B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((521 * 7) % 251) for _ in range(521))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0522_typed() -> None:
    """tail=+522B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((522 * 7) % 251) for _ in range(522))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0523_typed() -> None:
    """tail=+523B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((523 * 7) % 251) for _ in range(523))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0524_typed() -> None:
    """tail=+524B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((524 * 7) % 251) for _ in range(524))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0525_typed() -> None:
    """tail=+525B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((525 * 7) % 251) for _ in range(525))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0526_typed() -> None:
    """tail=+526B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((526 * 7) % 251) for _ in range(526))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0527_typed() -> None:
    """tail=+527B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((527 * 7) % 251) for _ in range(527))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0528_typed() -> None:
    """tail=+528B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((528 * 7) % 251) for _ in range(528))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0529_typed() -> None:
    """tail=+529B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((529 * 7) % 251) for _ in range(529))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0530_typed() -> None:
    """tail=+530B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((530 * 7) % 251) for _ in range(530))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0531_typed() -> None:
    """tail=+531B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((531 * 7) % 251) for _ in range(531))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0532_typed() -> None:
    """tail=+532B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((532 * 7) % 251) for _ in range(532))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0533_typed() -> None:
    """tail=+533B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((533 * 7) % 251) for _ in range(533))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0534_typed() -> None:
    """tail=+534B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((534 * 7) % 251) for _ in range(534))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0535_typed() -> None:
    """tail=+535B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((535 * 7) % 251) for _ in range(535))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0536_typed() -> None:
    """tail=+536B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((536 * 7) % 251) for _ in range(536))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0537_typed() -> None:
    """tail=+537B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((537 * 7) % 251) for _ in range(537))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0538_typed() -> None:
    """tail=+538B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((538 * 7) % 251) for _ in range(538))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0539_typed() -> None:
    """tail=+539B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((539 * 7) % 251) for _ in range(539))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0540_typed() -> None:
    """tail=+540B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((540 * 7) % 251) for _ in range(540))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0541_typed() -> None:
    """tail=+541B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((541 * 7) % 251) for _ in range(541))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0542_typed() -> None:
    """tail=+542B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((542 * 7) % 251) for _ in range(542))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0543_typed() -> None:
    """tail=+543B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((543 * 7) % 251) for _ in range(543))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0544_typed() -> None:
    """tail=+544B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((544 * 7) % 251) for _ in range(544))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0545_typed() -> None:
    """tail=+545B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((545 * 7) % 251) for _ in range(545))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0546_typed() -> None:
    """tail=+546B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((546 * 7) % 251) for _ in range(546))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0547_typed() -> None:
    """tail=+547B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((547 * 7) % 251) for _ in range(547))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0548_typed() -> None:
    """tail=+548B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((548 * 7) % 251) for _ in range(548))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0549_typed() -> None:
    """tail=+549B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((549 * 7) % 251) for _ in range(549))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0550_typed() -> None:
    """tail=+550B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((550 * 7) % 251) for _ in range(550))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0551_typed() -> None:
    """tail=+551B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((551 * 7) % 251) for _ in range(551))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0552_typed() -> None:
    """tail=+552B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((552 * 7) % 251) for _ in range(552))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0553_typed() -> None:
    """tail=+553B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((553 * 7) % 251) for _ in range(553))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0554_typed() -> None:
    """tail=+554B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((554 * 7) % 251) for _ in range(554))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0555_typed() -> None:
    """tail=+555B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((555 * 7) % 251) for _ in range(555))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0556_typed() -> None:
    """tail=+556B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((556 * 7) % 251) for _ in range(556))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0557_typed() -> None:
    """tail=+557B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((557 * 7) % 251) for _ in range(557))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0558_typed() -> None:
    """tail=+558B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((558 * 7) % 251) for _ in range(558))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0559_typed() -> None:
    """tail=+559B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((559 * 7) % 251) for _ in range(559))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0560_typed() -> None:
    """tail=+560B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((560 * 7) % 251) for _ in range(560))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0561_typed() -> None:
    """tail=+561B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((561 * 7) % 251) for _ in range(561))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0562_typed() -> None:
    """tail=+562B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((562 * 7) % 251) for _ in range(562))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0563_typed() -> None:
    """tail=+563B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((563 * 7) % 251) for _ in range(563))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0564_typed() -> None:
    """tail=+564B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((564 * 7) % 251) for _ in range(564))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0565_typed() -> None:
    """tail=+565B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((565 * 7) % 251) for _ in range(565))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0566_typed() -> None:
    """tail=+566B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((566 * 7) % 251) for _ in range(566))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0567_typed() -> None:
    """tail=+567B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((567 * 7) % 251) for _ in range(567))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0568_typed() -> None:
    """tail=+568B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((568 * 7) % 251) for _ in range(568))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0569_typed() -> None:
    """tail=+569B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((569 * 7) % 251) for _ in range(569))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0570_typed() -> None:
    """tail=+570B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((570 * 7) % 251) for _ in range(570))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0571_typed() -> None:
    """tail=+571B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((571 * 7) % 251) for _ in range(571))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0572_typed() -> None:
    """tail=+572B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((572 * 7) % 251) for _ in range(572))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0573_typed() -> None:
    """tail=+573B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((573 * 7) % 251) for _ in range(573))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0574_typed() -> None:
    """tail=+574B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((574 * 7) % 251) for _ in range(574))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0575_typed() -> None:
    """tail=+575B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((575 * 7) % 251) for _ in range(575))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0576_typed() -> None:
    """tail=+576B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((576 * 7) % 251) for _ in range(576))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0577_typed() -> None:
    """tail=+577B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((577 * 7) % 251) for _ in range(577))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0578_typed() -> None:
    """tail=+578B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((578 * 7) % 251) for _ in range(578))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0579_typed() -> None:
    """tail=+579B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((579 * 7) % 251) for _ in range(579))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0580_typed() -> None:
    """tail=+580B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((580 * 7) % 251) for _ in range(580))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0581_typed() -> None:
    """tail=+581B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((581 * 7) % 251) for _ in range(581))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0582_typed() -> None:
    """tail=+582B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((582 * 7) % 251) for _ in range(582))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0583_typed() -> None:
    """tail=+583B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((583 * 7) % 251) for _ in range(583))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0584_typed() -> None:
    """tail=+584B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((584 * 7) % 251) for _ in range(584))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0585_typed() -> None:
    """tail=+585B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((585 * 7) % 251) for _ in range(585))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0586_typed() -> None:
    """tail=+586B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((586 * 7) % 251) for _ in range(586))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0587_typed() -> None:
    """tail=+587B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((587 * 7) % 251) for _ in range(587))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0588_typed() -> None:
    """tail=+588B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((588 * 7) % 251) for _ in range(588))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0589_typed() -> None:
    """tail=+589B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((589 * 7) % 251) for _ in range(589))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0590_typed() -> None:
    """tail=+590B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((590 * 7) % 251) for _ in range(590))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0591_typed() -> None:
    """tail=+591B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((591 * 7) % 251) for _ in range(591))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0592_typed() -> None:
    """tail=+592B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((592 * 7) % 251) for _ in range(592))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0593_typed() -> None:
    """tail=+593B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((593 * 7) % 251) for _ in range(593))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0594_typed() -> None:
    """tail=+594B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((594 * 7) % 251) for _ in range(594))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0595_typed() -> None:
    """tail=+595B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((595 * 7) % 251) for _ in range(595))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0596_typed() -> None:
    """tail=+596B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((596 * 7) % 251) for _ in range(596))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0597_typed() -> None:
    """tail=+597B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((597 * 7) % 251) for _ in range(597))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0598_typed() -> None:
    """tail=+598B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((598 * 7) % 251) for _ in range(598))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0599_typed() -> None:
    """tail=+599B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((599 * 7) % 251) for _ in range(599))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0600_typed() -> None:
    """tail=+600B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((600 * 7) % 251) for _ in range(600))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0601_typed() -> None:
    """tail=+601B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((601 * 7) % 251) for _ in range(601))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0602_typed() -> None:
    """tail=+602B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((602 * 7) % 251) for _ in range(602))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0603_typed() -> None:
    """tail=+603B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((603 * 7) % 251) for _ in range(603))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0604_typed() -> None:
    """tail=+604B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((604 * 7) % 251) for _ in range(604))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0605_typed() -> None:
    """tail=+605B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((605 * 7) % 251) for _ in range(605))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0606_typed() -> None:
    """tail=+606B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((606 * 7) % 251) for _ in range(606))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0607_typed() -> None:
    """tail=+607B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((607 * 7) % 251) for _ in range(607))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0608_typed() -> None:
    """tail=+608B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((608 * 7) % 251) for _ in range(608))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0609_typed() -> None:
    """tail=+609B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((609 * 7) % 251) for _ in range(609))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0610_typed() -> None:
    """tail=+610B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((610 * 7) % 251) for _ in range(610))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0611_typed() -> None:
    """tail=+611B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((611 * 7) % 251) for _ in range(611))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0612_typed() -> None:
    """tail=+612B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((612 * 7) % 251) for _ in range(612))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0613_typed() -> None:
    """tail=+613B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((613 * 7) % 251) for _ in range(613))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0614_typed() -> None:
    """tail=+614B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((614 * 7) % 251) for _ in range(614))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0615_typed() -> None:
    """tail=+615B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((615 * 7) % 251) for _ in range(615))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0616_typed() -> None:
    """tail=+616B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((616 * 7) % 251) for _ in range(616))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0617_typed() -> None:
    """tail=+617B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((617 * 7) % 251) for _ in range(617))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0618_typed() -> None:
    """tail=+618B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((618 * 7) % 251) for _ in range(618))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0619_typed() -> None:
    """tail=+619B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((619 * 7) % 251) for _ in range(619))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0620_typed() -> None:
    """tail=+620B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((620 * 7) % 251) for _ in range(620))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0621_typed() -> None:
    """tail=+621B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((621 * 7) % 251) for _ in range(621))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0622_typed() -> None:
    """tail=+622B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((622 * 7) % 251) for _ in range(622))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0623_typed() -> None:
    """tail=+623B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((623 * 7) % 251) for _ in range(623))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0624_typed() -> None:
    """tail=+624B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((624 * 7) % 251) for _ in range(624))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0625_typed() -> None:
    """tail=+625B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((625 * 7) % 251) for _ in range(625))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0626_typed() -> None:
    """tail=+626B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((626 * 7) % 251) for _ in range(626))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0627_typed() -> None:
    """tail=+627B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((627 * 7) % 251) for _ in range(627))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0628_typed() -> None:
    """tail=+628B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((628 * 7) % 251) for _ in range(628))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0629_typed() -> None:
    """tail=+629B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((629 * 7) % 251) for _ in range(629))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0630_typed() -> None:
    """tail=+630B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((630 * 7) % 251) for _ in range(630))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0631_typed() -> None:
    """tail=+631B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((631 * 7) % 251) for _ in range(631))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0632_typed() -> None:
    """tail=+632B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((632 * 7) % 251) for _ in range(632))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0633_typed() -> None:
    """tail=+633B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((633 * 7) % 251) for _ in range(633))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0634_typed() -> None:
    """tail=+634B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((634 * 7) % 251) for _ in range(634))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0635_typed() -> None:
    """tail=+635B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((635 * 7) % 251) for _ in range(635))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0636_typed() -> None:
    """tail=+636B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((636 * 7) % 251) for _ in range(636))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0637_typed() -> None:
    """tail=+637B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((637 * 7) % 251) for _ in range(637))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0638_typed() -> None:
    """tail=+638B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((638 * 7) % 251) for _ in range(638))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0639_typed() -> None:
    """tail=+639B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((639 * 7) % 251) for _ in range(639))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0640_typed() -> None:
    """tail=+640B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((640 * 7) % 251) for _ in range(640))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0641_typed() -> None:
    """tail=+641B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((641 * 7) % 251) for _ in range(641))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0642_typed() -> None:
    """tail=+642B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((642 * 7) % 251) for _ in range(642))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0643_typed() -> None:
    """tail=+643B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((643 * 7) % 251) for _ in range(643))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0644_typed() -> None:
    """tail=+644B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((644 * 7) % 251) for _ in range(644))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0645_typed() -> None:
    """tail=+645B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((645 * 7) % 251) for _ in range(645))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0646_typed() -> None:
    """tail=+646B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((646 * 7) % 251) for _ in range(646))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0647_typed() -> None:
    """tail=+647B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((647 * 7) % 251) for _ in range(647))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0648_typed() -> None:
    """tail=+648B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((648 * 7) % 251) for _ in range(648))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0649_typed() -> None:
    """tail=+649B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((649 * 7) % 251) for _ in range(649))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0650_typed() -> None:
    """tail=+650B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((650 * 7) % 251) for _ in range(650))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0651_typed() -> None:
    """tail=+651B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((651 * 7) % 251) for _ in range(651))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0652_typed() -> None:
    """tail=+652B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((652 * 7) % 251) for _ in range(652))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0653_typed() -> None:
    """tail=+653B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((653 * 7) % 251) for _ in range(653))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0654_typed() -> None:
    """tail=+654B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((654 * 7) % 251) for _ in range(654))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0655_typed() -> None:
    """tail=+655B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((655 * 7) % 251) for _ in range(655))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0656_typed() -> None:
    """tail=+656B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((656 * 7) % 251) for _ in range(656))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0657_typed() -> None:
    """tail=+657B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((657 * 7) % 251) for _ in range(657))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0658_typed() -> None:
    """tail=+658B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((658 * 7) % 251) for _ in range(658))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0659_typed() -> None:
    """tail=+659B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((659 * 7) % 251) for _ in range(659))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0660_typed() -> None:
    """tail=+660B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((660 * 7) % 251) for _ in range(660))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0661_typed() -> None:
    """tail=+661B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((661 * 7) % 251) for _ in range(661))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0662_typed() -> None:
    """tail=+662B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((662 * 7) % 251) for _ in range(662))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0663_typed() -> None:
    """tail=+663B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((663 * 7) % 251) for _ in range(663))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0664_typed() -> None:
    """tail=+664B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((664 * 7) % 251) for _ in range(664))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0665_typed() -> None:
    """tail=+665B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((665 * 7) % 251) for _ in range(665))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0666_typed() -> None:
    """tail=+666B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((666 * 7) % 251) for _ in range(666))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0667_typed() -> None:
    """tail=+667B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((667 * 7) % 251) for _ in range(667))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0668_typed() -> None:
    """tail=+668B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((668 * 7) % 251) for _ in range(668))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0669_typed() -> None:
    """tail=+669B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((669 * 7) % 251) for _ in range(669))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0670_typed() -> None:
    """tail=+670B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((670 * 7) % 251) for _ in range(670))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0671_typed() -> None:
    """tail=+671B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((671 * 7) % 251) for _ in range(671))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0672_typed() -> None:
    """tail=+672B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((672 * 7) % 251) for _ in range(672))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0673_typed() -> None:
    """tail=+673B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((673 * 7) % 251) for _ in range(673))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0674_typed() -> None:
    """tail=+674B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((674 * 7) % 251) for _ in range(674))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0675_typed() -> None:
    """tail=+675B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((675 * 7) % 251) for _ in range(675))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0676_typed() -> None:
    """tail=+676B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((676 * 7) % 251) for _ in range(676))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0677_typed() -> None:
    """tail=+677B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((677 * 7) % 251) for _ in range(677))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0678_typed() -> None:
    """tail=+678B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((678 * 7) % 251) for _ in range(678))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0679_typed() -> None:
    """tail=+679B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((679 * 7) % 251) for _ in range(679))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0680_typed() -> None:
    """tail=+680B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((680 * 7) % 251) for _ in range(680))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0681_typed() -> None:
    """tail=+681B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((681 * 7) % 251) for _ in range(681))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0682_typed() -> None:
    """tail=+682B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((682 * 7) % 251) for _ in range(682))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0683_typed() -> None:
    """tail=+683B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((683 * 7) % 251) for _ in range(683))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0684_typed() -> None:
    """tail=+684B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((684 * 7) % 251) for _ in range(684))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0685_typed() -> None:
    """tail=+685B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((685 * 7) % 251) for _ in range(685))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0686_typed() -> None:
    """tail=+686B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((686 * 7) % 251) for _ in range(686))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0687_typed() -> None:
    """tail=+687B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((687 * 7) % 251) for _ in range(687))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0688_typed() -> None:
    """tail=+688B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((688 * 7) % 251) for _ in range(688))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0689_typed() -> None:
    """tail=+689B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((689 * 7) % 251) for _ in range(689))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0690_typed() -> None:
    """tail=+690B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((690 * 7) % 251) for _ in range(690))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0691_typed() -> None:
    """tail=+691B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((691 * 7) % 251) for _ in range(691))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0692_typed() -> None:
    """tail=+692B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((692 * 7) % 251) for _ in range(692))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0693_typed() -> None:
    """tail=+693B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((693 * 7) % 251) for _ in range(693))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0694_typed() -> None:
    """tail=+694B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((694 * 7) % 251) for _ in range(694))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0695_typed() -> None:
    """tail=+695B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((695 * 7) % 251) for _ in range(695))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0696_typed() -> None:
    """tail=+696B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((696 * 7) % 251) for _ in range(696))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0697_typed() -> None:
    """tail=+697B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((697 * 7) % 251) for _ in range(697))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0698_typed() -> None:
    """tail=+698B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((698 * 7) % 251) for _ in range(698))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0699_typed() -> None:
    """tail=+699B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((699 * 7) % 251) for _ in range(699))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0700_typed() -> None:
    """tail=+700B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((700 * 7) % 251) for _ in range(700))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0701_typed() -> None:
    """tail=+701B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((701 * 7) % 251) for _ in range(701))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0702_typed() -> None:
    """tail=+702B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((702 * 7) % 251) for _ in range(702))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0703_typed() -> None:
    """tail=+703B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((703 * 7) % 251) for _ in range(703))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0704_typed() -> None:
    """tail=+704B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((704 * 7) % 251) for _ in range(704))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0705_typed() -> None:
    """tail=+705B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((705 * 7) % 251) for _ in range(705))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0706_typed() -> None:
    """tail=+706B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((706 * 7) % 251) for _ in range(706))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0707_typed() -> None:
    """tail=+707B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((707 * 7) % 251) for _ in range(707))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0708_typed() -> None:
    """tail=+708B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((708 * 7) % 251) for _ in range(708))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0709_typed() -> None:
    """tail=+709B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((709 * 7) % 251) for _ in range(709))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0710_typed() -> None:
    """tail=+710B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((710 * 7) % 251) for _ in range(710))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0711_typed() -> None:
    """tail=+711B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((711 * 7) % 251) for _ in range(711))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0712_typed() -> None:
    """tail=+712B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((712 * 7) % 251) for _ in range(712))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0713_typed() -> None:
    """tail=+713B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((713 * 7) % 251) for _ in range(713))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0714_typed() -> None:
    """tail=+714B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((714 * 7) % 251) for _ in range(714))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0715_typed() -> None:
    """tail=+715B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((715 * 7) % 251) for _ in range(715))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0716_typed() -> None:
    """tail=+716B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((716 * 7) % 251) for _ in range(716))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0717_typed() -> None:
    """tail=+717B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((717 * 7) % 251) for _ in range(717))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0718_typed() -> None:
    """tail=+718B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((718 * 7) % 251) for _ in range(718))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0719_typed() -> None:
    """tail=+719B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((719 * 7) % 251) for _ in range(719))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0720_typed() -> None:
    """tail=+720B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((720 * 7) % 251) for _ in range(720))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0721_typed() -> None:
    """tail=+721B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((721 * 7) % 251) for _ in range(721))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0722_typed() -> None:
    """tail=+722B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((722 * 7) % 251) for _ in range(722))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0723_typed() -> None:
    """tail=+723B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((723 * 7) % 251) for _ in range(723))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0724_typed() -> None:
    """tail=+724B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((724 * 7) % 251) for _ in range(724))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0725_typed() -> None:
    """tail=+725B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((725 * 7) % 251) for _ in range(725))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0726_typed() -> None:
    """tail=+726B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((726 * 7) % 251) for _ in range(726))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0727_typed() -> None:
    """tail=+727B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((727 * 7) % 251) for _ in range(727))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0728_typed() -> None:
    """tail=+728B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((728 * 7) % 251) for _ in range(728))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0729_typed() -> None:
    """tail=+729B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((729 * 7) % 251) for _ in range(729))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0730_typed() -> None:
    """tail=+730B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((730 * 7) % 251) for _ in range(730))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0731_typed() -> None:
    """tail=+731B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((731 * 7) % 251) for _ in range(731))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0732_typed() -> None:
    """tail=+732B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((732 * 7) % 251) for _ in range(732))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0733_typed() -> None:
    """tail=+733B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((733 * 7) % 251) for _ in range(733))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0734_typed() -> None:
    """tail=+734B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((734 * 7) % 251) for _ in range(734))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0735_typed() -> None:
    """tail=+735B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((735 * 7) % 251) for _ in range(735))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0736_typed() -> None:
    """tail=+736B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((736 * 7) % 251) for _ in range(736))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0737_typed() -> None:
    """tail=+737B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((737 * 7) % 251) for _ in range(737))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0738_typed() -> None:
    """tail=+738B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((738 * 7) % 251) for _ in range(738))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0739_typed() -> None:
    """tail=+739B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((739 * 7) % 251) for _ in range(739))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0740_typed() -> None:
    """tail=+740B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((740 * 7) % 251) for _ in range(740))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0741_typed() -> None:
    """tail=+741B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((741 * 7) % 251) for _ in range(741))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0742_typed() -> None:
    """tail=+742B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((742 * 7) % 251) for _ in range(742))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0743_typed() -> None:
    """tail=+743B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((743 * 7) % 251) for _ in range(743))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0744_typed() -> None:
    """tail=+744B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((744 * 7) % 251) for _ in range(744))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0745_typed() -> None:
    """tail=+745B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((745 * 7) % 251) for _ in range(745))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0746_typed() -> None:
    """tail=+746B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((746 * 7) % 251) for _ in range(746))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0747_typed() -> None:
    """tail=+747B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((747 * 7) % 251) for _ in range(747))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0748_typed() -> None:
    """tail=+748B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((748 * 7) % 251) for _ in range(748))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0749_typed() -> None:
    """tail=+749B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((749 * 7) % 251) for _ in range(749))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0750_typed() -> None:
    """tail=+750B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((750 * 7) % 251) for _ in range(750))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0751_typed() -> None:
    """tail=+751B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((751 * 7) % 251) for _ in range(751))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0752_typed() -> None:
    """tail=+752B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((752 * 7) % 251) for _ in range(752))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0753_typed() -> None:
    """tail=+753B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((753 * 7) % 251) for _ in range(753))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_trail_trail0754_typed() -> None:
    """tail=+754B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((754 * 7) % 251) for _ in range(754))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0755_typed() -> None:
    """tail=+755B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((755 * 7) % 251) for _ in range(755))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0756_typed() -> None:
    """tail=+756B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((756 * 7) % 251) for _ in range(756))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0757_typed() -> None:
    """tail=+757B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((757 * 7) % 251) for _ in range(757))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0758_typed() -> None:
    """tail=+758B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((758 * 7) % 251) for _ in range(758))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0759_typed() -> None:
    """tail=+759B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((759 * 7) % 251) for _ in range(759))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0760_typed() -> None:
    """tail=+760B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((760 * 7) % 251) for _ in range(760))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0761_typed() -> None:
    """tail=+761B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((761 * 7) % 251) for _ in range(761))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0762_typed() -> None:
    """tail=+762B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((762 * 7) % 251) for _ in range(762))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0763_typed() -> None:
    """tail=+763B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((763 * 7) % 251) for _ in range(763))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0764_typed() -> None:
    """tail=+764B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((764 * 7) % 251) for _ in range(764))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0765_typed() -> None:
    """tail=+765B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((765 * 7) % 251) for _ in range(765))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0766_typed() -> None:
    """tail=+766B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((766 * 7) % 251) for _ in range(766))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0767_typed() -> None:
    """tail=+767B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((767 * 7) % 251) for _ in range(767))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0768_typed() -> None:
    """tail=+768B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((768 * 7) % 251) for _ in range(768))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0769_typed() -> None:
    """tail=+769B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((769 * 7) % 251) for _ in range(769))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0770_typed() -> None:
    """tail=+770B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((770 * 7) % 251) for _ in range(770))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0771_typed() -> None:
    """tail=+771B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((771 * 7) % 251) for _ in range(771))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0772_typed() -> None:
    """tail=+772B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((772 * 7) % 251) for _ in range(772))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0773_typed() -> None:
    """tail=+773B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((773 * 7) % 251) for _ in range(773))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0774_typed() -> None:
    """tail=+774B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((774 * 7) % 251) for _ in range(774))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0775_typed() -> None:
    """tail=+775B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((775 * 7) % 251) for _ in range(775))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0776_typed() -> None:
    """tail=+776B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((776 * 7) % 251) for _ in range(776))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0777_typed() -> None:
    """tail=+777B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((777 * 7) % 251) for _ in range(777))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0778_typed() -> None:
    """tail=+778B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((778 * 7) % 251) for _ in range(778))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0779_typed() -> None:
    """tail=+779B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((779 * 7) % 251) for _ in range(779))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0780_typed() -> None:
    """tail=+780B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((780 * 7) % 251) for _ in range(780))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0781_typed() -> None:
    """tail=+781B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((781 * 7) % 251) for _ in range(781))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0782_typed() -> None:
    """tail=+782B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((782 * 7) % 251) for _ in range(782))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0783_typed() -> None:
    """tail=+783B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((783 * 7) % 251) for _ in range(783))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0784_typed() -> None:
    """tail=+784B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((784 * 7) % 251) for _ in range(784))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0785_typed() -> None:
    """tail=+785B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((785 * 7) % 251) for _ in range(785))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0786_typed() -> None:
    """tail=+786B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((786 * 7) % 251) for _ in range(786))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0787_typed() -> None:
    """tail=+787B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((787 * 7) % 251) for _ in range(787))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0788_typed() -> None:
    """tail=+788B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((788 * 7) % 251) for _ in range(788))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0789_typed() -> None:
    """tail=+789B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((789 * 7) % 251) for _ in range(789))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0790_typed() -> None:
    """tail=+790B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((790 * 7) % 251) for _ in range(790))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0791_typed() -> None:
    """tail=+791B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((791 * 7) % 251) for _ in range(791))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0792_typed() -> None:
    """tail=+792B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((792 * 7) % 251) for _ in range(792))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0793_typed() -> None:
    """tail=+793B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((793 * 7) % 251) for _ in range(793))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0794_typed() -> None:
    """tail=+794B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((794 * 7) % 251) for _ in range(794))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0795_typed() -> None:
    """tail=+795B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((795 * 7) % 251) for _ in range(795))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0796_typed() -> None:
    """tail=+796B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((796 * 7) % 251) for _ in range(796))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0797_typed() -> None:
    """tail=+797B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((797 * 7) % 251) for _ in range(797))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0798_typed() -> None:
    """tail=+798B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((798 * 7) % 251) for _ in range(798))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0799_typed() -> None:
    """tail=+799B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((799 * 7) % 251) for _ in range(799))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0800_typed() -> None:
    """tail=+800B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((800 * 7) % 251) for _ in range(800))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0801_typed() -> None:
    """tail=+801B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((801 * 7) % 251) for _ in range(801))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0802_typed() -> None:
    """tail=+802B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((802 * 7) % 251) for _ in range(802))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0803_typed() -> None:
    """tail=+803B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((803 * 7) % 251) for _ in range(803))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0804_typed() -> None:
    """tail=+804B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((804 * 7) % 251) for _ in range(804))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0805_typed() -> None:
    """tail=+805B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((805 * 7) % 251) for _ in range(805))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0806_typed() -> None:
    """tail=+806B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((806 * 7) % 251) for _ in range(806))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0807_typed() -> None:
    """tail=+807B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((807 * 7) % 251) for _ in range(807))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0808_typed() -> None:
    """tail=+808B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((808 * 7) % 251) for _ in range(808))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0809_typed() -> None:
    """tail=+809B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((809 * 7) % 251) for _ in range(809))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0810_typed() -> None:
    """tail=+810B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((810 * 7) % 251) for _ in range(810))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0811_typed() -> None:
    """tail=+811B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((811 * 7) % 251) for _ in range(811))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0812_typed() -> None:
    """tail=+812B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((812 * 7) % 251) for _ in range(812))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0813_typed() -> None:
    """tail=+813B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((813 * 7) % 251) for _ in range(813))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0814_typed() -> None:
    """tail=+814B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((814 * 7) % 251) for _ in range(814))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0815_typed() -> None:
    """tail=+815B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((815 * 7) % 251) for _ in range(815))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0816_typed() -> None:
    """tail=+816B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((816 * 7) % 251) for _ in range(816))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0817_typed() -> None:
    """tail=+817B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((817 * 7) % 251) for _ in range(817))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0818_typed() -> None:
    """tail=+818B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((818 * 7) % 251) for _ in range(818))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0819_typed() -> None:
    """tail=+819B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((819 * 7) % 251) for _ in range(819))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0820_typed() -> None:
    """tail=+820B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((820 * 7) % 251) for _ in range(820))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0821_typed() -> None:
    """tail=+821B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((821 * 7) % 251) for _ in range(821))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0822_typed() -> None:
    """tail=+822B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((822 * 7) % 251) for _ in range(822))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0823_typed() -> None:
    """tail=+823B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((823 * 7) % 251) for _ in range(823))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0824_typed() -> None:
    """tail=+824B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((824 * 7) % 251) for _ in range(824))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0825_typed() -> None:
    """tail=+825B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((825 * 7) % 251) for _ in range(825))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0826_typed() -> None:
    """tail=+826B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((826 * 7) % 251) for _ in range(826))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0827_typed() -> None:
    """tail=+827B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((827 * 7) % 251) for _ in range(827))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0828_typed() -> None:
    """tail=+828B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((828 * 7) % 251) for _ in range(828))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0829_typed() -> None:
    """tail=+829B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((829 * 7) % 251) for _ in range(829))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0830_typed() -> None:
    """tail=+830B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((830 * 7) % 251) for _ in range(830))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0831_typed() -> None:
    """tail=+831B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((831 * 7) % 251) for _ in range(831))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0832_typed() -> None:
    """tail=+832B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((832 * 7) % 251) for _ in range(832))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0833_typed() -> None:
    """tail=+833B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((833 * 7) % 251) for _ in range(833))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0834_typed() -> None:
    """tail=+834B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((834 * 7) % 251) for _ in range(834))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0835_typed() -> None:
    """tail=+835B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((835 * 7) % 251) for _ in range(835))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0836_typed() -> None:
    """tail=+836B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((836 * 7) % 251) for _ in range(836))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0837_typed() -> None:
    """tail=+837B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((837 * 7) % 251) for _ in range(837))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0838_typed() -> None:
    """tail=+838B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((838 * 7) % 251) for _ in range(838))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0839_typed() -> None:
    """tail=+839B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((839 * 7) % 251) for _ in range(839))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0840_typed() -> None:
    """tail=+840B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((840 * 7) % 251) for _ in range(840))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0841_typed() -> None:
    """tail=+841B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((841 * 7) % 251) for _ in range(841))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0842_typed() -> None:
    """tail=+842B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((842 * 7) % 251) for _ in range(842))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0843_typed() -> None:
    """tail=+843B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((843 * 7) % 251) for _ in range(843))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0844_typed() -> None:
    """tail=+844B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((844 * 7) % 251) for _ in range(844))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0845_typed() -> None:
    """tail=+845B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((845 * 7) % 251) for _ in range(845))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0846_typed() -> None:
    """tail=+846B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((846 * 7) % 251) for _ in range(846))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0847_typed() -> None:
    """tail=+847B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((847 * 7) % 251) for _ in range(847))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0848_typed() -> None:
    """tail=+848B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((848 * 7) % 251) for _ in range(848))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0849_typed() -> None:
    """tail=+849B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((849 * 7) % 251) for _ in range(849))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0850_typed() -> None:
    """tail=+850B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((850 * 7) % 251) for _ in range(850))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0851_typed() -> None:
    """tail=+851B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((851 * 7) % 251) for _ in range(851))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0852_typed() -> None:
    """tail=+852B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((852 * 7) % 251) for _ in range(852))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0853_typed() -> None:
    """tail=+853B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((853 * 7) % 251) for _ in range(853))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0854_typed() -> None:
    """tail=+854B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((854 * 7) % 251) for _ in range(854))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0855_typed() -> None:
    """tail=+855B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((855 * 7) % 251) for _ in range(855))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0856_typed() -> None:
    """tail=+856B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((856 * 7) % 251) for _ in range(856))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0857_typed() -> None:
    """tail=+857B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((857 * 7) % 251) for _ in range(857))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0858_typed() -> None:
    """tail=+858B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((858 * 7) % 251) for _ in range(858))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0859_typed() -> None:
    """tail=+859B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((859 * 7) % 251) for _ in range(859))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0860_typed() -> None:
    """tail=+860B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((860 * 7) % 251) for _ in range(860))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0861_typed() -> None:
    """tail=+861B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((861 * 7) % 251) for _ in range(861))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0862_typed() -> None:
    """tail=+862B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((862 * 7) % 251) for _ in range(862))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0863_typed() -> None:
    """tail=+863B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((863 * 7) % 251) for _ in range(863))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0864_typed() -> None:
    """tail=+864B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((864 * 7) % 251) for _ in range(864))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0865_typed() -> None:
    """tail=+865B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((865 * 7) % 251) for _ in range(865))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0866_typed() -> None:
    """tail=+866B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((866 * 7) % 251) for _ in range(866))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0867_typed() -> None:
    """tail=+867B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((867 * 7) % 251) for _ in range(867))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0868_typed() -> None:
    """tail=+868B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((868 * 7) % 251) for _ in range(868))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0869_typed() -> None:
    """tail=+869B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((869 * 7) % 251) for _ in range(869))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0870_typed() -> None:
    """tail=+870B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((870 * 7) % 251) for _ in range(870))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0871_typed() -> None:
    """tail=+871B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((871 * 7) % 251) for _ in range(871))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0872_typed() -> None:
    """tail=+872B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((872 * 7) % 251) for _ in range(872))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0873_typed() -> None:
    """tail=+873B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((873 * 7) % 251) for _ in range(873))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0874_typed() -> None:
    """tail=+874B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((874 * 7) % 251) for _ in range(874))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0875_typed() -> None:
    """tail=+875B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((875 * 7) % 251) for _ in range(875))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0876_typed() -> None:
    """tail=+876B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((876 * 7) % 251) for _ in range(876))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0877_typed() -> None:
    """tail=+877B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((877 * 7) % 251) for _ in range(877))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0878_typed() -> None:
    """tail=+878B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((878 * 7) % 251) for _ in range(878))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0879_typed() -> None:
    """tail=+879B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((879 * 7) % 251) for _ in range(879))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0880_typed() -> None:
    """tail=+880B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((880 * 7) % 251) for _ in range(880))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0881_typed() -> None:
    """tail=+881B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((881 * 7) % 251) for _ in range(881))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0882_typed() -> None:
    """tail=+882B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((882 * 7) % 251) for _ in range(882))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0883_typed() -> None:
    """tail=+883B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((883 * 7) % 251) for _ in range(883))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0884_typed() -> None:
    """tail=+884B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((884 * 7) % 251) for _ in range(884))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0885_typed() -> None:
    """tail=+885B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((885 * 7) % 251) for _ in range(885))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0886_typed() -> None:
    """tail=+886B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((886 * 7) % 251) for _ in range(886))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0887_typed() -> None:
    """tail=+887B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((887 * 7) % 251) for _ in range(887))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0888_typed() -> None:
    """tail=+888B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((888 * 7) % 251) for _ in range(888))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0889_typed() -> None:
    """tail=+889B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((889 * 7) % 251) for _ in range(889))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0890_typed() -> None:
    """tail=+890B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((890 * 7) % 251) for _ in range(890))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0891_typed() -> None:
    """tail=+891B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((891 * 7) % 251) for _ in range(891))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0892_typed() -> None:
    """tail=+892B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((892 * 7) % 251) for _ in range(892))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0893_typed() -> None:
    """tail=+893B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((893 * 7) % 251) for _ in range(893))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0894_typed() -> None:
    """tail=+894B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((894 * 7) % 251) for _ in range(894))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0895_typed() -> None:
    """tail=+895B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((895 * 7) % 251) for _ in range(895))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0896_typed() -> None:
    """tail=+896B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((896 * 7) % 251) for _ in range(896))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0897_typed() -> None:
    """tail=+897B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((897 * 7) % 251) for _ in range(897))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0898_typed() -> None:
    """tail=+898B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((898 * 7) % 251) for _ in range(898))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0899_typed() -> None:
    """tail=+899B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((899 * 7) % 251) for _ in range(899))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0900_typed() -> None:
    """tail=+900B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((900 * 7) % 251) for _ in range(900))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0901_typed() -> None:
    """tail=+901B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((901 * 7) % 251) for _ in range(901))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0902_typed() -> None:
    """tail=+902B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((902 * 7) % 251) for _ in range(902))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0903_typed() -> None:
    """tail=+903B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((903 * 7) % 251) for _ in range(903))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0904_typed() -> None:
    """tail=+904B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((904 * 7) % 251) for _ in range(904))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0905_typed() -> None:
    """tail=+905B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((905 * 7) % 251) for _ in range(905))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0906_typed() -> None:
    """tail=+906B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((906 * 7) % 251) for _ in range(906))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0907_typed() -> None:
    """tail=+907B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((907 * 7) % 251) for _ in range(907))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0908_typed() -> None:
    """tail=+908B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((908 * 7) % 251) for _ in range(908))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0909_typed() -> None:
    """tail=+909B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((909 * 7) % 251) for _ in range(909))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0910_typed() -> None:
    """tail=+910B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((910 * 7) % 251) for _ in range(910))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0911_typed() -> None:
    """tail=+911B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((911 * 7) % 251) for _ in range(911))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0912_typed() -> None:
    """tail=+912B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((912 * 7) % 251) for _ in range(912))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0913_typed() -> None:
    """tail=+913B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((913 * 7) % 251) for _ in range(913))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0914_typed() -> None:
    """tail=+914B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((914 * 7) % 251) for _ in range(914))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0915_typed() -> None:
    """tail=+915B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((915 * 7) % 251) for _ in range(915))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0916_typed() -> None:
    """tail=+916B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((916 * 7) % 251) for _ in range(916))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0917_typed() -> None:
    """tail=+917B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((917 * 7) % 251) for _ in range(917))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0918_typed() -> None:
    """tail=+918B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((918 * 7) % 251) for _ in range(918))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0919_typed() -> None:
    """tail=+919B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((919 * 7) % 251) for _ in range(919))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0920_typed() -> None:
    """tail=+920B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((920 * 7) % 251) for _ in range(920))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0921_typed() -> None:
    """tail=+921B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((921 * 7) % 251) for _ in range(921))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0922_typed() -> None:
    """tail=+922B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((922 * 7) % 251) for _ in range(922))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0923_typed() -> None:
    """tail=+923B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((923 * 7) % 251) for _ in range(923))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0924_typed() -> None:
    """tail=+924B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((924 * 7) % 251) for _ in range(924))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0925_typed() -> None:
    """tail=+925B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((925 * 7) % 251) for _ in range(925))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0926_typed() -> None:
    """tail=+926B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((926 * 7) % 251) for _ in range(926))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0927_typed() -> None:
    """tail=+927B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((927 * 7) % 251) for _ in range(927))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0928_typed() -> None:
    """tail=+928B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((928 * 7) % 251) for _ in range(928))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0929_typed() -> None:
    """tail=+929B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((929 * 7) % 251) for _ in range(929))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0930_typed() -> None:
    """tail=+930B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((930 * 7) % 251) for _ in range(930))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0931_typed() -> None:
    """tail=+931B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((931 * 7) % 251) for _ in range(931))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0932_typed() -> None:
    """tail=+932B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((932 * 7) % 251) for _ in range(932))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0933_typed() -> None:
    """tail=+933B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((933 * 7) % 251) for _ in range(933))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0934_typed() -> None:
    """tail=+934B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((934 * 7) % 251) for _ in range(934))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0935_typed() -> None:
    """tail=+935B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((935 * 7) % 251) for _ in range(935))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0936_typed() -> None:
    """tail=+936B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((936 * 7) % 251) for _ in range(936))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0937_typed() -> None:
    """tail=+937B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((937 * 7) % 251) for _ in range(937))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0938_typed() -> None:
    """tail=+938B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((938 * 7) % 251) for _ in range(938))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0939_typed() -> None:
    """tail=+939B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((939 * 7) % 251) for _ in range(939))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0940_typed() -> None:
    """tail=+940B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((940 * 7) % 251) for _ in range(940))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0941_typed() -> None:
    """tail=+941B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((941 * 7) % 251) for _ in range(941))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0942_typed() -> None:
    """tail=+942B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((942 * 7) % 251) for _ in range(942))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0943_typed() -> None:
    """tail=+943B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((943 * 7) % 251) for _ in range(943))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0944_typed() -> None:
    """tail=+944B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((944 * 7) % 251) for _ in range(944))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0945_typed() -> None:
    """tail=+945B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((945 * 7) % 251) for _ in range(945))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0946_typed() -> None:
    """tail=+946B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((946 * 7) % 251) for _ in range(946))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0947_typed() -> None:
    """tail=+947B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((947 * 7) % 251) for _ in range(947))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0948_typed() -> None:
    """tail=+948B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((948 * 7) % 251) for _ in range(948))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0949_typed() -> None:
    """tail=+949B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((949 * 7) % 251) for _ in range(949))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0950_typed() -> None:
    """tail=+950B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((950 * 7) % 251) for _ in range(950))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0951_typed() -> None:
    """tail=+951B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((951 * 7) % 251) for _ in range(951))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0952_typed() -> None:
    """tail=+952B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((952 * 7) % 251) for _ in range(952))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0953_typed() -> None:
    """tail=+953B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((953 * 7) % 251) for _ in range(953))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0954_typed() -> None:
    """tail=+954B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((954 * 7) % 251) for _ in range(954))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0955_typed() -> None:
    """tail=+955B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((955 * 7) % 251) for _ in range(955))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0956_typed() -> None:
    """tail=+956B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((956 * 7) % 251) for _ in range(956))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0957_typed() -> None:
    """tail=+957B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((957 * 7) % 251) for _ in range(957))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0958_typed() -> None:
    """tail=+958B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((958 * 7) % 251) for _ in range(958))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0959_typed() -> None:
    """tail=+959B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((959 * 7) % 251) for _ in range(959))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0960_typed() -> None:
    """tail=+960B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((960 * 7) % 251) for _ in range(960))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0961_typed() -> None:
    """tail=+961B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((961 * 7) % 251) for _ in range(961))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0962_typed() -> None:
    """tail=+962B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((962 * 7) % 251) for _ in range(962))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0963_typed() -> None:
    """tail=+963B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((963 * 7) % 251) for _ in range(963))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0964_typed() -> None:
    """tail=+964B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((964 * 7) % 251) for _ in range(964))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0965_typed() -> None:
    """tail=+965B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((965 * 7) % 251) for _ in range(965))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0966_typed() -> None:
    """tail=+966B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((966 * 7) % 251) for _ in range(966))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0967_typed() -> None:
    """tail=+967B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((967 * 7) % 251) for _ in range(967))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0968_typed() -> None:
    """tail=+968B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((968 * 7) % 251) for _ in range(968))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0969_typed() -> None:
    """tail=+969B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((969 * 7) % 251) for _ in range(969))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0970_typed() -> None:
    """tail=+970B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((970 * 7) % 251) for _ in range(970))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0971_typed() -> None:
    """tail=+971B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((971 * 7) % 251) for _ in range(971))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0972_typed() -> None:
    """tail=+972B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((972 * 7) % 251) for _ in range(972))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0973_typed() -> None:
    """tail=+973B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((973 * 7) % 251) for _ in range(973))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0974_typed() -> None:
    """tail=+974B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((974 * 7) % 251) for _ in range(974))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0975_typed() -> None:
    """tail=+975B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((975 * 7) % 251) for _ in range(975))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0976_typed() -> None:
    """tail=+976B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((976 * 7) % 251) for _ in range(976))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0977_typed() -> None:
    """tail=+977B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((977 * 7) % 251) for _ in range(977))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0978_typed() -> None:
    """tail=+978B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((978 * 7) % 251) for _ in range(978))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0979_typed() -> None:
    """tail=+979B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((979 * 7) % 251) for _ in range(979))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0980_typed() -> None:
    """tail=+980B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((980 * 7) % 251) for _ in range(980))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0981_typed() -> None:
    """tail=+981B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((981 * 7) % 251) for _ in range(981))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0982_typed() -> None:
    """tail=+982B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((982 * 7) % 251) for _ in range(982))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0983_typed() -> None:
    """tail=+983B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((983 * 7) % 251) for _ in range(983))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0984_typed() -> None:
    """tail=+984B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((984 * 7) % 251) for _ in range(984))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0985_typed() -> None:
    """tail=+985B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((985 * 7) % 251) for _ in range(985))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0986_typed() -> None:
    """tail=+986B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((986 * 7) % 251) for _ in range(986))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0987_typed() -> None:
    """tail=+987B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((987 * 7) % 251) for _ in range(987))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0988_typed() -> None:
    """tail=+988B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((988 * 7) % 251) for _ in range(988))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0989_typed() -> None:
    """tail=+989B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((989 * 7) % 251) for _ in range(989))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0990_typed() -> None:
    """tail=+990B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((990 * 7) % 251) for _ in range(990))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0991_typed() -> None:
    """tail=+991B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((991 * 7) % 251) for _ in range(991))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0992_typed() -> None:
    """tail=+992B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((992 * 7) % 251) for _ in range(992))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0993_typed() -> None:
    """tail=+993B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((993 * 7) % 251) for _ in range(993))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0994_typed() -> None:
    """tail=+994B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((994 * 7) % 251) for _ in range(994))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0995_typed() -> None:
    """tail=+995B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((995 * 7) % 251) for _ in range(995))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0996_typed() -> None:
    """tail=+996B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((996 * 7) % 251) for _ in range(996))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0997_typed() -> None:
    """tail=+997B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((997 * 7) % 251) for _ in range(997))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0998_typed() -> None:
    """tail=+998B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((998 * 7) % 251) for _ in range(998))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail0999_typed() -> None:
    """tail=+999B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((999 * 7) % 251) for _ in range(999))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1000_typed() -> None:
    """tail=+1000B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1000 * 7) % 251) for _ in range(1000))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1001_typed() -> None:
    """tail=+1001B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1001 * 7) % 251) for _ in range(1001))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1002_typed() -> None:
    """tail=+1002B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1002 * 7) % 251) for _ in range(1002))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1003_typed() -> None:
    """tail=+1003B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1003 * 7) % 251) for _ in range(1003))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1004_typed() -> None:
    """tail=+1004B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1004 * 7) % 251) for _ in range(1004))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_trail_trail1005_typed() -> None:
    """tail=+1005B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1005 * 7) % 251) for _ in range(1005))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1006_typed() -> None:
    """tail=+1006B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1006 * 7) % 251) for _ in range(1006))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1007_typed() -> None:
    """tail=+1007B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1007 * 7) % 251) for _ in range(1007))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1008_typed() -> None:
    """tail=+1008B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1008 * 7) % 251) for _ in range(1008))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1009_typed() -> None:
    """tail=+1009B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1009 * 7) % 251) for _ in range(1009))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1010_typed() -> None:
    """tail=+1010B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1010 * 7) % 251) for _ in range(1010))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1011_typed() -> None:
    """tail=+1011B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1011 * 7) % 251) for _ in range(1011))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1012_typed() -> None:
    """tail=+1012B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1012 * 7) % 251) for _ in range(1012))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1013_typed() -> None:
    """tail=+1013B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1013 * 7) % 251) for _ in range(1013))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1014_typed() -> None:
    """tail=+1014B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1014 * 7) % 251) for _ in range(1014))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1015_typed() -> None:
    """tail=+1015B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1015 * 7) % 251) for _ in range(1015))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1016_typed() -> None:
    """tail=+1016B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1016 * 7) % 251) for _ in range(1016))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1017_typed() -> None:
    """tail=+1017B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1017 * 7) % 251) for _ in range(1017))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1018_typed() -> None:
    """tail=+1018B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1018 * 7) % 251) for _ in range(1018))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1019_typed() -> None:
    """tail=+1019B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1019 * 7) % 251) for _ in range(1019))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1020_typed() -> None:
    """tail=+1020B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1020 * 7) % 251) for _ in range(1020))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1021_typed() -> None:
    """tail=+1021B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1021 * 7) % 251) for _ in range(1021))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1022_typed() -> None:
    """tail=+1022B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1022 * 7) % 251) for _ in range(1022))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1023_typed() -> None:
    """tail=+1023B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1023 * 7) % 251) for _ in range(1023))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1024_typed() -> None:
    """tail=+1024B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1024 * 7) % 251) for _ in range(1024))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1025_typed() -> None:
    """tail=+1025B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1025 * 7) % 251) for _ in range(1025))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1026_typed() -> None:
    """tail=+1026B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1026 * 7) % 251) for _ in range(1026))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1027_typed() -> None:
    """tail=+1027B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1027 * 7) % 251) for _ in range(1027))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1028_typed() -> None:
    """tail=+1028B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1028 * 7) % 251) for _ in range(1028))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1029_typed() -> None:
    """tail=+1029B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1029 * 7) % 251) for _ in range(1029))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1030_typed() -> None:
    """tail=+1030B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1030 * 7) % 251) for _ in range(1030))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1031_typed() -> None:
    """tail=+1031B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1031 * 7) % 251) for _ in range(1031))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1032_typed() -> None:
    """tail=+1032B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1032 * 7) % 251) for _ in range(1032))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1033_typed() -> None:
    """tail=+1033B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1033 * 7) % 251) for _ in range(1033))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1034_typed() -> None:
    """tail=+1034B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1034 * 7) % 251) for _ in range(1034))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1035_typed() -> None:
    """tail=+1035B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1035 * 7) % 251) for _ in range(1035))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1036_typed() -> None:
    """tail=+1036B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1036 * 7) % 251) for _ in range(1036))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1037_typed() -> None:
    """tail=+1037B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1037 * 7) % 251) for _ in range(1037))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1038_typed() -> None:
    """tail=+1038B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1038 * 7) % 251) for _ in range(1038))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1039_typed() -> None:
    """tail=+1039B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1039 * 7) % 251) for _ in range(1039))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1040_typed() -> None:
    """tail=+1040B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1040 * 7) % 251) for _ in range(1040))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1041_typed() -> None:
    """tail=+1041B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1041 * 7) % 251) for _ in range(1041))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1042_typed() -> None:
    """tail=+1042B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1042 * 7) % 251) for _ in range(1042))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1043_typed() -> None:
    """tail=+1043B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1043 * 7) % 251) for _ in range(1043))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1044_typed() -> None:
    """tail=+1044B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1044 * 7) % 251) for _ in range(1044))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1045_typed() -> None:
    """tail=+1045B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1045 * 7) % 251) for _ in range(1045))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1046_typed() -> None:
    """tail=+1046B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1046 * 7) % 251) for _ in range(1046))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1047_typed() -> None:
    """tail=+1047B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1047 * 7) % 251) for _ in range(1047))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1048_typed() -> None:
    """tail=+1048B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1048 * 7) % 251) for _ in range(1048))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1049_typed() -> None:
    """tail=+1049B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1049 * 7) % 251) for _ in range(1049))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1050_typed() -> None:
    """tail=+1050B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1050 * 7) % 251) for _ in range(1050))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1051_typed() -> None:
    """tail=+1051B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1051 * 7) % 251) for _ in range(1051))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1052_typed() -> None:
    """tail=+1052B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1052 * 7) % 251) for _ in range(1052))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1053_typed() -> None:
    """tail=+1053B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1053 * 7) % 251) for _ in range(1053))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1054_typed() -> None:
    """tail=+1054B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1054 * 7) % 251) for _ in range(1054))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1055_typed() -> None:
    """tail=+1055B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1055 * 7) % 251) for _ in range(1055))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1056_typed() -> None:
    """tail=+1056B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1056 * 7) % 251) for _ in range(1056))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1057_typed() -> None:
    """tail=+1057B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1057 * 7) % 251) for _ in range(1057))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1058_typed() -> None:
    """tail=+1058B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1058 * 7) % 251) for _ in range(1058))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1059_typed() -> None:
    """tail=+1059B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1059 * 7) % 251) for _ in range(1059))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1060_typed() -> None:
    """tail=+1060B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1060 * 7) % 251) for _ in range(1060))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1061_typed() -> None:
    """tail=+1061B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1061 * 7) % 251) for _ in range(1061))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1062_typed() -> None:
    """tail=+1062B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1062 * 7) % 251) for _ in range(1062))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1063_typed() -> None:
    """tail=+1063B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1063 * 7) % 251) for _ in range(1063))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1064_typed() -> None:
    """tail=+1064B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1064 * 7) % 251) for _ in range(1064))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1065_typed() -> None:
    """tail=+1065B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1065 * 7) % 251) for _ in range(1065))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1066_typed() -> None:
    """tail=+1066B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1066 * 7) % 251) for _ in range(1066))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1067_typed() -> None:
    """tail=+1067B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1067 * 7) % 251) for _ in range(1067))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1068_typed() -> None:
    """tail=+1068B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1068 * 7) % 251) for _ in range(1068))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1069_typed() -> None:
    """tail=+1069B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1069 * 7) % 251) for _ in range(1069))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1070_typed() -> None:
    """tail=+1070B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1070 * 7) % 251) for _ in range(1070))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1071_typed() -> None:
    """tail=+1071B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1071 * 7) % 251) for _ in range(1071))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1072_typed() -> None:
    """tail=+1072B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1072 * 7) % 251) for _ in range(1072))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1073_typed() -> None:
    """tail=+1073B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1073 * 7) % 251) for _ in range(1073))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1074_typed() -> None:
    """tail=+1074B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1074 * 7) % 251) for _ in range(1074))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1075_typed() -> None:
    """tail=+1075B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1075 * 7) % 251) for _ in range(1075))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1076_typed() -> None:
    """tail=+1076B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1076 * 7) % 251) for _ in range(1076))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1077_typed() -> None:
    """tail=+1077B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1077 * 7) % 251) for _ in range(1077))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1078_typed() -> None:
    """tail=+1078B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1078 * 7) % 251) for _ in range(1078))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1079_typed() -> None:
    """tail=+1079B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1079 * 7) % 251) for _ in range(1079))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1080_typed() -> None:
    """tail=+1080B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1080 * 7) % 251) for _ in range(1080))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1081_typed() -> None:
    """tail=+1081B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1081 * 7) % 251) for _ in range(1081))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1082_typed() -> None:
    """tail=+1082B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1082 * 7) % 251) for _ in range(1082))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1083_typed() -> None:
    """tail=+1083B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1083 * 7) % 251) for _ in range(1083))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1084_typed() -> None:
    """tail=+1084B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1084 * 7) % 251) for _ in range(1084))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1085_typed() -> None:
    """tail=+1085B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1085 * 7) % 251) for _ in range(1085))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1086_typed() -> None:
    """tail=+1086B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1086 * 7) % 251) for _ in range(1086))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1087_typed() -> None:
    """tail=+1087B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1087 * 7) % 251) for _ in range(1087))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1088_typed() -> None:
    """tail=+1088B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1088 * 7) % 251) for _ in range(1088))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1089_typed() -> None:
    """tail=+1089B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1089 * 7) % 251) for _ in range(1089))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1090_typed() -> None:
    """tail=+1090B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1090 * 7) % 251) for _ in range(1090))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1091_typed() -> None:
    """tail=+1091B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1091 * 7) % 251) for _ in range(1091))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1092_typed() -> None:
    """tail=+1092B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1092 * 7) % 251) for _ in range(1092))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1093_typed() -> None:
    """tail=+1093B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1093 * 7) % 251) for _ in range(1093))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1094_typed() -> None:
    """tail=+1094B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1094 * 7) % 251) for _ in range(1094))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1095_typed() -> None:
    """tail=+1095B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1095 * 7) % 251) for _ in range(1095))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1096_typed() -> None:
    """tail=+1096B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1096 * 7) % 251) for _ in range(1096))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1097_typed() -> None:
    """tail=+1097B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1097 * 7) % 251) for _ in range(1097))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1098_typed() -> None:
    """tail=+1098B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1098 * 7) % 251) for _ in range(1098))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1099_typed() -> None:
    """tail=+1099B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1099 * 7) % 251) for _ in range(1099))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1100_typed() -> None:
    """tail=+1100B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1100 * 7) % 251) for _ in range(1100))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1101_typed() -> None:
    """tail=+1101B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1101 * 7) % 251) for _ in range(1101))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1102_typed() -> None:
    """tail=+1102B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1102 * 7) % 251) for _ in range(1102))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1103_typed() -> None:
    """tail=+1103B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1103 * 7) % 251) for _ in range(1103))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1104_typed() -> None:
    """tail=+1104B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1104 * 7) % 251) for _ in range(1104))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1105_typed() -> None:
    """tail=+1105B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1105 * 7) % 251) for _ in range(1105))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1106_typed() -> None:
    """tail=+1106B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1106 * 7) % 251) for _ in range(1106))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1107_typed() -> None:
    """tail=+1107B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1107 * 7) % 251) for _ in range(1107))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1108_typed() -> None:
    """tail=+1108B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1108 * 7) % 251) for _ in range(1108))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1109_typed() -> None:
    """tail=+1109B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1109 * 7) % 251) for _ in range(1109))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1110_typed() -> None:
    """tail=+1110B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1110 * 7) % 251) for _ in range(1110))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1111_typed() -> None:
    """tail=+1111B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1111 * 7) % 251) for _ in range(1111))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1112_typed() -> None:
    """tail=+1112B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1112 * 7) % 251) for _ in range(1112))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1113_typed() -> None:
    """tail=+1113B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1113 * 7) % 251) for _ in range(1113))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1114_typed() -> None:
    """tail=+1114B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1114 * 7) % 251) for _ in range(1114))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1115_typed() -> None:
    """tail=+1115B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1115 * 7) % 251) for _ in range(1115))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1116_typed() -> None:
    """tail=+1116B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1116 * 7) % 251) for _ in range(1116))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1117_typed() -> None:
    """tail=+1117B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1117 * 7) % 251) for _ in range(1117))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1118_typed() -> None:
    """tail=+1118B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1118 * 7) % 251) for _ in range(1118))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1119_typed() -> None:
    """tail=+1119B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1119 * 7) % 251) for _ in range(1119))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1120_typed() -> None:
    """tail=+1120B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1120 * 7) % 251) for _ in range(1120))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1121_typed() -> None:
    """tail=+1121B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1121 * 7) % 251) for _ in range(1121))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1122_typed() -> None:
    """tail=+1122B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1122 * 7) % 251) for _ in range(1122))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1123_typed() -> None:
    """tail=+1123B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1123 * 7) % 251) for _ in range(1123))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1124_typed() -> None:
    """tail=+1124B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1124 * 7) % 251) for _ in range(1124))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1125_typed() -> None:
    """tail=+1125B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1125 * 7) % 251) for _ in range(1125))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1126_typed() -> None:
    """tail=+1126B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1126 * 7) % 251) for _ in range(1126))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1127_typed() -> None:
    """tail=+1127B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1127 * 7) % 251) for _ in range(1127))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1128_typed() -> None:
    """tail=+1128B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1128 * 7) % 251) for _ in range(1128))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1129_typed() -> None:
    """tail=+1129B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1129 * 7) % 251) for _ in range(1129))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1130_typed() -> None:
    """tail=+1130B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1130 * 7) % 251) for _ in range(1130))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1131_typed() -> None:
    """tail=+1131B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1131 * 7) % 251) for _ in range(1131))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1132_typed() -> None:
    """tail=+1132B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1132 * 7) % 251) for _ in range(1132))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1133_typed() -> None:
    """tail=+1133B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1133 * 7) % 251) for _ in range(1133))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1134_typed() -> None:
    """tail=+1134B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1134 * 7) % 251) for _ in range(1134))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1135_typed() -> None:
    """tail=+1135B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1135 * 7) % 251) for _ in range(1135))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1136_typed() -> None:
    """tail=+1136B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1136 * 7) % 251) for _ in range(1136))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1137_typed() -> None:
    """tail=+1137B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1137 * 7) % 251) for _ in range(1137))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1138_typed() -> None:
    """tail=+1138B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1138 * 7) % 251) for _ in range(1138))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1139_typed() -> None:
    """tail=+1139B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1139 * 7) % 251) for _ in range(1139))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1140_typed() -> None:
    """tail=+1140B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1140 * 7) % 251) for _ in range(1140))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1141_typed() -> None:
    """tail=+1141B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1141 * 7) % 251) for _ in range(1141))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1142_typed() -> None:
    """tail=+1142B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1142 * 7) % 251) for _ in range(1142))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1143_typed() -> None:
    """tail=+1143B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1143 * 7) % 251) for _ in range(1143))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1144_typed() -> None:
    """tail=+1144B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1144 * 7) % 251) for _ in range(1144))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1145_typed() -> None:
    """tail=+1145B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1145 * 7) % 251) for _ in range(1145))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1146_typed() -> None:
    """tail=+1146B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1146 * 7) % 251) for _ in range(1146))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1147_typed() -> None:
    """tail=+1147B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1147 * 7) % 251) for _ in range(1147))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1148_typed() -> None:
    """tail=+1148B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1148 * 7) % 251) for _ in range(1148))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1149_typed() -> None:
    """tail=+1149B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1149 * 7) % 251) for _ in range(1149))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1150_typed() -> None:
    """tail=+1150B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1150 * 7) % 251) for _ in range(1150))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1151_typed() -> None:
    """tail=+1151B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1151 * 7) % 251) for _ in range(1151))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1152_typed() -> None:
    """tail=+1152B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1152 * 7) % 251) for _ in range(1152))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1153_typed() -> None:
    """tail=+1153B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1153 * 7) % 251) for _ in range(1153))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1154_typed() -> None:
    """tail=+1154B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1154 * 7) % 251) for _ in range(1154))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1155_typed() -> None:
    """tail=+1155B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1155 * 7) % 251) for _ in range(1155))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1156_typed() -> None:
    """tail=+1156B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1156 * 7) % 251) for _ in range(1156))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1157_typed() -> None:
    """tail=+1157B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1157 * 7) % 251) for _ in range(1157))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1158_typed() -> None:
    """tail=+1158B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1158 * 7) % 251) for _ in range(1158))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1159_typed() -> None:
    """tail=+1159B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1159 * 7) % 251) for _ in range(1159))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1160_typed() -> None:
    """tail=+1160B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1160 * 7) % 251) for _ in range(1160))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1161_typed() -> None:
    """tail=+1161B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1161 * 7) % 251) for _ in range(1161))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1162_typed() -> None:
    """tail=+1162B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1162 * 7) % 251) for _ in range(1162))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1163_typed() -> None:
    """tail=+1163B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1163 * 7) % 251) for _ in range(1163))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1164_typed() -> None:
    """tail=+1164B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1164 * 7) % 251) for _ in range(1164))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1165_typed() -> None:
    """tail=+1165B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1165 * 7) % 251) for _ in range(1165))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1166_typed() -> None:
    """tail=+1166B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1166 * 7) % 251) for _ in range(1166))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1167_typed() -> None:
    """tail=+1167B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1167 * 7) % 251) for _ in range(1167))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1168_typed() -> None:
    """tail=+1168B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1168 * 7) % 251) for _ in range(1168))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1169_typed() -> None:
    """tail=+1169B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1169 * 7) % 251) for _ in range(1169))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1170_typed() -> None:
    """tail=+1170B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1170 * 7) % 251) for _ in range(1170))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1171_typed() -> None:
    """tail=+1171B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1171 * 7) % 251) for _ in range(1171))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1172_typed() -> None:
    """tail=+1172B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1172 * 7) % 251) for _ in range(1172))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1173_typed() -> None:
    """tail=+1173B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1173 * 7) % 251) for _ in range(1173))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1174_typed() -> None:
    """tail=+1174B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1174 * 7) % 251) for _ in range(1174))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1175_typed() -> None:
    """tail=+1175B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1175 * 7) % 251) for _ in range(1175))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1176_typed() -> None:
    """tail=+1176B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1176 * 7) % 251) for _ in range(1176))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1177_typed() -> None:
    """tail=+1177B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1177 * 7) % 251) for _ in range(1177))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1178_typed() -> None:
    """tail=+1178B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1178 * 7) % 251) for _ in range(1178))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1179_typed() -> None:
    """tail=+1179B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1179 * 7) % 251) for _ in range(1179))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1180_typed() -> None:
    """tail=+1180B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1180 * 7) % 251) for _ in range(1180))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1181_typed() -> None:
    """tail=+1181B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1181 * 7) % 251) for _ in range(1181))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1182_typed() -> None:
    """tail=+1182B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1182 * 7) % 251) for _ in range(1182))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1183_typed() -> None:
    """tail=+1183B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1183 * 7) % 251) for _ in range(1183))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1184_typed() -> None:
    """tail=+1184B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1184 * 7) % 251) for _ in range(1184))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1185_typed() -> None:
    """tail=+1185B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1185 * 7) % 251) for _ in range(1185))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1186_typed() -> None:
    """tail=+1186B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1186 * 7) % 251) for _ in range(1186))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1187_typed() -> None:
    """tail=+1187B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1187 * 7) % 251) for _ in range(1187))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1188_typed() -> None:
    """tail=+1188B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1188 * 7) % 251) for _ in range(1188))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1189_typed() -> None:
    """tail=+1189B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1189 * 7) % 251) for _ in range(1189))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1190_typed() -> None:
    """tail=+1190B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1190 * 7) % 251) for _ in range(1190))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1191_typed() -> None:
    """tail=+1191B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1191 * 7) % 251) for _ in range(1191))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1192_typed() -> None:
    """tail=+1192B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1192 * 7) % 251) for _ in range(1192))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1193_typed() -> None:
    """tail=+1193B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1193 * 7) % 251) for _ in range(1193))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1194_typed() -> None:
    """tail=+1194B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1194 * 7) % 251) for _ in range(1194))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1195_typed() -> None:
    """tail=+1195B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1195 * 7) % 251) for _ in range(1195))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1196_typed() -> None:
    """tail=+1196B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1196 * 7) % 251) for _ in range(1196))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1197_typed() -> None:
    """tail=+1197B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1197 * 7) % 251) for _ in range(1197))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1198_typed() -> None:
    """tail=+1198B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1198 * 7) % 251) for _ in range(1198))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1199_typed() -> None:
    """tail=+1199B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1199 * 7) % 251) for _ in range(1199))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trail_trail1200_typed() -> None:
    """tail=+1200B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(base + bytes(((1200 * 7) % 251) for _ in range(1200))))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'
