"""
Live LLM evaluation for the proactive mentor notification system.

Tests the unified prompt + structured output approach with rich context.
Verifies:
- Generic advice gets low confidence scores
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

from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI

# ---------------------------------------------------------------------------
# LLM clients
# ---------------------------------------------------------------------------
llm_mini = ChatOpenAI(model="gpt-4.1-mini")
llm_judge = ChatOpenAI(model="gpt-5.1")


# ---------------------------------------------------------------------------
# Models (same as production)
# ---------------------------------------------------------------------------
class ProactiveAdvice(BaseModel):
    notification_text: str = Field(description="The push notification message (<300 chars, direct, personal)")
    reasoning: str = Field(
        description="Why this notification is worth sending. MUST cite a specific fact, goal, or past conversation."
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score")
    category: str = Field(
        description="One of: goal_connection, pattern_insight, mistake_prevention, commitment_reminder, dot_connecting"
    )


class ProactiveNotificationResult(BaseModel):
    has_advice: bool = Field(description="True ONLY when the notification scores high on at least 3 of 4 axes.")
    advice: ProactiveAdvice | None = Field(default=None, description="The notification to send.")
    context_summary: str = Field(description="Brief summary of current conversation context.")


# ---------------------------------------------------------------------------
# Prompt template (same as production)
# ---------------------------------------------------------------------------
PROACTIVE_PROMPT_TEMPLATE = """You are {user_name}'s sharp, observant friend who has been listening to their conversations and knows their history deeply. You are NOT a life coach, therapist, or wellness advisor. You are the friend who connects dots others miss.

Your job: Decide if the current conversation warrants a push notification. Most of the time, it does NOT.

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
Before deciding to send a notification, evaluate on ALL FOUR axes:

1. ACTIONABILITY: Can {user_name} DO something concrete right now based on this? ("You should think about..." = NOT actionable. "Call Mike back about the deal before 5pm" = actionable.)

2. TIMELINESS: Does this matter RIGHT NOW vs later? Is there a window closing? A decision being made? If it can wait until tomorrow, don't send it now.

3. NON-OBVIOUSNESS: Would {user_name} have figured this out themselves? This is the "holy shit" axis. Connecting their goal X with something they said 2 weeks ago with what they're about to do RIGHT NOW = non-obvious. Telling them to "stay focused" = painfully obvious.

4. CONNECTION TO HISTORY/GOALS: Does this link the current conversation to their stated goals, past patterns, or previous commitments? The more specific the connection, the higher the value.

has_advice should be true ONLY when the notification scores high on at least 3 of these 4 axes.

== CONFIDENCE CALIBRATION ==
- 0.90+ : Preventing a concrete mistake OR critical connection to a specific goal with time pressure
- 0.75-0.89 : Non-obvious dot-connecting across different conversations or time periods
- 0.50-0.74 : Useful insight but user might figure it out themselves
- Below 0.50 : Generic observation — DO NOT SEND

== ANTI-PATTERNS (instant has_advice=false) ==
- Generic wellness advice ("take a break", "stay hydrated", "practice mindfulness")
- Vague suggestions without specific references ("you might want to consider...")
- Restating what the user just said back to them
- Motivational platitudes ("you've got this!", "believe in yourself!")
- Advice that doesn't reference a specific fact, goal, or past conversation
- Hedging with "however" or "on the other hand" — take a clear stance or don't send

== REASONING REQUIREMENT ==
The reasoning field MUST cite a specific fact, goal, or past conversation. Example:
- GOOD: "User's goal is 'save $50k for house' and they're about to spend $3k on a vacation they mentioned regretting last month"
- BAD: "User seems stressed and could use some encouragement"
If you cannot write a reasoning that cites a concrete connection, set has_advice=false.

== OUTPUT ==
Always provide context_summary (brief summary of current conversation).
Set has_advice=true only when you have a genuinely valuable, non-obvious notification.
When has_advice=true, provide the full advice object with notification_text (<300 chars), reasoning, confidence, and category."""

FREQUENCY_GUIDANCE = {
    1: "Ultra selective. Only for preventing clear mistakes or truly critical insights. 1-3 per day max.",
    2: "Very selective. Only non-obvious insights that connect to their goals or history. 3-5 per day.",
    3: "Balanced. Interrupt when you have specific, actionable value tied to their goals/patterns. 5-10 per day.",
    4: "Proactive. Share relevant insights connecting current conversation to goals/history. 8-12 per day.",
    5: "Very proactive. Look for any opportunity to connect dots and add value. Up to 12 per day.",
}


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

# Cases where notification SHOULD fire (goal connection, pattern insight, dot-connecting)
SHOULD_NOTIFY_CASES = [
    {
        "id": "goal_01",
        "conversation": [
            "[Emma]: I'm thinking of ordering pizza tonight",
            "[other]: Sounds good",
            "[Emma]: Yeah, and maybe some wings too. Third time this week",
        ],
        "user_name": "Emma",
        "user_facts": "Emma has been dieting for 2 months, lost 10 pounds. She tends to order out when stressed about work.",
        "goals": [{"title": "Lose 20 pounds by June"}],
        "past_conversations": "Last week Emma said she was proud of cooking at home 5 days in a row.",
        "recent_notifications": [],
        "frequency": 3,
        "description": "Goal contradiction with pattern insight",
    },
    {
        "id": "goal_02",
        "conversation": [
            "[Mike]: I signed up for another online course",
            "[other]: Which one?",
            "[Mike]: Machine learning. That's my fifth course this month",
        ],
        "user_name": "Mike",
        "user_facts": "Mike starts many courses but rarely finishes them. He's completed 1 out of 8 courses in the past year.",
        "goals": [{"title": "Complete AWS certification by March"}],
        "past_conversations": "Two weeks ago Mike complained about not finishing things and said he'd focus on AWS only.",
        "recent_notifications": [],
        "frequency": 3,
        "description": "Breaking own commitment with historical pattern",
    },
    {
        "id": "goal_03",
        "conversation": [
            "[Jake]: I'm going to buy that new gaming console",
            "[other]: Nice, which one?",
            "[Jake]: The latest one, it's only 600 bucks",
        ],
        "user_name": "Jake",
        "user_facts": "Jake has been saving for a down payment. Currently at $42,000 saved. Budget is tight.",
        "goals": [{"title": "Save $50,000 for house down payment by December"}],
        "past_conversations": "Last month Jake said every dollar counts toward the house goal.",
        "recent_notifications": [],
        "frequency": 3,
        "description": "Spending contradicts active savings goal",
    },
    {
        "id": "pattern_01",
        "conversation": [
            "[Sara]: I'm going to skip my morning run tomorrow",
            "[other]: Why?",
            "[Sara]: I want to sleep in. I'll run next week instead",
        ],
        "user_name": "Sara",
        "user_facts": "Sara is training for a half marathon in 6 weeks. She's skipped 3 of her last 5 planned runs.",
        "goals": [{"title": "Run half marathon in under 2 hours"}],
        "past_conversations": "Sara said two weeks ago that she can't afford to miss any more training runs.",
        "recent_notifications": [],
        "frequency": 3,
        "description": "Declining pattern threatens goal with time pressure",
    },
    {
        "id": "dot_connect_01",
        "conversation": [
            "[Ben]: I'm going to accept that job offer at the big company",
            "[other]: What about your startup?",
            "[Ben]: I'll put it on pause. The salary is too good to pass up",
        ],
        "user_name": "Ben",
        "user_facts": "Ben has been building a startup for 8 months with 500 users. Last month he said he'd never go back to corporate.",
        "goals": [{"title": "Grow startup to 5,000 users by Q3"}],
        "past_conversations": "Three weeks ago Ben said 'I'd rather eat ramen than go back to a desk job.' His startup just got a mention in TechCrunch.",
        "recent_notifications": [],
        "frequency": 3,
        "description": "Cross-time dot-connecting: contradicting own strong statement",
    },
]

# Cases where notification should NOT fire (generic, obvious, anti-patterns)
SHOULD_NOT_NOTIFY_CASES = [
    {
        "id": "generic_01",
        "conversation": [
            "[Jo]: Had a great lunch today",
            "[other]: Nice, where did you go?",
            "[Jo]: That new Thai place downtown, really good pad thai",
        ],
        "user_name": "Jo",
        "user_facts": "Jo likes trying new restaurants.",
        "goals": [],
        "past_conversations": "",
        "recent_notifications": [],
        "frequency": 3,
        "description": "Casual conversation, no goal connection",
    },
    {
        "id": "generic_02",
        "conversation": [
            "[Dan]: I'm going to read for an hour today",
            "[other]: What book?",
            "[Dan]: That new fiction book I bought. Really enjoying it",
        ],
        "user_name": "Dan",
        "user_facts": "Dan loves reading.",
        "goals": [{"title": "Read 2 books per month"}],
        "past_conversations": "",
        "recent_notifications": [],
        "frequency": 3,
        "description": "User doing something aligned with goal — no conflict",
    },
    {
        "id": "generic_03",
        "conversation": [
            "[Nora]: I had a really productive day today",
            "[other]: That's awesome! What did you accomplish?",
            "[Nora]: Finished the report, had a great meeting, and even went for a run",
        ],
        "user_name": "Nora",
        "user_facts": "Nora is a project manager.",
        "goals": [],
        "past_conversations": "",
        "recent_notifications": [],
        "frequency": 3,
        "description": "Positive update, no intervention needed",
    },
    {
        "id": "generic_04",
        "conversation": [
            "[Chloe]: I'm going to start meditating every morning",
            "[other]: That's a great idea",
            "[Chloe]: Yeah, I heard it helps with focus",
        ],
        "user_name": "Chloe",
        "user_facts": "Chloe struggles with focus at work.",
        "goals": [{"title": "Improve focus and productivity at work"}],
        "past_conversations": "",
        "recent_notifications": [],
        "frequency": 3,
        "description": "User taking positive action aligned with goals",
    },
    {
        "id": "wellness_01",
        "conversation": [
            "[Pat]: I'm so tired today",
            "[other]: Long day?",
            "[Pat]: Yeah, didn't sleep well",
        ],
        "user_name": "Pat",
        "user_facts": "Pat works in marketing.",
        "goals": [],
        "past_conversations": "",
        "recent_notifications": [],
        "frequency": 3,
        "description": "Would produce generic wellness advice (anti-pattern)",
    },
]

# Cases testing self-regulation with populated notification history
SELF_REGULATION_CASES = [
    {
        "id": "selfregulate_01",
        "conversation": [
            "[Eli]: I'm going to eat out every day this week",
            "[other]: That's expensive",
            "[Eli]: I know but I hate cooking",
        ],
        "user_name": "Eli",
        "user_facts": "Eli spends a lot on food delivery.",
        "goals": [{"title": "Cook at home at least 5 days a week to save money"}],
        "past_conversations": "",
        "recent_notifications": [
            {
                "text": "Hey Eli, you mentioned cooking more to save money — today would be a great day to try that new recipe!",
                "created_at": "10 minutes ago",
            },
            {
                "text": "Eli, your food spending is trending up again. Remember your goal to cook 5x/week?",
                "created_at": "2 hours ago",
            },
            {
                "text": "Quick reminder: your goal to cook more is slipping. Maybe prep something tonight?",
                "created_at": "5 hours ago",
            },
        ],
        "frequency": 3,
        "description": "Already sent 3 similar notifications — should self-regulate and NOT send another",
    },
]


def run_eval_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """Run a single test case against the unified prompt with structured output."""
    goals_text = (
        "\n".join(f"- {g['title']}" for g in case.get("goals", [])) if case.get("goals") else "No active goals set."
    )

    conversation_text = "\n".join(case["conversation"])

    recent_noti_text = "No recent notifications sent."
    if case.get("recent_notifications"):
        lines = [f"[{n['created_at']}]: {n['text']}" for n in case["recent_notifications"]]
        recent_noti_text = "\n".join(lines)

    prompt = PROACTIVE_PROMPT_TEMPLATE.format(
        user_name=case["user_name"],
        user_facts=case["user_facts"],
        goals_text=goals_text,
        past_conversations=case.get("past_conversations") or "No relevant past conversations found.",
        current_conversation=conversation_text,
        recent_notifications=recent_noti_text,
        frequency_guidance=FREQUENCY_GUIDANCE.get(case.get("frequency", 3)),
    )

    with_parser = llm_mini.with_structured_output(ProactiveNotificationResult)
    result: ProactiveNotificationResult = with_parser.invoke(prompt)

    return {
        "case_id": case["id"],
        "has_advice": result.has_advice,
        "confidence": result.advice.confidence if result.advice else 0,
        "notification_text": result.advice.notification_text if result.advice else "",
        "reasoning": result.advice.reasoning if result.advice else "",
        "category": result.advice.category if result.advice else "",
        "context_summary": result.context_summary,
    }


def judge_notification(case: Dict[str, Any], eval_result: Dict[str, Any], should_notify: bool) -> Dict[str, Any]:
    """Use gpt-5.1 to judge the quality of a notification decision."""
    if not should_notify:
        # For cases that should NOT notify
        if not eval_result["has_advice"]:
            return {"pass": True, "total": 25, "explanation": "Correctly did not send notification"}
        else:
            # It notified when it shouldn't have
            return {
                "pass": False,
                "total": 5,
                "explanation": f"Should NOT have notified. Sent: '{eval_result['notification_text'][:100]}'",
            }

    if not eval_result["has_advice"]:
        return {"pass": False, "total": 0, "explanation": "Should have notified but didn't"}

    judge_prompt = f"""You are evaluating the quality of a proactive push notification from an AI mentor.

CONVERSATION:
{chr(10).join(case["conversation"])}

USER CONTEXT:
- Name: {case["user_name"]}
- Facts: {case["user_facts"]}
- Goals: {json.dumps(case.get("goals", []))}
- Past conversations: {case.get("past_conversations", "None")}

NOTIFICATION SENT:
Text: "{eval_result['notification_text']}"
Confidence: {eval_result['confidence']}
Reasoning: "{eval_result['reasoning']}"
Category: {eval_result['category']}

Rate this notification on 5 criteria (1-5 each):
1. RELEVANCE: Does the notification directly address what's happening in the conversation?
2. NON-OBVIOUSNESS: Does it connect dots the user wouldn't connect themselves?
3. ACTIONABILITY: Does it suggest something concrete the user can do?
4. REASONING QUALITY: Does the reasoning cite specific facts/goals/past conversations?
5. APPROPRIATENESS: Is the confidence level well-calibrated?

Return ONLY a JSON object:
{{"relevance": N, "non_obviousness": N, "actionability": N, "reasoning_quality": N, "appropriateness": N, "total": N, "explanation": "brief explanation"}}

Total is the sum of all 5 scores (max 25). A score >= 18 is PASS."""

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
    all_should_notify = SHOULD_NOTIFY_CASES
    all_should_not = SHOULD_NOT_NOTIFY_CASES
    all_self_reg = SELF_REGULATION_CASES
    total_cases = len(all_should_notify) + len(all_should_not) + len(all_self_reg)

    print(f"\n{'='*70}")
    print(f"PROACTIVE MENTOR — UNIFIED PROMPT EVAL ({total_cases} test cases)")
    print(f"Model: gpt-4.1-mini | Judge: gpt-5.1")
    print(f"{'='*70}")

    results = []
    stats = {
        "should_notify": {"total": 0, "pass": 0},
        "should_not": {"total": 0, "pass": 0},
        "self_reg": {"total": 0, "pass": 0},
    }

    # Should notify cases
    print(f"\n  --- SHOULD NOTIFY (goal/pattern/dot-connecting) ---")
    for case in all_should_notify:
        stats["should_notify"]["total"] += 1
        print(f"  [{case['id']}] {case['description'][:50]}... ", end="", flush=True)

        eval_result = run_eval_case(case)
        judge_result = judge_notification(case, eval_result, should_notify=True)

        if judge_result.get("pass"):
            stats["should_notify"]["pass"] += 1

        status = "PASS" if judge_result.get("pass") else "FAIL"
        conf_str = f" conf={eval_result['confidence']:.2f}" if eval_result["has_advice"] else " no_advice"
        judge_str = f" judge={judge_result.get('total', 'N/A')}/25" if eval_result["has_advice"] else ""
        print(f"{status}{conf_str}{judge_str}")

        if not judge_result.get("pass"):
            print(f"         -> {judge_result.get('explanation', '')[:120]}")

        results.append({"case": case, "eval_result": eval_result, "judge_result": judge_result, "expected": "notify"})

    # Should NOT notify cases
    print(f"\n  --- SHOULD NOT NOTIFY (generic/obvious/anti-pattern) ---")
    for case in all_should_not:
        stats["should_not"]["total"] += 1
        print(f"  [{case['id']}] {case['description'][:50]}... ", end="", flush=True)

        eval_result = run_eval_case(case)
        judge_result = judge_notification(case, eval_result, should_notify=False)

        if judge_result.get("pass"):
            stats["should_not"]["pass"] += 1

        status = "PASS" if judge_result.get("pass") else "FAIL"
        advice_str = (
            " (correctly silent)"
            if not eval_result["has_advice"]
            else f" UNEXPECTED conf={eval_result['confidence']:.2f}"
        )
        print(f"{status}{advice_str}")

        if not judge_result.get("pass"):
            print(f"         -> {judge_result.get('explanation', '')[:120]}")

        results.append({"case": case, "eval_result": eval_result, "judge_result": judge_result, "expected": "silent"})

    # Self-regulation cases
    print(f"\n  --- SELF-REGULATION (notification history populated) ---")
    for case in all_self_reg:
        stats["self_reg"]["total"] += 1
        print(f"  [{case['id']}] {case['description'][:50]}... ", end="", flush=True)

        eval_result = run_eval_case(case)
        # Should NOT notify because of recent notification history
        judge_result = judge_notification(case, eval_result, should_notify=False)

        if judge_result.get("pass"):
            stats["self_reg"]["pass"] += 1

        status = "PASS" if judge_result.get("pass") else "FAIL"
        advice_str = (
            " (correctly self-regulated)"
            if not eval_result["has_advice"]
            else f" FAILED conf={eval_result['confidence']:.2f}"
        )
        print(f"{status}{advice_str}")

        if not judge_result.get("pass"):
            print(f"         -> {judge_result.get('explanation', '')[:120]}")

        results.append(
            {"case": case, "eval_result": eval_result, "judge_result": judge_result, "expected": "self_regulate"}
        )

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")

    total_pass = sum(1 for r in results if r["judge_result"].get("pass"))

    print(f"\n  Should Notify:    {stats['should_notify']['pass']}/{stats['should_notify']['total']}")
    print(f"  Should NOT Notify: {stats['should_not']['pass']}/{stats['should_not']['total']}")
    print(f"  Self-Regulation:   {stats['self_reg']['pass']}/{stats['self_reg']['total']}")
    print(f"\n  OVERALL: {total_pass}/{total_cases} passed ({total_pass/total_cases*100:.0f}%)")
    print(f"{'='*70}\n")

    # Write results to file
    output_path = os.path.join(os.path.dirname(__file__), "proactive_tools_eval_results.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Full results written to: {output_path}")

    return total_pass >= total_cases * 0.8  # Pass if >= 80%


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
