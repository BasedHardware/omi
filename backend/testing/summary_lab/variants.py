"""Named pipeline variants. Recorded keys are hermetic; live is opt-in."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Variant:
    id: str
    recorded_key: str
    description: str
    live: bool = False


VARIANTS: tuple[Variant, ...] = (
    Variant(
        id='notes_v2_recorded',
        recorded_key='notes_v2',
        description='Current notes-v2 shape: sectioned recap, verb-led actions.',
    ),
    Variant(
        id='legacy_recorded',
        recorded_key='legacy',
        description='Pre-v2 overview-primary note. Used as the cost/quality baseline.',
    ),
    Variant(
        id='defective_recorded',
        recorded_key='defective',
        description='Calibration: filler, playback commands, and speaker leaks.',
    ),
)

VARIANTS_BY_ID = {variant.id: variant for variant in VARIANTS}
