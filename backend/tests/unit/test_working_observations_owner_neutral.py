"""Owner-neutral L1 prefix eval (W12): flag off is byte-legacy, flag on is shareable.

The flag ships default off. These tests are the gate recorded in the feature
flag registry: every load-bearing instruction line survives the neutral
rewording, the owner identity and per-account language move (and stay) in the
volatile tail on both message paths, and the neutral system prefix is
byte-identical across accounts so the prompt-cache key is shareable.
"""

import os

os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8787")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test")

from langchain_core.messages import AIMessage

from utils.llm.conversation_prompt_context import ConversationPromptPrefix
from utils.llm.prompt_cache import prefix_cache_key
from utils.llm.working_observations import (
    MEMORY_L1_CACHE_NAMESPACE,
    _build_l1_messages,
    _owner_identity_intro,
    extract_l1_memory_archive_items_from_text,
)

NAME = "David"
OTHER_NAME = "Priya"
SOURCE_TEXT = "A source transcript long enough for prompt construction."
FORMAT_INSTRUCTIONS = "Return the requested JSON schema."
LANGUAGE_INSTRUCTION = "Write the memories in Spanish."


class FakeLLM:
    model_name = "gpt-6-luna"

    def __init__(self, content):
        self.content = content
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content=self.content)


def _messages(name=NAME, *, owner_neutral=False, language=""):
    messages = _build_l1_messages(
        name,
        "voice_transcript",
        SOURCE_TEXT,
        FORMAT_INSTRUCTIONS,
        language_instruction=language,
        rejected_memory_examples=("The user likes an aisle seat",),
        owner_neutral=owner_neutral,
    )
    return messages[0][1], messages[1][1]


def test_default_off_serves_legacy_wording(monkeypatch):
    monkeypatch.delenv("MEMORY_L1_OWNER_NEUTRAL_PREFIX_ENABLED", raising=False)

    system, _human = _messages()

    assert NAME in system
    assert f'referred to here as {NAME}' in system


def test_neutral_wording_moves_identity_and_language_to_the_tail():
    system, human = _messages(owner_neutral=True, language=LANGUAGE_INSTRUCTION)

    assert NAME not in system
    assert LANGUAGE_INSTRUCTION not in system
    assert human.startswith(_owner_identity_intro(NAME, LANGUAGE_INSTRUCTION))
    assert NAME in human
    assert LANGUAGE_INSTRUCTION in human


def test_neutral_prefix_is_identical_across_accounts():
    david_system, _ = _messages(NAME, owner_neutral=True, language=LANGUAGE_INSTRUCTION)
    priya_system, _ = _messages(OTHER_NAME, owner_neutral=True, language=LANGUAGE_INSTRUCTION)

    assert david_system == priya_system


def test_neutral_prefix_cache_key_is_shareable():
    david_system, _ = _messages(NAME, owner_neutral=True)
    priya_system, _ = _messages(OTHER_NAME, owner_neutral=True)

    assert prefix_cache_key(MEMORY_L1_CACHE_NAMESPACE, david_system) == prefix_cache_key(
        MEMORY_L1_CACHE_NAMESPACE, priya_system
    )


def test_neutral_prompt_preserves_every_load_bearing_instruction():
    """The eval gate: each legacy rule survives the neutral rewording.

    Pairs are (legacy wording, neutral wording) for every instruction line that
    changes between the two variants; lines that never contained the owner name
    must appear verbatim in both.
    """

    legacy_system, _ = _messages()
    neutral_system, _ = _messages(owner_neutral=True)

    pairs = [
        (
            f"You are looking at something from {NAME}'s life",
            "You are looking at something from the account owner's life",
        ),
        (f"do not assume every speaker is {NAME}", "do not assume every speaker is the account owner"),
        (f"Treat a statement as about {NAME} only when", "Treat a statement as about the account owner only when"),
        (f"- Facts about {NAME}: their decisions", "- Facts about the account owner: their decisions"),
        (
            f"- Facts about people {NAME} cares about",
            "- Facts about people the account owner cares about",
        ),
        (
            f"- Facts about recurring places, pets, or entities in {NAME}'s life.",
            "- Facts about recurring places, pets, or entities in the account owner's life.",
        ),
        (
            f"BYSTANDER: if {NAME} said little or nothing, the slice contributes nothing about {NAME}.",
            "BYSTANDER: if the account owner said little or nothing, the slice contributes nothing about the account owner.",
        ),
        (
            f"a marine biologist and {NAME} asks about funding — extract nothing about {NAME}",
            "a marine biologist and the account owner asks about funding — extract nothing about the account owner",
        ),
        (
            f'- "the user" or "{NAME}" → only when the evidence is clearly about the primary user',
            '- "the user" or the owner\'s exact name (given in the request context) → only when the evidence is clearly about the primary user',
        ),
        (
            f"The primary user is the owner of this memory account, referred to here as {NAME}.",
            "The primary user is the owner of this memory account; the request context names them.",
        ),
    ]
    for legacy, neutral in pairs:
        assert legacy in legacy_system, legacy
        assert neutral in neutral_system, neutral

    unchanged = [
        "WHO IS WHO: the owner is only the segments the transcript marks as the owner",
        "NAME WHOSE FACT: every item names its subject in about",
        "BASIS: decided only for a commitment or decision on tape by the owner",
        "PARTICIPATING IS NOT A FACT",
        "Each item must be grounded in a quote from the source.",
        "Use class=\"sensitive\" for credentials, health details, finances, family matters.",
    ]
    for line in unchanged:
        assert line in legacy_system, line
        assert line in neutral_system, line
