from unittest.mock import Mock

import pytest

from scripts import rearm_conversation_artifact_purges as repair


@pytest.mark.parametrize('apply', [False, True])
def test_rearm_requires_apply(monkeypatch, apply):
    candidate = ('owner', 'conversation', object())
    monkeypatch.setattr(repair, 'candidates', lambda *args: iter([candidate]))
    arm = Mock(return_value=True)
    monkeypatch.setattr(repair, 'rearm', arm)
    counts = {'rearmed': 0}
    repair.run(None, None, None, None, apply, 1, counts)
    assert counts['rearmed'] == int(apply)
    assert arm.call_count == int(apply)


def test_incomplete_scan_cannot_arm_partial_batch(monkeypatch):
    def incomplete(*args):
        yield 'owner', 'conversation', object()
        raise repair.Incomplete('request_budget_exhausted')

    arm = Mock()
    monkeypatch.setattr(repair, 'candidates', incomplete)
    monkeypatch.setattr(repair, 'rearm', arm)
    with pytest.raises(repair.Incomplete, match='request_budget_exhausted'):
        repair.run(None, None, None, None, True, 1, {})
    arm.assert_not_called()
