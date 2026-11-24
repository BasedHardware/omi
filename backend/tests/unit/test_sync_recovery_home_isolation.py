"""Receipt clocks cannot become Home episode or temporal duplicate evidence."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.unit.test_episode_live_integrity import lane, row, T0
from utils.episodes import service, sync_attach
from utils.conversations import duplicate_capture


@pytest.mark.parametrize('entry', ['intake', 'finalize', 'canonical'])
def test_untrusted_recovery_never_attaches_by_time_or_canonical_group(lane, monkeypatch, entry):
    store, c, _ = lane
    service.attach_conversation('u', 'live', 'omi', started_at=T0, collaborators=c)
    recovered = row('receipt-source', capture_time_trust='untrusted')
    store.rows['users', 'u', 'conversations', 'receipt-source'] = recovered
    monkeypatch.setattr(service.client_gate, 'client_seen_cached', lambda _: True)
    canonical = Mock(side_effect=lambda uid, cid, *a, **kw: row('live') if cid == 'receipt-source' else None)
    monkeypatch.setattr(sync_attach.episode_groups, 'canonical_row', canonical)
    before = deepcopy(store.rows)
    if entry == 'intake':
        outcome = service.attach_synced_intake('u', 'receipt-source', recovered, collaborators=c)
    elif entry == 'finalize':
        outcome = service.on_conversation_finalized(
            'u', 'receipt-source', recovered, trigger='sync_update', collaborators=c
        )
    else:
        outcome = service._attach_synced('u', 'receipt-source', recovered, c)
    assert outcome == 'skipped_unknown_date'
    assert store.rows == before
    canonical.assert_not_called()


@pytest.mark.parametrize('model', [False, True])
def test_untrusted_span_never_proposes_a_time_duplicate(model, monkeypatch):
    record = row('receipt-source', capture_time_trust='untrusted')
    candidate = SimpleNamespace(**record) if model else record
    assert duplicate_capture.capture_record(candidate, 'u') is None
    query = Mock()
    monkeypatch.setattr(duplicate_capture.conversations_db, 'get_conversations_finished_after', query)
    duplicate_capture.link_duplicate_captures('u', candidate)
    query.assert_not_called()
