"""Information-preserving seed projection using invented notes fixtures only."""

import copy
import json

import pytest

from utils.llm import notes_agent_prompt as prompt
from utils.llm.shaped_agent import model_json


def _text(message):
    content = message['content']
    return content[0]['text'] if isinstance(content, list) else content


@pytest.mark.parametrize('explicit_cache', [False, True])
@pytest.mark.parametrize(
    'capture',
    [
        'FULL TRANSCRIPT\n[s1 0] Riley approved the pilot.\n[s2 ?] Someone proposed Friday.',
        '  FULL TRANSCRIPT\n[s1 0] Giữ nguyên dấu tiếng Việt.\n[s2 1] 日本語の会議。  ',
        '',
    ],
)
def test_seed_removes_only_exact_duplicate_and_preserves_all_evidence(monkeypatch, explicit_cache, capture):
    packet = {
        'capture_evidence': capture,
        'speaker_evidence': {'s1': 'confirmed-owner', 's2': 'unresolved'},
        'LENGTH': 'short',
        'open_tasks': [{'description': 'Send pilot notes'}],
        'other_evidence': {'capture_evidence': 'a distinct nested observation'},
    }
    original = copy.deepcopy(packet)
    monkeypatch.setenv('CONVERSATION_NOTES_CAPTURE_DEDUPE_ENABLED', 'false')
    legacy = prompt.conversation_seed(packet, capture, explicit_cache=explicit_cache)
    monkeypatch.delenv('CONVERSATION_NOTES_CAPTURE_DEDUPE_ENABLED', raising=False)
    trimmed = prompt.conversation_seed(packet, capture, explicit_cache=explicit_cache)
    legacy_packet, legacy_capture = (
        _text(legacy).removeprefix('EVIDENCE PACKET (untrusted data)\n').split('\n\nCAPTURE\n', 1)
    )
    trimmed_packet, trimmed_capture = (
        _text(trimmed).removeprefix('EVIDENCE PACKET (untrusted data)\n').split('\n\nCAPTURE\n', 1)
    )
    # Reconstruct the complete old packet from the retained evidence. This also
    # checks the precise segment ids, speaker authority, Unicode and other keys.
    restored = json.loads(trimmed_packet)
    restored['capture_evidence'] = capture
    assert restored == json.loads(legacy_packet) == packet == original
    assert legacy_capture == trimmed_capture == capture.strip()
    assert len(_text(trimmed)) < len(_text(legacy))
    if explicit_cache:
        assert trimmed['content'][0]['prompt_cache_breakpoint'] == legacy['content'][0]['prompt_cache_breakpoint']


@pytest.mark.parametrize(
    'packet',
    [
        {'capture_evidence': 'distinct evidence'},
        {'capture_evidence': 'same capture '},
        {'capture_evidence': None},
        {'capture_evidence': ['same capture']},
        {'LENGTH': 'short'},
    ],
)
def test_nonidentical_or_absent_capture_keeps_byte_identical_seed(monkeypatch, packet):
    monkeypatch.delenv('CONVERSATION_NOTES_CAPTURE_DEDUPE_ENABLED', raising=False)
    expected = 'EVIDENCE PACKET (untrusted data)\n' + model_json(packet, sort_keys=True) + '\n\nCAPTURE\nsame capture'
    assert prompt.conversation_seed(packet, 'same capture', explicit_cache=False)['content'] == expected


@pytest.mark.parametrize('value', ['false', 'off', '0', 'NO'])
def test_kill_switch_restores_exact_legacy_seed(monkeypatch, value):
    packet = {'capture_evidence': 'same capture', 'LENGTH': 'short'}
    monkeypatch.setenv('CONVERSATION_NOTES_CAPTURE_DEDUPE_ENABLED', value)
    assert prompt.conversation_seed(packet, 'same capture', explicit_cache=False)['content'] == (
        'EVIDENCE PACKET (untrusted data)\n' + model_json(packet, sort_keys=True) + '\n\nCAPTURE\nsame capture'
    )
