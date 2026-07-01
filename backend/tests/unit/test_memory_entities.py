import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

google_stub = sys.modules.setdefault('google', types.ModuleType('google'))
cloud_stub = sys.modules.setdefault('google.cloud', types.ModuleType('google.cloud'))
firestore_stub = sys.modules.setdefault('google.cloud.firestore', types.ModuleType('google.cloud.firestore'))
firestore_v1_stub = sys.modules.setdefault('google.cloud.firestore_v1', types.ModuleType('google.cloud.firestore_v1'))
firestore_v1_stub.FieldFilter = MagicMock
firestore_v1_stub.transactional = lambda func: func
cloud_stub.firestore = firestore_stub
google_stub.cloud = cloud_stub

if 'database._client' not in sys.modules:
    client_stub = types.ModuleType('database._client')
    client_stub.db = MagicMock()
    client_stub.document_id_from_seed = lambda seed: 'id-' + str(abs(hash(seed)) % (10**12))
    sys.modules['database._client'] = client_stub
else:
    sys.modules['database._client'].db = getattr(sys.modules['database._client'], 'db', MagicMock())

from database import entities, memory_ledger  # noqa: E402
from models.memories import SubjectAttribution  # noqa: E402
from utils.conversations.subjects import infer_subject_from_segments  # noqa: E402


def test_infer_subject_from_user_only_segments():
    subject_id, attribution = infer_subject_from_segments([SimpleNamespace(is_user=True, person_id=None)])

    assert subject_id == entities.USER_ENTITY_ID
    assert attribution == SubjectAttribution.user


def test_infer_subject_from_non_user_person_segments():
    subject_id, attribution = infer_subject_from_segments([SimpleNamespace(is_user=False, person_id='p1')])

    assert subject_id == entities.person_entity_id('p1')
    assert attribution == SubjectAttribution.third_party


def test_infer_subject_from_mixed_segments_is_unknown():
    subject_id, attribution = infer_subject_from_segments(
        [SimpleNamespace(is_user=True, person_id=None), SimpleNamespace(is_user=False, person_id='p1')]
    )

    assert subject_id is None
    assert attribution == SubjectAttribution.unknown


def test_merge_then_split_entities_round_trips_state():
    original = {
        'person:p1': {'id': 'person:p1', 'label': 'Sarah Chen', 'aliases': []},
        'person:p2': {'id': 'person:p2', 'label': 'Sarah from sales', 'aliases': []},
    }
    merged = entities.apply_entity_mutations(
        original,
        [memory_ledger.merge_entities('person:p1', 'person:p2', evidence={'source': 'test'}, confidence=0.9)],
    )

    restored = entities.apply_entity_mutations(
        merged,
        [
            memory_ledger.split_entity(
                'person:p1',
                into=[original['person:p1'], original['person:p2']],
                reason='wrong Sarah merge',
            )
        ],
    )

    assert set(merged) == {'person:p1'}
    assert restored == original
