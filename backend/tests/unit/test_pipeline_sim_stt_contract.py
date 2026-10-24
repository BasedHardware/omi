"""The simulation retry seam honors the production dispatch callback contract."""

from unittest.mock import Mock

import pytest

from testing.pipeline_sim.stt import EMPTY, ERROR, SPEECH, TIMEOUT, WORDS, PlannedWords, ProviderUnavailable, SimSamples


@pytest.mark.parametrize('outcome', [WORDS, EMPTY, ERROR, TIMEOUT, None])
@pytest.mark.parametrize('allowed', [False, True])
def test_planned_retry_matches_dispatch_admission_and_acceptance(outcome, allowed):
    provider = PlannedWords()
    provider.plan['synthetic-segment'] = {'first': EMPTY, 'retry': outcome}
    samples = SimSamples.for_seconds('synthetic-segment', SPEECH, 2)
    before, after = Mock(return_value=allowed), Mock()

    def recover():
        return provider.recover_words(samples, 120, before_dispatch=before, after_dispatch=after)

    if allowed and outcome in {ERROR, TIMEOUT}:
        with pytest.raises(ProviderUnavailable):
            recover()
    else:
        result = recover()
        if outcome is None or not allowed:
            assert result is None
        else:
            assert bool(result) == (outcome == WORDS)

    if outcome is None:
        before.assert_not_called()  # Unplanned/oversize work never reaches dispatch.
    else:
        before.assert_called_once_with()
    if allowed and outcome in {WORDS, EMPTY}:
        after.assert_called_once_with(8.0)  # Two real seconds plus the production padding.
    else:
        after.assert_not_called()


def test_planned_retry_rejects_oversize_before_dispatch():
    provider = PlannedWords()
    provider.plan['synthetic-segment'] = {'first': EMPTY, 'retry': WORDS}
    before, after = Mock(return_value=True), Mock()
    samples = SimSamples.for_seconds('synthetic-segment', SPEECH, 117)
    assert provider.recover_words(samples, 272, before_dispatch=before, after_dispatch=after) is None
    before.assert_not_called()
    after.assert_not_called()
