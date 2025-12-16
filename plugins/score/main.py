"""
OMI Score Plugin - Daily Performance Score (0-5)

Calculates your daily score based on:
- 40% Learning: New memories/facts learned today
- 60% Execution: Tasks completed vs created today

Formula:
- Learn = 5 * (1 - exp(-L/3))
- Exec = 5 * clamp(0,1, 1.5*p - 0.5) where p = tasks_done / total_tasks
- Raw = 0.4*Learn + 0.6*Exec
- Rating = clamp(0,5, round(Raw*2)/2)
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import logging
import os
import requests
import math
import random

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="OMI Score", version="1.0.0")

# API credentials
OMI_APP_ID = os.getenv("OMI_APP_ID", "01KCAHZ0D65QAFPSB6H1REXQ06")
OMI_APP_SECRET = os.getenv("OMI_APP_SECRET", "sk_df20c320860abc34459db713f6166132")
OMI_BASE_API_URL = os.getenv("OMI_BASE_API_URL", "https://api.omi.me")


def clamp(a: float, b: float, x: float) -> float:
    """Clamp x between a and b."""
    return min(b, max(a, x))


def fetch_memories_last_24h(uid: str) -> List[dict]:
    """Fetch memories created in the last 24 hours."""
    try:
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(hours=24)
        
        url = f"{OMI_BASE_API_URL}/v2/integrations/{OMI_APP_ID}/memories"
        params = {"uid": uid, "limit": 100, "offset": 0}
        headers = {
            "Authorization": f"Bearer {OMI_APP_SECRET}",
            "Content-Type": "application/json",
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            memories = data if isinstance(data, list) else data.get("memories", [])
            
            recent_memories = []
            for memory in memories:
                created_at = memory.get("created_at")
                if created_at:
                    try:
                        if isinstance(created_at, str):
                            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        else:
                            created_dt = created_at
                        if created_dt >= yesterday:
                            recent_memories.append(memory)
                    except Exception as e:
                        logger.debug(f"Could not parse date: {created_at}, error: {e}")
            
            logger.info(f"Found {len(recent_memories)} memories in last 24h")
            return recent_memories
        else:
            logger.error(f"Failed to fetch memories: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"Error fetching memories: {e}")
        return []


def fetch_conversations_last_24h(uid: str) -> List[dict]:
    """Fetch conversations from the last 24 hours to extract tasks."""
    try:
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(hours=24)
        
        url = f"{OMI_BASE_API_URL}/v2/integrations/{OMI_APP_ID}/conversations"
        params = {"uid": uid, "limit": 100, "offset": 0}
        headers = {
            "Authorization": f"Bearer {OMI_APP_SECRET}",
            "Content-Type": "application/json",
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            conversations = data if isinstance(data, list) else data.get("conversations", [])
            
            recent_convos = []
            for conv in conversations:
                created_at = conv.get("created_at") or conv.get("started_at")
                if created_at:
                    try:
                        if isinstance(created_at, str):
                            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        else:
                            created_dt = created_at
                        if created_dt >= yesterday:
                            recent_convos.append(conv)
                    except Exception as e:
                        logger.debug(f"Could not parse date: {created_at}")
            
            logger.info(f"Found {len(recent_convos)} conversations in last 24h")
            return recent_convos
        else:
            logger.error(f"Failed to fetch conversations: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"Error fetching conversations: {e}")
        return []


def extract_tasks_from_conversations(conversations: List[dict]) -> dict:
    """Extract tasks from conversations and count done vs total."""
    tasks_done = 0
    tasks_total = 0
    
    for conv in conversations:
        action_items = conv.get("action_items", [])
        if action_items:
            for item in action_items:
                tasks_total += 1
                if item.get("completed", False) or item.get("done", False):
                    tasks_done += 1
        
        structured = conv.get("structured", {})
        if structured:
            struct_actions = structured.get("action_items", [])
            for item in struct_actions:
                tasks_total += 1
                if item.get("completed", False) or item.get("done", False):
                    tasks_done += 1
    
    return {
        "tasks_done": tasks_done,
        "tasks_total": tasks_total,
        "tasks_missed": tasks_total - tasks_done
    }


def calculate_omi_score(memories_count: int, tasks_done: int, tasks_total: int) -> dict:
    """Calculate OMI score using the formula."""
    L = memories_count
    Td = tasks_done
    T = tasks_total
    
    learn_score = 5 * (1 - math.exp(-L / 3))
    
    if T == 0:
        exec_score = 2.5
    else:
        p = Td / T
        exec_score = 5 * clamp(0, 1, 1.5 * p - 0.5)
    
    raw_score = 0.4 * learn_score + 0.6 * exec_score
    rating = clamp(0, 5, round(raw_score * 2) / 2)
    
    return {
        "rating": rating,
        "raw_score": round(raw_score, 2),
        "learn_score": round(learn_score, 2),
        "exec_score": round(exec_score, 2),
        "memories_today": L,
        "tasks_done": Td,
        "tasks_total": T,
        "tasks_missed": T - Td,
        "completion_rate": round(Td / T * 100, 1) if T > 0 else None
    }


# Research-backed advice for task completion (anti-procrastination)
TASK_ADVICE = [
    {
        "title": "Use the 2-Minute Rule",
        "detail": "If a task takes less than 2 minutes, do it right now. Small wins create momentum and reduce your mental backlog."
    },
    {
        "title": "Eat the Frog First",
        "detail": "Tackle your hardest or most dreaded task first thing in the morning when your willpower is highest. Everything else feels easier after."
    },
    {
        "title": "Try a 25-Minute Focus Sprint",
        "detail": "Set a timer for 25 minutes and work on one task only. No phone, no tabs, no interruptions. Take a 5-minute break after. Repeat."
    },
    {
        "title": "Remove All Distractions Now",
        "detail": "Put your phone in another room, close unnecessary tabs, and tell people you're unavailable. Environment shapes behavior more than willpower."
    },
    {
        "title": "Break It Into Tiny Steps",
        "detail": "Write down the very next physical action for your task. Not 'work on project' but 'open the document and write one sentence.' Make starting stupidly easy."
    },
    {
        "title": "Schedule a Specific Time Block",
        "detail": "Put your task on your calendar with a specific start and end time. Treat it like a meeting you can't miss. Vague intentions fail; scheduled blocks succeed."
    },
    {
        "title": "Use Implementation Intentions",
        "detail": "Say: 'When [TIME/TRIGGER], I will [TASK] in [LOCATION].' Example: 'When I finish lunch, I will write the report at my desk.' This doubles your follow-through rate."
    },
    {
        "title": "Start With Just 5 Minutes",
        "detail": "Commit to working on the task for only 5 minutes. You can stop after that. Most times you'll keep going once you've started—starting is the hardest part."
    },
    {
        "title": "Create Accountability",
        "detail": "Tell someone what you'll complete today and when. Text them when it's done. External accountability is 3x more effective than internal motivation."
    },
    {
        "title": "Visualize the Consequences",
        "detail": "Imagine how you'll feel tonight if you don't do this task. Then imagine the relief when it's done. Make the future real and let it pull you forward."
    },
]

# Advice for learning more
LEARNING_ADVICE = [
    {
        "title": "Listen to a Podcast",
        "detail": "Queue up a podcast on a topic you're curious about during your commute, workout, or chores. Learning while doing routine tasks is free time multiplication."
    },
    {
        "title": "Have a Deep Conversation",
        "detail": "Call or meet someone smarter than you in an area you want to grow. Ask them questions. One good conversation can teach you more than hours of reading."
    },
    {
        "title": "Read for 20 Minutes",
        "detail": "Pick up a book or long-form article on something you want to understand better. 20 focused minutes of reading compounds into thousands of pages per year."
    },
    {
        "title": "Watch a TED Talk or Documentary",
        "detail": "Replace one entertainment video with something educational today. YouTube, TED, or documentaries—there's world-class knowledge free on every topic."
    },
    {
        "title": "Teach Someone What You Know",
        "detail": "Explain something you learned recently to a friend or colleague. Teaching forces you to understand deeply and reveals gaps in your knowledge."
    },
    {
        "title": "Explore a Curiosity",
        "detail": "What's something you've wondered about but never looked up? Spend 15 minutes going down that rabbit hole today. Curiosity is the engine of learning."
    },
    {
        "title": "Ask More Questions Today",
        "detail": "In your next conversation, ask follow-up questions instead of just responding. 'How did you learn that?' 'What surprised you about it?' Questions unlock insights."
    },
    {
        "title": "Take Notes on What You Hear",
        "detail": "Keep a small note in your phone for interesting things people say today. Capturing ideas makes you listen more actively and remember more."
    },
]

# Advice when no tasks were set
PLANNING_ADVICE = [
    {
        "title": "Set 3 Clear Goals for Tomorrow",
        "detail": "Before bed tonight, write down exactly 3 things you want to accomplish tomorrow. Not 10, not 1—three is the sweet spot for focus and achievement."
    },
    {
        "title": "Plan Your Day Tonight",
        "detail": "Spend 5 minutes planning tomorrow's priorities. People who plan the night before are 2-3x more likely to complete their most important tasks."
    },
    {
        "title": "Define Your One Must-Do",
        "detail": "Ask yourself: 'If I could only accomplish one thing tomorrow, what would make the day a success?' Make that your non-negotiable."
    },
]


def get_actionable_advice(rating: float, learn_score: float, exec_score: float, 
                          memories: int, tasks_done: int, tasks_total: int) -> dict:
    """Get detailed actionable advice based on what needs improvement."""
    
    # Determine what needs work
    learning_weak = learn_score < 3.0
    execution_weak = exec_score < 3.0
    no_tasks = tasks_total == 0
    
    # Excellent day
    if rating >= 4.5:
        return {
            "headline": "Exceptional Day",
            "primary": {
                "title": "You're in the Zone",
                "detail": "Strong execution and continuous learning. This is what peak performance looks like. Keep this rhythm going tomorrow."
            },
            "secondary": None
        }
    
    # Great day
    if rating >= 4.0:
        return {
            "headline": "Strong Performance",
            "primary": {
                "title": "Great Balance Today",
                "detail": "You're doing well on both fronts. Small improvements compound over time—see if you can push a little further tomorrow."
            },
            "secondary": None
        }
    
    # Both need work
    if learning_weak and (execution_weak or no_tasks):
        # Execution is worse or equal—prioritize tasks
        if no_tasks:
            return {
                "headline": "Set Your Targets",
                "primary": random.choice(PLANNING_ADVICE),
                "secondary": random.choice(LEARNING_ADVICE)
            }
        else:
            return {
                "headline": "Time to Execute",
                "primary": random.choice(TASK_ADVICE),
                "secondary": random.choice(LEARNING_ADVICE)
            }
    
    # Only execution needs work
    if execution_weak or (no_tasks and not learning_weak):
        if no_tasks:
            return {
                "headline": "Define Your Goals",
                "primary": random.choice(PLANNING_ADVICE),
                "secondary": None
            }
        else:
            return {
                "headline": "Focus on Execution",
                "primary": random.choice(TASK_ADVICE),
                "secondary": None
            }
    
    # Only learning needs work
    if learning_weak:
        return {
            "headline": "Feed Your Mind",
            "primary": random.choice(LEARNING_ADVICE),
            "secondary": None
        }
    
    # Default - decent day
    return {
        "headline": "Solid Progress",
        "primary": {
            "title": "Keep the Momentum",
            "detail": "You're making progress. Stay consistent and push a bit harder tomorrow to reach your potential."
        },
        "secondary": None
    }


SCORE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OMI Score</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #000000;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            color: #fff;
        }}
        
        .container {{ 
            max-width: 400px; 
            width: 100%; 
        }}
        
        .header {{
            text-align: center;
            margin-bottom: 8px;
        }}
        
        .header .label {{
            font-size: 11px;
            font-weight: 500;
            letter-spacing: 2px;
            color: rgba(255, 255, 255, 0.4);
            text-transform: uppercase;
        }}
        
        .header .date {{
            font-size: 13px;
            color: rgba(255, 255, 255, 0.5);
            margin-top: 4px;
        }}
        
        /* Arc gauge */
        .gauge-container {{
            position: relative;
            width: 280px;
            height: 180px;
            margin: 20px auto 0;
        }}
        
        .gauge-svg {{
            width: 100%;
            height: 100%;
        }}
        
        .score-center {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -20%);
            text-align: center;
        }}
        
        .score-number {{
            font-size: 72px;
            font-weight: 300;
            letter-spacing: -2px;
            color: #fff;
            line-height: 1;
        }}
        
        .score-status {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            margin-top: 8px;
        }}
        
        .status-dot {{
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: {status_color};
        }}
        
        .status-text {{
            font-size: 13px;
            color: rgba(255, 255, 255, 0.6);
        }}
        
        /* Advice cards */
        .advice-section {{
            margin: 24px 0;
        }}
        
        .advice-headline {{
            font-size: 11px;
            font-weight: 500;
            letter-spacing: 1.5px;
            color: rgba(255, 255, 255, 0.4);
            text-transform: uppercase;
            margin-bottom: 12px;
            padding-left: 4px;
        }}
        
        .advice-card {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 12px;
        }}
        
        .advice-card.secondary {{
            background: rgba(255, 255, 255, 0.02);
            border-color: rgba(255, 255, 255, 0.04);
        }}
        
        .advice-title {{
            font-size: 15px;
            font-weight: 600;
            color: #fff;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .advice-icon {{
            font-size: 14px;
        }}
        
        .advice-detail {{
            font-size: 14px;
            color: rgba(255, 255, 255, 0.6);
            line-height: 1.6;
        }}
        
        /* Metrics row */
        .metrics {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-top: 16px;
        }}
        
        .metric-card {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 16px;
            padding: 20px;
        }}
        
        .metric-label {{
            font-size: 10px;
            font-weight: 500;
            letter-spacing: 1.5px;
            color: rgba(255, 255, 255, 0.4);
            text-transform: uppercase;
            margin-bottom: 12px;
        }}
        
        .metric-value {{
            font-size: 32px;
            font-weight: 300;
            color: #fff;
        }}
        
        .metric-sub {{
            display: flex;
            align-items: center;
            gap: 6px;
            margin-top: 4px;
        }}
        
        .metric-score {{
            font-size: 13px;
            color: rgba(255, 255, 255, 0.5);
        }}
        
        .metric-indicator {{
            width: 5px;
            height: 5px;
            border-radius: 50%;
        }}
        
        .indicator-green {{ background: #22c55e; }}
        .indicator-yellow {{ background: #eab308; }}
        .indicator-red {{ background: #ef4444; }}
        
        /* Footer */
        .footer {{
            text-align: center;
            margin-top: 24px;
            padding-top: 16px;
            border-top: 1px solid rgba(255, 255, 255, 0.06);
        }}
        
        .footer-text {{
            font-size: 11px;
            color: rgba(255, 255, 255, 0.3);
            font-family: 'SF Mono', Monaco, monospace;
        }}
        
        /* No UID state */
        .no-uid {{
            text-align: center;
            padding: 60px 24px;
        }}
        
        .no-uid-icon {{
            font-size: 48px;
            margin-bottom: 20px;
            opacity: 0.6;
        }}
        
        .no-uid h2 {{
            font-size: 20px;
            font-weight: 500;
            color: #fff;
            margin-bottom: 12px;
        }}
        
        .no-uid p {{
            font-size: 14px;
            color: rgba(255, 255, 255, 0.5);
            margin-bottom: 20px;
        }}
        
        .no-uid code {{
            display: inline-block;
            background: rgba(255, 255, 255, 0.08);
            padding: 10px 16px;
            border-radius: 8px;
            font-size: 13px;
            color: #60a5fa;
            font-family: 'SF Mono', Monaco, monospace;
        }}
    </style>
</head>
<body>
    <div class="container">
        {content}
    </div>
</body>
</html>
"""

SCORE_CONTENT = """
<div class="header">
    <div class="label">OMI Score</div>
    <div class="date">{date_display}</div>
</div>

<div class="gauge-container">
    <svg class="gauge-svg" viewBox="0 0 200 120">
        <g class="gauge-ticks">
            {gauge_ticks}
        </g>
    </svg>
    <div class="score-center">
        <div class="score-number">{rating_display}</div>
        <div class="score-status">
            <div class="status-dot"></div>
            <span class="status-text">{status_label}</span>
        </div>
    </div>
</div>

<div class="advice-section">
    <div class="advice-headline">{headline}</div>
    <div class="advice-card">
        <div class="advice-title">
            <span class="advice-icon">{primary_icon}</span>
            {primary_title}
        </div>
        <div class="advice-detail">{primary_detail}</div>
    </div>
    {secondary_card}
</div>

<div class="metrics">
    <div class="metric-card">
        <div class="metric-label">Learning</div>
        <div class="metric-value">{memories}</div>
        <div class="metric-sub">
            <span class="metric-score">{learn_score}/5</span>
            <div class="metric-indicator {learn_indicator}"></div>
        </div>
    </div>
    <div class="metric-card">
        <div class="metric-label">Execution</div>
        <div class="metric-value">{tasks_display}</div>
        <div class="metric-sub">
            <span class="metric-score">{exec_score}/5</span>
            <div class="metric-indicator {exec_indicator}"></div>
        </div>
    </div>
</div>

<div class="footer">
    <div class="footer-text">{uid_display}</div>
</div>
"""

SECONDARY_CARD_TEMPLATE = """
<div class="advice-card secondary">
    <div class="advice-title">
        <span class="advice-icon">{icon}</span>
        {title}
    </div>
    <div class="advice-detail">{detail}</div>
</div>
"""

NO_UID_CONTENT = """
<div class="no-uid">
    <div class="no-uid-icon">📊</div>
    <h2>OMI Score</h2>
    <p>See your daily performance based on<br>learning and task completion.</p>
    <code>/score?uid=YOUR_ID</code>
</div>
"""


def generate_gauge_ticks(rating: float) -> str:
    """Generate SVG ticks for the gauge arc."""
    ticks = []
    total_ticks = 50
    filled_ticks = int((rating / 5) * total_ticks)
    
    cx, cy = 100, 100
    radius = 80
    start_angle = 180
    
    for i in range(total_ticks):
        progress = i / (total_ticks - 1)
        angle_deg = start_angle - (progress * 180)
        angle_rad = math.radians(angle_deg)
        
        x1 = cx + (radius - 4) * math.cos(angle_rad)
        y1 = cy - (radius - 4) * math.sin(angle_rad)
        x2 = cx + (radius + 4) * math.cos(angle_rad)
        y2 = cy - (radius + 4) * math.sin(angle_rad)
        
        if i < filled_ticks:
            if rating >= 4.0:
                color = "#22c55e"
            elif rating >= 2.5:
                color = "#3b82f6"
            else:
                color = "#ef4444"
        else:
            color = "rgba(255, 255, 255, 0.1)"
        
        ticks.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/>')
    
    return '\n'.join(ticks)


def get_status_label(rating: float) -> str:
    """Get status label for the score."""
    if rating >= 4.5:
        return "Excellent"
    elif rating >= 4.0:
        return "Great"
    elif rating >= 3.0:
        return "Good"
    elif rating >= 2.0:
        return "Fair"
    elif rating >= 1.0:
        return "Low"
    else:
        return "Needs work"


def get_status_color(rating: float) -> str:
    """Get status dot color."""
    if rating >= 4.0:
        return "#22c55e"
    elif rating >= 2.5:
        return "#3b82f6"
    else:
        return "#ef4444"


def get_indicator_class(score: float) -> str:
    """Get indicator color class based on score."""
    if score >= 4.0:
        return "indicator-green"
    elif score >= 2.5:
        return "indicator-yellow"
    else:
        return "indicator-red"


def get_advice_icon(advice_type: str) -> str:
    """Get icon for advice type."""
    if "task" in advice_type.lower() or "execute" in advice_type.lower() or "frog" in advice_type.lower() or "focus" in advice_type.lower() or "minute" in advice_type.lower() or "distraction" in advice_type.lower() or "break" in advice_type.lower() or "schedule" in advice_type.lower() or "account" in advice_type.lower() or "visualize" in advice_type.lower() or "time" in advice_type.lower() or "goal" in advice_type.lower() or "plan" in advice_type.lower() or "must-do" in advice_type.lower():
        return "⚡"
    elif "podcast" in advice_type.lower() or "learn" in advice_type.lower() or "read" in advice_type.lower() or "conversation" in advice_type.lower() or "ted" in advice_type.lower() or "teach" in advice_type.lower() or "curiosity" in advice_type.lower() or "question" in advice_type.lower() or "note" in advice_type.lower():
        return "🧠"
    elif "zone" in advice_type.lower() or "balance" in advice_type.lower() or "momentum" in advice_type.lower() or "exceptional" in advice_type.lower() or "strong" in advice_type.lower():
        return "🌟"
    else:
        return "💡"


@app.get("/", response_class=HTMLResponse)
async def root():
    """Root redirects to score page."""
    html = SCORE_HTML.format(
        content=NO_UID_CONTENT,
        status_color="#3b82f6"
    )
    return HTMLResponse(content=html)


@app.get("/score", response_class=HTMLResponse)
async def score_page(uid: Optional[str] = Query(None, description="User ID")):
    """OMI Score page."""
    if not uid:
        html = SCORE_HTML.format(
            content=NO_UID_CONTENT,
            status_color="#3b82f6"
        )
        return HTMLResponse(content=html)
    
    try:
        logger.info(f"Calculating score for uid: {uid}")
        
        # Fetch data
        memories = fetch_memories_last_24h(uid)
        conversations = fetch_conversations_last_24h(uid)
        task_data = extract_tasks_from_conversations(conversations)
        
        # Calculate score
        score = calculate_omi_score(
            memories_count=len(memories),
            tasks_done=task_data["tasks_done"],
            tasks_total=task_data["tasks_total"]
        )
        
        # Get advice
        advice_data = get_actionable_advice(
            score["rating"],
            score["learn_score"],
            score["exec_score"],
            len(memories),
            task_data["tasks_done"],
            task_data["tasks_total"]
        )
        
        # Format rating display
        rating_display = f"{score['rating']:.1f}".rstrip('0').rstrip('.')
        if '.' not in rating_display:
            rating_display = str(int(score['rating']))
        
        # Tasks display
        if task_data["tasks_total"] > 0:
            tasks_display = f"{task_data['tasks_done']}/{task_data['tasks_total']}"
        else:
            tasks_display = "—"
        
        # Build secondary card if exists
        secondary_card = ""
        if advice_data.get("secondary"):
            secondary_card = SECONDARY_CARD_TEMPLATE.format(
                icon=get_advice_icon(advice_data["secondary"]["title"]),
                title=advice_data["secondary"]["title"],
                detail=advice_data["secondary"]["detail"]
            )
        
        # Generate content
        content = SCORE_CONTENT.format(
            date_display=datetime.now().strftime("%A, %b %d"),
            gauge_ticks=generate_gauge_ticks(score["rating"]),
            rating_display=rating_display,
            status_label=get_status_label(score["rating"]),
            headline=advice_data["headline"],
            primary_icon=get_advice_icon(advice_data["primary"]["title"]),
            primary_title=advice_data["primary"]["title"],
            primary_detail=advice_data["primary"]["detail"],
            secondary_card=secondary_card,
            memories=len(memories),
            learn_score=score["learn_score"],
            learn_indicator=get_indicator_class(score["learn_score"]),
            tasks_display=tasks_display,
            exec_score=score["exec_score"],
            exec_indicator=get_indicator_class(score["exec_score"]),
            uid_display=uid[:24] + "..." if len(uid) > 24 else uid
        )
        
        html = SCORE_HTML.format(
            content=content,
            status_color=get_status_color(score["rating"])
        )
        return HTMLResponse(content=html)
        
    except Exception as e:
        logger.error(f"Error calculating score: {e}")
        error_content = f'<div class="no-uid"><h2>Error</h2><p>{str(e)}</p></div>'
        html = SCORE_HTML.format(
            content=error_content,
            status_color="#ef4444"
        )
        return HTMLResponse(content=html)


@app.get("/score/api")
async def score_api(uid: str = Query(..., description="User ID")):
    """API endpoint to get score as JSON."""
    try:
        memories = fetch_memories_last_24h(uid)
        conversations = fetch_conversations_last_24h(uid)
        task_data = extract_tasks_from_conversations(conversations)
        
        score = calculate_omi_score(
            memories_count=len(memories),
            tasks_done=task_data["tasks_done"],
            tasks_total=task_data["tasks_total"]
        )
        
        advice_data = get_actionable_advice(
            score["rating"],
            score["learn_score"],
            score["exec_score"],
            len(memories),
            task_data["tasks_done"],
            task_data["tasks_total"]
        )
        
        return JSONResponse(content={
            "uid": uid,
            **score,
            "headline": advice_data["headline"],
            "primary_advice": advice_data["primary"],
            "secondary_advice": advice_data.get("secondary")
        })
        
    except Exception as e:
        logger.error(f"Error getting score: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/score/setup-status")
async def setup_status():
    """Setup status endpoint required by OMI."""
    return {"is_setup_completed": True}


if __name__ == '__main__':
    import uvicorn
    port = int(os.getenv('PORT', 8000))
    uvicorn.run(app, host='0.0.0.0', port=port)

