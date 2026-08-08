"""Review-queue and extractor schema tests (legacy consolidation stack removed in O-W6)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from database import review_queue
from tests.store_fakes import FakeDocumentStore
from utils.llm.memories import HighRecallMemories, Memories


def test_high_recall_short_term_extractor_schema_removes_legacy_cap():
    capped_schema = Memories.model_json_schema()['properties']['facts']
    high_recall_schema = HighRecallMemories.model_json_schema()['properties']['facts']

    assert capped_schema['maxItems'] == 2
    assert 'maxItems' not in high_recall_schema


def test_review_policy_blocks_pending_irreversible_actions():
    assert review_queue.can_use_for_action('accepted', 'irreversible') is True
    assert review_queue.can_use_for_action('pending_review', 'irreversible') is False
    assert review_queue.can_use_for_action('pending_review', 'answer') is True
    assert review_queue.permitted_uses('tombstoned') == set()


def test_review_economics_escalates_only_ambiguous_high_impact_conflicts():
    high_veracity_new = _fact('new', 'Lives in SF', arguments={'location': 'SF'}, veracity=0.9)
    weak_new = _fact('weak', 'Lives in SF', arguments={'location': 'SF'}, veracity=0.4)
    weak_new['qualifiers'] = {'importance': 0.8}
    low_impact = _fact('low', 'Lives in SF', arguments={'location': 'SF'}, veracity=0.4)
    low_impact['qualifiers'] = {'importance': 0.05}
    old = _fact('old', 'Lives in NYC', arguments={'location': 'NYC'}, veracity=0.9)

    assert review_queue.should_escalate_conflict(high_veracity_new, old) is False
    assert review_queue.should_escalate_conflict(low_impact, old) is False
    assert review_queue.should_escalate_conflict(weak_new, old) is True


def test_pending_timeout_resolves_by_evidence_not_fixed_outcome():
    assert review_queue.timeout_decision({'review_id': 'r1'}, current_veracity=0.8) == 'accept'
    assert review_queue.timeout_decision({'review_id': 'r1'}, current_veracity=0.5) == 'drop'


def test_review_resolution_mutations_and_correction_record(monkeypatch):
    monkeypatch.setattr(review_queue, '_store', lambda: FakeDocumentStore())
    item = {
        'review_id': 'review1',
        'fact_id': 'new',
        'candidate': _fact('new', 'Lives in SF', arguments={'location': 'SF'}, veracity=0.4),
        'conflict_with': ['old'],
    }

    accept = review_queue.resolution_mutations(item, 'accept')
    reject = review_queue.resolution_mutations(item, 'reject')
    correct = review_queue.resolution_mutations(
        item,
        'correct',
        correction={'target_fact_id': 'new', 'arg_changes': {'location': {'to': 'Oakland'}}},
    )
    record = review_queue.record_correction(
        'uid-1',
        item=item,
        decision='correct',
        prior_head_diff=[{'type': 'supersede_fact'}],
        final_correction={'location': 'Oakland'},
        reason='user corrected city',
    )

    assert [mutation['type'] for mutation in accept] == ['add_fact', 'supersede_fact']
    assert accept[0]['fact']['status'] == 'accepted'
    assert accept[0]['fact']['qualifiers']['epistemic_status'] == 'accepted'
    assert reject[0]['type'] == 'retract_fact'
    assert correct[0]['type'] == 'refine_fact'
    assert record['candidate']['id'] == 'new'
    assert record['prior_head_state'] == [{'type': 'supersede_fact'}]
    assert record['final_correction'] == {'location': 'Oakland'}


def test_review_queue_lists_pending_items_by_impact(monkeypatch):
    fake = FakeDocumentStore()
    base = 'users/uid-1/memory_review_queue'
    fake.set(f'{base}/low', {'status': 'pending', 'impact': 0.2})
    fake.set(f'{base}/done', {'status': 'accepted', 'impact': 1.0})
    fake.set(f'{base}/high', {'status': 'pending', 'impact': 0.8})
    monkeypatch.setattr(review_queue, '_store', lambda: fake)

    items = review_queue.list_review_conflicts('uid-1', limit=10)

    assert [item['review_id'] for item in items] == ['high', 'low']


def test_review_queue_resolve_accept_appends_commit_updates_queue_and_records_correction(monkeypatch):
    item = {
        'review_id': 'review1',
        'fact_id': 'new',
        'candidate': _fact('new', 'Lives in SF', arguments={'location': 'SF'}, veracity=0.4),
        'conflict_with': ['old'],
        'source_short_term_id': 'st-new',
        'status': 'pending',
    }
    fake = FakeDocumentStore()
    # The review-queue doc exists when resolve runs (get_review_conflict read it); seed it so the
    # projection update() targets an existing doc — update requires one on every backend.
    fake.set('users/uid-1/memory_review_queue/review1', item)
    merges = []
    corrections = []
    marked_short_term = []

    monkeypatch.setattr(review_queue, 'get_review_conflict', lambda uid, review_id: item)
    monkeypatch.setattr(review_queue, '_store', lambda: fake)
    monkeypatch.setattr(
        review_queue.memories_db,
        'merge_contradict_memory',
        lambda uid, new_memory, superseded_ids: merges.append((new_memory, superseded_ids))
        or {'commit': {'commit_id': 'commit-review'}},
    )
    monkeypatch.setattr(
        review_queue,
        'record_correction',
        lambda uid, **kwargs: corrections.append(kwargs) or {'correction_id': 'correction-review'},
    )
    monkeypatch.setattr(
        review_queue.short_term_db,
        'mark_consolidated',
        lambda uid, short_term_id, commit_id: marked_short_term.append((short_term_id, commit_id)),
    )

    result = review_queue.resolve_review_conflict('uid-1', 'review1', 'accept', reason='looks right')

    assert result['status'] == 'resolved'
    assert result['decision'] == 'accept'
    assert merges[0][0]['status'] == 'accepted'
    assert merges[0][0]['qualifiers']['epistemic_status'] == 'accepted'
    assert merges[0][1] == ['old']
    stored_update = fake._docs['users/uid-1/memory_review_queue/review1']
    assert stored_update['status'] == 'accepted'
    assert stored_update['resolution_commit_id'] == 'commit-review'
    assert corrections[0]['decision'] == 'accept'
    assert marked_short_term == [('st-new', 'commit-review')]


def test_canonical_review_resolution_uses_canonical_authority_and_redacts_projection(monkeypatch):
    item = {
        'review_id': 'review-canonical',
        'fact_id': 'mem-canonical',
        'candidate': {'id': 'mem-canonical', 'content': 'Private candidate text'},
        'conflict_with': ['mem-old'],
        'source_short_term_id': 'mem-canonical',
        'authority': 'canonical_memory',
        'status': 'pending',
    }
    docs: dict = {}

    resolved_item = {
        **item,
        'status': 'accepted',
        'decision': 'accept',
        'candidate': {'id': 'mem-canonical'},
        'permitted_uses': [],
        'resolution_commit_id': 'canonical-commit',
    }
    monkeypatch.setattr(review_queue, 'get_review_conflict', MagicMock(side_effect=[item, resolved_item]))
    monkeypatch.setattr(review_queue, '_store', lambda: FakeDocumentStore(backing=docs))
    canonical_commit = MagicMock(return_value={'commit': {'commit_id': 'canonical-commit'}})
    monkeypatch.setattr(review_queue, '_append_canonical_resolution_commit', canonical_commit)
    monkeypatch.setattr(
        review_queue,
        'append_resolution_commit',
        lambda *_args, **_kwargs: pytest.fail('canonical review wrote legacy memory authority'),
    )
    monkeypatch.setattr(
        review_queue,
        'record_correction',
        lambda *_args, **_kwargs: pytest.fail('canonical review retained a legacy correction record'),
    )
    monkeypatch.setattr(
        review_queue.short_term_db,
        'mark_consolidated',
        lambda *_args, **_kwargs: pytest.fail('canonical review touched the legacy short-term store'),
    )

    result = review_queue.resolve_review_conflict(
        'uid-1',
        'review-canonical',
        'accept',
        reason='confirmed',
    )

    canonical_commit.assert_called_once_with('uid-1', item, 'accept', None, 'confirmed')
    assert result['commit']['commit_id'] == 'canonical-commit'
    assert result['correction'] is None
    assert result['item']['candidate'] == {'id': 'mem-canonical'}
    # Canonical review routes through its sole mutation authority and never writes the legacy
    # review-doc projection through the neutral store.
    assert docs == {}


def test_review_queue_reject_uses_projection_writer(monkeypatch):
    item = {
        'review_id': 'review1',
        'fact_id': 'new',
        'candidate': _fact('new', 'Lives in SF', arguments={'location': 'SF'}, veracity=0.4),
        'conflict_with': ['old'],
        'source_short_term_id': 'st-new',
        'status': 'pending',
    }
    fake = FakeDocumentStore()
    # The review-queue doc exists when resolve runs; seed it so the projection update() has a target.
    fake.set('users/uid-1/memory_review_queue/review1', item)
    projection_updates = []
    marked_short_term = []

    class Snapshot:
        exists = True

    class Transaction:
        def get(self, path):
            return Snapshot()

        def update(self, ref, payload):
            projection_updates.append((ref, payload))

    monkeypatch.setattr(review_queue, 'get_review_conflict', lambda uid, review_id: item)
    monkeypatch.setattr(review_queue, '_store', lambda: fake)
    monkeypatch.setattr(review_queue, 'record_correction', lambda uid, **kwargs: {'correction_id': 'correction-review'})
    monkeypatch.setattr(
        review_queue.short_term_db,
        'mark_consolidated',
        lambda uid, short_term_id, commit_id: marked_short_term.append((short_term_id, commit_id)),
    )
    monkeypatch.setattr(
        review_queue,
        'persist_non_active_route_outcome',
        lambda outcome: outcome,
    )

    def fake_append_commit(uid, parent, mutations, **kwargs):
        kwargs['projection_writer'](Transaction())
        return {'commit': {'commit_id': 'commit-review'}}

    monkeypatch.setattr(review_queue.memory_ledger, 'append_commit', fake_append_commit)

    result = review_queue.resolve_review_conflict('uid-1', 'review1', 'reject')

    assert result['decision'] == 'reject'
    assert result['item']['status'] == 'rejected'
    assert projection_updates[0][1]['review_status'] == 'rejected'
    assert marked_short_term == [('st-new', 'commit-review')]


def test_review_queue_timeout_accepts_or_drops_by_current_evidence(monkeypatch):
    expired = datetime(2026, 6, 1, tzinfo=timezone.utc)
    items = [
        {'review_id': 'review-accept', 'fact_id': 'fact-accept', 'status': 'pending', 'expires_at': expired},
        {'review_id': 'review-drop', 'fact_id': 'fact-drop', 'status': 'pending', 'expires_at': expired},
    ]
    resolved = []

    monkeypatch.setattr(review_queue, 'list_review_conflicts', lambda uid, status, limit: items)
    monkeypatch.setattr(
        review_queue,
        'resolve_review_conflict',
        lambda uid, review_id, decision, **kwargs: resolved.append((review_id, kwargs['current_veracity']))
        or {'decision': review_queue.timeout_decision({}, kwargs['current_veracity'])},
    )

    result = review_queue.resolve_expired_review_conflicts(
        'uid-1',
        now=datetime(2026, 6, 2, tzinfo=timezone.utc),
        current_veracity_by_fact={'fact-accept': 0.8, 'fact-drop': 0.5},
    )

    assert [item['decision'] for item in result] == ['accept', 'drop']
    assert resolved == [('review-accept', 0.8), ('review-drop', 0.5)]


def _fact(
    fact_id,
    content,
    *,
    predicate='resides_in',
    arguments=None,
    subject_entity_id='user',
    veracity=0.8,
):
    return {
        'id': fact_id,
        'content': content,
        'predicate': predicate,
        'arguments': arguments or {},
        'subject_entity_id': subject_entity_id,
        'category': 'system',
        'veracity': veracity,
        'qualifiers': {},
    }
