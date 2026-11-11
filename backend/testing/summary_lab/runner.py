"""Run fixture × variant matrix through a seam, then judge and price it."""

from __future__ import annotations

from dataclasses import dataclass

from testing.summary_lab.fixtures import Fixture
from testing.summary_lab.judge import JudgeReport, score_note
from testing.summary_lab.pricing import CostEstimate, estimate_usd
from testing.summary_lab.seams import SummarizeFn, recorded_seam
from testing.summary_lab.variants import VARIANTS, Variant


@dataclass(frozen=True)
class CellResult:
    fixture_id: str
    variant_id: str
    note: dict[str, object]
    judge: JudgeReport
    cost: CostEstimate

    def as_dict(self) -> dict[str, object]:
        return {
            'fixture_id': self.fixture_id,
            'variant_id': self.variant_id,
            'note': self.note,
            'judge': self.judge.as_dict(),
            'cost': self.cost.as_dict(),
        }


@dataclass(frozen=True)
class LabRun:
    cells: tuple[CellResult, ...]

    def as_dict(self) -> dict[str, object]:
        return {'cells': [cell.as_dict() for cell in self.cells]}

    @property
    def mean_usefulness(self) -> float:
        if not self.cells:
            return 0.0
        return sum(cell.judge.usefulness for cell in self.cells) / len(self.cells)

    @property
    def total_usd(self) -> float:
        return sum(cell.cost.usd for cell in self.cells)


def run_matrix(
    fixtures: tuple[Fixture, ...],
    variants: tuple[Variant, ...] = VARIANTS,
    *,
    summarize: SummarizeFn | None = None,
) -> LabRun:
    seam = summarize or recorded_seam
    cells: list[CellResult] = []
    for fixture in fixtures:
        for variant in variants:
            note = seam(fixture, variant)
            judge = score_note(
                note,
                expected_facts=fixture.expected_facts,
                must_not_contain=fixture.must_not_contain,
            )
            cost = estimate_usd(
                fixture.token_estimate.get('input', 0),
                fixture.token_estimate.get('output', 0),
            )
            cells.append(
                CellResult(
                    fixture_id=fixture.id,
                    variant_id=variant.id,
                    note=note,
                    judge=judge,
                    cost=cost,
                )
            )
    return LabRun(cells=tuple(cells))
