"""decode_units end-to-end grid: bundles, ceilings, joins, splits and hostile frames.

``decode_units`` is the CPU coordinator's strict WAL admission decoder: it
counts every uploaded frame, decodes via the shared sync decoder, packs
capture-clock units and refuses anything the bundle contract cannot
guarantee. This grid pins the end-to-end outcome for:

- happy bundles across the declared PCM codec tokens (rate/width variants),
- every hostile unit ceiling (non-finite, non-positive, over the 2 h
  horizon) and the boundary-valid ceilings,
- corrupt frames at each bundle position (typed frame faults and the
  bundle-preservation fault),
- join-gap boundaries at the 30 s seam and unit splits under a clipped
  ceiling.

Every expectation is a verified literal; every fault is the typed
``StagedAudioInvalid`` family type.

Failure-Class: FC-sync-decode-fault-anonymous-at-typed-boundaries
"""

import pathlib
import struct
import tempfile

import pytest

from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.capture_decode import decode_units


def _bundle(root: pathlib.Path, files) -> list:
    root.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, (stamp, data, rate, width) in enumerate(files):
        path = root / f'batch{index}_pcm{width * 8}_{rate}_{stamp}.bin'
        path.write_bytes(data)
        paths.append(str(path))
    return paths


@pytest.fixture(scope='module')
def grid_root(tmp_path_factory):
    return tmp_path_factory.mktemp('sync_units_grid')


def test_units_happy_r16000_w2_f1_n1(grid_root) -> None:
    """happy_r16000_w2_f1_n1: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell0",
        [(1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2)],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [0.002]


def test_units_happy_r16000_w2_f1_n2(grid_root) -> None:
    """happy_r16000_w2_f1_n2: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell1",
        [
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
            (1700000010, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [10.002]


def test_units_happy_r16000_w2_f2_n1(grid_root) -> None:
    """happy_r16000_w2_f2_n1: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell2",
        [
            (
                1700000000,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                16000,
                2,
            )
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [0.004]


def test_units_happy_r16000_w2_f2_n2(grid_root) -> None:
    """happy_r16000_w2_f2_n2: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell3",
        [
            (
                1700000000,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                16000,
                2,
            ),
            (
                1700000010,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                16000,
                2,
            ),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [10.004]


def test_units_happy_r16000_w2_f3_n1(grid_root) -> None:
    """happy_r16000_w2_f3_n1: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell4",
        [
            (
                1700000000,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                16000,
                2,
            )
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [0.006]


def test_units_happy_r16000_w2_f3_n2(grid_root) -> None:
    """happy_r16000_w2_f3_n2: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell5",
        [
            (
                1700000000,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                16000,
                2,
            ),
            (
                1700000010,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                16000,
                2,
            ),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [10.006]


def test_units_happy_r8000_w2_f1_n1(grid_root) -> None:
    """happy_r8000_w2_f1_n1: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell6",
        [(1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 8000, 2)],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [0.0039375]


def test_units_happy_r8000_w2_f1_n2(grid_root) -> None:
    """happy_r8000_w2_f1_n2: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell7",
        [
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 8000, 2),
            (1700000010, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 8000, 2),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [10.0039375]


def test_units_happy_r8000_w2_f2_n1(grid_root) -> None:
    """happy_r8000_w2_f2_n1: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell8",
        [
            (
                1700000000,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                8000,
                2,
            )
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [0.0079375]


def test_units_happy_r8000_w2_f2_n2(grid_root) -> None:
    """happy_r8000_w2_f2_n2: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell9",
        [
            (
                1700000000,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                8000,
                2,
            ),
            (
                1700000010,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                8000,
                2,
            ),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [10.0079375]


def test_units_happy_r8000_w2_f3_n1(grid_root) -> None:
    """happy_r8000_w2_f3_n1: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell10",
        [
            (
                1700000000,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                8000,
                2,
            )
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [0.0119375]


def test_units_happy_r8000_w2_f3_n2(grid_root) -> None:
    """happy_r8000_w2_f3_n2: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell11",
        [
            (
                1700000000,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                8000,
                2,
            ),
            (
                1700000010,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                8000,
                2,
            ),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [10.0119375]


def test_units_happy_r44100_w2_f1_n1(grid_root) -> None:
    """happy_r44100_w2_f1_n1: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell12",
        [(1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 44100, 2)],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [0.00075]


def test_units_happy_r44100_w2_f1_n2(grid_root) -> None:
    """happy_r44100_w2_f1_n2: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell13",
        [
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 44100, 2),
            (1700000010, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 44100, 2),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [10.00075]


def test_units_happy_r44100_w2_f2_n1(grid_root) -> None:
    """happy_r44100_w2_f2_n1: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell14",
        [
            (
                1700000000,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                44100,
                2,
            )
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [0.0014375]


def test_units_happy_r44100_w2_f2_n2(grid_root) -> None:
    """happy_r44100_w2_f2_n2: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell15",
        [
            (
                1700000000,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                44100,
                2,
            ),
            (
                1700000010,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                44100,
                2,
            ),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [10.0014375]


def test_units_happy_r44100_w2_f3_n1(grid_root) -> None:
    """happy_r44100_w2_f3_n1: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell16",
        [
            (
                1700000000,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                44100,
                2,
            )
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [0.0021875]


def test_units_happy_r44100_w2_f3_n2(grid_root) -> None:
    """happy_r44100_w2_f3_n2: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell17",
        [
            (
                1700000000,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                44100,
                2,
            ),
            (
                1700000010,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                44100,
                2,
            ),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [10.0021875]


def test_units_happy_r48000_w2_f1_n1(grid_root) -> None:
    """happy_r48000_w2_f1_n1: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell18",
        [(1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 48000, 2)],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [0.0006875]


def test_units_happy_r48000_w2_f1_n2(grid_root) -> None:
    """happy_r48000_w2_f1_n2: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell19",
        [
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 48000, 2),
            (1700000010, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 48000, 2),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [10.0006875]


def test_units_happy_r48000_w2_f2_n1(grid_root) -> None:
    """happy_r48000_w2_f2_n1: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell20",
        [
            (
                1700000000,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                48000,
                2,
            )
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [0.001375]


def test_units_happy_r48000_w2_f2_n2(grid_root) -> None:
    """happy_r48000_w2_f2_n2: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell21",
        [
            (
                1700000000,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                48000,
                2,
            ),
            (
                1700000010,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                48000,
                2,
            ),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [10.001375]


def test_units_happy_r48000_w2_f3_n1(grid_root) -> None:
    """happy_r48000_w2_f3_n1: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell22",
        [
            (
                1700000000,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                48000,
                2,
            )
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [0.002]


def test_units_happy_r48000_w2_f3_n2(grid_root) -> None:
    """happy_r48000_w2_f3_n2: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell23",
        [
            (
                1700000000,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                48000,
                2,
            ),
            (
                1700000010,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                48000,
                2,
            ),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [10.002]


def test_units_happy_r8000_w1_f1_n1(grid_root) -> None:
    """happy_r8000_w1_f1_n1: 1 unit(s), frozen captures and durations."""
    paths = _bundle(grid_root / "cell24", [(1700000000, b' \x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 8000, 1)])
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [0.0039375]


def test_units_happy_r8000_w1_f1_n2(grid_root) -> None:
    """happy_r8000_w1_f1_n2: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell25",
        [
            (1700000000, b' \x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 8000, 1),
            (1700000010, b' \x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 8000, 1),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [10.0039375]


def test_units_happy_r8000_w1_f2_n1(grid_root) -> None:
    """happy_r8000_w1_f2_n1: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell26",
        [
            (
                1700000000,
                b' \x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ \x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                8000,
                1,
            )
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [0.0079375]


def test_units_happy_r8000_w1_f2_n2(grid_root) -> None:
    """happy_r8000_w1_f2_n2: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell27",
        [
            (
                1700000000,
                b' \x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ \x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                8000,
                1,
            ),
            (
                1700000010,
                b' \x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ \x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                8000,
                1,
            ),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [10.0079375]


def test_units_happy_r8000_w1_f3_n1(grid_root) -> None:
    """happy_r8000_w1_f3_n1: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell28",
        [
            (
                1700000000,
                b' \x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ \x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ \x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                8000,
                1,
            )
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [0.0119375]


def test_units_happy_r8000_w1_f3_n2(grid_root) -> None:
    """happy_r8000_w1_f3_n2: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell29",
        [
            (
                1700000000,
                b' \x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ \x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ \x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                8000,
                1,
            ),
            (
                1700000010,
                b' \x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ \x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ \x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                8000,
                1,
            ),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [10.0119375]


def test_units_ceiling_inf(grid_root) -> None:
    """ceiling_-inf: typed deterministic refusal."""
    paths = _bundle(
        grid_root / "cell30",
        [(1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2)],
    )
    with pytest.raises(StagedAudioInvalid) as caught:
        list(decode_units(paths, max_seconds=float("-inf")))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid dedicated capture-unit ceiling'
    assert isinstance(caught.value, ValueError)


def test_units_ceiling_1_0(grid_root) -> None:
    """ceiling_-1.0: typed deterministic refusal."""
    paths = _bundle(
        grid_root / "cell31",
        [(1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2)],
    )
    with pytest.raises(StagedAudioInvalid) as caught:
        list(decode_units(paths, max_seconds=-1.0))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid dedicated capture-unit ceiling'
    assert isinstance(caught.value, ValueError)


def test_units_ceiling_0_0(grid_root) -> None:
    """ceiling_0.0: typed deterministic refusal."""
    paths = _bundle(
        grid_root / "cell32",
        [(1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2)],
    )
    with pytest.raises(StagedAudioInvalid) as caught:
        list(decode_units(paths, max_seconds=0.0))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid dedicated capture-unit ceiling'
    assert isinstance(caught.value, ValueError)


def test_units_ceiling_nan(grid_root) -> None:
    """ceiling_nan: typed deterministic refusal."""
    paths = _bundle(
        grid_root / "cell33",
        [(1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2)],
    )
    with pytest.raises(StagedAudioInvalid) as caught:
        list(decode_units(paths, max_seconds=float("nan")))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid dedicated capture-unit ceiling'
    assert isinstance(caught.value, ValueError)


def test_units_ceiling_inf(grid_root) -> None:
    """ceiling_inf: typed deterministic refusal."""
    paths = _bundle(
        grid_root / "cell34",
        [(1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2)],
    )
    with pytest.raises(StagedAudioInvalid) as caught:
        list(decode_units(paths, max_seconds=float("inf")))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid dedicated capture-unit ceiling'
    assert isinstance(caught.value, ValueError)


def test_units_ceiling_7201_0(grid_root) -> None:
    """ceiling_7201.0: typed deterministic refusal."""
    paths = _bundle(
        grid_root / "cell35",
        [(1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2)],
    )
    with pytest.raises(StagedAudioInvalid) as caught:
        list(decode_units(paths, max_seconds=7201.0))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid dedicated capture-unit ceiling'
    assert isinstance(caught.value, ValueError)


def test_units_ceilingok_0_001(grid_root) -> None:
    """ceilingok_0.001: 4 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell36",
        [
            (
                1700000000,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                16000,
                2,
            )
        ],
    )
    units = list(decode_units(paths, max_seconds=0.001))
    assert len(units) == 4
    assert [u.capture_at for u in units] == [1700000000.0, 1700000000.001, 1700000000.002, 1700000000.003]
    assert [u.duration_seconds for u in units] == [0.001, 0.001, 0.001, 0.001]


def test_units_ceilingok_0_004(grid_root) -> None:
    """ceilingok_0.004: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell37",
        [
            (
                1700000000,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                16000,
                2,
            )
        ],
    )
    units = list(decode_units(paths, max_seconds=0.004))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [0.004]


def test_units_ceilingok_7200(grid_root) -> None:
    """ceilingok_7200: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell38",
        [
            (
                1700000000,
                b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                16000,
                2,
            )
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [0.004]


def test_units_corrupt_zero_at0(grid_root) -> None:
    """corrupt_zero_at0: typed deterministic refusal."""
    paths = _bundle(
        grid_root / "cell39",
        [
            (1700000000, b'\x00\x00\x00\x00\x01\x01\x01\x01\x01\x01\x01\x01', 16000, 2),
            (1700000010, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
        ],
    )
    with pytest.raises(StagedAudioInvalid) as caught:
        list(decode_units(paths, max_seconds=7200))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid sync audio frame'
    assert isinstance(caught.value, ValueError)


def test_units_corrupt_zero_at1(grid_root) -> None:
    """corrupt_zero_at1: typed deterministic refusal."""
    paths = _bundle(
        grid_root / "cell40",
        [
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
            (1700000010, b'\x00\x00\x00\x00\x01\x01\x01\x01\x01\x01\x01\x01', 16000, 2),
        ],
    )
    with pytest.raises(StagedAudioInvalid) as caught:
        list(decode_units(paths, max_seconds=7200))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid sync audio frame'
    assert isinstance(caught.value, ValueError)


def test_units_corrupt_oversize_at0(grid_root) -> None:
    """corrupt_oversize_at0: typed deterministic refusal."""
    paths = _bundle(
        grid_root / "cell41",
        [
            (1700000000, b'\x01\x00\x01\x00\x01\x01\x01\x01\x01\x01\x01\x01', 16000, 2),
            (1700000010, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
        ],
    )
    with pytest.raises(StagedAudioInvalid) as caught:
        list(decode_units(paths, max_seconds=7200))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid sync audio frame'
    assert isinstance(caught.value, ValueError)


def test_units_corrupt_oversize_at1(grid_root) -> None:
    """corrupt_oversize_at1: typed deterministic refusal."""
    paths = _bundle(
        grid_root / "cell42",
        [
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
            (1700000010, b'\x01\x00\x01\x00\x01\x01\x01\x01\x01\x01\x01\x01', 16000, 2),
        ],
    )
    with pytest.raises(StagedAudioInvalid) as caught:
        list(decode_units(paths, max_seconds=7200))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid sync audio frame'
    assert isinstance(caught.value, ValueError)


def test_units_corrupt_short_at0(grid_root) -> None:
    """corrupt_short_at0: typed deterministic refusal."""
    paths = _bundle(
        grid_root / "cell43",
        [
            (1700000000, b'@\x00\x00\x00\x01\x01\x01\x01\x01\x01\x01\x01', 16000, 2),
            (1700000010, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
        ],
    )
    with pytest.raises(StagedAudioInvalid) as caught:
        list(decode_units(paths, max_seconds=7200))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid sync audio frame'
    assert isinstance(caught.value, ValueError)


def test_units_corrupt_short_at1(grid_root) -> None:
    """corrupt_short_at1: typed deterministic refusal."""
    paths = _bundle(
        grid_root / "cell44",
        [
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
            (1700000010, b'@\x00\x00\x00\x01\x01\x01\x01\x01\x01\x01\x01', 16000, 2),
        ],
    )
    with pytest.raises(StagedAudioInvalid) as caught:
        list(decode_units(paths, max_seconds=7200))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'invalid sync audio frame'
    assert isinstance(caught.value, ValueError)


def test_units_corrupt_header2_at0(grid_root) -> None:
    """corrupt_header2_at0: typed deterministic refusal."""
    paths = _bundle(
        grid_root / "cell45",
        [
            (1700000000, b'\x01\x02', 16000, 2),
            (1700000010, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
        ],
    )
    with pytest.raises(StagedAudioInvalid) as caught:
        list(decode_units(paths, max_seconds=7200))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated sync audio frame'
    assert isinstance(caught.value, ValueError)


def test_units_corrupt_header2_at1(grid_root) -> None:
    """corrupt_header2_at1: typed deterministic refusal."""
    paths = _bundle(
        grid_root / "cell46",
        [
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
            (1700000010, b'\x01\x02', 16000, 2),
        ],
    )
    with pytest.raises(StagedAudioInvalid) as caught:
        list(decode_units(paths, max_seconds=7200))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'truncated sync audio frame'
    assert isinstance(caught.value, ValueError)


def test_units_corrupt_empty_at0(grid_root) -> None:
    """corrupt_empty_at0: typed deterministic refusal."""
    paths = _bundle(
        grid_root / "cell47",
        [
            (1700000000, b'', 16000, 2),
            (1700000010, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
        ],
    )
    with pytest.raises(StagedAudioInvalid) as caught:
        list(decode_units(paths, max_seconds=7200))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'empty sync audio'
    assert isinstance(caught.value, ValueError)


def test_units_corrupt_empty_at1(grid_root) -> None:
    """corrupt_empty_at1: typed deterministic refusal."""
    paths = _bundle(
        grid_root / "cell48",
        [
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
            (1700000010, b'', 16000, 2),
        ],
    )
    with pytest.raises(StagedAudioInvalid) as caught:
        list(decode_units(paths, max_seconds=7200))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'empty sync audio'
    assert isinstance(caught.value, ValueError)


def test_units_corrupt_odd_at0(grid_root) -> None:
    """corrupt_odd_at0: typed deterministic refusal."""
    paths = _bundle(
        grid_root / "cell49",
        [
            (1700000000, b'\x03\x00\x00\x00\x01\x02\x03', 16000, 2),
            (1700000010, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
        ],
    )
    with pytest.raises(StagedAudioInvalid) as caught:
        list(decode_units(paths, max_seconds=7200))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'sync decode did not preserve every uploaded frame'
    assert isinstance(caught.value, ValueError)


def test_units_corrupt_odd_at1(grid_root) -> None:
    """corrupt_odd_at1: typed deterministic refusal."""
    paths = _bundle(
        grid_root / "cell50",
        [
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
            (1700000010, b'\x03\x00\x00\x00\x01\x02\x03', 16000, 2),
        ],
    )
    with pytest.raises(StagedAudioInvalid) as caught:
        list(decode_units(paths, max_seconds=7200))
    assert type(caught.value) is StagedAudioInvalid
    assert str(caught.value) == 'sync decode did not preserve every uploaded frame'
    assert isinstance(caught.value, ValueError)


def test_units_gap_0(grid_root) -> None:
    """gap_0: 2 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell51",
        [
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 2
    assert [u.capture_at for u in units] == [1700000000.0, 1700000000.0]
    assert [u.duration_seconds for u in units] == [0.002, 0.002]


def test_units_gap_1(grid_root) -> None:
    """gap_1: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell52",
        [
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
            (1700000001, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [1.002]


def test_units_gap_2(grid_root) -> None:
    """gap_2: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell53",
        [
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
            (1700000002, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [2.002]


def test_units_gap_15(grid_root) -> None:
    """gap_15: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell54",
        [
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
            (1700000015, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [15.002]


def test_units_gap_29(grid_root) -> None:
    """gap_29: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell55",
        [
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
            (1700000029, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [29.002]


def test_units_gap_30(grid_root) -> None:
    """gap_30: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell56",
        [
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
            (1700000030, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [30.002]


def test_units_gap_31(grid_root) -> None:
    """gap_31: 2 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell57",
        [
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
            (1700000031, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 2
    assert [u.capture_at for u in units] == [1700000000.0, 1700000031.0]
    assert [u.duration_seconds for u in units] == [0.002, 0.002]


def test_units_gap_61(grid_root) -> None:
    """gap_61: 2 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell58",
        [
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
            (1700000061, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 2
    assert [u.capture_at for u in units] == [1700000000.0, 1700000061.0]
    assert [u.duration_seconds for u in units] == [0.002, 0.002]


def test_units_split_63(grid_root) -> None:
    """split_63: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell59",
        [
            (
                1700000000,
                b'~\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                16000,
                2,
            )
        ],
    )
    units = list(decode_units(paths, max_seconds=0.004))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [0.0039375]


def test_units_split_64(grid_root) -> None:
    """split_64: 1 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell60",
        [
            (
                1700000000,
                b'\x80\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                16000,
                2,
            )
        ],
    )
    units = list(decode_units(paths, max_seconds=0.004))
    assert len(units) == 1
    assert [u.capture_at for u in units] == [1700000000.0]
    assert [u.duration_seconds for u in units] == [0.004]


def test_units_split_65(grid_root) -> None:
    """split_65: 2 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell61",
        [
            (
                1700000000,
                b'\x82\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                16000,
                2,
            )
        ],
    )
    units = list(decode_units(paths, max_seconds=0.004))
    assert len(units) == 2
    assert [u.capture_at for u in units] == [1700000000.0, 1700000000.004]
    assert [u.duration_seconds for u in units] == [0.004, 6.25e-05]


def test_units_split_128(grid_root) -> None:
    """split_128: 2 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell62",
        [
            (
                1700000000,
                b'\x00\x01\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                16000,
                2,
            )
        ],
    )
    units = list(decode_units(paths, max_seconds=0.004))
    assert len(units) == 2
    assert [u.capture_at for u in units] == [1700000000.0, 1700000000.004]
    assert [u.duration_seconds for u in units] == [0.004, 0.004]


def test_units_split_129(grid_root) -> None:
    """split_129: 3 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell63",
        [
            (
                1700000000,
                b'\x02\x01\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ',
                16000,
                2,
            )
        ],
    )
    units = list(decode_units(paths, max_seconds=0.004))
    assert len(units) == 3
    assert [u.capture_at for u in units] == [1700000000.0, 1700000000.004, 1700000000.008]
    assert [u.duration_seconds for u in units] == [0.004, 0.004, 6.25e-05]


def test_units_same_stamp3(grid_root) -> None:
    """same_stamp3: 3 unit(s), frozen captures and durations."""
    paths = _bundle(
        grid_root / "cell64",
        [
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
            (1700000000, b'@\x00\x00\x00ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ', 16000, 2),
        ],
    )
    units = list(decode_units(paths, max_seconds=7200))
    assert len(units) == 3
    assert [u.capture_at for u in units] == [1700000000.0, 1700000000.0, 1700000000.0]
    assert [u.duration_seconds for u in units] == [0.002, 0.002, 0.002]
