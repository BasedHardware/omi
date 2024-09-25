---
layout: default
title: Memory Embeddings
parent: Backend
nav_order: 5
---

# 🧠 Guide to Memory Embedding Process in Omi

This document provides an in-depth look at how Omi creates, stores, and utilizes embeddings for memories, a crucial component of its intelligent retrieval and analysis capabilities.

## 🔄 Process Overview

1. Memory processing triggers embedding creation
2. Structured data is extracted and prepared from the memory
3. OpenAI API generates the embedding vector
4. Metadata is created for the embedding
5. Embedding vector and metadata are stored in Pinecone
6. Embeddings are used for semantic search and memory retrieval

![Embeddings](/images/embeddings.png)

## 📊 Detailed Steps in Memory Embedding

### 1. Memory Processing Triggers Embedding Creation

The embedding process is initiated in `utils/memories/process_memory.py` under two main scenarios:

a) When a new memory is created
b) When an existing memory is reprocessed (e.g., after post-processing)

```python
# In utils/memories/process_memory.py
async def process_memory(uid: str, processing_memory_id: str):
    # Retrieve the processing memory
    processing_memory = get_processing_memory_by_id(uid, processing_memory_id)
    
    # Extract structured data
    structured_data = await extract_structured_data(processing_memory.transcript)
    
    # Generate embedding
    embedding = generate_memory_embedding(processing_memory, structured_data)
    
    # Create the memory object
    memory_data = create_memory_object(processing_memory, structured_data)
    
    # Store the memory and its embedding
    upsert_memory(uid, memory_data)
    upsert_vector(uid, memory_data, embedding)
```

### 2. Extract and Prepare Structured Data

The `extract_structured_data` function in `utils/llm.py` uses OpenAI's language model to extract key information from the memory transcript:

```python
# In utils/llm.py
async def extract_structured_data(transcript: str) -> dict:
    prompt = f"Extract key information from this transcript:\n\n{transcript}\n\nProvide a structured output with title, overview, emoji, category, action items, and events."
    response = await openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that extracts structured information from text."},
            {"role": "user", "content": prompt}
        ]
    )
    return json.loads(response.choices[0].message.content)
```

#### Structured Data Fields

| Field | Description | Example |
|-------|-------------|---------|
| `title` | Concise title of the memory | "Team Meeting on Q2 Goals" |
| `overview` | Brief summary of the memory content | "Discussed product launch and market expansion strategies for Q2" |
| `emoji` | Representative emoji for the memory | "🚀" |
| `category` | General category of the memory | "work" |
| `action_items` | List of tasks or follow-ups | ["Finalize product features", "Schedule market research"] |
| `events` | List of calendar events mentioned | [{"title": "Q2 Review", "start_time": "2023-07-01T14:00:00"}] |

### 3. Generate Embedding with OpenAI API

The `generate_memory_embedding` function in `utils/llm.py` creates the embedding:

```python
# In utils/llm.py
def generate_memory_embedding(memory: Memory, structured_data: dict) -> List[float]:
    # Combine relevant memory data for embedding
    embedding_text = f"{memory.transcript}\n\nTitle: {structured_data['title']}\nOverview: {structured_data['overview']}\nCategory: {structured_data['category']}"
    
    # Generate embedding using OpenAI's API
    response = openai.Embedding.create(
        input=embedding_text,
        model="text-embedding-3-large"
    )
    return response['data'][0]['embedding']
```

**Note:** We use the `text-embedding-3-large` model for its superior performance in capturing semantic meaning.

### 4. Create Metadata

Metadata is crucial for efficient filtering and retrieval of embeddings. The `upsert_vector` function in `database/vector_db.py` prepares this metadata:

```python
# In database/vector_db.py
def upsert_vector(uid: str, memory: Memory, vector: List[float]):
    metadata = {
        'uid': uid,
        'memory_id': memory.id,
        'created_at': memory.created_at.timestamp(),
        'category': memory.structured['category'],
        'source': memory.source
    }
    # ... (continue with Pinecone upsert)
```

### 5. Store in Pinecone

The embedding vector and metadata are stored in Pinecone, a vector database optimized for similarity search:

```python
# In database/vector_db.py
def upsert_vector(uid: str, memory: Memory, vector: List[float]):
    # ... (metadata creation)
    index.upsert(vectors=[{
        "id": f'{uid}-{memory.id}',
        "values": vector,
        'metadata': metadata
    }], namespace="ns1")
```

**Important:** We use a namespace (`"ns1"`) in Pinecone to logically separate vectors, allowing for more efficient querying and management.

## 🔍 Utilizing Embeddings for Memory Retrieval

### Semantic Search

The `query_vectors` function in `database/vector_db.py` performs semantic search using the embeddings:

```python
# In database/vector_db.py
def query_vectors(query: str, uid: str, k: int = 5) -> List[str]:
    # Generate embedding for the query
    query_embedding = embeddings.embed_query(query)
    
    # Prepare filter
    filter_data = {'uid': uid}
    if starts_at is not None:
        filter_data['created_at'] = {'$gte': starts_at, '$lte': ends_at}
    
    # Perform the query
    results = index.query(
        vector=query_embedding,
        top_k=k,
        namespace="ns1",
        filter=filter_data
    )
    
    # Extract and return memory IDs
    return [item['id'].split('-')[1] for item in results['matches']]
```

This function allows for:
- Semantic similarity search based on the query
- Filtering by user ID to ensure data isolation
- Optional date range filtering
- Returning the top-k most similar memories

## 🔍 Practical Examples of Embedding Usage

### 1. Semantic Search for Relevant Memories

```python
def find_relevant_memories(user_query: str, uid: str, k: int = 5):
    query_embedding = generate_memory_embedding(user_query)
    relevant_memory_ids = query_vectors(query_embedding, uid, k=k)
    return get_memories_by_id(uid, relevant_memory_ids)
```

This function allows the retrieval of memories semantically similar to a user's query, enhancing the contextual understanding in conversations.

### 2. Clustering Similar Memories

```python
from sklearn.cluster import KMeans

def cluster_user_memories(uid: str, n_clusters: int = 5):
    memories = get_all_user_memories(uid)
    embeddings = [memory.embedding for memory in memories]
    kmeans = KMeans(n_clusters=n_clusters)
    clusters = kmeans.fit_predict(embeddings)
    return list(zip(memories, clusters))
```

This function groups similar memories together, which can be used for generating summaries or identifying trends in user experiences.

### 3. Memory Deduplication

```python
def find_duplicate_memories(uid: str, similarity_threshold: float = 0.95):
    memories = get_all_user_memories(uid)
    duplicates = []
    for i, mem1 in enumerate(memories):
        for j, mem2 in enumerate(memories[i+1:]):
            similarity = cosine_similarity(mem1.embedding, mem2.embedding)
            if similarity > similarity_threshold:
                duplicates.append((mem1, mem2))
    return duplicates
```

This function identifies potentially duplicate memories, helping to maintain a clean and non-redundant memory store.

## 🚀 Performance Optimization for Embeddings

### 1. Batch Processing

For improved efficiency when dealing with multiple memories:

```python
def batch_upsert_vectors(uid: str, memories: List[Memory], vectors: List[List[float]]):
    batch_size = 100  # Adjust based on Pinecone's recommendations
    for i in range(0, len(memories), batch_size):
        batch_memories = memories[i:i+batch_size]
        batch_vectors = vectors[i:i+batch_size]
        
        index.upsert(
            vectors=[{
                "id": f'{uid}-{memory.id}',
                "values": vector,
                'metadata': create_metadata(uid, memory)
            } for memory, vector in zip(batch_memories, batch_vectors)],
            namespace="ns1"
        )
```

### 2. Caching Frequently Accessed Embeddings

Implement a caching layer for frequently accessed embeddings:

```python
import redis
from functools import lru_cache

redis_client = redis.Redis(host='localhost', port=6379, db=0)

@lru_cache(maxsize=1000)
def get_cached_embedding(memory_id: str):
    cached = redis_client.get(f"embedding:{memory_id}")
    if cached:
        return json.loads(cached)
    
    embedding = fetch_embedding_from_pinecone(memory_id)
    redis_client.setex(f"embedding:{memory_id}", 3600, json.dumps(embedding))  # Cache for 1 hour
    return embedding
```

### 3. Asynchronous Embedding Generation

For non-blocking embedding generation:

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

async def generate_embeddings_async(texts: List[str]):
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        embeddings = await asyncio.gather(
            *[loop.run_in_executor(executor, generate_memory_embedding, text) for text in texts]
        )
    return embeddings
```

## 💻 Complex Operations with Embeddings

### 1. Time-Weighted Memory Retrieval

This function retrieves relevant memories with a bias towards more recent ones:

```python
import numpy as np

def time_weighted_memory_retrieval(query: str, uid: str, k: int = 5, time_decay: float = 0.1):
    query_embedding = generate_memory_embedding(query)
    results = index.query(
        vector=query_embedding,
        top_k=k*2,  # Retrieve more results for post-processing
        namespace="ns1",
        filter={"uid": uid}
    )
    
    weighted_results = []
    for item in results['matches']:
        memory_id = item['id'].split('-')[1]
        memory = get_memory(uid, memory_id)
        time_diff = (datetime.now() - memory.created_at).days
        time_weight = np.exp(-time_decay * time_diff)
        weighted_score = item['score'] * time_weight
        weighted_results.append((memory, weighted_score))
    
    return sorted(weighted_results, key=lambda x: x[1], reverse=True)[:k]
```

### 2. Multi-Query Embedding Search

This function allows searching with multiple query embeddings and aggregates the results:

```python
from collections import defaultdict

def multi_query_search(queries: List[str], uid: str, k: int = 5):
    query_embeddings = [generate_memory_embedding(query) for query in queries]
    
    all_results = defaultdict(float)
    for embedding in query_embeddings:
        results = index.query(
            vector=embedding,
            top_k=k,
            namespace="ns1",
            filter={"uid": uid}
        )
        for item in results['matches']:
            memory_id = item['id'].split('-')[1]
            all_results[memory_id] += item['score']
    
    top_memories = sorted(all_results.items(), key=lambda x: x[1], reverse=True)[:k]
    return [get_memory(uid, memory_id) for memory_id, _ in top_memories]
```

These advanced techniques and optimizations showcase the power and flexibility of using embeddings for memory retrieval and analysis in the Omi backend.

## 🎯 Why Embeddings Matter

1. **Semantic Understanding:** Embeddings capture the meaning of memories, not just keywords.
2. **Efficient Retrieval:** Vector similarity search is fast and scalable.
3. **Cross-Lingual Capabilities:** Embeddings can bridge language barriers in memory retrieval.
4. **Contextual Responses:** Omi can provide more relevant and context-aware responses in conversations.

## 🔒 Security and Privacy Considerations

- Embeddings are stored with user IDs to ensure data isolation.
- Access to Pinecone is restricted and authenticated to prevent unauthorized access.
- Consider implementing encryption-at-rest for the vector database for additional security.

## 🚀 Performance Optimization

1. **Batch Processing:** Use Pinecone's batch upsert for multiple embeddings.
2. **Caching:** Implement a caching layer (e.g., Redis) for frequently accessed embeddings.
3. **Index Optimization:** Regularly monitor and optimize the Pinecone index for query performance.

## 🔄 Continuous Improvement

- Regularly evaluate and update the embedding model to benefit from advancements in NLP.
- Implement A/B testing to compare different embedding strategies and their impact on retrieval quality.
- Collect user feedback on search results to fine-tune the embedding and retrieval process.

## 💻 Key Code Components

```python
# In utils/memories/process_memory.py
async def process_memory(uid: str, processing_memory_id: str):
    # ... (previous code)
    embedding = generate_memory_embedding(memory, structured_data)
    upsert_vector(uid, memory, embedding)

# In utils/llm.py
def generate_memory_embedding(memory: Memory, structured_data: dict) -> List[float]:
    embedding_text = prepare_embedding_text(memory, structured_data)
    return openai.Embedding.create(input=embedding_text, model="text-embedding-3-large")['data'][0]['embedding']

# In database/vector_db.py
def upsert_vector(uid: str, memory: Memory, vector: List[float]):
    metadata = prepare_metadata(uid, memory)
    index.upsert(vectors=[{"id": f'{uid}-{memory.id}', "values": vector, 'metadata': metadata}], namespace="ns1")

def query_vectors(query: str, uid: str, k: int = 5) -> List[str]:
    query_embedding = embeddings.embed_query(query)
    results = index.query(vector=query_embedding, top_k=k, namespace="ns1", filter={"uid": uid})
    return [item['id'].split('-')[1] for item in results['matches']]
```

By implementing this comprehensive embedding process, Omi ensures that memories are not just stored, but are made intelligently accessible, enabling rich, context-aware interactions and insights.
