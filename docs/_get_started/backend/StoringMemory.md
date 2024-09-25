---
layout: default
title: Memory Storage
parent: Backend
nav_order: 3
---

# 📚 Guide to Omi's Memory Storage Process

This document provides an in-depth look at how Omi stores and manages memory objects, a crucial component of its intelligent AI assistant capabilities.

## 🔄 Overview of the Memory Storage Process

1. Memory object creation and initial processing
2. Conversion of memory object to a structured dictionary
3. Data organization into specific fields
4. Storage in Firebase Firestore
5. Vector embedding generation and storage in Pinecone
6. Optional post-processing and updates

![Backend Memory Storage](/images/memorystore.png)

## 🧠 Detailed Steps in Memory Storage

### 1. 📥 Memory Object Creation and Initial Processing

The journey of a memory begins with its creation, typically triggered by a user interaction such as a conversation or an OpenGlass capture.

```python
# In utils/memories/process_memory.py
async def process_memory(uid: str, processing_memory_id: str):
    # Retrieve the processing memory
    processing_memory = get_processing_memory_by_id(uid, processing_memory_id)
    
    # Extract structured data using OpenAI's LLM
    structured_data = await extract_structured_data(processing_memory.transcript)
    
    # Generate initial embedding
    embedding = generate_memory_embedding(processing_memory)
    
    # Create the memory object
    memory_data = {
        "id": str(uuid.uuid4()),
        "created_at": processing_memory.created_at,
        "transcript_segments": processing_memory.transcript_segments,
        "structured": structured_data,
        # ... other memory fields
    }
    
    # Store the memory and its embedding
    upsert_memory(uid, memory_data)
    upsert_vector(uid, memory_data, embedding)
    
    # Clean up the processing memory
    delete_processing_memory(uid, processing_memory_id)
```

### 2. 🔄 Conversion to Structured Dictionary

The memory object is converted into a structured Python dictionary. This step is crucial as it prepares the data for storage in Firestore, which uses a JSON-like format.

### 3. 📊 Detailed Data Fields

The memory dictionary contains the following key fields:

| Field | Description | Example |
|-------|-------------|---------|
| `id` | Unique identifier for the memory | `"550e8400-e29b-41d4-a716-446655440000"` |
| `created_at` | Timestamp of memory creation | `datetime(2023, 4, 1, 12, 0, 0)` |
| `started_at` | Timestamp when the associated event started | `datetime(2023, 4, 1, 11, 55, 0)` |
| `finished_at` | Timestamp when the associated event ended | `datetime(2023, 4, 1, 12, 5, 0)` |
| `source` | Origin of the memory | `"conversation"`, `"openglass"`, `"workflow"` |
| `language` | Language code of the conversation | `"en-US"` |
| `structured` | Dictionary of extracted structured information | (see below) |
| `transcript_segments` | List of transcript segments | (see below) |
| `geolocation` | Location data (if available) | `{"latitude": 37.7749, "longitude": -122.4194}` |
| `plugins_results` | Results from any plugins run on the memory | `[{"plugin_id": "weather", "data": {...}}]` |
| `external_data` | Additional data from external integrations | `{"source": "calendar", "event_id": "123"}` |
| `postprocessing` | Information about post-processing status | `{"status": "completed", "model": "fal_whisperx"}` |
| `discarded` | Boolean indicating if the memory is low-quality | `false` |
| `deleted` | Boolean indicating if the memory has been deleted | `false` |
| `visibility` | Visibility setting of the memory | `"private"` |

#### 📋 Structured Information

The `structured` field contains key information extracted from the memory:

```python
structured = {
    "title": "Team Meeting Discussion on Q2 Goals",
    "overview": "Discussed Q2 goals, focusing on product launch and market expansion.",
    "emoji": "🚀",
    "category": "work",
    "action_items": [
        "Finalize product features by April 15",
        "Schedule market research presentation for next week"
    ],
    "events": [
        {
            "title": "Q2 Goals Follow-up",
            "start_time": "2023-04-08T14:00:00",
            "end_time": "2023-04-08T15:00:00"
        }
    ]
}
```

#### 🗣️ Transcript Segments

Each segment in `transcript_segments` includes detailed information about the speech:

```python
transcript_segments = [
    {
        "speaker": "SPEAKER_00",
        "start": 0.0,
        "end": 5.2,
        "text": "Good morning, team. Let's discuss our Q2 goals.",
        "is_user": True,
        "person_id": None
    },
    {
        "speaker": "SPEAKER_01",
        "start": 5.5,
        "end": 10.8,
        "text": "Sounds good. I think we should focus on the product launch.",
        "is_user": False,
        "person_id": "colleague123"
    }
    # ... more segments
]
```

#### 🔄 Postprocessing Information

The `postprocessing` field contains information about any additional processing:

```python
postprocessing = {
    "status": "completed",  # Options: "not_started", "in_progress", "completed", "failed"
    "model": "fal_whisperx",
    "fail_reason": None  # Contains error message if status is "failed"
}
```

### 4. 💾 Storage in Firebase Firestore

The `upsert_memory` function in `database/memories.py` handles the storage of the memory in Firestore:

```python
def upsert_memory(uid: str, memory_data: dict):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_data['id'])
    memory_ref.set(memory_data, merge=True)
```

#### 📁 Firestore Structure

The memories are stored in a nested structure within Firestore:

```
Users Collection
└── User Document (uid)
    └── memories Collection
        ├── Memory Document 1 (memory_id)
        ├── Memory Document 2 (memory_id)
        └── ...
```

This structure allows for efficient querying and management of user-specific memory data.

### 5. 🧠 Vector Embedding Storage

Along with storing the memory in Firestore, we generate and store a vector embedding of the memory in Pinecone:

```python
def upsert_vector(uid: str, memory: Memory, vector: List[float]):
    index.upsert(vectors=[{
        "id": f'{uid}-{memory.id}',
        "values": vector,
        'metadata': {
            'uid': uid,
            'memory_id': memory.id,
            'created_at': memory.created_at.timestamp(),
        }
    }], namespace="ns1")
```

This vector embedding allows for semantic search and similarity matching of memories.

### 6. 🔄 Optional Post-Processing and Updates

After initial storage, memories can undergo additional processing:

1. **Transcript Enhancement:** Using more accurate models like WhisperX for improved transcription.
2. **Emotional Analysis:** Processing with Hume AI to extract emotional context.
3. **Additional Plugin Processing:** Running newly enabled plugins on existing memories.

After post-processing, the memory is updated in both Firestore and Pinecone to reflect the new information.

## 🔍 Querying and Retrieving Memories

Memories can be retrieved using various methods:

1. **Direct Lookup:** Using the memory ID to fetch from Firestore.
2. **Semantic Search:** Using vector embeddings in Pinecone to find similar memories.
3. **Filtered Queries:** Using Firestore queries to filter memories by date, category, etc.

Example of a semantic search:

```python
def query_vectors(query: str, uid: str, k: int = 5) -> List[str]:
    xq = embeddings.embed_query(query)
    results = index.query(vector=xq, top_k=k, namespace="ns1", filter={"uid": uid})
    return [item['id'].split('-')[1] for item in results['matches']]
```

## 🔒 Security and Privacy Considerations

- All memory data is associated with a specific user ID for data isolation.
- Firestore security rules ensure that users can only access their own memories.
- Sensitive information in memories (e.g., personal identifiers) should be handled with care.

## 🚀 Performance Optimization

- Use of Firestore indexes for frequently accessed query patterns.
- Caching of frequently accessed memories in Redis for faster retrieval.
- Batch operations for inserting or updating multiple memories at once.

## 🔄 Continuous Improvement

The memory storage process is continually refined to improve:

- Accuracy of structured data extraction
- Efficiency of vector embedding generation
- Integration with new data sources and plugins

By following this comprehensive memory storage process, Omi ensures that user interactions are accurately captured, enriched, and made available for intelligent retrieval and analysis.
