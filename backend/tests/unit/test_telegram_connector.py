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

import utils.telegram_connector as tc  # noqa: E402
from models.telegram import TelegramIngestRequest, TelegramMessage, TelegramThread  # noqa: E402

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _msg(mid, text, from_me, secs, handle=None):
    return TelegramMessage(
        message_id=mid, text=text, is_from_me=from_me, timestamp=BASE + timedelta(seconds=secs), handle=handle
    )


def test_build_new_conversation_uses_deterministic_id_and_telegram_source():
    conv_id = tc.telegram_conversation_id('uid', 'c1', '2026-01-01')
    segs, _ = tc._build_segments([_msg('m1', 'hi', False, 0, 'tg:111')], BASE, {'tg:111': 'p1'}, {}, 1)
    conv = tc._build_new_conversation(conv_id, BASE, BASE, segs, 'en')
    # The deterministic id is preserved so same chat+day converges across syncs.
    assert conv.id == conv_id
    assert conv.source.value == 'telegram'
    assert conv.started_at <= conv.finished_at


def test_processed_message_key_stable():
    a = tc.processed_message_key('c1', 'm1')
    b = tc.processed_message_key('c1', 'm1')
    c = tc.processed_message_key('c1', 'm2')
    assert a == b and a != c


def test_get_settings_defaults():
    with patch.object(tc.users_db, 'get_integration', return_value=None):
        s = tc.get_settings('uid')
        assert s.enabled is False
        assert s.backfill_days == 90


async def _fake_run_blocking(executor, fn, *args, **kwargs):
    return fn(*args, **kwargs)


def test_ingest_dedup_windowing_and_people():
    """Empty messages ignored; ledger-claimed messages skipped; surviving messages
    grouped into one (chat, day) window; connect+consent recorded on the doc."""
    doc_state = {}

    def fake_get_integration(uid, key):
        return dict(doc_state)

    def fake_set_integration(uid, key, data):
        doc_state.clear()
        doc_state.update(data)

    def fake_get_or_create(uid, handle, name, source='imessage'):
        assert source == 'telegram'  # telegram namespaces its People
        return {'id': f'p_{handle}', 'name': name or handle, 'handles': [handle]}

    started = []

    def fake_start_bg(coro, name=None):
        coro.close()  # don't actually run post-processing
        started.append(name)
        return None

    req = TelegramIngestRequest(
        threads=[
            TelegramThread(
                chat_id='c1',
                display_name='Alice',
                messages=[
                    _msg('m_blank', '   ', False, 1, 'tg:1'),  # empty -> ignored
                    _msg('m_new', 'brand new', False, 2, 'tg:1'),
                    _msg('m_me', 'my reply', True, 3),
                ],
            )
        ],
        language='en',
    )

    with patch.object(tc, 'run_blocking', _fake_run_blocking), patch.object(
        tc, 'start_background_task', fake_start_bg
    ), patch.object(tc.users_db, 'get_integration', fake_get_integration), patch.object(
        tc.users_db, 'set_integration', fake_set_integration
    ), patch.object(
        tc.users_db, 'get_or_create_person_by_handle', fake_get_or_create
    ), patch.object(
        tc.telegram_db, 'filter_claimed_keys', return_value=set()
    ), patch.object(
        # Insert-first durable persist: every message is won and the (chat, day)
        # window is created synchronously before responding.
        tc.telegram_db,
        'claim_message',
        return_value=True,
    ), patch.object(
        tc.conversations_db, 'create_conversation_if_absent', return_value=True
    ):
        resp = asyncio.run(tc.ingest_threads('uid', req))

    assert resp.success is True
    assert resp.conversations_created == 1  # m_new + m_me collapse into one (c1, day) window
    assert resp.people_upserted == 1
    assert resp.messages_ingested == 2  # m_new + m_me (m_blank ignored)
    assert doc_state['connected'] is True
    assert doc_state['enabled'] is True
    assert doc_state['conversations_ingested'] == 1
    assert started  # background processing kicked off


def test_ingest_skips_opted_out_and_ledger_claimed():
    """Opted-out sender handles never ingest, and messages already in the ledger are
    reported as skipped duplicates."""
    doc_state = {'opted_out_handles': ['tg:blocked']}

    def fake_get_integration(uid, key):
        return dict(doc_state)

    def fake_set_integration(uid, key, data):
        doc_state.clear()
        doc_state.update(data)

    def fake_get_or_create(uid, handle, name, source='imessage'):
        return {'id': f'p_{handle}', 'name': name or handle, 'handles': [handle]}

    def fake_start_bg(coro, name=None):
        coro.close()
        return None

    # m_seen is already claimed in the ledger -> skipped as a duplicate.
    seen_key = tc.processed_message_key('c1', 'm_seen')

    req = TelegramIngestRequest(
        threads=[
            TelegramThread(
                chat_id='c1',
                display_name='Alice',
                messages=[
                    _msg('m_seen', 'already ingested', False, 0, 'tg:1'),
                    _msg('m_blocked', 'from a blocked sender', False, 1, 'tg:blocked'),
                    _msg('m_ok', 'fresh from allowed sender', False, 2, 'tg:1'),
                ],
            )
        ],
        language='en',
    )

    with patch.object(tc, 'run_blocking', _fake_run_blocking), patch.object(
        tc, 'start_background_task', fake_start_bg
    ), patch.object(tc.users_db, 'get_integration', fake_get_integration), patch.object(
        tc.users_db, 'set_integration', fake_set_integration
    ), patch.object(
        tc.users_db, 'get_or_create_person_by_handle', fake_get_or_create
    ), patch.object(
        tc.telegram_db, 'filter_claimed_keys', return_value={seen_key}
    ), patch.object(
        tc.telegram_db, 'claim_message', return_value=True
    ), patch.object(
        tc.conversations_db, 'create_conversation_if_absent', return_value=True
    ):
        resp = asyncio.run(tc.ingest_threads('uid', req))

    # Only m_ok survives: m_seen deduped by the ledger, m_blocked opted out.
    assert resp.messages_ingested == 1
    assert resp.skipped_duplicates == 1  # m_seen (ledger)
    assert resp.people_upserted == 1
