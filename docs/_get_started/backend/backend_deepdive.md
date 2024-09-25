---
layout: default
title: Backend Deep Dive
parent: Backend
nav_order: 2
---

# Omi Backend Deep Dive 🧠🎙️

## Table of Contents

1. [Understanding the Omi Ecosystem](#understanding-the-omi-ecosystem-)
2. [System Architecture](#system-architecture)
3. [The Flow of Information: From User Interaction to Memory](#the-flow-of-information-from-user-interaction-to-memory-)
4. [The Core Components: A Closer Look](#the-core-components-a-closer-look-)
    - [database/memories.py: The Memory Guardian](#1-databasememoriespy-the-memory-guardian-)
    - [database/vector_db.py: The Embedding Expert](#2-databasevector_dbpy-the-embedding-expert-)
    - [utils/llm.py: The AI Maestro](#3-utilsllmpy-the-ai-maestro-)
    - [utils/other/storage.py: The Cloud Storage Manager](#4-utilsotherstoragepy-the-cloud-storage-manager-)
    - [database/redis_db.py: The Data Speedster](#5-databaseredis_dbpy-the-data-speedster-)
    - [routers/transcribe.py: The Real-Time Transcription Engine](#6-routerstranscribepy-the-real-time-transcription-engine-)
5. [Other Important Components](#other-important-components-)
6. [Contributing](#contributing-)
7. [Support](#support-)

Welcome to the Omi backend! This document provides a comprehensive overview of Omi's architecture and code, guiding you through its key components, functionalities, and how it all works together to
power a unique and intelligent AI assistant experience.

## Understanding the Omi Ecosystem 🗺️

Omi is a multimodal AI assistant designed to understand and interact with users in a way that's both intelligent and human-centered. The backend plays a crucial role in this by:

- **Processing and analyzing data:** Converting audio to text, extracting meaning, and creating structured information from user interactions.
- **Storing and managing memories:** Building a rich knowledge base of user experiences that Omi can draw upon to provide context and insights.
- **Facilitating intelligent conversations:** Understanding user requests, retrieving relevant information, and generating personalized responses.
- **Integrating with external services:** Extending Omi's capabilities and connecting it to other tools and platforms.

This deep dive will walk you through the **core elements** of Omi's backend, providing a clear roadmap for developers and enthusiasts alike to understand its inner workings.

## System Architecture

![Backend Detailed Overview](/images/backend.png)

You can click on the image to view it in full size and zoom in for more detail.

## The Flow of Information: From User Interaction to Memory 🌊

Let's trace the journey of a typical interaction with Omi, focusing on how audio recordings are transformed into lasting memories:

### A. User Initiates a Recording 🎤

1. **Recording Audio:** The user starts a recording session using the Omi app, capturing a conversation or their thoughts.

### B. Real-Time Transcription with Deepgram 🎧

2. **WebSocket Connection:** The Omi app establishes a real-time connection with the backend using WebSockets (at the `/listen` endpoint in `routers/transcribe.py`).
3. **Streaming Audio:** The app streams audio data continuously through the WebSocket to the backend.
4. **Deepgram Processing:** The backend forwards the audio data to the Deepgram API for real-time speech-to-text conversion.
5. **Transcription Results:** As Deepgram transcribes the audio, it sends results back to the backend.
6. **Live Feedback:** The backend relays these transcription results back to the Omi app, allowing for live transcription display as the user is speaking.

### C. Creating a Lasting Memory 💾

7. **API Request to `/v1/memories`:** When the conversation session ends, the Omi app sends a POST request to the `/v1/memories` endpoint in `routers/memories.py`.
8. **Data Formatting:** The request includes information about the start and end time of the recording, the language, optional geolocation data, and the transcribed text segments from Deepgram.
9. **Memory Creation (`routers/memories.py`):** The `create_memory` function in this file receives the request and performs basic validation on the data.
10. **Processing the Memory (`utils/memories/process_memory.py`):**
    - The `create_memory` function delegates the core memory processing logic to the `process_memory` function. This function is where the real magic happens!
    - **Structure Extraction:** OpenAI's powerful large language model (LLM) is used to analyze the transcript and extract key information, creating a structured representation of the memory. This
      includes:
        - `title`: A short, descriptive title.
        - `overview`: A concise summary of the main points.
        - `category`: A relevant category to organize memories (work, personal, etc.).
        - `action_items`: Any tasks or to-dos mentioned.
        - `events`: Events that might need to be added to a calendar.
    - **Embedding Generation:** The LLM is also used to create a vector embedding of the memory, capturing its semantic meaning for later retrieval.
    - **Plugin Execution:** If the user has enabled any plugins, relevant plugins are run to enrich the memory with additional insights, external actions, or other context-specific information.
    - **Storage in Firestore:** The fully processed memory, including the transcript, structured data, plugin results, and other metadata, is stored in Firebase Firestore (a NoSQL database) for
      persistence.
    - **Embedding Storage in Pinecone:** The memory embedding is sent to Pinecone, a vector database, to enable fast and efficient similarity searches later.

### D. Enhancing the Memory (Optional)

11. **Post-Processing:** The user can optionally trigger post-processing of the memory to improve the quality of the transcript. This involves:
    - Sending the audio to a more accurate transcription service (like WhisperX through a FAL.ai function).
    - Updating the memory in Firestore with the new transcript.
    - Re-generating the embedding to reflect the updated content.

## The Core Components: A Closer Look 🔎

Now that you understand the general flow, let's dive deeper into the key modules and services that power Omi's backend.

### 1. `database/memories.py`: The Memory Guardian 🛡️

This module is responsible for managing the interaction with Firebase Firestore, Omi's main database for storing memories and related data.

**Key Functions:**

- `upsert_memory`: Creates or updates a memory document in Firestore, ensuring efficient storage and handling of updates.
- `get_memory`: Retrieves a specific memory by its ID.
- `get_memories`: Fetches a list of memories for a user, allowing for filtering, pagination, and optional inclusion of discarded memories.
- **OpenGlass Functions:** Handles the storage and retrieval of photos associated with memories created through OpenGlass.
- **Post-Processing Functions:** Manages the storage of data related to transcript post-processing (status, model used, alternative transcription segments).

**Firestore Structure:**

Each memory is stored as a document in Firestore with the following fields:

```python
class Memory(BaseModel):
    id: str  # Unique ID
    created_at: datetime  # Creation timestamp
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    source: Optional[MemorySource]
    language: Optional[str]

    structured: Structured  # Contains extracted title, overview, action items, etc. 
    transcript_segments: List[TranscriptSegment]
    geolocation: Optional[Geolocation]
    photos: List[MemoryPhoto]

    plugins_results: List[PluginResult]
    external_data: Optional[Dict]
    postprocessing: Optional[MemoryPostProcessing]

    discarded: bool
    deleted: bool 
```

### 2. `database/vector_db.py`: The Embedding Expert 🌲

This module manages the interaction with Pinecone, a vector database used to store and query memory embeddings.

**Key Functions:**

- `upsert_vector`: Adds or updates a memory embedding in Pinecone.
- `upsert_vectors`: Efficiently adds or updates multiple embeddings.
- `query_vectors`: Performs similarity search to find memories relevant to a user query.
- `delete_vector`: Removes a memory embedding.

**Pinecone's Role:**

Pinecone's specialized vector search capabilities are essential for:

- **Contextual Retrieval:** Finding memories that are semantically related to a user's request, even if they don't share exact keywords.
- **Efficient Search:** Quickly retrieving relevant memories from a large collection.
- **Scalability:** Handling the growing number of memory embeddings as the user creates more memories.

### 3. `utils/llm.py`: The AI Maestro 🧠

This module is where the power of OpenAI's LLMs is harnessed for a wide range of tasks. It's the core of Omi's intelligence!

**Key Functionalities:**

- **Memory Processing:**
    - Determines if a conversation should be discarded.
    - Extracts structured information from transcripts (title, overview, categories, etc.).
    - Runs plugins on memory data.
    - Handles post-processing of transcripts to improve accuracy.
- **OpenGlass and External Integration Processing:**
    - Creates structured summaries from photos and descriptions (OpenGlass).
    - Processes data from external sources (like ScreenPipe) to generate memories.
- **Chat and Retrieval:**
    - Generates initial chat messages.
    - Analyzes chat conversations to determine if context is needed.
    - Extracts relevant topics and dates from chat history.
    - Retrieves and summarizes relevant memory content for chat responses.
- **Emotional Processing:**
    - Analyzes conversation transcripts for user emotions.
    - Generates emotionally aware responses based on context and user facts.
- **Fact Extraction:** Identifies and extracts new facts about the user from conversation transcripts.

**OpenAI Integration:**

- `llm.py` leverages OpenAI's `ChatOpenAI` model (specifically `gpt-4o` in the code, but you can use other models) for language understanding, generation, and reasoning.
- It uses OpenAI's `OpenAIEmbeddings` model to generate vector embeddings for memories and user queries.

**Why `llm.py` is Essential:**

- **The Brain of Omi:** This module enables Omi's core AI capabilities, including natural language understanding, content generation, and context-aware interactions.
- **Memory Enhancement:** It enriches raw data by extracting meaning and creating structured information.
- **Personalized Responses:** It helps Omi provide responses that are tailored to individual users, incorporating their unique facts, memories, and even emotional states.
- **Extensibility:** The plugin system and integration with external services make Omi highly versatile.

### 4. `utils/other/storage.py`: The Cloud Storage Manager ☁️

This module handles interactions with Google Cloud Storage (GCS), specifically for managing user speech profiles.

**Key Functions:**

- **`upload_profile_audio(file_path: str, uid: str)`:**
    - Uploads a user's speech profile audio recording to the GCS bucket specified by the `BUCKET_SPEECH_PROFILES` environment variable.
    - Organizes audio files within the bucket using the user's ID (`uid`).
    - Returns the public URL of the uploaded file.
- **`get_profile_audio_if_exists(uid: str) -> str`:**
    - Checks if a speech profile already exists for a given user ID in the GCS bucket.
    - Downloads the speech profile audio to a local temporary file if it exists and returns the file path.
    - Returns `None` if the profile does not exist.

**Usage:**

- The `upload_profile_audio` function is called when a user uploads a new speech profile recording through the `/v3/upload-audio` endpoint (defined in `routers/speech_profile.py`).
- The `get_profile_audio_if_exists` function is used to retrieve a user's speech profile when needed, for example, during speaker identification in real-time transcription or post-processing.

### 5. `database/redis_db.py`: The Data Speedster 🚀

Redis is an in-memory data store known for its speed and efficiency. The `database/redis_db.py` module handles Omi's interactions with Redis, which is primarily used for caching, managing user
settings, and storing user speech profiles.

**Data Stored and Retrieved from Redis:**

- **User Speech Profiles:**
    - **Storage:** When a user uploads a speech profile, the raw audio data, along with its duration, is stored in Redis.
    - **Retrieval:** During real-time transcription or post-processing, the user's speech profile is retrieved from Redis to aid in speaker identification.
- **Enabled Plugins:**
    - **Storage:** A set of plugin IDs is stored for each user, representing the plugins they have enabled.
    - **Retrieval:** When processing a memory or handling a chat request, the backend checks Redis to see which plugins are enabled for the user.
- **Plugin Reviews:**
    - **Storage:** Reviews for each plugin (score, review text, date) are stored in Redis, organized by plugin ID and user ID.
    - **Retrieval:** When displaying plugin information, the backend retrieves reviews from Redis.
- **Cached User Names:**
    - **Storage:** User names are cached in Redis to avoid repeated lookups from Firebase.
    - **Retrieval:** The backend first checks Redis for a user's name before querying Firestore, improving performance.

**Key Functions:**

- `store_user_speech_profile`, `get_user_speech_profile`: For storing and retrieving speech profiles.
- `store_user_speech_profile_duration`, `get_user_speech_profile_duration`: For managing speech profile durations.
- `enable_plugin`, `disable_plugin`, `get_enabled_plugins`: For handling plugin enable/disable states.
- `get_plugin_reviews`: Retrieves reviews for a plugin.
- `cache_user_name`, `get_cached_user_name`: For caching user names.
  **Why Redis is Important:**

- **Performance:** Caching data in Redis significantly improves the backend's speed, as frequently accessed data can be retrieved from memory very quickly.
- **User Data Management:** Redis provides a flexible and efficient way to manage user-specific data, such as plugin preferences and speech profiles.
- **Real-time Features:** The low-latency nature of Redis makes it ideal for supporting real-time features like live transcription and instant plugin interactions.
- **Scalability:** As the number of users grows, Redis helps maintain performance by reducing the load on primary databases.

### 6. `routers/transcribe.py`: The Real-Time Transcription Engine 🎙️

This module is the powerhouse behind Omi's real-time transcription capabilities, allowing the app to convert spoken audio into text as the user is speaking. It leverages WebSockets for bidirectional
communication with the Omi app and Deepgram's speech-to-text API for accurate and efficient transcription.

#### 1. WebSocket Communication: The Lifeline of Real-Time Interactions 🔌

- **`/listen` Endpoint:** The Omi app initiates a WebSocket connection with the backend at the `/listen` endpoint, which is defined in the `websocket_endpoint` function of `routers/transcribe.py`.
- **Bidirectional Communication:** WebSockets enable a two-way communication channel, allowing:
    - The Omi app to stream audio data to the backend continuously.
    - The backend to send back transcribed text segments as they become available from Deepgram.
- **Real-Time Feedback:** This constant back-and-forth ensures that users see their words being transcribed in real-time, creating a more interactive and engaging experience.

#### 2. Deepgram Integration: Converting Speech to Text with Precision 🎧➡️📝

- **`process_audio_dg` Function:** The `process_audio_dg` function (found in `utils/stt/streaming.py`) manages the interaction with Deepgram.
- **Deepgram API:** The audio chunks streamed from the Omi app are sent to the Deepgram API for transcription. Deepgram's sophisticated speech recognition models process the audio and return text
  results.
- **Options Configuration:** The `process_audio_dg` function configures various Deepgram options, including:
    - `punctuate`: Automatically adds punctuation to the transcribed text.
    - `no_delay`: Minimizes latency for real-time feedback.
    - `language`: Sets the language for transcription.
    - `interim_results`: (Set to `False` in the code) Controls whether to send interim (partial) transcription results or only final results.
    - `diarize`: Enables speaker diarization (identifying different speakers in the audio).
    - `encoding`, `sample_rate`: Sets audio encoding and sample rate for compatibility with Deepgram.

#### 3. Transcription Flow: A Step-by-Step Breakdown 🌊

1. **App Streams Audio:** The Omi app captures audio from the user's device and continuously sends chunks of audio data through the WebSocket to the backend's `/listen` endpoint.
2. **Backend Receives and Forwards:** The backend's `websocket_endpoint` function receives the audio chunks and immediately forwards them to Deepgram using the `process_audio_dg` function.
3. **Deepgram Processes:** Deepgram's speech recognition models transcribe the audio data in real-time.
4. **Results Sent Back:** Deepgram sends the transcribed text segments back to the backend as they become available.
5. **Backend Relays to App:** The backend immediately sends these transcription results back to the Omi app over the WebSocket connection.
6. **App Displays Transcript:** The Omi app updates the user interface with the newly transcribed text, providing instant feedback.

#### 4. Key Considerations

- **Speaker Identification:** The code uses Deepgram's speaker diarization feature to identify different speakers in the audio. This information is included in the transcription results, allowing the
  app to display who said what.
- **User Speech Profile Integration:** If a user has uploaded a speech profile, the backend can use this information (retrieved from Redis or Google Cloud Storage) to improve the accuracy of speaker
  identification.
- **Latency Management:** Real-time transcription requires careful attention to latency to ensure a seamless user experience. The `no_delay` option in Deepgram and the efficient handling of data in
  the backend are essential for minimizing delays.
- **Error Handling:** The code includes error handling mechanisms to gracefully handle any issues that may occur during the WebSocket connection or Deepgram transcription process.

#### 5. Example Code Snippet (Simplified):

```python
from fastapi import APIRouter, WebSocket

# ... other imports ...

router = APIRouter()


@router.websocket("/listen")
async def websocket_endpoint(websocket: WebSocket, uid: str, language: str = 'en', ...):
    await websocket.accept()  # Accept the WebSocket connection

    # Start Deepgram transcription
    transcript_socket = await process_audio_dg(uid, websocket, language, ...)

    # Receive and process audio chunks from the app
    async for data in websocket.iter_bytes():
        transcript_socket.send(data)

        # ... other logic for speaker identification, error handling, etc. 
```

## Other Important Components 🧩

- **`routers/transcribe.py`:** Manages real-time audio transcription using Deepgram, sending the transcribed text back to the Omi app for display.
- **`routers/workflow.py`, `routers/screenpipe.py`:** Define API endpoints for external integrations to trigger memory creation.

We hope this deep dive into the Omi backend has provided valuable insights into its architecture, codebase, and the powerful technologies that drive its intelligent and human-centered interactions.

## Contributing 🤝

We welcome contributions from the open source community! Whether it's improving documentation, adding new features, or reporting bugs, your input is valuable. Check out
our [Contribution Guide](https://docs.omi.me/developer/Contribution/) for more information.

## Support 🆘

If you're stuck, have questions, or just want to chat about Omi:

- **GitHub Issues:** 🐛 For bug reports and feature requests
- **Community Forum:** 💬 Join our [community forum](https://discord.gg/ZutWMTJnwA) for discussions and questions
- **Documentation:** 📚 Check out our [full documentation](https://docs.omi.me/) for in-depth guides

Happy coding! 💻 If you have any questions or need further assistance, don't hesitate to reach out to our community.
