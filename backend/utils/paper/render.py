"""Render an edition to paper.

Two outputs from one model: HTML sized for an actual sheet, and plaintext at a
fixed column width. The plaintext path is not decoration — it is what a thermal
printer consumes, so keeping it working makes the hardware step a driver swap
rather than a rewrite.
"""

import pathlib
import textwrap
from datetime import date
from typing import Any, cast

from jinja2 import Environment, FileSystemLoader, select_autoescape

from models.paper import Edition

_TEMPLATES = pathlib.Path(__file__).parent.parent.parent / 'templates'

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES)),
    autoescape=select_autoescape(['html']),
    trim_blocks=True,
    lstrip_blocks=True,
)

# Receipt-printer standard at font A.
TEXT_WIDTH = 42


def _dateline(iso_date: str) -> str:
    """`SUNDAY, AUGUST 2, 2026` — falls back to the raw string if unparseable.

    Built without ``%-d``. That directive is a glibc extension that raises on
    Windows and musl, and it sat outside the parse guard, so an unsupported
    platform failed the whole render instead of falling back as documented.
    """
    try:
        parsed = date.fromisoformat(iso_date[:10])
    except (ValueError, TypeError):
        return iso_date
    return f'{parsed.strftime("%A, %B")} {parsed.day}, {parsed.year}'.upper()


def _clock(iso_stamp: str) -> str:
    """`09:30` from an ISO timestamp, or empty when there isn't one."""
    if not iso_stamp:
        return ''
    try:
        return iso_stamp[11:16] if len(iso_stamp) >= 16 else ''
    except (TypeError, IndexError):
        return ''


def _hours(minutes: int) -> str:
    """`1h 40m` / `25m` — focus time as a person would say it."""
    if minutes < 60:
        return f'{minutes}m'
    hours, rest = divmod(minutes, 60)
    return f'{hours}h' if rest == 0 else f'{hours}h {rest}m'


# Jinja types `filters` as a union of every builtin filter signature, so a plain
# assignment does not type-check against it. The dict is genuinely str -> callable.
_filters = cast('dict[str, Any]', _env.filters)
_filters['dateline'] = _dateline
_filters['clock'] = _clock
_filters['hours'] = _hours


def render_html(edition: Edition, reader_name: str = '') -> str:
    """The edition as a printable page."""
    return _env.get_template('paper.html').render(
        edition=edition,
        reader_name=reader_name,
        dateline=_dateline(edition.date),
        arxiv_health=next((h for h in edition.source_health if h.source.lower() == 'arxiv'), None),
        day_strip=day_strip_svg(edition.yesterday.timeline) if edition.yesterday else '',
    )


# ---------------------------------------------------------------------------
# Plaintext — 42 columns, for the printer.
# ---------------------------------------------------------------------------


def _wrap(text: str, indent: str = '') -> list[str]:
    """Wrap to the column width, honouring an indent on continuation lines."""
    if not text:
        return []
    return textwrap.wrap(
        text,
        width=TEXT_WIDTH,
        initial_indent=indent,
        subsequent_indent=indent,
    ) or [indent + text[:TEXT_WIDTH]]


def _rule(char: str = '-') -> str:
    return char * TEXT_WIDTH


def _heading(title: str) -> list[str]:
    return ['', title.upper()[:TEXT_WIDTH], _rule()]


def render_text(edition: Edition, reader_name: str = '') -> str:
    """The edition at 42 columns.

    Every line is width-aware, including headers built from user data — a long
    name must wrap rather than blow past the column count.
    """
    lines: list[str] = []

    masthead = 'PAPER' if not reader_name else f'PAPER — {reader_name}'
    lines.extend(_wrap(masthead))
    lines.extend(_wrap(_dateline(edition.date)))
    lines.append(_wrap(f'No. {edition.issue_number}')[0])
    lines.append(_rule('='))

    if edition.cover.thesis:
        lines.append('')
        lines.extend(_wrap(edition.cover.thesis))
        if edition.cover.standfirst:
            lines.extend(_wrap(edition.cover.standfirst))

    yesterday = edition.yesterday
    if yesterday:
        lines.extend(_heading('Yesterday'))
        if yesterday.headline:
            lines.extend(_wrap(yesterday.headline))
            lines.append('')
        lines.extend(_wrap(yesterday.story))

        if yesterday.timeline:
            lines.append('')
            header = f'{_hours(yesterday.recorded_minutes)} recorded, {len(yesterday.timeline)} sessions'
            if yesterday.unbounded_sessions:
                header += f', {yesterday.unbounded_sessions} left open'
            lines.extend(_wrap(header))
            for entry in sorted(yesterday.timeline, key=lambda e: -e.minutes)[:5]:
                if not entry.minutes and not entry.unbounded:
                    continue
                stamp = _clock(entry.start)
                length = 'left open' if entry.unbounded else _hours(entry.minutes)
                lines.extend(_wrap(f'{stamp}  {entry.label} ({length})'))

        if yesterday.done:
            lines.append('')
            lines.extend(_wrap('Done'))
            for item in yesterday.done:
                lines.extend(_wrap(f'- {item}'))

        for block in yesterday.focus:
            lines.extend(_wrap(f'{block.label}: {_hours(block.minutes)}', indent='  '))
        if yesterday.decisions:
            lines.append('')
            lines.extend(_wrap('Decided'))
            for decision in yesterday.decisions:
                lines.extend(_wrap(f'- {decision}'))
        if yesterday.unacted:
            lines.append('')
            lines.extend(_wrap(f'Still open: {yesterday.unacted}'))

    today = edition.today
    if today and not today.is_clear:
        lines.extend(_heading('Today'))
        if today.note:
            lines.extend(_wrap(today.note))
            lines.append('')
        for event in today.events:
            stamp = _clock(event.start)
            prefix = f'{stamp}  ' if stamp else ''
            lines.extend(_wrap(f'{prefix}{event.title}'))
        if today.commitments:
            lines.append('')
            lines.extend(_wrap('To do'))
            for commitment in today.commitments:
                due = f' (due {commitment.due})' if commitment.due else ''
                lines.extend(_wrap(f'[ ] {commitment.text}{due}'))
    elif today and today.is_unknown:
        lines.extend(_heading('Today'))
        lines.extend(_wrap('Calendar unavailable.'))
    elif today:
        lines.extend(_heading('Today'))
        lines.extend(_wrap('Nothing scheduled.'))

    if edition.newsletters:
        lines.extend(_heading('Newsletters'))
        for story in edition.newsletters:
            lines.extend(_wrap(f'- {story.summary}'))
            names = ', '.join(source.name for source in story.sources)
            if names:
                lines.extend(_wrap(f'({names})', indent='  '))
            # The tie to this reader is the only thing separating the section
            # from a feed reader, so it prints here as well as in the HTML.
            if story.why:
                lines.extend(_wrap(story.why, indent='  '))

    for_you = edition.for_you
    searched = next((h for h in edition.source_health if h.source.lower() == 'arxiv'), None)
    if for_you.is_empty and searched and searched.ok and searched.fetched:
        # Silence cannot be told apart from "never ran". State the count.
        lines.extend(_heading('For you'))
        lines.extend(_wrap(f'Nothing cleared the bar. {searched.fetched} entries scanned.'))
    elif not for_you.is_empty:
        lines.extend(_heading('For you'))
        for item in for_you.papers:
            lines.extend(_wrap(item.title))
            if item.why_it_matters:
                lines.extend(_wrap(item.why_it_matters, indent='  '))
            if item.experiment:
                lines.extend(_wrap(f'Try: {item.experiment}', indent='  '))
            lines.append('')
        for tool in for_you.tools:
            lines.extend(_wrap(f'- {tool.name}: {tool.what}'))
        for line in for_you.news:
            if not line.claim.is_printable:
                continue
            lines.extend(_wrap(f'- {line.claim.text}'))
            names = ', '.join(source.name for source in line.claim.sources)
            if names:
                lines.extend(_wrap(f'({names})', indent='  '))
            if line.why:
                lines.extend(_wrap(line.why, indent='  '))

    if edition.photo and edition.photo.is_printable:
        lines.extend(_heading('Yesterday, drawn'))
        lines.extend(_wrap(edition.photo.caption or edition.photo.moment))

    if edition.source_health:
        lines.extend(_heading('Sources'))
        for health in edition.source_health:
            if not health.ok:
                note = f': {health.note}' if health.note else ''
                lines.extend(_wrap(f'- {health.source} unavailable{note}'))
                continue
            if health.fetched:
                detail = f'{health.kept} of {health.fetched}'
            elif health.kept:
                # A source that produces without fetching, like the drawn photo.
                detail = f'{health.kept} kept'
            else:
                detail = health.note or 'nothing found'
            lines.extend(_wrap(f'- {health.source} ok, {detail}'))

    return '\n'.join(lines).rstrip() + '\n'


# ---------------------------------------------------------------------------
# The day strip — hand-built SVG, exact values.
#
# Charts are drawn from stored numbers, never generated. An image model invents
# axis labels and plausible-looking values, which on a page whose whole claim is
# "this is what actually happened" is the same failure as inventing a quote.
# ---------------------------------------------------------------------------

STRIP_WIDTH = 720
STRIP_HEIGHT = 40
STRIP_TOP = 12
MINUTES_IN_DAY = 24 * 60


def day_strip_svg(entries: list) -> str:
    """One band across the day, a block per recorded stretch.

    Positions come from the recorded start stamp and length. An entry whose
    stamp will not parse is skipped rather than placed, because a position on a
    timeline is itself a claim about when something happened.
    """
    placed = [entry for entry in entries if entry.start_minute >= 0]
    if not placed:
        return ''

    def x_of(minute: int) -> float:
        return round(minute / MINUTES_IN_DAY * STRIP_WIDTH, 2)

    parts = [
        f'<svg viewBox="0 0 {STRIP_WIDTH} {STRIP_HEIGHT}" width="100%" height="{STRIP_HEIGHT}" '
        f'role="img" aria-label="Recorded activity across the day" class="strip">'
    ]

    # Hour ticks every three hours, plus the baseline.
    for hour in range(0, 25, 3):
        x = x_of(hour * 60)
        parts.append(f'<line x1="{x}" y1="{STRIP_TOP - 4}" x2="{x}" y2="{STRIP_TOP + 16}" class="strip-tick"/>')
        if hour < 24:
            parts.append(f'<text x="{x + 3}" y="{STRIP_HEIGHT - 4}" class="strip-label">{hour:02d}</text>')
    parts.append(f'<line x1="0" y1="{STRIP_TOP + 16}" x2="{STRIP_WIDTH}" y2="{STRIP_TOP + 16}" class="strip-axis"/>')

    for entry in placed:
        start = max(0, min(entry.start_minute, MINUTES_IN_DAY))
        # A one-minute conversation still has to be visible, so blocks have a floor.
        width = max(x_of(max(entry.minutes, 4)) - x_of(0), 1.5)
        x = x_of(start)
        if x + width > STRIP_WIDTH:
            width = max(STRIP_WIDTH - x, 1.5)
        title = entry.label.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        parts.append(
            f'<rect x="{x}" y="{STRIP_TOP}" width="{round(width, 2)}" height="16" rx="1" class="strip-block">'
            f'<title>{title}</title></rect>'
        )

    parts.append('</svg>')
    return ''.join(parts)
