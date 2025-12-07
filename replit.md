# Overview

Omi is an open-source AI wearable platform that captures and transcribes conversations, providing automatic summaries, action items, and intelligent assistance. The system consists of a Flutter mobile app, Python FastAPI backend, hardware firmware, documentation site, and several companion projects including omiGlass (smart glasses), Zeke Core (personal AI assistant), and an MCP (Model Context Protocol) server.

The platform enables users to:
- Connect wearable devices (Omi hardware or omiGlass) to capture audio
- Automatically transcribe conversations using Deepgram
- Generate structured memories and insights using OpenAI
- Manage action items and tasks
- Interact via chat interface with RAG-powered context retrieval
- Extend functionality through a plugin/app system
- Sync data across devices with optional private cloud storage

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Mobile Application (Flutter)
- **Framework**: Flutter with multi-flavor support (dev/prod)
- **State Management**: SharedPreferences for local data, Firebase Firestore for cloud sync
- **Bluetooth**: BLE communication with wearable devices for audio streaming
- **Audio Processing**: Real-time transcription via Deepgram WebSocket connection
- **Local AI**: Vector similarity search for memory retrieval using embeddings
- **Authentication**: Firebase Auth with custom token support
- **Platforms**: iOS, Android, macOS, Web, Windows

## Backend (FastAPI + Modal)
- **API Framework**: FastAPI with modular router architecture
- **Deployment**: Modal.com for serverless functions, supports traditional hosting
- **Authentication**: Firebase Admin SDK for token verification, custom API keys for MCP/developer access
- **Database**: Google Firestore for primary data storage
- **Caching**: Redis (Upstash recommended) for performance optimization
- **Storage**: Google Cloud Storage for audio recordings and media files
- **Real-time Processing**: Webhook-based event system for conversation processing
- **Background Jobs**: Modal scheduled functions for notifications and batch processing

## Data Architecture

### Firestore Collections
- **users**: User profiles, settings, subscriptions, data protection preferences
- **conversations**: Audio transcripts with speaker diarization, timestamps, geolocation
- **memories**: Structured insights extracted from conversations (encrypted when enhanced protection enabled)
- **messages**: Chat history between user and AI assistant
- **action_items**: Tasks and to-dos derived from conversations
- **plugins_data**: Community apps/plugins metadata and reviews
- **mcp_api_keys**: API keys for Model Context Protocol access
- **dev_api_keys**: Developer API keys for external integrations

### Subcollections Pattern
- **users/{uid}/fcm_tokens**: Push notification tokens per device
- **users/{uid}/hourly_usage**: Time-series usage statistics
- **plugins_data/{app_id}/reviews**: User reviews for apps

### Data Protection Levels
- **Standard**: Plain text storage in Firestore
- **Enhanced**: AES encryption for sensitive fields (conversations, memories, chat) using user-specific keys

## AI/ML Pipeline

### Speech-to-Text
- **Primary**: Deepgram WebSocket API with speaker diarization
- **Features**: Multi-language support, real-time streaming, speaker identification
- **Speaker Profiles**: SpeechBrain ECAPA-VOXCELEB embeddings for speaker recognition

### Memory Generation
- **Model**: OpenAI GPT (configurable model selection)
- **Process**: 
  1. Transcription → structured overview (title, emoji, category, action items)
  2. Context-aware extraction distinguishing interesting facts from routine events
  3. Trend detection across multiple memories
- **Optimization**: DSPy ReAct framework for prompt tuning (memories-tuner tool)

### Vector Search
- **Database**: Pinecone for semantic memory search
- **Embeddings**: OpenAI text-embedding-ada-002
- **Use Cases**: RAG-based chat responses, similar memory retrieval

### Voice Activity Detection
- **Model**: Pyannote.audio VAD pipeline
- **Purpose**: Audio chunking optimization, silence removal

## Plugin/App System
- **Capabilities**: Memories processing, chat integration, external triggers
- **Triggers**: `audio_bytes`, `memory_created`, `conversation_finished`
- **Integration**: Webhook-based with OAuth support for authenticated apps
- **Discovery**: JSON-based app registry with community ratings

## Authentication & Authorization
- **Primary Auth**: Firebase Authentication (email, phone, OAuth providers)
- **API Keys**: 
  - MCP keys for Model Context Protocol servers
  - Dev keys for external integrations
  - Bearer token validation with Redis caching
- **Encryption**: Per-user AES keys derived from Firebase UID for enhanced protection

## Notification System
- **Push**: Firebase Cloud Messaging (FCM) with multi-device support
- **Scheduling**: Cron-based daily summaries and proactive notifications
- **Channels**: In-app, push notifications, SMS (via Twilio)

## Hardware Integration
- **Omi Device**: ESP32-based BLE wearable with continuous audio capture
- **omiGlass**: Smart glasses with Seeed XIAO ESP32 S3, Ollama integration
- **OTA Updates**: Nordic DFU protocol for firmware updates
- **Communication**: Custom BLE protocol for audio streaming

## Companion Projects

### Zeke Core
- **Purpose**: Personal AI assistant with proactive task management
- **Architecture**: Event-driven skill orchestrator (not multi-agent)
- **Skills**: Memory curation, task planning, research, communications, location awareness
- **Integration**: Bridges Limitless API to Omi (temporary, removable)
- **Stack**: FastAPI, PostgreSQL + pgvector, Celery + Redis workers
- **Location Tracking**: Overland iOS app integration for GPS context

#### Distributed Task Queue (Celery + Redis)
- **Architecture**: Decoupled API gateway with background workers for heavy processing
- **Process Recycling**: Workers restart after 50 tasks (`worker_max_tasks_per_child`) to eliminate memory leaks
- **Task Queues**: zeke_default, zeke_processing, zeke_curation, zeke_notifications
- **Scheduled Tasks**: Due task checks (15m), notification flush (15m), curation (4x daily)
- **Tasks**: process_conversation, send_scheduled_reminder, check_due_tasks, run_memory_curation

#### Semantic Cache (Performance Optimization)
- **Purpose**: Cache LLM responses for semantically similar queries
- **Similarity Threshold**: 0.90 cosine similarity using OpenAI embeddings
- **Performance**: ~40x faster cache hits (~80ms vs ~3500ms), ~99% cost reduction
- **TTL**: Responses expire after 1 hour by default
- **Endpoints**: GET /chat/cache/metrics, DELETE /chat/cache

#### Overland GPS Integration
- **App**: Overland iOS (https://overland.p3k.app/) sends GPS data via HTTP POST
- **Endpoint**: POST `/api/overland/` receives location batches in GeoJSON format
- **Data Captured**: Latitude, longitude, altitude, speed, motion state (walking/driving/stationary), battery level
- **Storage**: PostgreSQL `locations` table with automatic retention (90 days default)
- **Context Injection**: Location context automatically added to AI prompts for location-aware responses
- **Dashboard**: Location widget displays current motion, status, speed, and battery
- **Security**: Bearer token authentication via `OVERLAND_API_KEY` environment variable (required in production)
- **API Endpoints**:
  - `GET /api/overland/context` - Current location context summary
  - `GET /api/overland/current` - Most recent location point
  - `GET /api/overland/recent` - Recent location history
  - `GET /api/overland/summary` - Motion summary (time spent walking, driving, etc.)

#### Memory Curation System
- **Purpose**: Automatically classify, tag, enrich, and clean memories to keep ZEKE's knowledge base accurate
- **Service**: `MemoryCurationService` in `zeke-core/app/services/curation_service.py`
- **Classification**: Uses keyword-based detection (fast) with LLM fallback (OpenAI) for accuracy
- **Topics**: personal_profile, relationships, commitments, health, travel, finance, hobbies, work, preferences, facts, other
- **Quality Control**: Detects too-short content, vague language, contradictions, invalid data
- **Curation Status**: pending, clean, needs_review, flagged, deleted
- **Confidence Gating**: High confidence (>0.85) auto-updates; low confidence flags for human review
- **Storage**: Memories table with curation fields (primary_topic, curation_status, curation_notes, enriched_context, curation_confidence, last_curated)
- **Run Tracking**: `memory_curation_runs` table logs each curation job (processed, updated, flagged, deleted counts)
- **Background Jobs**: Celery cron runs curation 4x daily (0:30, 6:30, 12:30, 18:30) when Redis available
- **Dashboard**: Curation page shows stats, progress bar, topic breakdown, review queue with approve/reject actions
- **API Endpoints**:
  - `GET /api/curation/stats/{user_id}` - Curation statistics and topic breakdown
  - `GET /api/curation/flagged/{user_id}` - Memories needing review
  - `POST /api/curation/run` - Trigger manual curation run
  - `POST /api/curation/approve/{memory_id}` - Mark memory as clean
  - `POST /api/curation/reject/{memory_id}` - Reject/delete memory
  - `POST /api/curation/batch-action` - Bulk approve/reject operations

### MCP Server
- **Protocol**: Model Context Protocol for AI tool integration
- **Package**: Published to PyPI as `mcp-server-omi`
- **Tools**: get_memories, create_memory, edit_memory, delete_memory, get_conversations
- **Deployment**: Docker container, uv/uvx for local development
- **Authentication**: User-specific API keys with token-based auth

## Development Tools
- **Documentation**: Mintlify for docs site
- **Memory Tuning**: Streamlit app with DSPy optimization
- **Testing**: Flutter flavors for dev/staging environments
- **Code Style**: Black formatter (120 char line length) for Python

# External Dependencies

## Core Services
- **Firebase**: Authentication, Firestore database, Cloud Messaging, Admin SDK
- **Google Cloud Platform**: Cloud Storage (audio files), Service Account authentication
- **Modal.com**: Serverless deployment platform for backend functions
- **Upstash Redis**: Managed Redis for caching and rate limiting

## AI/ML APIs
- **OpenAI**: GPT-4/GPT-3.5 for text generation, text-embedding-ada-002 for embeddings
- **Deepgram**: Real-time speech-to-text with speaker diarization
- **Pinecone**: Vector database for semantic search
- **Hume AI**: Emotional analysis (optional integration)

## Third-Party Integrations
- **Twilio**: SMS notifications and webhooks
- **Langfuse**: LLM observability and prompt optimization
- **Google APIs**: OAuth, Calendar, Gmail (for task integrations)
- **Ollama**: Local LLM hosting for omiGlass offline features

## Development & Deployment
- **PyPI**: Package distribution for MCP server
- **npm**: Documentation and build tools
- **GitHub Actions**: CI/CD workflows (implied by .github structure)
- **Expo**: React Native tooling for omiGlass app

## Python Libraries
- **FastAPI**: Web framework with async support
- **Pydantic**: Data validation and settings management
- **SQLAlchemy**: ORM for Zeke Core PostgreSQL
- **arq**: Async job queue with Redis backend
- **SpeechBrain**: Speaker recognition models
- **Pyannote**: Audio processing and VAD
- **DSPy**: LLM prompt optimization framework

## Flutter Dependencies
- **Firebase packages**: Authentication, Firestore, messaging
- **BLE**: Bluetooth communication with wearables
- **Audio**: Recording, playback, file system access
- **Platform-specific**: iOS/Android native integrations