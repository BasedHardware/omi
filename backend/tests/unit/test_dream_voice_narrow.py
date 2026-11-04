"""Person voice data stays out of every model-facing view; staging keeps the full row."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from config.dream_session import SessionLimits
from models.agent_tools import HarnessQuestion, Read
from utils import dream_seed
from utils.agent_capabilities import staging
from utils.agent_capabilities.evidence import model_view
from tests.unit.test_dream_session import call, turn
from utils.agent_capabilities.session import Session, serialized_bytes

SECRET = 'synthetic-voice-words'
PERSON = {
    'name': 'Sam',
    'user_confirmed': True,
    'speaker_embedding': [0.25, 0.5],
    'speech_samples': ['synthetic/' + SECRET],
    'speech_sample_transcripts': [SECRET],
    'speech_sample_source': {'conversation_id': SECRET},
    'person_voice_base': {'embedding': [0.5], 'transcripts': [SECRET]},
    'person_voice_confirmations': [{'embedding': [0.75], 'transcript': SECRET}],
    'voice_field_added_later': SECRET,
}
VISIBLE = {'name': 'Sam', 'user_confirmed': True, 'has_voice_profile': True}


class Source:
    async def read(self, ref):
        return dict(PERSON)


def _session(**kwargs):
    return Session(
        'synthetic-owner',
        Source(),
        SessionLimits(read_bytes=512000),
        {'targets': ['people/sam']},
        authority='dream',
        **kwargs
    )


def test_read_tool_returns_the_model_view_and_keeps_the_full_row():
    session = _session()

    result = asyncio.run(session.read(Read(refs=['people/sam'])))

    assert result['records']['people/sam'] == VISIBLE
    assert session.records['people/sam']['speaker_embedding'] == PERSON['speaker_embedding']


def test_the_read_budget_charges_what_the_model_sees():
    session = _session()
    before = session.read_bytes

    asyncio.run(session.read(Read(refs=['people/sam'])))

    assert session.read_bytes - before == serialized_bytes({'people/sam': VISIBLE})


def test_seed_records_reach_the_prompt_as_the_model_view():
    session = _session(records={'people/sam': dict(PERSON)})
    seen = []

    async def model(mount, messages):
        seen.append(json.dumps(messages, default=str))
        return turn([call('finish', {'summary': 'Nothing to do.'})])

    assert asyncio.run(session.run(model, deadline_seconds=5)).reason == 'finished'
    assert seen and SECRET not in seen[0]
    assert 'has_voice_profile' in seen[0]
    assert session.records['people/sam']['speaker_embedding'] == PERSON['speaker_embedding']


def _question(quote):
    return HarnessQuestion(
        kind='spelling',
        title='Spelling?',
        quote=quote,
        source_ref='people/sam',
        spelling={'term_id': 'synthetic', 'options': ['Sam', 'Samm'], 'allow_custom': False},
        value=4,
        why_it_matters='Synthetic reason',
    )


def test_a_question_cannot_quote_hidden_voice_text():
    with pytest.raises(ValueError, match='agent_invalid_question_evidence'):
        asyncio.run(
            staging.stage('synthetic-owner', _question(SECRET), {'people/sam': dict(PERSON)}, authority='dream')
        )


def test_other_records_pass_through_untouched():
    memory = {'content': 'Synthetic fact', 'speech_samples': ['not a person row']}

    assert model_view('memory_items/one', memory) is memory
    assert model_view('people/sam', None) is None


def test_empty_voice_fields_are_not_a_voice_profile():
    assert model_view('people/junk', {'name': 'Canadian', 'speech_samples': [], 'speaker_embedding': None}) == {
        'name': 'Canadian'
    }


class _Query:
    def __getattr__(self, name):
        return lambda *args, **kwargs: self

    def stream(self):
        return []


def _seed_notes(monkeypatch, source):
    monkeypatch.setattr(dream_seed.dream_history, 'history_count', lambda *args, **kwargs: 0)
    monkeypatch.setattr(dream_seed.users, 'get_user_profile', lambda uid: {})
    monkeypatch.setattr(dream_seed.dream_store, 'vocabulary', lambda uid: [])
    monkeypatch.setattr(dream_seed.dream_store, 'dirty_refs', lambda uid, limit=32, newest=False: [])
    monkeypatch.setattr(dream_seed.dream_store, 'own_runs', lambda uid, limit=1: [('run', {'source': source})])
    monkeypatch.setattr(dream_seed.review_store, 'decode_doc', lambda uid, raw: raw)
    monkeypatch.setattr(dream_seed.review_store, 'user', lambda uid: SimpleNamespace(collection=lambda name: _Query()))
    return dream_seed.load('synthetic-owner', SimpleNamespace(tokens=1000, edits=1))[0]['previous_notes']


def test_notes_from_before_the_narrowing_never_reach_a_prompt(monkeypatch):
    assert _seed_notes(monkeypatch, {'notes': SECRET}) == ''


def test_notes_written_after_the_narrowing_carry_forward(monkeypatch):
    assert _seed_notes(monkeypatch, {'notes': 'Check tasks next.', 'notes_voice_free': True}) == 'Check tasks next.'
