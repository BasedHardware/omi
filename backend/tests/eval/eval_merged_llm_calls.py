"""
Evaluation: Separate vs Combined LLM calls for conversation processing.

Compares quality of:
  OLD: get_transcript_structure() + extract_action_items()  (2 LLM calls)
  NEW: get_transcript_structure_with_action_items()          (1 LLM call)

Uses GPT-5.1 as judge on 10+ synthetic conversations with 10-100 transcript segments.
"""

import json
import os
import sys
import types
import time
import random
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

# Setup paths and env
backend_dir = os.path.join(os.path.dirname(__file__), '..', '..')
backend_dir = os.path.abspath(backend_dir)
sys.path.insert(0, backend_dir)

from dotenv import load_dotenv

env_file = os.path.join('/home/claude/.config/omi/dev/backend', '.env')
load_dotenv(env_file)


# Stub database modules that require GCP credentials
def _stub_module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


database_mod = _stub_module("database")
database_mod.__path__ = []
for submodule in [
    "redis_db",
    "memories",
    "conversations",
    "notifications",
    "users",
    "tasks",
    "trends",
    "action_items",
    "folders",
    "calendar_meetings",
    "vector_db",
    "apps",
    "llm_usage",
    "_client",
    "auth",
]:
    mod = _stub_module(f"database.{submodule}")
    setattr(database_mod, submodule, mod)

# Add required attributes to stubs
llm_usage_mod = sys.modules["database.llm_usage"]
llm_usage_mod.record_llm_usage = MagicMock()

client_mod = sys.modules["database._client"]
client_mod.document_id_from_seed = MagicMock(return_value="doc-id")

redis_mod = sys.modules["database.redis_db"]
redis_mod.r = MagicMock()

from openai import OpenAI
from utils.llm.conversation_processing import (
    get_transcript_structure,
    extract_action_items,
    get_transcript_structure_with_action_items,
)

openai_client = OpenAI()

# ─── Synthetic Conversation Generator ───────────────────────────────────────

SCENARIOS = [
    {
        "theme": "team_standup",
        "description": "Daily standup meeting with status updates and blockers",
        "speakers": ["Alice", "Bob", "Carol"],
        "segments_template": [
            "{s0}: Good morning everyone, let's do our standup.",
            "{s1}: Hey! So yesterday I finished the database migration.",
            "{s1}: Today I'm going to start on the API endpoint for user profiles.",
            "{s1}: No blockers on my end.",
            "{s2}: I'm still working on the frontend dashboard redesign.",
            "{s2}: I need the API spec from Bob before I can integrate the new charts.",
            "{s0}: Bob, can you get that spec to Carol by end of day?",
            "{s1}: Yeah, I'll have it ready by 3 PM.",
            "{s0}: Great. I had a meeting with the product team yesterday.",
            "{s0}: They want us to prioritize the notification system. We need to ship it by Friday.",
            "{s2}: That's tight. Do we have designs for it?",
            "{s0}: The design team said they'll send mockups by tomorrow morning.",
            "{s0}: I'll set up a review meeting for Wednesday at 2 PM.",
            "{s1}: Sounds good. Should I also look into the email service integration?",
            "{s0}: Yes, please research options and share a comparison by Thursday.",
            "{s2}: One more thing - don't forget we have the sprint review on Friday at 4 PM.",
        ],
    },
    {
        "theme": "doctor_appointment",
        "description": "Patient discussing symptoms and treatment plan with doctor",
        "speakers": ["Patient", "Dr. Smith"],
        "segments_template": [
            "{s0}: Hi Doctor, I've been having headaches for about two weeks now.",
            "{s1}: I see. Can you describe the headaches? Where exactly do you feel the pain?",
            "{s0}: It's mostly on the right side, kind of behind my eye.",
            "{s0}: It gets worse in the afternoon, especially when I'm at the computer.",
            "{s1}: How many hours a day are you at the computer?",
            "{s0}: About 8 to 10 hours. I work in software development.",
            "{s1}: That could be contributing. Have you noticed any vision changes?",
            "{s0}: Actually yes, things get a bit blurry sometimes.",
            "{s1}: I'd like to refer you to an ophthalmologist. Let me write that referral.",
            "{s1}: In the meantime, I'm going to prescribe some anti-inflammatory medication.",
            "{s0}: Should I take it daily?",
            "{s1}: Take one tablet twice a day with food. Don't take it on an empty stomach.",
            "{s1}: Also, try the 20-20-20 rule. Every 20 minutes, look at something 20 feet away for 20 seconds.",
            "{s0}: Got it. Should I schedule a follow-up?",
            "{s1}: Yes, come back in two weeks. If the headaches get worse before then, call us immediately.",
            "{s1}: And please schedule that eye appointment as soon as possible.",
        ],
    },
    {
        "theme": "startup_planning",
        "description": "Co-founders planning product launch and fundraising",
        "speakers": ["Maya", "Jordan"],
        "segments_template": [
            "{s0}: So we need to finalize our launch timeline. The MVP is almost ready.",
            "{s1}: Right. I think we can launch the beta by March 15th.",
            "{s0}: That works. But we need to get the payment integration done first.",
            "{s1}: I've been looking at Stripe and they have a good API. Should take about a week.",
            "{s0}: Good. While you handle that, I'll focus on the marketing site.",
            "{s0}: We also need to think about our pitch deck. The investor meeting is on April 1st.",
            "{s1}: Oh right, the meeting with Sequoia. We should start on the deck this weekend.",
            "{s0}: I'll draft the market size and competitive analysis slides.",
            "{s1}: I'll prepare the technical architecture and growth projections.",
            "{s0}: Don't forget we need to update our financial model. Revenue projections need to be realistic.",
            "{s1}: True. I think we should project $500K ARR by end of year one.",
            "{s0}: That's ambitious but doable if we hit 1000 paying users.",
            "{s1}: Speaking of users, we should reach out to our beta waitlist. We have 2000 signups.",
            "{s0}: Let's send the invite emails next Monday. I'll set up the onboarding flow this week.",
            "{s1}: Also, remind me to register the company trademark before launch.",
            "{s0}: Good call. I'll add that to our checklist. And we need to review the terms of service with our lawyer by March 10th.",
        ],
    },
    {
        "theme": "family_dinner_planning",
        "description": "Family planning a birthday dinner party",
        "speakers": ["Mom", "Dad", "Teenager"],
        "segments_template": [
            "{s0}: OK so grandma's birthday is next Saturday. We need to plan the dinner.",
            "{s1}: How many people are we expecting?",
            "{s0}: About 15. Uncle Robert's family, Aunt Sarah, the cousins.",
            "{s2}: Can I invite Jake and Emma? Grandma loves them.",
            "{s0}: Sure, that makes it 17 then.",
            "{s1}: Should we cook at home or book a restaurant?",
            "{s0}: I think she'd prefer home-cooked. She always says restaurant food is too salty.",
            "{s2}: I can help with dessert. I want to make her favorite carrot cake.",
            "{s0}: That's sweet of you. Make sure to get the cream cheese frosting recipe from Aunt Sarah.",
            "{s1}: I'll handle the main course. Thinking roast chicken with the herb stuffing she likes.",
            "{s0}: Perfect. I'll do the appetizers and salad.",
            "{s1}: We need to go grocery shopping on Thursday. Friday will be too hectic.",
            "{s2}: Don't forget grandma is allergic to shellfish. No shrimp in the appetizers.",
            "{s0}: Of course. Also, we need to pick up her gift. The cashmere scarf from Nordstrom.",
            "{s1}: I'll pick it up tomorrow after work. The store closes at 9.",
            "{s0}: Oh, and we need to call Uncle Robert to confirm he's bringing the wine.",
        ],
    },
    {
        "theme": "code_review",
        "description": "Senior developer reviewing junior developer's pull request",
        "speakers": ["Senior Dev", "Junior Dev"],
        "segments_template": [
            "{s0}: Let's go through your PR for the authentication module.",
            "{s1}: Sure. I implemented JWT token refresh and added rate limiting.",
            "{s0}: Good. I see you're storing the refresh token in localStorage. That's a security risk.",
            "{s1}: Oh, what should I use instead?",
            "{s0}: Use an httpOnly secure cookie. It's not accessible via JavaScript, so it's safer against XSS.",
            "{s1}: Got it. I'll change that.",
            "{s0}: Also, your rate limiter uses an in-memory store. That won't work in production with multiple instances.",
            "{s1}: Right, because each instance would have its own counter.",
            "{s0}: Exactly. Use Redis for the rate limit counters. We already have it set up.",
            "{s1}: I'll switch to Redis. Should I use the sliding window pattern?",
            "{s0}: Yes, sliding window is better than fixed window. Less bursty at boundaries.",
            "{s0}: One more thing - your error handling. When the token refresh fails, you're returning a 500.",
            "{s1}: What should it be?",
            "{s0}: Return a 401 with a clear message. The client needs to know to re-authenticate.",
            "{s1}: Makes sense. I'll fix all three issues and push an update today.",
            "{s0}: Great. Also, add unit tests for the token refresh flow. We need at least 80% coverage on this module.",
        ],
    },
    {
        "theme": "travel_planning",
        "description": "Couple planning a vacation trip",
        "speakers": ["Alex", "Sam"],
        "segments_template": [
            "{s0}: So for our Japan trip in April, I've been looking at flights.",
            "{s1}: Nice! What did you find?",
            "{s0}: ANA has a direct flight from SF to Tokyo for $1200 round trip.",
            "{s1}: That's not bad. When would we leave?",
            "{s0}: I was thinking April 5th to April 19th. Two weeks.",
            "{s1}: Perfect. Cherry blossom season.",
            "{s0}: Exactly. We should book the flights by this weekend before prices go up.",
            "{s1}: Agreed. For hotels, should we do Airbnb or traditional ryokan?",
            "{s0}: Mix of both? Ryokan in Kyoto, hotel in Tokyo.",
            "{s1}: I love that idea. I'll research ryokans in the Higashiyama district.",
            "{s0}: We also need to get our Japan Rail Pass. It saves a lot on bullet trains.",
            "{s1}: Right. Remind me to order it at least two weeks before departure.",
            "{s0}: I'll set a reminder. Also, we need to exchange some yen before we go.",
            "{s1}: The bank has better rates than the airport. Let's go next Friday.",
            "{s0}: Don't forget to check if our credit cards charge foreign transaction fees.",
            "{s1}: Good point. And we should download offline maps and a translation app.",
        ],
    },
    {
        "theme": "real_estate",
        "description": "Realtor discussing property options with a buyer",
        "speakers": ["Buyer", "Realtor"],
        "segments_template": [
            "{s0}: We've been looking for about two months now. I think we're ready to make an offer.",
            "{s1}: Great! Which property are you most interested in?",
            "{s0}: The three-bedroom on Oak Street. The one listed at $650,000.",
            "{s1}: That's a solid choice. It's been on the market for 45 days, so there might be room to negotiate.",
            "{s0}: What do you think we should offer?",
            "{s1}: Based on comparable sales in the area, I'd suggest starting at $620,000.",
            "{s0}: That sounds reasonable. We got pre-approved for up to $700,000.",
            "{s1}: Good. I'd also recommend including an inspection contingency.",
            "{s0}: Definitely. The roof looked like it might need work.",
            "{s1}: I noticed that too. A roof inspection is essential. Could be $15,000 to $25,000 to replace.",
            "{s0}: Can we factor that into the offer price?",
            "{s1}: Absolutely. We can note it in the offer letter. Let me draft it up today.",
            "{s0}: How quickly do we need to hear back?",
            "{s1}: I'll set a 48-hour response window. That's standard.",
            "{s0}: One more thing - when would we need to have the earnest money ready?",
            "{s1}: Within 3 business days of acceptance. Usually 1% to 2% of the offer price, so around $6,200.",
        ],
    },
    {
        "theme": "project_retrospective",
        "description": "Team retrospective after a product launch",
        "speakers": ["PM", "Designer", "Engineer", "QA"],
        "segments_template": [
            "{s0}: Alright team, let's do our retro on the v2.0 launch. What went well?",
            "{s1}: The new onboarding flow got great feedback. User completion rate went from 40% to 78%.",
            "{s2}: The infrastructure handled the traffic spike really well. We hit 50K concurrent users.",
            "{s3}: Testing caught two critical bugs before launch. The payment double-charge issue would have been bad.",
            "{s0}: Excellent. Now what didn't go well?",
            "{s2}: We had that 30-minute outage at 2 AM on launch night. The database connection pool was exhausted.",
            "{s1}: The mobile responsive design broke on some Android devices. We missed that in QA.",
            "{s3}: We didn't have enough time for load testing. I flagged this two weeks before launch.",
            "{s0}: That's fair. We need to build in more QA time. What should we do differently next time?",
            "{s2}: We need better database monitoring. I'll set up connection pool alerts by next sprint.",
            "{s1}: We should add more Android devices to our testing matrix.",
            "{s3}: I'd like to start load testing at least one month before any major launch.",
            "{s0}: Great action items. Let me capture these.",
            "{s0}: I'll also schedule a post-mortem for the database outage. Can everyone do Thursday at 3 PM?",
            "{s2}: Works for me.",
            "{s1}: Same here. Also, can we prioritize fixing those Android responsive issues this sprint?",
        ],
    },
    {
        "theme": "financial_review",
        "description": "Business owner reviewing quarterly finances with accountant",
        "speakers": ["Owner", "Accountant"],
        "segments_template": [
            "{s0}: So how did we do this quarter?",
            "{s1}: Revenue is up 15% compared to last quarter. We hit $320,000.",
            "{s0}: That's great! What about expenses?",
            "{s1}: Total expenses were $245,000. Operating margin is about 23%.",
            "{s0}: Where are we spending the most?",
            "{s1}: Payroll is the biggest at $150,000. Then rent at $25,000. Marketing was $35,000.",
            "{s0}: Marketing seems high. Are we getting good ROI?",
            "{s1}: Customer acquisition cost went down from $85 to $62. So yes, the spend is efficient.",
            "{s0}: Good. What about taxes?",
            "{s1}: We need to make our estimated quarterly payment by March 15th. It'll be around $18,000.",
            "{s0}: Okay. Anything else I should know?",
            "{s1}: Your accounts receivable is growing. You have $45,000 in unpaid invoices over 60 days.",
            "{s0}: That's too much. Who owes us?",
            "{s1}: Three clients. I'll send you the list. You should follow up personally this week.",
            "{s0}: I'll call them tomorrow. What about our cash reserves?",
            "{s1}: You have about four months of runway. I'd recommend building that to six months.",
        ],
    },
    {
        "theme": "fitness_coaching",
        "description": "Personal trainer creating a workout and nutrition plan",
        "speakers": ["Client", "Trainer"],
        "segments_template": [
            "{s0}: I want to get in shape for my wedding in June. That's about three months away.",
            "{s1}: Congratulations! What are your specific goals?",
            "{s0}: I want to lose about 15 pounds and tone up. Especially arms and core.",
            "{s1}: That's very achievable in three months. Let's create a plan.",
            "{s0}: I can commit to working out four days a week.",
            "{s1}: Perfect. I'd recommend two strength days and two cardio-HIIT days.",
            "{s0}: I've never done HIIT before. Is it hard?",
            "{s1}: We'll start easy and ramp up. First two weeks will be introductory.",
            "{s0}: What about nutrition? I eat out a lot.",
            "{s1}: We need to address that. I want you to track your meals for the first week using MyFitnessPal.",
            "{s0}: I can do that.",
            "{s1}: Target 1,600 calories daily. Aim for 120 grams of protein per day.",
            "{s0}: That's a lot of protein. I'm not sure how to hit that.",
            "{s1}: I'll send you a meal prep guide tomorrow. Focus on chicken, fish, eggs, and Greek yogurt.",
            "{s0}: Should I cut out carbs?",
            "{s1}: No, you need carbs for energy. Just switch to complex carbs. Brown rice, sweet potatoes, oats.",
            "{s0}: When do we start?",
            "{s1}: Monday. Come to the gym at 7 AM. And buy a food scale this weekend. Portion control is key.",
        ],
    },
    {
        "theme": "school_conference",
        "description": "Parent-teacher conference about student performance",
        "speakers": ["Teacher", "Parent"],
        "segments_template": [
            "{s0}: Thanks for coming in. I wanted to discuss Emma's progress this semester.",
            "{s1}: Of course. How is she doing?",
            "{s0}: Academically, she's doing very well. She's got an A in English and B+ in Science.",
            "{s1}: That's wonderful. She loves reading at home.",
            "{s0}: It shows. Her book reports are some of the best in the class.",
            "{s0}: However, I am a bit concerned about her math performance.",
            "{s1}: Oh no, what's happening?",
            "{s0}: She's struggling with fractions and word problems. Her math grade is a C+.",
            "{s1}: She did mention math was getting harder.",
            "{s0}: I'd recommend she does 30 minutes of extra math practice daily. Khan Academy is great for this.",
            "{s1}: I'll make sure she does that every evening.",
            "{s0}: Also, we have a tutoring program on Wednesdays after school. Free for students.",
            "{s1}: That would be perfect. How do I sign her up?",
            "{s0}: I'll email you the registration form. Just fill it out and return it by Friday.",
            "{s1}: I will. Anything else?",
            "{s0}: She's been a bit shy about asking questions in class. Encourage her to speak up.",
            "{s1}: Thank you. We'll work on that at home too.",
        ],
    },
    {
        "theme": "crisis_management",
        "description": "Team handling a production outage",
        "speakers": ["SRE Lead", "Backend Dev", "Support Lead"],
        "segments_template": [
            "{s0}: We've got a P1. The payment service is returning 500 errors. About 40% of transactions are failing.",
            "{s1}: I'm looking at the logs now. There's a connection timeout to the payment gateway.",
            "{s2}: Support is getting flooded. We've had 200 tickets in the last 30 minutes.",
            "{s0}: OK, first thing - let's post a status page update. Users need to know we're aware.",
            "{s2}: I'll draft it right now.",
            "{s1}: Found it. The issue started after the last deployment at 2:15 PM. The new retry logic is hammering the gateway.",
            "{s0}: Can we roll back?",
            "{s1}: Rolling back now. It should take about 5 minutes.",
            "{s0}: Good. While that's happening, I'll notify the payment gateway team.",
            "{s2}: Should I offer refunds to affected customers?",
            "{s0}: Not yet. Let's first confirm the rollback fixes it. Then we'll assess the damage.",
            "{s1}: Rollback is complete. Monitoring the error rate now.",
            "{s1}: Error rate is dropping. Down to 5% and falling.",
            "{s0}: Good. Keep watching it for the next 30 minutes.",
            "{s0}: After this stabilizes, I want a post-mortem document by tomorrow. Include timeline, root cause, and prevention plan.",
            "{s1}: I'll write it up. We definitely need circuit breakers on the retry logic before we redeploy.",
        ],
    },
]


def generate_conversation(scenario: dict, target_segments: int) -> str:
    """Generate a transcript with the target number of segments."""
    speakers = scenario["speakers"]
    template = scenario["segments_template"]

    # Map speaker placeholders
    segments = []
    for seg_text in template:
        text = seg_text
        for i, speaker in enumerate(speakers):
            text = text.replace(f"{{s{i}}}", f"Speaker {i}")
        segments.append(text)

    # If we need more segments than the template, duplicate with variation
    while len(segments) < target_segments:
        idx = random.randint(0, len(template) - 1)
        text = template[idx]
        for i, speaker in enumerate(speakers):
            text = text.replace(f"{{s{i}}}", f"Speaker {i}")
        # Add slight variation
        variations = [
            "Actually, ",
            "You know what, ",
            "One more thing - ",
            "Oh also, ",
            "Wait, ",
            "By the way, ",
        ]
        text = random.choice(variations) + text.split(": ", 1)[1] if ": " in text else text
        speaker_id = random.randint(0, len(speakers) - 1)
        text = f"Speaker {speaker_id}: {text}"
        segments.append(text)

    # Trim to target
    segments = segments[:target_segments]
    return "\n\n".join(segments)


# ─── Run old approach (2 separate calls) ─────────────────────────────────────


def run_old_approach(transcript: str, started_at: datetime, language_code: str, tz: str):
    """Run the old 2-call approach: structure + action items."""
    structured = get_transcript_structure(transcript, started_at, language_code, tz)
    action_items = extract_action_items(transcript, started_at, language_code, tz)
    structured.action_items = action_items
    return structured


# ─── Run new approach (1 combined call) ──────────────────────────────────────


def run_new_approach(transcript: str, started_at: datetime, language_code: str, tz: str):
    """Run the new combined call."""
    return get_transcript_structure_with_action_items(transcript, started_at, language_code, tz)


# ─── GPT-5.1 Judge ──────────────────────────────────────────────────────────

JUDGE_PROMPT = """You are an expert evaluator comparing two different outputs from an LLM conversation processing system.

Both outputs were generated from the SAME conversation transcript. The goal is to determine if the outputs are of comparable quality.

## Transcript
{transcript}

## Output A (Baseline — separate LLM calls)
Title: {title_a}
Overview: {overview_a}
Emoji: {emoji_a}
Category: {category_a}
Events: {events_a}
Action Items: {action_items_a}

## Output B (Candidate — single combined LLM call)
Title: {title_b}
Overview: {overview_b}
Emoji: {emoji_b}
Category: {category_b}
Events: {events_b}
Action Items: {action_items_b}

## Evaluation Criteria

Score each dimension from 1-5 for BOTH outputs:

1. **Title Quality** (1-5): Clear, concise, captures main topic? ≤10 words?
2. **Overview Quality** (1-5): Comprehensive summary? Key points captured?
3. **Category Accuracy** (1-5): Correct categorization?
4. **Action Items - Completeness** (1-5): All important tasks extracted? No critical items missed?
5. **Action Items - Precision** (1-5): No false positives, no trivial items, no duplicates?
6. **Action Items - Formatting** (1-5): Concise descriptions? Time refs in due_at not description? Verb-first?
7. **Events Quality** (1-5): Correct events extracted? Proper dates?

Respond in this EXACT JSON format (no markdown, no extra text):
{{
  "scores_a": {{
    "title": <int>,
    "overview": <int>,
    "category": <int>,
    "action_completeness": <int>,
    "action_precision": <int>,
    "action_formatting": <int>,
    "events": <int>
  }},
  "scores_b": {{
    "title": <int>,
    "overview": <int>,
    "category": <int>,
    "action_completeness": <int>,
    "action_precision": <int>,
    "action_formatting": <int>,
    "events": <int>
  }},
  "winner": "A" or "B" or "tie",
  "reasoning": "<1-2 sentence explanation>"
}}"""


def judge_outputs(transcript: str, output_a, output_b) -> dict:
    """Use GPT-5.1 to compare two outputs."""

    def fmt_action_items(items):
        if not items:
            return "None"
        lines = []
        for item in items:
            due = item.due_at.isoformat() if item.due_at else "No due date"
            lines.append(f"- {item.description} (Due: {due})")
        return "\n".join(lines)

    def fmt_events(events):
        if not events:
            return "None"
        return "\n".join([f"- {e.title} (Start: {e.start.isoformat()}, Duration: {e.duration} min)" for e in events])

    prompt = JUDGE_PROMPT.format(
        transcript=transcript[:3000],  # Truncate for judge context
        title_a=output_a.title,
        overview_a=output_a.overview,
        emoji_a=output_a.emoji,
        category_a=output_a.category.value if output_a.category else "other",
        events_a=fmt_events(output_a.events),
        action_items_a=fmt_action_items(output_a.action_items),
        title_b=output_b.title,
        overview_b=output_b.overview,
        emoji_b=output_b.emoji,
        category_b=output_b.category.value if output_b.category else "other",
        events_b=fmt_events(output_b.events),
        action_items_b=fmt_action_items(output_b.action_items),
    )

    response = openai_client.chat.completions.create(
        model="gpt-5.1",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    content = response.choices[0].message.content.strip()
    # Try to parse JSON
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try extracting JSON from markdown code block
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            return json.loads(content.strip())
        raise


# ─── Main ────────────────────────────────────────────────────────────────────


def main():
    print("=" * 80)
    print("EVAL: Separate vs Combined LLM Calls for Conversation Processing")
    print("=" * 80)

    # Generate test conversations with varying lengths
    segment_counts = [10, 15, 20, 25, 30, 40, 50, 60, 75, 90, 16, 35]
    test_cases = []
    for i, count in enumerate(segment_counts):
        scenario = SCENARIOS[i % len(SCENARIOS)]
        test_cases.append(
            {
                "id": i + 1,
                "scenario": scenario["theme"],
                "description": scenario["description"],
                "segments": count,
                "transcript": generate_conversation(scenario, count),
            }
        )

    print(f"\nGenerated {len(test_cases)} test conversations")
    print(f"Segment range: {min(segment_counts)} - {max(segment_counts)}")
    print()

    results = []
    started_at = datetime.now(timezone.utc)

    for tc in test_cases:
        print(f"[{tc['id']:2d}/{len(test_cases)}] {tc['scenario']} ({tc['segments']} segments)...", end=" ", flush=True)

        try:
            # Run OLD approach (2 calls)
            t0 = time.time()
            output_a = run_old_approach(tc["transcript"], started_at, "en", "America/Los_Angeles")
            time_old = time.time() - t0

            # Run NEW approach (1 call)
            t0 = time.time()
            output_b = run_new_approach(tc["transcript"], started_at, "en", "America/Los_Angeles")
            time_new = time.time() - t0

            # Judge
            judgment = judge_outputs(tc["transcript"], output_a, output_b)

            result = {
                "id": tc["id"],
                "scenario": tc["scenario"],
                "segments": tc["segments"],
                "time_old": round(time_old, 2),
                "time_new": round(time_new, 2),
                "time_saved_pct": round((1 - time_new / time_old) * 100, 1) if time_old > 0 else 0,
                "scores_a": judgment["scores_a"],
                "scores_b": judgment["scores_b"],
                "avg_a": round(sum(judgment["scores_a"].values()) / len(judgment["scores_a"]), 2),
                "avg_b": round(sum(judgment["scores_b"].values()) / len(judgment["scores_b"]), 2),
                "winner": judgment["winner"],
                "reasoning": judgment["reasoning"],
                "action_items_a_count": len(output_a.action_items),
                "action_items_b_count": len(output_b.action_items),
                "events_a_count": len(output_a.events) if output_a.events else 0,
                "events_b_count": len(output_b.events) if output_b.events else 0,
            }
            results.append(result)

            winner_str = {"A": "OLD wins", "B": "NEW wins", "tie": "TIE"}[judgment["winner"]]
            print(
                f"OLD={result['avg_a']:.1f} NEW={result['avg_b']:.1f} [{winner_str}] "
                f"({time_old:.1f}s vs {time_new:.1f}s, {result['time_saved_pct']:+.0f}%)"
            )

        except Exception as e:
            print(f"ERROR: {e}")
            results.append({"id": tc["id"], "scenario": tc["scenario"], "segments": tc["segments"], "error": str(e)})

    # ─── Summary ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)

    valid = [r for r in results if "error" not in r]
    errors = [r for r in results if "error" in r]

    if not valid:
        print("No valid results!")
        return

    wins_a = sum(1 for r in valid if r["winner"] == "A")
    wins_b = sum(1 for r in valid if r["winner"] == "B")
    ties = sum(1 for r in valid if r["winner"] == "tie")

    avg_score_a = sum(r["avg_a"] for r in valid) / len(valid)
    avg_score_b = sum(r["avg_b"] for r in valid) / len(valid)
    avg_time_old = sum(r["time_old"] for r in valid) / len(valid)
    avg_time_new = sum(r["time_new"] for r in valid) / len(valid)
    avg_time_saved = sum(r["time_saved_pct"] for r in valid) / len(valid)

    # Per-dimension averages
    dims = ["title", "overview", "category", "action_completeness", "action_precision", "action_formatting", "events"]
    print(f"\nPer-dimension scores (avg across {len(valid)} conversations):")
    print(f"{'Dimension':<25} {'OLD (A)':>8} {'NEW (B)':>8} {'Delta':>8}")
    print("-" * 51)
    for dim in dims:
        avg_a = sum(r["scores_a"][dim] for r in valid) / len(valid)
        avg_b = sum(r["scores_b"][dim] for r in valid) / len(valid)
        delta = avg_b - avg_a
        marker = "  " if abs(delta) < 0.2 else (" +" if delta > 0 else " -")
        print(f"{dim:<25} {avg_a:>8.2f} {avg_b:>8.2f} {delta:>+8.2f}{marker}")

    print(f"\n{'Overall Average':<25} {avg_score_a:>8.2f} {avg_score_b:>8.2f} {avg_score_b - avg_score_a:>+8.2f}")

    print(f"\nWins: OLD={wins_a}  NEW={wins_b}  TIE={ties}")
    print(f"Avg latency: OLD={avg_time_old:.1f}s  NEW={avg_time_new:.1f}s  (saved {avg_time_saved:.0f}%)")
    print(f"Errors: {len(errors)}")

    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  [{e['id']}] {e['scenario']}: {e['error']}")

    # Save detailed results
    output_path = os.path.join(os.path.dirname(__file__), "eval_results.json")
    with open(output_path, "w") as f:
        json.dump(
            {
                "summary": {
                    "total": len(test_cases),
                    "valid": len(valid),
                    "wins_old": wins_a,
                    "wins_new": wins_b,
                    "ties": ties,
                    "avg_score_old": round(avg_score_a, 3),
                    "avg_score_new": round(avg_score_b, 3),
                    "avg_time_old": round(avg_time_old, 2),
                    "avg_time_new": round(avg_time_new, 2),
                },
                "results": results,
            },
            f,
            indent=2,
            default=str,
        )
    print(f"\nDetailed results saved to: {output_path}")

    # Verdict
    print("\n" + "=" * 80)
    quality_delta = avg_score_b - avg_score_a
    if quality_delta >= -0.1:
        print(
            f"VERDICT: PASS — Quality preserved (delta={quality_delta:+.2f}) with {avg_time_saved:.0f}% latency savings"
        )
    elif quality_delta >= -0.3:
        print(f"VERDICT: MARGINAL — Small quality drop (delta={quality_delta:+.2f}), may need prompt tuning")
    else:
        print(f"VERDICT: FAIL — Quality degradation detected (delta={quality_delta:+.2f}), do not ship")
    print("=" * 80)


if __name__ == "__main__":
    main()
