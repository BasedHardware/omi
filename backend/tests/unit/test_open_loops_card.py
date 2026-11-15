"""Open-loop card writer: self-contained deterministic templates.

Every card names who and what in recognizable words, says where it came from
(conversation title + weekday in the user's timezone) and why now, stays
within the length budget, and uses no internal jargon.
"""

from datetime import datetime, timezone

import pytest

from utils.open_loops.card import (
    COMBINED_MAX_CHARS,
    OpenLoopCard,
    build_card,
    build_review_card,
    llm_polisher,
)

_NOW = datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc)  # Monday
_TUESDAY_LAST = '2026-10-20T15:00:00+00:00'  # Tuesday


def _card(**overrides):
    loop = {
        'kind': 'owed_to_user',
        'who': 'Maya',
        'what': 'send the vendor write-up',
        'by_when': None,
        'evidence': 'I will send it over tomorrow',
        'title': 'Pricing sync',
        'started_at': _TUESDAY_LAST,
    }
    loop.update(overrides)
    return loop, build_card(loop, tz='America/Los_Angeles', now=_NOW)


def _assert_contract(card: OpenLoopCard):
    assert card.question.endswith('?')
    assert card.combined_chars <= COMBINED_MAX_CHARS
    lowered = f'{card.question} {card.context_line}'.casefold()
    for token in ('open loop', 'extraction', 'schema', 'action item', 'loop_id', 'task_id'):
        assert token not in lowered
    # source_ref always names the origin: title + local weekday (+ date).
    assert '(' in card.source_ref and card.source_ref.strip()


def test_delegated_with_known_who_names_who_and_source():
    loop, card = _card()
    assert card.question == 'Did Maya send the vendor write-up?'
    assert card.context_line.startswith("From Tuesday's Pricing sync")
    assert 'no follow-up since Tuesday' in card.context_line  # 6 days stale
    assert card.source_ref == 'Pricing sync (Tuesday), 2026-10-20'
    _assert_contract(card)


def test_unattributed_request_asks_anyone():
    loop, card = _card(who='unknown', what='find a notary for the filing', by_when='2026-10-28')
    assert card.question == "Did anyone find a notary for the filing?"
    assert 'due Wednesday' in card.context_line  # 2026-10-28 within two days
    _assert_contract(card)


def test_stale_own_task_uses_the_related_task_title():
    loop, card = _card(
        kind='own_commitment',
        who=None,
        what='',
        related_task={'title': 'Review the Omi PR diff'},
        started_at='2026-10-19T09:00:00+00:00',
    )
    assert card.question == 'Did you review the Omi PR diff?'
    assert 'no follow-up since Oct 19' in card.context_line  # older than a week: date form
    _assert_contract(card)


def test_strong_task_link_renders_the_your_task_clause():
    """A model-asserted task link asks about the task in the task's own words
    and says so — the clause is what makes Done evidence about the task."""
    loop, card = _card(
        kind='own_commitment',
        who=None,
        what='',  # card_view sets the task title as `what` for strong links
        related_task={
            'title': 'send Tyler the bullets for the Stably write-up',
            'opened_on': '2026-10-22T09:00:00+00:00',  # a Thursday
        },
        started_at='2026-10-22T09:00:00+00:00',
    )
    assert card.question.startswith('Did you send Tyler the bullets for the Stably write-up')
    assert card.question.endswith('(your task from Thursday)?')
    _assert_contract(card)


def test_observed_defect_keeps_the_imperative_next_step():
    loop, card = _card(
        kind='issue_or_blocker',
        who='the intern',
        what='File the recordings cutting off and duplicating bug',
        title='Omi Access call',
    )
    assert card.question == 'Did you file the recordings cutting off and duplicating bug?'
    assert "From Tuesday's Omi Access call" in card.context_line
    _assert_contract(card)


def test_due_today_and_overdue_forms():
    _, due_today = _card(by_when='2026-10-26')
    assert 'due today' in due_today.context_line
    _, overdue = _card(by_when='2026-10-24')
    assert 'was due Saturday' in overdue.context_line


def test_fresh_loop_has_no_staleness_clause():
    _, card = _card(started_at='2026-10-25T10:00:00+00:00')
    assert 'no follow-up' not in card.context_line
    assert 'due' not in card.context_line


def test_long_titles_and_phrases_are_truncated_within_budget():
    loop, card = _card(
        who='Dr. Verylongname von Richardson-Smith',
        what='send the extremely detailed quarterly vendor compliance write-up with every single appendix attached and reviewed',
        title='The incredibly long quarterly business review session with all stakeholders present',
        by_when='2026-11-20',
    )
    _assert_contract(card)
    assert '…' in card.question  # the phrase was clipped, not run wild
    assert len(card.question) <= 140
    assert card.source_ref.startswith('The incredibly long quarterly…')


def test_weekday_follows_the_user_timezone():
    loop = {
        'kind': 'owed_to_user',
        'who': 'Ann',
        'what': 'send the deck',
        'title': 'Late call',
        'started_at': '2026-10-25T23:30:00+00:00',
    }
    assert '(Sunday)' in build_card(loop, tz='UTC', now=_NOW).source_ref
    assert '(Monday)' in build_card(loop, tz='Asia/Tokyo', now=_NOW).source_ref


def test_bad_timezone_falls_back_to_utc():
    loop, _ = _card()
    fallback = build_card(loop, tz='Not/AZone', now=_NOW)
    assert 'Tuesday' in fallback.source_ref


def test_history_entry_drives_the_staleness_date():
    loop, card = _card(
        history=[{'date': '2026-10-21', 'status': 'opened'}, {'date': '2026-10-23', 'status': 'progressing'}]
    )
    assert 'no follow-up since Friday' in card.context_line


def test_polish_acceptance_and_rejection():
    loop, template = _card()

    def good(card, _loop):
        return OpenLoopCard(
            question='Did Maya send the vendor write-up?',
            context_line="Tuesday's Pricing sync — still nothing back",
            source_ref=card.source_ref,
            polished=True,
        )

    polished = build_review_card(loop, tz='UTC', now=_NOW, polisher=good)
    assert polished.polished and polished.question.startswith('Did Maya')

    def jargon(card, _loop):
        return OpenLoopCard(
            question='Open loop: did Maya send it?',
            context_line='extraction pending',
            source_ref=card.source_ref,
            polished=True,
        )

    def oversized(card, _loop):
        return OpenLoopCard(
            question='Did Maya send the thing ' * 6, context_line='x' * 90, source_ref=card.source_ref, polished=True
        )

    def no_question_mark(card, _loop):
        return OpenLoopCard(
            question='Did Maya send the write-up', context_line='ok', source_ref=card.source_ref, polished=True
        )

    def boom(card, _loop):
        raise RuntimeError('provider down')

    for bad in (jargon, oversized, no_question_mark, boom):
        kept = build_review_card(loop, tz='UTC', now=_NOW, polisher=bad)
        assert kept == template and not kept.polished


def test_polisher_is_none_while_the_switch_is_off(monkeypatch):
    monkeypatch.delenv('OPEN_LOOPS_CARD_POLISH_ENABLED', raising=False)
    assert llm_polisher('u') is None
    monkeypatch.setenv('OPEN_LOOPS_CARD_POLISH_ENABLED', 'true')
    assert llm_polisher('u') is not None


def _nano_response(content: str):
    class _Nano:
        def invoke(self, messages):
            return content

    return _Nano()


def test_llm_polish_happy_path_parses_json(monkeypatch):
    monkeypatch.setenv('OPEN_LOOPS_CARD_POLISH_ENABLED', 'true')
    import utils.open_loops.card as card_module

    monkeypatch.setattr(
        card_module,
        'get_llm',
        lambda *a, **k: _nano_response(
            '{"question": "Did Maya send the write-up?", "context_line": "Pricing sync, Tuesday"}'
        ),
    )
    loop, _ = _card()
    polished = build_review_card(loop, tz='UTC', now=_NOW, polisher=llm_polisher('u'))
    assert polished.polished
    assert polished.question == 'Did Maya send the write-up?'


def test_llm_polish_parses_fenced_json(monkeypatch):
    monkeypatch.setenv('OPEN_LOOPS_CARD_POLISH_ENABLED', 'true')
    import utils.open_loops.card as card_module

    monkeypatch.setattr(
        card_module,
        'get_llm',
        lambda *a, **k: _nano_response(
            '```json\n{"question": "Did Maya send the write-up?", "context_line": "Pricing sync, Tuesday"}\n```'
        ),
    )
    loop, template = _card()
    polished = build_review_card(loop, tz='UTC', now=_NOW, polisher=llm_polisher('u'))
    assert polished.polished and polished != template


def test_usage_tracking_wraps_the_polish_call(monkeypatch):
    monkeypatch.setenv('OPEN_LOOPS_CARD_POLISH_ENABLED', 'true')
    import utils.open_loops.card as card_module

    tracked: list = []
    real_track = card_module.track_usage

    def spy(uid, feature):
        tracked.append(feature)
        return real_track(uid, feature)

    monkeypatch.setattr(card_module, 'track_usage', spy)
    monkeypatch.setattr(
        card_module,
        'get_llm',
        lambda *a, **k: _nano_response(
            '{"question": "Did Maya send the write-up?", "context_line": "Pricing sync, Tuesday"}'
        ),
    )
    loop, _ = _card()
    assert build_review_card(loop, tz='UTC', now=_NOW, polisher=llm_polisher('u')).polished
    assert tracked == ['open_loop_card']
