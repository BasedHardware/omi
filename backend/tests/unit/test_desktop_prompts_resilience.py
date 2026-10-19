"""Unit tests for desktop_prompts router resilience against malformed Firestore documents and store errors."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import routers.desktop_prompts as desktop_prompts_router
from routers.desktop_prompts import get_desktop_prompts, prompt_matches_audience, spec_from_doc


def _base_doc(**overrides):
    doc = {
        'id': 'prompt-2026-10',
        'type': 'stars',
        'question': 'How is Omi Desktop working for you?',
        'active': True,
        'trigger': {'kind': 'question_count', 'count': 5},
        'audience': {'rollout_pct': 100},
    }
    doc.update(overrides)
    return doc


def test_prompt_matches_audience_rejects_non_dict_document():
    assert prompt_matches_audience(None, 'uid-1', 'stable', 100) is False  # type: ignore[arg-type]
    assert prompt_matches_audience(['not-a-dict'], 'uid-1', 'stable', 100) is False  # type: ignore[arg-type]
    assert prompt_matches_audience('raw-string', 'uid-1', 'stable', 100) is False  # type: ignore[arg-type]


@pytest.mark.parametrize('bad_audience', ['all', ['beta'], 100, True])
def test_prompt_matches_audience_rejects_non_dict_audience_field(bad_audience):
    doc = _base_doc(audience=bad_audience)
    assert prompt_matches_audience(doc, 'uid-1', 'stable', 100) is False


def test_prompt_matches_audience_rejects_non_sequence_channels():
    # A string 'stable-beta' would otherwise match 'stable' via substring `in` check!
    assert prompt_matches_audience(_base_doc(audience={'channels': 'stable-beta'}), 'uid-1', 'stable', 100) is False
    assert prompt_matches_audience(_base_doc(audience={'channels': 123}), 'uid-1', 'stable', 100) is False
    assert prompt_matches_audience(_base_doc(audience={'channels': {'stable': True}}), 'uid-1', 'stable', 100) is False


def test_prompt_matches_audience_rejects_channels_containing_only_invalid_entries():
    assert prompt_matches_audience(_base_doc(audience={'channels': [None, '   ', 42]}), 'uid-1', 'stable', 100) is False


def test_prompt_matches_audience_trims_valid_channel_names():
    doc = _base_doc(audience={'channels': ['  beta  ', 'nightly']})
    assert prompt_matches_audience(doc, 'uid-1', 'beta', 100) is True
    assert prompt_matches_audience(doc, 'uid-1', 'stable', 100) is False


def test_prompt_matches_audience_coerces_numeric_string_min_build():
    doc_str = _base_doc(audience={'min_build': '12000'})
    assert prompt_matches_audience(doc_str, 'uid-1', 'stable', 12500) is True
    assert prompt_matches_audience(doc_str, 'uid-1', 'stable', 11500) is False


@pytest.mark.parametrize('bad_min_build', ['not-a-build', True, False, -5, [100]])
def test_prompt_matches_audience_rejects_invalid_min_build(bad_min_build):
    doc_bad = _base_doc(audience={'min_build': bad_min_build})
    assert prompt_matches_audience(doc_bad, 'uid-1', 'stable', 12500) is False


@pytest.mark.parametrize('bad_pct', ['50%', 'nan', float('inf'), True, False, ['100'], {'pct': 100}])
def test_prompt_matches_audience_handles_malformed_rollout_pct(bad_pct):
    doc = _base_doc(audience={'rollout_pct': bad_pct})
    assert prompt_matches_audience(doc, 'uid-1', 'stable', 100) is False


def test_prompt_matches_audience_clamps_out_of_range_rollout_pct():
    assert prompt_matches_audience(_base_doc(audience={'rollout_pct': -10}), 'uid-1', 'stable', 100) is False
    assert prompt_matches_audience(_base_doc(audience={'rollout_pct': 250}), 'uid-1', 'stable', 100) is True


@pytest.mark.parametrize('bad_id', [None, '', '   ', 123, True])
def test_prompt_matches_audience_rejects_missing_or_blank_id(bad_id):
    assert prompt_matches_audience(_base_doc(id=bad_id), 'uid-1', 'stable', 100) is False


def test_spec_from_doc_rejects_non_dict_or_blank_required_fields():
    assert spec_from_doc(None) is None  # type: ignore[arg-type]
    assert spec_from_doc('not-a-dict') is None  # type: ignore[arg-type]
    assert spec_from_doc(_base_doc(id='   ')) is None
    assert spec_from_doc(_base_doc(id=123)) is None
    assert spec_from_doc(_base_doc(question='   ')) is None
    assert spec_from_doc(_base_doc(question=True)) is None
    assert spec_from_doc(_base_doc(type=None)) is None
    assert spec_from_doc(_base_doc(type=123)) is None


def test_spec_from_doc_tolerates_non_dict_trigger_and_cta():
    spec = spec_from_doc(_base_doc(trigger='app_launch', cta=['https://omi.me']))
    assert spec is not None
    assert spec.trigger_kind == 'app_launch'
    assert spec.trigger_count == 0
    assert spec.cta_label is None
    assert spec.cta_url is None


def test_spec_from_doc_does_not_split_string_options_into_characters():
    # Previously `options='yes,no'` produced ['y', 'e', 's', ',', 'n', 'o']
    spec_str = spec_from_doc(_base_doc(type='choice', options='yes,no'))
    assert spec_str is not None
    assert spec_str.options == []

    spec_list = spec_from_doc(
        _base_doc(type='choice', options=['  Yes  ', None, True, '   ', 'No', 'Maybe', '4', '5', '6', '7'])
    )
    assert spec_list is not None
    assert spec_list.options == ['Yes', 'No', 'Maybe', '4', '5', '6']


def test_spec_from_doc_coerces_and_clamps_trigger_count_and_max_per_day():
    spec = spec_from_doc(
        _base_doc(
            trigger={'kind': '  session_end  ', 'count': '-5'},
            max_per_day='invalid',
        )
    )
    assert spec is not None
    assert spec.trigger_kind == 'session_end'
    assert spec.trigger_count == 0
    assert spec.max_per_day == 1

    spec_bool = spec_from_doc(
        _base_doc(
            trigger={'kind': 123, 'count': True},
            max_per_day=False,
        )
    )
    assert spec_bool is not None
    assert spec_bool.trigger_kind == 'app_launch'
    assert spec_bool.trigger_count == 0
    assert spec_bool.max_per_day == 1


def test_spec_from_doc_sanitizes_non_string_and_blank_cta_fields():
    spec = spec_from_doc(_base_doc(type='banner', cta={'label': '   ', 'url': 12345}))
    assert spec is not None
    assert spec.cta_label is None
    assert spec.cta_url is None


def test_get_desktop_prompts_skips_corrupted_snapshots_and_returns_valid_ones():
    broken_snap = SimpleNamespace(
        id='broken-snap', to_dict=lambda: (_ for _ in ()).throw(RuntimeError('corrupt protobuf'))
    )
    non_dict_snap = SimpleNamespace(id='non-dict', to_dict=lambda: ['unexpected', 'list'])
    bad_audience_snap = SimpleNamespace(id='bad-aud', to_dict=lambda: _base_doc(id='bad-aud', audience='invalid'))
    valid_snap_b = SimpleNamespace(
        id='prompt-b',
        to_dict=lambda: _base_doc(id='  ', question='  Second question?  ', trigger='bad-trigger'),
    )
    valid_snap_a = SimpleNamespace(
        id='prompt-a',
        to_dict=lambda: _base_doc(id='prompt-a', question='First question?'),
    )

    with patch.object(
        desktop_prompts_router,
        'list_active_desktop_prompt_snapshots',
        return_value=[broken_snap, non_dict_snap, bad_audience_snap, valid_snap_b, valid_snap_a],
    ):
        res = get_desktop_prompts(channel='stable', build=12500, uid='user-123')

    assert [p.id for p in res.prompts] == ['prompt-a', 'prompt-b']
    assert res.prompts[1].question == 'Second question?'
    assert res.prompts[1].trigger_kind == 'app_launch'


def test_get_desktop_prompts_raises_sanitized_500_on_store_outage():
    with patch.object(
        desktop_prompts_router,
        'list_active_desktop_prompt_snapshots',
        side_effect=RuntimeError('Firestore token=secret_abc failed'),
    ):
        with pytest.raises(HTTPException) as exc_info:
            get_desktop_prompts(channel='stable', build=12500, uid='user-123')

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == 'Failed to load desktop prompts'
