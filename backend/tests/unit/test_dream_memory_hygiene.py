"""Full-owner memory hygiene through canonical commits and the real Review seam."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import json

import pytest
from pydantic import ValidationError

from config.dream_agent import Caps, auto_apply_kinds
from database import memory_apply_store, review_changes, review_store
from database.memory_collections import MemoryCollections
from models.dream_agent import Plan, FullPlan
from models.dream_edit import Edit, FullEdit, MemoryHygieneEdit
from models.memory_apply import MemoryControlState, WriterMode, memory_content_hash
from models.product_memory import MemoryItem
from models.review import AgentProposalItem
from tests.unit.test_dream_rung2 import store, run, UID, REF, REAL_DEMOTED_TYPES
from utils import dream_agent, dream_reads, dream_tools, dream_metrics
from utils.dream_consensus import majority, unanimous_memory_hygiene
from utils.dream_context import EvidenceRecords
from utils.dream_decisions import edit_decisions
from utils.dream_prompt import fits_full

NOW = datetime(2026, 1, 10, tzinfo=timezone.utc)
MREF = 'memory_items/old'
NREF = 'memory_items/new'


def memory(key, content, when=NOW):
    return MemoryItem(
        memory_id=key,
        uid=UID,
        version=3,
        item_revision=4,
        ledger_commit_id='synthetic-prior',
        ledger_sequence=1,
        tier='long_term',
        status='active',
        processing_state='processed',
        content=content,
        content_hash=memory_content_hash(content=content, evidence_ids=[]),
        source_state='active',
        sensitivity_labels=[],
        visibility='private',
        user_asserted=True,
        captured_at=when,
        updated_at=when,
        valid_from=when,
        ledger_schema_version='knowledge_ledger.v1',
        kind='fact',
        subject_scope='primary_user',
        slot='location',
        curation_weight=2,
        write_reason='agent_reusable_conclusion',
        intent_backed=True,
    ).model_dump(mode='json') | {'captured_at': when, 'updated_at': when, 'valid_from': when}


def edit(kind='retire_memory', **kw):
    return FullEdit.model_validate(
        {'kind': kind, 'target': MREF, 'reason': 'Synthetic contradictory fact', 'evidence': [REF], 'value': 5, **kw}
    )


@pytest.fixture
def hygiene(store, monkeypatch):
    monkeypatch.setenv('MEMORY_ENABLED', 'on')
    monkeypatch.setattr(memory_apply_store, '_firestore_transactional', lambda fn: fn)
    store.rows[('users', UID, 'memory_state', 'apply_control')] = MemoryControlState(
        uid=UID, writer_mode=WriterMode.ledger, head_commit_id='genesis', account_generation=0, source_generation=0
    ).model_dump(mode='json')
    store.rows[('users', UID, 'memory_items', 'old')] = memory('old', 'Lives in Toytown.')
    store.rows[('users', UID, 'memory_items', 'new')] = memory(
        'new', 'Since January, lives in New Toytown.', NOW + timedelta(days=1)
    )
    original = dream_agent.dream_reads.read_changes

    def records(*args, **kw):
        evidence, consumed = original(*args, **kw)
        evidence.update(
            {
                MREF: deepcopy(store.rows[('users', UID, 'memory_items', 'old')]),
                NREF: deepcopy(store.rows[('users', UID, 'memory_items', 'new')]),
            }
        )
        evidence.context_mode = 'full'
        return evidence, consumed

    monkeypatch.setattr(dream_agent.dream_reads, 'read_changes', records)
    monkeypatch.setattr(dream_tools, 'proposal_record', lambda uid, ref, snapshot: records()[0][ref])
    return store, records


@pytest.mark.parametrize(
    'operation',
    [
        edit(),
        edit('supersede_memory', other=NREF),
        edit('supersede_memory', after='Since January, lives in New Toytown.'),
    ],
)
def test_apply_undo_redo_exactness(hygiene, operation):
    db, records = hygiene
    db.rows[('users', UID, 'memory_items', 'old')]['future_metadata'] = {'synthetic': True}
    db.rows[('users', UID, 'memory_items', 'old')].pop('belief_class')
    before = deepcopy(db.rows[('users', UID, 'memory_items', 'old')])
    newer = deepcopy(db.rows[('users', UID, 'memory_items', 'new')])
    report = run([FullPlan(edits=[operation])] * 3)
    assert report['outcomes'][0]['status'] == 'applied'
    assert db.rows[('users', UID, 'memory_items', 'old')]['status'] == 'superseded'
    assert db.rows[('users', UID, 'memory_items', 'old')]['future_metadata'] == {'synthetic': True}
    assert 'belief_class' not in db.rows[('users', UID, 'memory_items', 'old')]
    assert db.rows[('users', UID, 'memory_items', 'new')] == newer
    changes = [row for path, row in db.rows.items() if path[-2] == 'review_changes']
    assert set(changes[0]['memory_hygiene']) == {'review_encrypted_v1'}
    assert 'Toytown' not in json.dumps(changes[0], default=str)
    data = review_store.decode_doc(UID, changes[0])
    change_id = data['change']['change_id']
    after = deepcopy(db.rows[('users', UID, 'memory_items', 'old')])
    assert review_changes.set_undone(UID, change_id, True).undone
    restored = db.rows[('users', UID, 'memory_items', 'old')]

    def sans_stamps(row):
        return {key: value for key, value in row.items() if key not in {'ledger_commit_id', 'ledger_sequence'}}

    # Undo restores every prior field, but the restored row must carry the
    # reversal commit: its outbox events are stamped with that commit and
    # vector hydration rejects rows whose stamp differs from the projection.
    assert sans_stamps(restored) == sans_stamps(before)
    assert restored['ledger_commit_id'] != after['ledger_commit_id']
    journal_doc = review_store.decode_doc(
        UID, next(row for path, row in db.rows.items() if path[-2] == 'review_changes')
    )
    assert journal_doc
    journal = journal_doc['memory_hygiene']
    assert restored['ledger_commit_id'] == journal['undone_rows']['old']['ledger_commit_id']
    assert db.rows[('users', UID, 'memory_items', 'new')] == newer
    assert not review_changes.agent_change_allowed(UID, dream_tools.edit_key(operation, records()[0]))
    if operation.after:
        tails = [row for path, row in db.rows.items() if path[-2] == 'memory_items' and path[-1] not in {'old', 'new'}]
        assert len(tails) == 1 and tails[0]['status'] == 'superseded'
    assert not review_changes.set_undone(UID, change_id, False).undone
    redone = db.rows[('users', UID, 'memory_items', 'old')]
    assert sans_stamps(redone) == sans_stamps(after)
    assert redone['ledger_commit_id'] not in {after['ledger_commit_id'], restored['ledger_commit_id']}
    assert len([path for path in db.rows if path[-2] == 'memory_commits']) == 3
    events = [row for path, row in db.rows.items() if path[-2] == 'memory_outbox']
    assert {row['payload']['action'] for row in events} == {'upsert', 'delete'}


@pytest.mark.parametrize(
    'kind,kw',
    [
        ('retire_memory', {}),
        ('supersede_memory', {'other': NREF}),
        ('merge_memories', {'other': NREF, 'after': 'Since January, lives in New Toytown.'}),
    ],
)
def test_majority_offers_value_ranked_review(hygiene, kind, kw):
    db, _ = hygiene
    operation = edit(kind, **kw)
    report = run([FullPlan(edits=[operation]), FullPlan(edits=[operation]), FullPlan()])
    assert report['outcomes'][0]['status'] == 'suggested'
    assert report['questions_offered'] == 1 and report['suggested_majority'] == 1
    assert db.rows[('users', UID, 'memory_items', 'old')]['status'] == 'active'
    assert len([path for path in db.rows if path[-2] == 'review_proposals']) == 1


def test_demoted_unanimous_and_low_value(hygiene, monkeypatch):
    monkeypatch.setattr(dream_agent.dream_store, 'demoted_types', lambda *a: {'retire_memory'})
    report = run([FullPlan(edits=[edit()])] * 3)
    assert report['outcomes'][0]['status'] == 'suggested'
    assert report['auto_applied_unanimous'] == 0
    low = edit().model_copy(update={'value': 2})
    report = run([FullPlan(edits=[low]), FullPlan(edits=[low]), FullPlan()])
    assert report['questions_offered'] == 0
    assert report['questions_dropped_low_value'] == 1


def test_consensus_other_ref_and_single_sample():
    one, two = edit('supersede_memory', other=NREF), edit('supersede_memory', other='memory_items/different')
    assert majority([FullPlan(edits=[one]), FullPlan(edits=[two]), FullPlan()]).edits == []
    survivor = majority([FullPlan(edits=[one])]).edits[0]
    assert not unanimous_memory_hygiene(survivor)


def test_nonallowlisted_and_bounded_cannot_auto_apply(hygiene, monkeypatch):
    _, records = hygiene
    assert {'merge_memories', 'retire_memory', 'supersede_memory'} <= auto_apply_kinds(UID)
    assert not {'merge_memories', 'retire_memory', 'supersede_memory'} & auto_apply_kinds('synthetic-outsider')
    operation = majority([FullPlan(edits=[edit()])] * 3).edits[0]
    with pytest.raises(ValueError):
        dream_tools.apply_unanimous_edit('synthetic-outsider', operation, records()[0])
    bounded = EvidenceRecords(records()[0])
    bounded.context_mode = 'bounded'
    with pytest.raises(ValueError):
        dream_tools.validate_edit(operation, bounded)
    _, policies = edit_decisions(FullPlan(edits=[operation]), records()[0], [], auto_apply_kinds(UID), set(), False, {})
    assert set(policies.values()) == {'suggest'}
    assert Plan.model_json_schema()['$defs']['Edit']['properties']['kind']['enum'] == [
        'spelling',
        'title',
        'overview',
        'memory',
        'merge_people',
        'entity_summary',
        'close_task',
        'retire_task',
        'merge_memories',
    ]


@pytest.mark.parametrize(
    'kw',
    [
        dict(kind='retire_memory', after='Text'),
        dict(kind='retire_memory', other=NREF),
        dict(kind='supersede_memory'),
        dict(kind='supersede_memory', other=NREF, after='Text'),
        dict(kind='retire_memory', reason='   '),
        dict(kind='retire_memory', evidence=[]),
    ],
)
def test_schema_rejects_invalid_hygiene(kw):
    with pytest.raises(ValidationError):
        edit(
            **{key: value for key, value in kw.items() if key == 'kind'},
            **{key: value for key, value in kw.items() if key != 'kind'}
        )


def test_user_authored_facts_require_review_not_auto_apply(hygiene):
    """A unanimous pass may still not silently close a user-authored fact."""
    db, _ = hygiene
    db.rows[('users', UID, 'memory_items', 'old')]['write_reason'] = 'direct_user_statement'
    operation = edit()
    report = run([FullPlan(edits=[operation])] * 3)
    assert report['outcomes'][0]['status'] == 'suggested'
    assert db.rows[('users', UID, 'memory_items', 'old')]['status'] == 'active'
    assert len([path for path in db.rows if path[-2] == 'review_proposals']) == 1
    # A user-accepted proposal still applies: Review is the authority seam.
    proposal = review_store.decode_doc(
        UID, next(row for path, row in db.rows.items() if path[-2] == 'review_proposals')
    )
    from models.review import AgentProposalItem

    answer = dream_tools.answer_proposal(
        UID, AgentProposalItem.model_validate(proposal['item']['agent_proposal']), proposal['source'], 'accept'
    )
    assert answer and db.rows[('users', UID, 'memory_items', 'old')]['status'] == 'superseded'


def test_whitespace_after_with_other_uses_existing_fact(hygiene):
    """Whitespace-only `after` must behave like an absent replacement."""
    db, _ = hygiene
    operation = edit('supersede_memory', other=NREF, after='   ')
    report = run([FullPlan(edits=[operation])] * 3)
    assert report['outcomes'][0]['status'] == 'applied'
    assert db.rows[('users', UID, 'memory_items', 'old')]['superseded_by'] == 'new'
    tails = [row for path, row in db.rows.items() if path[-2] == 'memory_items' and path[-1] not in {'old', 'new'}]
    assert tails == []


def test_short_term_replacement_tail_gets_fresh_expiry(hygiene):
    """A new tail from an expired short-term fact must remain valid."""
    db, _ = hygiene
    stale = NOW - timedelta(days=4)
    db.rows[('users', UID, 'memory_items', 'old')]['tier'] = 'short_term'
    db.rows[('users', UID, 'memory_items', 'old')]['captured_at'] = stale
    db.rows[('users', UID, 'memory_items', 'old')]['updated_at'] = stale
    db.rows[('users', UID, 'memory_items', 'old')]['valid_from'] = stale
    db.rows[('users', UID, 'memory_items', 'old')]['expires_at'] = stale + timedelta(hours=48)
    operation = edit('supersede_memory', after='Since January, lives in New Toytown.')
    report = run([FullPlan(edits=[operation])] * 3)
    assert report['outcomes'][0]['status'] == 'applied'
    tail = next(row for path, row in db.rows.items() if path[-2] == 'memory_items' and path[-1] not in {'old', 'new'})
    assert tail['tier'] == 'short_term'
    assert tail['expires_at'] > tail['captured_at']


def test_undo_conflicts_with_later_edit(hygiene):
    db, _ = hygiene
    run([FullPlan(edits=[edit()])] * 3)
    data = review_store.decode_doc(UID, next(row for path, row in db.rows.items() if path[-2] == 'review_changes'))
    db.rows[('users', UID, 'memory_items', 'old')]['content'] = 'A later synthetic correction.'
    with pytest.raises(review_store.ReviewConflict):
        review_changes.set_undone(UID, data['change']['change_id'], True)


def tail_row(db):
    return next(row for path, row in db.rows.items() if path[-2] == 'memory_items' and path[-1] not in {'old', 'new'})


def decoded(db, collection):
    data = review_store.decode_doc(UID, next(row for path, row in db.rows.items() if path[-2] == collection))
    assert data
    return data


def test_replacement_binds_every_cited_conversation_as_source(hygiene):
    """The new active fact must join each cited conversation's source cohort."""
    db, _ = hygiene
    operation = edit('supersede_memory', after='Since January, lives in New Toytown.')
    report = run([FullPlan(edits=[operation])] * 3)
    assert report['outcomes'][0]['status'] == 'applied'
    item = MemoryItem.model_validate(tail_row(db))
    # Canonical evidence carries the bare conversation id: source-cohort
    # discovery probes source_ids with array_contains on the raw id.
    assert 'toy' in item.source_ids
    evidence_rows = [row for path, row in db.rows.items() if path[-2] == 'memory_evidence']
    assert len(evidence_rows) == 1
    assert evidence_rows[0]['conversation_id'] == 'toy'


def test_secret_shaped_replacement_content_is_restricted(hygiene):
    """Free-form replacements never inherit unrestricted labels blindly."""
    db, _ = hygiene
    operation = edit('supersede_memory', after='Leaked key sk-ABCDEFGHIJKLMNOPQRSTUVWX in the transcript.')
    report = run([FullPlan(edits=[operation])] * 3)
    assert report['outcomes'][0]['status'] == 'applied'
    assert 'credential' in tail_row(db)['sensitivity_labels']


def test_background_tail_uses_reconciliation_reason_review_accept_does_not(hygiene):
    db, _ = hygiene
    operation = edit('supersede_memory', after='Since January, lives in New Toytown.')
    report = run([FullPlan(edits=[operation])] * 3)
    assert report['outcomes'][0]['status'] == 'applied'
    # The scheduled effect loop (dream_writing set) is the reconciliation
    # channel; its conclusions must not outrank the sweep's later corrections.
    assert tail_row(db)['write_reason'] == 'daily_reconciliation'
    # A user-accepted Review proposal applies outside the effect loop and
    # keeps the request-serving agent-conclusion reason.
    db.rows[('users', UID, 'memory_items', 'new')]['write_reason'] = 'direct_user_statement'
    accepted = edit('supersede_memory', target=NREF, after='Now lives in Futurtown for good.')
    report = run([FullPlan(edits=[accepted])] * 3)
    assert report['outcomes'][0]['status'] == 'suggested'
    proposal = decoded(db, 'review_proposals')
    from models.review import AgentProposalItem as Wire

    assert dream_tools.answer_proposal(
        UID, Wire.model_validate(proposal['item']['agent_proposal']), proposal['source'], 'accept'
    )
    tails = [row for path, row in db.rows.items() if path[-2] == 'memory_items' and path[-1] not in {'old', 'new'}]
    assert tails[-1]['write_reason'] == 'agent_reusable_conclusion'


def test_hygiene_proposal_carries_full_fact_contents(hygiene):
    db, _ = hygiene
    db.rows[('users', UID, 'memory_items', 'old')]['write_reason'] = 'direct_user_statement'
    run([FullPlan(edits=[edit('supersede_memory', other=NREF)])] * 3)
    wire = decoded(db, 'review_proposals')['item']['agent_proposal']
    assert wire['target_content'] == 'Lives in Toytown.'
    assert wire['other_content'] == 'Since January, lives in New Toytown.'


def test_replacement_effective_time_comes_from_evidence(hygiene):
    from utils.dream_guards import timestamp

    db, _ = hygiene
    since = (NOW - timedelta(days=3)).isoformat()
    operation = edit('supersede_memory', after='Since January, lives in New Toytown.', effective_from=since)
    report = run([FullPlan(edits=[operation])] * 3)
    assert report['outcomes'][0]['status'] == 'applied'
    tail = tail_row(db)
    valid_from, expected = timestamp(tail['valid_from']), timestamp(since)
    assert valid_from is not None and valid_from == expected
    closed_at = timestamp(db.rows[('users', UID, 'memory_items', 'old')]['valid_to'])
    assert closed_at is not None and closed_at > valid_from


def test_future_effective_time_falls_back_to_apply_time(hygiene):
    from utils.dream_guards import timestamp

    db, _ = hygiene
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    operation = edit('supersede_memory', after='Will move to Futurtown.', effective_from=future)
    report = run([FullPlan(edits=[operation])] * 3)
    assert report['outcomes'][0]['status'] == 'applied'
    valid_from, future_at = timestamp(tail_row(db)['valid_from']), timestamp(future)
    assert valid_from is not None and future_at is not None and valid_from < future_at


def test_context_includes_active_memories_within_budget(monkeypatch):
    calls = []
    monkeypatch.setattr(
        dream_reads,
        'MemoryService',
        lambda: SimpleNamespace(
            read=lambda uid, **kw: calls.append(kw) or [SimpleNamespace(id='huge'), SimpleNamespace(id='small')]
        ),
    )
    monkeypatch.setattr(dream_reads, 'context_candidates', lambda *a, **kw: iter(()))
    records = EvidenceRecords({REF: {'id': 'toy', 'transcript_segments': [{'text': 'Synthetic evidence.'}]}})
    records.context_mode = 'full'
    caps = replace(Caps(), context_mode='full', tokens=20000, completion_tokens=1000)
    rows = {
        'memory_items/huge': {'content': 'a' * 100000},
        'memory_items/small': {'id': 'small', 'content': 'Lives in Toytown.'},
    }
    diagnostics = {}
    admitted = dream_reads.retrieve_context(
        UID, records, caps, read=lambda uid, ref: rows[ref], diagnostics=diagnostics
    )
    assert 'memory_items/small' in admitted and 'memory_items/huge' not in admitted
    assert fits_full(admitted, caps)
    assert calls == [{'limit': 100}]
    assert diagnostics['memory_context_counts'] == {'found': 2, 'failed': 0, 'admitted': 1}


def test_metrics_counts_by_kind(monkeypatch):
    observed = {}

    class Metric:
        def labels(self, kind, disposition):
            return SimpleNamespace(inc=lambda count: observed.__setitem__((kind, disposition), count))

    monkeypatch.setattr(dream_metrics, 'MEMORY_EDITS', Metric())
    dream_metrics.record_pass(
        {
            'context_mode': 'full',
            'status': 'complete',
            'proposed': {'edits': [{'kind': 'retire_memory'}]},
            'outcomes': [{'key': 'dream:retire_memory:opaque', 'status': 'applied'}],
        }
    )
    assert observed[('retire_memory', 'proposed')] == observed[('retire_memory', 'auto_applied')] == 1
    assert observed[('retire_memory', 'suggested')] == 0


def test_real_undo_rate_demotes_each_hygiene_kind(hygiene, monkeypatch):
    db, _ = hygiene
    run([FullPlan(edits=[edit()])] * 3)
    path, raw = next((path, raw) for path, raw in db.rows.items() if path[-2] == 'review_changes')
    change = review_store.decode_doc(UID, raw)
    review_changes.set_undone(UID, change['change']['change_id'], True)
    query = SimpleNamespace()
    query.where = lambda **kw: query
    query.order_by = lambda *a, **kw: query
    query.limit = lambda n: query
    query.stream = lambda: iter([SimpleNamespace(to_dict=lambda: db.rows[path])])
    query_db = SimpleNamespace(
        collection=lambda name: SimpleNamespace(document=lambda uid: SimpleNamespace(collection=lambda name: query))
    )
    caps = Caps(undo_min_samples=1, undo_rate=0.2)
    assert REAL_DEMOTED_TYPES(UID, caps, firestore_client=query_db) == {'retire_memory'}
    monkeypatch.setattr(
        dream_agent.dream_store,
        'demoted_types',
        lambda uid, caps: REAL_DEMOTED_TYPES(uid, caps, firestore_client=query_db),
    )
    another = edit(target=NREF)
    report = run([FullPlan(edits=[another])] * 3, caps=caps)
    assert report['outcomes'][0]['status'] == 'suggested'
    assert db.rows[('users', UID, 'memory_items', 'new')]['status'] == 'active'


@pytest.mark.parametrize(
    'kw', [{'evidence': [MREF]}, {'evidence': ['people/synthetic-person']}, {'other': MREF, 'kind': 'supersede_memory'}]
)
def test_hygiene_requires_other_memory_or_conversation_evidence(hygiene, kw):
    _, records = hygiene
    evidence = records()[0]
    evidence['people/synthetic-person'] = {'name': 'Synthetic person'}
    with pytest.raises((ValueError, review_store.ReviewConflict)):
        dream_tools.validate_edit(edit(**kw), evidence)


def test_hygiene_attention_admission_checks_live_lease(hygiene):
    db, records = hygiene
    db.rows[('dream_users', UID)]['lease'] = {'run_id': 'newer-run', 'mode': 'on'}
    with pytest.raises(review_store.ReviewConflict, match='dream_lease_lost'):
        dream_tools.suggest_hygiene(UID, edit(), records()[0], 'synthetic-run')
    assert not any(path[-2] == 'review_proposals' for path in db.rows)


def test_existing_review_proposal_wire_is_unchanged():
    proposal = AgentProposalItem(
        edit=Edit(
            kind='memory',
            target=MREF,
            after='Synthetic corrected fact.',
            reason='Synthetic correction.',
            evidence=[REF],
        )
    )
    assert set(proposal.model_dump()) == {'target_label', 'other_label', 'edit', 'vocabulary'}
    assert 'memory_hygiene' not in proposal.model_dump(mode='json')


@pytest.mark.parametrize('fence', ['source_generation', 'account_generation', 'deletion'])
def test_undo_preserves_changed_generation_and_deletion_authority(hygiene, fence):
    db, _ = hygiene
    run([FullPlan(edits=[edit()])] * 3)
    data = review_store.decode_doc(UID, next(row for path, row in db.rows.items() if path[-2] == 'review_changes'))
    before = deepcopy(db.rows[('users', UID, 'memory_items', 'old')])
    if fence == 'deletion':
        db.rows[('account_deletions', UID)] = {'wipe_status': 'completed'}
    else:
        db.rows[('users', UID, 'memory_state', 'apply_control')][fence] += 1
    with pytest.raises(review_store.ReviewConflict):
        review_changes.set_undone(UID, data['change']['change_id'], True)
    assert db.rows[('users', UID, 'memory_items', 'old')] == before


def test_bounded_merge_vote_identity_stays_unchanged():
    first = Edit(
        kind='merge_memories',
        target=MREF,
        other=NREF,
        after='Synthetic merged fact.',
        reason='Synthetic duplicate.',
        evidence=[REF],
    )
    second = first.model_copy(update={'other': 'memory_items/different'})
    bounded = [Plan(edits=[first]), Plan(edits=[second]), Plan()]
    result = majority(bounded)
    assert len(result.edits) == 1 and result.edits[0].other == NREF
    full = [FullPlan.model_validate(plan.model_dump()) for plan in bounded]
    assert majority(full).edits == []
