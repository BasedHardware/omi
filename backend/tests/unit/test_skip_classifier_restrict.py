"""Tests for skipping LLM classifier when user is already at restrict stage (#6316).

Verifies that trigger_classifier_if_needed() returns early without calling
the LLM classifier when the user's enforcement stage is already 'restrict',
since restrict is the terminal stage with no further escalation possible.
"""

import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

import utils.fair_use as fair_use_mod


def _make_trigger(trigger_type='daily'):
    mock_trigger = MagicMock()
    mock_trigger.value = trigger_type
    return [{'trigger': mock_trigger}]


class TestSkipClassifierRestrict:
    """Verify classifier is skipped for users already at restrict stage."""

    def test_restrict_skips_classifier(self):
        """Users at restrict stage should not trigger the LLM classifier."""
        fair_use_mod.redis_client = MagicMock()

        mock_classify = AsyncMock(return_value={'misuse_score': 0.9, 'usage_type': 'audiobook'})

        with patch.object(fair_use_mod, 'get_enforcement_stage', return_value='restrict'), patch.object(
            fair_use_mod, '_get_classify_user_purpose', return_value=mock_classify
        ) as mock_getter:
            asyncio.get_event_loop().run_until_complete(
                fair_use_mod.trigger_classifier_if_needed('test-uid', _make_trigger())
            )
            mock_getter.assert_not_called()

    def test_restrict_skips_redis_lock(self):
        """Users at restrict stage should not even acquire the Redis lock."""
        fair_use_mod.redis_client = MagicMock()

        with patch.object(fair_use_mod, 'get_enforcement_stage', return_value='restrict'):
            asyncio.get_event_loop().run_until_complete(
                fair_use_mod.trigger_classifier_if_needed('test-uid', _make_trigger())
            )
            fair_use_mod.redis_client.set.assert_not_called()

    def test_restrict_does_not_escalate(self):
        """Users at restrict should not call escalate_enforcement either."""
        fair_use_mod.redis_client = MagicMock()

        with patch.object(fair_use_mod, 'get_enforcement_stage', return_value='restrict'), patch.object(
            fair_use_mod, 'escalate_enforcement'
        ) as mock_escalate:
            asyncio.get_event_loop().run_until_complete(
                fair_use_mod.trigger_classifier_if_needed('test-uid', _make_trigger())
            )
            mock_escalate.assert_not_called()

    def test_throttle_still_runs_classifier(self):
        """Users at throttle stage should still run the classifier (can escalate to restrict)."""
        fair_use_mod.redis_client = MagicMock()
        fair_use_mod.redis_client.set.return_value = True

        mock_classify = AsyncMock(return_value={'misuse_score': 0.5, 'usage_type': 'personal'})

        with patch.object(fair_use_mod, 'get_enforcement_stage', return_value='throttle'), patch.object(
            fair_use_mod, 'is_free_credits_exhausted', return_value=False
        ), patch.object(
            fair_use_mod, '_get_classify_user_purpose', return_value=mock_classify
        ) as mock_getter, patch.object(
            fair_use_mod,
            'escalate_enforcement',
            return_value={'action': 'none', 'previous_stage': 'throttle', 'new_stage': 'throttle', 'event_id': '1'},
        ):
            asyncio.get_event_loop().run_until_complete(
                fair_use_mod.trigger_classifier_if_needed('test-uid', _make_trigger())
            )
            mock_classify.assert_called_once()

    def test_warning_still_runs_classifier(self):
        """Users at warning stage should still run the classifier."""
        fair_use_mod.redis_client = MagicMock()
        fair_use_mod.redis_client.set.return_value = True

        mock_classify = AsyncMock(return_value={'misuse_score': 0.3, 'usage_type': 'personal'})

        with patch.object(fair_use_mod, 'get_enforcement_stage', return_value='warning'), patch.object(
            fair_use_mod, 'is_free_credits_exhausted', return_value=False
        ), patch.object(
            fair_use_mod, '_get_classify_user_purpose', return_value=mock_classify
        ) as mock_getter, patch.object(
            fair_use_mod,
            'escalate_enforcement',
            return_value={'action': 'none', 'previous_stage': 'warning', 'new_stage': 'warning', 'event_id': '2'},
        ):
            asyncio.get_event_loop().run_until_complete(
                fair_use_mod.trigger_classifier_if_needed('test-uid', _make_trigger())
            )
            mock_classify.assert_called_once()

    def test_none_still_runs_classifier(self):
        """Users at none stage should still run the classifier."""
        fair_use_mod.redis_client = MagicMock()
        fair_use_mod.redis_client.set.return_value = True

        mock_classify = AsyncMock(return_value={'misuse_score': 0.1, 'usage_type': 'personal'})

        with patch.object(fair_use_mod, 'get_enforcement_stage', return_value='none'), patch.object(
            fair_use_mod, 'is_free_credits_exhausted', return_value=False
        ), patch.object(
            fair_use_mod, '_get_classify_user_purpose', return_value=mock_classify
        ) as mock_getter, patch.object(
            fair_use_mod,
            'escalate_enforcement',
            return_value={'action': 'none', 'previous_stage': 'none', 'new_stage': 'none', 'event_id': '3'},
        ):
            asyncio.get_event_loop().run_until_complete(
                fair_use_mod.trigger_classifier_if_needed('test-uid', _make_trigger())
            )
            mock_classify.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
