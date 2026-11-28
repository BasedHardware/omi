"""Content-free observation context for paid conversation model calls."""

from contextlib import contextmanager
from contextvars import ContextVar

HEADER = 'X-Omi-LLM-Margin-Cohort'
REVISIONS = frozenset({'first_completion', 'same_revision', 'changed_revision', 'unknown'})
INPUTS = frozenset({'short_transcript', 'other_transcript', 'unknown'})
FEATURES = frozenset({'conversation_v3_outline', 'conversation_v3_summary', 'conversation_v3_summary_open'})
LANES = frozenset('omi:auto:' + feature.replace('_', '-') for feature in FEATURES)
_current: ContextVar[str | None] = ContextVar('llm_margin_attribution', default=None)


@contextmanager
def observe(*, revision: str = 'unknown', input_size: str = 'unknown'):
    token = _current.set(f'{revision}/{input_size}')
    try:
        yield
    finally:
        _current.reset(token)


def header_for(feature: str | None) -> str | None:
    return _current.get() if feature in FEATURES else None


def parse_header(value: str | None) -> tuple[str, str]:
    revision, _, input_size = (value or '').partition('/')
    return (
        revision if revision in REVISIONS else 'unknown',
        input_size if input_size in INPUTS else 'unknown',
    )
