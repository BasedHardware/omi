"""Escalation gate: auto-reply must hand a message back to the user (rather than
auto-send) when it can't answer truthfully, needs the user's own decision, or asks
for sensitive info. See utils/llm/reply_draft.classify_escalation + draft_reply."""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
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

import utils.llm.reply_draft as rd  # noqa: E402


def _as_text(arg):
    if isinstance(arg, str):
        return arg
    return "\n".join(getattr(m, "content", str(m)) for m in arg)


def _escalation_call(prompt) -> bool:
    """The classify_escalation call is the one carrying the safety-gate system prompt."""
    return 'safety gate for an auto-reply assistant' in _as_text(prompt)


class _ScriptedLLM:
    """Generation returns the candidate list; selection returns an index; the
    escalation-classify call returns a fixed verdict JSON object."""

    def __init__(self, candidates, verdict):
        self.candidates = candidates
        self.verdict = verdict

    def invoke(self, prompt):
        if _escalation_call(prompt):
            return SimpleNamespace(content=json.dumps(self.verdict))
        if 'Reply with ONLY the number' in _as_text(prompt):
            return SimpleNamespace(content='0')
        return SimpleNamespace(content=json.dumps(self.candidates))


# --- classify_escalation (unit) ---------------------------------------------


def _fake_llm(verdict_content):
    return SimpleNamespace(invoke=lambda prompt: SimpleNamespace(content=verdict_content))


def test_classify_escalation_decision():
    llm = _fake_llm('{"escalate": true, "category": "decision", "reason": "They want to lock in a time"}')
    with patch.object(rd, 'get_llm', return_value=llm):
        out = rd.classify_escalation('can you meet Tuesday at 3pm?', '', 'sure, that works')
    assert out['escalate'] is True
    assert out['category'] == 'decision'
    assert out['reason'] == 'They want to lock in a time'


def test_classify_escalation_unknown():
    llm = _fake_llm('{"escalate": true, "category": "unknown", "reason": "You may know this"}')
    with patch.object(rd, 'get_llm', return_value=llm):
        out = rd.classify_escalation('did you file the taxes yet?', '(no context)', 'yeah all done')
    assert out['escalate'] is True
    assert out['category'] == 'unknown'


def test_classify_escalation_sensitive():
    llm = _fake_llm('{"escalate": true, "category": "sensitive", "reason": "They asked for private info"}')
    with patch.object(rd, 'get_llm', return_value=llm):
        out = rd.classify_escalation("what's your social security number?", '', 'sure its...')
    assert out['escalate'] is True
    assert out['category'] == 'sensitive'


def test_classify_escalation_casual_does_not_escalate():
    llm = _fake_llm('{"escalate": false, "category": "none", "reason": ""}')
    with patch.object(rd, 'get_llm', return_value=llm):
        out = rd.classify_escalation('hey how is it going', '', 'good, you?')
    assert out['escalate'] is False
    assert out['category'] == 'none'


def test_classify_escalation_empty_inbound_short_circuits_no_llm():
    called = {'llm': False}

    def boom(prompt):
        called['llm'] = True
        raise AssertionError('should not invoke the LLM on empty inbound')

    with patch.object(rd, 'get_llm', return_value=SimpleNamespace(invoke=boom)):
        out = rd.classify_escalation('', '', 'draft')
    assert out['escalate'] is False
    assert called['llm'] is False


def test_classify_escalation_fails_open_on_unparseable_verdict():
    """A garbled/non-JSON verdict must NOT escalate — escalation is a safety net over
    auto-reply, so a classifier hiccup preserves the normal send path."""
    llm = _fake_llm('the model rambled without json')
    with patch.object(rd, 'get_llm', return_value=llm):
        out = rd.classify_escalation('can you meet Tuesday?', '', 'sure')
    assert out['escalate'] is False


def test_classify_escalation_fails_open_on_llm_error():
    def boom(prompt):
        raise RuntimeError('llm down')

    with patch.object(rd, 'get_llm', return_value=SimpleNamespace(invoke=boom)):
        out = rd.classify_escalation('can you meet Tuesday?', '', 'sure')
    assert out['escalate'] is False


def test_classify_escalation_rejects_contradictory_verdict():
    """escalate=true with an unrecognized/none category is contradictory — don't
    surface a mislabeled escalation."""
    llm = _fake_llm('{"escalate": true, "category": "banter", "reason": "x"}')
    with patch.object(rd, 'get_llm', return_value=llm):
        out = rd.classify_escalation('yo', '', 'hey')
    assert out['escalate'] is False


# --- draft_reply integration ------------------------------------------------


def test_draft_reply_escalates_one_to_one():
    """A 1:1 message the classifier escalates returns the draft as a SUGGESTION plus
    needs_input=True and a reason — it must NOT be a normal sendable draft."""
    verdict = {"escalate": True, "category": "decision", "reason": "They want to lock in a time"}
    llm = _ScriptedLLM(candidates=['sure, that works for me'], verdict=verdict)
    with patch.object(rd, 'resolve_person', return_value=None), patch.object(
        rd, '_relevant_context', return_value=''
    ), patch.object(rd.conversations_db, 'get_conversations', return_value=[]), patch.object(
        rd, 'get_llm', return_value=llm
    ):
        out = rd.draft_reply('uid', '+15551234567', [{'text': 'can you meet Tuesday at 3?', 'is_from_me': False}])

    assert out['draft'] == 'sure, that works for me'
    assert out['needs_input'] is True
    assert out['needs_input_reason'] == 'They want to lock in a time'


def test_draft_reply_does_not_escalate_casual():
    verdict = {"escalate": False, "category": "none", "reason": ""}
    llm = _ScriptedLLM(candidates=['good, you?'], verdict=verdict)
    with patch.object(rd, 'resolve_person', return_value=None), patch.object(
        rd, '_relevant_context', return_value=''
    ), patch.object(rd.conversations_db, 'get_conversations', return_value=[]), patch.object(
        rd, 'get_llm', return_value=llm
    ):
        out = rd.draft_reply('uid', '+15551234567', [{'text': 'hey hows it going', 'is_from_me': False}])

    assert out['draft'] == 'good, you?'
    assert out.get('needs_input', False) is False


def test_draft_reply_group_never_escalates():
    """Groups are already draft-only/reviewed, so the escalation classifier must not
    run for them — its call would never happen and needs_input stays unset."""
    called = {'escalation': False}

    class _GroupLLM:
        def invoke(self, prompt):
            if _escalation_call(prompt):
                called['escalation'] = True
                return SimpleNamespace(content='{"escalate": true, "category": "decision", "reason": "x"}')
            if 'Reply with ONLY the number' in _as_text(prompt):
                return SimpleNamespace(content='0')
            return SimpleNamespace(content=json.dumps(['sure, im down']))

    thread = [{'text': 'anyone free tonight?', 'is_from_me': False, 'sender': 'Bob'}]
    with patch.object(rd, 'resolve_person', return_value={'id': 'p1', 'name': 'Group'}), patch.object(
        rd.memories_db, 'get_memories_by_subject_entity', return_value=[]
    ), patch.object(rd, '_relevant_context', return_value=''), patch.object(
        rd.conversations_db, 'get_conversations', return_value=[]
    ), patch.object(
        rd, 'get_llm', return_value=_GroupLLM()
    ):
        out = rd.draft_reply('uid', 'Group', thread, is_group=True)

    assert out.get('needs_input', False) is False
    assert called['escalation'] is False


def test_draft_reply_empty_draft_skips_escalation():
    """No draft produced → nothing to escalate; the classifier must not run."""
    called = {'escalation': False}

    class _EmptyGenLLM:
        def invoke(self, prompt):
            if _escalation_call(prompt):
                called['escalation'] = True
                return SimpleNamespace(content='{"escalate": true, "category": "decision", "reason": "x"}')
            return SimpleNamespace(content='')  # empty generation -> no candidates

    with patch.object(rd, 'resolve_person', return_value=None), patch.object(
        rd, '_relevant_context', return_value=''
    ), patch.object(rd.conversations_db, 'get_conversations', return_value=[]), patch.object(
        rd, 'get_llm', return_value=_EmptyGenLLM()
    ):
        out = rd.draft_reply('uid', '+15551234567', [{'text': 'yo', 'is_from_me': False}])

    assert out['draft'] == ''
    assert out.get('needs_input', False) is False
    assert called['escalation'] is False
