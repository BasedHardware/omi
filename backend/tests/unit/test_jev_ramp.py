"""The relevance percentage is the sole Jev cohort control."""

import hashlib

import pytest

from config import jev_decisions as config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv('CONVERSATION_RELEVANCE_JEV_PERCENT', raising=False)


def test_unset_percentage_keeps_jev_off_and_zero_canary_is_recordable(monkeypatch):
    assert config.relevance_arm('conversation') == 'nano'
    assert config.relevance_experiment_active() is False
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_PERCENT', '0')
    assert config.relevance_arm('conversation') == 'nano'
    assert config.relevance_experiment_active() is True


def test_percentage_selects_stable_conversation_cohort(monkeypatch):
    conversation_id = 'synthetic-conversation'
    digest = hashlib.sha256(b'relevance-arm-v2\0synthetic-conversation').digest()
    expected_bucket = min(int.from_bytes(digest[:8], 'big') / 2**64 * 100, 99.99999999999999)
    assert config.uid_bucket(conversation_id, 'relevance-arm-v2') == expected_bucket
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_PERCENT', '100')
    assert all(config.relevance_arm(conversation_id) == 'jev' for _ in range(20))
    assert all(config.relevance_arm(str(i)) == 'jev' for i in range(100))
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_PERCENT', '0')
    assert all(config.relevance_arm(str(i)) == 'nano' for i in range(100))


def test_percentage_ramp_is_monotone_and_approximately_sized(monkeypatch):
    conversations = [f'conversation-{i}' for i in range(10_000)]
    previous = set()
    for percent in ('1', '10', '50', '100'):
        monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_PERCENT', percent)
        selected = {cid for cid in conversations if config.relevance_arm(cid) == 'jev'}
        assert previous < selected
        if percent == '10':
            assert 850 <= len(selected) <= 1150
        previous = selected


@pytest.mark.parametrize('invalid', ['broken', '', '-1', '101', 'nan', 'inf'])
def test_invalid_percentage_fails_closed(invalid, monkeypatch):
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_PERCENT', invalid)
    assert all(config.relevance_arm(f'conversation-{i}') == 'nano' for i in range(500))
