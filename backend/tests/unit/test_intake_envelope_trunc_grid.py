"""Intake envelope tail-truncation walk grid: frozen verdict per cell.

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


def test_trunc_trunc0001_typed() -> None:
    """tail=-1B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0002_typed() -> None:
    """tail=-2B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-2]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0003_typed() -> None:
    """tail=-3B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-3]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0004_typed() -> None:
    """tail=-4B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-4]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0005_typed() -> None:
    """tail=-5B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-5]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0006_typed() -> None:
    """tail=-6B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-6]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0007_typed() -> None:
    """tail=-7B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-7]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0008_typed() -> None:
    """tail=-8B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-8]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0009_typed() -> None:
    """tail=-9B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-9]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0010_typed() -> None:
    """tail=-10B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-10]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0011_typed() -> None:
    """tail=-11B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-11]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0012_typed() -> None:
    """tail=-12B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-12]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0013_typed() -> None:
    """tail=-13B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-13]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0014_typed() -> None:
    """tail=-14B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-14]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0015_typed() -> None:
    """tail=-15B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-15]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0016_typed() -> None:
    """tail=-16B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-16]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0017_typed() -> None:
    """tail=-17B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-17]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0018_typed() -> None:
    """tail=-18B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-18]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0019_typed() -> None:
    """tail=-19B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-19]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0020_typed() -> None:
    """tail=-20B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-20]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0021_typed() -> None:
    """tail=-21B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-21]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0022_typed() -> None:
    """tail=-22B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-22]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0023_typed() -> None:
    """tail=-23B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-23]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0024_typed() -> None:
    """tail=-24B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-24]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0025_typed() -> None:
    """tail=-25B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-25]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0026_typed() -> None:
    """tail=-26B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-26]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0027_typed() -> None:
    """tail=-27B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-27]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0028_typed() -> None:
    """tail=-28B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-28]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0029_typed() -> None:
    """tail=-29B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-29]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0030_typed() -> None:
    """tail=-30B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-30]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0031_typed() -> None:
    """tail=-31B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-31]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0032_typed() -> None:
    """tail=-32B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-32]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0033_typed() -> None:
    """tail=-33B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-33]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0034_typed() -> None:
    """tail=-34B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-34]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0035_typed() -> None:
    """tail=-35B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-35]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0036_typed() -> None:
    """tail=-36B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-36]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0037_typed() -> None:
    """tail=-37B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-37]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0038_typed() -> None:
    """tail=-38B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-38]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0039_typed() -> None:
    """tail=-39B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-39]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0040_typed() -> None:
    """tail=-40B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-40]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0041_typed() -> None:
    """tail=-41B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-41]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0042_typed() -> None:
    """tail=-42B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-42]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0043_typed() -> None:
    """tail=-43B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-43]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0044_typed() -> None:
    """tail=-44B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-44]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0045_typed() -> None:
    """tail=-45B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-45]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0046_typed() -> None:
    """tail=-46B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-46]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0047_typed() -> None:
    """tail=-47B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-47]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0048_typed() -> None:
    """tail=-48B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-48]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0049_typed() -> None:
    """tail=-49B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-49]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0050_typed() -> None:
    """tail=-50B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-50]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0051_typed() -> None:
    """tail=-51B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-51]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0052_typed() -> None:
    """tail=-52B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-52]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0053_typed() -> None:
    """tail=-53B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-53]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0054_typed() -> None:
    """tail=-54B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-54]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0055_typed() -> None:
    """tail=-55B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-55]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0056_typed() -> None:
    """tail=-56B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-56]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0057_typed() -> None:
    """tail=-57B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-57]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0058_typed() -> None:
    """tail=-58B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-58]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0059_typed() -> None:
    """tail=-59B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-59]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0060_typed() -> None:
    """tail=-60B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-60]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0061_typed() -> None:
    """tail=-61B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-61]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0062_typed() -> None:
    """tail=-62B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-62]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0063_typed() -> None:
    """tail=-63B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-63]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0064_typed() -> None:
    """tail=-64B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-64]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0065_typed() -> None:
    """tail=-65B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-65]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0066_typed() -> None:
    """tail=-66B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-66]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0067_typed() -> None:
    """tail=-67B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-67]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0068_typed() -> None:
    """tail=-68B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-68]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0069_typed() -> None:
    """tail=-69B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-69]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0070_typed() -> None:
    """tail=-70B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-70]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0071_typed() -> None:
    """tail=-71B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-71]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0072_typed() -> None:
    """tail=-72B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-72]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0073_typed() -> None:
    """tail=-73B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-73]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0074_typed() -> None:
    """tail=-74B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-74]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0075_typed() -> None:
    """tail=-75B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-75]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0076_typed() -> None:
    """tail=-76B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-76]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0077_typed() -> None:
    """tail=-77B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-77]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0078_typed() -> None:
    """tail=-78B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-78]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0079_typed() -> None:
    """tail=-79B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-79]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0080_typed() -> None:
    """tail=-80B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-80]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0081_typed() -> None:
    """tail=-81B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-81]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0082_typed() -> None:
    """tail=-82B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-82]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0083_typed() -> None:
    """tail=-83B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-83]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0084_typed() -> None:
    """tail=-84B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-84]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0085_typed() -> None:
    """tail=-85B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-85]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0086_typed() -> None:
    """tail=-86B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-86]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0087_typed() -> None:
    """tail=-87B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-87]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_trunc_trunc0088_typed() -> None:
    """tail=-88B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-88]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_trunc_trunc0089_typed() -> None:
    """tail=-89B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-89]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_trunc_trunc0090_typed() -> None:
    """tail=-90B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-90]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_trunc_trunc0091_typed() -> None:
    """tail=-91B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-91]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_trunc_trunc0092_typed() -> None:
    """tail=-92B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-92]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_trunc_trunc0093_typed() -> None:
    """tail=-93B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-93]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_trunc_trunc0094_typed() -> None:
    """tail=-94B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-94]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'authenticated intake context is required'


def test_trunc_trunc0095_typed() -> None:
    """tail=-95B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-95]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0096_typed() -> None:
    """tail=-96B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-96]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0097_typed() -> None:
    """tail=-97B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-97]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0098_typed() -> None:
    """tail=-98B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-98]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0099_typed() -> None:
    """tail=-99B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-99]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0100_typed() -> None:
    """tail=-100B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-100]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0101_typed() -> None:
    """tail=-101B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-101]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0102_typed() -> None:
    """tail=-102B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-102]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0103_typed() -> None:
    """tail=-103B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-103]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0104_typed() -> None:
    """tail=-104B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-104]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0105_typed() -> None:
    """tail=-105B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-105]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0106_typed() -> None:
    """tail=-106B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-106]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0107_typed() -> None:
    """tail=-107B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-107]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0108_typed() -> None:
    """tail=-108B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-108]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0109_typed() -> None:
    """tail=-109B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-109]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0110_typed() -> None:
    """tail=-110B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-110]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0111_typed() -> None:
    """tail=-111B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-111]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0112_typed() -> None:
    """tail=-112B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-112]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0113_typed() -> None:
    """tail=-113B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-113]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0114_typed() -> None:
    """tail=-114B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-114]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0115_typed() -> None:
    """tail=-115B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-115]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0116_typed() -> None:
    """tail=-116B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-116]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0117_typed() -> None:
    """tail=-117B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-117]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0118_typed() -> None:
    """tail=-118B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-118]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0119_typed() -> None:
    """tail=-119B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-119]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0120_typed() -> None:
    """tail=-120B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-120]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0121_typed() -> None:
    """tail=-121B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-121]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0122_typed() -> None:
    """tail=-122B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-122]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0123_typed() -> None:
    """tail=-123B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-123]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0124_typed() -> None:
    """tail=-124B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-124]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0125_typed() -> None:
    """tail=-125B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-125]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0126_typed() -> None:
    """tail=-126B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-126]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0127_typed() -> None:
    """tail=-127B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-127]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0128_typed() -> None:
    """tail=-128B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-128]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0129_typed() -> None:
    """tail=-129B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-129]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0130_typed() -> None:
    """tail=-130B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-130]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0131_typed() -> None:
    """tail=-131B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-131]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0132_typed() -> None:
    """tail=-132B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-132]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0133_typed() -> None:
    """tail=-133B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-133]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0134_typed() -> None:
    """tail=-134B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-134]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0135_typed() -> None:
    """tail=-135B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-135]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0136_typed() -> None:
    """tail=-136B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-136]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0137_typed() -> None:
    """tail=-137B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-137]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0138_typed() -> None:
    """tail=-138B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-138]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0139_typed() -> None:
    """tail=-139B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-139]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0140_typed() -> None:
    """tail=-140B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-140]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0141_typed() -> None:
    """tail=-141B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-141]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0142_typed() -> None:
    """tail=-142B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-142]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0143_typed() -> None:
    """tail=-143B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-143]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0144_typed() -> None:
    """tail=-144B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-144]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0145_typed() -> None:
    """tail=-145B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-145]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0146_typed() -> None:
    """tail=-146B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-146]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0147_typed() -> None:
    """tail=-147B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-147]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0148_typed() -> None:
    """tail=-148B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-148]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0149_typed() -> None:
    """tail=-149B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-149]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0150_typed() -> None:
    """tail=-150B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-150]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0151_typed() -> None:
    """tail=-151B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-151]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0152_typed() -> None:
    """tail=-152B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-152]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0153_typed() -> None:
    """tail=-153B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-153]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0154_typed() -> None:
    """tail=-154B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-154]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0155_typed() -> None:
    """tail=-155B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-155]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0156_typed() -> None:
    """tail=-156B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-156]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0157_typed() -> None:
    """tail=-157B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-157]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0158_typed() -> None:
    """tail=-158B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-158]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0159_typed() -> None:
    """tail=-159B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-159]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0160_typed() -> None:
    """tail=-160B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-160]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0161_typed() -> None:
    """tail=-161B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-161]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0162_typed() -> None:
    """tail=-162B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-162]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0163_typed() -> None:
    """tail=-163B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-163]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0164_typed() -> None:
    """tail=-164B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-164]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0165_typed() -> None:
    """tail=-165B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-165]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0166_typed() -> None:
    """tail=-166B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-166]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0167_typed() -> None:
    """tail=-167B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-167]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0168_typed() -> None:
    """tail=-168B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-168]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0169_typed() -> None:
    """tail=-169B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-169]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0170_typed() -> None:
    """tail=-170B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-170]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0171_typed() -> None:
    """tail=-171B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-171]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0172_typed() -> None:
    """tail=-172B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-172]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0173_typed() -> None:
    """tail=-173B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-173]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0174_typed() -> None:
    """tail=-174B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-174]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0175_typed() -> None:
    """tail=-175B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-175]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0176_typed() -> None:
    """tail=-176B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-176]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0177_typed() -> None:
    """tail=-177B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-177]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0178_typed() -> None:
    """tail=-178B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-178]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0179_typed() -> None:
    """tail=-179B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-179]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0180_typed() -> None:
    """tail=-180B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-180]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0181_typed() -> None:
    """tail=-181B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-181]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0182_typed() -> None:
    """tail=-182B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-182]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0183_typed() -> None:
    """tail=-183B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-183]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0184_typed() -> None:
    """tail=-184B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-184]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0185_typed() -> None:
    """tail=-185B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-185]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0186_typed() -> None:
    """tail=-186B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-186]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0187_typed() -> None:
    """tail=-187B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-187]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0188_typed() -> None:
    """tail=-188B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-188]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0189_typed() -> None:
    """tail=-189B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-189]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0190_typed() -> None:
    """tail=-190B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-190]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0191_typed() -> None:
    """tail=-191B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-191]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0192_typed() -> None:
    """tail=-192B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-192]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0193_typed() -> None:
    """tail=-193B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-193]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0194_typed() -> None:
    """tail=-194B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-194]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0195_typed() -> None:
    """tail=-195B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-195]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0196_typed() -> None:
    """tail=-196B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-196]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0197_typed() -> None:
    """tail=-197B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-197]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0198_typed() -> None:
    """tail=-198B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-198]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0199_typed() -> None:
    """tail=-199B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-199]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0200_typed() -> None:
    """tail=-200B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-200]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0201_typed() -> None:
    """tail=-201B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-201]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0202_typed() -> None:
    """tail=-202B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-202]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0203_typed() -> None:
    """tail=-203B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-203]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0204_typed() -> None:
    """tail=-204B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-204]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0205_typed() -> None:
    """tail=-205B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-205]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0206_typed() -> None:
    """tail=-206B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-206]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0207_typed() -> None:
    """tail=-207B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-207]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0208_typed() -> None:
    """tail=-208B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-208]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0209_typed() -> None:
    """tail=-209B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-209]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0210_typed() -> None:
    """tail=-210B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-210]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0211_typed() -> None:
    """tail=-211B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-211]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0212_typed() -> None:
    """tail=-212B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-212]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0213_typed() -> None:
    """tail=-213B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-213]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0214_typed() -> None:
    """tail=-214B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-214]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0215_typed() -> None:
    """tail=-215B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-215]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0216_typed() -> None:
    """tail=-216B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-216]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0217_typed() -> None:
    """tail=-217B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-217]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0218_typed() -> None:
    """tail=-218B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-218]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0219_typed() -> None:
    """tail=-219B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-219]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0220_typed() -> None:
    """tail=-220B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-220]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0221_typed() -> None:
    """tail=-221B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-221]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0222_typed() -> None:
    """tail=-222B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-222]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0223_typed() -> None:
    """tail=-223B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-223]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0224_typed() -> None:
    """tail=-224B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-224]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0225_typed() -> None:
    """tail=-225B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-225]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0226_typed() -> None:
    """tail=-226B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-226]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0227_typed() -> None:
    """tail=-227B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-227]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0228_typed() -> None:
    """tail=-228B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-228]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0229_typed() -> None:
    """tail=-229B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-229]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0230_typed() -> None:
    """tail=-230B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-230]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0231_typed() -> None:
    """tail=-231B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-231]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0232_typed() -> None:
    """tail=-232B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-232]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0233_typed() -> None:
    """tail=-233B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-233]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0234_typed() -> None:
    """tail=-234B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-234]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0235_typed() -> None:
    """tail=-235B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-235]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0236_typed() -> None:
    """tail=-236B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-236]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0237_typed() -> None:
    """tail=-237B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-237]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0238_typed() -> None:
    """tail=-238B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-238]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0239_typed() -> None:
    """tail=-239B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-239]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0240_typed() -> None:
    """tail=-240B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-240]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0241_typed() -> None:
    """tail=-241B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-241]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0242_typed() -> None:
    """tail=-242B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-242]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0243_typed() -> None:
    """tail=-243B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-243]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0244_typed() -> None:
    """tail=-244B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-244]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0245_typed() -> None:
    """tail=-245B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-245]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0246_typed() -> None:
    """tail=-246B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-246]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0247_typed() -> None:
    """tail=-247B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-247]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0248_typed() -> None:
    """tail=-248B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-248]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0249_typed() -> None:
    """tail=-249B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-249]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0250_typed() -> None:
    """tail=-250B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-250]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0251_typed() -> None:
    """tail=-251B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-251]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0252_typed() -> None:
    """tail=-252B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-252]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0253_typed() -> None:
    """tail=-253B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-253]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0254_typed() -> None:
    """tail=-254B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-254]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0255_typed() -> None:
    """tail=-255B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-255]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0256_typed() -> None:
    """tail=-256B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-256]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0257_typed() -> None:
    """tail=-257B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-257]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0258_typed() -> None:
    """tail=-258B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-258]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0259_typed() -> None:
    """tail=-259B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-259]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0260_typed() -> None:
    """tail=-260B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-260]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0261_typed() -> None:
    """tail=-261B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-261]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0262_typed() -> None:
    """tail=-262B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-262]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0263_typed() -> None:
    """tail=-263B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-263]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0264_typed() -> None:
    """tail=-264B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-264]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0265_typed() -> None:
    """tail=-265B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-265]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0266_typed() -> None:
    """tail=-266B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-266]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0267_typed() -> None:
    """tail=-267B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-267]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0268_typed() -> None:
    """tail=-268B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-268]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0269_typed() -> None:
    """tail=-269B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-269]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0270_typed() -> None:
    """tail=-270B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-270]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0271_typed() -> None:
    """tail=-271B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-271]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0272_typed() -> None:
    """tail=-272B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-272]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0273_typed() -> None:
    """tail=-273B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-273]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0274_typed() -> None:
    """tail=-274B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-274]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0275_typed() -> None:
    """tail=-275B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-275]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0276_typed() -> None:
    """tail=-276B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-276]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0277_typed() -> None:
    """tail=-277B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-277]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0278_typed() -> None:
    """tail=-278B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-278]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0279_typed() -> None:
    """tail=-279B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-279]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0280_typed() -> None:
    """tail=-280B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-280]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0281_typed() -> None:
    """tail=-281B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-281]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0282_typed() -> None:
    """tail=-282B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-282]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0283_typed() -> None:
    """tail=-283B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-283]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0284_typed() -> None:
    """tail=-284B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-284]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0285_typed() -> None:
    """tail=-285B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-285]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0286_typed() -> None:
    """tail=-286B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-286]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0287_typed() -> None:
    """tail=-287B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-287]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0288_typed() -> None:
    """tail=-288B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-288]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0289_typed() -> None:
    """tail=-289B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-289]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0290_typed() -> None:
    """tail=-290B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-290]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0291_typed() -> None:
    """tail=-291B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-291]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0292_typed() -> None:
    """tail=-292B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-292]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0293_typed() -> None:
    """tail=-293B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-293]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0294_typed() -> None:
    """tail=-294B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-294]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0295_typed() -> None:
    """tail=-295B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-295]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0296_typed() -> None:
    """tail=-296B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-296]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0297_typed() -> None:
    """tail=-297B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-297]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0298_typed() -> None:
    """tail=-298B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-298]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0299_typed() -> None:
    """tail=-299B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-299]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0300_typed() -> None:
    """tail=-300B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-300]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0301_typed() -> None:
    """tail=-301B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-301]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0302_typed() -> None:
    """tail=-302B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-302]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0303_typed() -> None:
    """tail=-303B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-303]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0304_typed() -> None:
    """tail=-304B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-304]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0305_typed() -> None:
    """tail=-305B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-305]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0306_typed() -> None:
    """tail=-306B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-306]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0307_typed() -> None:
    """tail=-307B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-307]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0308_typed() -> None:
    """tail=-308B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-308]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0309_typed() -> None:
    """tail=-309B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-309]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0310_typed() -> None:
    """tail=-310B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-310]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0311_typed() -> None:
    """tail=-311B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-311]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0312_typed() -> None:
    """tail=-312B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-312]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0313_typed() -> None:
    """tail=-313B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-313]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0314_typed() -> None:
    """tail=-314B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-314]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0315_typed() -> None:
    """tail=-315B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-315]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0316_typed() -> None:
    """tail=-316B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-316]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0317_typed() -> None:
    """tail=-317B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-317]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0318_typed() -> None:
    """tail=-318B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-318]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0319_typed() -> None:
    """tail=-319B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-319]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0320_typed() -> None:
    """tail=-320B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-320]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0321_typed() -> None:
    """tail=-321B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-321]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0322_typed() -> None:
    """tail=-322B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-322]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0323_typed() -> None:
    """tail=-323B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-323]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0324_typed() -> None:
    """tail=-324B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-324]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0325_typed() -> None:
    """tail=-325B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-325]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0326_typed() -> None:
    """tail=-326B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-326]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0327_typed() -> None:
    """tail=-327B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-327]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0328_typed() -> None:
    """tail=-328B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-328]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0329_typed() -> None:
    """tail=-329B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-329]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0330_typed() -> None:
    """tail=-330B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-330]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0331_typed() -> None:
    """tail=-331B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-331]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0332_typed() -> None:
    """tail=-332B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-332]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0333_typed() -> None:
    """tail=-333B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-333]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0334_typed() -> None:
    """tail=-334B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-334]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0335_typed() -> None:
    """tail=-335B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-335]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0336_typed() -> None:
    """tail=-336B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-336]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0337_typed() -> None:
    """tail=-337B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-337]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0338_typed() -> None:
    """tail=-338B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-338]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0339_typed() -> None:
    """tail=-339B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-339]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0340_typed() -> None:
    """tail=-340B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-340]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0341_typed() -> None:
    """tail=-341B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-341]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0342_typed() -> None:
    """tail=-342B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-342]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0343_typed() -> None:
    """tail=-343B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-343]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0344_typed() -> None:
    """tail=-344B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-344]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0345_typed() -> None:
    """tail=-345B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-345]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0346_typed() -> None:
    """tail=-346B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-346]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0347_typed() -> None:
    """tail=-347B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-347]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0348_typed() -> None:
    """tail=-348B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-348]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0349_typed() -> None:
    """tail=-349B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-349]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0350_typed() -> None:
    """tail=-350B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-350]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0351_typed() -> None:
    """tail=-351B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-351]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0352_typed() -> None:
    """tail=-352B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-352]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0353_typed() -> None:
    """tail=-353B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-353]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0354_typed() -> None:
    """tail=-354B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-354]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0355_typed() -> None:
    """tail=-355B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-355]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0356_typed() -> None:
    """tail=-356B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-356]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0357_typed() -> None:
    """tail=-357B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-357]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0358_typed() -> None:
    """tail=-358B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-358]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0359_typed() -> None:
    """tail=-359B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-359]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0360_typed() -> None:
    """tail=-360B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-360]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0361_typed() -> None:
    """tail=-361B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-361]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0362_typed() -> None:
    """tail=-362B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-362]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0363_typed() -> None:
    """tail=-363B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-363]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0364_typed() -> None:
    """tail=-364B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-364]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0365_typed() -> None:
    """tail=-365B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-365]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0366_typed() -> None:
    """tail=-366B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-366]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0367_typed() -> None:
    """tail=-367B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-367]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0368_typed() -> None:
    """tail=-368B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-368]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0369_typed() -> None:
    """tail=-369B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-369]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0370_typed() -> None:
    """tail=-370B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-370]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0371_typed() -> None:
    """tail=-371B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-371]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0372_typed() -> None:
    """tail=-372B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-372]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0373_typed() -> None:
    """tail=-373B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-373]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0374_typed() -> None:
    """tail=-374B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-374]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0375_typed() -> None:
    """tail=-375B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-375]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0376_typed() -> None:
    """tail=-376B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-376]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0377_typed() -> None:
    """tail=-377B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-377]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0378_typed() -> None:
    """tail=-378B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-378]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0379_typed() -> None:
    """tail=-379B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-379]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0380_typed() -> None:
    """tail=-380B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-380]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0381_typed() -> None:
    """tail=-381B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-381]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0382_typed() -> None:
    """tail=-382B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-382]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0383_typed() -> None:
    """tail=-383B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-383]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0384_typed() -> None:
    """tail=-384B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-384]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0385_typed() -> None:
    """tail=-385B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-385]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0386_typed() -> None:
    """tail=-386B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-386]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0387_typed() -> None:
    """tail=-387B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-387]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0388_typed() -> None:
    """tail=-388B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-388]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0389_typed() -> None:
    """tail=-389B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-389]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0390_typed() -> None:
    """tail=-390B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-390]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0391_typed() -> None:
    """tail=-391B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-391]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0392_typed() -> None:
    """tail=-392B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-392]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0393_typed() -> None:
    """tail=-393B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-393]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0394_typed() -> None:
    """tail=-394B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-394]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0395_typed() -> None:
    """tail=-395B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-395]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0396_typed() -> None:
    """tail=-396B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-396]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0397_typed() -> None:
    """tail=-397B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-397]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0398_typed() -> None:
    """tail=-398B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-398]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0399_typed() -> None:
    """tail=-399B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-399]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0400_typed() -> None:
    """tail=-400B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-400]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0401_typed() -> None:
    """tail=-401B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-401]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0402_typed() -> None:
    """tail=-402B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-402]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0403_typed() -> None:
    """tail=-403B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-403]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0404_typed() -> None:
    """tail=-404B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-404]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0405_typed() -> None:
    """tail=-405B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-405]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0406_typed() -> None:
    """tail=-406B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-406]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0407_typed() -> None:
    """tail=-407B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-407]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0408_typed() -> None:
    """tail=-408B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-408]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0409_typed() -> None:
    """tail=-409B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-409]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0410_typed() -> None:
    """tail=-410B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-410]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0411_typed() -> None:
    """tail=-411B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-411]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0412_typed() -> None:
    """tail=-412B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-412]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0413_typed() -> None:
    """tail=-413B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-413]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0414_typed() -> None:
    """tail=-414B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-414]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0415_typed() -> None:
    """tail=-415B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-415]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0416_typed() -> None:
    """tail=-416B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-416]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0417_typed() -> None:
    """tail=-417B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-417]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0418_typed() -> None:
    """tail=-418B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-418]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0419_typed() -> None:
    """tail=-419B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-419]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0420_typed() -> None:
    """tail=-420B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-420]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0421_typed() -> None:
    """tail=-421B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-421]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0422_typed() -> None:
    """tail=-422B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-422]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0423_typed() -> None:
    """tail=-423B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-423]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0424_typed() -> None:
    """tail=-424B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-424]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0425_typed() -> None:
    """tail=-425B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-425]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0426_typed() -> None:
    """tail=-426B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-426]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0427_typed() -> None:
    """tail=-427B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-427]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0428_typed() -> None:
    """tail=-428B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-428]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0429_typed() -> None:
    """tail=-429B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-429]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0430_typed() -> None:
    """tail=-430B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-430]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0431_typed() -> None:
    """tail=-431B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-431]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0432_typed() -> None:
    """tail=-432B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-432]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0433_typed() -> None:
    """tail=-433B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-433]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0434_typed() -> None:
    """tail=-434B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-434]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0435_typed() -> None:
    """tail=-435B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-435]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0436_typed() -> None:
    """tail=-436B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-436]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0437_typed() -> None:
    """tail=-437B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-437]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0438_typed() -> None:
    """tail=-438B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-438]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0439_typed() -> None:
    """tail=-439B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-439]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0440_typed() -> None:
    """tail=-440B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-440]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0441_typed() -> None:
    """tail=-441B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-441]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0442_typed() -> None:
    """tail=-442B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-442]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0443_typed() -> None:
    """tail=-443B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-443]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0444_typed() -> None:
    """tail=-444B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-444]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0445_typed() -> None:
    """tail=-445B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-445]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0446_typed() -> None:
    """tail=-446B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-446]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0447_typed() -> None:
    """tail=-447B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-447]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0448_typed() -> None:
    """tail=-448B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-448]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0449_typed() -> None:
    """tail=-449B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-449]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0450_typed() -> None:
    """tail=-450B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-450]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0451_typed() -> None:
    """tail=-451B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-451]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0452_typed() -> None:
    """tail=-452B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-452]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0453_typed() -> None:
    """tail=-453B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-453]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0454_typed() -> None:
    """tail=-454B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-454]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0455_typed() -> None:
    """tail=-455B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-455]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0456_typed() -> None:
    """tail=-456B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-456]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0457_typed() -> None:
    """tail=-457B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-457]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0458_typed() -> None:
    """tail=-458B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-458]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0459_typed() -> None:
    """tail=-459B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-459]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0460_typed() -> None:
    """tail=-460B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-460]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0461_typed() -> None:
    """tail=-461B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-461]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0462_typed() -> None:
    """tail=-462B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-462]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0463_typed() -> None:
    """tail=-463B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-463]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0464_typed() -> None:
    """tail=-464B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-464]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0465_typed() -> None:
    """tail=-465B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-465]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0466_typed() -> None:
    """tail=-466B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-466]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0467_typed() -> None:
    """tail=-467B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-467]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0468_typed() -> None:
    """tail=-468B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-468]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0469_typed() -> None:
    """tail=-469B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-469]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0470_typed() -> None:
    """tail=-470B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-470]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0471_typed() -> None:
    """tail=-471B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-471]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0472_typed() -> None:
    """tail=-472B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-472]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0473_typed() -> None:
    """tail=-473B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-473]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0474_typed() -> None:
    """tail=-474B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-474]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0475_typed() -> None:
    """tail=-475B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-475]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0476_typed() -> None:
    """tail=-476B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-476]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0477_typed() -> None:
    """tail=-477B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-477]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0478_typed() -> None:
    """tail=-478B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-478]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0479_typed() -> None:
    """tail=-479B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-479]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0480_typed() -> None:
    """tail=-480B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-480]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0481_typed() -> None:
    """tail=-481B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-481]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0482_typed() -> None:
    """tail=-482B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-482]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0483_typed() -> None:
    """tail=-483B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-483]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0484_typed() -> None:
    """tail=-484B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-484]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0485_typed() -> None:
    """tail=-485B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-485]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0486_typed() -> None:
    """tail=-486B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-486]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0487_typed() -> None:
    """tail=-487B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-487]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0488_typed() -> None:
    """tail=-488B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-488]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0489_typed() -> None:
    """tail=-489B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-489]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0490_typed() -> None:
    """tail=-490B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-490]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0491_typed() -> None:
    """tail=-491B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-491]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0492_typed() -> None:
    """tail=-492B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-492]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0493_typed() -> None:
    """tail=-493B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-493]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0494_typed() -> None:
    """tail=-494B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-494]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0495_typed() -> None:
    """tail=-495B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-495]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0496_typed() -> None:
    """tail=-496B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-496]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0497_typed() -> None:
    """tail=-497B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-497]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0498_typed() -> None:
    """tail=-498B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-498]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0499_typed() -> None:
    """tail=-499B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-499]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0500_typed() -> None:
    """tail=-500B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-500]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0501_typed() -> None:
    """tail=-501B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-501]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0502_typed() -> None:
    """tail=-502B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-502]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0503_typed() -> None:
    """tail=-503B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-503]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0504_typed() -> None:
    """tail=-504B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-504]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0505_typed() -> None:
    """tail=-505B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-505]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0506_typed() -> None:
    """tail=-506B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-506]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0507_typed() -> None:
    """tail=-507B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-507]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0508_typed() -> None:
    """tail=-508B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-508]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0509_typed() -> None:
    """tail=-509B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-509]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0510_typed() -> None:
    """tail=-510B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-510]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0511_typed() -> None:
    """tail=-511B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-511]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0512_typed() -> None:
    """tail=-512B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-512]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0513_typed() -> None:
    """tail=-513B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-513]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0514_typed() -> None:
    """tail=-514B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-514]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0515_typed() -> None:
    """tail=-515B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-515]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0516_typed() -> None:
    """tail=-516B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-516]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0517_typed() -> None:
    """tail=-517B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-517]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0518_typed() -> None:
    """tail=-518B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-518]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0519_typed() -> None:
    """tail=-519B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-519]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0520_typed() -> None:
    """tail=-520B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-520]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0521_typed() -> None:
    """tail=-521B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-521]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0522_typed() -> None:
    """tail=-522B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-522]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0523_typed() -> None:
    """tail=-523B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-523]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0524_typed() -> None:
    """tail=-524B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-524]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0525_typed() -> None:
    """tail=-525B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-525]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0526_typed() -> None:
    """tail=-526B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-526]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0527_typed() -> None:
    """tail=-527B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-527]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0528_typed() -> None:
    """tail=-528B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-528]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0529_typed() -> None:
    """tail=-529B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-529]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0530_typed() -> None:
    """tail=-530B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-530]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0531_typed() -> None:
    """tail=-531B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-531]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0532_typed() -> None:
    """tail=-532B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-532]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0533_typed() -> None:
    """tail=-533B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-533]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0534_typed() -> None:
    """tail=-534B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-534]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0535_typed() -> None:
    """tail=-535B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-535]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0536_typed() -> None:
    """tail=-536B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-536]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0537_typed() -> None:
    """tail=-537B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-537]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0538_typed() -> None:
    """tail=-538B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-538]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0539_typed() -> None:
    """tail=-539B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-539]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0540_typed() -> None:
    """tail=-540B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-540]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0541_typed() -> None:
    """tail=-541B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-541]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0542_typed() -> None:
    """tail=-542B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-542]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0543_typed() -> None:
    """tail=-543B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-543]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0544_typed() -> None:
    """tail=-544B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-544]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0545_typed() -> None:
    """tail=-545B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-545]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0546_typed() -> None:
    """tail=-546B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-546]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0547_typed() -> None:
    """tail=-547B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-547]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0548_typed() -> None:
    """tail=-548B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-548]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0549_typed() -> None:
    """tail=-549B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-549]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0550_typed() -> None:
    """tail=-550B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-550]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0551_typed() -> None:
    """tail=-551B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-551]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0552_typed() -> None:
    """tail=-552B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-552]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0553_typed() -> None:
    """tail=-553B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-553]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0554_typed() -> None:
    """tail=-554B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-554]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0555_typed() -> None:
    """tail=-555B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-555]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0556_typed() -> None:
    """tail=-556B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-556]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0557_typed() -> None:
    """tail=-557B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-557]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0558_typed() -> None:
    """tail=-558B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-558]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0559_typed() -> None:
    """tail=-559B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-559]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0560_typed() -> None:
    """tail=-560B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-560]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0561_typed() -> None:
    """tail=-561B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-561]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0562_typed() -> None:
    """tail=-562B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-562]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0563_typed() -> None:
    """tail=-563B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-563]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0564_typed() -> None:
    """tail=-564B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-564]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0565_typed() -> None:
    """tail=-565B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-565]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0566_typed() -> None:
    """tail=-566B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-566]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0567_typed() -> None:
    """tail=-567B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-567]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0568_typed() -> None:
    """tail=-568B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-568]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0569_typed() -> None:
    """tail=-569B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-569]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0570_typed() -> None:
    """tail=-570B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-570]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0571_typed() -> None:
    """tail=-571B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-571]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0572_typed() -> None:
    """tail=-572B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-572]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0573_typed() -> None:
    """tail=-573B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-573]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0574_typed() -> None:
    """tail=-574B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-574]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0575_typed() -> None:
    """tail=-575B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-575]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0576_typed() -> None:
    """tail=-576B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-576]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0577_typed() -> None:
    """tail=-577B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-577]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0578_typed() -> None:
    """tail=-578B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-578]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0579_typed() -> None:
    """tail=-579B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-579]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0580_typed() -> None:
    """tail=-580B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-580]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0581_typed() -> None:
    """tail=-581B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-581]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0582_typed() -> None:
    """tail=-582B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-582]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0583_typed() -> None:
    """tail=-583B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-583]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0584_typed() -> None:
    """tail=-584B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-584]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0585_typed() -> None:
    """tail=-585B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-585]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0586_typed() -> None:
    """tail=-586B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-586]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0587_typed() -> None:
    """tail=-587B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-587]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0588_typed() -> None:
    """tail=-588B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-588]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0589_typed() -> None:
    """tail=-589B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-589]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0590_typed() -> None:
    """tail=-590B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-590]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0591_typed() -> None:
    """tail=-591B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-591]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0592_typed() -> None:
    """tail=-592B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-592]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0593_typed() -> None:
    """tail=-593B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-593]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0594_typed() -> None:
    """tail=-594B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-594]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0595_typed() -> None:
    """tail=-595B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-595]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0596_typed() -> None:
    """tail=-596B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-596]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0597_typed() -> None:
    """tail=-597B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-597]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0598_typed() -> None:
    """tail=-598B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-598]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0599_typed() -> None:
    """tail=-599B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-599]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0600_typed() -> None:
    """tail=-600B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-600]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0601_typed() -> None:
    """tail=-601B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-601]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0602_typed() -> None:
    """tail=-602B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-602]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0603_typed() -> None:
    """tail=-603B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-603]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0604_typed() -> None:
    """tail=-604B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-604]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0605_typed() -> None:
    """tail=-605B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-605]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0606_typed() -> None:
    """tail=-606B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-606]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0607_typed() -> None:
    """tail=-607B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-607]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0608_typed() -> None:
    """tail=-608B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-608]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0609_typed() -> None:
    """tail=-609B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-609]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0610_typed() -> None:
    """tail=-610B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-610]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0611_typed() -> None:
    """tail=-611B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-611]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0612_typed() -> None:
    """tail=-612B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-612]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0613_typed() -> None:
    """tail=-613B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-613]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0614_typed() -> None:
    """tail=-614B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-614]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0615_typed() -> None:
    """tail=-615B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-615]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0616_typed() -> None:
    """tail=-616B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-616]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0617_typed() -> None:
    """tail=-617B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-617]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0618_typed() -> None:
    """tail=-618B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-618]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0619_typed() -> None:
    """tail=-619B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-619]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0620_typed() -> None:
    """tail=-620B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-620]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0621_typed() -> None:
    """tail=-621B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-621]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0622_typed() -> None:
    """tail=-622B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-622]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0623_typed() -> None:
    """tail=-623B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-623]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0624_typed() -> None:
    """tail=-624B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-624]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0625_typed() -> None:
    """tail=-625B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-625]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0626_typed() -> None:
    """tail=-626B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-626]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0627_typed() -> None:
    """tail=-627B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-627]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0628_typed() -> None:
    """tail=-628B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-628]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0629_typed() -> None:
    """tail=-629B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-629]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0630_typed() -> None:
    """tail=-630B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-630]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0631_typed() -> None:
    """tail=-631B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-631]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0632_typed() -> None:
    """tail=-632B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-632]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0633_typed() -> None:
    """tail=-633B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-633]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0634_typed() -> None:
    """tail=-634B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-634]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0635_typed() -> None:
    """tail=-635B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-635]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0636_typed() -> None:
    """tail=-636B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-636]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0637_typed() -> None:
    """tail=-637B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-637]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0638_typed() -> None:
    """tail=-638B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-638]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0639_typed() -> None:
    """tail=-639B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-639]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0640_typed() -> None:
    """tail=-640B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-640]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0641_typed() -> None:
    """tail=-641B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-641]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0642_typed() -> None:
    """tail=-642B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-642]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0643_typed() -> None:
    """tail=-643B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-643]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0644_typed() -> None:
    """tail=-644B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-644]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0645_typed() -> None:
    """tail=-645B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-645]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0646_typed() -> None:
    """tail=-646B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-646]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0647_typed() -> None:
    """tail=-647B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-647]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0648_typed() -> None:
    """tail=-648B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-648]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0649_typed() -> None:
    """tail=-649B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-649]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0650_typed() -> None:
    """tail=-650B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-650]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0651_typed() -> None:
    """tail=-651B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-651]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0652_typed() -> None:
    """tail=-652B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-652]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0653_typed() -> None:
    """tail=-653B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-653]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0654_typed() -> None:
    """tail=-654B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-654]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0655_typed() -> None:
    """tail=-655B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-655]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0656_typed() -> None:
    """tail=-656B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-656]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0657_typed() -> None:
    """tail=-657B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-657]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0658_typed() -> None:
    """tail=-658B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-658]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0659_typed() -> None:
    """tail=-659B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-659]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0660_typed() -> None:
    """tail=-660B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-660]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0661_typed() -> None:
    """tail=-661B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-661]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0662_typed() -> None:
    """tail=-662B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-662]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0663_typed() -> None:
    """tail=-663B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-663]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0664_typed() -> None:
    """tail=-664B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-664]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0665_typed() -> None:
    """tail=-665B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-665]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0666_typed() -> None:
    """tail=-666B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-666]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0667_typed() -> None:
    """tail=-667B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-667]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0668_typed() -> None:
    """tail=-668B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-668]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0669_typed() -> None:
    """tail=-669B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-669]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0670_typed() -> None:
    """tail=-670B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-670]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0671_typed() -> None:
    """tail=-671B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-671]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0672_typed() -> None:
    """tail=-672B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-672]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0673_typed() -> None:
    """tail=-673B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-673]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0674_typed() -> None:
    """tail=-674B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-674]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0675_typed() -> None:
    """tail=-675B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-675]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0676_typed() -> None:
    """tail=-676B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-676]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0677_typed() -> None:
    """tail=-677B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-677]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0678_typed() -> None:
    """tail=-678B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-678]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0679_typed() -> None:
    """tail=-679B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-679]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0680_typed() -> None:
    """tail=-680B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-680]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0681_typed() -> None:
    """tail=-681B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-681]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0682_typed() -> None:
    """tail=-682B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-682]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0683_typed() -> None:
    """tail=-683B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-683]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0684_typed() -> None:
    """tail=-684B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-684]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0685_typed() -> None:
    """tail=-685B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-685]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0686_typed() -> None:
    """tail=-686B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-686]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0687_typed() -> None:
    """tail=-687B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-687]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0688_typed() -> None:
    """tail=-688B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-688]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0689_typed() -> None:
    """tail=-689B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-689]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0690_typed() -> None:
    """tail=-690B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-690]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0691_typed() -> None:
    """tail=-691B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-691]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0692_typed() -> None:
    """tail=-692B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-692]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0693_typed() -> None:
    """tail=-693B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-693]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0694_typed() -> None:
    """tail=-694B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-694]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0695_typed() -> None:
    """tail=-695B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-695]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0696_typed() -> None:
    """tail=-696B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-696]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0697_typed() -> None:
    """tail=-697B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-697]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0698_typed() -> None:
    """tail=-698B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-698]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0699_typed() -> None:
    """tail=-699B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-699]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0700_typed() -> None:
    """tail=-700B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-700]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0701_typed() -> None:
    """tail=-701B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-701]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0702_typed() -> None:
    """tail=-702B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-702]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0703_typed() -> None:
    """tail=-703B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-703]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0704_typed() -> None:
    """tail=-704B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-704]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0705_typed() -> None:
    """tail=-705B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-705]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0706_typed() -> None:
    """tail=-706B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-706]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0707_typed() -> None:
    """tail=-707B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-707]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0708_typed() -> None:
    """tail=-708B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-708]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0709_typed() -> None:
    """tail=-709B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-709]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0710_typed() -> None:
    """tail=-710B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-710]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0711_typed() -> None:
    """tail=-711B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-711]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0712_typed() -> None:
    """tail=-712B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-712]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0713_typed() -> None:
    """tail=-713B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-713]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0714_typed() -> None:
    """tail=-714B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-714]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0715_typed() -> None:
    """tail=-715B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-715]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0716_typed() -> None:
    """tail=-716B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-716]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0717_typed() -> None:
    """tail=-717B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-717]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0718_typed() -> None:
    """tail=-718B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-718]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0719_typed() -> None:
    """tail=-719B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-719]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0720_typed() -> None:
    """tail=-720B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-720]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0721_typed() -> None:
    """tail=-721B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-721]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0722_typed() -> None:
    """tail=-722B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-722]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0723_typed() -> None:
    """tail=-723B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-723]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0724_typed() -> None:
    """tail=-724B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-724]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0725_typed() -> None:
    """tail=-725B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-725]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0726_typed() -> None:
    """tail=-726B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-726]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0727_typed() -> None:
    """tail=-727B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-727]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0728_typed() -> None:
    """tail=-728B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-728]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0729_typed() -> None:
    """tail=-729B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-729]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0730_typed() -> None:
    """tail=-730B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-730]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0731_typed() -> None:
    """tail=-731B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-731]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0732_typed() -> None:
    """tail=-732B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-732]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0733_typed() -> None:
    """tail=-733B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-733]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0734_typed() -> None:
    """tail=-734B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-734]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0735_typed() -> None:
    """tail=-735B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-735]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0736_typed() -> None:
    """tail=-736B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-736]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0737_typed() -> None:
    """tail=-737B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-737]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0738_typed() -> None:
    """tail=-738B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-738]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0739_typed() -> None:
    """tail=-739B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-739]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0740_typed() -> None:
    """tail=-740B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-740]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0741_typed() -> None:
    """tail=-741B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-741]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0742_typed() -> None:
    """tail=-742B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-742]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0743_typed() -> None:
    """tail=-743B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-743]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0744_typed() -> None:
    """tail=-744B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-744]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0745_typed() -> None:
    """tail=-745B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-745]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0746_typed() -> None:
    """tail=-746B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-746]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0747_typed() -> None:
    """tail=-747B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-747]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0748_typed() -> None:
    """tail=-748B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-748]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0749_typed() -> None:
    """tail=-749B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-749]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0750_typed() -> None:
    """tail=-750B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-750]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0751_typed() -> None:
    """tail=-751B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-751]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0752_typed() -> None:
    """tail=-752B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-752]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0753_typed() -> None:
    """tail=-753B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-753]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0754_typed() -> None:
    """tail=-754B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-754]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0755_typed() -> None:
    """tail=-755B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-755]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0756_typed() -> None:
    """tail=-756B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-756]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0757_typed() -> None:
    """tail=-757B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-757]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0758_typed() -> None:
    """tail=-758B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-758]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0759_typed() -> None:
    """tail=-759B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-759]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0760_typed() -> None:
    """tail=-760B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-760]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0761_typed() -> None:
    """tail=-761B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-761]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0762_typed() -> None:
    """tail=-762B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-762]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0763_typed() -> None:
    """tail=-763B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-763]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0764_typed() -> None:
    """tail=-764B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-764]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0765_typed() -> None:
    """tail=-765B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-765]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0766_typed() -> None:
    """tail=-766B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-766]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0767_typed() -> None:
    """tail=-767B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-767]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0768_typed() -> None:
    """tail=-768B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-768]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0769_typed() -> None:
    """tail=-769B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-769]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0770_typed() -> None:
    """tail=-770B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-770]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0771_typed() -> None:
    """tail=-771B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-771]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0772_typed() -> None:
    """tail=-772B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-772]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0773_typed() -> None:
    """tail=-773B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-773]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0774_typed() -> None:
    """tail=-774B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-774]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0775_typed() -> None:
    """tail=-775B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-775]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0776_typed() -> None:
    """tail=-776B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-776]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0777_typed() -> None:
    """tail=-777B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-777]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0778_typed() -> None:
    """tail=-778B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-778]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0779_typed() -> None:
    """tail=-779B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-779]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0780_typed() -> None:
    """tail=-780B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-780]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0781_typed() -> None:
    """tail=-781B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-781]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0782_typed() -> None:
    """tail=-782B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-782]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0783_typed() -> None:
    """tail=-783B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-783]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0784_typed() -> None:
    """tail=-784B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-784]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0785_typed() -> None:
    """tail=-785B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-785]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0786_typed() -> None:
    """tail=-786B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-786]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0787_typed() -> None:
    """tail=-787B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-787]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0788_typed() -> None:
    """tail=-788B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-788]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0789_typed() -> None:
    """tail=-789B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-789]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0790_typed() -> None:
    """tail=-790B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-790]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0791_typed() -> None:
    """tail=-791B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-791]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0792_typed() -> None:
    """tail=-792B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-792]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0793_typed() -> None:
    """tail=-793B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-793]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0794_typed() -> None:
    """tail=-794B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-794]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0795_typed() -> None:
    """tail=-795B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-795]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0796_typed() -> None:
    """tail=-796B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-796]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0797_typed() -> None:
    """tail=-797B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-797]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0798_typed() -> None:
    """tail=-798B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-798]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0799_typed() -> None:
    """tail=-799B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-799]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0800_typed() -> None:
    """tail=-800B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-800]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0801_typed() -> None:
    """tail=-801B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-801]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0802_typed() -> None:
    """tail=-802B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-802]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0803_typed() -> None:
    """tail=-803B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-803]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0804_typed() -> None:
    """tail=-804B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-804]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0805_typed() -> None:
    """tail=-805B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-805]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0806_typed() -> None:
    """tail=-806B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-806]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0807_typed() -> None:
    """tail=-807B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-807]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0808_typed() -> None:
    """tail=-808B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-808]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0809_typed() -> None:
    """tail=-809B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-809]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0810_typed() -> None:
    """tail=-810B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-810]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0811_typed() -> None:
    """tail=-811B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-811]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0812_typed() -> None:
    """tail=-812B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-812]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0813_typed() -> None:
    """tail=-813B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-813]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0814_typed() -> None:
    """tail=-814B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-814]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0815_typed() -> None:
    """tail=-815B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-815]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0816_typed() -> None:
    """tail=-816B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-816]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0817_typed() -> None:
    """tail=-817B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-817]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0818_typed() -> None:
    """tail=-818B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-818]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0819_typed() -> None:
    """tail=-819B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-819]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0820_typed() -> None:
    """tail=-820B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-820]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0821_typed() -> None:
    """tail=-821B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-821]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0822_typed() -> None:
    """tail=-822B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-822]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0823_typed() -> None:
    """tail=-823B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-823]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0824_typed() -> None:
    """tail=-824B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-824]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0825_typed() -> None:
    """tail=-825B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-825]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0826_typed() -> None:
    """tail=-826B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-826]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0827_typed() -> None:
    """tail=-827B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-827]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0828_typed() -> None:
    """tail=-828B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-828]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0829_typed() -> None:
    """tail=-829B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-829]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0830_typed() -> None:
    """tail=-830B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-830]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0831_typed() -> None:
    """tail=-831B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-831]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0832_typed() -> None:
    """tail=-832B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-832]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0833_typed() -> None:
    """tail=-833B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-833]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0834_typed() -> None:
    """tail=-834B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-834]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0835_typed() -> None:
    """tail=-835B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-835]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0836_typed() -> None:
    """tail=-836B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-836]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0837_typed() -> None:
    """tail=-837B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-837]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0838_typed() -> None:
    """tail=-838B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-838]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0839_typed() -> None:
    """tail=-839B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-839]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0840_typed() -> None:
    """tail=-840B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-840]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0841_typed() -> None:
    """tail=-841B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-841]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0842_typed() -> None:
    """tail=-842B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-842]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0843_typed() -> None:
    """tail=-843B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-843]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0844_typed() -> None:
    """tail=-844B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-844]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0845_typed() -> None:
    """tail=-845B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-845]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0846_typed() -> None:
    """tail=-846B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-846]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0847_typed() -> None:
    """tail=-847B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-847]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0848_typed() -> None:
    """tail=-848B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-848]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0849_typed() -> None:
    """tail=-849B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-849]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0850_typed() -> None:
    """tail=-850B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-850]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0851_typed() -> None:
    """tail=-851B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-851]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0852_typed() -> None:
    """tail=-852B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-852]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0853_typed() -> None:
    """tail=-853B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-853]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0854_typed() -> None:
    """tail=-854B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-854]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0855_typed() -> None:
    """tail=-855B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-855]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0856_typed() -> None:
    """tail=-856B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-856]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0857_typed() -> None:
    """tail=-857B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-857]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0858_typed() -> None:
    """tail=-858B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-858]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0859_typed() -> None:
    """tail=-859B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-859]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0860_typed() -> None:
    """tail=-860B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-860]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0861_typed() -> None:
    """tail=-861B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-861]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0862_typed() -> None:
    """tail=-862B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-862]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0863_typed() -> None:
    """tail=-863B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-863]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0864_typed() -> None:
    """tail=-864B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-864]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0865_typed() -> None:
    """tail=-865B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-865]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0866_typed() -> None:
    """tail=-866B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-866]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0867_typed() -> None:
    """tail=-867B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-867]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0868_typed() -> None:
    """tail=-868B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-868]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0869_typed() -> None:
    """tail=-869B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-869]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0870_typed() -> None:
    """tail=-870B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-870]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0871_typed() -> None:
    """tail=-871B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-871]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0872_typed() -> None:
    """tail=-872B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-872]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0873_typed() -> None:
    """tail=-873B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-873]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0874_typed() -> None:
    """tail=-874B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-874]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0875_typed() -> None:
    """tail=-875B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-875]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0876_typed() -> None:
    """tail=-876B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-876]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0877_typed() -> None:
    """tail=-877B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-877]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0878_typed() -> None:
    """tail=-878B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-878]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0879_typed() -> None:
    """tail=-879B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-879]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0880_typed() -> None:
    """tail=-880B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-880]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0881_typed() -> None:
    """tail=-881B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-881]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0882_typed() -> None:
    """tail=-882B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-882]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0883_typed() -> None:
    """tail=-883B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-883]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0884_typed() -> None:
    """tail=-884B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-884]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0885_typed() -> None:
    """tail=-885B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-885]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0886_typed() -> None:
    """tail=-886B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-886]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0887_typed() -> None:
    """tail=-887B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-887]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0888_typed() -> None:
    """tail=-888B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-888]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0889_typed() -> None:
    """tail=-889B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-889]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0890_typed() -> None:
    """tail=-890B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-890]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0891_typed() -> None:
    """tail=-891B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-891]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0892_typed() -> None:
    """tail=-892B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-892]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0893_typed() -> None:
    """tail=-893B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-893]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0894_typed() -> None:
    """tail=-894B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-894]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0895_typed() -> None:
    """tail=-895B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-895]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0896_typed() -> None:
    """tail=-896B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-896]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0897_typed() -> None:
    """tail=-897B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-897]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0898_typed() -> None:
    """tail=-898B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-898]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0899_typed() -> None:
    """tail=-899B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-899]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0900_typed() -> None:
    """tail=-900B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-900]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0901_typed() -> None:
    """tail=-901B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-901]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0902_typed() -> None:
    """tail=-902B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-902]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0903_typed() -> None:
    """tail=-903B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-903]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0904_typed() -> None:
    """tail=-904B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-904]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0905_typed() -> None:
    """tail=-905B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-905]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0906_typed() -> None:
    """tail=-906B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-906]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0907_typed() -> None:
    """tail=-907B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-907]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0908_typed() -> None:
    """tail=-908B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-908]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0909_typed() -> None:
    """tail=-909B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-909]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0910_typed() -> None:
    """tail=-910B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-910]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0911_typed() -> None:
    """tail=-911B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-911]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0912_typed() -> None:
    """tail=-912B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-912]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0913_typed() -> None:
    """tail=-913B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-913]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0914_typed() -> None:
    """tail=-914B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-914]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0915_typed() -> None:
    """tail=-915B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-915]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0916_typed() -> None:
    """tail=-916B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-916]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0917_typed() -> None:
    """tail=-917B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-917]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0918_typed() -> None:
    """tail=-918B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-918]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0919_typed() -> None:
    """tail=-919B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-919]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0920_typed() -> None:
    """tail=-920B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-920]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0921_typed() -> None:
    """tail=-921B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-921]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0922_typed() -> None:
    """tail=-922B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-922]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0923_typed() -> None:
    """tail=-923B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-923]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0924_typed() -> None:
    """tail=-924B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-924]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0925_typed() -> None:
    """tail=-925B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-925]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0926_typed() -> None:
    """tail=-926B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-926]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0927_typed() -> None:
    """tail=-927B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-927]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0928_typed() -> None:
    """tail=-928B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-928]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0929_typed() -> None:
    """tail=-929B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-929]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0930_typed() -> None:
    """tail=-930B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-930]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0931_typed() -> None:
    """tail=-931B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-931]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0932_typed() -> None:
    """tail=-932B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-932]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0933_typed() -> None:
    """tail=-933B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-933]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0934_typed() -> None:
    """tail=-934B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-934]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0935_typed() -> None:
    """tail=-935B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-935]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0936_typed() -> None:
    """tail=-936B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-936]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0937_typed() -> None:
    """tail=-937B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-937]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0938_typed() -> None:
    """tail=-938B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-938]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0939_typed() -> None:
    """tail=-939B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-939]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0940_typed() -> None:
    """tail=-940B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-940]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0941_typed() -> None:
    """tail=-941B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-941]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0942_typed() -> None:
    """tail=-942B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-942]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0943_typed() -> None:
    """tail=-943B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-943]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0944_typed() -> None:
    """tail=-944B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-944]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0945_typed() -> None:
    """tail=-945B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-945]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0946_typed() -> None:
    """tail=-946B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-946]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0947_typed() -> None:
    """tail=-947B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-947]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0948_typed() -> None:
    """tail=-948B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-948]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0949_typed() -> None:
    """tail=-949B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-949]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0950_typed() -> None:
    """tail=-950B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-950]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0951_typed() -> None:
    """tail=-951B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-951]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0952_typed() -> None:
    """tail=-952B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-952]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0953_typed() -> None:
    """tail=-953B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-953]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0954_typed() -> None:
    """tail=-954B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-954]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0955_typed() -> None:
    """tail=-955B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-955]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0956_typed() -> None:
    """tail=-956B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-956]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0957_typed() -> None:
    """tail=-957B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-957]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0958_typed() -> None:
    """tail=-958B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-958]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0959_typed() -> None:
    """tail=-959B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-959]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0960_typed() -> None:
    """tail=-960B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-960]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0961_typed() -> None:
    """tail=-961B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-961]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0962_typed() -> None:
    """tail=-962B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-962]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0963_typed() -> None:
    """tail=-963B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-963]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0964_typed() -> None:
    """tail=-964B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-964]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0965_typed() -> None:
    """tail=-965B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-965]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0966_typed() -> None:
    """tail=-966B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-966]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0967_typed() -> None:
    """tail=-967B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-967]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0968_typed() -> None:
    """tail=-968B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-968]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0969_typed() -> None:
    """tail=-969B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-969]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0970_typed() -> None:
    """tail=-970B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-970]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0971_typed() -> None:
    """tail=-971B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-971]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0972_typed() -> None:
    """tail=-972B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-972]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0973_typed() -> None:
    """tail=-973B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-973]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0974_typed() -> None:
    """tail=-974B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-974]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0975_typed() -> None:
    """tail=-975B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-975]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0976_typed() -> None:
    """tail=-976B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-976]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0977_typed() -> None:
    """tail=-977B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-977]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0978_typed() -> None:
    """tail=-978B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-978]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0979_typed() -> None:
    """tail=-979B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-979]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0980_typed() -> None:
    """tail=-980B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-980]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0981_typed() -> None:
    """tail=-981B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-981]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0982_typed() -> None:
    """tail=-982B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-982]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0983_typed() -> None:
    """tail=-983B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-983]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0984_typed() -> None:
    """tail=-984B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-984]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0985_typed() -> None:
    """tail=-985B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-985]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0986_typed() -> None:
    """tail=-986B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-986]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0987_typed() -> None:
    """tail=-987B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-987]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0988_typed() -> None:
    """tail=-988B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-988]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0989_typed() -> None:
    """tail=-989B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-989]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0990_typed() -> None:
    """tail=-990B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-990]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0991_typed() -> None:
    """tail=-991B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-991]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0992_typed() -> None:
    """tail=-992B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-992]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0993_typed() -> None:
    """tail=-993B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-993]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0994_typed() -> None:
    """tail=-994B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-994]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0995_typed() -> None:
    """tail=-995B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-995]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0996_typed() -> None:
    """tail=-996B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-996]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0997_typed() -> None:
    """tail=-997B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-997]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0998_typed() -> None:
    """tail=-998B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-998]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc0999_typed() -> None:
    """tail=-999B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-999]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1000_typed() -> None:
    """tail=-1000B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1000]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1001_typed() -> None:
    """tail=-1001B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1001]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1002_typed() -> None:
    """tail=-1002B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1002]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1003_typed() -> None:
    """tail=-1003B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1003]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1004_typed() -> None:
    """tail=-1004B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1004]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1005_typed() -> None:
    """tail=-1005B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1005]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1006_typed() -> None:
    """tail=-1006B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1006]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1007_typed() -> None:
    """tail=-1007B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1007]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1008_typed() -> None:
    """tail=-1008B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1008]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1009_typed() -> None:
    """tail=-1009B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1009]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1010_typed() -> None:
    """tail=-1010B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1010]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1011_typed() -> None:
    """tail=-1011B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1011]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1012_typed() -> None:
    """tail=-1012B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1012]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1013_typed() -> None:
    """tail=-1013B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1013]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1014_typed() -> None:
    """tail=-1014B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1014]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1015_typed() -> None:
    """tail=-1015B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1015]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1016_typed() -> None:
    """tail=-1016B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1016]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1017_typed() -> None:
    """tail=-1017B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1017]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1018_typed() -> None:
    """tail=-1018B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1018]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1019_typed() -> None:
    """tail=-1019B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1019]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1020_typed() -> None:
    """tail=-1020B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1020]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1021_typed() -> None:
    """tail=-1021B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1021]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1022_typed() -> None:
    """tail=-1022B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1022]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1023_typed() -> None:
    """tail=-1023B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1023]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1024_typed() -> None:
    """tail=-1024B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1024]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1025_typed() -> None:
    """tail=-1025B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1025]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1026_typed() -> None:
    """tail=-1026B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1026]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1027_typed() -> None:
    """tail=-1027B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1027]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1028_typed() -> None:
    """tail=-1028B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1028]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1029_typed() -> None:
    """tail=-1029B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1029]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1030_typed() -> None:
    """tail=-1030B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1030]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1031_typed() -> None:
    """tail=-1031B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1031]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1032_typed() -> None:
    """tail=-1032B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1032]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1033_typed() -> None:
    """tail=-1033B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1033]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1034_typed() -> None:
    """tail=-1034B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1034]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1035_typed() -> None:
    """tail=-1035B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1035]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1036_typed() -> None:
    """tail=-1036B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1036]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1037_typed() -> None:
    """tail=-1037B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1037]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1038_typed() -> None:
    """tail=-1038B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1038]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1039_typed() -> None:
    """tail=-1039B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1039]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1040_typed() -> None:
    """tail=-1040B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1040]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1041_typed() -> None:
    """tail=-1041B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1041]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1042_typed() -> None:
    """tail=-1042B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1042]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1043_typed() -> None:
    """tail=-1043B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1043]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1044_typed() -> None:
    """tail=-1044B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1044]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1045_typed() -> None:
    """tail=-1045B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1045]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1046_typed() -> None:
    """tail=-1046B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1046]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1047_typed() -> None:
    """tail=-1047B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1047]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1048_typed() -> None:
    """tail=-1048B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1048]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1049_typed() -> None:
    """tail=-1049B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1049]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1050_typed() -> None:
    """tail=-1050B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1050]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1051_typed() -> None:
    """tail=-1051B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1051]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1052_typed() -> None:
    """tail=-1052B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1052]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1053_typed() -> None:
    """tail=-1053B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1053]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1054_typed() -> None:
    """tail=-1054B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1054]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1055_typed() -> None:
    """tail=-1055B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1055]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1056_typed() -> None:
    """tail=-1056B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1056]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1057_typed() -> None:
    """tail=-1057B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1057]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1058_typed() -> None:
    """tail=-1058B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1058]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1059_typed() -> None:
    """tail=-1059B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1059]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1060_typed() -> None:
    """tail=-1060B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1060]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1061_typed() -> None:
    """tail=-1061B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1061]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1062_typed() -> None:
    """tail=-1062B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1062]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1063_typed() -> None:
    """tail=-1063B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1063]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1064_typed() -> None:
    """tail=-1064B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1064]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1065_typed() -> None:
    """tail=-1065B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1065]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1066_typed() -> None:
    """tail=-1066B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1066]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1067_typed() -> None:
    """tail=-1067B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1067]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1068_typed() -> None:
    """tail=-1068B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1068]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1069_typed() -> None:
    """tail=-1069B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1069]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1070_typed() -> None:
    """tail=-1070B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1070]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1071_typed() -> None:
    """tail=-1071B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1071]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1072_typed() -> None:
    """tail=-1072B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1072]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1073_typed() -> None:
    """tail=-1073B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1073]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1074_typed() -> None:
    """tail=-1074B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1074]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1075_typed() -> None:
    """tail=-1075B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1075]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1076_typed() -> None:
    """tail=-1076B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1076]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1077_typed() -> None:
    """tail=-1077B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1077]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1078_typed() -> None:
    """tail=-1078B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1078]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1079_typed() -> None:
    """tail=-1079B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1079]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1080_typed() -> None:
    """tail=-1080B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1080]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1081_typed() -> None:
    """tail=-1081B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1081]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1082_typed() -> None:
    """tail=-1082B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1082]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1083_typed() -> None:
    """tail=-1083B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1083]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1084_typed() -> None:
    """tail=-1084B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1084]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1085_typed() -> None:
    """tail=-1085B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1085]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1086_typed() -> None:
    """tail=-1086B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1086]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1087_typed() -> None:
    """tail=-1087B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1087]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1088_typed() -> None:
    """tail=-1088B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1088]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1089_typed() -> None:
    """tail=-1089B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1089]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1090_typed() -> None:
    """tail=-1090B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1090]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1091_typed() -> None:
    """tail=-1091B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1091]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1092_typed() -> None:
    """tail=-1092B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1092]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1093_typed() -> None:
    """tail=-1093B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1093]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1094_typed() -> None:
    """tail=-1094B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1094]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1095_typed() -> None:
    """tail=-1095B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1095]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1096_typed() -> None:
    """tail=-1096B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1096]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1097_typed() -> None:
    """tail=-1097B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1097]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1098_typed() -> None:
    """tail=-1098B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1098]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1099_typed() -> None:
    """tail=-1099B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1099]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1100_typed() -> None:
    """tail=-1100B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1100]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1101_typed() -> None:
    """tail=-1101B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1101]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1102_typed() -> None:
    """tail=-1102B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1102]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1103_typed() -> None:
    """tail=-1103B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1103]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1104_typed() -> None:
    """tail=-1104B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1104]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1105_typed() -> None:
    """tail=-1105B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1105]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1106_typed() -> None:
    """tail=-1106B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1106]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1107_typed() -> None:
    """tail=-1107B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1107]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1108_typed() -> None:
    """tail=-1108B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1108]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1109_typed() -> None:
    """tail=-1109B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1109]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1110_typed() -> None:
    """tail=-1110B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1110]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1111_typed() -> None:
    """tail=-1111B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1111]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1112_typed() -> None:
    """tail=-1112B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1112]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1113_typed() -> None:
    """tail=-1113B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1113]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1114_typed() -> None:
    """tail=-1114B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1114]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1115_typed() -> None:
    """tail=-1115B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1115]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1116_typed() -> None:
    """tail=-1116B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1116]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1117_typed() -> None:
    """tail=-1117B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1117]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1118_typed() -> None:
    """tail=-1118B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1118]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1119_typed() -> None:
    """tail=-1119B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1119]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1120_typed() -> None:
    """tail=-1120B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1120]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1121_typed() -> None:
    """tail=-1121B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1121]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1122_typed() -> None:
    """tail=-1122B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1122]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1123_typed() -> None:
    """tail=-1123B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1123]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1124_typed() -> None:
    """tail=-1124B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1124]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1125_typed() -> None:
    """tail=-1125B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1125]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1126_typed() -> None:
    """tail=-1126B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1126]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1127_typed() -> None:
    """tail=-1127B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1127]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1128_typed() -> None:
    """tail=-1128B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1128]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1129_typed() -> None:
    """tail=-1129B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1129]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1130_typed() -> None:
    """tail=-1130B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1130]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1131_typed() -> None:
    """tail=-1131B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1131]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1132_typed() -> None:
    """tail=-1132B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1132]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1133_typed() -> None:
    """tail=-1133B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1133]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1134_typed() -> None:
    """tail=-1134B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1134]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1135_typed() -> None:
    """tail=-1135B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1135]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1136_typed() -> None:
    """tail=-1136B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1136]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1137_typed() -> None:
    """tail=-1137B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1137]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1138_typed() -> None:
    """tail=-1138B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1138]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1139_typed() -> None:
    """tail=-1139B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1139]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1140_typed() -> None:
    """tail=-1140B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1140]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1141_typed() -> None:
    """tail=-1141B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1141]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1142_typed() -> None:
    """tail=-1142B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1142]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1143_typed() -> None:
    """tail=-1143B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1143]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1144_typed() -> None:
    """tail=-1144B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1144]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1145_typed() -> None:
    """tail=-1145B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1145]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1146_typed() -> None:
    """tail=-1146B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1146]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1147_typed() -> None:
    """tail=-1147B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1147]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1148_typed() -> None:
    """tail=-1148B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1148]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1149_typed() -> None:
    """tail=-1149B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1149]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1150_typed() -> None:
    """tail=-1150B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1150]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1151_typed() -> None:
    """tail=-1151B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1151]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1152_typed() -> None:
    """tail=-1152B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1152]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1153_typed() -> None:
    """tail=-1153B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1153]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1154_typed() -> None:
    """tail=-1154B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1154]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1155_typed() -> None:
    """tail=-1155B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1155]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1156_typed() -> None:
    """tail=-1156B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1156]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1157_typed() -> None:
    """tail=-1157B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1157]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1158_typed() -> None:
    """tail=-1158B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1158]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1159_typed() -> None:
    """tail=-1159B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1159]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1160_typed() -> None:
    """tail=-1160B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1160]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1161_typed() -> None:
    """tail=-1161B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1161]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1162_typed() -> None:
    """tail=-1162B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1162]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1163_typed() -> None:
    """tail=-1163B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1163]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1164_typed() -> None:
    """tail=-1164B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1164]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1165_typed() -> None:
    """tail=-1165B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1165]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1166_typed() -> None:
    """tail=-1166B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1166]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1167_typed() -> None:
    """tail=-1167B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1167]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1168_typed() -> None:
    """tail=-1168B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1168]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1169_typed() -> None:
    """tail=-1169B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1169]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1170_typed() -> None:
    """tail=-1170B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1170]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1171_typed() -> None:
    """tail=-1171B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1171]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1172_typed() -> None:
    """tail=-1172B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1172]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1173_typed() -> None:
    """tail=-1173B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1173]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1174_typed() -> None:
    """tail=-1174B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1174]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1175_typed() -> None:
    """tail=-1175B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1175]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1176_typed() -> None:
    """tail=-1176B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1176]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1177_typed() -> None:
    """tail=-1177B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1177]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1178_typed() -> None:
    """tail=-1178B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1178]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1179_typed() -> None:
    """tail=-1179B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1179]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1180_typed() -> None:
    """tail=-1180B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1180]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1181_typed() -> None:
    """tail=-1181B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1181]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1182_typed() -> None:
    """tail=-1182B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1182]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1183_typed() -> None:
    """tail=-1183B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1183]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1184_typed() -> None:
    """tail=-1184B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1184]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1185_typed() -> None:
    """tail=-1185B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1185]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1186_typed() -> None:
    """tail=-1186B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1186]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1187_typed() -> None:
    """tail=-1187B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1187]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1188_typed() -> None:
    """tail=-1188B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1188]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1189_typed() -> None:
    """tail=-1189B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1189]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1190_typed() -> None:
    """tail=-1190B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1190]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1191_typed() -> None:
    """tail=-1191B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1191]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1192_typed() -> None:
    """tail=-1192B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1192]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1193_typed() -> None:
    """tail=-1193B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1193]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1194_typed() -> None:
    """tail=-1194B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1194]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1195_typed() -> None:
    """tail=-1195B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1195]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1196_typed() -> None:
    """tail=-1196B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1196]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1197_typed() -> None:
    """tail=-1197B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1197]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1198_typed() -> None:
    """tail=-1198B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1198]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1199_typed() -> None:
    """tail=-1199B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1199]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'


def test_trunc_trunc1200_typed() -> None:
    """tail=-1200B re-sealed: typed deterministic refusal."""
    with pytest.raises(StagedAudioInvalid) as caught:
        read_context(_riff(longbase[:-1200]))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated intake WAV chunk'
