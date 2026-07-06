"""Unit tests for Phase 1 `enrich_persons_from_conversation`.

Verifies the orchestrator:
- runs ONLY for texting-source conversations (imessage/telegram/whatsapp),
- keys extracted facts to each person's `subject_entity_id` with third_party attribution,
- falls back to segment.person_id when `conversation.person_ids` is empty,
- skips unknown persons and never raises into the caller.

The extractor + writer are mocked so no LLM/DB/network is touched.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import utils.memory.person_messaging_enrichment as e  # noqa: E402
from models.conversation_enums import ConversationSource  # noqa: E402
from models.memories import Memory, MemoryCategory, SubjectAttribution  # noqa: E402


def _seg(person_id, sid='s1'):
    return SimpleNamespace(id=sid, start=0.0, end=1.0, person_id=person_id)


def _conv(source, person_ids, segments=None):
    return SimpleNamespace(
        id='conv_1',
        source=source,
        person_ids=person_ids,
        transcript_segments=segments if segments is not None else [_seg('p_alice')],
    )


def _mem():
    return Memory(content='Alice moved to Austin', category=MemoryCategory.system)


def test_non_texting_source_is_skipped():
    conv = _conv(ConversationSource.omi, ['p_alice'])
    with patch.object(e, 'extract_person_messaging_memories') as extract, patch.object(
        e, 'write_subject_memories'
    ) as write:
        out = e.enrich_persons_from_conversation('uid1', conv, language='en')
    assert out == {}
    extract.assert_not_called()
    write.assert_not_called()


def test_texting_source_person_keyed_write():
    conv = _conv(ConversationSource.imessage, ['p_alice'])
    with patch.object(e, 'get_prompt_memories', return_value=('Me', '')), patch.object(
        e.users_db, 'get_person', return_value={'id': 'p_alice', 'name': 'Alice'}
    ), patch.object(e.memories_db, 'get_memories_by_subject_entity', return_value=[]), patch.object(
        e, 'extract_person_messaging_memories', return_value=[_mem()]
    ) as extract, patch.object(
        e, 'write_subject_memories', return_value=1
    ) as write:
        out = e.enrich_persons_from_conversation('uid1', conv, language='en')

    assert out == {'p_alice': 1}
    # Extractor called with the resolved person name.
    assert extract.call_args[0][1] == 'Alice'
    # Writer keyed to the person's subject entity id with third_party attribution.
    wkwargs = write.call_args.kwargs
    assert wkwargs['subject_entity_id'] == 'person:p_alice'
    assert wkwargs['subject_attribution'] == SubjectAttribution.third_party
    assert wkwargs['source_id'] == 'conv_1'


def test_person_ids_fallback_from_segments():
    conv = _conv(ConversationSource.telegram, [], segments=[_seg('p_bob')])
    with patch.object(e, 'get_prompt_memories', return_value=('Me', '')), patch.object(
        e.users_db, 'get_person', return_value={'id': 'p_bob', 'name': 'Bob'}
    ), patch.object(e.memories_db, 'get_memories_by_subject_entity', return_value=[]), patch.object(
        e, 'extract_person_messaging_memories', return_value=[_mem()]
    ), patch.object(
        e, 'write_subject_memories', return_value=1
    ) as write:
        out = e.enrich_persons_from_conversation('uid1', conv, language='en')

    assert out == {'p_bob': 1}
    assert write.call_args.kwargs['subject_entity_id'] == 'person:p_bob'


def test_unknown_person_is_skipped():
    conv = _conv(ConversationSource.whatsapp, ['p_ghost'])
    with patch.object(e, 'get_prompt_memories', return_value=('Me', '')), patch.object(
        e.users_db, 'get_person', return_value=None
    ), patch.object(e, 'extract_person_messaging_memories') as extract, patch.object(
        e, 'write_subject_memories'
    ) as write:
        out = e.enrich_persons_from_conversation('uid1', conv, language='en')

    assert out == {}
    extract.assert_not_called()
    write.assert_not_called()


def test_no_facts_records_zero_and_skips_write():
    conv = _conv(ConversationSource.imessage, ['p_alice'])
    with patch.object(e, 'get_prompt_memories', return_value=('Me', '')), patch.object(
        e.users_db, 'get_person', return_value={'id': 'p_alice', 'name': 'Alice'}
    ), patch.object(e.memories_db, 'get_memories_by_subject_entity', return_value=[]), patch.object(
        e, 'extract_person_messaging_memories', return_value=[]
    ), patch.object(
        e, 'write_subject_memories'
    ) as write:
        out = e.enrich_persons_from_conversation('uid1', conv, language='en')

    assert out == {'p_alice': 0}
    write.assert_not_called()


def test_string_source_value_is_recognized():
    """Source may already be a plain string (schemaless reads) — still gate correctly."""
    conv = _conv(ConversationSource.imessage.value, ['p_alice'])
    with patch.object(e, 'get_prompt_memories', return_value=('Me', '')), patch.object(
        e.users_db, 'get_person', return_value={'id': 'p_alice', 'name': 'Alice'}
    ), patch.object(e.memories_db, 'get_memories_by_subject_entity', return_value=[]), patch.object(
        e, 'extract_person_messaging_memories', return_value=[_mem()]
    ), patch.object(
        e, 'write_subject_memories', return_value=2
    ):
        out = e.enrich_persons_from_conversation('uid1', conv, language='en')
    assert out == {'p_alice': 2}


def test_never_raises_into_caller():
    conv = _conv(ConversationSource.imessage, ['p_alice'])
    with patch.object(e, 'get_prompt_memories', side_effect=RuntimeError('boom')):
        out = e.enrich_persons_from_conversation('uid1', conv, language='en')
    assert out == {}


def test_group_conversation_over_cap_is_skipped():
    """Cost guard: a multi-participant window would fire one full-transcript extraction per
    person, so above the participant cap (1 by default) we skip and leave it to the existing
    whole-conversation extraction."""
    conv = _conv(ConversationSource.imessage, ['p_alice', 'p_bob', 'p_carol'])
    with patch.object(e, 'get_prompt_memories', return_value=('Me', '')), patch.object(
        e, 'extract_person_messaging_memories'
    ) as extract, patch.object(e, 'write_subject_memories') as write:
        out = e.enrich_persons_from_conversation('uid1', conv, language='en')
    assert out == {}
    extract.assert_not_called()
    write.assert_not_called()


def test_kill_switch_disables_enrichment():
    conv = _conv(ConversationSource.imessage, ['p_alice'])
    with patch.object(e, '_ENRICHMENT_ENABLED', False), patch.object(
        e, 'extract_person_messaging_memories'
    ) as extract, patch.object(e, 'write_subject_memories') as write:
        out = e.enrich_persons_from_conversation('uid1', conv, language='en')
    assert out == {}
    extract.assert_not_called()
    write.assert_not_called()


def test_last_contacted_at_set_when_newer():
    from datetime import datetime, timezone

    when = datetime(2026, 7, 1, tzinfo=timezone.utc)
    conv = _conv(ConversationSource.imessage, ['p_alice'])
    conv.finished_at = when
    with patch.object(e, 'get_prompt_memories', return_value=('Me', '')), patch.object(
        e.users_db, 'get_person', return_value={'id': 'p_alice', 'name': 'Alice', 'last_contacted_at': None}
    ), patch.object(e.memories_db, 'get_memories_by_subject_entity', return_value=[]), patch.object(
        e, 'extract_person_messaging_memories', return_value=[]
    ), patch.object(
        e.users_db, 'update_person_profile'
    ) as upd:
        e.enrich_persons_from_conversation('uid1', conv, language='en')
    upd.assert_called_once_with('uid1', 'p_alice', {'last_contacted_at': when})


def test_last_contacted_at_not_moved_backward():
    from datetime import datetime, timezone

    older = datetime(2026, 6, 1, tzinfo=timezone.utc)
    newer = datetime(2026, 7, 1, tzinfo=timezone.utc)
    conv = _conv(ConversationSource.imessage, ['p_alice'])
    conv.finished_at = older  # an out-of-order backfill window
    with patch.object(e, 'get_prompt_memories', return_value=('Me', '')), patch.object(
        e.users_db, 'get_person', return_value={'id': 'p_alice', 'name': 'Alice', 'last_contacted_at': newer}
    ), patch.object(e.memories_db, 'get_memories_by_subject_entity', return_value=[]), patch.object(
        e, 'extract_person_messaging_memories', return_value=[]
    ), patch.object(
        e.users_db, 'update_person_profile'
    ) as upd:
        e.enrich_persons_from_conversation('uid1', conv, language='en')
    upd.assert_not_called()
