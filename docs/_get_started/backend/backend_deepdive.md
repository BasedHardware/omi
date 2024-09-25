---
layout: default
title: Backend Deep Dive
parent: Backend
nav_order: 2
---

# Omi Backend Deep Dive

## Table of Contents

1. [Understanding the Omi Ecosystem](#understanding-the-omi-ecosystem)
2. [System Architecture](#system-architecture)
3. [The Flow of Information: From User Interaction to Memory](#the-flow-of-information-from-user-interaction-to-memory)
4. [The Core Components: A Closer Look](#the-core-components-a-closer-look)
   - [database/memories.py: Memory Management](#1-databasememoriespy-memory-management)
   - [database/vector_db.py: Vector Database Management](#2-databasevector_dbpy-vector-database-management)
   - [utils/llm.py: Language Model Utilities](#3-utilsllmpy-language-model-utilities)
   - [utils/other/storage.py: Cloud Storage Manager](#4-utilsotherstoragepy-cloud-storage-manager)
   - [database/redis_db.py: Redis Database Operations](#5-databaseredis_dbpy-redis-database-operations)
   - [routers/transcribe.py: Real-Time Transcription Engine](#6-routerstranscribepy-real-time-transcription-engine)
   - [database/processing_memories.py: Memory Processing Pipeline](#7-databaseprocessing_memoriespy-memory-processing-pipeline)
5. [Modal Serverless Deployment](#modal-serverless-deployment)
6. [Error Handling and Logging](#error-handling-and-logging)
7. [Performance Optimization](#performance-optimization)
8. [Security Considerations](#security-considerations)
9. [External Integrations and Workflows](#external-integrations-and-workflows)
10. [Contributing](#contributing)
11. [Support](#support)

Welcome to the Omi Backend Deep Dive. This document provides a comprehensive overview of Omi's architecture and code, guiding you through its key components, functionalities, and how it all works together to power a unique and intelligent AI assistant experience.

## Understanding the Omi Ecosystem

Omi is a multimodal AI assistant designed to understand and interact with users in a way that is both intelligent and human-centered. The backend plays a crucial role in this by:

- **Processing and analyzing data:** Converting audio to text, extracting meaning, and creating structured information from user interactions.
- **Storing and managing memories:** Building a rich knowledge base of user experiences that Omi can draw upon to provide context and insights.
- **Facilitating intelligent conversations:** Understanding user requests, retrieving relevant information, and generating personalized responses.
- **Integrating with external services:** Extending Omi's capabilities and connecting it to other tools and platforms.

This document will walk you through the core elements of Omi's backend, providing a clear roadmap for developers and enthusiasts to understand its inner workings.

## System Architecture

![Backend Detailed Overview](/images/backend.png)

*You can click on the image to view it in full size and zoom in for more detail.*

### Component Interactions

Here's a detailed look at how key components interact:

1. **Real-time Transcription Flow:**

   ```mermaid
   sequenceDiagram
       participant User
       participant OmiApp
       participant WebSocket
       participant TranscriptionServices
       participant MemoryProcessing

       User->>OmiApp: Start recording
       OmiApp->>WebSocket: Establish connection
       loop Audio Streaming
           OmiApp->>WebSocket: Stream audio chunks
           WebSocket->>TranscriptionServices: Forward audio
           TranscriptionServices->>WebSocket: Return transcripts
           WebSocket->>OmiApp: Send live transcripts
       end
       User->>OmiApp: Stop recording
       OmiApp->>MemoryProcessing: Process transcribed memory
   ```

2. **Memory Creation and Embedding Flow:**

   ```mermaid
   sequenceDiagram
       participant MemoryProcessing
       participant OpenAI
       participant Firestore
       participant Pinecone

       MemoryProcessing->>OpenAI: Extract structured data
       OpenAI->>MemoryProcessing: Return structured info
       MemoryProcessing->>OpenAI: Generate embedding
       OpenAI->>MemoryProcessing: Return embedding vector
       MemoryProcessing->>Firestore: Store memory data
       MemoryProcessing->>Pinecone: Store embedding vector
   ```

### Modal Serverless Deployment

Omi's backend leverages Modal for serverless deployment, allowing for efficient scaling and management of computational resources. Key components of the Modal setup include:

- **App Configuration:** The `modal_app` is configured in `main.py` with specific secrets and environment variables.
- **Image Definition:** A custom Docker image is defined with necessary dependencies and configurations.
- **API Function:** The main FastAPI app is wrapped in a Modal function, allowing for easy deployment and scaling.
- **Cron Job:** A notifications cron job is set up to run every minute using Modal's scheduling capabilities.

```python
modal_app = App(
    name='backend',
    secrets=[Secret.from_name("gcp-credentials"), Secret.from_name('envs')],
)
image = (
    Image.debian_slim()
    .apt_install('ffmpeg', 'git', 'unzip')
    .pip_install_from_requirements('requirements.txt')
)

@modal_app.function(
    image=image,
    keep_warm=2,
    memory=(512, 1024),
    cpu=2,
    allow_concurrent_inputs=10,
    timeout=60 * 10,
)
@asgi_app()
def api():
    return app

@modal_app.function(image=image, schedule=Cron('* * * * *'))
async def notifications_cronjob():
    await start_cron_job()
```

## The Flow of Information: From User Interaction to Memory

Let's trace the journey of a typical interaction with Omi, focusing on how audio recordings are transformed into lasting memories:

### A. User Initiates a Recording

1. **Recording Audio:** The user starts a recording session using the Omi app, capturing a conversation or their thoughts.

### B. Real-Time Transcription with Multiple Services

2. **WebSocket Connection:** The Omi app establishes a real-time connection with the backend using WebSockets (at the `/listen` endpoint in `routers/transcribe.py`).
3. **Streaming Audio:** The app streams audio data continuously through the WebSocket to the backend.
4. **Multiple Transcription Services:** The backend forwards the audio data to multiple transcription services, including Deepgram, Soniox, and Speechmatics, for real-time speech-to-text conversion.
5. **Transcription Results:** As the services transcribe the audio, they send results back to the backend.
6. **Live Feedback:** The backend relays these transcription results back to the Omi app, allowing for live transcription display as the user is speaking.

### C. Creating a Processing Memory

7. **API Request to `/v1/processing-memories`:** When the conversation session ends, the Omi app sends a POST request to the `/v1/processing-memories` endpoint in `routers/processing_memories.py`.
8. **Data Formatting:** The request includes information about the start and end time of the recording, the language, optional geolocation data, and the transcribed text segments from the transcription services.
9. **Processing Memory Creation:** The `create_processing_memory` function receives the request and creates a new processing memory document.

### D. Processing the Memory

10. **Memory Processing (`utils/memories/process_memory.py`):**
    - The processing memory is analyzed and enriched with additional information.
    - **Structure Extraction:** OpenAI's large language model (LLM) is used to analyze the transcript and extract key information, creating a structured representation of the memory.
    - **Embedding Generation:** The LLM generates a vector embedding of the memory, capturing its semantic meaning for later retrieval.
    - **Plugin Execution:** If the user has enabled any plugins, relevant plugins are run to enrich the memory with additional insights, external actions, or other context-specific information.
    - **Emotional Analysis:** If enabled, the audio is analyzed for emotional content using Hume AI.

### E. Finalizing the Memory

11. **Storage in Firestore:** The fully processed memory, including the transcript, structured data, plugin results, emotional analysis, and other metadata, is stored in Firebase Firestore for persistence.
12. **Embedding Storage in Pinecone:** The memory embedding is sent to Pinecone, a vector database, to enable fast and efficient similarity searches later.

### F. Post-Processing (Optional)

13. **Enhanced Transcription:** The user can optionally trigger post-processing of the memory to improve the quality of the transcript using more accurate models like WhisperX through FAL.ai.
14. **Updating the Memory:** The memory in Firestore is updated with the new transcript, and the embedding is regenerated to reflect the updated content.

## The Core Components: A Closer Look

Now that you understand the general flow, let's dive deeper into the key modules and services that power Omi's backend.

### 1. `database/memories.py`: Memory Management

This module handles memory storage and management features:

- **Post-Processing:** Functions handle the storage and retrieval of post-processing data, including status updates and alternative transcription segments.
- **OpenGlass Integration:** Functions for storing and retrieving photos associated with memories created through OpenGlass.
- **Visibility Management:** Functions manage the visibility of memories, allowing for public and private memories.

**Key Functions:**

```python
def upsert_memory(uid: str, memory_data: dict):
    # Creates or updates a memory document in Firestore

def get_memory_photos(uid: str, memory_id: str):
    # Retrieves photos associated with a memory (OpenGlass integration)

def set_memory_visibility(uid: str, memory_id: str, visibility: str):
    # Sets the visibility status of a memory (public/private)

def set_postprocessing_status(uid: str, memory_id: str, status: PostProcessingStatus, fail_reason: str = None, model: PostProcessingModel = PostProcessingModel.fal_whisperx):
    # Updates the post-processing status of a memory

def store_model_emotion_predictions_result(uid: str, memory_id: str, model_name: str, predictions: List[hume.HumeJobModelPredictionResponseModel]):
    # Stores emotional analysis results for a memory
```

### 2. `database/vector_db.py`: Vector Database Management

This module manages the vector embeddings using the Pinecone client:

- **Namespace Usage:** Vectors are stored in a namespace, allowing for better organization of embeddings.
- **Metadata Filtering:** The `query_vectors` function supports advanced filtering based on metadata, including date ranges.

```python
def query_vectors(query: str, uid: str, starts_at: int = None, ends_at: int = None, k: int = 5) -> List[str]:
    filter_data = {'uid': uid}
    if starts_at is not None:
        filter_data['created_at'] = {'$gte': starts_at, '$lte': ends_at}

    xq = embeddings.embed_query(query)
    xc = index.query(vector=xq, top_k=k, include_metadata=False, filter=filter_data, namespace="ns1")
    return [item['id'].replace(f'{uid}-', '') for item in xc['matches']]
```

### 3. `utils/llm.py`: Language Model Utilities

This module harnesses the power of OpenAI's LLMs for a wide range of tasks:

**Key Functionalities:**

- **Memory Processing:** Analyzes transcripts, extracts structured information, runs plugins on memory data, and handles post-processing of transcripts.
- **External Integration Processing:** Creates structured summaries from photos and descriptions, processes data from external sources.
- **Chat and Retrieval:** Generates initial chat messages, analyzes chat conversations, extracts relevant topics and dates, retrieves and summarizes relevant memory content.
- **Emotional Processing:** Analyzes conversation transcripts for user emotions, generates emotionally aware responses.
- **Fact Extraction:** Identifies and extracts new facts about the user from conversation transcripts.

### 4. `utils/other/storage.py`: Cloud Storage Manager

This module handles interactions with Google Cloud Storage (GCS), specifically for managing user speech profiles.

**Key Functions:**

```python
def upload_profile_audio(file_path: str, uid: str):
    # Uploads a user's speech profile audio to GCS

def get_profile_audio_if_exists(uid: str) -> str:
    # Retrieves a user's speech profile from GCS if it exists
```

### 5. `database/redis_db.py`: Redis Database Operations

Redis is used for caching, managing user settings, and storing user speech profiles.

**Key Functions:**

```python
def store_user_speech_profile(uid: str, data: List[List[int]]):
    # Stores a user's speech profile in Redis

def get_enabled_plugins(uid: str):
    # Retrieves the list of enabled plugins for a user

def cache_signed_url(blob_path: str, signed_url: str, ttl: int = 60 * 60):
    # Caches a signed URL for cloud storage objects

def add_public_memory(memory_id: str):
    # Marks a memory as public in Redis
```

### 6. `routers/transcribe.py`: Real-Time Transcription Engine

This module manages real-time audio transcription using multiple services.

**Key Features:**

- **Multiple Transcription Services:** Integrates Deepgram, Soniox, and Speechmatics for real-time speech-to-text conversion.
- **WebSocket Communication:** Utilizes WebSockets for real-time data streaming.
- **Speaker Diarization:** Integrates user speech profile for speaker identification.

```python
@router.websocket("/listen")
async def websocket_endpoint(websocket: WebSocket, uid: str, language: str = 'en', ...):
    await websocket.accept()

    # Start multiple transcription services
    transcript_socket_deepgram = await process_audio_dg(uid, websocket, language, ...)
    transcript_socket_soniox = await process_audio_soniox(uid, websocket, language, ...)
    transcript_socket_speechmatics = await process_audio_speechmatics(uid, websocket, language, ...)

    # ... (rest of the function)
```

### 7. `database/processing_memories.py`: Memory Processing Pipeline

This module manages memories that are still in the processing stage.

**Key Functions:**

```python
def upsert_processing_memory(uid: str, processing_memory_data: dict):
    # Creates or updates a processing memory document

def update_processing_memory_segments(uid: str, id: str, segments: List[dict]):
    # Updates the transcript segments of a processing memory

def get_last(uid: str):
    # Retrieves the most recent processing memory for a user
```

## Error Handling and Logging

Omi implements a robust error handling and logging system:

### Global Exception Handler

```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log_error(exc)
    return JSONResponse(
        status_code=500,
        content={"message": "An unexpected error occurred. Our team has been notified."},
    )
```

### Structured Logging

```python
import structlog

logger = structlog.get_logger()

def log_error(exc: Exception, **kwargs):
    logger.error("An error occurred", error=str(exc), traceback=traceback.format_exc(), **kwargs)
```

### Error Monitoring

- **Integration with Monitoring Services:** Integration with error monitoring services (e.g., Sentry) for real-time alerts and error tracking.

## Performance Optimization

Omi employs several strategies to optimize performance:

### Caching

- **Redis Caching:** Redis is used for caching frequently accessed data.
- **Embeddings Caching:** Intelligent caching of embeddings and transcription results to reduce redundant computations.

### Database Optimization

- **Indexed Firestore Queries:** Firestore indexes are carefully designed for common query patterns.
- **Batch Operations:** Batch operations are used for bulk updates to minimize network overhead.

### Asynchronous Processing

- **Background Workers:** Long-running tasks are offloaded to background workers.
- **Async I/O Operations:** Utilizes Python's `asyncio` for non-blocking I/O operations.

### Load Testing and Profiling

- **Regular Load Testing:** Identifies bottlenecks and ensures scalability.
- **Profiling Tools:** Critical paths are profiled to optimize resource usage.

## Security Considerations

Omi takes security seriously to protect user data and system integrity. Key security measures include:

- **Data Encryption:** All data is encrypted at rest and in transit using industry-standard encryption algorithms.
- **Access Control:** Fine-grained access control mechanisms are implemented to ensure only authorized users can access their data.
- **Authentication and Authorization:** Robust authentication and authorization mechanisms are in place to prevent unauthorized access.
- **Input Validation:** All user input is validated and sanitized to prevent injection attacks and other security vulnerabilities.
- **Secure Deployment:** Omi is deployed in a secure environment with strict access controls and network segmentation.

## Contributing

We welcome contributions from the open source community. Whether it's improving documentation, adding new features, or reporting bugs, your input is valuable. Check out our [Contribution Guide](https://docs.omi.me/developer/Contribution/) for more information.

## Support

If you're stuck, have questions, or just want to chat about Omi:

- **GitHub Issues:** For bug reports and feature requests.
- **Community Forum:** Join our [community forum](https://discord.gg/ZutWMTJnwA) for discussions and questions.
- **Documentation:** Check out our [full documentation](https://docs.omi.me/) for in-depth guides.

If you have any questions or need further assistance, please don't hesitate to reach out to our community.
