import os
import sys
from datetime import datetime, timedelta, timezone
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

import utils.llm.user_tone_guide as utg  # noqa: E402

_TEXTING_SOURCE = next(iter(utg._TEXTING_SOURCES))


def _convo(source, user_texts):
    return {
        'source': source,
        'transcript_segments': [{'text': t, 'is_user': True} for t in user_texts],
    }


def _many_samples(n):
    # Distinct, short, genuine texting lines so they survive the voice-sample filter/dedupe.
    return [f'msg number {i} lol' for i in range(n)]


# --- staleness gating -------------------------------------------------------


def test_needs_refresh():
    assert utg._needs_refresh(None) is True
    assert utg._needs_refresh({'guide_text': ''}) is True  # empty text
    assert utg._needs_refresh({'guide_text': 'x'}) is True  # no timestamp
    fresh = {'guide_text': 'x', 'generated_at': datetime.now(timezone.utc).isoformat()}
    assert utg._needs_refresh(fresh) is False
    stale_dt = datetime.now(timezone.utc) - timedelta(days=utg.TONE_GUIDE_STALE_DAYS + 1)
    assert utg._needs_refresh({'guide_text': 'x', 'generated_at': stale_dt.isoformat()}) is True
    # Malformed timestamp => treat as needing refresh, never raise.
    assert utg._needs_refresh({'guide_text': 'x', 'generated_at': 'not-a-date'}) is True


def test_skips_when_fresh_without_llm_or_write():
    fresh = {'guide_text': 'x', 'generated_at': datetime.now(timezone.utc).isoformat()}
    with patch.object(utg.users_db, 'get_user_tone_guide', return_value=fresh), patch.object(
        utg.users_db, 'update_user_tone_guide'
    ) as upd, patch.object(utg, 'get_llm') as gl:
        assert utg.generate_user_tone_guide('uid', force=False) is False
        upd.assert_not_called()
        gl.assert_not_called()


# --- sample collection ------------------------------------------------------


def test_collect_filters_to_texting_sources_and_voice_samples():
    convos = [
        _convo(_TEXTING_SOURCE, ['hey there', 'https://example.com/a-link', 'ok cool']),
        _convo('audio', ['this is voice-captured speech, not texting']),  # non-texting source
    ]
    with patch.object(utg.conversations_db, 'get_conversations', return_value=convos):
        samples = utg._collect_outgoing_samples('uid')
    assert 'hey there' in samples
    assert 'ok cool' in samples
    assert all('http' not in s for s in samples)  # link dropped by voice-sample filter
    assert 'this is voice-captured speech, not texting' not in samples  # wrong source


def test_recipient_notes_sorted_and_capped():
    people = [
        {'name': 'A', 'tone_notes': 'warm', 'message_count': 5},
        {'name': 'B', 'tone_notes': 'terse', 'message_count': 50},
        {'name': 'C', 'tone_notes': '', 'message_count': 100},  # no tone_notes -> skipped
        {'name': 'D', 'tone_notes': 'formal', 'message_count': 1},
    ]
    with patch.object(utg.users_db, 'get_people', return_value=people):
        notes = utg._collect_recipient_notes('uid')
    names = [n['name'] for n in notes]
    assert names[0] == 'B'  # highest message_count first
    assert 'C' not in names  # skipped: no tone_notes
    assert len(notes) <= utg.TOP_PEOPLE_FOR_RECIPIENTS


# --- generation -------------------------------------------------------------


def test_skips_when_too_few_samples_even_with_force():
    convos = [_convo(_TEXTING_SOURCE, _many_samples(utg.MIN_SAMPLES_FOR_GUIDE - 1))]
    with patch.object(utg.users_db, 'get_user_tone_guide', return_value=None), patch.object(
        utg.conversations_db, 'get_conversations', return_value=convos
    ), patch.object(utg.users_db, 'update_user_tone_guide') as upd, patch.object(utg, 'get_llm') as gl:
        assert utg.generate_user_tone_guide('uid', force=True) is False
        upd.assert_not_called()
        gl.assert_not_called()


def test_generates_and_stores_when_enough_samples():
    convos = [_convo(_TEXTING_SOURCE, _many_samples(utg.MIN_SAMPLES_FOR_GUIDE + 5))]
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = SimpleNamespace(
        content='## Voice\nwrites in all lowercase.\n\n## By recipient\n(none)'
    )
    with patch.object(utg.users_db, 'get_user_tone_guide', return_value=None), patch.object(
        utg.conversations_db, 'get_conversations', return_value=convos
    ), patch.object(utg.users_db, 'get_people', return_value=[]), patch.object(
        utg, 'get_llm', return_value=fake_llm
    ), patch.object(
        utg.users_db, 'update_user_tone_guide'
    ) as upd:
        assert utg.generate_user_tone_guide('uid', force=True) is True
        upd.assert_called_once()
        kwargs = upd.call_args.kwargs
        assert kwargs['guide_text'].startswith('## Voice')
        assert kwargs['sample_count'] >= utg.MIN_SAMPLES_FOR_GUIDE
        assert kwargs['generated_at']  # ISO timestamp recorded


def test_empty_llm_output_is_not_stored():
    convos = [_convo(_TEXTING_SOURCE, _many_samples(utg.MIN_SAMPLES_FOR_GUIDE + 5))]
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = SimpleNamespace(content='   ')
    with patch.object(utg.users_db, 'get_user_tone_guide', return_value=None), patch.object(
        utg.conversations_db, 'get_conversations', return_value=convos
    ), patch.object(utg.users_db, 'get_people', return_value=[]), patch.object(
        utg, 'get_llm', return_value=fake_llm
    ), patch.object(
        utg.users_db, 'update_user_tone_guide'
    ) as upd:
        assert utg.generate_user_tone_guide('uid', force=True) is False
        upd.assert_not_called()
