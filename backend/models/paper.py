"""PAPER — the daily edition built from ambient context.

The edition has five sections and every one of them is fed by a live source:
what you did yesterday, what is on you today, your newsletters deduped to one
line per story, external material ranked against interests we learned from your
own record, and one image of a real moment.

Two rules shape every model here.

**No source, no print.** Anything asserted about the outside world carries the
place it came from (:class:`Claim`). A claim with no source is not printable,
which is enforced rather than asked for.

**Silent degradation is the failure mode.** A source that quietly returns
nothing looks exactly like a quiet day. Every run reports per-source health, so
an edition that has had no Gmail for two weeks says so on its face.

See docs/product/paper/SPEC.md.
"""

from enum import Enum

from pydantic import BaseModel, Field


class EditionTier(str, Enum):
    """Paywall gate. Free prints yesterday only; paid prints the whole edition."""

    BRIEF = 'brief'
    EDITION = 'edition'


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
        """No source, no print — the one rule the whole edition rests on."""
        return bool(self.text.strip()) and bool(self.sources)


# ---------------------------------------------------------------------------
# What we learned about the reader. This is the ranking rubric for everything
# external, derived from their own record rather than a topic list they typed.
# ---------------------------------------------------------------------------


class Interest(BaseModel):
    """One thing the reader demonstrably cares about, and the proof."""

    topic: str
    evidence: str = ''  # what in their record shows it — never invented
    weight: float = 1.0


class InterestProfile(BaseModel):
    """The learned analogue of a hand-written thesis.

    ``thesis`` is the one-line through-line. ``interests`` is the scoring rubric
    external candidates are ranked against. ``exclusions`` is what to drop even
    when it scores well, which is what stops the edition drifting generic.
    """

    generated_at: str = ''
    covers_days: int = 0
    thesis: str = ''
    interests: list[Interest] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)

    @property
    def is_usable(self) -> bool:
        """A profile with no interests ranks nothing — the caller must not pretend it does."""
        return bool(self.interests)


# ---------------------------------------------------------------------------
# Section 1 — Yesterday. The day wrapped, from conversations and screen.
# ---------------------------------------------------------------------------


class FocusBlock(BaseModel):
    """Where a stretch of yesterday actually went."""

    label: str
    minutes: int = 0
    detail: str = ''


class Yesterday(BaseModel):
    """What the reader did and thought, in their own day's terms."""

    headline: str = ''
    story: str = ''  # 3-5 plain sentences
    focus: list[FocusBlock] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    unacted: str = ''  # an idea raised and not taken up — the highest-value line
    source_date: str = ''

    @property
    def tracked_minutes(self) -> int:
        return sum(block.minutes for block in self.focus)


# ---------------------------------------------------------------------------
# Section 2 — Today. What is actually on them.
# ---------------------------------------------------------------------------


class CalendarEntry(BaseModel):
    title: str
    start: str = ''
    end: str = ''
    attendees: list[str] = Field(default_factory=list)
    location: str = ''


class Commitment(BaseModel):
    """Something the reader said they would do.

    ``source`` names where it was found so an item can be traced back rather
    than looking like the paper invented a task.
    """

    text: str
    due: str = ''
    source: str = ''  # action_item | conversation


class Today(BaseModel):
    events: list[CalendarEntry] = Field(default_factory=list)
    commitments: list[Commitment] = Field(default_factory=list)
    note: str = ''  # one line on the shape of the day

    @property
    def is_clear(self) -> bool:
        return not self.events and not self.commitments


# ---------------------------------------------------------------------------
# Section 3 — Newsletters. Many publications, one line per story.
# ---------------------------------------------------------------------------


class NewsletterStory(BaseModel):
    """One story, however many newsletters covered it.

    ``sources`` carries every publication that ran it, which is also the signal
    for how big the story is.
    """

    summary: str
    sources: list[SourceRef] = Field(default_factory=list)
    why: str = ''  # the tie to this reader, when there is one

    @property
    def is_printable(self) -> bool:
        return bool(self.summary.strip()) and bool(self.sources)


# ---------------------------------------------------------------------------
# Section 4 — For you. External material, ranked against the profile.
# ---------------------------------------------------------------------------


class PaperItem(BaseModel):
    title: str
    authors: str = ''
    submitted: str = ''
    identifier: str = ''  # e.g. arXiv:2607.29377
    url: str = ''
    what_it_says: str = ''
    why_it_matters: str = ''  # the bridge to the reader's own work
    experiment: str = ''  # one thing they could run tomorrow


class ToolItem(BaseModel):
    name: str
    what: str = ''
    why: str = ''
    source: SourceRef | None = None


class NewsLine(BaseModel):
    category: str
    claim: Claim


class ForYou(BaseModel):
    papers: list[PaperItem] = Field(default_factory=list)
    tools: list[ToolItem] = Field(default_factory=list)
    news: list[NewsLine] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not any([self.papers, self.tools, self.news])


# ---------------------------------------------------------------------------
# Section 5 — The photo. One real moment, drawn.
# ---------------------------------------------------------------------------


class Photo(BaseModel):
    """An illustration of something that actually happened yesterday.

    ``moment`` is the line from the record it depicts. It is required for the
    photo to print: an image with no moment behind it is decoration, and
    decoration presented as memory is a fabrication.
    """

    moment: str = ''
    caption: str = ''
    prompt: str = ''
    image_b64: str = ''

    @property
    def is_printable(self) -> bool:
        return bool(self.image_b64) and bool(self.moment.strip())


# ---------------------------------------------------------------------------
# Housekeeping — what we cut, and whether each source worked.
# ---------------------------------------------------------------------------


class HeldBack(BaseModel):
    """Something deliberately cut, and why.

    Printing the exclusions is what makes the inclusions trustworthy.
    """

    item: str
    reason: str


class SourceHealth(BaseModel):
    """Per-source result for this run."""

    source: str
    ok: bool = True
    fetched: int = 0
    kept: int = 0
    note: str = ''


class Cover(BaseModel):
    thesis: str = ''  # the through-line across today's material
    emphasis: str = ''  # the one word set in italic accent
    standfirst: str = ''


class Edition(BaseModel):
    """One day's paper.

    ``issue_number`` doubles as the streak counter — it is the count of editions
    published through this date, which is also just what a masthead prints.
    """

    date: str
    issue_number: int = 1
    tier: EditionTier = EditionTier.EDITION

    cover: Cover = Field(default_factory=Cover)
    photo: Photo | None = None
    yesterday: Yesterday | None = None
    today: Today | None = None
    newsletters: list[NewsletterStory] = Field(default_factory=list)
    for_you: ForYou = Field(default_factory=ForYou)

    held_back: list[HeldBack] = Field(default_factory=list)
    source_health: list[SourceHealth] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True when there was not enough signal to print anything at all."""
        return not any(
            [
                self.yesterday,
                self.today,
                self.newsletters,
                not self.for_you.is_empty,
                self.photo,
            ]
        )

    @property
    def degraded_sources(self) -> list[SourceHealth]:
        """Sources that failed this run. Printed, never swallowed."""
        return [health for health in self.source_health if not health.ok]
