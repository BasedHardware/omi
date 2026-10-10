"""Invented regressions for deterministic post-model Dream quality policy."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from database import dream_feedback, dream_store, review_changes, review_store
from models.dream_agent import Edit, Feedback, Plan
from utils import dream_agent, dream_guards, dream_metrics, dream_tools, dream_transport

SPEECH = (
    'We will build a solar powered toy boat for the garden basin. '
    'The hull needs paint and the panel needs testing before Saturday. '
    'Our group will bring water and tools then check the steering and photograph the first launch together.'
)


def row(**fields):
    return {'structured': {'title': '', 'overview': '', **fields}, 'transcript_segments': [{'text': SPEECH}]}


def edit(kind='title', after='Solar powered toy boat', before=''):
    return Edit(
        kind=kind,
        target='conversations/c1',
        before=before,
        after=after,
        reason='Invented',
        evidence=['conversations/c1'],
    )


def feedback(text, component='transcription'):
    return Feedback(
        component=component,
        failure_class='spelling',
        severity='warning',
        count=1,
        latency_ms=0,
        error_rate=0,
        reproduction=text,
    )


@pytest.mark.parametrize('kind', ['title', 'overview'])
def test_nonempty_fields_cannot_be_rewritten_even_if_claimed_contradicted(kind):
    current = '## Garden launch\n\n- Paint and test the boat.' if kind == 'overview' else 'Untitled'
    assert dream_guards.summary_rejection(edit(kind, before=current), row(**{kind: current})) == 'nonempty_field'


@pytest.mark.parametrize('speech', [None, '', 'um yes', 'word ' * 39])
@pytest.mark.parametrize('kind', ['title', 'overview'])
def test_sparse_conversations_never_gain_placeholders(kind, speech):
    source = row()
    source['transcript_segments'] = [{'text': speech}]
    assert (
        dream_guards.summary_rejection(
            edit(kind, 'Missing Title' if kind == 'title' else 'This conversation has no discernible content.'), source
        )
        == 'insufficient_speech'
    )


def test_threshold_counts_across_segments_and_is_configurable(monkeypatch):
    source = row()
    source['transcript_segments'] = [{'text': 'solar ' * 20}, {'text': 'boat ' * 20}]
    assert dream_guards.summary_rejection(edit(), source) is None
    monkeypatch.setattr(dream_guards, 'MIN_SUMMARY_TRANSCRIPT_WORDS', 41)
    assert dream_guards.summary_rejection(edit(), source) == 'insufficient_speech'


@pytest.mark.parametrize(
    'text',
    [
        'Missing Title',
        'Untitled garden conversation',
        'Unknown boat subject',
        'No content available',
        'No discernible speech',
        'Conversation',
        'N/A',
        'Không có tiêu đề',
        'Không rõ nội dung',
        'Chưa có tiêu đề',
        'This conversation has no discernible content.',
        'The title is missing.',
        'Toy boat',
        'No meaningful discussion recorded',
        'Title updated from transcript',
        'Chưa xác định chủ đề',
    ],
)
def test_placeholder_and_meta_titles_rejected(text):
    assert dream_guards.summary_rejection(edit(after=text), row()) == 'placeholder'


def test_unrelated_title_rejected_and_grounding_is_accent_insensitive():
    assert dream_guards.summary_rejection(edit(after='Quantum particle experiments'), row()) == 'ungrounded'
    source = row()
    source['transcript_segments'] = [{'text': 'Chúng ta trồng rau trên ban công. ' * 6}]
    assert dream_guards.summary_rejection(edit(after='Trong rau tren ban cong'), source) is None


@pytest.mark.parametrize(
    'after,expected',
    [
        ('Boat is ready.', 'placeholder'),
        ('## Boat launch\n\nThe group will test the solar powered boat tomorrow.', 'overview_format'),
        ('The group will test the solar powered boat tomorrow in the basin.', 'overview_format'),
        ('## Boat launch\n- The solar boat will be tested tomorrow in a basin.', 'overview_format'),
        ('## Boat launch\n\n- The solar boat will be tested tomorrow in a basin.', None),
    ],
)
def test_overviews_require_long_enough_markdown_sections(after, expected):
    assert dream_guards.summary_rejection(edit('overview', after, before=' \n'), row(overview=' \n')) == expected


def test_visible_sections_are_not_erased_when_overview_is_blank():
    assert (
        dream_guards.summary_rejection(
            edit('overview', '## Solar boat\n\n- We will test the solar boat in the basin tomorrow.'),
            row(sections=[{'heading': 'Good notes', 'body_markdown': '- The boat is ready.'}]),
        )
        == 'nonempty_field'
    )


@pytest.mark.parametrize(
    'text',
    [
        'Mixed English/Vietnamese speech causes transcription failure.',
        'Non-English words should be translated.',
        'Code-switching causes a defect.',
        'Bilingual speech appears in the transcript.',
        'Translation failed.',
        'Lỗi ngôn ngữ trong bản chép.',
        'Không nhận dạng tiếng Việt.',
        'Can dich sang tieng Anh.',
        'Lời nói song ngữ bị trộn.',
    ],
)
def test_language_is_never_feedback_defect(text):
    assert dream_guards.feedback_rejection(feedback(text)) == 'language_not_defect'
    with pytest.raises(ValueError, match='language_not_defect'):
        dream_feedback.validate(feedback(text), {}, [])


@pytest.mark.parametrize(
    'text',
    [
        'conversations/abcdef12',
        'memory_items/deadbeef-1234',
        'abcdef12-3456-7890-abcd-1234567890ab',
        'CONVERSATIONS/ABCDEF12',
    ],
)
def test_generic_refs_and_uuids_rejected_even_if_not_in_input(text):
    assert dream_guards.feedback_rejection(feedback(text)) == 'ref_leak'
    with pytest.raises(ValueError, match='ref_leak'):
        dream_feedback.validate(feedback(text), {}, [])


def test_filter_counts_reasons_without_content_and_caps_valid_feedback():
    raw = Plan(
        edits=[edit(), edit(after='Unknown boat subject')],
        feedback=[
            feedback('Mixed-language transcript.'),
            feedback('ref conversations/deadbeef'),
            feedback('synthetic dropped heading.', 'notes'),
            feedback('synthetic stale heading.', 'notes'),
        ],
    )
    sink = {}
    filtered = dream_guards.filter_plan(raw, {'conversations/c1': row()}, usage_sink=sink)
    filtered.feedback = dream_guards.cap_feedback(filtered.feedback, usage_sink=sink)
    assert filtered.edits == [raw.edits[0]]
    assert len(filtered.feedback) == 1
    assert sink == {'rejected': {'placeholder': 1, 'language_not_defect': 1, 'ref_leak': 1, 'feedback_cap': 1}}
    assert len(raw.edits) == 2  # filtering does not mutate the model response


def test_short_spelling_options_are_dropped_and_counted():
    sink = {}
    plan = dream_transport.parse_response(
        Plan,
        {
            'questions': [
                {
                    'item_id': 'spelling:invented',
                    'kind': 'spelling',
                    'title': 'Which spelling?',
                    'reason': 'Invented',
                    'created_at': '2026-10-11T00:00:00Z',
                    'spelling': {'term_id': 'invented', 'allow_custom': True, 'options': ['One']},
                }
            ]
        },
        usage_sink=sink,
    )
    assert not plan.questions
    assert sink['dropped_invalid']['questions'] == 1
    assert sink['validation_errors']['questions.spelling.options:too_short'] == 1


@pytest.mark.parametrize('privacy_fault', [False, True])
def test_run_filters_before_shadow_persistence_and_effects(monkeypatch, caplog, privacy_fault):
    records = {'conversations/c1': row(overview='## Garden launch\n\n- Preserve these good notes.')}
    records['conversations/near'] = {'structured': {'title': ''}, 'transcript_segments': [{'text': 'um'}]}
    near_edit = edit().model_copy(
        update={'target': 'conversations/near', 'evidence': ['conversations/near'], 'after': 'Missing Title'}
    )
    plan = Plan(
        edits=[
            near_edit,
            edit(
                'overview',
                'The overview is now a single flat sentence about the boat.',
                before=records['conversations/c1']['structured']['overview'],
            ),
        ],
        feedback=[
            feedback('English/Vietnamese mixed speech.'),
            feedback('conversations/deadbeef'),
            feedback('The invented transcript is accurate.', 'notes'),
            feedback('synthetic heading absent.', 'notes'),
            feedback('synthetic heading stale.', 'notes'),
        ],
    )
    monkeypatch.setattr(dream_store, 'acquire', lambda *a, **k: {'run_id': 'synthetic', 'mode': 'shadow'})
    monkeypatch.setattr(dream_store, 'vocabulary', lambda *a: [])
    monkeypatch.setattr(dream_agent.dream_reads, 'read_changes', lambda *a: (records, []))
    monkeypatch.setattr(dream_agent, 'plan_pass', AsyncMock(return_value=(plan, 100)))
    monkeypatch.setattr(dream_store, 'demoted_types', lambda *a: set())
    monkeypatch.setattr(review_store, 'remaining_today', lambda *a: 3)
    monkeypatch.setattr(dream_store, 'assert_lease', lambda *a: None)
    monkeypatch.setattr(dream_tools, 'apply_edit', lambda *a: pytest.fail('unsafe edit applied'))
    if privacy_fault:

        def fail_privacy(*args, **kwargs):
            raise RuntimeError('invented privacy service fault')

        monkeypatch.setattr(dream_feedback, 'validate', fail_privacy)
    saved = []
    monkeypatch.setattr(dream_store, 'finish', lambda *a, **k: saved.append(deepcopy(a[2])))
    with caplog.at_level('INFO', logger=dream_metrics.__name__):
        result = asyncio.run(dream_agent.run_pass('invented'))
    if privacy_fault:
        assert result['status'] == 'failed'
        assert saved[0]['proposed']['feedback'] == []
        assert saved[0]['proposed']['edits'] == []
        return
    assert result['status'] == 'complete'
    assert result['proposed']['edits'] == []
    assert len(result['proposed']['feedback']) == 1
    assert result['rejected'] == {
        'insufficient_speech': 1,
        'nonempty_field': 1,
        'language_not_defect': 1,
        'ref_leak': 1,
        'feedback_cap': 1,
        'not_a_failure': 1,
    }
    assert saved[0]['rejected'] == result['rejected']
    assert 'insufficient_speech' in caplog.text
    assert 'deadbeef' not in caplog.text and 'Mixed' not in caplog.text


def test_apply_rechecks_quality_before_journaling(monkeypatch):
    source = row()
    monkeypatch.setattr(review_changes, 'agent_change_allowed', lambda *a: True)
    monkeypatch.setattr(review_changes, 'record_agent_change', lambda *a, **k: pytest.fail('unsafe journal'))
    with pytest.raises(ValueError, match='dream_summary_ungrounded'):
        dream_tools.apply_edit('invented', edit(after='Quantum particle experiments'), {'conversations/c1': source})


def test_whitespace_title_is_preserved_but_whitespace_overview_is_empty():
    assert dream_guards.summary_rejection(edit(before='   '), row(title='   ')) == 'nonempty_field'
    assert (
        dream_guards.summary_rejection(
            edit('overview', '## Boat launch\n\n- The solar boat will be tested tomorrow in a basin.', before='   '),
            row(overview='   '),
        )
        is None
    )


def test_valid_feedback_survives_policy_but_existing_privacy_gate_remains():
    item = feedback('invented widget disappears after processing.', 'notes')
    assert dream_guards.feedback_rejection(item) is None
    with pytest.raises(ValueError, match='feedback_input_overlap'):
        dream_feedback.validate(item, {'text': 'invented widget disappears after processing.'}, [])


@pytest.mark.parametrize(
    'after',
    [
        'This conversation has no discernible content and no information to summarize.',
        '## Không có nội dung\n\n- Không rõ chủ đề vì chưa có thông tin trong bản ghi.',
    ],
)
def test_long_placeholder_overviews_are_rejected(after):
    assert dream_guards.summary_rejection(edit('overview', after), row()) == 'placeholder'


def test_user_title_is_also_preserved_before_shadow_persistence():
    source = {**row(), 'user_title': 'Chosen by owner'}
    sink = {}
    plan = dream_guards.filter_plan(Plan(edits=[edit()]), {'conversations/c1': source}, usage_sink=sink)
    assert not plan.edits
    assert sink['rejected'] == {'nonempty_field': 1}


def test_rejection_metric_uses_only_fixed_labels():
    sample = dream_metrics.REJECTED.labels('insufficient_speech')
    before = sample._value.get()
    dream_metrics.record_pass({'status': 'complete', 'rejected': {'insufficient_speech': 2, 'private-token': 1}})
    assert sample._value.get() == before + 2
    assert not any(
        s.labels.get('reason') == 'private-token' for metric in dream_metrics.REJECTED.collect() for s in metric.samples
    )


@pytest.mark.parametrize('failure_class', ['success', 'none', 'ok'])
def test_non_failure_classes_are_parsed_then_dropped_and_counted(failure_class):
    item = feedback('invented heading dropped.', 'notes').model_dump()
    item['failure_class'] = failure_class
    sink = {}
    parsed = dream_transport.parse_response(Plan, {'feedback': [item]}, usage_sink=sink)
    assert len(parsed.feedback) == 1
    filtered = dream_guards.filter_plan(parsed, {}, usage_sink=sink)
    assert not filtered.feedback
    assert sink['rejected'] == {'not_a_failure': 1}
    assert not sink['dropped_invalid']['feedback']
    with pytest.raises(ValueError, match='not_a_failure'):
        dream_feedback.validate(parsed.feedback[0], {}, [])


def test_info_severity_is_not_failure_even_with_a_failure_class():
    item = feedback('invented heading dropped.', 'notes').model_copy(update={'severity': 'info'})
    assert dream_guards.feedback_rejection(item) == 'not_a_failure'
    with pytest.raises(ValueError, match='not_a_failure'):
        dream_feedback.store('invented', item, {}, [], firestore_client=None)


@pytest.mark.parametrize(
    'text',
    [
        'The invented transcript is accurate and does not require any edits.',
        'The sample is fine.',
        'Everything looks correct.',
        'No issues were found.',
        'No errors in the sample.',
        'The sample does not need corrections.',
        "The sample doesn't require any edits.",
        'Accurate sample transcription.',
        'The sample accurately captures the test utterance.',
        'All good.',
        'Bản chép chính xác và không cần chỉnh sửa.',
        'Mọi thứ đều ổn.',
        'Không có vấn đề nào.',
        'Không có lỗi trong bản ghi.',
        'Khong can bat ky chinh sua nao.',
        'Nội dung hoàn toàn chính xác.',
        'Chính xác hoàn toàn.',
    ],
)
def test_english_and_vietnamese_positive_assurances_are_not_failures(text):
    item = feedback(text, 'notes')
    assert dream_guards.feedback_rejection(item) == 'not_a_failure'
    with pytest.raises(ValueError, match='not_a_failure'):
        dream_feedback.validate(item, {}, [])


@pytest.mark.parametrize(
    'text',
    [
        'The invented transcript is not accurate.',
        'The invented transcript is inaccurate.',
        'Bản chép không chính xác.',
        'An invented heading disappears after processing.',
    ],
)
def test_actual_failure_descriptions_survive_non_failure_guard(text):
    assert dream_guards.feedback_rejection(feedback(text, 'notes')) is None


def test_non_failure_rejection_metric_is_counted():
    sample = dream_metrics.REJECTED.labels('not_a_failure')
    before = sample._value.get()
    dream_metrics.record_pass({'status': 'complete', 'rejected': {'not_a_failure': 2}})
    assert sample._value.get() == before + 2
