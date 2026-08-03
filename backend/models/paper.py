"""PAPER — the daily edition built from ambient context.

An edition is finite by construction: five optional blocks, each capped. Blocks with
nothing worth printing are omitted rather than padded, so a quiet day yields a short
paper. See docs/product/paper/SPEC.md.
"""

from enum import Enum

from pydantic import BaseModel, Field


class EditionTier(str, Enum):
    """Paywall gate. Free prints the lede only; paid prints the personalized blocks."""

    BRIEF = 'brief'
    EDITION = 'edition'


class Lede(BaseModel):
    """The one thing that actually mattered."""

    headline: str
    body: str = ''
    source_date: str = ''


class OpenLoop(BaseModel):
    """A question raised and never resolved, carried forward until it closes."""

    question: str
    first_raised: str
    days_open: int = 0


class Counterpoint(BaseModel):
    """The strongest argument against a position asserted one-sidedly."""

    position: str
    argument: str
    days_asserted: int = 0
    first_asserted: str = ''


class DeskItem(BaseModel):
    """Someone mentioned, then dropped."""

    name: str
    context: str = ''
    last_mentioned: str = ''
    days_since: int = 0


class MarginNote(BaseModel):
    """One thing learned, printed back as fact."""

    insight: str
    source_date: str = ''


class Edition(BaseModel):
    """One day's paper.

    ``issue_number`` doubles as the streak counter — it is the count of editions
    published to date, which is also just what a masthead prints.
    """

    date: str
    issue_number: int = 1
    tier: EditionTier = EditionTier.EDITION

    lede: Lede | None = None
    open_loops: list[OpenLoop] = Field(default_factory=list)
    counterpoint: Counterpoint | None = None
    desk: list[DeskItem] = Field(default_factory=list)
    margin: MarginNote | None = None

    @property
    def is_empty(self) -> bool:
        """True when there was not enough signal to print anything at all."""
        return not any([self.lede, self.open_loops, self.counterpoint, self.desk, self.margin])
