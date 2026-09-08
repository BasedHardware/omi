from datetime import datetime, timezone

from utils.goals_response import normalize_goal_history_entry, normalize_goal_response
from utils.llm.app_generation_prompts import APP_GENERATION_FALLBACK_PROMPTS, app_generation_prompts_from_llm_payload


def test_goal_response_normalization_repairs_legacy_goal_docs_before_response_validation():
    normalized = normalize_goal_response(
        {
            'id': 'goal_legacy',
            'title': 'Read',
            'is_active': True,
            'created_at': '2026-01-01T00:00:00Z',
        }
    )

    assert normalized['id'] == 'goal_legacy'
    assert normalized['title'] == 'Read'
    assert normalized['goal_type'] == 'scale'
    assert normalized['target_value'] == 0
    assert normalized['current_value'] == 0
    assert normalized['min_value'] == 0
    assert normalized['max_value'] == 10
    assert normalized['created_at'] == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert normalized['updated_at'].tzinfo is not None


def test_goal_history_normalization_repairs_legacy_history_docs_before_response_validation():
    normalized = normalize_goal_history_entry({'date': '2026-01-01', 'value': '4.5'})

    assert normalized['date'] == '2026-01-01'
    assert normalized['value'] == 4.5
    assert normalized['recorded_at'].tzinfo is not None


def test_app_generation_prompt_payload_rejects_mixed_llm_lists_before_response_validation():
    response = app_generation_prompts_from_llm_payload(['a', 'b', 3, 'd', 'e'])

    assert response['prompts'] == APP_GENERATION_FALLBACK_PROMPTS


def test_app_generation_prompt_payload_accepts_first_five_strings():
    response = app_generation_prompts_from_llm_payload(['a', 'b', 'c', 'd', 'e', 'f'])

    assert response['prompts'] == ['a', 'b', 'c', 'd', 'e']
