from utils import dream_review_policy

"""Full-owner memory hygiene through canonical commits and the real Review seam."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import json

import pytest
from pydantic import ValidationError

from config.dream_agent import Caps
from database import memory_apply_store, review_changes, review_store
from database.memory_collections import MemoryCollections
from models.dream_edit import Edit, MemoryHygieneEdit
from models.agent_edit import HarnessEdit
from models.agent_tools import VerificationBatch, Verification
from config.dream_session import SessionLimits
from utils.llm.shaped_agent import Turn
from models.memory_apply import MemoryControlState, WriterMode, memory_content_hash
from models.product_memory import MemoryItem
from models.review import AgentProposalItem
from tests.unit.test_dream_harness_runtime import runtime, store, UID
from tests.unit.test_dream_cleanup_edits import records as cleanup_records
from tests.unit.test_dream_session import call, turn as tool_turn
from database import dream_store
from utils import dream_seed

REF = "conversations/one"
REAL_DEMOTED_TYPES = dream_store.demoted_types
from utils.agent_capabilities import tools as dream_tools
from utils import dream_agent
from utils.agent_capabilities.evidence import EvidenceRecords

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
    return HarnessEdit.model_validate(
        {'kind': kind, 'target': MREF, 'reason': 'Synthetic contradictory fact', 'evidence': [REF], 'value': 5, **kw}
    )


@pytest.fixture
def hygiene(runtime, monkeypatch):
    store = runtime
    monkeypatch.setenv('MEMORY_ENABLED', 'on')
    monkeypatch.setattr(memory_apply_store, '_firestore_transactional', lambda fn: fn)
    store.rows[('users', UID, 'memory_state', 'apply_control')] = MemoryControlState(
        uid=UID, writer_mode=WriterMode.ledger, head_commit_id='genesis', account_generation=0, source_generation=0
    ).model_dump(mode='json')
    store.rows[('users', UID, 'memory_items', 'old')] = memory('old', 'Lives in Toytown.')
    store.rows[('users', UID, 'memory_items', 'new')] = memory(
        'new', 'Since January, lives in New Toytown.', NOW + timedelta(days=1)
    )

    def records():
        evidence = EvidenceRecords(cleanup_records(store))
        evidence.update(
            {
                MREF: deepcopy(store.rows[('users', UID, 'memory_items', 'old')]),
                NREF: deepcopy(store.rows[('users', UID, 'memory_items', 'new')]),
            }
        )
        return evidence, []

    monkeypatch.setattr(
        dream_seed,
        'load',
        lambda uid, caps: ({'targets': list(records()[0]), 'vocabulary': []}, records()[0], [], SessionLimits()),
    )
    monkeypatch.setattr(dream_tools, 'proposal_record', lambda uid, ref, snapshot: records()[0][ref])
    return store, records


def run(operation, *, caps=None, votes=(True, True), trigger='schedule'):
    import asyncio
    from utils.dream_harness_transport import MAIN_LANE

    index = 0

    async def model(uid, lane, mount, messages):
        nonlocal index
        if lane == MAIN_LANE:
            return tool_turn(
                [
                    call('propose_edit', {'edit': operation.model_dump(mode='json')}),
                    call('finish', {'summary': 'Checked synthetic facts'}, 2),
                ]
            )
        batch = json.loads(messages[-1]['content'].split('\n', 1)[1])
        agree = votes[index]
        index += 1
        return Turn(
            tokens=10,
            value=VerificationBatch(
                decisions=[
                    Verification(id=row['id'], agree=agree, reason='Synthetic independent verification')
                    for row in batch
                ]
            ),
        )

    return asyncio.run(dream_agent.run_pass(UID, turn=model, caps=caps, trigger=trigger))


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
    db.rows[('users', UID, 'memory_items', 'old')].pop('belief_class', None)
    before = deepcopy(db.rows[('users', UID, 'memory_items', 'old')])
    newer = deepcopy(db.rows[('users', UID, 'memory_items', 'new')])
    report = run(operation)
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
    assert sans_stamps(db.rows[('users', UID, 'memory_items', 'old')]) == sans_stamps(before)
    assert db.rows[('users', UID, 'memory_items', 'new')] == newer
    assert not review_changes.agent_change_allowed(UID, dream_tools.edit_key(operation, records()[0]))
    if operation.after:
        tails = [row for path, row in db.rows.items() if path[-2] == 'memory_items' and path[-1] not in {'old', 'new'}]
        assert len(tails) == 1 and tails[0]['status'] == 'superseded'
    assert not review_changes.set_undone(UID, change_id, False).undone
    assert sans_stamps(db.rows[('users', UID, 'memory_items', 'old')]) == sans_stamps(after)
    assert len([path for path in db.rows if path[-2] == 'memory_commits']) == 3
    events = [row for path, row in db.rows.items() if path[-2] == 'memory_outbox']
    assert {row['payload']['action'] for row in events} == {'upsert', 'delete'}


def test_verified_duplicate_merge_commits_both_facts_and_restores_exactly(hygiene):
    db, _ = hygiene
    keys = [('users', UID, 'memory_items', key) for key in ('old', 'new')]
    before = [deepcopy(db.rows[key]) for key in keys]
    operation = edit('merge_memories', other=NREF, after='Lives in the invented New Toytown.')
    report = run(operation)
    assert report['outcomes'][0]['status'] == 'applied', report
    after = [deepcopy(db.rows[key]) for key in keys]
    assert all(row['status'] == 'superseded' for row in after)
    assert after[0]['superseded_by'] == after[1]['superseded_by']
    assert after[0]['ledger_commit_id'] == after[1]['ledger_commit_id']
    tail = db.rows[('users', UID, 'memory_items', after[0]['superseded_by'])]
    assert tail['status'] == 'active' and tail['write_reason'] == 'daily_reconciliation'
    journal = next(
        review_store.decode_doc(UID, raw) for path, raw in db.rows.items() if path[2:3] == ('review_changes',)
    )
    assert journal['memory_hygiene']['before']['old'] == before[0]
    assert journal['memory_hygiene']['before']['new'] == before[1]
    change_id = journal['change']['change_id']
    review_changes.set_undone(UID, change_id, True)
    assert [sans_stamps(db.rows[key]) for key in keys] == [sans_stamps(row) for row in before]
    assert db.rows[('users', UID, 'memory_items', tail['memory_id'])]['status'] == 'superseded'
    review_changes.set_undone(UID, change_id, False)
    assert [sans_stamps(db.rows[key]) for key in keys] == [sans_stamps(row) for row in after]


def test_memory_merge_refuses_a_changed_second_source_without_partial_writes(hygiene):
    db, sources = hygiene
    records = sources()[0]
    fences = dream_tools.proposal_fences(UID, {'records': records})
    db.rows[('users', UID, 'memory_items', 'new')]['content'] = 'A later synthetic edit'
    before = deepcopy(db.rows)
    with pytest.raises(review_store.ReviewConflict):
        dream_tools.apply_edit(
            UID, edit('merge_memories', other=NREF, after='Synthetic combined fact'), records, expected_records=fences
        )
    assert db.rows == before


@pytest.mark.parametrize(
    'content,reason',
    [
        ('uh um invented extraction fragment', 'Synthetic extraction junk rather than low importance'),
        ('Owner speaks Martian.', 'Another synthetic speaker said this about themselves'),
    ],
)
def test_scripted_garbage_and_misattribution_replay_retires_with_exact_undo(hygiene, content, reason):
    db, _ = hygiene
    path = ('users', UID, 'memory_items', 'old')
    db.rows[path] = memory('old', content)
    if content == 'Owner speaks Martian.':
        db.rows[('users', UID, 'conversations', 'one')]['transcript_segments'][0].update(
            text='I am the invented other speaker. I speak Martian as an invented language.', is_user=False
        )
    before = deepcopy(db.rows[path])
    report = run(edit(reason=reason))
    assert report['outcomes'][0]['status'] == 'applied'
    journal = next(
        review_store.decode_doc(UID, row) for path, row in db.rows.items() if path[2:3] == ('review_changes',)
    )
    review_changes.set_undone(UID, journal['change']['change_id'], True)
    assert sans_stamps(db.rows[path]) == sans_stamps(before)


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


def test_undo_conflicts_with_later_edit(hygiene):
    db, _ = hygiene
    run(edit())
    data = review_store.decode_doc(UID, next(row for path, row in db.rows.items() if path[-2] == 'review_changes'))
    db.rows[('users', UID, 'memory_items', 'old')]['content'] = 'A later synthetic correction.'
    with pytest.raises(review_store.ReviewConflict):
        review_changes.set_undone(UID, data['change']['change_id'], True)


def test_real_undo_rate_demotes_each_hygiene_kind(hygiene, monkeypatch):
    db, _ = hygiene
    run(edit())
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
    caps = Caps(undo_min_samples=1, undo_rate=0.2, passes=10)
    assert REAL_DEMOTED_TYPES(UID, caps, firestore_client=query_db) == {'retire_memory'}
    monkeypatch.setattr(
        dream_agent.dream_store,
        'demoted_types',
        lambda uid, caps: REAL_DEMOTED_TYPES(uid, caps, firestore_client=query_db),
    )
    another = edit(target=NREF)
    report = run(another, caps=caps, trigger='manual')
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
    db.rows.setdefault(('dream_users', UID), {})['lease'] = {'run_id': 'newer-run', 'mode': 'on'}
    with pytest.raises(review_store.ReviewConflict, match='dream_lease_lost'):
        dream_review_policy.suggest_hygiene(UID, edit(), records()[0], 'stale-synthetic-run')
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
    run(edit())
    data = review_store.decode_doc(UID, next(row for path, row in db.rows.items() if path[-2] == 'review_changes'))
    before = deepcopy(db.rows[('users', UID, 'memory_items', 'old')])
    if fence == 'deletion':
        db.rows[('account_deletions', UID)] = {'wipe_status': 'completed'}
    else:
        db.rows[('users', UID, 'memory_state', 'apply_control')][fence] += 1
    with pytest.raises(review_store.ReviewConflict):
        review_changes.set_undone(UID, data['change']['change_id'], True)
    assert db.rows[('users', UID, 'memory_items', 'old')] == before


def sans_stamps(row):
    return {key: value for key, value in row.items() if key not in {'ledger_commit_id', 'ledger_sequence'}}


def test_user_authored_facts_require_review_not_auto_apply(hygiene):
    """Two agreeing verifiers may still not silently close a user-authored fact."""
    db, _ = hygiene
    db.rows[('users', UID, 'memory_items', 'old')]['write_reason'] = 'direct_user_statement'
    operation = edit()
    report = run(operation)
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
    report = run(operation)
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
    report = run(operation)
    assert report['outcomes'][0]['status'] == 'applied'
    tail = next(row for path, row in db.rows.items() if path[-2] == 'memory_items' and path[-1] not in {'old', 'new'})
    assert tail['tier'] == 'short_term'
    assert tail['expires_at'] > tail['captured_at']


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
    report = run(operation)
    assert report['outcomes'][0]['status'] == 'applied'
    item = MemoryItem.model_validate(tail_row(db))
    # Canonical evidence carries the bare conversation id: source-cohort
    # discovery probes source_ids with array_contains on the raw id.
    assert REF.partition('/')[2] in item.source_ids
    evidence_rows = [row for path, row in db.rows.items() if path[-2] == 'memory_evidence']
    assert len(evidence_rows) == 1
    assert evidence_rows[0]['conversation_id'] == REF.partition('/')[2]


def test_secret_shaped_replacement_content_is_restricted(hygiene):
    """Free-form replacements never inherit unrestricted labels blindly."""
    db, _ = hygiene
    operation = edit('supersede_memory', after='Leaked key sk-ABCDEFGHIJKLMNOPQRSTUVWX in the transcript.')
    report = run(operation)
    assert report['outcomes'][0]['status'] == 'applied'
    assert 'credential' in tail_row(db)['sensitivity_labels']


def test_background_tail_uses_reconciliation_reason_review_accept_does_not(hygiene):
    db, _ = hygiene
    operation = edit('supersede_memory', after='Since January, lives in New Toytown.')
    report = run(operation)
    assert report['outcomes'][0]['status'] == 'applied'
    # The scheduled effect loop (dream_writing set) is the reconciliation
    # channel; its conclusions must not outrank the sweep's later corrections.
    assert tail_row(db)['write_reason'] == 'daily_reconciliation'
    # A user-accepted Review proposal applies outside the effect loop and
    # keeps the request-serving agent-conclusion reason.
    db.rows[('users', UID, 'memory_items', 'new')]['write_reason'] = 'direct_user_statement'
    accepted = edit('supersede_memory', target=NREF, after='Now lives in Futurtown for good.')
    report = run(accepted, trigger='manual')
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
    run(edit('supersede_memory', other=NREF))
    wire = decoded(db, 'review_proposals')['item']['agent_proposal']
    assert wire['target_content'] == 'Lives in Toytown.'
    assert wire['other_content'] == 'Since January, lives in New Toytown.'


def test_replacement_effective_time_comes_from_evidence(hygiene):
    from utils.agent_capabilities.guards import timestamp

    db, _ = hygiene
    since = (NOW - timedelta(days=3)).isoformat()
    operation = edit('supersede_memory', after='Since January, lives in New Toytown.', effective_from=since)
    report = run(operation)
    assert report['outcomes'][0]['status'] == 'applied'
    tail = tail_row(db)
    valid_from, expected = timestamp(tail['valid_from']), timestamp(since)
    assert valid_from is not None and valid_from == expected
    closed_at = timestamp(db.rows[('users', UID, 'memory_items', 'old')]['valid_to'])
    assert closed_at is not None and closed_at > valid_from


def test_future_effective_time_falls_back_to_apply_time(hygiene):
    from utils.agent_capabilities.guards import timestamp

    db, _ = hygiene
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    operation = edit('supersede_memory', after='Will move to Futurtown.', effective_from=future)
    report = run(operation)
    assert report['outcomes'][0]['status'] == 'applied'
    valid_from, future_at = timestamp(tail_row(db)['valid_from']), timestamp(future)
    assert valid_from is not None and future_at is not None and valid_from < future_at
