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
        'OMI_ENV_STAGE',
        'CONVERSATION_RELEVANCE_JEV_ENABLED',
        'CONVERSATION_RELEVANCE_JEV_PERCENT',
        'CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT',
        'CONVERSATION_RELEVANCE_JEV_UID_ALLOWLIST',
        'CONVERSATION_RELEVANCE_JEV_SHADOW_PERCENT',
        'MEMORY_OWNER_JEV_FLIP_ENABLED',
        'MEMORY_OWNER_JEV_FLIP_PERCENT',
    ):
        monkeypatch.delenv(name, raising=False)


def test_bucket_is_stable_salted_and_in_range():
    expected = int.from_bytes(hashlib.sha256(b'relevance-arm-v2\0conversation').digest()[:8], 'big') / 2**64 * 100
    assert config.uid_bucket('conversation', 'relevance-arm-v2') == expected
    assert expected != config.uid_bucket('conversation', 'owner-shadow-v1')
    assert all(0 <= config.uid_bucket(str(i), 'salt') < 100 for i in range(500))


def test_same_uid_can_get_keep_all_and_nano_across_conversations(monkeypatch):
    monkeypatch.setenv('CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT', '2')
    selected = next(str(i) for i in range(1000) if config.keep_all_selected(f'conversation-{i}'))
    unselected = next(str(i) for i in range(1000) if not config.keep_all_selected(f'conversation-{i}'))
    assert config.relevance_arm('same-user', f'conversation-{selected}') == 'keep_all'
    assert config.relevance_arm('same-user', f'conversation-{unselected}') == 'nano'


def test_keep_all_selection_is_stable_per_conversation_id(monkeypatch):
    monkeypatch.setenv('CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT', '2')
    conversation_id = 'synthetic-conversation'
    expected = config.keep_all_selected(conversation_id)
    assert all(config.keep_all_selected(conversation_id) is expected for _ in range(20))


def test_keep_all_selection_is_approximately_configured_percentage(monkeypatch):
    monkeypatch.setenv('CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT', '2')
    selected = sum(config.keep_all_selected(f'conversation-{i}') for i in range(10_000))
    # Expected 200, sd ~14: bounds are ~5 sd, and the loop stays inside the fast-unit CPU guard.
    assert 120 <= selected <= 280


@pytest.mark.parametrize('invalid', ['broken', '', '-1', '101', 'nan', 'inf'])
def test_invalid_keep_all_percentage_never_selects(invalid, monkeypatch):
    monkeypatch.setenv('CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT', invalid)
    assert all(not config.keep_all_selected(f'conversation-{i}') for i in range(500))


def test_zero_keep_all_percentage_never_selects(monkeypatch):
    monkeypatch.setenv('CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT', '0')
    assert all(not config.keep_all_selected(f'conversation-{i}') for i in range(500))


def test_conversation_keep_all_precedes_jev_conversation_window(monkeypatch):
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_ENABLED', 'true')
    monkeypatch.setenv('CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT', '2')
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_PERCENT', '10')
    buckets = {
        ('sampled', 'relevance-keepall-v1'): 1.0,
        ('before-jev', 'relevance-keepall-v1'): 50.0,
        ('jev', 'relevance-keepall-v1'): 50.0,
        ('after-jev', 'relevance-keepall-v1'): 50.0,
        ('before-jev', 'relevance-arm-v2'): 1.0,
        ('jev', 'relevance-arm-v2'): 2.0,
        ('after-jev', 'relevance-arm-v2'): 12.0,
    }
    monkeypatch.setattr(config, 'uid_bucket', lambda value, salt: buckets[(value, salt)])
    assert config.relevance_arm('same-user', 'sampled') == 'keep_all'
    assert config.relevance_arm('same-user', 'before-jev') == 'nano'
    assert config.relevance_arm('same-user', 'jev') == 'jev'
    assert config.relevance_arm('same-user', 'after-jev') == 'nano'


@pytest.mark.parametrize('invalid', ['broken', '', '-1', '101', 'nan', 'inf'])
@pytest.mark.parametrize('invalid_controls', ['keep_all', 'jev', 'both'])
@pytest.mark.parametrize('enabled', ['true', 'false'])
def test_invalid_percentages_fail_closed(monkeypatch, invalid, invalid_controls, enabled):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_ENABLED', enabled)
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_UID_ALLOWLIST', 'user')
    monkeypatch.setenv('CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT', '0' if invalid_controls == 'jev' else invalid)
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_PERCENT', invalid if invalid_controls != 'keep_all' else '100')
    uids = ['user', *(str(i) for i in range(100))]
    assert all(config.relevance_arm(uid, str(i)) == 'nano' for i, uid in enumerate(uids))


@pytest.mark.parametrize('percent', ['0', '1', '50', '99.9', 'broken', '', '-1', '101', 'nan', 'inf'])
def test_owner_flip_percentage_is_a_universal_fail_closed_control(monkeypatch, percent):
    monkeypatch.setenv('MEMORY_OWNER_JEV_FLIP_ENABLED', 'true')
    monkeypatch.setenv('MEMORY_OWNER_JEV_FLIP_PERCENT', percent)
    assert config.memory_owner_jev_flip_enabled() is False


def test_owner_flip_100_still_requires_the_flag(monkeypatch):
    monkeypatch.setenv('MEMORY_OWNER_JEV_FLIP_PERCENT', '100')
    assert config.memory_owner_jev_flip_enabled() is False
    monkeypatch.setenv('MEMORY_OWNER_JEV_FLIP_ENABLED', 'true')
    assert config.memory_owner_jev_flip_enabled() is True


def test_unset_percent_preserves_dev_and_allowlist_requires_flag(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_UID_ALLOWLIST', 'user')
    assert config.relevance_arm('user', 'conversation') == 'nano'
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_ENABLED', 'true')
    assert all(config.relevance_arm(str(i), f'conversation-{i}') == 'jev' for i in range(50))
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_PERCENT', '0')
    assert config.relevance_arm('user', 'conversation') == 'jev'
    assert config.relevance_arm('other', 'conversation') == 'nano'
    monkeypatch.setenv('CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT', '100')
    assert config.relevance_arm('user', 'conversation') == 'keep_all'


def test_owner_flip_flag_is_universal_not_uid_sampled(monkeypatch):
    """INV-MEM-5: the live owner flip applies to every UID or none."""
    monkeypatch.setenv('MEMORY_OWNER_JEV_FLIP_ENABLED', 'true')
    assert config.memory_owner_jev_flip_enabled() is True
    monkeypatch.setenv('MEMORY_OWNER_JEV_FLIP_ENABLED', 'false')
    assert config.memory_owner_jev_flip_enabled() is False
    assert not hasattr(config, 'owner_flip_enabled_for')


def test_jev_ramp_is_monotone_and_no_account_is_pinned(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_ENABLED', 'true')
    monkeypatch.setenv('CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT', '2')
    conversations = [f'conversation-{i}' for i in range(1500)]
    previous = set()
    keep_all = {cid for cid in conversations if config.keep_all_selected(cid)}
    for percent in ('1', '10', '50', '100'):
        monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_PERCENT', percent)
        arms = {cid: config.relevance_arm('same-user', cid) for cid in conversations}
        selected = {cid for cid, arm in arms.items() if arm == 'jev'}
        assert previous < selected
        assert keep_all == {cid for cid, arm in arms.items() if arm == 'keep_all'}
        assert selected.isdisjoint(keep_all)
        assert set(arms.values()) == {'nano', 'jev', 'keep_all'}
        for uid in ('another-user', 'third-user', 'same-user'):
            assert {cid: config.relevance_arm(uid, cid) for cid in conversations} == arms
        previous = selected
    # K and J use different salts: at J=100, the [0,K) gap still uses nano.
    assert all(
        config.relevance_arm('same-user', cid) == 'nano'
        for cid in conversations
        if cid not in keep_all and config.uid_bucket(cid, 'relevance-arm-v2') < 2
    )


@pytest.mark.parametrize('stage', ['prod', 'local', 'offline', '', None])
def test_allowlist_is_never_read_outside_dev(monkeypatch, stage):
    if stage is not None:
        monkeypatch.setenv('OMI_ENV_STAGE', stage)
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_ENABLED', 'true')
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_PERCENT', '0')
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_UID_ALLOWLIST', 'user')
    getenv = config.os.getenv

    def forbid_allowlist(name, default=None):
        assert name != 'CONVERSATION_RELEVANCE_JEV_UID_ALLOWLIST'
        return getenv(name, default)

    monkeypatch.setattr(config.os, 'getenv', forbid_allowlist)
    assert config.relevance_arm('user', 'conversation') == 'nano'


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


def test_keep_all_keeps_and_never_calls_jev_but_records_the_nano_counterfactual():
    jev = MagicMock()
    for nano_discards, verdict, reason in ((True, 'discard', 'model_discard'), (False, 'keep', 'model_keep')):
        result = decision(
            arm='keep_all',
            model_discards=lambda on_error, adjacent, d=nano_discards: d,
            jev_discard_probability=jev,
        )
        assert (result.verdict, result.decided_by, result.reason) == ('keep', 'policy', 'keep_all_arm')
        assert result.model_tier_reached and result.as_record()['arm'] == 'keep_all'
        assert (result.nano_verdict, result.nano_reason) == (verdict, reason)
    jev.assert_not_called()


def test_keep_all_records_neighbor_fragment_counterfactual_and_keeps():
    result = decision(
        arm='keep_all',
        model_discards=lambda on_error, adjacent: True,
        neighbor=lambda: Neighbor('kept-neighbor', 20, 'before'),
    )
    assert result.verdict == 'keep' and result.reason == 'keep_all_arm'
    assert (result.nano_verdict, result.nano_reason) == ('discard', 'neighbor_fragment')


def test_keep_all_nano_failure_still_keeps_with_no_counterfactual():
    def failing(on_error, adjacent):
        on_error(RuntimeError('nano down'))
        return False

    result = decision(arm='keep_all', model_discards=failing)
    assert result.verdict == 'keep' and result.reason == 'keep_all_arm'
    assert result.nano_verdict is None and result.nano_reason is None


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
