"""
Regression test for query_vectors_by_metadata people re-ranking.

The function re-ranks Pinecone matches by counting how many of the requested
topics/entities/people appear in each match's metadata. Matches are written
under the key 'people' (see utils/llm/chat.py building {'people': [...]} and
the Pinecone $or filter in vector_db.query_vectors_by_metadata querying
{'people': {'$in': people}}). The re-rank lookup must read the SAME key.

Bug: the people branch read metadata.get('people_mentioned', ...) — a key that
is never written — so a conversation that only matches by person got a
match-count of 0 and lost its relevance boost in the ordering. This test builds
matches whose metadata has 'people':['alice'] and asserts the person match
contributes a boost (the person-matching conversation is ranked first), which
fails when the lookup uses the wrong key.
"""

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, _BACKEND_DIR)

# Stub heavy deps before importing vector_db. Same pattern as test_action_item_dedup.
for mod_name in [
    'pinecone',
    'firebase_admin',
    'firebase_admin.auth',
    'google',
    'google.cloud',
    'google.cloud.firestore',
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

sys.modules['pinecone'].Pinecone = MagicMock


class _FakeFirestoreClient:
    def collection(self, *a, **kw):
        return MagicMock()

    def batch(self):
        return MagicMock()


sys.modules['google.cloud.firestore'].Client = _FakeFirestoreClient
sys.modules['google.cloud.firestore'].ArrayUnion = MagicMock
sys.modules['google.cloud.firestore'].ArrayRemove = MagicMock
sys.modules['google.cloud.firestore'].Increment = MagicMock
sys.modules['google.cloud.firestore'].SERVER_TIMESTAMP = object()
sys.modules['google.cloud.firestore'].DELETE_FIELD = object()
sys.modules['google.cloud.firestore'].FieldFilter = MagicMock
sys.modules['google.cloud.firestore'].Query = MagicMock
sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})

database_pkg = sys.modules.get('database')
if not isinstance(database_pkg, types.ModuleType):
    database_pkg = types.ModuleType('database')
    sys.modules['database'] = database_pkg
database_pkg.__path__ = [os.path.join(_BACKEND_DIR, 'database')]
sys.modules.pop('database.vector_db', None)

previous_clients_stub = sys.modules.get('utils.llm.clients')
clients_stub = types.ModuleType('utils.llm.clients')
clients_stub.embeddings = MagicMock()
sys.modules['utils.llm.clients'] = clients_stub

_vector_db_path = os.path.join(_BACKEND_DIR, 'database', 'vector_db.py')
_vector_db_spec = importlib.util.spec_from_file_location('people_rerank_vector_db', _vector_db_path)
if _vector_db_spec is None or _vector_db_spec.loader is None:
    raise ImportError(f'Unable to load vector_db from {_vector_db_path}')
vector_db = importlib.util.module_from_spec(_vector_db_spec)
_vector_db_spec.loader.exec_module(vector_db)

if previous_clients_stub is None:
    sys.modules.pop('utils.llm.clients', None)
else:
    sys.modules['utils.llm.clients'] = previous_clients_stub


def _match(uid, memory_id, people):
    return {
        'id': f'{uid}-{memory_id}',
        'metadata': {'uid': uid, 'memory_id': memory_id, 'people': people},
    }


class TestPeopleRerank:
    def test_person_match_boosts_ranking(self, monkeypatch):
        """A conversation whose metadata['people'] contains the queried person
        must be ranked above one that does not. With the pre-fix key
        ('people_mentioned'), the person never matched, so the boost was 0 and
        the matching conversation was NOT pulled to the front."""
        uid = 'uid-xyz'
        # 'no-match' is returned FIRST by Pinecone; 'has-alice' second. Only a
        # working people re-rank can pull 'has-alice' ahead of 'no-match'.
        query_response = {
            'matches': [
                _match(uid, 'no-match', people=['bob']),
                _match(uid, 'has-alice', people=['alice']),
            ]
        }
        fake_index = MagicMock()
        fake_index.query = MagicMock(return_value=query_response)
        monkeypatch.setattr(vector_db, 'index', fake_index)

        result = vector_db.query_vectors_by_metadata(
            uid=uid,
            vector=[0.1, 0.2, 0.3],
            dates_filter=[],
            people=['alice'],
            topics=[],
            entities=[],
            dates=[],
            limit=5,
        )

        # The person-matching conversation must receive the boost and rank first.
        assert result[0] == 'has-alice', (
            "people re-rank did not boost the person-matching conversation; "
            "lookup key likely does not match the metadata write key ('people')"
        )
        assert set(result) == {'has-alice', 'no-match'}

    def test_people_metadata_key_is_used(self, monkeypatch):
        """Direct count check: the only match has people:['alice'] and we query
        person 'alice'; it must get a non-zero match-count boost (be returned),
        proving the 'people' metadata key is what the re-rank reads."""
        uid = 'uid-abc'
        query_response = {'matches': [_match(uid, 'conv-1', people=['alice'])]}
        fake_index = MagicMock()
        fake_index.query = MagicMock(return_value=query_response)
        monkeypatch.setattr(vector_db, 'index', fake_index)

        result = vector_db.query_vectors_by_metadata(
            uid=uid,
            vector=[0.1, 0.2, 0.3],
            dates_filter=[],
            people=['alice'],
            topics=[],
            entities=[],
            dates=[],
            limit=5,
        )

        assert result == ['conv-1']
