"""Floor changes must keep both compute admission and creation-delivery coverage."""

import pytest

from tests.unit.test_workflow_contracts import selector_and_all_tests


@pytest.mark.parametrize(
    'source',
    [
        'backend/config/notes_short_clip.py',
        'backend/utils/llm/notes_short_clip.py',
        'backend/utils/llm/notes_short_clip_policy.py',
        'backend/utils/conversations/minimum_derived.py',
    ],
)
def test_floor_sources_select_their_behavior_contracts(selector_and_all_tests, source):
    selector, all_tests = selector_and_all_tests
    selected, reason = selector.tests_for_changed_paths([source], all_tests)
    assert reason == 'selected backend unit tests from changed paths and workflow contracts'
    assert {
        'tests/unit/test_short_clip_rollout.py',
        'tests/unit/test_short_clip_floor.py',
        'tests/unit/test_notes_packet_v2.py',
        'tests/unit/test_structured_emoji_never_defaults_to_brain.py',
        'tests/unit/test_listen_finalization_cloud_tasks.py',
    }.issubset(selected)
