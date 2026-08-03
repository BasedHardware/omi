"""The deterministic half of a PAPER edition.

Open loops, the stance ledger and the desk are pure functions of the stored daily
summaries, so they are asserted directly — no model, no fixtures beyond dicts shaped
like what ``database.daily_summaries`` returns. The paywall test at the bottom is the
one exception: the tier gate is a property of assembly rather than of any single block,
so it drives ``build_edition`` with its two IO seams patched.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from models.paper import Counterpoint, EditionTier, Lede
from utils.paper import edition
from utils.paper.desk import find_dropped_people
from utils.paper.loops import find_open_loops
from utils.paper.stances import find_one_sided_stance
from utils.paper.text import content_words, overlap

TODAY = date(2026, 6, 11)

HIRE_QUESTION = 'Should we hire a second backend engineer?'
SHIP_POSITION = 'Ship the desktop rewrite before the mobile refresh'


def _summary(day, *, questions=(), decisions=(), nuggets=(), headline='', overview='', highlights=()):
    """One stored daily summary, in the shape the blocks read."""
    return {
        'date': day,
        'headline': headline,
        'overview': overview,
        'highlights': [{'topic': topic, 'summary': text} for topic, text in highlights],
        'unresolved_questions': [{'question': question} for question in questions],
        'decisions_made': [{'decision': decision} for decision in decisions],
        'knowledge_nuggets': [{'insight': insight} for insight in nuggets],
    }


# ============================================================================
# OPEN LOOPS
# ============================================================================


def test_unanswered_question_is_carried_with_its_age():
    loops = find_open_loops([_summary('2026-06-01', questions=[HIRE_QUESTION])], TODAY)

    assert [loop.question for loop in loops] == [HIRE_QUESTION]
    assert loops[0].first_raised == '2026-06-01'
    assert loops[0].days_open == 10


def test_question_answered_by_a_later_decision_is_dropped():
    summaries = [
        _summary('2026-06-01', questions=[HIRE_QUESTION]),
        _summary('2026-06-04', decisions=['Decided to hire a second backend engineer this quarter.']),
    ]

    assert find_open_loops(summaries, TODAY) == []


def test_question_answered_by_a_later_nugget_is_dropped():
    summaries = [
        _summary('2026-06-01', questions=[HIRE_QUESTION]),
        _summary('2026-06-04', nuggets=['Hiring a second backend engineer takes eleven weeks.']),
    ]

    assert find_open_loops(summaries, TODAY) == []


def test_reasking_a_question_does_not_reset_its_clock():
    summaries = [
        _summary('2026-06-01', questions=[HIRE_QUESTION]),
        _summary('2026-06-08', questions=['Should we hire a second backend engineer this quarter?']),
    ]

    loops = find_open_loops(summaries, TODAY)

    assert len(loops) == 1
    assert loops[0].first_raised == '2026-06-01'
    assert loops[0].days_open == 10


def test_open_loops_are_ordered_oldest_first_and_capped():
    summaries = [
        _summary('2026-06-02', questions=['Should we move the office to Brooklyn?']),
        _summary('2026-06-05', questions=[HIRE_QUESTION]),
        _summary('2026-06-08', questions=['Should we drop the Android tablet layout?']),
    ]

    loops = find_open_loops(summaries, TODAY)

    assert [loop.days_open for loop in loops] == [9, 6, 3]
    assert find_open_loops(summaries, TODAY, limit=2) == loops[:2]


def test_question_raised_today_is_not_yet_a_loop():
    assert find_open_loops([_summary('2026-06-11', questions=[HIRE_QUESTION])], TODAY) == []


# ============================================================================
# STANCES
# ============================================================================


def test_position_repeated_across_days_is_a_counterpoint_candidate():
    summaries = [
        _summary('2026-06-02', decisions=[SHIP_POSITION]),
        _summary('2026-06-02', decisions=[SHIP_POSITION]),  # restated the same day
        _summary('2026-06-05', decisions=[SHIP_POSITION]),
        _summary('2026-06-09', decisions=[SHIP_POSITION]),
    ]

    stance = find_one_sided_stance(summaries)

    assert stance.position == SHIP_POSITION
    assert stance.days_asserted == 3  # distinct days, not restatements
    assert stance.first_asserted == '2026-06-02'
    assert stance.argument == ''  # a candidate: the model has not written the other side yet


def test_position_taken_on_a_single_day_is_not_a_pattern():
    summaries = [
        _summary('2026-06-02', decisions=[SHIP_POSITION]),
        _summary('2026-06-05', decisions=['Move the standup to Thursday mornings']),
    ]

    assert find_one_sided_stance(summaries) is None


def test_hedged_cluster_is_not_one_sided():
    summaries = [
        _summary('2026-06-02', decisions=[SHIP_POSITION]),
        _summary('2026-06-05', decisions=[f'{SHIP_POSITION}, however the risk to mobile is real']),
    ]

    assert find_one_sided_stance(summaries) is None


# ============================================================================
# THE DESK
# ============================================================================


def test_person_gone_quiet_lands_on_the_desk():
    summaries = [
        _summary('2026-06-06', headline='Maya walked through the roadmap'),
        _summary('2026-06-10', headline='Closed the billing migration'),
    ]

    desk = find_dropped_people(summaries, ['Maya Chen'], TODAY)

    assert [(item.name, item.days_since) for item in desk] == [('Maya Chen', 5)]
    assert desk[0].last_mentioned == '2026-06-06'
    assert desk[0].context == 'Maya walked through the roadmap'


def test_person_mentioned_this_week_is_not_dropped():
    summaries = [
        _summary('2026-06-02', headline='Maya walked through the roadmap'),
        _summary('2026-06-10', headline='Maya shipped the tablet layout'),
    ]

    # The most recent mention decides: an older mention must not resurrect a live thread.
    assert find_dropped_people(summaries, ['Maya Chen'], TODAY) == []


def test_long_closed_thread_is_not_dropped():
    summaries = [_summary('2026-04-12', headline='Maya walked through the roadmap')]

    assert find_dropped_people(summaries, ['Maya Chen'], TODAY) == []


def test_name_does_not_match_a_word_that_merely_contains_it():
    summaries = [_summary('2026-06-06', headline='We hit the same wall as Samsung last week')]

    assert find_dropped_people(summaries, ['Sam Rivera'], TODAY) == []


# ============================================================================
# TEXT PRIMITIVES
# ============================================================================


def test_overlap_is_asymmetric():
    question = 'billing migration'
    answer = 'we finished the billing migration to postgres today'

    # 2 of the question's 2 content words appear in the answer; 2 of the answer's 5 in the
    # question. Both ratios are exactly representable, so no approx (and no numpy) is needed.
    assert overlap(question, answer) == 1.0
    assert overlap(answer, question) == 0.4


def test_overlap_of_a_source_without_content_words_is_zero():
    assert overlap('', 'anything at all') == 0.0
    assert overlap('is it that was there', 'billing migration') == 0.0


def test_content_words_drops_stopwords_and_singularises_carefully():
    assert content_words('the and is a was') == set()
    assert content_words('loops css ops') == {'loop', 'css', 'ops'}


# ============================================================================
# PAYWALL
# ============================================================================


def test_brief_tier_prints_the_lede_and_nothing_longitudinal():
    """The paywall is the longitudinal read of the record, not a word count.

    Same summaries, same patched model output, both tiers: the edition tier fills every
    block, and the brief keeps only the lede — including dropping a counterpoint the
    editorial call already handed back.
    """
    summaries = [
        _summary('2026-06-01', questions=[HIRE_QUESTION]),
        _summary('2026-06-06', headline='Maya walked through the roadmap', decisions=[SHIP_POSITION]),
        _summary(
            '2026-06-11',
            headline='Closed the billing migration',
            decisions=[SHIP_POSITION],
            nuggets=['Postgres logical replication needs a primary key'],
        ),
    ]
    lede = Lede(headline='Billing Migration Closed', body='It shipped.', source_date='2026-06-11')
    counterpoint = Counterpoint(
        position=SHIP_POSITION,
        argument='Mobile is where the users already are.',
        days_asserted=2,
        first_asserted='2026-06-06',
    )

    with patch.object(edition, '_window', MagicMock(return_value=summaries)), patch.object(
        edition, 'write_editorial', MagicMock(return_value=(lede, counterpoint))
    ), patch.object(edition, 'get_people', MagicMock(return_value=[{'id': 'p1', 'name': 'Maya Chen'}])):
        brief = edition.build_edition('uid1', TODAY, tier=EditionTier.BRIEF, issue_number=7)
        full = edition.build_edition('uid1', TODAY, tier=EditionTier.EDITION, issue_number=7)

    # The signal is real — the paid edition prints every block from these same summaries.
    assert full.open_loops and full.desk and full.margin
    assert full.counterpoint == counterpoint

    assert brief.lede == lede
    assert brief.open_loops == []
    assert brief.desk == []
    assert brief.counterpoint is None
    assert brief.margin is None
