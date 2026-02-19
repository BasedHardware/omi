"""
Live LLM evaluation for proactive mentor tools.

Runs 30 test cases (10 per tool) against gpt-4.1-mini with tool calling,
then uses gpt-5.1 as judge to evaluate quality.

Usage:
    cd backend && python -m tests.eval.test_proactive_tools_eval

Requires OPENAI_API_KEY in environment.
"""

import json
import os
import sys
from typing import List, Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

# ---------------------------------------------------------------------------
# LLM clients
# ---------------------------------------------------------------------------
llm_mini = ChatOpenAI(model="gpt-4.1-mini")
llm_judge = ChatOpenAI(model="gpt-5.1")

# ---------------------------------------------------------------------------
# Tool definitions (same as production)
# ---------------------------------------------------------------------------
PROACTIVE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "trigger_argument_perspective",
            "description": (
                "User is in a disagreement with someone. Offer an honest outside perspective "
                "on who might be right and why, based on what you know about the user."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "notification_text": {
                        "type": "string",
                        "description": "Push notification message (<300 chars, direct, empathetic)",
                    },
                    "other_person": {
                        "type": "string",
                        "description": "Who the user is disagreeing with",
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "rationale": {
                        "type": "string",
                        "description": "Why this notification is warranted",
                    },
                },
                "required": ["notification_text", "confidence", "rationale"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_goal_misalignment",
            "description": (
                "User is discussing plans that contradict their stored goals. "
                "Alert them to the conflict so they can course-correct."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "notification_text": {
                        "type": "string",
                        "description": "Push notification message (<300 chars, direct, empathetic)",
                    },
                    "goal_name": {
                        "type": "string",
                        "description": "Which goal is conflicted",
                    },
                    "conflict_description": {
                        "type": "string",
                        "description": "How the plan conflicts with the goal",
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["notification_text", "goal_name", "conflict_description", "confidence"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_emotional_support",
            "description": (
                "User is expressing complaints or negative emotions. "
                "Suggest a concrete, actionable step they can take right now."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "notification_text": {
                        "type": "string",
                        "description": "Push notification message (<300 chars, direct, empathetic)",
                    },
                    "detected_emotion": {
                        "type": "string",
                        "description": "Primary emotion detected (e.g. frustration, loneliness, anxiety)",
                    },
                    "suggested_action": {
                        "type": "string",
                        "description": "Concrete actionable suggestion",
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["notification_text", "detected_emotion", "confidence"],
                "additionalProperties": False,
            },
        },
    },
]

# ---------------------------------------------------------------------------
# System prompt (same as production)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT_TEMPLATE = (
    "You are {user_name}'s proactive AI mentor and trusted friend. "
    "You may call multiple tools if multiple triggers clearly apply. "
    "Call a tool ONLY when the conversation clearly matches a trigger. "
    "If no trigger applies, respond with no tool calls.\n\n"
    "IMPORTANT RULES:\n"
    "- notification_text must be <300 chars, warm, and personal — like texting a close friend\n"
    "- Reference specific details from the conversation (names, situations, feelings)\n"
    "- For arguments: validate feelings first, then offer perspective. Don't be clinical.\n"
    "- For goal misalignment: ONLY trigger when user is ACTIVELY contradicting a goal. "
    "Do NOT trigger when they are doing something aligned with or neutral to their goals.\n"
    "- For emotional support: suggest ONE concrete action they can do RIGHT NOW\n"
    "- Always end with a gentle question or suggestion, never a lecture"
)

# ---------------------------------------------------------------------------
# Test cases: 10 per tool
# ---------------------------------------------------------------------------

# Each test case: {conversation, user_name, user_facts, goals, expected_tool, should_trigger}
ARGUMENT_TEST_CASES = [
    {
        "id": "arg_01",
        "conversation": [
            "[Alex]: My wife thinks I should quit my job and start a business",
            "[other]: What do you think?",
            "[Alex]: She's crazy, we have a mortgage to pay",
            "[other]: But she has a point about your unhappiness at work",
        ],
        "user_name": "Alex",
        "user_facts": "Alex is a software engineer, married, has a mortgage, has been complaining about work for months.",
        "goals": [],
        "expected_tool": "trigger_argument_perspective",
        "should_trigger": True,
    },
    {
        "id": "arg_02",
        "conversation": [
            "[Maria]: My partner wants to move to another city for his job",
            "[other]: And you don't want to?",
            "[Maria]: No way, my whole family is here. He's being selfish",
        ],
        "user_name": "Maria",
        "user_facts": "Maria is very close with her family, works remotely, has been dating partner for 3 years.",
        "goals": [],
        "expected_tool": "trigger_argument_perspective",
        "should_trigger": True,
    },
    {
        "id": "arg_03",
        "conversation": [
            "[Tom]: My coworker keeps taking credit for my work in meetings",
            "[other]: Have you talked to them about it?",
            "[Tom]: No, they'll just deny it. My manager saw it happen too and said nothing",
        ],
        "user_name": "Tom",
        "user_facts": "Tom is a junior developer, conflict-avoidant, values fairness.",
        "goals": [],
        "expected_tool": "trigger_argument_perspective",
        "should_trigger": True,
    },
    {
        "id": "arg_04",
        "conversation": [
            "[Sam]: My mom keeps telling me I should have kids already",
            "[other]: That's annoying",
            "[Sam]: She says I'm being irresponsible. I told her it's my choice",
        ],
        "user_name": "Sam",
        "user_facts": "Sam is 32, focused on career, doesn't want kids right now.",
        "goals": [],
        "expected_tool": "trigger_argument_perspective",
        "should_trigger": True,
    },
    {
        "id": "arg_05",
        "conversation": [
            "[Pat]: My friend said my startup idea is stupid",
            "[other]: Ouch. What did they say exactly?",
            "[Pat]: That nobody would pay for it. But they don't understand the market",
        ],
        "user_name": "Pat",
        "user_facts": "Pat has been working on a B2B SaaS idea for 6 months, has 3 paying beta users.",
        "goals": [],
        "expected_tool": "trigger_argument_perspective",
        "should_trigger": True,
    },
    {
        "id": "arg_06",
        "conversation": [
            "[Dana]: My roommate ate my leftovers again",
            "[other]: Did you talk to them?",
            "[Dana]: Yeah they said it's not a big deal. But it IS a big deal to me",
        ],
        "user_name": "Dana",
        "user_facts": "Dana is a college student on a tight budget.",
        "goals": [],
        "expected_tool": "trigger_argument_perspective",
        "should_trigger": True,
    },
    {
        "id": "arg_07",
        "conversation": [
            "[Chris]: My brother wants to borrow money again, I said no and now he's angry",
            "[other]: How much does he want?",
            "[Chris]: Five thousand. He never pays me back. He says family should help family",
        ],
        "user_name": "Chris",
        "user_facts": "Chris has lent brother money 3 times before, never repaid. Chris values family but is financially responsible.",
        "goals": [],
        "expected_tool": "trigger_argument_perspective",
        "should_trigger": True,
    },
    {
        "id": "arg_08",
        "conversation": [
            "[Jo]: Had a great lunch today",
            "[other]: Nice, where did you go?",
            "[Jo]: That new Thai place downtown, really good pad thai",
        ],
        "user_name": "Jo",
        "user_facts": "Jo likes trying new restaurants.",
        "goals": [],
        "expected_tool": None,
        "should_trigger": False,
    },
    {
        "id": "arg_09",
        "conversation": [
            "[Riley]: I disagree with the new company policy on remote work",
            "[other]: What changed?",
            "[Riley]: They want everyone back 5 days. My manager agrees with me that it's counterproductive",
        ],
        "user_name": "Riley",
        "user_facts": "Riley is a senior engineer, top performer, works best from home.",
        "goals": [],
        "expected_tool": "trigger_argument_perspective",
        "should_trigger": True,
    },
    {
        "id": "arg_10",
        "conversation": [
            "[Lee]: My wife and I can't agree on where to send our kid to school",
            "[other]: Public vs private?",
            "[Lee]: She wants private, I think public is fine. We had a big fight about it last night",
        ],
        "user_name": "Lee",
        "user_facts": "Lee went to public school, values practical education, budget-conscious. Wife went to private school.",
        "goals": [],
        "expected_tool": "trigger_argument_perspective",
        "should_trigger": True,
    },
]

GOAL_MISALIGNMENT_TEST_CASES = [
    {
        "id": "goal_01",
        "conversation": [
            "[Emma]: I'm thinking of ordering pizza tonight",
            "[other]: Sounds good",
            "[Emma]: Yeah, and maybe some wings too. I deserve a treat",
        ],
        "user_name": "Emma",
        "user_facts": "Emma has been dieting for 2 months, lost 10 pounds.",
        "goals": [{"title": "Lose 20 pounds by June"}],
        "expected_tool": "trigger_goal_misalignment",
        "should_trigger": True,
    },
    {
        "id": "goal_02",
        "conversation": [
            "[Mike]: I signed up for another online course",
            "[other]: Which one?",
            "[Mike]: Machine learning. That's my fifth course this month",
        ],
        "user_name": "Mike",
        "user_facts": "Mike starts many courses but rarely finishes them.",
        "goals": [{"title": "Complete AWS certification by March"}],
        "expected_tool": "trigger_goal_misalignment",
        "should_trigger": True,
    },
    {
        "id": "goal_03",
        "conversation": [
            "[Sara]: I'm going to skip my morning run tomorrow",
            "[other]: Why?",
            "[Sara]: I want to sleep in. I'll run next week instead",
        ],
        "user_name": "Sara",
        "user_facts": "Sara is training for a half marathon in 6 weeks.",
        "goals": [{"title": "Run half marathon in under 2 hours"}],
        "expected_tool": "trigger_goal_misalignment",
        "should_trigger": True,
    },
    {
        "id": "goal_04",
        "conversation": [
            "[Jake]: I'm going to buy that new gaming console",
            "[other]: Nice, which one?",
            "[Jake]: The latest one, it's only 600 bucks",
        ],
        "user_name": "Jake",
        "user_facts": "Jake has been saving for a down payment on a house.",
        "goals": [{"title": "Save $50,000 for house down payment by December"}],
        "expected_tool": "trigger_goal_misalignment",
        "should_trigger": True,
    },
    {
        "id": "goal_05",
        "conversation": [
            "[Nina]: I'm going to stay up late binge-watching that new show",
            "[other]: Which one?",
            "[Nina]: The one everyone's talking about. Probably until 3am",
        ],
        "user_name": "Nina",
        "user_facts": "Nina has been struggling with sleep quality.",
        "goals": [{"title": "Fix sleep schedule - be in bed by 11pm every night"}],
        "expected_tool": "trigger_goal_misalignment",
        "should_trigger": True,
    },
    {
        "id": "goal_06",
        "conversation": [
            "[Dan]: I'm going to read for an hour today",
            "[other]: What book?",
            "[Dan]: That new fiction book I bought. Really enjoying it",
        ],
        "user_name": "Dan",
        "user_facts": "Dan loves reading.",
        "goals": [{"title": "Read 2 books per month"}],
        "expected_tool": None,
        "should_trigger": False,
    },
    {
        "id": "goal_07",
        "conversation": [
            "[Ava]: I think I'll skip Spanish class again this week",
            "[other]: How many have you missed?",
            "[Ava]: Like three in a row. The teacher is boring anyway",
        ],
        "user_name": "Ava",
        "user_facts": "Ava enrolled in Spanish classes 2 months ago.",
        "goals": [{"title": "Become conversational in Spanish by summer"}],
        "expected_tool": "trigger_goal_misalignment",
        "should_trigger": True,
    },
    {
        "id": "goal_08",
        "conversation": [
            "[Ben]: I'm going to accept that job offer at the big company",
            "[other]: What about your startup?",
            "[Ben]: I'll put it on pause. The salary is too good to pass up",
        ],
        "user_name": "Ben",
        "user_facts": "Ben has been building a startup for 8 months with 500 users.",
        "goals": [{"title": "Grow startup to 5,000 users by Q3"}],
        "expected_tool": "trigger_goal_misalignment",
        "should_trigger": True,
    },
    {
        "id": "goal_09",
        "conversation": [
            "[Chloe]: I'm going to start meditating every morning",
            "[other]: That's a great idea",
            "[Chloe]: Yeah, I heard it helps with focus",
        ],
        "user_name": "Chloe",
        "user_facts": "Chloe struggles with focus at work.",
        "goals": [{"title": "Improve focus and productivity at work"}],
        "expected_tool": None,
        "should_trigger": False,
    },
    {
        "id": "goal_10",
        "conversation": [
            "[Eli]: I'm going to eat out every day this week",
            "[other]: That's expensive",
            "[Eli]: I know but I hate cooking. It's just easier",
        ],
        "user_name": "Eli",
        "user_facts": "Eli spends a lot on food delivery.",
        "goals": [{"title": "Cook at home at least 5 days a week to save money"}],
        "expected_tool": "trigger_goal_misalignment",
        "should_trigger": True,
    },
]

EMOTIONAL_SUPPORT_TEST_CASES = [
    {
        "id": "emo_01",
        "conversation": [
            "[Zoe]: I feel so lonely lately",
            "[other]: Have you tried reaching out to friends?",
            "[Zoe]: Nobody has time for me. I just sit at home every night",
        ],
        "user_name": "Zoe",
        "user_facts": "Zoe recently moved to a new city, works remotely.",
        "goals": [],
        "expected_tool": "trigger_emotional_support",
        "should_trigger": True,
    },
    {
        "id": "emo_02",
        "conversation": [
            "[Max]: I'm so anxious about my presentation tomorrow",
            "[other]: You'll do fine",
            "[Max]: No I won't. I always freeze up. I couldn't sleep last night thinking about it",
        ],
        "user_name": "Max",
        "user_facts": "Max has public speaking anxiety, is a data scientist.",
        "goals": [],
        "expected_tool": "trigger_emotional_support",
        "should_trigger": True,
    },
    {
        "id": "emo_03",
        "conversation": [
            "[Ivy]: Everything feels pointless right now",
            "[other]: What do you mean?",
            "[Ivy]: I work all day, come home exhausted, repeat. What's the point",
        ],
        "user_name": "Ivy",
        "user_facts": "Ivy is a nurse working 12-hour shifts.",
        "goals": [],
        "expected_tool": "trigger_emotional_support",
        "should_trigger": True,
    },
    {
        "id": "emo_04",
        "conversation": [
            "[Ray]: I got rejected from another job today",
            "[other]: Sorry to hear that",
            "[Ray]: That's the 15th rejection this month. I'm starting to think I'm just not good enough",
        ],
        "user_name": "Ray",
        "user_facts": "Ray was laid off 3 months ago, has 8 years of experience in marketing.",
        "goals": [],
        "expected_tool": "trigger_emotional_support",
        "should_trigger": True,
    },
    {
        "id": "emo_05",
        "conversation": [
            "[Lily]: I can't stop comparing myself to my friends",
            "[other]: In what way?",
            "[Lily]: They all seem to have their life together. Houses, marriages, babies. I have nothing",
        ],
        "user_name": "Lily",
        "user_facts": "Lily is 29, single, renting, loves travel and adventure.",
        "goals": [],
        "expected_tool": "trigger_emotional_support",
        "should_trigger": True,
    },
    {
        "id": "emo_06",
        "conversation": [
            "[Finn]: I'm so frustrated with my code today",
            "[other]: What's wrong?",
            "[Finn]: This bug has been driving me crazy for 3 days. I want to throw my laptop out the window",
        ],
        "user_name": "Finn",
        "user_facts": "Finn is a frontend developer, perfectionist.",
        "goals": [],
        "expected_tool": "trigger_emotional_support",
        "should_trigger": True,
    },
    {
        "id": "emo_07",
        "conversation": [
            "[Nora]: I had a really productive day today",
            "[other]: That's awesome! What did you accomplish?",
            "[Nora]: Finished the report, had a great meeting, and even went for a run",
        ],
        "user_name": "Nora",
        "user_facts": "Nora is a project manager.",
        "goals": [],
        "expected_tool": None,
        "should_trigger": False,
    },
    {
        "id": "emo_08",
        "conversation": [
            "[Oscar]: I'm exhausted. I can't keep doing this",
            "[other]: Doing what?",
            "[Oscar]: Working two jobs, taking care of my mom, never sleeping. Something has to give",
        ],
        "user_name": "Oscar",
        "user_facts": "Oscar is caretaking for his elderly mother while working two jobs.",
        "goals": [],
        "expected_tool": "trigger_emotional_support",
        "should_trigger": True,
    },
    {
        "id": "emo_09",
        "conversation": [
            "[Uma]: I feel like such a failure as a parent",
            "[other]: Why do you say that?",
            "[Uma]: My kid got in trouble at school again. I must be doing something wrong",
        ],
        "user_name": "Uma",
        "user_facts": "Uma is a single parent of a 10-year-old.",
        "goals": [],
        "expected_tool": "trigger_emotional_support",
        "should_trigger": True,
    },
    {
        "id": "emo_10",
        "conversation": [
            "[Vera]: I'm dreading going to work tomorrow",
            "[other]: What happened?",
            "[Vera]: My boss publicly criticized me in a meeting. I felt humiliated",
        ],
        "user_name": "Vera",
        "user_facts": "Vera is sensitive to criticism, works in sales.",
        "goals": [],
        "expected_tool": "trigger_emotional_support",
        "should_trigger": True,
    },
]


def run_tool_call(case: Dict[str, Any]) -> Dict[str, Any]:
    """Run a single test case against gpt-4.1-mini with tool calling."""
    conversation_text = "\n".join(case["conversation"])
    goals_text = "\n".join(f"- {g['title']}" for g in case.get("goals", [])) if case.get("goals") else "No goals set."

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(user_name=case["user_name"])
    user_message = (
        f"Conversation:\n{conversation_text}\n\n"
        f"What we know about {case['user_name']}:\n{case['user_facts']}\n\n"
        f"{case['user_name']}'s active goals:\n{goals_text}"
    )

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    llm_with_tools = llm_mini.bind_tools(PROACTIVE_TOOLS, tool_choice="auto")
    resp = llm_with_tools.invoke(messages)

    tool_calls = []
    for tc in resp.tool_calls:
        tool_calls.append(
            {
                "name": tc["name"],
                "args": tc["args"],
            }
        )

    return {
        "case_id": case["id"],
        "expected_tool": case["expected_tool"],
        "should_trigger": case["should_trigger"],
        "tool_calls": tool_calls,
        "triggered": len(tool_calls) > 0,
        "correct_tool": (
            any(tc["name"] == case["expected_tool"] for tc in tool_calls) if case["expected_tool"] else True
        ),
    }


def judge_notification(case: Dict[str, Any], tool_result: Dict[str, Any]) -> Dict[str, Any]:
    """Use gpt-5.1 to judge the quality of a notification."""
    if not tool_result["tool_calls"]:
        return {"score": 0, "explanation": "No tool call made", "pass": not case["should_trigger"]}

    # Find the relevant tool call
    relevant_tc = None
    for tc in tool_result["tool_calls"]:
        if tc["name"] == case.get("expected_tool"):
            relevant_tc = tc
            break
    if not relevant_tc:
        relevant_tc = tool_result["tool_calls"][0]

    notification_text = relevant_tc["args"].get("notification_text", "")
    confidence = relevant_tc["args"].get("confidence", 0)

    judge_prompt = f"""You are evaluating the quality of a proactive push notification from an AI mentor.

CONVERSATION:
{chr(10).join(case["conversation"])}

USER CONTEXT:
- Name: {case["user_name"]}
- Facts: {case["user_facts"]}
- Goals: {json.dumps(case.get("goals", []))}

NOTIFICATION SENT:
Tool: {relevant_tc["name"]}
Text: "{notification_text}"
Confidence: {confidence}

Rate this notification on 5 criteria (1-5 each):
1. RELEVANCE: Does the notification directly address what's happening in the conversation?
2. EMPATHY: Is the tone warm, direct, and non-judgmental?
3. ACTIONABILITY: Does it suggest something concrete the user can do?
4. BREVITY: Is it concise (<300 chars) and easy to read as a push notification?
5. APPROPRIATENESS: Should a notification have been sent at all? Is the tool choice correct?

Return ONLY a JSON object:
{{"relevance": N, "empathy": N, "actionability": N, "brevity": N, "appropriateness": N, "total": N, "explanation": "brief explanation"}}

Total is the sum of all 5 scores (max 25). A score >= 18 is PASS."""

    resp = llm_judge.invoke(judge_prompt)
    try:
        # Parse the JSON response
        content = resp.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        scores = json.loads(content)
        scores["pass"] = scores.get("total", 0) >= 18
        return scores
    except Exception as e:
        return {"error": str(e), "raw": resp.content, "pass": False}


def main():
    all_cases = ARGUMENT_TEST_CASES + GOAL_MISALIGNMENT_TEST_CASES + EMOTIONAL_SUPPORT_TEST_CASES

    print(f"\n{'='*70}")
    print(f"PROACTIVE MENTOR TOOLS — LIVE EVAL ({len(all_cases)} test cases)")
    print(f"Model: gpt-4.1-mini | Judge: gpt-5.1")
    print(f"{'='*70}\n")

    results = []
    category_stats = {
        "arg": {"total": 0, "correct_trigger": 0, "judge_pass": 0},
        "goal": {"total": 0, "correct_trigger": 0, "judge_pass": 0},
        "emo": {"total": 0, "correct_trigger": 0, "judge_pass": 0},
    }

    for case in all_cases:
        category = case["id"].split("_")[0]
        category_stats[category]["total"] += 1

        print(f"  [{case['id']}] ", end="", flush=True)

        # Run tool call
        tool_result = run_tool_call(case)

        # Check trigger correctness
        trigger_correct = tool_result["triggered"] == case["should_trigger"]
        tool_correct = tool_result["correct_tool"] if case["should_trigger"] else not tool_result["triggered"]

        if trigger_correct and tool_correct:
            category_stats[category]["correct_trigger"] += 1

        # Judge quality (only for cases that should trigger and did)
        judge_result = {"pass": True, "total": "N/A"}
        if case["should_trigger"] and tool_result["triggered"]:
            judge_result = judge_notification(case, tool_result)
            if judge_result.get("pass"):
                category_stats[category]["judge_pass"] += 1
        elif not case["should_trigger"] and not tool_result["triggered"]:
            category_stats[category]["judge_pass"] += 1  # Correctly not triggered

        # Status
        trigger_status = "OK" if trigger_correct else "WRONG"
        tool_status = ""
        if tool_result["triggered"]:
            tools_str = ", ".join(tc["name"] for tc in tool_result["tool_calls"])
            confidence_str = ", ".join(f"{tc['args'].get('confidence', '?')}" for tc in tool_result["tool_calls"])
            tool_status = f" tools=[{tools_str}] conf=[{confidence_str}]"
        judge_status = (
            f" judge={judge_result.get('total', 'N/A')}/25"
            if case["should_trigger"] and tool_result["triggered"]
            else ""
        )
        pass_str = "PASS" if judge_result.get("pass") else "FAIL"

        print(f"{pass_str} trigger={trigger_status}{tool_status}{judge_status}")

        if not judge_result.get("pass") and judge_result.get("explanation"):
            print(f"         -> {judge_result.get('explanation', '')[:120]}")

        results.append(
            {
                "case": case,
                "tool_result": tool_result,
                "judge_result": judge_result,
                "trigger_correct": trigger_correct,
            }
        )

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")

    total_pass = sum(1 for r in results if r["judge_result"].get("pass"))
    total = len(results)

    for cat, label in [("arg", "Argument Perspective"), ("goal", "Goal Misalignment"), ("emo", "Emotional Support")]:
        stats = category_stats[cat]
        print(f"\n  {label}:")
        print(f"    Trigger accuracy: {stats['correct_trigger']}/{stats['total']}")
        print(f"    Judge pass:       {stats['judge_pass']}/{stats['total']}")

    print(f"\n  OVERALL: {total_pass}/{total} passed ({total_pass/total*100:.0f}%)")
    print(f"{'='*70}\n")

    # Write results to file
    output_path = os.path.join(os.path.dirname(__file__), "proactive_tools_eval_results.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Full results written to: {output_path}")

    return total_pass >= total * 0.8  # Pass if >= 80%


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
