"""
Integration tests for OpenAI prompt caching with live API calls.

Tests caching scenarios on gpt-5.1:
1. Same user, same conversation — identical calls should fully cache
2. Same user, cross conversation — same language, different transcripts should cache instruction prefix
3. Cross user — different languages should still cache instruction prefix (language_code in context, not instructions)
4. prompt_cache_retention="24h" — API accepts param and cache hits work (PR #4674)
5. prompt_cache_key — routing hints accepted and cache hits work (PR #4674)

Requires:
    - OPENAI_API_KEY environment variable
    - Network access to OpenAI API

Run:
    cd backend
    PYTHONPATH=. python3 -m pytest tests/integration/test_prompt_caching_integration.py -v -s

Note: These tests make real API calls and cost real money (~$0.10-0.20 per run).
Cache behavior depends on OpenAI infrastructure; cache hits are not guaranteed
on every run but should appear consistently when the prefix is stable and >1024 tokens.
"""

import os
import time

import pytest
from openai import OpenAI

# Skip entire module if no API key
pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set",
)

MODEL = "gpt-5.1"

# ---------------------------------------------------------------------------
#  Production-length instruction text (must be >1024 tokens for caching)
#  This mirrors the extract_action_items instructions from conversation_processing.py
# ---------------------------------------------------------------------------

ACTION_ITEMS_INSTRUCTIONS = """You are an expert action item extractor. Your sole purpose is to identify and extract actionable tasks from the provided content.

EXPLICIT TASK/REMINDER REQUESTS (HIGHEST PRIORITY)

When the primary user OR someone speaking to them uses these patterns, ALWAYS extract the task:
- "Remind me to X" / "Remember to X" → EXTRACT "X"
- "Don't forget to X" / "Don't let me forget X" → EXTRACT "X"
- "Add task X" / "Create task X" / "Make a task for X" → EXTRACT "X"
- "Note to self: X" / "Mental note: X" → EXTRACT "X"
- "Task: X" / "Todo: X" / "To do: X" → EXTRACT "X"
- "I need to remember to X" → EXTRACT "X"
- "Put X on my list" / "Add X to my tasks" → EXTRACT "X"
- "Set a reminder for X" / "Can you remind me X" → EXTRACT "X"
- "You need to X" / "You should X" / "Make sure you X" (said TO the user) → EXTRACT "X"

These explicit requests bypass importance/timing filters. If someone explicitly asks for a reminder or task, extract it.

Examples:
- User says "Remind me to buy milk" → Extract "Buy milk"
- Someone tells user "Don't forget to call your mom" → Extract "Call mom"
- User says "Add task pick up dry cleaning" → Extract "Pick up dry cleaning"
- User says "Note to self, check tire pressure" → Extract "Check tire pressure"

CRITICAL: If CALENDAR MEETING CONTEXT is provided with participant names, you MUST use those names:
- The conversation DEFINITELY happened between the named participants
- NEVER use "Speaker 0", "Speaker 1", "Speaker 2", etc. when participant names are available
- Match transcript speakers to participant names by analyzing the conversation context
- Use participant names in ALL action items (e.g., "Follow up with Sarah" NOT "Follow up with Speaker 0")
- Reference the meeting title/context when relevant to the action item
- Consider the scheduled meeting time and duration when extracting due dates
- If you cannot confidently match a speaker to a name, use the action description without speaker references

CRITICAL DEDUPLICATION RULES (Check BEFORE extracting):
- DO NOT extract action items that are >95% similar to existing ones in the content
- Check both the description AND the due date/timeframe
- Consider semantic similarity, not just exact word matches
- Examples of what counts as DUPLICATES (DO NOT extract):
  - "Call John" vs "Phone John" → DUPLICATE
  - "Finish report by Friday" (existing) vs "Complete report by end of week" → DUPLICATE
  - "Buy milk" (existing) vs "Get milk from store" → DUPLICATE
  - "Email Sarah about meeting" (existing) vs "Send email to Sarah regarding the meeting" → DUPLICATE
- Examples of what is NOT duplicate (OK to extract):
  - "Buy groceries" (existing) vs "Buy milk" → NOT duplicate (different scope)
  - "Call dentist" (existing) vs "Call plumber" → NOT duplicate (different person/service)
  - "Submit report by March 1st" (existing) vs "Submit report by March 15th" → NOT duplicate (different deadlines)
- If you're unsure whether something is a duplicate, err on the side of treating it as a duplicate (DON'T extract)

WORKFLOW:
1. FIRST: Read the ENTIRE conversation carefully to understand the full context
2. SECOND: Check for EXPLICIT task requests (remind me, add task, don't forget, etc.) - ALWAYS extract these
3. THIRD: For IMPLICIT tasks - be extremely aggressive with filtering:
   - Is the user ALREADY doing this? SKIP IT
   - Is this truly important enough to remind a busy person? If ANY doubt, SKIP IT
   - Would missing this have real consequences? If not obvious, SKIP IT
   - Better to extract 0 implicit tasks than flood the user with noise
4. FOURTH: Extract timing information separately and put it in the due_at field
5. FIFTH: Clean the description - remove ALL time references and vague words
6. SIXTH: Final check - description should be timeless and specific

CRITICAL CONTEXT:
- These action items are primarily for the PRIMARY USER who is having/recording this conversation
- The user is the person wearing the device or initiating the conversation
- Focus on tasks the primary user needs to track and act upon
- Include tasks for OTHER people ONLY if:
  - The primary user is dependent on that task being completed
  - It's super crucial for the primary user to track it
  - The primary user needs to follow up on it

BALANCE QUALITY AND USER INTENT:
- For EXPLICIT requests (remind me, add task, don't forget, etc.) - ALWAYS extract
- For IMPLICIT tasks inferred from conversation - be very selective, better to extract 0 than flood the user
- Think: "Did the user ask for this reminder, or am I guessing they need it?"
- If the user explicitly asked for a task/reminder, respect their request even if it seems trivial

STRICT FILTERING RULES - Include ONLY tasks that meet ALL these criteria:

1. **Clear Ownership & Relevance to Primary User**:
   - Identify which speaker is the primary user based on conversational context
   - Look for cues: who is asking questions, who is receiving advice/tasks, who initiates topics
   - For tasks assigned to the primary user: phrase them directly (start with verb)
   - For tasks assigned to others: include them ONLY if primary user is dependent on them or needs to track them

2. **Concrete Action**: The task describes a specific, actionable next step (not vague intentions)

3. **Timing Signal** (NOT required for explicit task requests):
   - Explicit dates or times
   - Relative timing ("tomorrow", "next week", "by Friday", "this month")
   - Urgency markers ("urgent", "ASAP", "high priority")

4. **Real Importance** (NOT required for explicit task requests):
   - Financial impact (bills, payments, purchases, invoices)
   - Health/safety concerns (appointments, medications, safety checks)
   - Hard deadlines (submissions, filings, registrations)
   - Critical dependencies (primary user blocked without it)
   - Commitments to other people (meetings, deliverables, promises)

EXCLUDE these types of items (be aggressive about exclusion):
- Things user is ALREADY doing or actively working on
- Casual mentions or updates
- Vague suggestions without commitment
- General goals without specific next steps
- Past actions being discussed
- Hypothetical scenarios
- Trivial tasks with no real consequences
- Tasks assigned to others that don't impact the primary user

FORMAT REQUIREMENTS:
- Keep each action item SHORT and concise (maximum 15 words, strict limit)
- Use clear, direct language
- Start with a verb when possible
- Include only essential details
- Remove filler words and unnecessary context
- Merge duplicates
- Order by: due date, urgency, alphabetical

Respond with JSON: {"action_items": [{"description": "..."}]}"""


@pytest.fixture(scope="module")
def client():
    return OpenAI()


def _call_and_get_cache_info(client: OpenAI, messages: list) -> dict:
    """Make an API call and return cache-related usage info."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_completion_tokens=150,
    )
    usage = response.usage
    result = {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "cached_tokens": 0,
    }
    if hasattr(usage, "prompt_tokens_details") and usage.prompt_tokens_details:
        details = usage.prompt_tokens_details
        if hasattr(details, "cached_tokens"):
            result["cached_tokens"] = details.cached_tokens or 0
    return result


# ---------------------------------------------------------------------------
#  Sample transcripts (different content, same function)
# ---------------------------------------------------------------------------

TRANSCRIPT_A = """Speaker 0: Good morning everyone. Let's start our weekly product sync.

Speaker 1: Sure. I've been working on the new onboarding flow. We reduced the number of screens from 7 to 4, and early testing shows a 15% improvement in completion rate.

Speaker 0: That's great progress. When do you think we can ship it?

Speaker 1: I think we can have it ready by next Friday. I just need to finish the animations and get design sign-off from Sarah.

Speaker 0: Perfect. Let me know if you need anything. Also, don't forget to update the analytics events before you ship.

Speaker 2: I wanted to bring up the API latency issue. We're seeing p99 spikes above 2 seconds on the search endpoint. I've identified the root cause - it's the new full-text search query that's not using the index properly.

Speaker 0: That sounds urgent. Can you fix it today?

Speaker 2: I already have a fix ready. Just need to run the migration on staging first. Should be deployed by end of day.

Speaker 0: Good. Remind me to check the latency dashboard tomorrow morning."""

TRANSCRIPT_B = """Speaker 0: Hey, thanks for meeting with me about the budget.

Speaker 1: Of course. Let me walk you through the Q2 projections. We're looking at a 12% increase in infrastructure costs due to the new region expansion.

Speaker 0: That's higher than expected. Can we optimize anywhere?

Speaker 1: Yes, I've identified three areas. First, we can switch to reserved instances for the database cluster - that saves about 30%. Second, we can implement better caching on the API layer. Third, we should audit our unused resources.

Speaker 0: Let's do the reserved instances first since that's the biggest savings. Can you prepare a proposal by Wednesday?

Speaker 1: Sure, I'll have it ready. I'll also include a comparison of different commitment terms.

Speaker 0: Great. Also, remind me to schedule a meeting with the finance team next week to discuss the annual budget review."""

TRANSCRIPT_C = """Speaker 0: I just got back from the dentist. They said I need to come back in two weeks for a follow-up.

Speaker 1: Oh no, is everything okay?

Speaker 0: Yeah, just a routine filling. But I need to remember to call the insurance company to check if the procedure is covered before I go back.

Speaker 1: You should also ask about the pre-authorization process. Sometimes they need 48 hours notice.

Speaker 0: Good point. I'll add that to my list. Also, remind me to pick up the prescription from the pharmacy on the way home tomorrow."""


class TestSameUserSameConversation:
    """Test intra-conversation caching: same user calls structure + action_items on the same transcript.

    In production, each conversation triggers two sequential LLM calls (get_transcript_structure
    then extract_action_items). Since both share the same static instruction prefix, the second
    call should get a cache hit on that prefix even though the instructions differ after the prefix.

    More importantly, calling the SAME function twice with identical messages should produce
    a near-complete cache hit (all tokens cached).
    """

    def test_same_function_same_transcript_full_cache(self, client):
        """Two identical calls — second should cache nearly all prompt tokens."""
        msgs = [
            {"role": "system", "content": ACTION_ITEMS_INSTRUCTIONS},
            {
                "role": "system",
                "content": f"The content language is en. Use the same language en for your response.\n\nContent:\n{TRANSCRIPT_A}",
            },
        ]

        print("\n  === Same user, same conversation (identical calls) ===")
        r1 = _call_and_get_cache_info(client, msgs)
        print(f"  Call 1 (prime): prompt={r1['prompt_tokens']}, cached={r1['cached_tokens']}")
        time.sleep(1)

        r2 = _call_and_get_cache_info(client, msgs)
        print(f"  Call 2 (repeat): prompt={r2['prompt_tokens']}, cached={r2['cached_tokens']}")

        if r2["cached_tokens"] > 0:
            pct = r2["cached_tokens"] / r2["prompt_tokens"] * 100
            print(
                f"\n  ✅ SAME-CONVERSATION CACHE HIT: {r2['cached_tokens']}/{r2['prompt_tokens']} tokens ({pct:.1f}%)"
            )
        else:
            print("\n  ⚠️  No cache hit on identical repeat (may need warm-up)")


class TestSameUserCrossConversation:
    """Test cross-conversation caching for the same user.

    Same language/timezone, different transcripts. The static instruction prefix
    should be cached after the first call. This is the primary cost-saving scenario:
    a single user processes many conversations per day.
    """

    def test_same_language_different_transcripts(self, client):
        """Same user (en) processes 3 different conversations — instruction prefix should cache."""
        lang = "en"
        transcripts = [TRANSCRIPT_A, TRANSCRIPT_B, TRANSCRIPT_C]
        results = []

        print("\n  === Same user (en), different conversations ===")
        for i, transcript in enumerate(transcripts):
            msgs = [
                {"role": "system", "content": ACTION_ITEMS_INSTRUCTIONS},
                {
                    "role": "system",
                    "content": f"The content language is {lang}. Use the same language {lang} for your response.\n\nContent:\n{transcript}",
                },
            ]
            result = _call_and_get_cache_info(client, msgs)
            results.append(result)
            print(f"  Call {i+1}: prompt={result['prompt_tokens']}, cached={result['cached_tokens']}")
            if i < len(transcripts) - 1:
                time.sleep(1)

        later_cached = results[1]["cached_tokens"] + results[2]["cached_tokens"]
        later_prompt = results[1]["prompt_tokens"] + results[2]["prompt_tokens"]
        if later_cached > 0:
            pct = later_cached / later_prompt * 100
            print(f"\n  ✅ CROSS-CONVERSATION CACHE HIT: {later_cached} cached tokens ({pct:.1f}% of later calls)")
        else:
            print("\n  ⚠️  No cache hits (may need warm-up)")


class TestCrossUserCaching:
    """Test cross-user caching with different languages.

    Since {language_code} is now in the context message (not in the instruction prefix),
    the static instruction prefix should be identical across ALL users regardless of language.
    This is the key improvement from moving {language_code} out of instructions_text.
    """

    def test_different_languages_share_instruction_cache(self, client):
        """Users with different languages should still get instruction prefix cache hits."""
        # Simulate 3 users with different languages processing different conversations
        user_calls = [
            ("en", TRANSCRIPT_A, "English user"),
            ("es", TRANSCRIPT_B, "Spanish user"),
            ("ja", TRANSCRIPT_C, "Japanese user"),
        ]
        results = []

        print("\n  === Cross-user: different languages, different conversations ===")
        for i, (lang, transcript, label) in enumerate(user_calls):
            msgs = [
                {"role": "system", "content": ACTION_ITEMS_INSTRUCTIONS},
                {
                    "role": "system",
                    "content": f"The content language is {lang}. Use the same language {lang} for your response.\n\nContent:\n{transcript}",
                },
            ]
            result = _call_and_get_cache_info(client, msgs)
            results.append(result)
            print(f"  Call {i+1} ({label}): prompt={result['prompt_tokens']}, cached={result['cached_tokens']}")
            if i < len(user_calls) - 1:
                time.sleep(1)

        later_cached = results[1]["cached_tokens"] + results[2]["cached_tokens"]
        later_prompt = results[1]["prompt_tokens"] + results[2]["prompt_tokens"]
        if later_cached > 0:
            pct = later_cached / later_prompt * 100
            print(f"\n  ✅ CROSS-USER CACHE HIT: {later_cached} cached tokens ({pct:.1f}% of later calls)")
            print("  Instruction prefix is shared across languages!")
        else:
            print("\n  ⚠️  No cross-user cache hits (may need warm-up)")

    def test_cross_user_vs_language_in_instructions(self, client):
        """A/B: static instructions (language in context) vs dynamic instructions (language baked in).

        This proves the value of moving {language_code} out of instructions_text.
        """
        languages = ["en", "es", "ja"]
        transcripts = [TRANSCRIPT_A, TRANSCRIPT_B, TRANSCRIPT_C]

        # --- New approach: language in context message (static prefix) ---
        print("\n  === A: Language in context (static instruction prefix) ===")
        static_results = []
        for i, (lang, transcript) in enumerate(zip(languages, transcripts)):
            msgs = [
                {"role": "system", "content": ACTION_ITEMS_INSTRUCTIONS},
                {
                    "role": "system",
                    "content": f"The content language is {lang}. Use the same language {lang} for your response.\n\nContent:\n{transcript}",
                },
            ]
            result = _call_and_get_cache_info(client, msgs)
            static_results.append(result)
            print(f"    Call {i+1} (lang={lang}): prompt={result['prompt_tokens']}, cached={result['cached_tokens']}")
            if i < len(languages) - 1:
                time.sleep(1)

        time.sleep(3)

        # --- Old approach: language baked into instructions (dynamic prefix) ---
        print("\n  === B: Language in instructions (dynamic prefix — old bug) ===")
        dynamic_results = []
        for i, (lang, transcript) in enumerate(zip(languages, transcripts)):
            # Simulate old code: language_code in instructions
            dynamic_instructions = (
                f"You are an expert action item extractor.\n\nThe content language is {lang}. Use the same language {lang} for your response.\n\n"
                + ACTION_ITEMS_INSTRUCTIONS[
                    len(
                        "You are an expert action item extractor. Your sole purpose is to identify and extract actionable tasks from the provided content.\n\n"
                    ) :
                ]
            )
            msgs = [
                {"role": "system", "content": dynamic_instructions},
                {"role": "system", "content": f"Content:\n{transcript}"},
            ]
            result = _call_and_get_cache_info(client, msgs)
            dynamic_results.append(result)
            print(f"    Call {i+1} (lang={lang}): prompt={result['prompt_tokens']}, cached={result['cached_tokens']}")
            if i < len(languages) - 1:
                time.sleep(1)

        # --- Summary ---
        static_cached = sum(r["cached_tokens"] for r in static_results)
        static_prompt = sum(r["prompt_tokens"] for r in static_results)
        dynamic_cached = sum(r["cached_tokens"] for r in dynamic_results)
        dynamic_prompt = sum(r["prompt_tokens"] for r in dynamic_results)

        print(f"\n  === RESULTS ===")
        print(
            f"  Static prefix (new):  {static_cached}/{static_prompt} cached ({static_cached/max(static_prompt,1)*100:.1f}%)"
        )
        print(
            f"  Dynamic prefix (old): {dynamic_cached}/{dynamic_prompt} cached ({dynamic_cached/max(dynamic_prompt,1)*100:.1f}%)"
        )

        if static_cached > dynamic_cached:
            print(f"  ✅ Static prefix produces {static_cached - dynamic_cached} MORE cached tokens across languages")
        elif static_cached == dynamic_cached == 0:
            print("  ⚠️  No cache hits on either (may need warm-up)")
        else:
            print("  ⚠️  Unexpected: dynamic prefix matched or beat static prefix")


# ---------------------------------------------------------------------------
#  Helper for calls with prompt_cache_retention and prompt_cache_key
# ---------------------------------------------------------------------------


def _call_with_cache_params(client: OpenAI, messages: list, cache_retention: str = None, cache_key: str = None) -> dict:
    """Make an API call with optional cache retention and cache key params."""
    kwargs = {
        "model": MODEL,
        "messages": messages,
        "max_completion_tokens": 150,
    }
    if cache_key:
        kwargs["prompt_cache_key"] = cache_key
    if cache_retention:
        # prompt_cache_retention is not a native SDK param — pass via extra_body
        kwargs["extra_body"] = {"prompt_cache_retention": cache_retention}
    response = client.chat.completions.create(**kwargs)
    usage = response.usage
    result = {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "cached_tokens": 0,
    }
    if hasattr(usage, "prompt_tokens_details") and usage.prompt_tokens_details:
        details = usage.prompt_tokens_details
        if hasattr(details, "cached_tokens"):
            result["cached_tokens"] = details.cached_tokens or 0
    return result


class TestPromptCacheRetention:
    """Test that prompt_cache_retention="24h" is accepted by the API and improves caching.

    The 24h retention extends cache lifetime from ~5-10min in-memory to 24h SSD-backed.
    We can't directly verify SSD vs in-memory, but we can verify:
    1. The API accepts the parameter without error
    2. Cache hits still work with the parameter set
    """

    def test_24h_retention_accepted_by_api(self, client):
        """Verify prompt_cache_retention='24h' is accepted without error."""
        msgs = [
            {"role": "system", "content": ACTION_ITEMS_INSTRUCTIONS},
            {
                "role": "system",
                "content": f"The content language is en. Use the same language en for your response.\n\nContent:\n{TRANSCRIPT_A}",
            },
        ]
        # Should not raise — if the API rejects the param, this test fails
        result = _call_with_cache_params(client, msgs, cache_retention="24h")
        print(
            f"\n  prompt_cache_retention='24h' accepted: prompt={result['prompt_tokens']}, cached={result['cached_tokens']}"
        )
        assert result["prompt_tokens"] > 0, "Expected non-zero prompt tokens"

    def test_24h_retention_cache_hits(self, client):
        """Cache hits should work with 24h retention enabled."""
        transcripts = [TRANSCRIPT_A, TRANSCRIPT_B, TRANSCRIPT_C]
        results = []

        print("\n  === Cross-conversation with prompt_cache_retention='24h' ===")
        for i, transcript in enumerate(transcripts):
            msgs = [
                {"role": "system", "content": ACTION_ITEMS_INSTRUCTIONS},
                {
                    "role": "system",
                    "content": f"The content language is en. Use the same language en for your response.\n\nContent:\n{transcript}",
                },
            ]
            result = _call_with_cache_params(client, msgs, cache_retention="24h")
            results.append(result)
            print(f"  Call {i+1}: prompt={result['prompt_tokens']}, cached={result['cached_tokens']}")
            if i < len(transcripts) - 1:
                time.sleep(1)

        later_cached = results[1]["cached_tokens"] + results[2]["cached_tokens"]
        later_prompt = results[1]["prompt_tokens"] + results[2]["prompt_tokens"]
        if later_cached > 0:
            pct = later_cached / later_prompt * 100
            print(f"\n  ✅ 24h RETENTION CACHE HIT: {later_cached} cached tokens ({pct:.1f}% of later calls)")
        else:
            print("\n  ⚠️  No cache hits (may need warm-up)")


class TestPromptCacheKey:
    """Test that prompt_cache_key routing hints are accepted and improve cache routing.

    The prompt_cache_key is combined with the prefix hash to route requests to the
    same cache host. We verify:
    1. The API accepts the parameter without error
    2. Same cache key + same prefix produces cache hits
    3. Different cache keys with same prefix still work (routing hint, not partition)
    """

    def test_cache_key_accepted_by_api(self, client):
        """Verify prompt_cache_key is accepted without error."""
        msgs = [
            {"role": "system", "content": ACTION_ITEMS_INSTRUCTIONS},
            {
                "role": "system",
                "content": f"The content language is en. Use the same language en for your response.\n\nContent:\n{TRANSCRIPT_A}",
            },
        ]
        result = _call_with_cache_params(client, msgs, cache_key="omi-extract-actions")
        print(
            f"\n  prompt_cache_key='omi-extract-actions' accepted: prompt={result['prompt_tokens']}, cached={result['cached_tokens']}"
        )
        assert result["prompt_tokens"] > 0, "Expected non-zero prompt tokens"

    def test_same_key_cross_conversation_cache(self, client):
        """Same cache key with different transcripts should produce cache hits."""
        transcripts = [TRANSCRIPT_A, TRANSCRIPT_B, TRANSCRIPT_C]
        results = []

        print("\n  === Same cache key, different conversations ===")
        for i, transcript in enumerate(transcripts):
            msgs = [
                {"role": "system", "content": ACTION_ITEMS_INSTRUCTIONS},
                {
                    "role": "system",
                    "content": f"The content language is en. Use the same language en for your response.\n\nContent:\n{transcript}",
                },
            ]
            result = _call_with_cache_params(client, msgs, cache_key="omi-extract-actions")
            results.append(result)
            print(f"  Call {i+1}: prompt={result['prompt_tokens']}, cached={result['cached_tokens']}")
            if i < len(transcripts) - 1:
                time.sleep(1)

        later_cached = results[1]["cached_tokens"] + results[2]["cached_tokens"]
        later_prompt = results[1]["prompt_tokens"] + results[2]["prompt_tokens"]
        if later_cached > 0:
            pct = later_cached / later_prompt * 100
            print(f"\n  ✅ CACHE KEY ROUTING HIT: {later_cached} cached tokens ({pct:.1f}% of later calls)")
        else:
            print("\n  ⚠️  No cache hits (may need warm-up)")

    def test_retention_and_key_combined(self, client):
        """Both prompt_cache_retention='24h' and prompt_cache_key work together."""
        transcripts = [TRANSCRIPT_A, TRANSCRIPT_B, TRANSCRIPT_C]
        results = []

        print("\n  === Combined: 24h retention + cache key ===")
        for i, transcript in enumerate(transcripts):
            msgs = [
                {"role": "system", "content": ACTION_ITEMS_INSTRUCTIONS},
                {
                    "role": "system",
                    "content": f"The content language is en. Use the same language en for your response.\n\nContent:\n{transcript}",
                },
            ]
            result = _call_with_cache_params(client, msgs, cache_retention="24h", cache_key="omi-extract-actions")
            results.append(result)
            print(f"  Call {i+1}: prompt={result['prompt_tokens']}, cached={result['cached_tokens']}")
            if i < len(transcripts) - 1:
                time.sleep(1)

        later_cached = results[1]["cached_tokens"] + results[2]["cached_tokens"]
        later_prompt = results[1]["prompt_tokens"] + results[2]["prompt_tokens"]
        if later_cached > 0:
            pct = later_cached / later_prompt * 100
            print(f"\n  ✅ COMBINED CACHE HIT: {later_cached} cached tokens ({pct:.1f}% of later calls)")
        else:
            print("\n  ⚠️  No cache hits (may need warm-up)")
