# Zeke Core Architecture

## Overview

Zeke Core is a personal AI assistant built on top of Omi's open-source wearable platform. It provides intelligent conversation analysis, memory management, task automation, and proactive assistance.

## Design Principles

1. **Omi-First Ingestion** - All audio capture and transcription flows through Omi
2. **Event-Driven Processing** - Async workflows triggered by events, not polling
3. **Unified Orchestration** - Single coordinator with specialized skills, not separate agents
4. **Swappable Bridge** - Limitless sync is temporary; designed for easy removal

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        INGESTION LAYER                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐ │
│  │ Omi Device  │───▶│ Omi Backend │───▶│ Webhook: /omi/event │ │
│  └─────────────┘    └─────────────┘    └─────────────────────┘ │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Limitless Bridge (TEMPORARY - remove when native support)  ││
│  │ Limitless API ──▶ Converter ──▶ Omi external_integration   ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        ZEKE CORE                                 │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   API LAYER (FastAPI)                     │   │
│  │  /chat  /memories  /tasks  /automations  /sms/webhook    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                 SKILL ORCHESTRATOR                        │   │
│  │  Coordinates skills based on intent, manages context      │   │
│  │  Uses finite-state workflow instead of agent chatter      │   │
│  └──────────────────────────────────────────────────────────┘   │
│         │           │           │           │                    │
│         ▼           ▼           ▼           ▼                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ Memory   │ │ Task     │ │ Research │ │ Comms    │            │
│  │ Curator  │ │ Planner  │ │ Scout    │ │ Manager  │            │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘            │
│         │           │           │           │                    │
│         └───────────┴───────────┴───────────┘                    │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   KNOWLEDGE LAYER                         │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────────┐  │   │
│  │  │ Memories   │  │ Contacts   │  │ Conversations      │  │   │
│  │  │ (pgvector) │  │            │  │ (from Omi)         │  │   │
│  │  └────────────┘  └────────────┘  └────────────────────┘  │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────────┐  │   │
│  │  │ Tasks      │  │ Automations│  │ Locations          │  │   │
│  │  └────────────┘  └────────────┘  └────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DELIVERY LAYER                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ SMS/Twilio  │  │ Web UI      │  │ Push Notifications      │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
zeke-core/
├── app/
│   ├── api/              # FastAPI routes
│   │   ├── chat.py       # Chat endpoint
│   │   ├── memories.py   # Memory CRUD
│   │   ├── tasks.py      # Task management
│   │   ├── automations.py# Automation builder
│   │   ├── omi.py        # Omi webhook receiver
│   │   └── sms.py        # Twilio webhook
│   │
│   ├── core/             # Core application logic
│   │   ├── config.py     # Pydantic settings
│   │   ├── database.py   # Database connection
│   │   ├── events.py     # Event bus
│   │   └── orchestrator.py # Skill orchestrator
│   │
│   ├── models/           # Pydantic & SQLAlchemy models
│   │   ├── memory.py
│   │   ├── conversation.py
│   │   ├── task.py
│   │   ├── contact.py
│   │   └── automation.py
│   │
│   ├── services/         # Business logic services
│   │   ├── memory_service.py
│   │   ├── conversation_service.py
│   │   ├── task_service.py
│   │   └── notification_service.py
│   │
│   ├── skills/           # AI skills (replaces agents)
│   │   ├── memory_curator.py
│   │   ├── task_planner.py
│   │   ├── research_scout.py
│   │   └── comms_manager.py
│   │
│   ├── integrations/     # External service integrations
│   │   ├── omi.py        # Omi API client
│   │   ├── openai.py     # OpenAI/LLM client
│   │   ├── twilio.py     # SMS
│   │   ├── calendar.py   # Google Calendar
│   │   ├── weather.py    # Weather API
│   │   └── limitless_bridge.py  # TEMPORARY
│   │
│   └── utils/            # Utilities
│       ├── embeddings.py
│       └── context.py
│
├── dashboard/            # React web dashboard (Vite + TypeScript)
│   ├── src/
│   │   ├── components/   # Reusable UI components
│   │   │   ├── Layout.tsx
│   │   │   └── Sidebar.tsx
│   │   ├── pages/        # Page components
│   │   │   ├── Dashboard.tsx  # Overview with stats
│   │   │   ├── Chat.tsx       # AI chat interface
│   │   │   ├── Memories.tsx   # Memory management
│   │   │   └── Tasks.tsx      # Task management
│   │   ├── lib/
│   │   │   └── api.ts    # API client
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── package.json
│   └── vite.config.ts
│
├── tests/                # Test suite
├── main.py               # FastAPI app entry
├── requirements.txt      # Dependencies
└── ARCHITECTURE.md       # This file
```

## Data Flow

### 1. Conversation Ingestion (from Omi)

```
Omi processes audio → POST /api/omi/conversation → 
  → Store in conversations table
  → Emit "conversation.created" event
  → Memory Curator extracts memories
  → Task Planner extracts action items
  → Store extracted data
```

### 2. Chat Interaction

```
User sends message (SMS/Web) → POST /api/chat →
  → Orchestrator determines intent
  → Loads relevant context (memories, recent conversations)
  → Calls appropriate skill(s)
  → Generates response
  → Stores interaction
  → Returns response
```

### 3. Proactive Notifications

```
Scheduled job runs → Check for triggers →
  → Weather alerts, task reminders, etc.
  → Queue notification
  → Batch and send via SMS (respecting quiet hours)
```

## Database Schema (Postgres + pgvector)

### Core Tables

- `conversations` - Synced from Omi, stores transcripts and metadata
- `memories` - Extracted facts and learnings with embeddings
- `tasks` - Action items and todos
- `contacts` - People mentioned in conversations
- `automations` - User-defined automated workflows
- `chat_history` - Conversation history with Zeke
- `locations` - GPS history for context enrichment

## Skills vs Agents

### Old (Multi-Agent)
- 7 separate agents with their own prompts
- Agents coordinate via message passing
- High token overhead from inter-agent communication
- Complex debugging

### New (Skills)
- Single orchestrator with tool-calling
- Skills are functions, not autonomous agents
- Orchestrator decides which skill(s) to invoke
- Lower token usage, faster responses
- Easier to debug and maintain

## Distributed Task Queue (Celery + Redis)

### Architecture
Zeke uses Celery with Redis for distributed task processing, providing:
- **Process recycling** - Workers restart after 50 tasks to eliminate memory leaks
- **Fault tolerance** - Tasks retry automatically on failure
- **Scalability** - Spawn additional workers as load increases
- **Self-healing** - Process isolation prevents crashes from affecting the API

### Task Queues
- `zeke_default` - General tasks
- `zeke_processing` - Conversation processing
- `zeke_curation` - Memory curation
- `zeke_notifications` - Reminders and alerts

### Scheduled Tasks (Celery Beat)
- Check due tasks: every 15 minutes
- Flush notifications: every 15 minutes (offset by 5 min)
- Memory curation: 4x daily (0:30, 6:30, 12:30, 18:30)

### Worker Configuration
```python
worker_max_tasks_per_child=50  # Restart worker after 50 tasks
task_acks_late=True            # Acknowledge after completion
worker_prefetch_multiplier=1   # Fair task distribution
```

## Semantic Cache (Performance Optimization)

### How It Works
1. Query comes in → Generate embedding via OpenAI
2. Compare against cached embeddings using cosine similarity
3. If similarity > 0.90, return cached response (~40x faster)
4. If miss, generate new response and cache it

### Benefits
- **Latency**: ~80ms cache hit vs ~3500ms full LLM call
- **Cost**: ~99% reduction for repeated queries
- **TTL**: Responses expire after 1 hour by default

### Endpoints
- `GET /chat/cache/metrics` - View hit/miss rates
- `DELETE /chat/cache` - Clear all cached responses

## Limitless Bridge (Temporary)

The bridge runs as a background job that:
1. Polls Limitless API for new lifelogs
2. Converts to Omi's conversation format
3. Pushes to Omi via external_integration endpoint

When native Limitless-to-Omi hardware support arrives:
1. Disable the bridge job
2. Remove limitless_bridge.py
3. Everything else continues unchanged

## Configuration

All config via environment variables (Pydantic Settings):

```
# Database
DATABASE_URL=postgresql://...

# Omi
OMI_API_URL=https://...
OMI_API_KEY=...

# OpenAI
OPENAI_API_KEY=...

# Twilio
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=...
USER_PHONE_NUMBER=...

# Limitless (temporary)
LIMITLESS_API_KEY=...
LIMITLESS_SYNC_ENABLED=true  # Set to false when native support arrives

# Optional
GOOGLE_CALENDAR_CREDENTIALS=...
OPENWEATHERMAP_API_KEY=...
```
