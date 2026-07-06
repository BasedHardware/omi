"""Unit tests for Phase 1 `extract_person_messaging_memories`.

Verifies the extractor:
- short-circuits on empty/too-short transcripts,
- returns the LLM-produced high-recall facts on a real thread, and
- fails closed (returns []) on any LLM/parse error.

The LLM chain is replaced with a fake pipe so no network/credentials are touched.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import utils.llm.person_messaging as pm  # noqa: E402
from models.memories import Memory, MemoryCategory  # noqa: E402
from models.transcript_segment import TranscriptSegment  # noqa: E402


class _FakeChain:
    """Stands in for `prompt | get_llm(...) | parser`. Absorbs the `|` composition and
    returns a preset response (or raises) on `.invoke`."""

    def __init__(self, response):
        self._response = response

    def __or__(self, other):
        return self

    def invoke(self, inputs):
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _seg(text, is_user, person_id=None, start=0.0):
    return TranscriptSegment(text=text, is_user=is_user, person_id=person_id, start=start, end=start + 1.0)


def _thread():
    return [
        _seg('Hey, I just started a new job at Stripe as a backend engineer.', False, person_id='p_alice', start=0.0),
        _seg('That is awesome, congrats!', True, start=2.0),
        _seg('Thanks. Also I moved to Austin last month.', False, person_id='p_alice', start=4.0),
    ]


def test_returns_empty_on_short_transcript():
    segs = [_seg('ok', False, person_id='p_alice')]
    with patch.object(pm.users_db, 'get_people_by_ids', return_value=[]):
        out = pm.extract_person_messaging_memories(
            'uid1', 'Alice', segs, user_name='Me', memories_str='', language='en'
        )
    assert out == []


def test_returns_extracted_facts():
    facts = [
        Memory(content='Alice started a job at Stripe as backend engineer', category=MemoryCategory.system),
        Memory(content='Alice moved to Austin', category=MemoryCategory.system),
    ]
    response = SimpleNamespace(facts=facts)
    with patch.object(pm.users_db, 'get_people_by_ids', return_value=[]), patch.object(
        pm, 'extract_person_messaging_memories_prompt', _FakeChain(response)
    ):
        out = pm.extract_person_messaging_memories(
            'uid1', 'Alice', _thread(), user_name='Me', memories_str='', language='en'
        )
    assert [m.content for m in out] == [
        'Alice started a job at Stripe as backend engineer',
        'Alice moved to Austin',
    ]


def test_returns_empty_on_llm_error():
    with patch.object(pm.users_db, 'get_people_by_ids', return_value=[]), patch.object(
        pm, 'extract_person_messaging_memories_prompt', _FakeChain(RuntimeError('boom'))
    ):
        out = pm.extract_person_messaging_memories(
            'uid1', 'Alice', _thread(), user_name='Me', memories_str='', language='en'
        )
    assert out == []


def test_empty_facts_response_returns_empty_list():
    response = SimpleNamespace(facts=[])
    with patch.object(pm.users_db, 'get_people_by_ids', return_value=[]), patch.object(
        pm, 'extract_person_messaging_memories_prompt', _FakeChain(response)
    ):
        out = pm.extract_person_messaging_memories(
            'uid1', 'Alice', _thread(), user_name='Me', memories_str='', language='en'
        )
    assert out == []
