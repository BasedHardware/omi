"""Compare two lab runs cell-by-cell."""

from __future__ import annotations

from dataclasses import dataclass

from testing.summary_lab.runner import CellResult, LabRun


@dataclass(frozen=True)
class CellDelta:
    fixture_id: str
    variant_id: str
    usefulness_delta: float
    usd_delta: float
    left_defects: tuple[str, ...]
    right_defects: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            'fixture_id': self.fixture_id,
            'variant_id': self.variant_id,
            'usefulness_delta': round(self.usefulness_delta, 3),
            'usd_delta': round(self.usd_delta, 6),
            'left_defects': list(self.left_defects),
            'right_defects': list(self.right_defects),
        }


@dataclass(frozen=True)
class CompareReport:
    deltas: tuple[CellDelta, ...]
    mean_usefulness_delta: float
    total_usd_delta: float

    def as_dict(self) -> dict[str, object]:
        return {
            'mean_usefulness_delta': round(self.mean_usefulness_delta, 3),
            'total_usd_delta': round(self.total_usd_delta, 6),
            'deltas': [delta.as_dict() for delta in self.deltas],
        }


def _index(run: LabRun) -> dict[tuple[str, str], CellResult]:
    return {(cell.fixture_id, cell.variant_id): cell for cell in run.cells}


def compare_variants(run: LabRun, left_variant: str, right_variant: str) -> CompareReport:
    """Pair cells that share a fixture across two named variants of one run."""
    left = LabRun(cells=tuple(cell for cell in run.cells if cell.variant_id == left_variant))
    right = LabRun(cells=tuple(cell for cell in run.cells if cell.variant_id == right_variant))
    return compare_runs(left, right, by_fixture_only=True)


def compare_runs(left: LabRun, right: LabRun, *, by_fixture_only: bool = False) -> CompareReport:
    if by_fixture_only:
        left_index = {(cell.fixture_id,): cell for cell in left.cells}
        right_index = {(cell.fixture_id,): cell for cell in right.cells}
    else:
        left_index = _index(left)
        right_index = _index(right)
    keys = sorted(set(left_index) | set(right_index))
    deltas: list[CellDelta] = []
    for key in keys:
        left_cell = left_index.get(key)
        right_cell = right_index.get(key)
        left_score = left_cell.judge.usefulness if left_cell else 0.0
        right_score = right_cell.judge.usefulness if right_cell else 0.0
        left_usd = left_cell.cost.usd if left_cell else 0.0
        right_usd = right_cell.cost.usd if right_cell else 0.0
        left_variant = left_cell.variant_id if left_cell else '?'
        right_variant = right_cell.variant_id if right_cell else '?'
        variant_id = key[1] if len(key) > 1 else f'{left_variant}->{right_variant}'
        deltas.append(
            CellDelta(
                fixture_id=key[0],
                variant_id=variant_id,
                usefulness_delta=right_score - left_score,
                usd_delta=right_usd - left_usd,
                left_defects=left_cell.judge.defects if left_cell else ('missing-left',),
                right_defects=right_cell.judge.defects if right_cell else ('missing-right',),
            )
        )
    mean = sum(delta.usefulness_delta for delta in deltas) / len(deltas) if deltas else 0.0
    return CompareReport(
        deltas=tuple(deltas),
        mean_usefulness_delta=mean,
        total_usd_delta=right.total_usd - left.total_usd,
    )
