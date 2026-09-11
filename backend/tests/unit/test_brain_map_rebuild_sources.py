"""A Brain Map rebuild reads the whole account, not just its memories.

An account with two memories and hundreds of conversations used to rebuild into
three dots. These pin what a rebuild feeds the extractor: every readable
conversation as summary-first prose, the people directory and active goals as
one payload each, memories under their own ids so canonical assertions and the
inspector keep resolving them.
"""

from __future__ import annotations

from types import SimpleNamespace

# Imported at module level so the store's import cost lands in collection, not
# in the fast-unit duration guard of the test that patches it.
from database import conversations as conversations_db
from utils.memory import brain_map_sources as sources


def _conversation(conversation_id: str, **overrides):
    conversation = {
        'id': conversation_id,
        'structured': {
            'title': 'Weekly standup',
            'overview': 'Planned the launch with Sarah.',
            'category': 'business',
            'action_items': [{'description': 'Ship the beta'}],
            'events': [{'title': 'Launch review'}],
        },
        'transcript_segments': [{'text': 'We should ship the beta by Friday.'}, {'text': 'Agreed.'}],
    }
    conversation.update(overrides)
    return conversation


def test_conversation_text_leads_with_the_summary_and_ends_with_the_transcript():
    text = sources.conversation_source_text(_conversation('c1'))

    assert text.splitlines() == [
        'Conversation: Weekly standup',
        'Topic: business',
        'Summary: Planned the launch with Sarah.',
        'Action items: Ship the beta',
        'Events: Launch review',
        'Transcript: We should ship the beta by Friday. Agreed.',
    ]


def test_a_long_transcript_is_cut_rather_than_dropping_the_conversation():
    conversation = _conversation('c1', transcript_segments=[{'text': 'word ' * 2_000}])

    text = sources.conversation_source_text(conversation, transcript_chars=100)

    transcript_line = text.splitlines()[-1]
    assert transcript_line.startswith('Transcript: ')
    assert transcript_line.endswith('…')
    assert len(transcript_line) < 120
    # The summary survived the cut.
    assert 'Summary: Planned the launch with Sarah.' in text


def test_every_source_becomes_a_payload_with_a_recognisable_id():
    memories = [
        SimpleNamespace(id='m1', content='Nathan is 23.'),
        SimpleNamespace(id='m2', content='locked', is_locked=True),
        SimpleNamespace(id='m3', content='   '),
    ]
    conversations = [
        _conversation('c1'),
        _conversation('c2', discarded=True),
        _conversation('c3', is_locked=True),
        _conversation('c4', structured={}, transcript_segments=[]),
    ]
    people = [{'name': 'Sarah'}, {'name': 'Alex'}, {'name': ''}, {'name': 'Sarah'}]
    goals = [
        {'title': 'Ship v1', 'desired_outcome': 'Ship v1'},
        {'title': 'Run more', 'desired_outcome': 'Three runs a week'},
        {'title': ''},
    ]

    built = sources.build_brain_map_sources(memories=memories, conversations=conversations, people=people, goals=goals)

    assert [payload['id'] for payload in built.payloads] == [
        'm1',
        'conversation:c1',
        sources.PEOPLE_SOURCE_ID,
        sources.GOALS_SOURCE_ID,
    ]
    by_id = {payload['id']: payload['content'] for payload in built.payloads}
    assert by_id['m1'] == 'Nathan is 23.'
    assert by_id['conversation:c1'].startswith('Conversation: Weekly standup')
    assert by_id[sources.PEOPLE_SOURCE_ID] == 'People the user knows and talks with: Alex, Sarah.'
    assert by_id[sources.GOALS_SOURCE_ID] == 'Goals the user is working toward: Ship v1; Run more — Three runs a week.'
    assert built.counts == {'memories': 1, 'conversations': 1, 'people': 2, 'goals': 2}


def test_the_conversation_budget_bounds_llm_calls_but_not_the_other_sources():
    conversations = [_conversation(f'c{index}') for index in range(10)]

    built = sources.build_brain_map_sources(
        conversations=conversations, people=[{'name': 'Sarah'}], conversation_limit=3
    )

    assert built.counts['conversations'] == 3
    assert [payload['id'] for payload in built.payloads] == [
        'conversation:c0',
        'conversation:c1',
        'conversation:c2',
        sources.PEOPLE_SOURCE_ID,
    ]


def test_collect_reads_every_store_through_its_seam():
    reads = []

    built = sources.collect_brain_map_sources(
        'uid-1',
        read_memories=lambda: reads.append('memories') or [SimpleNamespace(id='m1', content='fact')],
        read_conversations=lambda: reads.append('conversations') or [_conversation('c1')],
        read_people=lambda: reads.append('people') or [{'name': 'Sarah'}],
        read_goals=lambda: reads.append('goals') or [{'title': 'Ship'}],
    )

    assert reads == ['memories', 'conversations', 'people', 'goals']
    assert built.counts == {'memories': 1, 'conversations': 1, 'people': 1, 'goals': 1}


class _FakeQuery:
    """The chain `get_conversations` builds, recording what it filters on."""

    def __init__(self, docs, filters):
        self.docs = docs
        self.filters = filters

    def where(self, filter):  # noqa: A002 - Firestore's keyword
        self.filters.append(filter.field_path)
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, _limit):
        return self

    def offset(self, _offset):
        return self

    def stream(self):
        return iter(self.docs)

    # `db.collection('users').document(uid).collection('conversations')`
    def collection(self, _name):
        return self

    def document(self, _name):
        return self


def test_the_default_conversation_reader_keeps_legacy_rows_and_names_them_by_document_id(monkeypatch):
    # Two ways an old account loses its conversations: the store's own
    # `discarded == False` filter drops every row written before the field
    # existed, and a row without an `id` field cannot be cited. The default
    # reader asks for discarded rows and filters them here, and every row is
    # named by its document id.
    class _Doc:
        update_time = None

        def __init__(self, doc_id, data):
            self.id = doc_id
            self._data = data

        def to_dict(self):
            return dict(self._data)

    docs = [
        _Doc('legacy', {'structured': {'title': 'Before the flag'}}),
        _Doc('kept', {'id': 'kept', 'discarded': False, 'structured': {'title': 'Kept'}}),
        _Doc('binned', {'id': 'binned', 'discarded': True, 'structured': {'title': 'Binned'}}),
    ]
    filters = []
    monkeypatch.setattr(conversations_db, 'db', _FakeQuery(docs, filters))

    built = sources.collect_brain_map_sources(
        'uid-1',
        read_memories=lambda: [],
        read_people=lambda: [],
        read_goals=lambda: [],
    )

    assert 'discarded' not in filters
    assert [payload['id'] for payload in built.payloads] == ['conversation:legacy', 'conversation:kept']
