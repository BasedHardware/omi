"""
Live LLM evaluation for the proactive notification system.

Tests the unified prompt + structured output approach. Verifies:
- Generic advice gets low confidence scores / has_advice=false
- Advice connecting to specific goals gets high confidence
- LLM self-regulates when notification history is populated
- Anti-patterns (wellness advice, vague suggestions) produce has_advice=false

Usage:
    cd backend && python -m tests.eval.test_proactive_tools_eval

Requires OPENAI_API_KEY in environment.
"""

import json
import os
import sys
from typing import List, Dict, Any

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# LLM clients
# ---------------------------------------------------------------------------
llm_mini = ChatOpenAI(model="gpt-4.1-mini")
llm_judge = ChatOpenAI(model="gpt-5.1")

# ---------------------------------------------------------------------------
# Pydantic models (same as production)
# ---------------------------------------------------------------------------


class EvalProactiveAdvice(BaseModel):
    notification_text: str = Field(description="Push notification message (<300 chars)")
    reasoning: str = Field(description="Must cite specific facts, goals, or past conversations")
    confidence: float = Field(ge=0, le=1, description="Confidence score 0-1")
    category: str = Field(
        description="One of: goal_connection, pattern_insight, mistake_prevention, dot_connecting, timely_nudge"
    )


class EvalProactiveNotificationResult(BaseModel):
    has_advice: bool = Field(description="True only when notification scores high on at least 3 of 4 axes")
    advice: EvalProactiveAdvice | None = Field(default=None)
    context_summary: str = Field(default="")


# ---------------------------------------------------------------------------
# Prompt (same as production)
# ---------------------------------------------------------------------------
PROACTIVE_NOTIFICATION_PROMPT = '''You are {user_name}'s sharp, observant friend who knows their history, goals, and patterns.
Your job: connect dots across time and conversations that {user_name} wouldn't connect themselves.

== {user_name}'S FACTS & PERSONALITY ==
{user_facts}

== {user_name}'S ACTIVE GOALS ==
{goals_text}

== RELEVANT PAST CONVERSATIONS ==
{past_conversations}

== CURRENT LIVE CONVERSATION ==
{current_conversation}

== YOUR RECENT NOTIFICATIONS (last 20) ==
{recent_notifications}

== NOTIFICATION FREQUENCY SETTING ==
{frequency_guidance}

== EVALUATION FRAMEWORK ==
Before sending ANY notification, evaluate on these four axes:

1. ACTIONABILITY: Can {user_name} DO something concrete right now based on this?
2. TIMELINESS: Does this matter NOW vs later? Is there a window closing?
3. NON-OBVIOUSNESS: Would {user_name} have figured this out themselves? (This is the "holy shit" axis.)
4. CONNECTION TO HISTORY/GOALS: Does this link the current conversation to their stated goals, past patterns, or previous commitments?

Set has_advice=true ONLY when the notification scores high on at least 3 of these 4 axes.

== CONFIDENCE CALIBRATION ==
- 0.90+: Preventing a specific mistake OR a critical connection to their goals that they clearly don't see
- 0.75-0.89: Non-obvious dot-connecting across conversations/history
- 0.50-0.74: Useful insight but the user might figure it out themselves
- Below 0.50: Generic advice. Do NOT send.

== ANTI-PATTERNS (never do these) ==
- Generic wellness advice ("take a break", "stay hydrated", "practice gratitude")
- Vague suggestions without specific reference to their history
- Restating what the user just said back to them
- Hedging or presenting both sides
- Advice that doesn't reference a specific fact, goal, or past conversation

== REASONING REQUIREMENT ==
The reasoning field MUST cite a specific fact, goal, or past conversation.
If you cannot write reasoning that cites specifics, set has_advice=false.

== OUTPUT FORMAT ==
- notification_text: <300 chars, direct, like a sharp friend texting. No markdown, no emojis. End with a specific question.
- category: goal_connection | pattern_insight | mistake_prevention | dot_connecting | timely_nudge
'''

FREQUENCY_GUIDANCE_DEFAULT = (
    "Balanced. Interrupt when you have specific, actionable value tied to their goals/patterns. 5-10 per day."
)

# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

# Cases that SHOULD produce high-confidence advice (goal connections, dot-connecting)
HIGH_CONFIDENCE_CASES = [
    {
        "id": "high_01_goal_conflict",
        "user_name": "Emma",
        "user_facts": "Emma has been dieting for 2 months, lost 10 pounds. Tends to emotionally eat when stressed.",
        "goals": [{"title": "Lose 20 pounds by June"}],
        "past_conversations": "2 weeks ago Emma said: 'I'm so proud of my progress, 10 pounds down. I can't let stress derail me again.'",
        "current_conversation": "[Emma]: I'm thinking of ordering pizza tonight\n[other]: Sounds good\n[Emma]: Yeah, and maybe some wings too. I deserve a treat. Work has been brutal.",
        "recent_notifications": "",
        "expected_has_advice": True,
        "expected_min_confidence": 0.75,
        "description": "Clear goal conflict with emotional eating pattern from history",
    },
    {
        "id": "high_02_saving_conflict",
        "user_name": "Jake",
        "user_facts": "Jake has been saving for a down payment on a house. Currently at $35,000 of $50,000 goal.",
        "goals": [{"title": "Save $50,000 for house down payment by December"}],
        "past_conversations": "Last week Jake said: 'I'm behind schedule on the house fund. Need to cut back on impulse purchases.'",
        "current_conversation": "[Jake]: I'm going to buy that new gaming console\n[other]: Nice, which one?\n[Jake]: The latest one, it's only 600 bucks",
        "recent_notifications": "",
        "expected_has_advice": True,
        "expected_min_confidence": 0.75,
        "description": "Direct goal conflict: impulse purchase vs house savings",
    },
    {
        "id": "high_03_training_skip",
        "user_name": "Sara",
        "user_facts": "Sara is training for a half marathon in 6 weeks. Has been consistent until this week.",
        "goals": [{"title": "Run half marathon in under 2 hours"}],
        "past_conversations": "3 days ago Sara's coach told her: 'The next 6 weeks are critical. Every session counts.'",
        "current_conversation": "[Sara]: I'm going to skip my morning run tomorrow\n[other]: Why?\n[Sara]: I want to sleep in. I'll run next week instead",
        "recent_notifications": "",
        "expected_has_advice": True,
        "expected_min_confidence": 0.75,
        "description": "Skipping training with deadline approaching, coach warning in history",
    },
    {
        "id": "high_04_startup_abandon",
        "user_name": "Ben",
        "user_facts": "Ben has been building a startup for 8 months with 500 users. Recently got accepted to an accelerator.",
        "goals": [{"title": "Grow startup to 5,000 users by Q3"}],
        "past_conversations": "Last month Ben said: 'Getting into the accelerator was a game changer. I'm all in on this.'",
        "current_conversation": "[Ben]: I'm going to accept that job offer at the big company\n[other]: What about your startup?\n[Ben]: I'll put it on pause. The salary is too good to pass up",
        "recent_notifications": "",
        "expected_has_advice": True,
        "expected_min_confidence": 0.75,
        "description": "Abandoning startup right after accelerator acceptance",
    },
    {
        "id": "high_05_dot_connecting",
        "user_name": "Lisa",
        "user_facts": "Lisa is a product manager. Recently complained about her team's velocity dropping.",
        "goals": [{"title": "Ship v2.0 by end of March"}],
        "past_conversations": "2 weeks ago Lisa mentioned: 'I think the issue is that we're in too many meetings. Nobody has time to actually code.'",
        "current_conversation": "[Lisa]: My manager wants to add a daily 1-hour standup for the whole team\n[other]: On top of existing meetings?\n[Lisa]: Yeah, he thinks more alignment will help us ship faster",
        "recent_notifications": "",
        "expected_has_advice": True,
        "expected_min_confidence": 0.70,
        "description": "Connecting: user identified meetings as problem, now more meetings being added",
    },
]

# Cases that SHOULD produce low confidence / no advice (generic, no connections)
LOW_CONFIDENCE_CASES = [
    {
        "id": "low_01_casual_lunch",
        "user_name": "Jo",
        "user_facts": "Jo likes trying new restaurants.",
        "goals": [],
        "past_conversations": "",
        "current_conversation": "[Jo]: Had a great lunch today\n[other]: Nice, where did you go?\n[Jo]: That new Thai place downtown, really good pad thai",
        "recent_notifications": "",
        "expected_has_advice": False,
        "expected_max_confidence": 0.50,
        "description": "Casual lunch conversation, no goals to connect to",
    },
    {
        "id": "low_02_productive_day",
        "user_name": "Nora",
        "user_facts": "Nora is a project manager.",
        "goals": [],
        "past_conversations": "",
        "current_conversation": "[Nora]: I had a really productive day today\n[other]: That's awesome! What did you accomplish?\n[Nora]: Finished the report, had a great meeting, and even went for a run",
        "recent_notifications": "",
        "expected_has_advice": False,
        "expected_max_confidence": 0.50,
        "description": "Positive day, nothing to advise on",
    },
    {
        "id": "low_03_reading_aligned",
        "user_name": "Dan",
        "user_facts": "Dan loves reading.",
        "goals": [{"title": "Read 2 books per month"}],
        "past_conversations": "",
        "current_conversation": "[Dan]: I'm going to read for an hour today\n[other]: What book?\n[Dan]: That new fiction book I bought. Really enjoying it",
        "recent_notifications": "",
        "expected_has_advice": False,
        "expected_max_confidence": 0.50,
        "description": "User is aligned with their goal, no conflict",
    },
    {
        "id": "low_04_meditation_aligned",
        "user_name": "Chloe",
        "user_facts": "Chloe struggles with focus at work.",
        "goals": [{"title": "Improve focus and productivity at work"}],
        "past_conversations": "",
        "current_conversation": "[Chloe]: I'm going to start meditating every morning\n[other]: That's a great idea\n[Chloe]: Yeah, I heard it helps with focus",
        "recent_notifications": "",
        "expected_has_advice": False,
        "expected_max_confidence": 0.50,
        "description": "User is taking action aligned with goal",
    },
    {
        "id": "low_05_weather_chat",
        "user_name": "Pat",
        "user_facts": "Pat lives in Seattle.",
        "goals": [],
        "past_conversations": "",
        "current_conversation": "[Pat]: It's raining again\n[other]: Typical Seattle\n[Pat]: Yeah, at least I have a good umbrella",
        "recent_notifications": "",
        "expected_has_advice": False,
        "expected_max_confidence": 0.50,
        "description": "Small talk about weather",
    },
]

# Cases testing self-regulation (notification history populated)
SELF_REGULATION_CASES = [
    {
        "id": "reg_01_already_notified",
        "user_name": "Mike",
        "user_facts": "Mike starts many courses but rarely finishes them.",
        "goals": [{"title": "Complete AWS certification by March"}],
        "past_conversations": "",
        "current_conversation": "[Mike]: I signed up for another online course\n[other]: Which one?\n[Mike]: Machine learning. That's my fifth course this month",
        "recent_notifications": (
            "[2024-01-15 10:00] Mike, you've signed up for 3 new courses this month but haven't finished your AWS cert prep. Maybe finish one thing before starting another?\n"
            "[2024-01-15 14:00] Hey Mike, your AWS cert exam is in 6 weeks. How's the study plan going?\n"
            "[2024-01-16 09:00] Mike, I noticed you opened another Udemy tab. Remember your AWS cert goal — would focusing on that feel better than spreading thin?"
        ),
        "expected_has_advice": False,
        "expected_max_confidence": 0.60,
        "description": "Same topic already covered in 3 recent notifications",
    },
]

# Anti-pattern cases (should never produce advice)
ANTI_PATTERN_CASES = [
    {
        "id": "anti_01_generic_wellness",
        "user_name": "Alex",
        "user_facts": "Alex is a software engineer.",
        "goals": [],
        "past_conversations": "",
        "current_conversation": "[Alex]: I've been working late again\n[other]: You should take a break\n[Alex]: Yeah maybe",
        "recent_notifications": "",
        "expected_has_advice": False,
        "expected_max_confidence": 0.50,
        "description": "Should not produce generic 'take a break' advice",
    },
    {
        "id": "anti_02_vague_suggestion",
        "user_name": "Sam",
        "user_facts": "Sam is 32, focused on career.",
        "goals": [],
        "past_conversations": "",
        "current_conversation": "[Sam]: I'm not sure what to do with my life\n[other]: That's deep\n[Sam]: Yeah, just feeling lost",
        "recent_notifications": "",
        "expected_has_advice": False,
        "expected_max_confidence": 0.50,
        "description": "No specific facts/goals to connect to — any advice would be generic",
    },
]


def run_evaluation(case: Dict[str, Any]) -> Dict[str, Any]:
    """Run a single test case against gpt-4.1-mini with structured output."""
    goals_text = "No active goals set."
    if case.get("goals"):
        goals_text = "\n".join(f"- {g['title']}" for g in case["goals"])

    prompt = PROACTIVE_NOTIFICATION_PROMPT.format(
        user_name=case["user_name"],
        user_facts=case["user_facts"],
        goals_text=goals_text,
        past_conversations=case.get("past_conversations") or "No relevant past conversations found.",
        current_conversation=case["current_conversation"],
        recent_notifications=case.get("recent_notifications") or "No recent notifications sent.",
        frequency_guidance=FREQUENCY_GUIDANCE_DEFAULT,
    )

    with_parser = llm_mini.with_structured_output(EvalProactiveNotificationResult)
    result: EvalProactiveNotificationResult = with_parser.invoke(prompt)

    return {
        "case_id": case["id"],
        "has_advice": result.has_advice,
        "confidence": result.advice.confidence if result.advice else 0,
        "notification_text": result.advice.notification_text if result.advice else "",
        "reasoning": result.advice.reasoning if result.advice else "",
        "category": result.advice.category if result.advice else "",
        "context_summary": result.context_summary,
    }


def judge_result(case: Dict[str, Any], eval_result: Dict[str, Any]) -> Dict[str, Any]:
    """Use gpt-5.1 to judge quality of the notification decision."""
    judge_prompt = f"""You are evaluating a proactive notification system's decision.

SCENARIO:
- User: {case["user_name"]}
- Facts: {case["user_facts"]}
- Goals: {json.dumps(case.get("goals", []))}
- Past conversations: {case.get("past_conversations", "None")}
- Current conversation:
{case["current_conversation"]}
- Recent notifications already sent: {case.get("recent_notifications", "None")}

SYSTEM DECISION:
- has_advice: {eval_result["has_advice"]}
- confidence: {eval_result["confidence"]}
- notification_text: "{eval_result["notification_text"]}"
- reasoning: "{eval_result["reasoning"]}"

EVALUATION CRITERIA:
1. DECISION CORRECTNESS (1-5): Was has_advice correct? Should advice have been sent?
   - If the conversation has a clear connection to goals/history: advice should be sent
   - If casual/aligned/no-goal: advice should NOT be sent
2. CONFIDENCE CALIBRATION (1-5): Is the confidence appropriate?
   - High confidence should be reserved for non-obvious dot-connecting
   - Generic advice should get low confidence
3. REASONING QUALITY (1-5): Does the reasoning cite specific facts, goals, or history?
   - Good: "User's goal X conflicts with action Y, and 2 weeks ago they said Z"
   - Bad: "User seems to be doing something that might not be ideal"
4. NOTIFICATION QUALITY (1-5): If sent, is it specific, actionable, non-generic?
   - Good: References specific details, asks a pointed question
   - Bad: Generic wellness advice, vague suggestions
5. SELF-REGULATION (1-5): If notification history is populated, does it avoid repeating?

Return ONLY a JSON object:
{{"decision_correctness": N, "confidence_calibration": N, "reasoning_quality": N, "notification_quality": N, "self_regulation": N, "total": N, "explanation": "brief explanation"}}

Total is the sum (max 25). Score >= 18 is PASS."""

    resp = llm_judge.invoke(judge_prompt)
    try:
        content = resp.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        scores = json.loads(content)
        scores["pass"] = scores.get("total", 0) >= 18
        return scores
    except Exception as e:
        return {"error": str(e), "raw": resp.content, "pass": False}


def main():
    all_cases = HIGH_CONFIDENCE_CASES + LOW_CONFIDENCE_CASES + SELF_REGULATION_CASES + ANTI_PATTERN_CASES

    print(f"\n{'='*70}")
    print(f"PROACTIVE NOTIFICATION SYSTEM — LIVE EVAL ({len(all_cases)} test cases)")
    print(f"Model: gpt-4.1-mini (structured output) | Judge: gpt-5.1")
    print(f"{'='*70}\n")

    results = []
    category_stats = {
        "high": {"total": 0, "correct": 0, "judge_pass": 0},
        "low": {"total": 0, "correct": 0, "judge_pass": 0},
        "reg": {"total": 0, "correct": 0, "judge_pass": 0},
        "anti": {"total": 0, "correct": 0, "judge_pass": 0},
    }

    for case in all_cases:
        category = case["id"].split("_")[0]
        category_stats[category]["total"] += 1

        print(f"  [{case['id']}] {case['description'][:50]}... ", end="", flush=True)

        eval_result = run_evaluation(case)

        # Check basic correctness
        correct = True
        if "expected_has_advice" in case:
            correct = eval_result["has_advice"] == case["expected_has_advice"]
        if correct and "expected_min_confidence" in case and eval_result["has_advice"]:
            correct = eval_result["confidence"] >= case["expected_min_confidence"]
        if correct and "expected_max_confidence" in case:
            correct = eval_result["confidence"] <= case["expected_max_confidence"] or not eval_result["has_advice"]

        if correct:
            category_stats[category]["correct"] += 1

        # Judge
        judge_result_data = judge_result(case, eval_result)
        if judge_result_data.get("pass"):
            category_stats[category]["judge_pass"] += 1

        # Status output
        advice_str = f"advice={eval_result['has_advice']} conf={eval_result['confidence']:.2f}"
        if eval_result["has_advice"]:
            advice_str += f" cat={eval_result['category']}"
        judge_str = f"judge={judge_result_data.get('total', 'N/A')}/25"
        pass_str = "PASS" if judge_result_data.get("pass") and correct else "FAIL"

        print(f"{pass_str} {advice_str} {judge_str}")

        if not judge_result_data.get("pass") or not correct:
            if eval_result.get("notification_text"):
                print(f"         text: {eval_result['notification_text'][:100]}")
            if judge_result_data.get("explanation"):
                print(f"         judge: {judge_result_data['explanation'][:120]}")

        results.append(
            {
                "case": case,
                "eval_result": eval_result,
                "judge_result": judge_result_data,
                "correct": correct,
            }
        )

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")

    total_pass = sum(1 for r in results if r["judge_result"].get("pass") and r["correct"])
    total = len(results)

    for cat, label in [
        ("high", "High Confidence (goal conflicts, dot-connecting)"),
        ("low", "Low Confidence (casual, aligned)"),
        ("reg", "Self-Regulation (notification history)"),
        ("anti", "Anti-Patterns (generic, vague)"),
    ]:
        stats = category_stats[cat]
        if stats["total"] > 0:
            print(f"\n  {label}:")
            print(f"    Decision accuracy: {stats['correct']}/{stats['total']}")
            print(f"    Judge pass:        {stats['judge_pass']}/{stats['total']}")

    print(f"\n  OVERALL: {total_pass}/{total} passed ({total_pass/total*100:.0f}%)")
    print(f"{'='*70}\n")

    # Write results to file
    output_path = os.path.join(os.path.dirname(__file__), "proactive_tools_eval_results.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Full results written to: {output_path}")

    return total_pass >= total * 0.7  # Pass if >= 70%


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
