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


# ---------------------------------------------------------------------------
# The brief — external world, read through the reader's own context.
#
# Everything below carries its source. A claim with no source does not get
# printed, and a number we computed ourselves is never presented as one the
# source published. That distinction is the whole product: a briefing people
# act on has to be auditable line by line.
# ---------------------------------------------------------------------------


class Provenance(str, Enum):
    """Where a number or claim actually came from."""

    REPORTED = 'reported'  # stated outright by the cited source
    DERIVED = 'derived'  # computed by us from a reported figure — must say so
    UNVERIFIED = 'unverified'  # single-source or low-confidence — printed, but flagged


class SourceRef(BaseModel):
    name: str
    url: str = ''


class Claim(BaseModel):
    """A statement plus everything needed to check it."""

    text: str
    sources: list[SourceRef] = Field(default_factory=list)
    provenance: Provenance = Provenance.REPORTED
    confidence: float = 1.0
    note: str = ''  # e.g. "arithmetic complement of the reported reduction"

    @property
    def is_printable(self) -> bool:
        """No source, no print — the one rule the whole briefing rests on."""
        return bool(self.text.strip()) and bool(self.sources)


class Figure(BaseModel):
    """A chart, with the caption that makes it honest.

    ``caption`` must state what was measured and where each number came from;
    ``comparable`` false renders the explicit warning that bars on one axis are
    not a ranking.
    """

    title: str
    subtitle: str = ''
    bars: list[tuple[str, float]] = Field(default_factory=list)
    caption: str = ''
    comparable: bool = True


class PaperItem(BaseModel):
    title: str
    authors: str = ''
    submitted: str = ''
    identifier: str = ''  # e.g. arXiv:2607.29377
    url: str = ''
    what_it_says: str = ''
    why_it_matters: str = ''  # the bridge to the reader's own work
    experiment: str = ''  # one thing they could run tomorrow
    figure: Figure | None = None


class ToolItem(BaseModel):
    name: str
    what: str = ''
    why: str = ''
    source: SourceRef | None = None


class NewsLine(BaseModel):
    category: str
    claim: Claim


class HeldBack(BaseModel):
    """Something deliberately cut, and why.

    Printing the exclusions is what makes the inclusions trustworthy.
    """

    item: str
    reason: str


class Draft(BaseModel):
    kind: str = 'post'
    body: str = ''
    basis: str = ''  # which paper or which of the reader's own threads it came from


class SourceHealth(BaseModel):
    """Per-source result for this run.

    Silent degradation is the real failure mode — a source that quietly returns
    nothing looks identical to a quiet day. Every source reports whether it
    worked, not only what it returned.
    """

    source: str
    ok: bool = True
    fetched: int = 0
    kept: int = 0
    note: str = ''


class Cover(BaseModel):
    thesis: str = ''  # the through-line across today's material
    emphasis: str = ''  # the one word set in italic accent
    standfirst: str = ''


class Brief(BaseModel):
    """One morning's briefing.

    ``your_day`` is the reader's own context — the same Edition the personal
    paper produces. The external sections are read through it, which is why the
    bridge field on a paper is ``why_it_matters`` rather than an abstract.
    """

    date: str
    issue_number: int = 1
    tier: EditionTier = EditionTier.EDITION

    cover: Cover = Field(default_factory=Cover)
    papers: list[PaperItem] = Field(default_factory=list)
    skim: list[Claim] = Field(default_factory=list)
    tools: list[ToolItem] = Field(default_factory=list)
    news: list[NewsLine] = Field(default_factory=list)
    your_day: Edition | None = None
    held_back: list[HeldBack] = Field(default_factory=list)
    drafts: list[Draft] = Field(default_factory=list)
    source_health: list[SourceHealth] = Field(default_factory=list)

    @property
    def counts(self) -> str:
        """The masthead tally: `3 PAPERS · 9 TOOLS · 17 NEWS LINES`."""
        parts = []
        for n, singular in ((len(self.papers), 'PAPER'), (len(self.tools), 'TOOL'), (len(self.news), 'NEWS LINE')):
            if n:
                parts.append(f"{n} {singular}{'' if n == 1 else 'S'}")
        return ' · '.join(parts)
