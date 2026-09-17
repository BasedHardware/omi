"""Explicit history widens lifecycle visibility, never account access fences."""

from datetime import datetime, timezone

import pytest

from models.product_memory import (
    MemoryAccessPolicy,
    MemoryConsumer,
    MemoryItemStatus,
    RESTRICTED_SENSITIVITY_LABELS,
)
from utils.memory.ledger_history_policy import is_temporal_history_access_eligible
from tests.unit.fixtures.canonical_memory_fakes import _fresh_short_term_item

NOW = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)


@pytest.fixture(scope='module')
def adapter():
    from utils.memory import canonical_memory_adapter

    return canonical_memory_adapter


def history_item(superseded=False):
    item = _fresh_short_term_item(
        uid='owner', memory_id='retained', conversation_id='conversation', content='Old location'
    )
    return item.model_copy(
        update={
            'status': MemoryItemStatus.superseded if superseded else MemoryItemStatus.active,
            'superseded_by': 'newer' if superseded else None,
            'arguments': {} if superseded else {'memory_use': {'suppressed': True}},
        }
    )


@pytest.mark.parametrize('superseded', [False, True])
def test_retained_history_access_does_not_change_the_canonical_item(adapter, superseded):
    item = history_item(superseded)
    before = item.model_dump(mode='json')
    policy = MemoryAccessPolicy.for_omi_chat(archive_capability=False)
    assert is_temporal_history_access_eligible(item, policy, now=NOW)
    assert adapter._canonical_scan_item_visible(
        item,
        policy=policy,
        now=NOW,
        include_pending_processing=False,
        include_archive=False,
        device_scope='all',
        client_device_id=None,
        view='history',
    )
    assert item.model_dump(mode='json') == before


def test_negative_truth_review_remains_owner_inspectable_history(adapter):
    item = history_item().model_copy(update={'arguments': {}, 'promotion': {'reviewed': True, 'user_review': False}})
    policy = MemoryAccessPolicy.for_omi_chat(archive_capability=False)
    assert is_temporal_history_access_eligible(item, policy, now=NOW)
    assert adapter._canonical_scan_item_visible(
        item,
        policy=policy,
        now=NOW,
        include_pending_processing=False,
        include_archive=False,
        device_scope='all',
        client_device_id=None,
        view='history',
    )


@pytest.mark.parametrize('superseded', [False, True])
@pytest.mark.parametrize('denial', ['restricted', 'visibility', 'missing_grant', 'unknown_consumer', 'locked'])
def test_suppression_or_supersession_cannot_bypass_history_access(adapter, superseded, denial):
    item = history_item(superseded)
    policy = MemoryAccessPolicy.for_omi_chat(archive_capability=False)
    if denial == 'restricted':
        item = item.model_copy(update={'sensitivity_labels': [next(iter(RESTRICTED_SENSITIVITY_LABELS))]})
    elif denial == 'visibility':
        item = item.model_copy(update={'visibility': 'unrecognized'})
    elif denial == 'missing_grant':
        policy = MemoryAccessPolicy(consumer=MemoryConsumer.third_party, app_has_default_memory_grant=False)
    elif denial == 'unknown_consumer':
        policy = MemoryAccessPolicy(consumer=MemoryConsumer.unknown)
    elif denial == 'locked':
        item = item.model_copy(update={'promotion': {'is_locked': True}})
    assert not adapter._canonical_scan_item_visible(
        item,
        policy=policy,
        now=NOW,
        include_pending_processing=False,
        include_archive=False,
        device_scope='all',
        client_device_id=None,
        view='history',
    )
