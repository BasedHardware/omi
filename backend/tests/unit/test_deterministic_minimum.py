"""S3: the §1.7 deterministic minimum, table-driven over the spec.

Spec: ``10-backend-plumbing.md`` §1.7. Every row of that table is asserted here,
including the empty-transcript fallback title and the rule that no managed call
is reachable from this path.

Automatic-or-dead: ``test_deterministic_minimum_module_reaches_no_managed_call``
walks the module's real import closure. Route the minimum through anything that
can reach ``get_llm`` and it goes red — the assertion is not a copy of the
module's import list, it is the closure of the module as loaded.
"""

from __future__ import annotations

import ast
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')

from models.conversation_enums import CategoryEnum, ConversationProcessingState
from utils.conversations.deterministic_minimum import (
    TITLE_MAX_CHARS,
    build_deterministic_minimum_structured,
    deterministic_minimum_title,
    fallback_title,
    first_sentence,
    truncate_on_word_boundary,
)

_BACKEND = Path(__file__).resolve().parents[2]
_STARTED_AT = datetime(2026, 9, 4, 15, 14, 0, tzinfo=timezone.utc)


def _conversation(*texts: str, started_at: datetime | None = _STARTED_AT) -> SimpleNamespace:
    return SimpleNamespace(
        transcript_segments=[SimpleNamespace(text=text) for text in texts],
        started_at=started_at,
    )


# ---------------------------------------------------------------- title table


_TITLE_CASES = [
    # (id, segment texts, expected title)
    ('first_sentence_wins', ('We shipped the fence today. Then we broke it.',), 'We shipped the fence today.'),
    ('no_terminator_uses_whole_text', ('Standup with the backend crew',), 'Standup with the backend crew'),
    ('question_terminates', ('Can we ship on Friday? Probably not.',), 'Can we ship on Friday?'),
    ('exclamation_terminates', ('It works! Finally.',), 'It works!'),
    (
        'leading_blank_segment_skipped',
        ('', '   ', 'Second segment carries the title.'),
        'Second segment carries the title.',
    ),
    (
        'segments_join_into_one_sentence',
        ('The migration ran', 'and every shard came back green.'),
        'The migration ran and every shard came back green.',
    ),
    ('internal_whitespace_collapses', ('Too    many\n\nspaces here.',), 'Too many spaces here.'),
]


@pytest.mark.parametrize(
    'texts,expected',
    [(case[1], case[2]) for case in _TITLE_CASES],
    ids=[case[0] for case in _TITLE_CASES],
)
def test_title_follows_the_spec_table(texts, expected) -> None:
    assert deterministic_minimum_title(_conversation(*texts)) == expected


def test_long_sentence_truncates_on_a_word_boundary() -> None:
    sentence = 'The quarterly planning review covering every workstream and its owners and their dates.'
    title = deterministic_minimum_title(_conversation(sentence))
    assert len(title) <= TITLE_MAX_CHARS
    assert not title.endswith(' ')
    # Cut between words, never mid-word: the truncated title is a word-aligned
    # prefix of the sentence.
    assert sentence.startswith(title)
    assert sentence[len(title)] == ' '


def test_single_token_longer_than_the_budget_is_hard_cut() -> None:
    token = 'x' * (TITLE_MAX_CHARS + 20)
    assert deterministic_minimum_title(_conversation(token)) == 'x' * TITLE_MAX_CHARS


def test_truncate_helper_is_a_noop_under_the_budget() -> None:
    assert truncate_on_word_boundary('short enough') == 'short enough'


def test_first_sentence_of_empty_text_is_empty() -> None:
    assert first_sentence('') == ''
    assert first_sentence('   \n  ') == ''


# ------------------------------------------------------------- fallback title


def test_empty_transcript_falls_back_to_source_and_start_time() -> None:
    title = deterministic_minimum_title(_conversation())
    assert title == 'Recording · 3:14 PM'


def test_fallback_uses_started_at_not_the_wall_clock() -> None:
    early = _conversation(started_at=datetime(2026, 9, 4, 6, 5, tzinfo=timezone.utc))
    assert deterministic_minimum_title(early) == 'Recording · 6:05 AM'


def test_fallback_renders_in_the_users_zone_when_one_is_supplied() -> None:
    title = deterministic_minimum_title(_conversation(), tz_name_provider=lambda: 'America/Los_Angeles')
    assert title == 'Recording · 8:14 AM'


def test_unknown_timezone_falls_back_to_utc_rather_than_raising() -> None:
    title = deterministic_minimum_title(_conversation(), tz_name_provider=lambda: 'Not/AZone')
    assert title == 'Recording · 3:14 PM'


def test_timezone_is_not_resolved_when_the_transcript_has_text() -> None:
    calls: list[int] = []

    def provider() -> str:
        calls.append(1)
        return 'America/Los_Angeles'

    assert deterministic_minimum_title(_conversation('Has a transcript.'), tz_name_provider=provider) == (
        'Has a transcript.'
    )
    assert calls == []


def test_naive_started_at_is_read_as_utc() -> None:
    assert fallback_title(datetime(2026, 9, 4, 15, 14)) == 'Recording · 3:14 PM'


def test_missing_started_at_still_yields_a_non_empty_title() -> None:
    # An empty title is what `_get_conversation_obj` reads as "discarded".
    assert deterministic_minimum_title(_conversation(started_at=None)) == 'Recording'


def test_source_label_is_configurable() -> None:
    assert fallback_title(_STARTED_AT, source_label='Meeting') == 'Meeting · 3:14 PM'
    assert fallback_title(_STARTED_AT, source_label='   ') == 'Recording · 3:14 PM'


def test_title_is_pure_over_repeated_calls() -> None:
    conversation = _conversation()
    assert deterministic_minimum_title(conversation) == deterministic_minimum_title(conversation)


# ------------------------------------------------------------- the whole row


def test_structured_matches_every_column_of_the_spec_table() -> None:
    structured = build_deterministic_minimum_structured(_conversation('Kickoff for the free tier.'))
    assert structured.title == 'Kickoff for the free tier.'
    # NOT a fabricated summary and NOT a placeholder that looks like content.
    assert structured.overview == ''
    assert structured.category == CategoryEnum.other
    assert structured.action_items == []
    assert structured.events == []
    assert structured.sections == []


def test_structured_title_is_never_empty_for_an_empty_conversation() -> None:
    assert build_deterministic_minimum_structured(_conversation()).title != ''


# ------------------------------------------------------- processing_state vocab


def test_processing_state_vocabulary_is_exactly_the_spec_pair() -> None:
    assert {state.value for state in ConversationProcessingState} == {'local_pending', 'none'}


# --------------------------------------------------- automatic-or-dead: no LLM


def _module_import_closure(entry: Path) -> set[str]:
    """Every first-party module reachable from ``entry`` by static import."""
    seen: set[str] = set()
    queue = [entry]
    while queue:
        path = queue.pop()
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            for name in names:
                if name in seen:
                    continue
                candidate = _BACKEND / (name.replace('.', '/') + '.py')
                if not candidate.exists():
                    continue
                seen.add(name)
                queue.append(candidate)
    return seen


def test_deterministic_minimum_module_reaches_no_managed_call() -> None:
    entry = _BACKEND / 'utils' / 'conversations' / 'deterministic_minimum.py'
    closure = _module_import_closure(entry)
    # The minimum is the deny-fallback for `authorize_managed_compute`; if it
    # could reach a model client it could not be the fallback.
    forbidden = {'utils.llm.clients', 'utils.llms.clients', 'llm_gateway'}
    reachable_llm = {module for module in closure if module in forbidden or module.startswith('llm_gateway')}
    assert reachable_llm == set(), f'deterministic minimum reaches a model client: {sorted(reachable_llm)}'

    # omi-test-quality: source-inspection -- static contract: the §1.7 minimum must be spendless by construction
    sources = [entry] + [_BACKEND / (module.replace('.', '/') + '.py') for module in sorted(closure)]
    for source in sources:
        text = source.read_text(encoding='utf-8')
        assert 'get_llm(' not in text, f'{source.relative_to(_BACKEND)} calls get_llm on the minimum path'
