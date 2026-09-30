"""EXP-004 cohorts and model-tier treatment, with synthetic identities only."""

import hashlib
import json
from unittest.mock import MagicMock

import pytest

from config import jev_decisions as config
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.relevance import Neighbor, decide_relevance, final_relevance
from utils.conversations.relevance_rules import RULES_VERSION


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in (
        'CONVERSATION_RELEVANCE_JEV_ENABLED',
        'CONVERSATION_RELEVANCE_JEV_PERCENT',
        'CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT',
        'CONVERSATION_RELEVANCE_JEV_UID_ALLOWLIST',
        'CONVERSATION_RELEVANCE_JEV_SHADOW_PERCENT',
        'MEMORY_OWNER_JEV_FLIP_ENABLED',
    ):
        monkeypatch.delenv(name, raising=False)


def test_bucket_is_stable_salted_and_in_range():
    expected = int.from_bytes(hashlib.sha256(b'relevance-arm-v1\0user').digest()[:8], 'big') / 2**64 * 100
    assert config.uid_bucket('user', 'relevance-arm-v1') == expected
    assert expected != config.uid_bucket('user', 'owner-shadow-v1')
    assert all(0 <= config.uid_bucket(str(i), 'salt') < 100 for i in range(500))


def test_disjoint_ranges_and_monotone_jev_ramp(monkeypatch):
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_ENABLED', 'true')
    monkeypatch.setenv('CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT', '2')
    previous = set()
    for percent in (1, 10, 50, 100):
        monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_PERCENT', str(percent))
        current = set()
        for i in range(500):
            uid = str(i)
            bucket = config.uid_bucket(uid, 'relevance-arm-v1')
            expected = 'keep_all' if bucket < 2 else 'jev' if bucket < min(100, 2 + percent) else 'nano'
            assert config.relevance_arm(uid) == expected
            if expected == 'jev':
                current.add(uid)
        assert previous <= current
        previous = current


def test_boundary_ranges_and_keep_all_window_shift(monkeypatch):
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_ENABLED', 'on')
    monkeypatch.setenv('CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT', '2')
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_PERCENT', '10')
    monkeypatch.setattr(config, 'uid_bucket', lambda uid, salt: float(uid))
    assert [config.relevance_arm(uid) for uid in ('0', '1.999', '2', '11.999', '12')] == [
        'keep_all',
        'keep_all',
        'jev',
        'jev',
        'nano',
    ]
    monkeypatch.setenv('CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT', '4')
    assert config.relevance_arm('2') == 'keep_all'
    assert config.relevance_arm('12') == 'jev'


@pytest.mark.parametrize('invalid', ['broken', '', '-1', '101', 'nan', 'inf'])
def test_invalid_percentages_fail_closed(monkeypatch, invalid):
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_ENABLED', 'true')
    for name in (
        'CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT',
        'CONVERSATION_RELEVANCE_JEV_PERCENT',
    ):
        monkeypatch.setenv(name, invalid)
    assert config.relevance_arm('user') == 'nano'


def test_invalid_percentage_blocks_the_allowlist_too(monkeypatch):
    """An allowlist must never rescue a malformed percentage (fail closed)."""
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_ENABLED', 'true')
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_UID_ALLOWLIST', 'user')
    for invalid in ('broken', '', '-1', '101', 'nan', 'inf'):
        monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_PERCENT', invalid)
        assert config.relevance_arm('user') == 'nano', invalid


def test_unset_percent_preserves_dev_and_allowlist_requires_flag(monkeypatch):
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_UID_ALLOWLIST', 'user')
    assert config.relevance_arm('user') == 'nano'
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_ENABLED', 'true')
    assert all(config.relevance_arm(str(i)) == 'jev' for i in range(50))
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_PERCENT', '0')
    assert config.relevance_arm('user') == 'jev'
    assert config.relevance_arm('other') == 'nano'
    monkeypatch.setenv('CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT', '100')
    assert config.relevance_arm('user') == 'keep_all'


def test_owner_flip_flag_is_universal_not_uid_sampled(monkeypatch):
    """INV-MEM-5: the live owner flip applies to every UID or none."""
    monkeypatch.setenv('MEMORY_OWNER_JEV_FLIP_ENABLED', 'true')
    assert config.memory_owner_jev_flip_enabled() is True
    monkeypatch.setenv('MEMORY_OWNER_JEV_FLIP_ENABLED', 'false')
    assert config.memory_owner_jev_flip_enabled() is False
    assert not hasattr(config, 'owner_flip_enabled_for')


def decision(**overrides):
    kwargs = dict(
        trigger=ProcessingTrigger.CAPTURE_END,
        texts=['Coming over there in a second.'],
        speech_seconds=2.0,
        has_photos=False,
        user_kept=False,
        exempt=False,
        trusted_wake_word=False,
        model_discards=MagicMock(return_value=True),
        calendar_retains=MagicMock(return_value=False),
        arm='nano',
    )
    kwargs.update(overrides)
    return decide_relevance(**kwargs)


def test_inactive_nano_record_is_byte_for_byte_unchanged():
    assert not config.relevance_experiment_active()
    actual = decision(record_arm=config.relevance_experiment_active()).as_record()
    expected = {
        'verdict': 'discard',
        'decided_by': 'model',
        'reason': 'model_discard',
        'trigger': 'capture_end',
        'rules_version': RULES_VERSION,
    }
    assert json.dumps(actual).encode() == json.dumps(expected).encode()


def test_keep_all_bypasses_both_models_and_neighbor_lookup():
    model, jev, neighbor = MagicMock(), MagicMock(), MagicMock()
    result = decision(arm='keep_all', model_discards=model, jev_discard_probability=jev, neighbor=neighbor)
    assert (result.verdict, result.decided_by, result.reason) == ('keep', 'policy', 'keep_all_arm')
    assert result.model_tier_reached and result.as_record()['arm'] == 'keep_all'
    for callback in (model, jev, neighbor):
        callback.assert_not_called()


@pytest.mark.parametrize(
    'overrides,reason',
    [
        ({'texts': ['Um.']}, 'filler_only'),
        ({'user_kept': True}, 'restored'),
        ({'trigger': ProcessingTrigger.FIRST_OPEN}, 'first_open'),
        ({'model_discards': None}, 'model_withheld'),
        ({'exempt': True}, 'exempt'),
    ],
)
def test_keep_all_does_not_override_earlier_tiers(overrides, reason):
    result = decision(arm='keep_all', **overrides)
    assert result.reason == reason
    assert not result.model_tier_reached and 'arm' not in result.as_record()


def test_active_model_records_have_arm_and_final_empty_title_retains_it():
    for arm in ('nano', 'jev', 'keep_all'):
        result = decision(arm=arm, record_arm=True, jev_discard_probability=lambda: 0.1)
        assert result.as_record()['arm'] == arm
        assert final_relevance(result, discarded=True).as_record()['arm'] == arm


def test_shadow_evidence_retains_raw_neighbor_discard_before_calendar_override():
    result = decision(
        record_arm=True, neighbor=lambda: Neighbor('kept-neighbor', 20, 'before'), calendar_retains=lambda: True
    )
    assert result.verdict == 'keep' and result.reason == 'calendar_overlap'
    assert result.nano_verdict == 'discard' and result.nano_reason == 'neighbor_fragment'


def test_bucket_rounding_never_admits_100(monkeypatch):
    digest = MagicMock()
    digest.digest.return_value = bytes([255]) * 32
    monkeypatch.setattr(config.hashlib, 'sha256', lambda _value: digest)
    assert config.uid_bucket('synthetic', 'salt') < 100
