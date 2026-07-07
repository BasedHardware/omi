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
        ps.users_db, 'get_person_by_handle', return_value=None
    ), patch.object(ps.users_db, 'get_people_by_name', return_value=[person]), patch.object(
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
        ps.users_db, 'get_people_by_name', return_value=[]
    ), patch.object(ps.users_db, 'get_person_by_handle', return_value=None):
        out = ps.get_person_context('uid', 'Nobody')
    assert "don't have anyone" in out.lower()


def test_resolve_prefers_id_first():
    with patch.object(ps.users_db, 'get_person', return_value={'id': 'p9', 'name': 'ById'}) as by_id:
        assert ps.resolve_person('uid', 'p9')['name'] == 'ById'
        by_id.assert_called_once()


def test_resolve_handle_wins_before_name():
    # An input that is a valid handle for exactly one person must resolve directly,
    # never be reported as an ambiguous name — handle is tried before the name lookup.
    ambiguous_names = [{'id': 'a', 'name': 'x'}, {'id': 'b', 'name': 'x'}]
    with patch.object(ps.users_db, 'get_person', return_value=None), patch.object(
        ps.users_db, 'get_person_by_handle', return_value={'id': 'h1', 'name': 'ByHandle'}
    ), patch.object(ps.users_db, 'get_people_by_name', return_value=ambiguous_names) as by_name:
        resolved = ps.resolve_person('uid', '+15551234567')
        assert not ps.is_ambiguous(resolved)
        assert resolved['id'] == 'h1'
        by_name.assert_not_called()


def test_resolve_ambiguous_name_does_not_guess():
    # Two people share the display name — resolve must NOT pick one arbitrarily.
    matches = [{'id': 'a', 'name': 'Sam'}, {'id': 'b', 'name': 'Sam'}]
    with patch.object(ps.users_db, 'get_person', return_value=None), patch.object(
        ps.users_db, 'get_people_by_name', return_value=matches
    ), patch.object(ps.users_db, 'get_person_by_handle', return_value=None):
        resolved = ps.resolve_person('uid', 'Sam')
        assert ps.is_ambiguous(resolved)
        # The context call surfaces a disambiguation ask instead of leaking a contact.
        out = ps.get_person_context('uid', 'Sam')
        assert 'multiple people' in out.lower()


def test_resolve_single_name_match_resolves():
    with patch.object(ps.users_db, 'get_person', return_value=None), patch.object(
        ps.users_db, 'get_person_by_handle', return_value=None
    ), patch.object(ps.users_db, 'get_people_by_name', return_value=[{'id': 'a', 'name': 'Sam'}]):
        resolved = ps.resolve_person('uid', 'Sam')
        assert not ps.is_ambiguous(resolved)
        assert resolved['id'] == 'a'


def test_resolve_case_insensitive_name_fallback():
    """A display name typed with different casing still resolves (Firestore '==' is
    case-sensitive, so we scan the roster and match on lowercased name)."""
    person = {'id': 'pM', 'name': 'Mila Finch', 'relationship': 'friend'}
    with patch.object(ps.users_db, 'get_person', return_value=None), patch.object(
        ps.users_db, 'get_person_by_handle', return_value=None
    ), patch.object(ps.users_db, 'get_people_by_name', return_value=[]), patch.object(
        ps.users_db, 'get_people', return_value=[{'id': 'pX', 'name': 'Bob'}, person]
    ):
        r = ps.resolve_person('uid', 'mila finch')
    assert isinstance(r, dict) and r['id'] == 'pM'


def test_resolve_case_insensitive_ambiguous():
    with patch.object(ps.users_db, 'get_person', return_value=None), patch.object(
        ps.users_db, 'get_person_by_handle', return_value=None
    ), patch.object(ps.users_db, 'get_people_by_name', return_value=[]), patch.object(
        ps.users_db, 'get_people', return_value=[{'id': 'a', 'name': 'Sam'}, {'id': 'b', 'name': 'sam'}]
    ):
        r = ps.resolve_person('uid', 'SAM')
    assert ps.is_ambiguous(r)
