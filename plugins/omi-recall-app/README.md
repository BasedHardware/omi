# Omi Recall 🧠

**Spaced-repetition flashcards from your conversations.**

Omi already remembers everything you learn — in meetings, lectures, and conversations. But Omi remembering *for* you is not the same as you actually learning it. Recall closes that loop:

1. A conversation ends → Recall automatically extracts flashcards from what you learned.
2. You say **"quiz me"** to Omi → it reviews your due cards with you, one at a time.
3. An **SM-2 spaced-repetition scheduler** decides when each card comes back (1 day → 6 days → growing intervals).
4. One link exports your whole deck to **Anki** (`.apkg`).

## Features

- **Automatic card creation** from Omi's conversation-created webhook — zero manual effort.
- **Chat-native reviews**: `quiz_me`, `reveal_answer`, `grade_card` (again / hard / good / easy), `deck_stats` exposed as Omi chat tools.
- **Real SM-2 scheduling** with ease factor, growing intervals, and lapse handling.
- **Anki export** at `/deck/{uid}.apkg` — a valid `.apkg` you can import directly.
- **LLM-quality extraction with graceful degradation**: uses OpenAI if `OPENAI_API_KEY` is set; otherwise falls back to a heuristic fact extractor, so the app works with zero external services.
- **Self-contained**: single-file FastAPI app + SQLite. No Redis, no Firestore, no sign-in.

> **Security note:** This plugin currently relies only on the Omi `uid` for access control. If you deploy this publicly, consider adding a shared webhook secret or API token so that only Omi can trigger `/webhook` and only the owning user can access `/deck/{uid}.apkg`.

## How It Works

```
Conversation ends
      │  POST /webhook?uid=...   (Omi conversation-created trigger)
      ▼
Card extraction (LLM or heuristic) ──► SQLite (per-user deck + SM-2 state)
      ▲                                        │
      │ "quiz me" / "grade it: good"           ▼
Omi chat tools (/.well-known/omi-tools.json)   GET /deck/{uid}.apkg → Anki
```

## Setup

### Prerequisites

- Python 3.11+
- (Optional) An OpenAI API key for best-quality card extraction

### Installation

1. `cd plugins/omi-recall-app`
2. `pip install -r requirements.txt`
3. `cp .env.example .env` and fill in values (all optional)
4. `uvicorn main:app --port 8080`

### Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Optional. Enables LLM flashcard extraction (recommended). |
| `OPENAI_MODEL` | Optional. Defaults to `gpt-4o-mini`. |
| `RECALL_DB_PATH` | Optional. SQLite path, defaults to `recall.db`. |
| `MAX_CARDS_PER_CONVERSATION` | Optional. Defaults to 5. |

## Registering with Omi

1. Create an app in Omi with the **External Integration** capability, trigger **Conversation Creation**, and set the webhook URL to `https://<your-host>/webhook`.
2. Add the **Chat Tools** capability with manifest URL `https://<your-host>/.well-known/omi-tools.json`.
3. Setup-status URL (optional): `https://<your-host>/setup-status` — always ready, no sign-in needed.

## Usage

- Have a conversation. When it ends, cards are created automatically.
- Say **"quiz me"** — Omi asks the due questions one at a time, waits for your attempt, reveals the answer, and asks how you did.
- Say **"how's my deck?"** — get totals, due count, and your Anki export link.
- Open `/deck/{uid}.apkg` to import everything into Anki.

## Tests

```bash
pytest test_main.py -v   # 12 end-to-end tests: webhook → quiz → SM-2 → Anki export
```

## License

MIT
