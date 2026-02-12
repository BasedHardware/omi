"""
Integration eval: compare gpt-4 vs gpt-4.1-mini on topic extraction quality.

Uses gpt-5.1 as an impartial judge to score both outputs on relevance,
completeness, and granularity.  No Jaccard — pure semantic evaluation.

Usage:
    OPENAI_API_KEY=sk-... pytest backend/tests/integration/test_mentor_topics_eval.py -v -s

Requires: OPENAI_API_KEY env var set.
"""

import json
import os
import time
from typing import Dict, List, Tuple

import pytest

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

JUDGE_MODEL = "gpt-5.1"

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
    """Call a model for topic extraction, return (topics, latency_ms, valid_json)."""
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


def _judge(conversation: str, topics_a: List[str], topics_b: List[str]) -> Dict:
    """Use gpt-5.1 to judge topic extraction quality. Model A vs Model B (blind)."""
    prompt = f"""You are an impartial judge evaluating topic extraction quality.

Given the original conversation and two candidate topic lists (A and B), score each on:

1. **relevance** (1-5): Are the extracted topics actually discussed in the conversation? Penalise hallucinated topics.
2. **completeness** (1-5): Does the list cover all key topics in the conversation? Penalise significant omissions.
3. **granularity** (1-5): Are topics at a useful level of specificity? Too broad (e.g. "stuff") or too narrow (e.g. "the word hello at minute 2") should score lower.

Then pick a **winner**: "A", "B", or "tie".

Respond with ONLY valid JSON, no other text:
{{"a_relevance": int, "a_completeness": int, "a_granularity": int, "b_relevance": int, "b_completeness": int, "b_granularity": int, "winner": "A"|"B"|"tie", "reason": "one sentence"}}

---
CONVERSATION:
{conversation}

MODEL A topics: {json.dumps(topics_a)}
MODEL B topics: {json.dumps(topics_b)}"""

    try:
        response = client.chat.completions.create(
            model=JUDGE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_completion_tokens=300,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        print(f"  JUDGE ERROR: {e}")
        return None


class TestTopicExtractionEval:
    """Side-by-side eval of gpt-4 vs gpt-4.1-mini, judged by gpt-5.1."""

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

    def test_llm_judge_quality_comparison(self):
        """gpt-5.1 judges gpt-4 (A) vs gpt-4.1-mini (B) on each sample."""
        results = []
        a_wins = 0
        b_wins = 0
        ties = 0

        print("\n" + "=" * 100)
        print(
            f"  {'Sample':<20} {'Winner':>7} {'A_rel':>5} {'A_comp':>6} {'A_gran':>6} {'B_rel':>5} {'B_comp':>6} {'B_gran':>6}  Reason"
        )
        print("-" * 100)

        for sample in EVAL_SAMPLES:
            gpt4_topics, gpt4_ms, _ = _call_model("gpt-4", sample["text"])
            mini_topics, mini_ms, _ = _call_model("gpt-4.1-mini", sample["text"])

            # A = gpt-4, B = gpt-4.1-mini (blind to judge)
            verdict = _judge(sample["text"], gpt4_topics, mini_topics)
            if not verdict:
                print(f"  {sample['id']:<20} JUDGE FAILED")
                continue

            winner = verdict.get("winner", "tie")
            if winner == "A":
                a_wins += 1
            elif winner == "B":
                b_wins += 1
            else:
                ties += 1

            results.append(
                {
                    "id": sample["id"],
                    "gpt4_topics": gpt4_topics,
                    "mini_topics": mini_topics,
                    "gpt4_ms": gpt4_ms,
                    "mini_ms": mini_ms,
                    "verdict": verdict,
                }
            )

            reason = verdict.get("reason", "")[:50]
            print(
                f"  {sample['id']:<20} {winner:>7}"
                f" {verdict.get('a_relevance', '?'):>5} {verdict.get('a_completeness', '?'):>6} {verdict.get('a_granularity', '?'):>6}"
                f" {verdict.get('b_relevance', '?'):>5} {verdict.get('b_completeness', '?'):>6} {verdict.get('b_granularity', '?'):>6}"
                f"  {reason}"
            )

        print("-" * 100)

        # Aggregate scores
        n = len(results)
        if n == 0:
            pytest.fail("No results — judge failed on all samples")

        avg_a_rel = sum(r["verdict"]["a_relevance"] for r in results) / n
        avg_a_comp = sum(r["verdict"]["a_completeness"] for r in results) / n
        avg_a_gran = sum(r["verdict"]["a_granularity"] for r in results) / n
        avg_b_rel = sum(r["verdict"]["b_relevance"] for r in results) / n
        avg_b_comp = sum(r["verdict"]["b_completeness"] for r in results) / n
        avg_b_gran = sum(r["verdict"]["b_granularity"] for r in results) / n
        avg_a_total = (avg_a_rel + avg_a_comp + avg_a_gran) / 3
        avg_b_total = (avg_b_rel + avg_b_comp + avg_b_gran) / 3

        avg_gpt4_ms = sum(r["gpt4_ms"] for r in results) / n
        avg_mini_ms = sum(r["mini_ms"] for r in results) / n

        print(f"\n  JUDGE SUMMARY (gpt-5.1):")
        print(f"  Model A = gpt-4, Model B = gpt-4.1-mini")
        print(f"")
        print(f"  Wins:  gpt-4: {a_wins}  |  gpt-4.1-mini: {b_wins}  |  ties: {ties}")
        print(f"")
        print(f"  Avg scores (1-5):")
        print(f"    {'':>20} {'Relevance':>10} {'Complete':>10} {'Granular':>10} {'Overall':>10}")
        print(f"    {'gpt-4':>20} {avg_a_rel:>10.1f} {avg_a_comp:>10.1f} {avg_a_gran:>10.1f} {avg_a_total:>10.2f}")
        print(
            f"    {'gpt-4.1-mini':>20} {avg_b_rel:>10.1f} {avg_b_comp:>10.1f} {avg_b_gran:>10.1f} {avg_b_total:>10.2f}"
        )
        print(f"")
        print(
            f"  Latency:  gpt-4: {avg_gpt4_ms:.0f}ms  |  gpt-4.1-mini: {avg_mini_ms:.0f}ms  |  speedup: {avg_gpt4_ms / avg_mini_ms:.1f}x"
        )
        print("=" * 100)

        # Quality gate: gpt-4.1-mini overall score must be >= 80% of gpt-4
        assert (
            avg_b_total >= avg_a_total * 0.80
        ), f"gpt-4.1-mini overall {avg_b_total:.2f} is < 80% of gpt-4 {avg_a_total:.2f}"

        # Quality gate: gpt-4.1-mini should not lose majority of head-to-head matchups
        assert (
            b_wins + ties >= a_wins
        ), f"gpt-4.1-mini lost majority: {a_wins} wins for gpt-4 vs {b_wins} for mini ({ties} ties)"

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
