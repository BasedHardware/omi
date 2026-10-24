import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock, patch

from routers.desktop_prompts import (
    get_desktop_prompts,
    prompt_matches_audience,
    spec_from_doc,
)


def _base_doc(**overrides):
    base = {
        'id': 'prompt-resilience-1',
        'type': 'stars',
        'question': 'How resilient is desktop prompts?',
        'active': True,
        'trigger': {'kind': 'app_launch', 'count': 1},
        'audience': {'rollout_pct': 100, 'min_build': 12000},
    }
    base.update(overrides)
    return base


class MockSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


def test_min_build_string_and_invalid_coercion():
    # String representation of an integer is properly coerced
    doc_str = _base_doc(audience={'min_build': '12500'})
    assert prompt_matches_audience(doc_str, 'user-1', 'stable', 12600) is True
    assert prompt_matches_audience(doc_str, 'user-1', 'stable', 12400) is False

    # Corrupt non-numeric string falls back to 0 without TypeError/ValueError
    doc_corrupt = _base_doc(audience={'min_build': 'corrupt_build'})
    assert prompt_matches_audience(doc_corrupt, 'user-1', 'stable', 100) is True


def test_rollout_pct_string_and_invalid_coercion():
    # String representation of rollout_pct is properly parsed
    doc_zero = _base_doc(audience={'rollout_pct': '0'})
    assert prompt_matches_audience(doc_zero, 'user-1', 'stable', 0) is False

    # Corrupt string falls back to 100
    doc_corrupt = _base_doc(audience={'rollout_pct': 'invalid'})
    assert prompt_matches_audience(doc_corrupt, 'user-1', 'stable', 0) is True


def test_spec_from_doc_non_iterable_options():
    # When options is an int or bool instead of list, it doesn't crash with TypeError
    doc_int_opts = _base_doc(options=12345)
    spec = spec_from_doc(doc_int_opts)
    assert spec is not None
    assert spec.options == []

    # When options is None, default empty list is preserved
    doc_none_opts = _base_doc(options=None)
    spec_none = spec_from_doc(doc_none_opts)
    assert spec_none is not None
    assert spec_none.options == []


def test_spec_from_doc_malformed_counts():
    # Malformed trigger count and max_per_day fallback gracefully
    doc_malformed = _base_doc(
        trigger={'count': 'not-a-number'},
        max_per_day='invalid-day',
    )
    spec = spec_from_doc(doc_malformed)
    assert spec is not None
    assert spec.trigger_count == 0
    assert spec.max_per_day == 1


def test_get_desktop_prompts_query_validation():
    # build < 0 raises HTTP 400
    with pytest.raises(HTTPException) as exc_info:
        get_desktop_prompts(build=-1, uid='user-1')
    assert exc_info.value.status_code == 400
    assert 'build must be non-negative' in exc_info.value.detail

    # channel empty or overly long raises HTTP 400
    with pytest.raises(HTTPException) as exc_info_channel:
        get_desktop_prompts(channel='', uid='user-1')
    assert exc_info_channel.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info_long:
        get_desktop_prompts(channel='a' * 65, uid='user-1')
    assert exc_info_long.value.status_code == 400


def test_get_desktop_prompts_per_document_error_isolation():
    valid_doc = _base_doc(id='valid-1')
    malformed_snapshot = MagicMock()
    malformed_snapshot.id = 'poison-doc'
    malformed_snapshot.to_dict.side_effect = Exception('Firestore corruption error')

    valid_snapshot = MockSnapshot('valid-1', valid_doc)

    with patch(
        'routers.desktop_prompts.list_active_desktop_prompt_snapshots',
        return_value=[malformed_snapshot, valid_snapshot],
    ):
        res = get_desktop_prompts(channel='stable', build=13000, uid='user-1')
        assert len(res.prompts) == 1
        assert res.prompts[0].id == 'valid-1'


def test_get_desktop_prompts_db_failure_shielded():
    with patch(
        'routers.desktop_prompts.list_active_desktop_prompt_snapshots',
        side_effect=RuntimeError('Database connection pool exhausted'),
    ):
        with pytest.raises(HTTPException) as exc_info:
            get_desktop_prompts(uid='user-1')
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == 'Failed to retrieve desktop prompts'
