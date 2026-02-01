# Omi Data Flow Documentation

This document describes the data flows for key workflows in the Omi system.

## 1. Conversation Recording & Processing Flow

### Overview
When a user records a conversation, audio flows from the device through the app to the backend, where it's transcribed, processed, and stored.

```mermaid
flowchart TD
    Start([User starts recording]) --> BLE[BLE Audio Stream<br/>Device → App]
    BLE --> WS[WebSocket Connection<br/>/v4/listen]
    WS --> STT[Deepgram STT Service]
    STT -->|Transcript segments| WS
    WS -->|Real-time display| App[Flutter App]
    WS -->|Store segments| FS1[(Firestore<br/>in_progress conversation)]
    
    App -->|User stops recording| POST[POST /v1/conversations]
    POST --> Process[process_conversation]
    
    Process --> Discard{Should discard?}
    Discard -->|Yes| Delete[Delete conversation]
    Discard -->|No| Extract[Extract structure via LLM]
    
    Extract --> Structure[Title, Overview,<br/>Action Items, Events]
    Extract --> Memories[Extract memories]
    
    Structure --> FS2[(Firestore<br/>completed conversation)]
    Memories --> FS3[(Firestore<br/>memories collection)]
    Structure --> PC[(Pinecone<br/>vector embedding)]
    
    FS2 --> Apps[Run enabled apps]
    Apps --> Webhooks[App webhooks]
```

### Detailed Steps

1. **Recording Initiation**
   - User starts recording in Flutter app
   - App connects to device via BLE
   - Audio stream begins

2. **WebSocket Connection**
   - App establishes WebSocket to `/v4/listen`
   - Backend creates "in_progress" conversation in Firestore
   - Audio chunks streamed continuously

3. **Real-time Transcription**
   - Backend forwards audio to Deepgram
   - Transcript segments returned in real-time
   - Segments displayed in app UI
   - Segments stored in Firestore as they arrive

4. **Recording Completion**
   - User stops recording
   - App sends `POST /v1/conversations` with empty body
   - Backend retrieves in-progress conversation

5. **Conversation Processing**
   - `process_conversation()` function called
   - LLM determines if conversation should be discarded
   - If kept, LLM extracts:
     - Title and overview
     - Action items
     - Calendar events
     - Memories (facts about user)

6. **Storage**
   - Conversation stored in Firestore with status "completed"
   - Vector embedding generated and stored in Pinecone
   - Memories stored in separate Firestore collection
   - Action items stored in action_items collection

7. **App Processing**
   - Enabled apps run on conversation data
   - Webhooks triggered for memory creation
   - Real-time transcript webhooks (if configured)

## 2. Chat Query Flow

### Overview
When a user asks a question in chat, the system routes it through LangGraph to determine if context is needed, then retrieves relevant information and generates a response.

```mermaid
flowchart TD
    Start([User asks question]) --> Chat[POST /v2/messages]
    Chat --> Classify[LangGraph Router<br/>requires_context]
    
    Classify -->|No context| Simple[Simple Path]
    Classify -->|Context needed| Agentic[Agentic Path]
    Classify -->|Persona| Persona[Persona Path]
    
    Simple --> LLM1[Direct LLM Response]
    
    Agentic --> Tools[Tool System]
    Tools --> ConvTool[get_conversations_tool]
    Tools --> SearchTool[search_conversations_tool]
    Tools --> MemoryTool[get_memories_tool]
    Tools --> CalendarTool[get_calendar_events_tool]
    Tools --> AppTools[App-specific tools]
    
    ConvTool --> FS[(Firestore)]
    SearchTool --> PC[(Pinecone<br/>Vector Search)]
    MemoryTool --> FS
    CalendarTool --> Google[Google Calendar API]
    AppTools --> External[External APIs]
    
    FS --> Context[Gather Context]
    PC --> Context
    Google --> Context
    External --> Context
    
    Context --> LLM2[LLM with Context]
    LLM2 --> Citations[Add Citations]
    
    Persona --> PersonaLLM[Persona LLM<br/>with app prompt]
    
    LLM1 --> Stream[Stream Response]
    Citations --> Stream
    PersonaLLM --> Stream
    
    Stream --> User([User sees answer])
```

### Detailed Steps

1. **Question Classification**
   - User sends message via `POST /v2/messages`
   - `requires_context()` function analyzes question
   - Routes to one of three paths:
     - **Simple**: General questions, greetings
     - **Agentic**: Questions needing user data
     - **Persona**: Questions for persona apps

2. **Simple Path**
   - Direct LLM call with system prompt
   - No tool calls needed
   - Fast response

3. **Agentic Path**
   - LangGraph ReAct agent activated
   - LLM decides which tools to call
   - Available tools (30+ core tools + dynamic app tools):
     - Conversation retrieval (date range, search)
     - Memory retrieval and search
     - Action item management (get, create, update)
     - Calendar operations (get, create, update, delete)
     - Health tools (Apple Health, Whoop)
     - Integration tools (Gmail, GitHub, Notion, Twitter, Perplexity)
     - File search
     - Notification settings
     - App-specific dynamic tools

4. **Tool Execution**
   - Tools execute in parallel when possible
   - Results gathered into context
   - Vector search in Pinecone for semantic similarity
   - Firestore queries for structured data

5. **Response Generation**
   - LLM receives question + context
   - Generates answer with citations
   - Citations link to source conversations `[1][2]`
   - Response streamed back to app

6. **Persona Path**
   - Uses app's configured `persona_prompt`
   - May have limited tool access
   - Character-consistent responses

## 3. Memory Extraction Flow

### Overview
Memories are extracted from conversations and stored separately for quick access.

```mermaid
flowchart TD
    Conv[Completed Conversation] --> Extract[Extract Memories<br/>via LLM]
    Extract --> Filter[Filter Existing Memories]
    Filter --> New[New Memories Only]
    New --> Validate[Validate Memory Quality]
    Validate --> Store[Store in Firestore<br/>memories collection]
    Store --> Vector[Generate Embedding]
    Vector --> PC[(Pinecone<br/>memory vectors)]
    Store --> Cache[Cache in Redis<br/>if frequently accessed]
```

### Memory Categories

- **Personal**: Facts about the user
- **Health**: Health-related information
- **Work**: Work-related facts
- **Relationships**: Information about people
- **Preferences**: User preferences and likes

## 4. App/Plugin Integration Flow

### Overview
Apps can integrate with Omi through webhooks, chat tools, and prompts.

```mermaid
flowchart TD
    App[Omi App Installed] --> Enable[User Enables App]
    Enable --> Register[Register Webhooks/Tools]
    
    Register --> MemoryHook[Memory Creation Webhook]
    Register --> TranscriptHook[Real-time Transcript Webhook]
    Register --> ChatTool[Chat Tool Registration]
    
    MemoryHook -->|Memory created| Webhook1[POST to app webhook]
    TranscriptHook -->|Live transcript| Webhook2[POST to app webhook]
    ChatTool -->|Tool call| Execute[Execute App Tool]
    
    Webhook1 --> Process1[App processes memory]
    Webhook2 --> Process2[App processes transcript]
    Execute --> Process3[App executes tool]
    
    Process1 --> Response1[App can create memories]
    Process2 --> Response2[App can trigger actions]
    Process3 --> Response3[App returns tool result]
```

### Integration Types

1. **Memory Triggers**
   - Webhook called when memory created
   - App can process and react to new memories
   - Example: Post to Slack when memory created

2. **Real-time Transcript**
   - Webhook receives transcript segments as they arrive
   - App can process live audio data
   - Example: Trigger smart home actions

3. **Chat Tools**
   - App defines custom tools for LangGraph
   - Tools available when app enabled
   - Example: "Create GitHub issue" tool

4. **Prompt-based Apps**
   - No server required
   - Customize chat or memory extraction prompts
   - Example: Fitness coach persona

## 5. Vector Search Flow

### Overview
Semantic search uses vector embeddings to find relevant conversations.

```mermaid
flowchart TD
    Query([User Query]) --> Embed[Generate Embedding<br/>text-embedding-3-large]
    Embed --> Search[Query Pinecone]
    Search --> Results[Top K Results<br/>by similarity]
    Results --> Filter[Filter by Metadata<br/>date, user, etc.]
    Filter --> Retrieve[Retrieve Full Conversations<br/>from Firestore]
    Retrieve --> Context[Use as Context<br/>for LLM]
```

### Vector Search Parameters

- **Top K**: Number of results (typically 5-10)
- **Similarity Threshold**: Minimum similarity score
- **Metadata Filters**: Date range, user ID, etc.
- **Namespace**: Separate namespaces per user

## 6. Developer API Flow

### Overview
External applications can access Omi data via the Developer API.

```mermaid
flowchart TD
    App[External App] --> Auth[Authenticate with<br/>API Key]
    Auth --> Request[API Request<br/>Bearer token]
    Request --> Validate[Validate API Key]
    Validate -->|Valid| Execute[Execute Request]
    Validate -->|Invalid| Error[401 Unauthorized]
    
    Execute --> RateLimit[Check Rate Limits]
    RateLimit -->|Exceeded| RateError[429 Too Many Requests]
    RateLimit -->|OK| Process[Process Request]
    
    Process --> FS[(Firestore)]
    Process --> PC[(Pinecone)]
    
    FS --> Response[Return Data]
    PC --> Response
    Response --> App
```

### API Key Management

- Keys generated in Omi app (Settings → Developer)
- Keys prefixed with `omi_dev_`
- Rate limits: 100/min, 10,000/day
- Keys can be revoked at any time

## Related Documentation

- Architecture: `.cursor/ARCHITECTURE.md`
- API Reference: `.cursor/API_REFERENCE.md`
- Backend Components: `.cursor/BACKEND_COMPONENTS.md`
- Chat System: `docs/doc/developer/backend/chat_system.mdx`
- Storing Conversations: `docs/doc/developer/backend/StoringConversations.mdx`
