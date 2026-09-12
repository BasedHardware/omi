# Omi Nobel Prize Global Laureates & Human Discovery Integration App

A standalone, zero-authentication Omi integration app providing voice-optimized tools to query Nobel Prizes, explore groundbreaking discoveries, and discover laureate biographies directly from your Omi AI wearable.

Powered by the official [Nobel Prize API](https://api.nobelprize.org/2.1/).

---

## Features & Voice Capabilities

- **Zero-Authentication**: Queries the official Nobel Prize Open Data API with 0 API keys or user signups required.
- **Voice-Optimized Markdown**: Output formatted specifically for speech synthesis and concise conversational display.
- **Non-blocking Async I/O**: High-throughput FastAPI architecture using `httpx.AsyncClient` with resilient error handling and network timeouts.
- **Defensive Validation**: Pydantic v2 schemas normalizing informal user aliases (e.g. `medicine` $\to$ `med`, `economics` $\to$ `eco`) and guarding against out-of-range years or empty queries.
- **Omi Tool Contract**: Exposes `/.well-known/omi-tools.json` and returns standard `ChatToolResponse` objects with mutually exclusive `result`/`error`.

---

## Registered Chat Tools

| Endpoint | Tool Name | Voice Prompts |
|---|---|---|
| `POST /tools/get_nobel_prizes` | `get_nobel_prizes` | *"Who won the Nobel Prizes in 2023?"*, *"Who won the Nobel Peace Prize?"* |
| `POST /tools/search_nobel_laureates` | `search_nobel_laureates` | *"Tell me about Marie Curie's Nobel Prizes"*, *"Search for Einstein's Nobel award"* |
| `POST /tools/get_nobel_prize_by_category` | `get_nobel_prize_by_category` | *"What are the latest Nobel Prizes in Medicine?"*, *"Recent Literature Nobel winners"* |
| `POST /tools/get_nobel_laureate_details` | `get_nobel_laureate_details` | *"Get the full dossier for Albert Einstein"*, *"Look up laureate ID 1"* |

---

## Tool API Specifications

### 1. `POST /tools/get_nobel_prizes`
Retrieves Nobel Prizes filtered by year (1901 to current year) and/or discipline.

```json
{
  "year": 2023,
  "category": "physics",
  "limit": 5
}
```

**Sample Response:**
```json
{
  "result": "### The Nobel Prize in Physics (2023)\n- **Pierre Agostini** (Share: 1/3): for experimental methods that generate attosecond pulses of light for the study of electron dynamics in matter\n- **Ferenc Krausz** (Share: 1/3): for experimental methods that generate attosecond pulses of light for the study of electron dynamics in matter\n- **Anne L'Huillier** (Share: 1/3): for experimental methods that generate attosecond pulses of light for the study of electron dynamics in matter",
  "error": null
}
```

### 2. `POST /tools/search_nobel_laureates`
Searches laureates by name or keyword and returns birth details, award year, and discovery motivation.

```json
{
  "query": "Einstein",
  "limit": 3
}
```

### 3. `POST /tools/get_nobel_prize_by_category`
Fetches recent prizes for a specific category (`physics`, `chemistry`, `medicine`, `literature`, `peace`, `economics`).

```json
{
  "category": "medicine",
  "limit": 3
}
```

### 4. `POST /tools/get_nobel_laureate_details`
Fetches deep biographical and award dossier for a laureate using numeric ID or exact name.

```json
{
  "identifier": "1"
}
```

---

## Local Development & Testing

### Prerequisites
- Python 3.10+
- `fastapi`, `uvicorn`, `httpx`, `pydantic`

### Run Locally
```bash
cd plugins/omi-nobel-prize-app
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Visit:
- Documentation dashboard: `http://localhost:8000/`
- Health check: `http://localhost:8000/health`
- Tool manifest: `http://localhost:8000/.well-known/omi-tools.json`

### Automated Tests

#### 1. Hermetic Unit Tests (100% mocked, 0 network required)
```bash
python -m unittest test_main.py -v
```

#### 2. Live Smoke Tests (validates against live api.nobelprize.org)
```bash
python smoke_test.py
```

---

## Deployment

### Railway
Deploy with one click via Docker or Nixpacks using `railway.toml`:
```bash
railway up
```

### Docker
```bash
docker build -t omi-nobel-prize-app .
docker run -p 8000:8000 omi-nobel-prize-app
```

### Render / Heroku
Uses standard `Procfile` (`web: uvicorn main:app --host 0.0.0.0 --port $PORT`) and `runtime.txt`.
