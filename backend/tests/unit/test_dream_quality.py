"""Invented language/privacy fixtures and reversible conversation polish boundaries."""

from copy import deepcopy
from types import SimpleNamespace
import unicodedata

import pytest
from pydantic import ValidationError

from database import dream_feedback, review_changes, review_store
from models.dream_agent import Edit, Feedback
from utils import dream_prompt, dream_tools


def feedback(text):
    return Feedback(
        component='notes',
        failure_class='stale_state',
        severity='warning',
        count=1,
        latency_ms=0,
        error_rate=0,
        reproduction=text,
    )


PRIVATE = {
    'conversations/opaque-71': {
        'id': 'opaque-71',
        'structured': {'title': ''},
        'transcript_segments': [
            {'id': 'seg-81', 'text': 'Mai An gặp Bảo Vy tại Vườn Lam. Chúng ta trồng rau cạnh cửa sổ.'}
        ],
    }
}


@pytest.mark.parametrize(
    'text',
    [
        'chúng ta trồng rau cạnh cửa sổ',
        unicodedata.normalize('NFD', 'chúng ta trồng rau cạnh cửa sổ'),
        'A sample says “trồng rau”.',
        'A sample says "cửa sổ".',
        'Mai An',
        'Bảo Vy',
        'Vườn Lam',
        'conversations/opaque-71',
        'opaque-71',
        'seg-81',
    ],
)
def test_feedback_rejects_private_unicode_quotes_names_and_record_ids(text):
    with pytest.raises(ValueError):
        dream_feedback.validate(feedback(text), PRIVATE, [])


def test_feedback_rejects_uncased_script_overlap_and_short_quotes():
    for text in ['我们明天 测试 玩具 小船', 'A sample says 「玩具」.']:
        with pytest.raises(ValueError, match='feedback_input_overlap'):
            dream_feedback.validate(feedback(text), {'text': '我们明天 测试 玩具 小船'}, [])


def test_generic_invented_feedback_is_accepted():
    dream_feedback.validate(feedback('Synthetic empty heading remains blank after processing.'), PRIVATE, [])


def summary(kind='title', **overrides):
    return Edit(
        kind=kind,
        target='conversations/c1',
        before='',
        after=(
            'Trồng rau trên ban công'
            if kind == 'title'
            else '## Trồng rau\n\n- Chúng ta chuẩn bị trồng rau trên ban công vào cuối tuần.'
        ),
        evidence=['conversations/c1'],
        reason='Missing heading',
        **overrides
    )


@pytest.mark.parametrize(
    'update',
    [
        {'target': 'people/p'},
        {'evidence': ['conversations/other']},
        {'after': ''},
        {'after': 'x' * 121},
        {'other': 'conversations/other'},
    ],
)
def test_summary_schema_rejects_wrong_target_evidence_and_unbounded_title(update):
    with pytest.raises(ValidationError):
        Edit.model_validate({**summary().model_dump(), **update})


def row():
    return {
        'id': 'c1',
        'structured': {
            'title': '',
            'overview': '',
            'sections': [],
            'note_claims': [{'text': 'Old claim'}],
        },
        'transcript_segments': [{'text': 'Chúng ta trồng rau trên ban công. ' * 6}],
    }


@pytest.mark.parametrize('kind', ['title', 'overview'])
def test_summary_applies_only_owned_fields_through_journal(monkeypatch, kind):
    source = row()
    ref = SimpleNamespace(get=lambda: SimpleNamespace(to_dict=lambda: deepcopy(source)))
    monkeypatch.setattr(
        review_store,
        'user',
        lambda uid: SimpleNamespace(collection=lambda name: SimpleNamespace(document=lambda key: ref)),
    )
    monkeypatch.setattr(review_changes, 'agent_change_allowed', lambda *a: True)
    calls = []
    monkeypatch.setattr(review_changes, 'record_agent_change', lambda *a, **kw: calls.append((a, kw)))
    assert dream_tools.apply_edit('synthetic', summary(kind), {'conversations/c1': source}) == 'applied'
    args, kw = calls[0]
    patch = args[2][0].patch
    assert patch['structured.' + kind] == summary(kind).after
    assert set(patch) <= review_changes.ALLOWED_FIELDS['conversations']
    assert kw['expected_documents'] == {'c1': source}
    assert args[1].snippet == summary(kind).after
    assert args[1].refs[0].id == 'c1'
    if kind == 'overview':
        assert patch['structured.sections'] == patch['structured.note_claims'] == []
    else:
        assert set(patch) == {'structured.title'}


@pytest.mark.parametrize(
    'update',
    [
        {'is_locked': True},
        {'discarded': True},
        {'deleted': True},
        {'user_title': 'User choice'},
        {'transcript_segments': [{'text': 'Changed evidence'}]},
        {'structured': {'title': 'User correction'}},
    ],
)
def test_summary_rechecks_current_visibility_locks_and_snapshot(monkeypatch, update):
    source = row()
    current = {**deepcopy(source), **update}
    ref = SimpleNamespace(get=lambda: SimpleNamespace(to_dict=lambda: current))
    monkeypatch.setattr(
        review_store,
        'user',
        lambda uid: SimpleNamespace(collection=lambda name: SimpleNamespace(document=lambda key: ref)),
    )
    monkeypatch.setattr(review_changes, 'agent_change_allowed', lambda *a: True)
    monkeypatch.setattr(review_changes, 'record_agent_change', lambda *a, **kw: pytest.fail('unsafe journal'))
    with pytest.raises(review_store.ReviewConflict):
        dream_tools.apply_edit('synthetic', summary(), {'conversations/c1': source})


def test_summary_requires_speech_and_exact_before():
    with pytest.raises(ValueError):
        dream_tools.validate_summary_edit(summary(), {'structured': {}})
    with pytest.raises(review_store.ReviewConflict):
        dream_tools.validate_summary_edit(summary(), {**row(), 'structured': {'title': 'New heading'}})


def test_projection_explicitly_exposes_empty_fields_and_user_title():
    projected = dream_prompt.project_record(
        'conversations/c1', {**row(), 'user_title': 'User heading'}, chars=600, names={}
    )
    assert 'title: ' in projected and 'overview: ' in projected and 'user_title: User heading' in projected


@pytest.mark.parametrize('quote', ['"', "'", '‘'])
def test_short_vietnamese_quotes_cannot_bypass_four_word_gate(quote):
    close = '’' if quote == '‘' else quote
    with pytest.raises(ValueError, match='feedback_input_overlap'):
        dream_feedback.validate(feedback('Example: ' + quote + 'cửa sổ' + close), PRIVATE, [])


def test_decomposed_proper_name_is_rejected_without_quoting():
    inputs = {'text': unicodedata.normalize('NFD', 'Bảo Vy đang thử thuyền.')}
    with pytest.raises(ValueError):
        dream_feedback.validate(feedback('bảo vy'), inputs, [])


def test_short_uncased_evidence_is_rejected_without_quoting():
    with pytest.raises(ValueError):
        dream_feedback.validate(feedback('Example: 玩具'), {'text': '玩具'}, [])


def test_overview_is_bounded_by_schema():
    with pytest.raises(ValidationError):
        Edit.model_validate({**summary('overview').model_dump(), 'after': 'x' * 1001})


def test_quoted_cjk_substring_does_not_require_word_boundaries():
    with pytest.raises(ValueError, match='feedback_input_overlap'):
        dream_feedback.validate(feedback('Example: 「小船」'), {'text': '我们明天测试小船。'}, [])
