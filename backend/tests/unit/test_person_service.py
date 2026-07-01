import os
import sys
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from tests.unit.memory_import_isolation import (  # noqa: E402
    ensure_utils_memory_packages_importable,
    install_canonical_write_runtime_stubs,
    install_database_client_stub,
    install_ws_i_heavy_import_stubs,
)

ensure_utils_memory_packages_importable(str(BACKEND_DIR))
install_database_client_stub()
install_canonical_write_runtime_stubs()
install_ws_i_heavy_import_stubs()

import utils.retrieval.tool_services.person_service as ps  # noqa: E402


def test_context_assembles_profile_facts_and_conversations():
    person = {
        'id': 'p1',
        'name': 'Alice',
        'relationship': 'friend',
        'profile_summary': 'Alice is a designer in NYC.',
        'tone_notes': 'casual, lots of emojis',
    }
    convo = {
        'structured': {'title': 'Dinner plans'},
        'transcript_segments': [
            {
                'text': 'want to grab dinner?',
                'is_user': False,
                'person_id': 'p1',
                'speaker': 'SPEAKER_01',
                'start': 0,
                'end': 1,
            },
            {'text': 'yes lets go', 'is_user': True, 'speaker': 'SPEAKER_00', 'start': 1, 'end': 2},
        ],
    }
    with patch.object(ps.users_db, 'get_person', return_value=None), patch.object(
        ps.users_db, 'get_person_by_name', return_value=person
    ), patch.object(
        ps.memories_db, 'get_memories_by_subject_entity', return_value=[{'content': 'Alice just adopted a dog'}]
    ), patch.object(
        ps.conversations_db, 'get_conversations_by_person_id', return_value=[convo]
    ):
        out = ps.get_person_context('uid', 'Alice')

    assert 'Context about Alice' in out
    assert 'friend' in out
    assert 'Alice is a designer in NYC.' in out
    assert 'casual, lots of emojis' in out
    assert 'Alice just adopted a dog' in out
    assert 'Dinner plans' in out
    assert 'want to grab dinner?' in out
    # The contact's segment renders under their name, not "Speaker N".
    assert 'Alice: want to grab dinner?' in out


def test_unknown_person_is_honest():
    with patch.object(ps.users_db, 'get_person', return_value=None), patch.object(
        ps.users_db, 'get_person_by_name', return_value=None
    ), patch.object(ps.users_db, 'get_person_by_handle', return_value=None):
        out = ps.get_person_context('uid', 'Nobody')
    assert "don't have anyone" in out.lower()


def test_resolve_prefers_id_then_name_then_handle():
    with patch.object(ps.users_db, 'get_person', return_value={'id': 'p9', 'name': 'ById'}) as by_id:
        assert ps.resolve_person('uid', 'p9')['name'] == 'ById'
        by_id.assert_called_once()
