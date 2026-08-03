"""The person-dossier contract: a field is grounded or it is absent.

The prompt is the risky part of the Phase-3 narrative layer, so what is tested here is its
*contract* rather than its prose:

  * evidence in -> a valid output shape out, with every surviving field carrying real provenance;
  * a model that asserts without citing -> the assertion is dropped, not softened;
  * thin evidence -> no model call at all, and an empty profile rather than an invented one;
  * the exact ids the model may cite are the ones it was given — an invented id grounds nothing.

Hermetic: pure functions only, no network (the session guard blocks it anyway), no Firestore.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from utils.llm.people_dossier import (
    MAX_EVIDENCE_ITEMS,
    MIN_EVIDENCE_ITEMS,
    DossierClaim,
    EvidenceItem,
    PersonDossierDraft,
    build_dossier_prompt,
    build_evidence,
    evidence_fingerprint,
    generate_person_dossier,
    ground_dossier,
)

PERSON = 'person:pid-1'
OTHER = 'person:pid-2'


def _memory(content, *, subject=None, objects=(), day=1):
    return {
        'content': content,
        'subject_entity_id': subject,
        'object_entity_ids': list(objects),
        'created_at': datetime(2026, 7, day, 12, 0, tzinfo=timezone.utc),
    }


def _evidence(count=4):
    return [EvidenceItem(id=f'm{i}', text=f'fact {i}', when='2026-07-01', role='subject') for i in range(count)]


# ---------------------------------------------------------------------------
# Evidence selection
# ---------------------------------------------------------------------------


def test_evidence_takes_subject_and_mention_memories_and_ignores_other_people():
    memories = [
        _memory('Priya runs the Thursday climbing session', subject=PERSON, day=3),
        _memory('User owes Priya the venue deposit', objects=[PERSON], day=2),
        _memory('Sam moved to Lisbon', subject=OTHER, day=4),
        _memory('', subject=PERSON, day=5),
    ]

    evidence = build_evidence(memories, PERSON)

    assert [item.text for item in evidence] == [
        'Priya runs the Thursday climbing session',
        'User owes Priya the venue deposit',
    ]
    # Subject memories rank ahead of mentions: a fact about the person is stronger evidence for
    # who they are than a fact that merely names them.
    assert [item.role for item in evidence] == ['subject', 'mention']
    assert [item.id for item in evidence] == ['m0', 'm1']


def test_evidence_is_capped():
    memories = [_memory(f'fact {i}', subject=PERSON) for i in range(MAX_EVIDENCE_ITEMS + 20)]

    assert len(build_evidence(memories, PERSON)) == MAX_EVIDENCE_ITEMS


def test_fingerprint_tracks_content_not_ordering_noise():
    base = build_evidence([_memory('a', subject=PERSON, day=2), _memory('b', subject=PERSON, day=1)], PERSON)
    same = build_evidence([_memory('a', subject=PERSON, day=2), _memory('b', subject=PERSON, day=1)], PERSON)
    edited = build_evidence([_memory('a!', subject=PERSON, day=2), _memory('b', subject=PERSON, day=1)], PERSON)

    assert evidence_fingerprint(base) == evidence_fingerprint(same)
    assert evidence_fingerprint(base) != evidence_fingerprint(edited)


# ---------------------------------------------------------------------------
# The grounding contract
# ---------------------------------------------------------------------------


def test_grounded_fields_survive_with_their_provenance():
    draft = PersonDossierDraft(
        who='Priya is a climbing partner.',
        facts=['Priya organizes the Thursday session.'],
        open_threads=['Priya is waiting on the venue deposit.'],
        claims=[
            DossierClaim(field='who', text='Priya is a climbing partner.', evidence=['m0']),
            DossierClaim(field='facts', text='Priya organizes the Thursday session.', evidence=['m0', 'm1']),
            DossierClaim(field='open_threads', text='Priya is waiting on the venue deposit.', evidence=['m2']),
        ],
    )

    grounded = ground_dossier(draft, ['m0', 'm1', 'm2'])

    assert grounded.who == 'Priya is a climbing partner.'
    assert grounded.facts == ['Priya organizes the Thursday session.']
    assert grounded.open_threads == ['Priya is waiting on the venue deposit.']
    assert {claim['field'] for claim in grounded.claims} == {'who', 'facts', 'open_threads'}
    assert [claim['evidence'] for claim in grounded.claims if claim['field'] == 'facts'] == [['m0', 'm1']]


@pytest.mark.parametrize(
    'claims',
    [
        pytest.param([], id='no_claims_at_all'),
        pytest.param(
            [DossierClaim(field='who', text='Priya works at Acme.', evidence=[])],
            id='claim_cites_nothing',
        ),
        pytest.param(
            [DossierClaim(field='who', text='Priya works at Acme.', evidence=['m99'])],
            id='claim_cites_an_invented_id',
        ),
        pytest.param(
            [DossierClaim(field='now', text='Priya works at Acme.', evidence=['m0'])],
            id='citation_is_for_a_different_field',
        ),
    ],
)
def test_an_ungrounded_assertion_is_dropped_not_softened(claims):
    draft = PersonDossierDraft(who='Priya works at Acme.', claims=claims)

    grounded = ground_dossier(draft, ['m0', 'm1'])

    assert grounded.who is None
    assert grounded.claims == [] or all(claim['field'] != 'who' for claim in grounded.claims)


def test_every_list_item_must_be_cited_individually():
    draft = PersonDossierDraft(
        facts=['Priya organizes the Thursday session.', 'Priya just bought a house in Lisbon.'],
        claims=[DossierClaim(field='facts', text='Priya organizes the Thursday session.', evidence=['m0'])],
    )

    grounded = ground_dossier(draft, ['m0'])

    # One citation does not carry the whole list — the uncited second fact is gone.
    assert grounded.facts == ['Priya organizes the Thursday session.']


def test_hedged_claims_are_dropped_everywhere():
    draft = PersonDossierDraft(
        who='Priya seems to be a coworker.',
        overall='Priya is a long-standing friend.',
        facts=['Priya probably lives in Lisbon.', 'Priya organizes the Thursday session.'],
        claims=[
            DossierClaim(field='who', text='Priya seems to be a coworker.', evidence=['m0']),
            DossierClaim(field='overall', text='Priya is a long-standing friend.', evidence=['m0']),
            DossierClaim(field='facts', text='Priya probably lives in Lisbon.', evidence=['m0']),
            DossierClaim(field='facts', text='Priya organizes the Thursday session.', evidence=['m0']),
        ],
    )

    grounded = ground_dossier(draft, ['m0'])

    assert grounded.who is None, 'a hedge is the tell of a claim without evidence'
    assert grounded.overall == 'Priya is a long-standing friend.'
    assert grounded.facts == ['Priya organizes the Thursday session.']


def test_thin_evidence_yields_an_empty_dossier_without_calling_a_model(monkeypatch):
    from utils.llm import people_dossier

    def explode(*args, **kwargs):  # pragma: no cover - reaching this is the failure
        raise AssertionError('a model must not be called for a person with no history')

    monkeypatch.setattr(people_dossier, 'get_llm', explode)

    result = generate_person_dossier('uid-1', 'Alex', 'Priya', _evidence(MIN_EVIDENCE_ITEMS - 1))

    assert result.is_empty
    assert result.as_dict() == {
        'who': None,
        'now': None,
        'overall': None,
        'facts': [],
        'activities': [],
        'open_threads': [],
        'claims': [],
    }


def test_a_malformed_draft_never_raises():
    grounded = ground_dossier(
        PersonDossierDraft(who='x', claims=[DossierClaim(field='nope', text='', evidence=[])]), []
    )

    assert grounded.is_empty


# ---------------------------------------------------------------------------
# The prompt itself
# ---------------------------------------------------------------------------


def test_prompt_names_the_person_as_subject_and_states_the_grounding_rules():
    prompt = build_dossier_prompt('Alex', 'Priya', _evidence(3), '{"who": "..."}')

    # Modelled on working_observations, which permits a third-party subject — NOT on
    # extract_memories_prompt, whose rules 7/8 forbid standalone third-party facts.
    assert 'The subject is Priya — NOT Alex' in prompt
    # The three rules the validator then enforces.
    assert 'must be left out' in prompt
    assert 'left unresolved' in prompt
    assert 'Do not hedge' in prompt
    # The evidence ids the model is allowed to cite are actually in the prompt.
    assert 'm0 (subject)' in prompt
    assert 'm2 (subject)' in prompt


def test_prompt_does_not_reuse_the_memory_extraction_rules():
    """`extract_memories_prompt` forbids standalone third-party facts; this prompt requires them."""
    from utils import prompts

    dossier_prompt = build_dossier_prompt('Alex', 'Priya', _evidence(3), '{}')
    memories_prompt = prompts.extract_memories_prompt.messages[0].prompt.template

    assert 'COLLEAGUE FACTS WITHOUT RELATIONSHIP' in memories_prompt
    assert 'COLLEAGUE FACTS WITHOUT RELATIONSHIP' not in dossier_prompt
    assert 'GENERIC RELATIONSHIPS' not in dossier_prompt
