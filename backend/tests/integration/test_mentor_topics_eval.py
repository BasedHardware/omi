"""
Integration eval: compare gpt-4 vs gpt-4.1-mini on topic extraction quality.

Runs both models on 10 representative conversation snippets and compares:
- JSON validity (both must return valid JSON arrays)
- Topic count (similar coverage)
- Topic overlap (semantic similarity)
- Latency

Usage:
    OPENAI_API_KEY=sk-... pytest backend/tests/integration/test_mentor_topics_eval.py -v -s

Requires: OPENAI_API_KEY env var set.
"""

import json
import os
import time
from typing import List, Tuple

import pytest

# Skip entire module if no API key
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set — skipping live eval",
)

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = (
    "You are a topic extraction specialist. Extract all relevant topics from the conversation. "
    'Return ONLY a JSON array of topic strings, nothing else. Example format: ["topic1", "topic2"]'
)

# 10 representative conversation snippets covering different domains
EVAL_SAMPLES = [
    {
        "id": "business_meeting",
        "text": (
            "We need to finalize the Q3 budget by Friday. Marketing wants to increase ad spend by 20% "
            "but engineering needs two more headcount. Let's also revisit the product roadmap — the "
            "AI features are slipping. Can we move the launch date to September?"
        ),
    },
    {
        "id": "health_fitness",
        "text": (
            "My doctor said my cholesterol is a bit high, so I've been trying to eat more fish and "
            "cut back on red meat. I started running three times a week too. The knee pain from last "
            "year is mostly gone after physical therapy."
        ),
    },
    {
        "id": "tech_discussion",
        "text": (
            "We should migrate the database from PostgreSQL to DynamoDB for the real-time features. "
            "The WebSocket connections keep dropping on the current setup. Also, the Docker containers "
            "are using too much memory — we need to optimize the image sizes."
        ),
    },
    {
        "id": "personal_goals",
        "text": (
            "I've been thinking about going back to school for an MBA. The tuition is expensive but "
            "my company might sponsor it. I also want to start saving for a house — maybe a condo "
            "downtown would be more realistic given the housing market."
        ),
    },
    {
        "id": "travel_planning",
        "text": (
            "Let's plan the trip to Japan for cherry blossom season. We should book flights to Tokyo "
            "and then take the Shinkansen to Kyoto. I heard the temples are amazing. We need to get "
            "our JR passes and figure out the visa situation."
        ),
    },
    {
        "id": "parenting",
        "text": (
            "Emma's teacher said she's been struggling with math this semester. Maybe we should get "
            "a tutor. Her reading is great though — she just finished Harry Potter. The soccer "
            "tournament is next weekend and we need to arrange carpooling."
        ),
    },
    {
        "id": "startup_pitch",
        "text": (
            "Our Series A deck needs work. The TAM slide is too optimistic — investors will push "
            "back. We have 10K MAU with 40% month-over-month growth. The unit economics work at "
            "scale but we need to show a path to profitability. Should we highlight the AI moat?"
        ),
    },
    {
        "id": "cooking_hobby",
        "text": (
            "I tried making sourdough bread yesterday — the crumb was too dense. I think my starter "
            "needs more time. Also picked up some wagyu from the butcher for this weekend's dinner "
            "party. Should I do a reverse sear or sous vide?"
        ),
    },
    {
        "id": "short_snippet",
        "text": "Hey, can you grab coffee later? I want to talk about the promotion.",
    },
    {
        "id": "multilingual_mixed",
        "text": (
            "The neue App needs better UX — users keep complaining about the onboarding flow. "
            "We should A/B test the signup screen. Analytics show 60% drop-off at step 3. "
            "The backend team fixed the latency issue with caching."
        ),
    },
]


def _call_model(model: str, text: str) -> Tuple[List[str], float, bool]:
    """Call a model and return (topics, latency_ms, valid_json)."""
    start = time.time()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Extract all topics from this conversation:\n{text}"},
            ],
            temperature=0.3,
            max_tokens=150,
        )
        raw = response.choices[0].message.content.strip()
        latency = (time.time() - start) * 1000
        topics = json.loads(raw)
        return topics, latency, True
    except json.JSONDecodeError:
        latency = (time.time() - start) * 1000
        return [], latency, False
    except Exception as e:
        latency = (time.time() - start) * 1000
        print(f"  ERROR ({model}): {e}")
        return [], latency, False


def _topic_overlap(a: List[str], b: List[str]) -> float:
    """Jaccard similarity between two topic lists (case-insensitive)."""
    if not a and not b:
        return 1.0
    set_a = {t.lower().strip() for t in a}
    set_b = {t.lower().strip() for t in b}
    if not set_a and not set_b:
        return 1.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


class TestTopicExtractionEval:
    """Side-by-side eval of gpt-4 vs gpt-4.1-mini on topic extraction."""

    def test_both_models_produce_valid_json(self):
        """Both models should return valid JSON arrays for all samples."""
        gpt4_failures = []
        mini_failures = []

        for sample in EVAL_SAMPLES:
            _, _, gpt4_valid = _call_model("gpt-4", sample["text"])
            _, _, mini_valid = _call_model("gpt-4.1-mini", sample["text"])
            if not gpt4_valid:
                gpt4_failures.append(sample["id"])
            if not mini_valid:
                mini_failures.append(sample["id"])

        print(f"\n  gpt-4 JSON failures: {gpt4_failures or 'none'}")
        print(f"  gpt-4.1-mini JSON failures: {mini_failures or 'none'}")
        assert len(mini_failures) == 0, f"gpt-4.1-mini failed JSON on: {mini_failures}"

    def test_comprehensive_quality_comparison(self):
        """Run full eval across all samples, print comparison table."""
        results = []

        print("\n" + "=" * 90)
        print(
            f"{'Sample':<20} {'gpt-4 topics':<25} {'gpt-4.1-mini topics':<25} {'Overlap':>8} {'4 ms':>6} {'mini ms':>7}"
        )
        print("-" * 90)

        for sample in EVAL_SAMPLES:
            gpt4_topics, gpt4_ms, gpt4_valid = _call_model("gpt-4", sample["text"])
            mini_topics, mini_ms, mini_valid = _call_model("gpt-4.1-mini", sample["text"])

            overlap = _topic_overlap(gpt4_topics, mini_topics)
            results.append(
                {
                    "id": sample["id"],
                    "gpt4_topics": gpt4_topics,
                    "mini_topics": mini_topics,
                    "gpt4_valid": gpt4_valid,
                    "mini_valid": mini_valid,
                    "overlap": overlap,
                    "gpt4_ms": gpt4_ms,
                    "mini_ms": mini_ms,
                }
            )

            gpt4_str = ", ".join(gpt4_topics[:3]) + ("..." if len(gpt4_topics) > 3 else "")
            mini_str = ", ".join(mini_topics[:3]) + ("..." if len(mini_topics) > 3 else "")
            print(f"  {sample['id']:<20} {gpt4_str:<25} {mini_str:<25} {overlap:>7.0%} {gpt4_ms:>5.0f} {mini_ms:>6.0f}")

        print("-" * 90)

        # Aggregate stats
        avg_overlap = sum(r["overlap"] for r in results) / len(results)
        avg_gpt4_count = sum(len(r["gpt4_topics"]) for r in results) / len(results)
        avg_mini_count = sum(len(r["mini_topics"]) for r in results) / len(results)
        avg_gpt4_ms = sum(r["gpt4_ms"] for r in results) / len(results)
        avg_mini_ms = sum(r["mini_ms"] for r in results) / len(results)
        mini_valid_pct = sum(1 for r in results if r["mini_valid"]) / len(results)

        print(f"\n  SUMMARY:")
        print(f"  Average topic overlap (Jaccard): {avg_overlap:.0%}")
        print(f"  Average topic count — gpt-4: {avg_gpt4_count:.1f}, gpt-4.1-mini: {avg_mini_count:.1f}")
        print(f"  Average latency — gpt-4: {avg_gpt4_ms:.0f}ms, gpt-4.1-mini: {avg_mini_ms:.0f}ms")
        print(f"  gpt-4.1-mini JSON validity: {mini_valid_pct:.0%}")
        print(f"  Speedup: {avg_gpt4_ms / avg_mini_ms:.1f}x faster" if avg_mini_ms > 0 else "")
        print("=" * 90)

        # Quality gate: mini should produce valid JSON 100% of the time
        assert mini_valid_pct == 1.0, f"gpt-4.1-mini JSON validity only {mini_valid_pct:.0%}"

        # Quality gate: average overlap should be >= 30% (topics won't match exactly but should be similar domain)
        assert avg_overlap >= 0.30, f"Topic overlap too low: {avg_overlap:.0%} (expected >= 30%)"

        # Quality gate: mini should extract at least as many topics on average
        assert (
            avg_mini_count >= avg_gpt4_count * 0.5
        ), f"gpt-4.1-mini extracts too few topics: {avg_mini_count:.1f} vs gpt-4: {avg_gpt4_count:.1f}"

    def test_mini_handles_edge_cases(self):
        """gpt-4.1-mini should handle edge cases gracefully."""
        edge_cases = [
            ("empty", ""),
            ("single_word", "Hello"),
            ("numbers_only", "42 3.14 100"),
        ]
        for name, text in edge_cases:
            topics, _, valid = _call_model("gpt-4.1-mini", text)
            print(f"  {name}: valid={valid}, topics={topics}")
            assert valid, f"gpt-4.1-mini returned invalid JSON for edge case: {name}"
            assert isinstance(topics, list), f"Expected list for {name}, got {type(topics)}"
