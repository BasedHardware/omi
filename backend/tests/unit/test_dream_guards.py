"""Invented regressions for deterministic post-model Dream quality policy."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from database import dream_feedback, dream_store, review_changes, review_store
from models.dream_agent import Edit, Feedback, Plan, Term
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
                    'source_ref': 'conversations/c1',
                    'quote': 'Invented',
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
    records.update(task_records(updated_at=LATER_TIME))
    records['conversations/near'] = {'structured': {'title': ''}, 'transcript_segments': [{'text': 'um'}]}
    near_edit = edit().model_copy(
        update={'target': 'conversations/near', 'evidence': ['conversations/near'], 'after': 'Missing Title'}
    )
    plan = Plan(
        edits=[
            task_edit(),
            Edit(
                kind='spelling',
                target='vocabulary:invented',
                before='Zevra',
                after='Zevrah',
                reason='Invented',
                evidence=['conversations/c1'],
            ),
            near_edit,
            edit(
                'overview',
                'The overview is now a single flat sentence about the boat.',
                before=records['conversations/c1']['structured']['overview'],
            ),
        ],
        vocabulary=[Term(kind='jargon', spelling='window', evidence=['conversations/c1'])],
        feedback=[
            feedback('English/Vietnamese mixed speech.'),
            feedback('conversations/deadbeef'),
            feedback('The invented transcript is accurate.', 'notes'),
            feedback('synthetic heading absent.', 'notes'),
            feedback('synthetic heading stale.', 'notes'),
        ],
    )
    monkeypatch.setattr(dream_agent.dream_capacity, 'claim', AsyncMock(return_value=('slot', 'token')))
    monkeypatch.setattr(dream_agent.dream_capacity, 'release', AsyncMock())
    monkeypatch.setattr(dream_agent.dream_capacity, 'available_model', AsyncMock(return_value='synthetic-model'))
    monkeypatch.setattr(dream_store, 'acquire', lambda *a, **k: {'run_id': 'synthetic', 'mode': 'shadow'})
    monkeypatch.setattr(dream_store, 'vocabulary', lambda *a: [])
    monkeypatch.setattr(dream_agent.dream_reads, 'read_changes', lambda *a, **k: (records, []))
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
    assert result['proposed']['vocabulary'] == []
    assert len(result['proposed']['feedback']) == 1
    assert result['rejected'] == {
        'stale_task_evidence': 1,
        'bad_target': 1,
        'common_word': 1,
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


TASK_TIME = '2026-01-10T00:00:00Z'
LATER_TIME = '2026-01-11T00:00:00Z'


def task_edit(kind='close_task', evidence=None):
    return Edit(
        kind=kind,
        target='action_items/t1',
        reason='Invented completion evidence',
        evidence=evidence or ['conversations/later'],
    )


def task_records(**fields):
    return {
        'action_items/t1': {'created_at': TASK_TIME, 'updated_at': TASK_TIME, 'conversation_id': 'source', **fields},
        'conversations/source': {'created_at': '2026-01-01T00:00:00Z', 'updated_at': LATER_TIME},
        'conversations/later': {'created_at': LATER_TIME},
    }


@pytest.mark.parametrize('kind', ['close_task', 'retire_task'])
@pytest.mark.parametrize('time', ['2026-01-01T00:00:00Z', LATER_TIME])
def test_task_source_cannot_authorize_terminal_transition(kind, time):
    records = task_records()
    records['conversations/source']['created_at'] = time
    item = task_edit(kind, ['conversations/source', 'action_items/t1'])
    sink = {}
    filtered = dream_guards.filter_plan(Plan(edits=[item]), records, usage_sink=sink)
    assert not filtered.edits
    assert sink == {'rejected': {'stale_task_evidence': 1}}


@pytest.mark.parametrize('time', [None, '', 'unknown', 123, TASK_TIME, '2026-01-09T23:59:59Z'])
def test_task_evidence_requires_known_strictly_newer_time(time):
    records = task_records()
    records['conversations/later'] = {'created_at': time}
    assert dream_guards.task_rejection(task_edit(), records['action_items/t1'], records) == 'stale_task_evidence'


@pytest.mark.parametrize(
    'fields',
    [
        {'updated_at': LATER_TIME},
        {'created_at': None, 'updated_at': None},
        {'created_at': 'invalid'},
        {'updated_at': 'invalid'},
    ],
)
def test_task_evidence_must_postdate_latest_known_task_state(fields):
    records = task_records(**fields)
    assert dream_guards.task_rejection(task_edit(), records['action_items/t1'], records) == 'stale_task_evidence'


def test_task_creation_and_update_are_both_fences():
    records = task_records(created_at=LATER_TIME, updated_at=TASK_TIME)
    assert dream_guards.task_rejection(task_edit(), records['action_items/t1'], records) == 'stale_task_evidence'


def test_old_conversation_metadata_refresh_is_not_new_evidence():
    records = task_records()
    records['conversations/later'] = {'created_at': TASK_TIME, 'updated_at': LATER_TIME}
    assert dream_guards.task_rejection(task_edit(), records['action_items/t1'], records) == 'stale_task_evidence'


def test_provenance_source_is_excluded_even_without_legacy_conversation_id():
    records = task_records(conversation_id=None, provenance=[{'kind': 'conversation', 'id': 'later'}])
    assert dream_guards.task_rejection(task_edit(), records['action_items/t1'], records) == 'stale_task_evidence'


@pytest.mark.parametrize('time', [LATER_TIME, '2026-01-11T02:00:00+02:00'])
def test_new_independent_evidence_allows_close_without_minimum_age(time):
    records = task_records()
    records['conversations/later']['created_at'] = time
    item = task_edit(evidence=['conversations/source', 'conversations/later'])
    filtered = dream_guards.filter_plan(Plan(edits=[item]), records)
    assert filtered.edits == [item]


def test_screen_capture_and_native_datetime_evidence_are_supported():
    records = task_records(created_at=datetime(2026, 1, 10), updated_at=None)
    records['screen/s1'] = {'timestamp': LATER_TIME}
    assert dream_guards.task_rejection(task_edit(evidence=['screen/s1']), records['action_items/t1'], records) is None
    records['conversations/later']['created_at'] = datetime(2026, 1, 11, tzinfo=timezone.utc)
    assert dream_guards.task_rejection(task_edit(), records['action_items/t1'], records) is None


@pytest.mark.parametrize(
    'age_days,expected', [(0, 'task_too_recent'), (6, 'task_too_recent'), (7, 'task_too_recent'), (8, None)]
)
def test_retirement_requires_more_than_seven_days(age_days, expected):
    records = task_records()
    now = datetime(2026, 1, 10, tzinfo=timezone.utc) + timedelta(days=age_days)
    assert (
        dream_guards.task_rejection(task_edit('retire_task'), records['action_items/t1'], records, now=now) == expected
    )


def test_retirement_requires_creation_time_even_with_known_update():
    records = task_records(created_at=None)
    assert (
        dream_guards.task_rejection(task_edit('retire_task'), records['action_items/t1'], records) == 'task_too_recent'
    )


@pytest.mark.parametrize(
    'target',
    [
        'vocabulary:term',
        'vocabulary/term',
        'entity/person:a',
        'action_items/t1',
        'conversations/',
        'conversations/a/b',
        'conversations',
    ],
)
def test_spelling_rejects_unsupported_and_malformed_targets_before_missing_evidence(target):
    item = Edit(
        kind='spelling', target=target, before='Zevra', after='Zevrah', reason='Invented', evidence=['conversations/c1']
    )
    sink = {}
    filtered = dream_guards.filter_plan(Plan(edits=[item]), {}, usage_sink=sink)
    assert not filtered.edits
    assert sink == {'rejected': {'bad_target': 1}}
    with pytest.raises(ValueError, match='dream_bad_target'):
        dream_tools.apply_edit('invented', item, {})


@pytest.mark.parametrize('collection', ['conversations', 'people', 'memories', 'memory_items'])
def test_supported_spelling_targets_survive_filter(collection):
    item = Edit(
        kind='spelling',
        target=collection + '/s1',
        before='Zevra',
        after='Zevrah',
        reason='Invented',
        evidence=[collection + '/s1'],
    )
    assert dream_guards.filter_plan(Plan(edits=[item]), {item.target: {}}).edits == [item]


@pytest.mark.parametrize('word', ['window', 'garden', 'table', ' Window '])
def test_common_jargon_is_removed_and_counted_without_changing_aliases(word):
    common = Term(kind='jargon', spelling=word, aliases=['synthetic-alias'], evidence=['conversations/c1'])
    rare = Term(kind='jargon', spelling='qubit', aliases=['window'], evidence=['conversations/c1'])
    plan = Plan(vocabulary=[common, rare])
    sink = {}
    filtered = dream_guards.filter_plan(plan, {}, usage_sink=sink)
    assert filtered.vocabulary == [rare]
    assert filtered.vocabulary[0].aliases == ['window']
    assert sink == {'rejected': {'common_word': 1}}
    assert plan.vocabulary == [common, rare]


@pytest.mark.parametrize('kind', ['person', 'organization', 'project'])
def test_named_vocabulary_is_unaffected_even_when_it_matches_a_common_word(kind):
    term = Term(kind=kind, spelling='Window', evidence=['conversations/c1'])
    assert dream_guards.filter_plan(Plan(vocabulary=[term]), {}).vocabulary == [term]


@pytest.mark.parametrize('word', ['garden gate', 'garden-gate', 'jardín', 'qubit'])
def test_compounds_and_specialized_terms_are_not_common_single_words(word):
    assert dream_guards.vocabulary_rejection(Term(kind='jargon', spelling=word, evidence=['conversations/c1'])) is None


def test_apply_rechecks_task_policy_before_any_journal_or_storage(monkeypatch):
    records = task_records(updated_at=LATER_TIME)
    monkeypatch.setattr(review_changes, 'agent_change_allowed', lambda *a: pytest.fail('unsafe task reached journal'))
    with pytest.raises(ValueError, match='dream_stale_task_evidence'):
        dream_tools.apply_edit('invented', task_edit(), records)


@pytest.mark.parametrize('reason', ['stale_task_evidence', 'task_too_recent', 'bad_target', 'common_word'])
def test_round_two_metrics_count_fixed_reason_codes_without_content(reason, caplog):
    sample = dream_metrics.REJECTED.labels(reason)
    before = sample._value.get()
    with caplog.at_level('INFO', logger=dream_metrics.__name__):
        dream_metrics.record_pass({'status': 'complete', 'rejected': {reason: 2}})
    assert sample._value.get() == before + 2
    assert reason in caplog.text
    assert 'Zevrah' not in caplog.text


def test_recent_retirement_is_filtered_and_counted_but_close_remains_eligible():
    now = datetime.now(timezone.utc)
    records = task_records(created_at=now - timedelta(days=1), updated_at=now - timedelta(hours=1))
    records['conversations/later']['created_at'] = now - timedelta(minutes=1)
    close = task_edit()
    sink = {}
    filtered = dream_guards.filter_plan(Plan(edits=[task_edit('retire_task'), close]), records, usage_sink=sink)
    assert filtered.edits == [close]
    assert sink == {'rejected': {'task_too_recent': 1}}


def test_close_with_independent_evidence_uses_reversible_journal_and_fences_current_task(monkeypatch):
    records = task_records()
    raw = deepcopy(records['action_items/t1'])
    ref = SimpleNamespace(get=lambda: SimpleNamespace(to_dict=lambda: raw))
    monkeypatch.setattr(
        review_store,
        'user',
        lambda *a: SimpleNamespace(collection=lambda *a: SimpleNamespace(document=lambda *a: ref)),
    )
    monkeypatch.setattr(dream_tools, 'get_task_workflow_control', lambda *a: SimpleNamespace(account_generation=0))
    monkeypatch.setattr(review_changes, 'agent_change_allowed', lambda *a: True)
    writes = []
    monkeypatch.setattr(review_changes, 'record_agent_change', lambda *a, **k: writes.append((a, k)))
    assert dream_tools.apply_edit('invented', task_edit(), records) == 'applied'
    args, kwargs = writes[0]
    assert args[2][0].patch['status'] == 'completed'
    assert kwargs['expected_documents'] == {'t1': raw}
    # A changed source must fail the policy even when its updated_at was not refreshed.
    raw['conversation_id'] = 'later'
    with pytest.raises(ValueError, match='dream_stale_task_evidence'):
        dream_tools.apply_edit('invented', task_edit(), records)
    assert len(writes) == 1
