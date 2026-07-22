"""
Omi Recall — Spaced-repetition flashcards from your conversations.

Omi already remembers everything you learn. Recall makes *you* remember it.
Every time a conversation ends, this app extracts flashcards from what you
learned, quizzes you through Omi chat with an SM-2 scheduler, and exports
your deck to Anki.

Integration points:
- POST /webhook?uid=...          Omi "conversation created" trigger
- GET  /.well-known/omi-tools.json  Chat tools manifest (quiz_me, grade_card, ...)
- GET  /deck/{uid}.apkg          Anki deck export
"""

import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

import genanki

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = os.getenv("RECALL_DB_PATH", "recall.db")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_CARDS_PER_CONVERSATION = int(os.getenv("MAX_CARDS_PER_CONVERSATION", "5"))
REQUEST_TIMEOUT_SECONDS = 30

app = FastAPI(
    title="Omi Recall",
    description="Spaced-repetition flashcards from your Omi conversations",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Storage (SQLite — zero external services required)
# ---------------------------------------------------------------------------

def _init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cards (
                id TEXT PRIMARY KEY,
                uid TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                source_title TEXT DEFAULT '',
                conversation_id TEXT DEFAULT '',
                created_at REAL NOT NULL,
                -- SM-2 scheduling state
                ease REAL NOT NULL DEFAULT 2.5,
                interval_days REAL NOT NULL DEFAULT 0,
                reps INTEGER NOT NULL DEFAULT 0,
                lapses INTEGER NOT NULL DEFAULT 0,
                due_at REAL NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cards_uid_due ON cards(uid, due_at)")


@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


_init_db()


# ---------------------------------------------------------------------------
# Flashcard extraction
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """You create high-quality spaced-repetition flashcards from a conversation transcript.

Rules:
- Only create cards for durable knowledge the user would want to remember weeks from now: facts, definitions, numbers, names, techniques, decisions and their reasons.
- Never create cards about small talk, logistics, or things with no learning value.
- Questions must be answerable without seeing the transcript (self-contained).
- Answers must be short (one sentence or a few words).
- If the conversation contains nothing worth remembering, return an empty list.

Respond ONLY with JSON: {"cards": [{"question": "...", "answer": "..."}]}"""


async def _extract_cards_llm(transcript: str, title: str, overview: str) -> list[dict[str, str]]:
    """Extract flashcards with an LLM (best quality path)."""
    user_prompt = (
        f"Conversation title: {title}\n"
        f"Overview: {overview}\n\n"
        f"Transcript:\n{transcript[:12000]}\n\n"
        f"Create at most {MAX_CARDS_PER_CONVERSATION} flashcards."
    )
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": OPENAI_MODEL,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            },
        )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    cards = json.loads(content).get("cards", [])
    return [
        {"question": c["question"].strip(), "answer": c["answer"].strip()}
        for c in cards
        if isinstance(c, dict) and c.get("question") and c.get("answer")
    ][:MAX_CARDS_PER_CONVERSATION]


# Sentences that tend to carry durable knowledge (definitions, numbers, causality).
_FACT_PATTERN = re.compile(
    r"\b(is|are|was|were|means|called|costs?|equals?|because|invented|founded|released|launched|discovered)\b",
    re.IGNORECASE,
)


def _extract_cards_heuristic(transcript: str, title: str, overview: str) -> list[dict[str, str]]:
    """No-LLM fallback: turn fact-like sentences from the summary/transcript into cards."""
    source_text = f"{overview} {transcript}"
    sentences = re.split(r"(?<=[.!?])\s+", source_text)
    cards: list[dict[str, str]] = []
    seen: set[str] = set()

    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 30 or len(sentence) > 240:
            continue
        if not _FACT_PATTERN.search(sentence):
            continue
        key = sentence.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        topic = title.strip() or "this conversation"
        cards.append(
            {
                "question": f'From "{topic}": complete the fact — "{sentence[: sentence.find(" ", len(sentence) // 2)]}..."',
                "answer": sentence,
            }
        )
        if len(cards) >= MAX_CARDS_PER_CONVERSATION:
            break
    return cards


async def extract_cards(transcript: str, title: str, overview: str) -> list[dict[str, str]]:
    if OPENAI_API_KEY:
        try:
            return await _extract_cards_llm(transcript, title, overview)
        except Exception as exc:  # noqa: BLE001 — fall back rather than drop the conversation
            print(f"LLM extraction failed, using heuristic fallback: {exc}", flush=True)
    return _extract_cards_heuristic(transcript, title, overview)


# ---------------------------------------------------------------------------
# SM-2 scheduling
# ---------------------------------------------------------------------------

GRADE_QUALITY = {"again": 1, "hard": 3, "good": 4, "easy": 5}


def sm2_update(ease: float, interval_days: float, reps: int, lapses: int, grade: str) -> dict[str, float]:
    """One SM-2 review step. Returns the new scheduling state."""
    quality = GRADE_QUALITY.get(grade, 4)

    if quality < 3:  # failed — relearn
        return {
            "ease": max(1.3, ease - 0.2),
            "interval_days": 0,  # due again in ~10 minutes
            "reps": 0,
            "lapses": lapses + 1,
            "due_at": time.time() + 10 * 60,
        }

    ease = max(1.3, ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
    if reps == 0:
        interval_days = 1
    elif reps == 1:
        interval_days = 6
    else:
        interval_days = round(interval_days * ease, 1)

    return {
        "ease": ease,
        "interval_days": interval_days,
        "reps": reps + 1,
        "lapses": lapses,
        "due_at": time.time() + interval_days * 86400,
    }


# ---------------------------------------------------------------------------
# Webhook: conversation created
# ---------------------------------------------------------------------------

@app.post("/webhook")
async def conversation_webhook(request: Request, uid: str = Query(..., description="User ID from Omi")):
    """Receives Omi's conversation-created payload and turns it into flashcards."""
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON payload"}, status_code=400)

    structured = payload.get("structured") or {}
    title = structured.get("title", "") or ""
    overview = structured.get("overview", "") or ""
    conversation_id = payload.get("id", "") or ""

    segments = payload.get("transcript_segments") or payload.get("segments") or []
    transcript = " ".join(
        seg.get("text", "").strip() for seg in segments if isinstance(seg, dict) and seg.get("text")
    ).strip()

    if not transcript and not overview:
        return {"status": "ok", "cards_created": 0}

    cards = await extract_cards(transcript, title, overview)

    now = time.time()
    with _db() as conn:
        for card in cards:
            conn.execute(
                "INSERT INTO cards (id, uid, question, answer, source_title, conversation_id, created_at, due_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex[:12], uid, card["question"], card["answer"], title, conversation_id, now, now),
            )

    print(f"Created {len(cards)} card(s) for uid={uid} from conversation '{title}'", flush=True)
    return {"status": "ok", "cards_created": len(cards)}


# ---------------------------------------------------------------------------
# Chat tools
# ---------------------------------------------------------------------------

class ChatToolResponse(BaseModel):
    result: Optional[str] = None
    error: Optional[str] = None


class QuizRequest(BaseModel):
    uid: str
    limit: Optional[int] = 3


class RevealRequest(BaseModel):
    uid: str
    card_id: str


class GradeRequest(BaseModel):
    uid: str
    card_id: str
    grade: str  # again | hard | good | easy


class StatsRequest(BaseModel):
    uid: str


@app.get("/.well-known/omi-tools.json")
async def omi_tools_manifest():
    return {
        "tools": [
            {
                "name": "quiz_me",
                "description": (
                    "Quiz the user on flashcards that are due for review. Use when the user says"
                    " 'quiz me', 'test me', 'review my flashcards', or asks to practice what they learned."
                    " Ask the questions one at a time and do NOT reveal answers until the user tries."
                ),
                "endpoint": "/tools/quiz_me",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max cards to review (default 3)"},
                    },
                    "required": [],
                },
            },
            {
                "name": "reveal_answer",
                "description": "Reveal the answer of a flashcard by card_id, after the user attempted it.",
                "endpoint": "/tools/reveal_answer",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {"card_id": {"type": "string", "description": "The card id"}},
                    "required": ["card_id"],
                },
            },
            {
                "name": "grade_card",
                "description": (
                    "Record how well the user remembered a flashcard so spaced repetition can schedule"
                    " the next review. Grade must be one of: again, hard, good, easy."
                ),
                "endpoint": "/tools/grade_card",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_id": {"type": "string", "description": "The card id"},
                        "grade": {"type": "string", "enum": ["again", "hard", "good", "easy"]},
                    },
                    "required": ["card_id", "grade"],
                },
            },
            {
                "name": "deck_stats",
                "description": (
                    "Get the user's flashcard deck stats: total cards, cards due now, and the Anki"
                    " export link. Use when the user asks about their deck, progress, or Anki export."
                ),
                "endpoint": "/tools/deck_stats",
                "method": "POST",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        ]
    }


@app.post("/tools/quiz_me", response_model=ChatToolResponse)
async def tool_quiz_me(body: QuizRequest):
    limit = max(1, min(body.limit or 3, 10))
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, question, source_title FROM cards WHERE uid = ? AND due_at <= ? ORDER BY due_at LIMIT ?",
            (body.uid, time.time(), limit),
        ).fetchall()

    if not rows:
        return ChatToolResponse(
            result="No cards are due right now. New flashcards are created automatically after your conversations."
        )

    lines = [f"{len(rows)} card(s) due. Ask one at a time, wait for the user's attempt, then grade it:"]
    for row in rows:
        source = f" (from: {row['source_title']})" if row["source_title"] else ""
        lines.append(f"- card_id={row['id']}{source}: {row['question']}")
    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/reveal_answer", response_model=ChatToolResponse)
async def tool_reveal_answer(body: RevealRequest):
    with _db() as conn:
        row = conn.execute(
            "SELECT answer FROM cards WHERE uid = ? AND id = ?", (body.uid, body.card_id)
        ).fetchone()
    if not row:
        return ChatToolResponse(error=f"Card {body.card_id} not found.")
    return ChatToolResponse(result=f"Answer: {row['answer']}")


@app.post("/tools/grade_card", response_model=ChatToolResponse)
async def tool_grade_card(body: GradeRequest):
    grade = body.grade.lower().strip()
    if grade not in GRADE_QUALITY:
        return ChatToolResponse(error="Grade must be one of: again, hard, good, easy.")

    with _db() as conn:
        row = conn.execute(
            "SELECT ease, interval_days, reps, lapses FROM cards WHERE uid = ? AND id = ?",
            (body.uid, body.card_id),
        ).fetchone()
        if not row:
            return ChatToolResponse(error=f"Card {body.card_id} not found.")

        new_state = sm2_update(row["ease"], row["interval_days"], row["reps"], row["lapses"], grade)
        conn.execute(
            "UPDATE cards SET ease = ?, interval_days = ?, reps = ?, lapses = ?, due_at = ? WHERE uid = ? AND id = ?",
            (
                new_state["ease"],
                new_state["interval_days"],
                new_state["reps"],
                new_state["lapses"],
                new_state["due_at"],
                body.uid,
                body.card_id,
            ),
        )

    if grade == "again":
        return ChatToolResponse(result="Got it — this card will come back in about 10 minutes.")
    days = new_state["interval_days"]
    return ChatToolResponse(result=f"Recorded '{grade}'. Next review in {days:g} day(s).")


@app.post("/tools/deck_stats", response_model=ChatToolResponse)
async def tool_deck_stats(body: StatsRequest, request: Request):
    with _db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM cards WHERE uid = ?", (body.uid,)).fetchone()[0]
        due = conn.execute(
            "SELECT COUNT(*) FROM cards WHERE uid = ? AND due_at <= ?", (body.uid, time.time())
        ).fetchone()[0]

    base = str(request.base_url).rstrip("/")
    return ChatToolResponse(
        result=(
            f"Deck: {total} card(s) total, {due} due for review now.\n"
            f"Anki export: {base}/deck/{body.uid}.apkg"
        )
    )


# ---------------------------------------------------------------------------
# Anki export
# ---------------------------------------------------------------------------

_ANKI_MODEL = genanki.Model(
    1607392319,
    "Omi Recall Card",
    fields=[{"name": "Question"}, {"name": "Answer"}, {"name": "Source"}],
    templates=[
        {
            "name": "Card 1",
            "qfmt": "{{Question}}<br><br><span style='font-size:12px;color:#888'>{{Source}}</span>",
            "afmt": "{{FrontSide}}<hr id='answer'>{{Answer}}",
        }
    ],
)


@app.get("/deck/{uid}.apkg")
async def export_deck(uid: str):
    with _db() as conn:
        rows = conn.execute(
            "SELECT question, answer, source_title FROM cards WHERE uid = ? ORDER BY created_at", (uid,)
        ).fetchall()

    if not rows:
        return JSONResponse({"error": "No cards for this user yet."}, status_code=404)

    deck = genanki.Deck(int(uuid.uuid5(uuid.NAMESPACE_DNS, uid).int % 10**10), "Omi Recall")
    for row in rows:
        deck.add_note(
            genanki.Note(model=_ANKI_MODEL, fields=[row["question"], row["answer"], row["source_title"] or "Omi"])
        )

    import tempfile
    fd, out_path = tempfile.mkstemp(suffix=".apkg")
    os.close(fd)
    genanki.Package(deck).write_to_file(out_path)
    with open(out_path, "rb") as f:
        data = f.read()
    os.remove(out_path)

    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="omi-recall-{uid}.apkg"'},
    )


# ---------------------------------------------------------------------------
# Landing + health + setup status
# ---------------------------------------------------------------------------

@app.get("/setup-status")
async def setup_status(uid: str = Query(...)):
    """Omi calls this to check whether the app is ready for a user. No setup needed."""
    return {"is_setup_completed": True}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return HTMLResponse(
        """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Omi Recall</title>
<style>
  :root { --ink:#1c1a17; --paper:#fdfcf9; --edge:#e4e0d8; --accent:#3b5bdb; }
  * { box-sizing:border-box; margin:0; }
  body { font-family:'Iowan Old Style',Georgia,serif; background:var(--paper); color:var(--ink);
         min-height:100vh; display:grid; place-items:center; padding:32px; }
  main { max-width:560px; }
  .card { border:1px solid var(--edge); border-radius:14px; padding:28px 30px; background:#fff;
          box-shadow:0 1px 0 var(--edge), 0 12px 28px -20px rgba(28,26,23,.35);
          transform:rotate(-.6deg); margin-bottom:14px; }
  .card.answer { transform:rotate(.5deg); border-left:3px solid var(--accent); }
  .label { font-family:ui-monospace,Menlo,monospace; font-size:11px; letter-spacing:.14em;
           text-transform:uppercase; color:#8b867c; margin-bottom:10px; }
  h1 { font-size:30px; font-weight:600; letter-spacing:-.01em; }
  p  { font-size:16px; line-height:1.55; color:#3f3b34; }
  .foot { margin-top:26px; font-family:ui-monospace,Menlo,monospace; font-size:12.5px; color:#8b867c; }
  .foot code { color:var(--accent); }
</style>
</head>
<body>
<main>
  <div class="card">
    <div class="label">Question</div>
    <h1>What did you learn today?</h1>
  </div>
  <div class="card answer">
    <div class="label">Answer</div>
    <p>Omi Recall turns your conversations into spaced-repetition flashcards —
       automatically. Say <em>"quiz me"</em> to Omi to review what's due,
       or export everything to Anki.</p>
  </div>
  <div class="foot">no sign-in · cards appear after each conversation · <code>/deck/&lt;uid&gt;.apkg</code></div>
</main>
</body>
</html>
        """
    )
