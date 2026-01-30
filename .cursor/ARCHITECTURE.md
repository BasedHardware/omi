# Omi System Architecture

This document provides a comprehensive overview of the Omi system architecture to help Cursor agents understand the codebase structure and component relationships.

## System Overview

Omi is a multimodal AI wearable platform that captures conversations, extracts memories, and provides intelligent chat capabilities. The system consists of multiple components working together:

```mermaid
flowchart TB
    subgraph Device["📱 Hardware Layer"]
        OmiDevice[Omi Wearable Device<br/>nRF/ESP32-S3]
        OmiGlass[Omi Glass<br/>ESP32-S3]
    end
    
    subgraph App["📱 Application Layer"]
        FlutterApp[Flutter App<br/>iOS/Android/macOS/Windows]
        WebApp[Next.js Web App]
    end
    
    subgraph Backend["🖥️ Backend Layer"]
        FastAPI[FastAPI Server]
        LangGraph[LangGraph Agentic System]
        STT[Speech-to-Text Services]
    end
    
    subgraph Storage["💾 Storage Layer"]
        Firestore[(Firestore<br/>Conversations & Memories)]
        Pinecone[(Pinecone<br/>Vector Embeddings)]
        Redis[(Redis<br/>Cache & Metadata)]
        GCS[(Google Cloud Storage<br/>Binary Files)]
    end
    
    subgraph External["🌐 External Services"]
        OpenAI[OpenAI LLMs]
        Deepgram[Deepgram STT]
        Integrations[External Integrations<br/>Gmail, Calendar, etc.]
    end
    
    OmiDevice -->|BLE Audio Stream| FlutterApp
    OmiGlass -->|BLE Audio Stream| FlutterApp
    FlutterApp -->|WebSocket| FastAPI
    WebApp -->|REST API| FastAPI
    
    FastAPI --> STT
    STT --> Deepgram
    FastAPI --> LangGraph
    LangGraph --> OpenAI
    
    FastAPI --> Firestore
    FastAPI --> Pinecone
    FastAPI --> Redis
    FastAPI --> GCS
    FastAPI --> Integrations
```

## Component Architecture

### 1. Backend (Python/FastAPI)

**Location**: `backend/`

The backend is organized into clear layers following a strict module hierarchy:

#### Module Hierarchy (lowest to highest)
1. **`database/`** - Database connections and data access
   - `conversations.py` - Firestore conversation CRUD
   - `memories.py` - Memory storage and retrieval
   - `vector_db.py` - Pinecone vector operations
   - `redis_db.py` - Redis caching
   - `action_items.py` - Task management
   
2. **`utils/`** - Utility functions and business logic
   - `llm/` - LLM client configurations and processing
   - `retrieval/` - LangGraph agentic system and RAG
   - `conversations/` - Conversation processing pipeline
   - `stt/` - Speech-to-text utilities
   - `other/` - Storage, webhooks, notifications
   
3. **`routers/`** - API endpoints (FastAPI routers)
   - `transcribe.py` - WebSocket audio streaming
   - `conversations.py` - Conversation management
   - `chat.py` - Chat system with LangGraph
   - `memories.py` - Memory operations
   - `apps.py` - App management
   - `developer.py` - Developer API
   - `mcp.py` - MCP server endpoints
   
4. **`main.py`** - Application entry point

#### Key Backend Patterns

**Import Rules**: 
- All imports at module top level (never in functions)
- Higher-level modules import from lower-level modules
- Never import from `main.py` or routers in utils/database

**Data Flow**:
1. Audio → WebSocket (`/v4/listen`) → STT service → Transcript
2. Transcript → `process_conversation()` → LLM extraction → Firestore + Pinecone
3. Chat query → LangGraph router → Tool calls → Context retrieval → LLM response

**Storage Strategy**:
- **Firestore**: Primary database for conversations, memories, users
- **Pinecone**: Vector embeddings for semantic search
- **Redis**: Caching (speech profiles, enabled apps, user names)
- **GCS**: Binary files (audio, photos, speech profiles)

### 2. Flutter App (Dart)

**Location**: `app/`

**Architecture**:
- **State Management**: Provider pattern
- **Backend Integration**: REST API client + WebSocket for real-time
- **BLE Communication**: Bluetooth Low Energy for device connection
- **Platform Support**: iOS, Android, macOS, Windows

**Key Directories**:
- `lib/backend/` - API client and WebSocket handling
- `lib/services/` - Business logic services
- `lib/providers/` - State management
- `lib/pages/` - UI screens
- `lib/widgets/` - Reusable UI components
- `lib/utils/bluetooth/` - BLE device communication

**Localization**: All user-facing strings use `context.l10n.keyName` (ARB files in `lib/l10n/`)

### 3. Firmware (C/C++)

**Location**: `omi/`, `omiGlass/`

**Platforms**:
- **Omi Device**: nRF chips with Zephyr RTOS
- **Omi Glass**: ESP32-S3

**Key Features**:
- BLE services for audio streaming
- Audio codecs: Opus (default), PCM, Mu-law
- Battery service and device info service

**BLE Protocol**: See `docs/doc/developer/Protocol.mdx`

### 4. Web (Next.js/TypeScript)

**Location**: `web/`

**Components**:
- `web/frontend/` - Main web application
- `web/app/` - Additional web services
- `web/personas-open-source/` - AI personas platform

**Tech Stack**:
- Next.js 14+ with App Router
- TypeScript
- Tailwind CSS
- Radix UI / Shadcn/ui
- Firebase Auth & Firestore

### 5. Plugins/Apps

**Location**: `plugins/`

**Types**:
- **Python plugins** (`plugins/example/`) - FastAPI-based integrations
- **JavaScript plugins** (`plugins/apps-js/`) - Node.js integrations
- **Prompt-based apps** - No server required, just prompts

**Capabilities**:
- Memory triggers (webhook on memory creation)
- Real-time transcript processing
- Chat tools (custom tools for LangGraph)
- Audio streaming (raw audio processing)

### 6. SDKs

**Location**: `sdks/`

- **Python SDK** (`sdks/python/`) - For building integrations
- **Swift SDK** (`sdks/swift/`) - Native iOS integration
- **React Native SDK** (`sdks/react-native/`) - Cross-platform mobile

### 7. MCP Server

**Location**: `mcp/`

Model Context Protocol server enabling AI assistants (like Claude) to interact with Omi data.

## Data Flow Examples

### Conversation Recording Flow

```mermaid
sequenceDiagram
    participant User
    participant App as Flutter App
    participant WS as WebSocket /v4/listen
    participant STT as Deepgram STT
    participant Backend as FastAPI Backend
    participant LLM as OpenAI
    participant FS as Firestore
    participant PC as Pinecone
    
    User->>App: Start recording
    App->>WS: Connect WebSocket
    App->>WS: Stream audio chunks
    WS->>STT: Forward audio
    STT-->>WS: Transcript segments
    WS-->>App: Display transcript
    App->>WS: End recording
    WS->>Backend: POST /v1/conversations
    Backend->>LLM: Extract structure
    LLM-->>Backend: Title, overview, action items
    Backend->>FS: Store conversation
    Backend->>PC: Store embedding
    Backend->>LLM: Extract memories
    LLM-->>Backend: User facts
    Backend->>FS: Store memories
```

### Chat Query Flow

```mermaid
sequenceDiagram
    participant User
    participant App as Flutter App
    participant Chat as Chat Router
    participant Router as LangGraph Router
    participant Tools as Tool System
    participant FS as Firestore
    participant PC as Pinecone
    participant LLM as OpenAI
    
    User->>App: Ask question
    App->>Chat: POST /v2/messages
    Chat->>Router: Classify question
    Router->>Router: requires_context()?
    
    alt No Context Needed
        Router->>LLM: Direct response
        LLM-->>Chat: Answer
    else Context Needed
        Router->>Tools: Call relevant tools
        Tools->>FS: Get conversations
        Tools->>PC: Vector search
        Tools->>FS: Get memories
        Tools-->>Router: Context data
        Router->>LLM: Question + Context
        LLM-->>Chat: Answer with citations
    end
    
    Chat-->>App: Stream response
```

## Key Design Patterns

### 1. Module Hierarchy
Strict import hierarchy prevents circular dependencies:
- Database → Utils → Routers → Main

### 2. Memory Management
Large objects (byte arrays, large dicts) are freed immediately after use with `del` or `.clear()`

### 3. Error Handling
- FastAPI exception handlers for consistent error responses
- Graceful degradation when optional services (Redis) unavailable

### 4. Caching Strategy
- Redis for frequently accessed metadata
- GCS for binary files
- Firestore for primary data

### 5. Real-time Processing
- WebSockets for bidirectional audio streaming
- Server-Sent Events (SSE) for MCP server
- Streaming responses for chat

## External Dependencies

### Required Services
- **Firebase**: Authentication, Firestore database
- **OpenAI**: LLM models for chat and extraction
- **Deepgram**: Primary STT service
- **Pinecone**: Vector database
- **Redis**: Caching (optional but recommended)

### Optional Services
- **Soniox/Speechmatics**: Alternative STT services
- **Google Calendar**: Calendar integration
- **Gmail**: Email integration
- **Whoop**: Health data
- **Notion**: Note-taking integration
- **GitHub**: Code repository integration

## Documentation References

- Backend Deep Dive: `docs/doc/developer/backend/backend_deepdive.mdx`
- Chat System: `docs/doc/developer/backend/chat_system.mdx`
- Storing Conversations: `docs/doc/developer/backend/StoringConversations.mdx`
- App Setup: `docs/doc/developer/AppSetup.mdx`
- Protocol: `docs/doc/developer/Protocol.mdx`
- API Overview: `docs/doc/developer/api/overview.mdx`
- Plugin Development: `docs/doc/developer/apps/Introduction.mdx`
- MCP: `docs/doc/developer/MCP.mdx`

## Related Files

- `.cursor/API_REFERENCE.md` - API endpoint reference
- `.cursor/DATA_FLOW.md` - Detailed data flow diagrams
- `.cursor/BACKEND_COMPONENTS.md` - Backend module reference
- `.cursor/FLUTTER_COMPONENTS.md` - Flutter app structure
- `.cursor/FIRMWARE_COMPONENTS.md` - Firmware architecture
