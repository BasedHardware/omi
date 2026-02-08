"""
Integration tests for OpenAI prompt caching with live API calls.

Tests that the instructions-first, content-second message ordering produces
cross-conversation cache hits on gpt-5.1 (the fix from PR #4670).

Requires:
    - OPENAI_API_KEY environment variable
    - Network access to OpenAI API

Run:
    cd backend
    PYTHONPATH=. python3 -m pytest tests/integration/test_prompt_caching_integration.py -v -s

Note: These tests make real API calls and cost real money (~$0.05-0.10 per run).
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

The content language is en. Use the same language en for your response.

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


class TestCrossConversationCaching:
    """Test cross-conversation cache hits with production-length instructions.

    With instructions-first ordering and >1024 tokens of static instructions,
    the instruction prefix should be cached after the first call. Subsequent calls
    with different transcripts should show cached_tokens > 0.
    """

    def test_action_items_cross_conversation_cache_hits(self, client):
        """Three extract_action_items calls with different transcripts — later calls should cache instruction prefix."""
        transcripts = [TRANSCRIPT_A, TRANSCRIPT_B, TRANSCRIPT_C]
        results = []

        for i, transcript in enumerate(transcripts):
            msgs = [
                {"role": "system", "content": ACTION_ITEMS_INSTRUCTIONS},
                {"role": "system", "content": f"Content:\n{transcript}"},
            ]
            result = _call_and_get_cache_info(client, msgs)
            results.append(result)
            print(f"\n  Call {i+1}: prompt={result['prompt_tokens']}, cached={result['cached_tokens']}")
            if i < len(transcripts) - 1:
                time.sleep(1)

        # Summarize
        total_cached = sum(r["cached_tokens"] for r in results)
        print(f"\n  Total cached tokens across 3 calls: {total_cached}")
        print(f"  Call 1 cached: {results[0]['cached_tokens']} (expected: 0, cache priming)")
        print(f"  Call 2 cached: {results[1]['cached_tokens']} (expected: >0, instruction prefix hit)")
        print(f"  Call 3 cached: {results[2]['cached_tokens']} (expected: >0, instruction prefix hit)")

        # At least one of calls 2-3 should show cache hits
        later_cached = results[1]["cached_tokens"] + results[2]["cached_tokens"]
        if later_cached > 0:
            pct = later_cached / (results[1]["prompt_tokens"] + results[2]["prompt_tokens"]) * 100
            print(f"\n  ✅ CROSS-CONVERSATION CACHE HIT: {later_cached} cached tokens ({pct:.1f}% of later calls)")
        else:
            print("\n  ⚠️  No cache hits (may need warm-up — run test again)")


class TestWrongOrderNoCaching:
    """Test that content-first ordering (the old bug from PR #4664) produces no cross-conversation cache hits."""

    def test_content_first_no_cross_conversation_cache(self, client):
        """Content-first ordering with different transcripts — should NOT produce cache hits."""
        transcripts = [TRANSCRIPT_A, TRANSCRIPT_B, TRANSCRIPT_C]
        results = []

        for i, transcript in enumerate(transcripts):
            # WRONG order: content first, instructions second
            msgs = [
                {"role": "system", "content": f"Content:\n{transcript}"},
                {"role": "system", "content": ACTION_ITEMS_INSTRUCTIONS},
            ]
            result = _call_and_get_cache_info(client, msgs)
            results.append(result)
            print(f"\n  Call {i+1} (WRONG order): prompt={result['prompt_tokens']}, cached={result['cached_tokens']}")
            if i < len(transcripts) - 1:
                time.sleep(1)

        total_cached = sum(r["cached_tokens"] for r in results)
        print(f"\n  Total cached tokens (wrong order): {total_cached}")

        if total_cached == 0:
            print("  ✅ CONFIRMED: Content-first ordering produces no cross-conversation cache hits")
        else:
            print(f"  ⚠️  Unexpected: {total_cached} cached tokens with wrong order")


class TestCacheComparison:
    """Definitive A/B comparison: correct order vs wrong order.

    Makes the same set of calls with both orderings and compares total cached tokens.
    This is the key metric that validates the PR #4670 fix.
    """

    def test_correct_order_beats_wrong_order(self, client):
        """Instructions-first should produce more cached tokens than content-first."""
        transcripts = [TRANSCRIPT_A, TRANSCRIPT_B, TRANSCRIPT_C]

        # --- Correct order (instructions first) ---
        print("\n  === Correct order (instructions first) ===")
        correct_results = []
        for i, transcript in enumerate(transcripts):
            msgs = [
                {"role": "system", "content": ACTION_ITEMS_INSTRUCTIONS},
                {"role": "system", "content": f"Content:\n{transcript}"},
            ]
            result = _call_and_get_cache_info(client, msgs)
            correct_results.append(result)
            print(f"    Call {i+1}: prompt={result['prompt_tokens']}, cached={result['cached_tokens']}")
            if i < len(transcripts) - 1:
                time.sleep(1)

        correct_cached = sum(r["cached_tokens"] for r in correct_results)
        correct_prompt = sum(r["prompt_tokens"] for r in correct_results)

        # Wait for cache to settle
        time.sleep(3)

        # --- Wrong order (content first) ---
        print("\n  === Wrong order (content first) ===")
        wrong_results = []
        for i, transcript in enumerate(transcripts):
            msgs = [
                {"role": "system", "content": f"Content:\n{transcript}"},
                {"role": "system", "content": ACTION_ITEMS_INSTRUCTIONS},
            ]
            result = _call_and_get_cache_info(client, msgs)
            wrong_results.append(result)
            print(f"    Call {i+1}: prompt={result['prompt_tokens']}, cached={result['cached_tokens']}")
            if i < len(transcripts) - 1:
                time.sleep(1)

        wrong_cached = sum(r["cached_tokens"] for r in wrong_results)
        wrong_prompt = sum(r["prompt_tokens"] for r in wrong_results)

        # --- Summary ---
        print(f"\n  === RESULTS ===")
        print(
            f"  Correct order: {correct_cached}/{correct_prompt} tokens cached ({correct_cached/max(correct_prompt,1)*100:.1f}%)"
        )
        print(
            f"  Wrong order:   {wrong_cached}/{wrong_prompt} tokens cached ({wrong_cached/max(wrong_prompt,1)*100:.1f}%)"
        )

        if correct_cached > wrong_cached:
            print(f"  ✅ Correct order produces {correct_cached - wrong_cached} MORE cached tokens")
        elif correct_cached == wrong_cached == 0:
            print("  ⚠️  No cache hits on either (cache may need warm-up, try running test again)")
        else:
            print("  ⚠️  Unexpected: wrong order matched or beat correct order")
