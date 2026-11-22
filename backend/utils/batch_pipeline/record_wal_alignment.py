"""Compare uploaded packets with writer-verified live custody manifests."""

from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
import math

CLOCK_RATE = 48_000
ANCHOR_PACKETS = 4
Anchor = tuple[tuple[str, int, int], ...]
Placement = tuple[int, int]


@dataclass(frozen=True)
class Packet:
    digest: str
    ticks: int
    start: int
    size: int
    source: tuple[str, int, int] | None = None

    @property
    def identity(self) -> tuple[str, int, int]:
        return self.digest, self.ticks, self.size


def _anchors(packets: Sequence[Packet], check: Callable[[float], object]) -> Iterator[tuple[Anchor, int]]:
    for start in range(len(packets) - ANCHOR_PACKETS + 1):
        if start % 128 == 0:
            check(2)
        window = packets[start : start + ANCHOR_PACKETS]
        if any(abs(left.start + left.ticks - right.start) > 96 for left, right in zip(window, window[1:])):
            continue
        if len({packet.digest for packet in window}) == ANCHOR_PACKETS:
            yield tuple(packet.identity for packet in window), start


def index_live(
    live_runs: Sequence[Sequence[Packet]], check: Callable[[float], object]
) -> dict[Anchor, Placement | None]:
    index: dict[Anchor, Placement | None] = {}
    for run, packets in enumerate(live_runs):
        for key, position in _anchors(packets, check):
            index[key] = None if key in index else (run, position)
    return index


def overlap(
    wal: Sequence[Packet],
    live_runs: Sequence[Sequence[Packet]],
    live_index: Mapping[Anchor, Placement | None],
    check: Callable[[float], object],
) -> dict[int, Placement]:
    """Return matched coordinates only if the ordered anchor placement is unique."""
    anchors = list(_anchors(wal, check))
    counts = Counter(key for key, _ in anchors)
    matches: dict[int, Placement] = {}
    for counter, (key, wal_index) in enumerate(anchors):
        if counter % 128 == 0:
            check(2)
        placement = live_index.get(key)
        if counts[key] != 1 or placement is None:
            continue
        run, live_start = placement
        for offset in range(ANCHOR_PACKETS):
            index = wal_index + offset
            position = (run, live_start + offset)
            if index in matches and matches[index] != position:
                return {}
            matches[index] = position
    ordered = sorted(matches.items())
    offsets = [live_runs[run][position].start - wal[index].start for index, (run, position) in ordered]
    if offsets and max(offsets) - min(offsets) > 96:
        return {}
    positions = [position for _, position in ordered]
    if any(left >= right for left, right in zip(positions, positions[1:])):
        return {}
    return matches


def tick(timestamp: object) -> int:
    if not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp) or not 0 < timestamp < 10**10:
        raise ValueError('invalid capture position')
    return round(timestamp * CLOCK_RATE)
