"""Dependency-free feature gate shared by JIT conversation prompt and tools."""

from typing import Any, Dict, Optional

JIT_CONVERSATION_RETRIEVAL_ENV = "JIT_CONVERSATION_RETRIEVAL_ENABLED"
JIT_CONVERSATION_RETRIEVAL_CONFIG_KEY = "jit_conversation_retrieval_enabled"
JIT_CONVERSATION_RETRIEVAL_PROMPT_SECTION = """
<jit_conversation_retrieval>
This request is in the explicitly enabled bounded JIT conversation-retrieval cohort.

For questions that require the user's conversation history:
1. Triage summaries before transcripts. Call conversation tools with
   max_transcript_segments=0 and include_transcript=false first.
2. Extract any date range, literal phrase, person/entity, and semantic intent from the
   question. When useful, issue at most four bounded summary searches in parallel: one
   literal query, one person/entity query, one semantic paraphrase, and one date-only
   get_conversations_tool call. Do not repeat equivalent searches.
3. Rank the returned summary cards, then hydrate only the relevant conversation IDs by
   exact conversation reference with include_transcript=true and at most 24 transcript
   segments. Never hydrate every candidate wholesale.
4. Before returning "not found", reformulate once with materially different terms. If a
   date range was supplied, retry once without topic terms and widen the date range once
   only when the user's wording permits it. Stop after those bounded retries.
5. If a person name is ambiguous, preserve the distinct candidates and ask which person
   the user means instead of merging identities or inventing an answer.
6. Preserve the released [index] inline syntax, using the selected Conversation card #N
   as [N]. Never print stable evidence-reference IDs in answer text; the server transports
   those references separately in the structured evidence envelope. Use only evidence
   from that cited card or its hydrated transcript window, and degrade honestly when
   evidence is missing or partial.
</jit_conversation_retrieval>
"""


def _is_enabled_value(value: Any) -> bool:
    """Accept only explicit boolean gate values and fail closed otherwise."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def is_jit_conversation_retrieval_enabled(configurable: Optional[Dict[str, Any]]) -> bool:
    """Return whether the additive JIT conversation contract is explicitly enabled.

    Only a UID-scoped request decision may opt in. The legacy process environment
    switch is deliberately not activation authority: live rollout must first resolve
    an approved cohort into this per-request value. Missing or malformed state fails
    closed, so one environment flip cannot activate every chat request.
    """
    if not isinstance(configurable, dict):
        return False
    uid = configurable.get("user_id")
    if not isinstance(uid, str) or not uid.strip():
        return False
    return _is_enabled_value(configurable.get(JIT_CONVERSATION_RETRIEVAL_CONFIG_KEY))


def append_jit_conversation_retrieval_prompt(prompt: str, *, enabled: bool) -> str:
    """Append the bounded strategy only for the explicitly enabled cohort."""
    if enabled is not True:
        return prompt
    return prompt.rstrip() + "\n\n" + JIT_CONVERSATION_RETRIEVAL_PROMPT_SECTION.strip()
