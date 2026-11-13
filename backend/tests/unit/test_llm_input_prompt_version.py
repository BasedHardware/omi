"""The notes/L1 reuse key is an explicit prompt version, guarded by a source digest.

The digest lives here, not on the runtime path. A prompt edit must fail this
test until the author bumps the version in ``config/llm_input_versions.py`` and
records the new digest, because a missed bump would serve stale notes or
memories for unchanged input. The runtime key combines that explicit version
with routing and installed dependency versions; unrelated deploy edits do not
re-buy unchanged input.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from config.llm_input_versions import PROMPT_VERSIONS, prompt_version

BACKEND = Path(__file__).resolve().parents[2]

# Prompt text, output schema, and the deterministic shaping that feeds the
# prompt. A change here can change the model's output for the same input.
PROMPT_SOURCES: dict[str, tuple[str, ...]] = {
    'notes': (
        'utils/llm/conversation_notes_prompts.py',
        'utils/llm/notes_packet.py',
        'utils/llm/notes_output.py',
        'utils/llm/notes_output_contract.py',
        'utils/llm/notes_identity.py',
        'utils/llm/notes_lengths.py',
        'utils/llm/notes_effort.py',
        'utils/llm/notes_short_clip.py',
        'utils/llm/notes_language_inputs.py',
        'utils/llm/conversation_title_people.py',
        'utils/llm/meeting_notes_rich_prompts.py',
        'utils/llm/meeting_notes_presentation.py',
        'utils/llm/meeting_notes_validation.py',
        'utils/llm/speaker_evidence_prompt.py',
        'utils/llm/conversation_prompt_context.py',
        'utils/llm/output_language.py',
        'utils/llm/action_item_v2.py',
        'utils/llm/conversation_processing.py',
        'utils/prompts.py',
        'models/structured.py',
        'models/structured_extraction.py',
    ),
    'l1': (
        'utils/llm/working_observations.py',
        'utils/llm/memories.py',
        'utils/memory/rejected_memory_feedback.py',
        'utils/llm/conversation_prompt_context.py',
        'utils/prompts.py',
        'models/memory_contracts.py',
        'models/memories.py',
    ),
}

# version -> digest of PROMPT_SOURCES at that version. Append, never rewrite:
# the newest entry must be the version the runtime key carries.
PINNED: dict[str, dict[str, str]] = {
    'notes': {
        'notes-1': '3f46a967f7c9e179f295724f3e9e4678515f87588b98bd62f130e2601a2e24bf',
        'notes-2': 'da38487a9fb7cc52ef0508b6fa3639c6724b42666c5b38600e5235fa9fbc7437',
        'notes-3': '5307871ec67f0f81cafbca8d9aa209dd4fdc3fe9eec9d13139156fd0706ac766',
    },
    'l1': {'l1-1': '0ad51076315481003b05af2a90ce18797539846e35f4970680dff906c00b7d70'},
}


def prompt_digest(feature: str) -> str:
    digest = hashlib.sha256()
    for relative in PROMPT_SOURCES[feature]:
        digest.update(relative.encode())
        digest.update(b'\0')
        digest.update((BACKEND / relative).read_bytes())
        digest.update(b'\0')
    return digest.hexdigest()


@pytest.mark.parametrize('feature', sorted(PROMPT_SOURCES))
def test_prompt_sources_match_the_pinned_digest(feature):
    version = prompt_version(feature)
    assert version in PINNED[feature], (
        f'{feature}: prompt version {version!r} has no pinned digest. Add '
        f'PINNED[{feature!r}][{version!r}] = prompt_digest({feature!r}).'
    )
    assert prompt_digest(feature) == PINNED[feature][version], (
        f'{feature}: prompt sources changed without a version bump. Bump the version in '
        f'config/llm_input_versions.py and pin the new digest, or revert the prompt change.'
    )


@pytest.mark.parametrize('feature', sorted(PROMPT_SOURCES))
def test_current_version_is_the_newest_pinned(feature):
    assert prompt_version(feature) == list(PINNED[feature])[-1]


def test_unknown_feature_fails_closed():
    with pytest.raises(ValueError):
        prompt_version('unknown')


def test_reuse_key_carries_the_version_not_a_file_digest():
    from utils.conversations import llm_input_dedupe

    assert llm_input_dedupe.implementation_digest('notes').startswith(PROMPT_VERSIONS['notes'] + ':')
    assert llm_input_dedupe.implementation_digest('l1').startswith(PROMPT_VERSIONS['l1'] + ':')
