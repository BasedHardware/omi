import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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

import utils.llm.person_profile as pp  # noqa: E402


def _segments(n):
    segs = []
    for i in range(n):
        is_user = i % 2 == 0
        segs.append(
            {
                'text': f'message {i}',
                'is_user': is_user,
                'person_id': None if is_user else 'p1',
                'speaker': 'SPEAKER_00' if is_user else 'SPEAKER_01',
                'start': float(i),
                'end': float(i) + 1,
            }
        )
    return segs


def test_needs_refresh():
    assert pp._needs_refresh({}) is True
    assert pp._needs_refresh({'profile_summary': 'x'}) is True  # no timestamp
    fresh = {'profile_summary': 'x', 'profile_updated_at': datetime.now(timezone.utc)}
    assert pp._needs_refresh(fresh) is False


def test_extract_json_handles_fences():
    assert pp._extract_json('```json\n{"a": 1}\n```') == {'a': 1}
    assert pp._extract_json('prefix {"a": 2} suffix') == {'a': 2}
    assert pp._extract_json('not json') is None


def test_generate_person_profile_stores_parsed_fields():
    person = {'id': 'p1', 'name': 'Alice'}
    convo = {'transcript_segments': _segments(8)}
    llm_json = '{"relationship": "friend", "profile_summary": "Alice is great.", "tone_notes": "casual"}'

    saved = {}

    def fake_update(uid, person_id, fields):
        saved.update(fields)

    with patch.object(pp.users_db, 'get_person', return_value=person), patch.object(
        pp.conversations_db, 'get_conversations_by_person_id', return_value=[convo]
    ), patch.object(pp.memories_db, 'get_memories_by_subject_entity', return_value=[]), patch.object(
        pp.users_db, 'update_person_profile', side_effect=fake_update
    ), patch.object(
        pp, 'get_llm', return_value=SimpleNamespace(invoke=lambda prompt: SimpleNamespace(content=llm_json))
    ):
        updated = pp.generate_person_profile('uid', 'p1', force=True)

    assert updated is True
    assert saved['relationship'] == 'friend'
    assert saved['profile_summary'] == 'Alice is great.'
    assert saved['tone_notes'] == 'casual'
    assert saved['message_count'] == 8


def test_generate_person_profile_skips_when_thin():
    person = {'id': 'p1', 'name': 'Alice'}
    with patch.object(pp.users_db, 'get_person', return_value=person), patch.object(
        pp.conversations_db, 'get_conversations_by_person_id', return_value=[{'transcript_segments': _segments(2)}]
    ), patch.object(pp.memories_db, 'get_memories_by_subject_entity', return_value=[]), patch.object(
        pp.users_db, 'update_person_profile'
    ) as upd:
        updated = pp.generate_person_profile('uid', 'p1', force=True)
    assert updated is False
    upd.assert_not_called()


def test_generate_person_profile_does_not_bump_timestamp_on_empty_llm_output():
    # A valid dict with no usable profile fields must NOT persist or bump
    # profile_updated_at — otherwise the staleness clock resets and retries are
    # suppressed for PROFILE_STALE_DAYS, masking a failed refresh.
    person = {'id': 'p1', 'name': 'Alice'}
    convo = {'transcript_segments': _segments(8)}
    empty_json = '{"relationship": "", "profile_summary": "  ", "tone_notes": null}'
    invoke_mock = MagicMock(return_value=SimpleNamespace(content=empty_json))
    with patch.object(pp.users_db, 'get_person', return_value=person), patch.object(
        pp.conversations_db, 'get_conversations_by_person_id', return_value=[convo]
    ), patch.object(pp.memories_db, 'get_memories_by_subject_entity', return_value=[]), patch.object(
        pp.users_db, 'update_person_profile'
    ) as upd, patch.object(
        pp, 'get_llm', return_value=SimpleNamespace(invoke=invoke_mock)
    ):
        updated = pp.generate_person_profile('uid', 'p1', force=True)
    assert updated is False
    # The empty-output branch must actually be reached — guard against a future
    # early-return that would make this test pass without exercising the LLM path.
    invoke_mock.assert_called_once()
    upd.assert_not_called()
