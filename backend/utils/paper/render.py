"""Render an edition to paper.

Two outputs from one model: HTML sized for an actual sheet of A4, and plaintext at a
fixed column width. The plaintext path is not decoration — it is what a thermal printer
consumes, so shipping it now keeps the hardware step a driver swap rather than a rewrite.
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
    """`SUNDAY, AUGUST 2, 2026` — falls back to the raw string if unparseable."""
    try:
        parsed = date.fromisoformat(iso_date[:10])
    except (ValueError, TypeError):
        return iso_date
    return parsed.strftime('%A, %B %-d, %Y').upper()


def _age(days: int) -> str:
    """`OPEN 1 DAY` / `OPEN 6 DAYS` — the age is the point of the block."""
    return f"OPEN {days} DAY" if days == 1 else f"OPEN {days} DAYS"


def _silence(days: int) -> str:
    return f"{days} DAY" if days == 1 else f"{days} DAYS"


def render_html(edition: Edition, reader_name: str = '') -> str:
    """Print-ready HTML. One page, black on white, no interactivity."""
    return _env.get_template('paper.html').render(
        edition=edition,
        reader=(reader_name or '').strip().upper(),
        dateline=_dateline(edition.date),
        age=_age,
        silence=_silence,
    )


def render_text(edition: Edition, reader_name: str = '') -> str:
    """Fixed-width plaintext for a thermal printer."""
    out: list[str] = []
    rule = '-' * TEXT_WIDTH

    def block(label: str) -> None:
        out.extend(['', rule, label, ''])

    def wrap(text: str, indent: str = '') -> None:
        out.extend(textwrap.wrap(text, TEXT_WIDTH - len(indent), initial_indent=indent, subsequent_indent=indent))

    out.append('PAPER'.center(TEXT_WIDTH))
    out.append('=' * TEXT_WIDTH)
    meta = ' * '.join(
        filter(
            None,
            [(reader_name or '').strip().upper(), _dateline(edition.date), f'NO. {edition.issue_number}'],
        )
    )
    out.extend(textwrap.wrap(meta, TEXT_WIDTH))

    if edition.lede:
        out.append('')
        wrap(edition.lede.headline.upper())
        if edition.lede.body:
            out.append('')
            wrap(edition.lede.body)

    if edition.open_loops:
        block('OPEN LOOPS')
        for loop in edition.open_loops:
            wrap(loop.question)
            out.append(f'  {_age(loop.days_open)}')
            out.append('')
        out.pop()

    if edition.counterpoint:
        block('COUNTERPOINT')
        wrap(f'You have said this on {edition.counterpoint.days_asserted} separate days:')
        out.append('')
        wrap(edition.counterpoint.position, indent='  ')
        out.append('')
        wrap(edition.counterpoint.argument)

    if edition.desk:
        block('THE DESK')
        for item in edition.desk:
            out.append(f'{item.name.upper()} - QUIET {_silence(item.days_since)}')
            if item.context:
                wrap(item.context)

    if edition.margin:
        block('THE MARGIN')
        wrap(edition.margin.insight)

    out.extend(['', '=' * TEXT_WIDTH, 'END OF EDITION'.center(TEXT_WIDTH), ''])
    return '\n'.join(out)
