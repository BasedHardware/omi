# Omi Classical Poetry & Verse Integration App (`omi-poetry-app`)

A standalone, unauthenticated integration app for the Omi AI ecosystem that connects wearable audio, smart glasses, and ambient conversational devices to the rich world of classical public-domain poetry, famous sonnets, and literary verse via **PoetryDB**.

---

## Highlights

- **Spoken Literary Wisdom for Wearables**: Instant, hands-free poetry recitation (Shakespeare, Emily Dickinson, Edgar Allan Poe, John Keats, Percy Bysshe Shelley, Walt Whitman, Robert Frost, etc.).
- **Voice-Optimized Line Lengths**: Filter poems by maximum line counts (e.g. short 14-line sonnets or brief 4-8 line verses) tailored for spoken audio recitation on smart glasses and necklaces.
- **Zero Authentication Required**: Uses 100% public domain literature via the open PoetryDB REST API. No API keys, OAuth, or accounts required.
- **Omi Chat-Tool Contract Compliant**: Implements strict `ChatToolResponse` protocol (`result` or `error`, omitting nulls), relative `endpoint`, `method: "POST"`, and `auth_required: false` in `/.well-known/omi-tools.json`.
- **In-Memory LRU Caching**: Bounded LRU cache buffers author directories and poems with TTL to optimize response speed.
- **Fully Tested**: Hermetic unit test suite (28/28 passing) and live ASGI integration smoke test suite (8/8 passing).

---

## Registered Chat Tools

| Tool Name | Endpoint | Description |
| :--- | :--- | :--- |
| `get_random_poem` | `POST /tools/get_random_poem` | Recite a random classical poem or sonnet with optional author and maximum line count filters. |
| `search_poems_by_author` | `POST /tools/search_poems_by_author` | Browse poems and preview excerpts by a specific classical poet. |
| `get_poem_by_title` | `POST /tools/get_poem_by_title` | Retrieve the complete text and verse lines of a famous poem by title. |
| `list_poets` | `POST /tools/list_poets` | Browse available poets in the collection with optional keyword filtering. |

---

## Quickstart

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Locally
```bash
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

### 3. Verify Health & Manifest
```bash
curl http://localhost:8080/health
curl http://localhost:8080/.well-known/omi-tools.json
```

### 4. Run Automated Tests
```bash
# Run hermetic unit tests (100% mocked, offline)
python3 -m unittest test_main.py

# Run live integration smoke tests
python3 smoke_test.py
```

---

## Example Tool Invocations

### 1. Recite a Random Short Poem by Shakespeare
```bash
curl -X POST http://localhost:8080/tools/get_random_poem \
  -H "Content-Type: application/json" \
  -d '{"author": "Shakespeare", "max_lines": 15}'
```

**Sample Response:**
```json
{
  "result": "📜 \"Sonnet 18: Shall I compare thee to a summer's day?\"\n✍️ by William Shakespeare (14 lines)\n\nShall I compare thee to a summer's day?\nThou art more lovely and more temperate:\nRough winds do shake the darling buds of May,\nAnd summer's lease hath all too short a date..."
}
```

### 2. Search Poems by Emily Dickinson
```bash
curl -X POST http://localhost:8080/tools/search_poems_by_author \
  -H "Content-Type: application/json" \
  -d '{"author": "Emily Dickinson", "max_results": 2}'
```

**Sample Response:**
```json
{
  "result": "📚 Found 362 poems by Emily Dickinson:\n\n1. \"Not at Home to Callers\" (4 lines):\n  Not at Home to Callers\n  Says the Naked Tree --\n  Bonnet due in April --\n  ...\n\n2. \"A slash of Blue --\" (8 lines):\n  A slash of Blue --\n  A sweep of Gray --\n  Some scarlet patches on the way,\n  ..."
}
```

### 3. Retrieve "Ozymandias"
```bash
curl -X POST http://localhost:8080/tools/get_poem_by_title \
  -H "Content-Type: application/json" \
  -d '{"title": "Ozymandias"}'
```

**Sample Response:**
```json
{
  "result": "📜 \"Ozymandias\"\n✍️ by Percy Bysshe Shelley (14 lines)\n\nI met a traveller from an antique land\nWho said: Two vast and trunkless legs of stone\nStand in the desert...Near them, on the sand,\nHalf sunk, a shattered visage lies..."
}
```

### 4. List Poets
```bash
curl -X POST http://localhost:8080/tools/list_poets \
  -H "Content-Type: application/json" \
  -d '{"query": "Shelley"}'
```

**Sample Response:**
```json
{
  "result": "🖋️ Poets matching 'Shelley' (1):\n• Percy Bysshe Shelley"
}
```

---

## Architecture & Reliability

- **Standard PoetryDB Integration**: Connects to the public `poetrydb.org` API for unauthenticated literary queries.
- **In-Memory LRU Caching**: Caches poet directories and query responses in `SimpleTTLCache` to prevent redundant network calls.
- **Pydantic v2 Boundary Protection**: Validates input lengths and sanitizes author/title strings.
- **Omi Chat-Tool Protocol Compliant**: Exposes `/.well-known/omi-tools.json` function manifest with JSON schema validation and structured `ChatToolResponse` error handling (omitting null fields).
- **Ready for Deployment**: Includes `railway.toml` (Nixpacks), `Procfile`, and `runtime.txt` (`python-3.11`).
