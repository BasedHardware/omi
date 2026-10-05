"""Offline cost experiment, explicitly selected; not a cache-dependent CI gate.

Uses installed o200k_base cache data read-only. The shared test network guard
remains active, so absent tokenizer data fails locally instead of fetching.
"""

import importlib
import json
import sys

import pytest

from testing.import_isolation import stub_modules
from tests.unit.test_summary_speaker_notes_call import imports, payloads, run_notes  # noqa: F401


@pytest.fixture(scope='module')
def encoder():
    # conftest's character-count stub is unsuitable for cost measurement.
    with stub_modules({}):
        sys.modules.pop('tiktoken', None)
        yield importlib.import_module('tiktoken').get_encoding('o200k_base')


def message_text(message):
    if isinstance(message.content, str):
        return message.content
    return ''.join(part.get('text', '') for part in message.content)


@pytest.mark.parametrize('words,participants', [(80, 1), (1800, 1), (16000, 4)])
def test_measure_marginal_tokens_with_real_prompt_builder(monkeypatch, encoder, words, participants):
    from utils.llm.meeting_notes_rich_prompts import _RICH_MEETING_RULES

    base, labeled = payloads(participants)
    _, off = run_notes(monkeypatch, enabled=False, payload=base, words=words, participants=participants)
    _, on = run_notes(monkeypatch, enabled=True, payload=labeled, words=words, participants=participants)

    def prompt_tokens(calls):
        return sum(len(encoder.encode(message_text(message))) for message in calls[0])

    input_delta = prompt_tokens(on) - prompt_tokens(off)
    output_delta = len(encoder.encode(json.dumps(labeled, separators=(',', ':')))) - len(
        encoder.encode(json.dumps(base, separators=(',', ':')))
    )
    owner_rule = next(line for line in _RICH_MEETING_RULES.splitlines() if line.startswith('- Keep notes in'))
    off_system = message_text(off[0][0])
    wording_delta = len(encoder.encode(off_system)) - len(encoder.encode(off_system.replace(owner_rule + '\n', '')))
    assert len(off) == len(on) == 1
    assert 0 < input_delta < 2000
    assert 0 < output_delta < 600
    print(
        f'COST_MEASUREMENT words={words} humans={participants+1} tokenizer=o200k_base '
        f'prompt_delta={input_delta} completion_delta={output_delta} owner_wording_delta={wording_delta} '
        f'off_prompt={prompt_tokens(off)} on_prompt={prompt_tokens(on)}'
    )
