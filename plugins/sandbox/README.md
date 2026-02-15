# Omi Sandbox Plugin

A generic, cloneable framework for building Omi plugins. Receives real-time transcript chunks, buffers them, processes with an LLM, and extracts tasks, memories, and notifications — all shaped by customizable **soul/** files.

Clone this, edit `soul/`, deploy.

## How It Works

```
Device → Omi Backend → Webhook POST → Sandbox Plugin
                                          │
                                    Buffer in Redis
                                          │
                                  Threshold reached?
                                   (10 chunks or 30s)
                                          │
                                  ┌───────────────┐
                                  │  soul/ files   │ ← loaded once
                                  │  + prompts/    │ ← cached prefix
                                  └───────┬───────┘
                                          │
                                    LLM Processing
                                   (OpenRouter API)
                                          │
                                 Confidence Filtering
                              ┌───────────┼───────────┐
                              │           │           │
                           Tasks      Memories    Notification
                          (≥ 0.6)     (≥ 0.5)      (≥ 0.8)
                              │           │           │
                         Omi API     Omi API    Webhook Response
```

## Quick Start

```bash
# 1. Clone and configure
cp .env.template .env
# Edit .env with your OpenRouter key and Omi credentials

# 2. Edit soul/ files to define your app's behavior

# 3. Run
docker compose up -d

# 4. Test
curl http://localhost:8080/health
```

## Soul — Define Your App

The `soul/` directory is the heart of your plugin. Each file controls a specific aspect of how the LLM processes conversations. Edit them to build any kind of Omi plugin.

```
soul/
├── identity.md        # App name and purpose
├── tasks.md           # Task extraction rules
├── memories.md        # Memory extraction rules
├── notifications.md   # Notification rules
├── personality.md     # Tone and style
└── custom_rules.md    # Domain-specific logic
```

### Files

| File | Purpose | Example |
|------|---------|---------|
| `identity.md` | Name and purpose of your app | "MeetingBot captures action items from meetings" |
| `tasks.md` | When to create tasks, what to ignore | "Capture direct commitments, ignore hypotheticals" |
| `memories.md` | What user facts to remember | "Store preferences and goals, ignore temporary states" |
| `notifications.md` | When to actively notify (high bar) | "Only notify for time-sensitive deadlines" |
| `personality.md` | Tone and style of messages | "Concise, no emojis, action-oriented" |
| `custom_rules.md` | Domain-specific logic and edge cases | "If user corrects themselves, discard the item" |

### Example: Fitness Coach App

**soul/identity.md**
```
FitTracker — captures workout commitments, health goals, and dietary
preferences from conversations.
```

**soul/tasks.md**
```
Capture: workout plans ("I'll run 5k tomorrow"), health appointments
("dentist on Friday"), meal prep commitments
Ignore: past workouts, hypothetical fitness goals without commitment
```

**soul/memories.md**
```
Capture: dietary restrictions, fitness goals, personal records,
preferred workout times, injuries
Ignore: daily mood, temporary soreness
```

**soul/notifications.md**
```
Notify: upcoming workout commitments, health appointment reminders
Don't notify: general fitness fact storage
```

**soul/personality.md**
```
Tone: motivational but brief
Style: "Leg day tomorrow at 6am" not "Don't forget your workout!"
```

**soul/custom_rules.md**
```
- Track specific numbers (weights, distances, times) in task descriptions
- If user mentions pain or injury, tag memory with "health-alert"
```

### Example: Sales Assistant App

**soul/identity.md**
```
DealBot — captures follow-up tasks, client preferences, and deal
context from sales conversations.
```

**soul/tasks.md**
```
Capture: follow-ups ("I'll send the quote"), meeting scheduling,
proposal deadlines, client requests
Ignore: internal team chatter, general industry discussion
```

**soul/memories.md**
```
Capture: client company details, budget ranges, decision makers,
pain points, product preferences, competitor mentions
Ignore: small talk, weather, sports
```

**soul/notifications.md**
```
Notify: follow-up deadlines within 24 hours, client meeting reminders
Don't notify: general CRM data capture
```

**soul/personality.md**
```
Tone: professional, brief
Style: "Send quote to Acme by 3pm" not "Remember to follow up"
```

**soul/custom_rules.md**
```
- Always include client/company name in task descriptions
- Tag memories with client name when identifiable
- Flag competitor mentions with "competitive-intel" tag
```

## Prompt Caching

The system prompt (`soul/` + `prompts/system.md`) is assembled **once at startup** and stays **identical across all API calls**, enabling automatic prompt caching:

- **DeepSeek V3**: Automatic prefix caching — 90% input cost reduction on cache hits
- **Gemini**: Automatic context caching — 90% discount on cached tokens
- **Anthropic models**: Uses `cache_control` breakpoints via OpenRouter

```
┌──────────────────────────────────────┐
│         SYSTEM MESSAGE (cached)      │
│                                      │
│  prompts/system.md                   │  ← framework template
│    ├── soul/identity.md              │  ← your content injected
│    ├── soul/tasks.md                 │
│    ├── soul/memories.md              │
│    ├── soul/notifications.md         │
│    ├── soul/personality.md           │
│    ├── soul/custom_rules.md          │
│    ├── output format (JSON schema)   │
│    └── confidence scoring rules      │
│                                      │
│  cache_control: ephemeral            │  ← Anthropic cache breakpoint
└──────────────────────────────────────┘
┌──────────────────────────────────────┐
│         USER MESSAGE (dynamic)       │
│                                      │
│  User: I need to call the dentist    │  ← only this changes per call
│  Other: Sure, I'll remind you        │
└──────────────────────────────────────┘
```

Only the transcript changes per call, so every request after the first hits the cache.

**Cost with caching** (DeepSeek V3):

| | Without cache | With cache |
|---|---|---|
| Input cost/1M tokens | $0.28 | $0.028 |
| Per call (~800 tokens) | $0.0002 | $0.00002 |
| 1000 calls/day, 30 days | $6.00 | $0.60 |

## Project Structure

```
plugins/sandbox/
├── soul/                       # ← YOUR APP'S BEHAVIOR (edit these)
│   ├── identity.md             #    App name and purpose
│   ├── tasks.md                #    Task extraction rules
│   ├── memories.md             #    Memory extraction rules
│   ├── notifications.md        #    Notification rules
│   ├── personality.md          #    Tone and style
│   └── custom_rules.md         #    Domain-specific logic
├── prompts/
│   └── system.md               #    Framework template (don't edit)
├── app/
│   ├── main.py                 #    FastAPI: /health + /webhook/transcript
│   ├── config.py               #    Env vars + prompt assembly
│   ├── models.py               #    Pydantic request/response schemas
│   ├── buffer.py               #    Redis-based segment accumulation
│   ├── processor.py            #    LLM call + confidence filtering
│   └── omi_client.py           #    Omi Integration API (tasks + memories)
├── Dockerfile
├── docker-compose.yml
├── .env.template
└── requirements.txt
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | Yes | — | Your OpenRouter API key |
| `LLM_MODEL` | No | `deepseek/deepseek-chat-v3-0324` | Model to use |
| `OMI_APP_ID` | Yes | — | Your registered Omi app ID |
| `OMI_APP_API_KEY` | Yes | — | API key for your Omi app |
| `OMI_API_URL` | No | `https://api.omi.me` | Omi API base URL |
| `CHUNK_THRESHOLD` | No | `10` | Segments before processing |
| `TIME_THRESHOLD_SECONDS` | No | `30` | Max seconds before processing |
| `NOTIFY_CONFIDENCE_THRESHOLD` | No | `0.8` | Min confidence for notifications |
| `TASK_CONFIDENCE_THRESHOLD` | No | `0.6` | Min confidence for tasks |
| `MEMORY_CONFIDENCE_THRESHOLD` | No | `0.5` | Min confidence for memories |
| `SYSTEM_PROMPT` | No | (built from soul/) | Full override — bypasses soul/ files |

### Confidence Thresholds

The LLM assigns a confidence score (0.0–1.0) to every extracted item:

| Score | Meaning | Example |
|-------|---------|---------|
| **1.0** | Explicitly stated | "I need to call mom tomorrow" |
| **0.7** | Strongly implied | "We should probably schedule that" |
| **0.4** | Weakly implied | "Maybe I will look into it" |
| **0.1** | Speculative | Vague or uncertain mentions |

```bash
# Strict — only explicit statements
NOTIFY_CONFIDENCE_THRESHOLD=0.9
TASK_CONFIDENCE_THRESHOLD=0.8
MEMORY_CONFIDENCE_THRESHOLD=0.7

# Relaxed — catch more, accept some noise
NOTIFY_CONFIDENCE_THRESHOLD=0.6
TASK_CONFIDENCE_THRESHOLD=0.4
MEMORY_CONFIDENCE_THRESHOLD=0.3
```

## Omi Integration

### Register Your App

```json
{
  "external_integration": {
    "triggers_on": "transcript_processed",
    "webhook_url": "https://your-domain.com/webhook/transcript",
    "actions": [
      { "action": "create_conversation" },
      { "action": "create_facts" }
    ]
  }
}
```

### Generate an API Key

```
POST /v1/apps/{app_id}/keys
```

Save the returned `secret` as `OMI_APP_API_KEY`.

### What Gets Created

- **Tasks** → `POST /v2/integrations/{app_id}/user/action-items`
- **Memories** → `POST /v2/integrations/{app_id}/user/memories`
- **Notifications** → Returned in webhook response for Omi to display

## API

### `GET /health`

Returns `{"status": "ok"}`

### `POST /webhook/transcript`

**Request:**
```json
{
  "session_id": "user-uid",
  "segments": [
    {
      "text": "I need to call the dentist tomorrow",
      "is_user": true,
      "speaker": "SPEAKER_00",
      "start": 0.0,
      "end": 2.5
    }
  ]
}
```

**Response (notification triggered):**
```json
{
  "message": "Call dentist tomorrow",
  "notification": {
    "prompt": "Call dentist tomorrow",
    "params": ["user_name"]
  }
}
```

**Response (buffering or no action):**
```json
{}
```

### LLM Output Format

```json
{
  "should_notify": true,
  "notify_confidence": 0.9,
  "message": "Call dentist tomorrow",
  "tasks": [
    { "description": "Call the dentist", "due_at": "2026-02-16T09:00:00", "confidence": 0.95 }
  ],
  "memories": [
    { "content": "Prefers morning appointments", "tags": ["preferences"], "confidence": 0.7 }
  ]
}
```

## Deploy on Coolify

1. Create a new service in Coolify
2. Point the build path to your cloned `plugins/sandbox/`
3. Select **Docker Compose** as the build method
4. Add environment variables from `.env`
5. Deploy — Coolify handles SSL and routing

## LLM Models

Any [OpenRouter model](https://openrouter.ai/models) works:

```bash
LLM_MODEL=deepseek/deepseek-chat-v3-0324    # Cheapest, good quality
LLM_MODEL=google/gemini-2.0-flash-001       # Fast, good caching
LLM_MODEL=openai/gpt-4.1-nano               # Cheapest OpenAI
LLM_MODEL=anthropic/claude-3.5-haiku         # Best quality/cost ratio
```

## Cost Estimate

With DeepSeek V3 + prompt caching:

| Usage | LLM Cost | Linode $5 VPS | Total |
|-------|----------|---------------|-------|
| 100 users, 10/day | ~$0.60/mo | $5 | **~$6/mo** |
| 500 users, 10/day | ~$3/mo | $5 | **~$8/mo** |
| 1000 users, 10/day | ~$6/mo | $12 | **~$18/mo** |
