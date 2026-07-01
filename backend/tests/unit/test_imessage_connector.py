import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# The connector imports process_conversation, whose transitive import chain would
# otherwise construct real Firestore/LLM clients (and hit the network) at import
# time. Install the shared unit-test stubs before importing the module.
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

import utils.imessage_connector as ic  # noqa: E402
from models.imessage import IMessageIngestRequest, IMessageMessage, IMessageThread  # noqa: E402

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _msg(guid, text, from_me, secs, handle=None):
    return IMessageMessage(
        guid=guid, text=text, is_from_me=from_me, timestamp=BASE + timedelta(seconds=secs), handle=handle
    )


def test_build_conversation_attribution():
    thread = IMessageThread(chat_guid='c1', display_name='Alice')
    msgs = [_msg('g1', 'hey there', False, 0, '+15551234567'), _msg('g2', 'hi Alice', True, 5)]
    create = ic._build_conversation(thread, msgs, {'+15551234567': 'p_alice'}, 'en')

    assert create is not None
    assert create.source.value == 'imessage'
    segs = create.transcript_segments
    assert len(segs) == 2
    # Contact message: not user, attributed to the person, non-zero speaker.
    assert segs[0].is_user is False
    assert segs[0].person_id == 'p_alice'
    assert segs[0].speaker == 'SPEAKER_01'
    assert segs[0].stt_provider == 'imessage'
    # User message: is_user, no person, speaker 0.
    assert segs[1].is_user is True
    assert segs[1].person_id is None
    assert segs[1].speaker == 'SPEAKER_00'
    assert create.started_at <= create.finished_at


def test_build_conversation_group_distinct_speakers():
    thread = IMessageThread(chat_guid='c2', display_name='Trip', is_group=True)
    msgs = [
        _msg('g1', 'yo', False, 0, '+111'),
        _msg('g2', 'sup', False, 1, '+222'),
        _msg('g3', 'me', True, 2),
        _msg('g4', 'again', False, 3, '+111'),
    ]
    create = ic._build_conversation(thread, msgs, {'+111': 'p1', '+222': 'p2'}, 'en')
    segs = create.transcript_segments
    # Same handle -> same speaker; distinct handles -> distinct speakers.
    assert segs[0].speaker == segs[3].speaker
    assert segs[0].speaker != segs[1].speaker
    assert segs[2].speaker == 'SPEAKER_00'


def test_build_conversation_skips_empty():
    thread = IMessageThread(chat_guid='c1', display_name='Alice')
    msgs = [_msg('g1', '   ', False, 0, '+1')]
    assert ic._build_conversation(thread, msgs, {}, 'en') is None


def test_get_settings_defaults():
    with patch.object(ic.users_db, 'get_integration', return_value=None):
        s = ic.get_settings('uid')
        assert s.enabled is False
        assert s.backfill_days == 90


async def _fake_run_blocking(executor, fn, *args, **kwargs):
    return fn(*args, **kwargs)


def test_ingest_dedup_and_people():
    """Already-processed message GUIDs are skipped; new contacts are upserted."""
    doc_state = {'processed_guids': ['g_old']}

    def fake_get_integration(uid, key):
        return dict(doc_state)

    def fake_set_integration(uid, key, data):
        doc_state.clear()
        doc_state.update(data)

    people = {}

    def fake_get_or_create(uid, handle, name):
        pid = f'p_{handle}'
        people[handle] = pid
        return {'id': pid, 'name': name or handle, 'handles': [handle]}

    started = []

    def fake_start_bg(coro, name=None):
        coro.close()  # don't actually run post-processing
        started.append(name)
        return None

    req = IMessageIngestRequest(
        threads=[
            IMessageThread(
                chat_guid='c1',
                display_name='Alice',
                messages=[
                    _msg('g_old', 'seen before', False, 0, '+1'),
                    _msg('g_new', 'brand new', False, 1, '+1'),
                    _msg('g_me', 'my reply', True, 2),
                ],
            )
        ],
        language='en',
        last_rowid=42,
    )

    with patch.object(ic, 'run_blocking', _fake_run_blocking), patch.object(
        ic, 'start_background_task', fake_start_bg
    ), patch.object(ic.users_db, 'get_integration', fake_get_integration), patch.object(
        ic.users_db, 'set_integration', fake_set_integration
    ), patch.object(
        ic.users_db, 'get_or_create_person_by_handle', fake_get_or_create
    ):
        resp = asyncio.run(ic.ingest_threads('uid', req))

    assert resp.success is True
    assert resp.skipped_duplicates == 1  # g_old
    assert resp.conversations_created == 1
    assert resp.people_upserted == 1
    assert resp.messages_ingested == 2  # g_new + g_me
    assert doc_state['connected'] is True
    assert doc_state['enabled'] is True
    assert doc_state['last_rowid'] == 42
    assert 'g_new' in doc_state['processed_guids']
    assert started  # background processing kicked off
