"""Render an edition to paper.

Two outputs from one model: HTML sized for an actual sheet, and plaintext at a
fixed column width. The plaintext path is not decoration — it is what a thermal
printer consumes, so keeping it working makes the hardware step a driver swap
rather than a rewrite.
"""

import pathlib
import textwrap
from datetime import date

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


_env.filters['dateline'] = _dateline
_env.filters['clock'] = _clock
_env.filters['hours'] = _hours


def render_html(edition: Edition, reader_name: str = '') -> str:
    """The edition as a printable page."""
    return _env.get_template('paper.html').render(
        edition=edition,
        reader_name=reader_name,
        dateline=_dateline(edition.date),
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

    yesterday = edition.yesterday
    if yesterday:
        lines.extend(_heading('Yesterday'))
        if yesterday.headline:
            lines.extend(_wrap(yesterday.headline))
            lines.append('')
        lines.extend(_wrap(yesterday.story))
        for block in yesterday.focus:
            lines.extend(_wrap(f'{block.label}: {_hours(block.minutes)}', indent='  '))
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
        for commitment in today.commitments:
            due = f' (due {commitment.due})' if commitment.due else ''
            lines.extend(_wrap(f'[ ] {commitment.text}{due}'))
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

    for_you = edition.for_you
    if not for_you.is_empty:
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

    if edition.photo and edition.photo.is_printable:
        lines.extend(_heading('Yesterday, drawn'))
        lines.extend(_wrap(edition.photo.caption or edition.photo.moment))

    degraded = edition.degraded_sources
    if degraded:
        lines.extend(_heading('Sources'))
        for health in degraded:
            note = f': {health.note}' if health.note else ''
            lines.extend(_wrap(f'- {health.source} unavailable{note}'))

    return '\n'.join(lines).rstrip() + '\n'
