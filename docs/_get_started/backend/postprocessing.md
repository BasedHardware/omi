---
layout: default
title: Memory Post-Processing
parent: Backend
nav_order: 6
---

# 🎛️ Omi Memory Post-Processing Workflow

This document provides a comprehensive overview of the post-processing workflow for memories in the Omi application. It covers the entire process from initial transcription to final storage, including all intermediate steps and key code components.

## 📊 Process Overview

1. Initial real-time transcription with multiple services
2. Processing memory creation
3. Initial memory processing and storage
4. Post-processing request initiation
5. Request handling and audio preparation
6. High-accuracy transcription with FAL.ai WhisperX
7. Transcript post-processing and segmentation
8. Speech profile matching for speaker identification
9. Memory update and reprocessing
10. Optional emotional analysis
11. Final storage and vector embedding update
12. Enhancing User Experience with Post-Processing Results

![Post Processing](/images/postprocessing.png)

## 🔍 Detailed Steps

### 1. Initial Real-Time Transcription

- Multiple transcription services (Deepgram, Soniox, Speechmatics) process audio in real-time
- Handled by `routers/transcribe.py` through WebSocket connections
- Each service provides its own transcription results

```python
@router.websocket("/listen")
async def websocket_endpoint(websocket: WebSocket, uid: str, language: str = 'en', ...):
    await websocket.accept()
    transcript_socket_deepgram = await process_audio_dg(uid, websocket, language, ...)
    transcript_socket_soniox = await process_audio_soniox(uid, websocket, language, ...)
    transcript_socket_speechmatics = await process_audio_speechmatics(uid, websocket, language, ...)
    # Process incoming audio and send transcripts back to the client
```

### 2. Processing Memory Creation

- `create_processing_memory` function in `database/processing_memories.py` creates a new processing memory
- Stores initial transcription results and metadata

```python
def create_processing_memory(uid: str, data: dict):
    processing_memory_id = str(uuid.uuid4())
    processing_memory_data = {
        "id": processing_memory_id,
        "created_at": datetime.now(timezone.utc),
        "transcript_segments": data["transcript_segments"],
        "language": data["language"],
        # ... other relevant data
    }
    upsert_processing_memory(uid, processing_memory_data)
    return processing_memory_id
```

### 3. Initial Memory Processing and Storage

- `process_memory` function in `utils/memories/process_memory.py` processes the memory
- Uses OpenAI's LLM to extract structured data (title, overview, etc.)
- Generates initial vector embedding
- Stores processed memory in Firebase Firestore
- Stores embedding in Pinecone vector database

```python
async def process_memory(uid: str, processing_memory_id: str):
    processing_memory = get_processing_memory_by_id(uid, processing_memory_id)
    structured_data = await extract_structured_data(processing_memory.transcript)
    embedding = generate_memory_embedding(processing_memory)
    
    memory_data = {
        "id": str(uuid.uuid4()),
        "created_at": processing_memory.created_at,
        "transcript_segments": processing_memory.transcript_segments,
        "structured": structured_data,
        # ... other memory fields
    }
    
    upsert_memory(uid, memory_data)
    upsert_vector(uid, memory_data, embedding)
    delete_processing_memory(uid, processing_memory_id)
```

### 4. Post-Processing Request Initiation

- Omi App sends POST request to `/v1/memories/{memory_id}/post-processing`
- Request includes audio recording and optional emotional analysis flag

```python
@router.post("/v1/memories/{memory_id}/post-processing", response_model=Memory)
async def postprocess_memory(
    memory_id: str,
    file: UploadFile,
    emotional_feedback: bool = False,
    background_tasks: BackgroundTasks,
    uid: str = Depends(get_current_user_id)
):
    # ... (request handling code)
```

### 5. Request Handling and Audio Preparation

- `postprocess_memory` function in `routers/postprocessing.py` processes the request
- Retrieves existing memory data from Firebase Firestore
- Uploads audio for processing to Google Cloud Storage
- Initiates background task for post-processing

```python
async def postprocess_memory(...):
    memory = get_memory(uid, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    audio_url = await upload_audio_for_processing(file, uid, memory_id)
    background_tasks.add_task(run_postprocessing, uid, memory_id, audio_url, emotional_feedback)
    return memory
```

### 6. High-Accuracy Transcription with FAL.ai WhisperX

- `fal_whisperx` function in `utils/stt/pre_recorded.py` sends audio to FAL.ai
- WhisperX model performs high-quality transcription and speaker diarization
- Returns list of transcribed words with speaker labels and timestamps

```python
async def fal_whisperx(audio_url: str):
    result = fal.apps.submit_and_wait(
        "110602490-whispercpp",
        {
            "audio": audio_url,
            "language": "en",
            "task": "transcribe",
            "vad_filter": True,
            "word_timestamps": True,
        },
    )
    return process_fal_result(result)
```

### 7. Transcript Post-Processing and Segmentation

- `fal_postprocessing` function cleans and segments the transcript data
- Groups words into `TranscriptSegment` objects based on speaker and timing

```python
def fal_postprocessing(words: List[dict]) -> List[TranscriptSegment]:
    segments = []
    current_segment = None
    for word in words:
        if not current_segment or word['speaker'] != current_segment.speaker:
            if current_segment:
                segments.append(current_segment)
            current_segment = TranscriptSegment(
                start=word['start'],
                end=word['end'],
                text=word['word'],
                speaker=word['speaker']
            )
        else:
            current_segment.end = word['end']
            current_segment.text += f" {word['word']}"
    if current_segment:
        segments.append(current_segment)
    return segments
```

### 8. Speech Profile Matching for Speaker Identification

- `get_speech_profile_matching_predictions` in `utils/stt/speech_profile.py` performs speaker identification
- Compares segment audio with user's speech profile and known people profiles
- Updates segments with `is_user` and `person_id` flags

```python
def get_speech_profile_matching_predictions(uid: str, segments: List[TranscriptSegment]):
    user_profile = get_user_speech_profile(uid)
    people_profiles = get_people_with_speech_samples(uid)
    
    for segment in segments:
        scores = {
            'user': sample_same_speaker_as_segment(user_profile, segment.audio),
            **{person['id']: sample_same_speaker_as_segment(person['profile'], segment.audio) for person in people_profiles}
        }
        best_match = max(scores, key=scores.get)
        segment.is_user = best_match == 'user'
        segment.person_id = None if segment.is_user else best_match
    
    return segments
```

### 9. Memory Update and Reprocessing

- Updates memory object with improved transcript and speaker identification
- Re-extracts structured data and regenerates embeddings
- Updates memory in Firestore and vector embedding in Pinecone

```python
async def reprocess_memory(uid: str, memory_id: str, new_segments: List[TranscriptSegment]):
    memory = get_memory(uid, memory_id)
    memory.transcript_segments = new_segments
    
    structured_data = await extract_structured_data(memory.transcript)
    memory.structured = structured_data
    
    embedding = generate_memory_embedding(memory)
    
    upsert_memory(uid, memory.dict())
    upsert_vector(uid, memory, embedding)
    
    return memory
```

### 10. Emotional Analysis (Optional)

- `process_user_emotion` function analyzes audio for emotional content using Hume AI
- Emotional data stored alongside memory

```python
async def process_user_emotion(uid: str, file_path: str):
    client = HumeStreamClient(os.getenv("HUME_API_KEY"))
    config = LanguageConfig(granularity="sentence")
    async with client.connect([config]) as socket:
        result = await socket.send_file(file_path)
    
    emotions = extract_emotions_from_result(result)
    store_model_emotion_predictions_result(uid, memory_id, "hume", emotions)
```

### 11. Final Storage and Vector Embedding Update

- Final memory data saved to Firebase Firestore
- Updated vector embedding stored in Pinecone for efficient retrieval

```python
def upsert_memory(uid: str, memory_data: dict):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_data['id'])
    memory_ref.set(memory_data)

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

### 12. Enhancing User Experience with Post-Processing Results

1. **Improved Transcript Accuracy:**
   - Higher quality transcripts lead to more accurate memory retrieval and analysis.
   - Users can rely on the transcripts for important information without manual corrections.

2. **Enhanced Speaker Identification:**
   - Accurate speaker labeling improves conversation context and personalization.
   - Enables features like speaker-specific insights and personalized recommendations.

3. **Emotional Context Awareness:**
   - Emotional analysis allows for more empathetic and context-aware responses from Omi.
   - Enables tracking of emotional patterns over time for personal growth insights.

4. **Better Memory Summarization:**
   - Improved transcripts and emotional data lead to more accurate and insightful memory summaries.
   - Enhances the quality of daily or weekly recap features.

5. **More Relevant Memory Retrieval:**
   - Higher quality transcripts and embeddings improve the accuracy of semantic search.
   - Users receive more relevant memories when asking questions or seeking past information.

## 🔄 Error Handling and Retry Mechanisms

Robust error handling and retry mechanisms are crucial for ensuring reliable post-processing:

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def run_postprocessing(uid: str, memory_id: str, audio_url: str):
    try:
        # Post-processing logic
        pass
    except TransientError as e:
        logger.warning(f"Transient error during post-processing: {str(e)}")
        raise  # This will trigger a retry
    except PermanentError as e:
        logger.error(f"Permanent error during post-processing: {str(e)}")
        update_memory_postprocessing_status(uid, memory_id, status="failed", error=str(e))
        # Notify user or support team
```

This implementation uses the `tenacity` library for advanced retry logic:
- Retries up to 3 times for transient errors.
- Uses exponential backoff to avoid overwhelming services.
- Distinguishes between transient and permanent errors for appropriate handling.

## 📊 Performance Metrics and Monitoring

Implementing comprehensive monitoring ensures optimal performance and quick issue resolution:

1. **Prometheus Metrics:**
   ```python
   from prometheus_client import Counter, Histogram

   POSTPROCESSING_DURATION = Histogram('memory_postprocessing_duration_seconds', 'Duration of memory post-processing')
   POSTPROCESSING_ERRORS = Counter('memory_postprocessing_errors_total', 'Total post-processing errors')

   async def run_postprocessing(uid: str, memory_id: str, audio_url: str):
       with POSTPROCESSING_DURATION.time():
           try:
               # Post-processing logic
               pass
           except Exception as e:
               POSTPROCESSING_ERRORS.inc()
               raise
   ```

2. **Logging Key Events:**
   ```python
   import structlog

   logger = structlog.get_logger()

   async def run_postprocessing(uid: str, memory_id: str, audio_url: str):
       logger.info("Starting post-processing", uid=uid, memory_id=memory_id)
       # ... processing logic ...
       logger.info("Post-processing completed", uid=uid, memory_id=memory_id, duration=duration)
   ```

3. **Alerting on Critical Issues:**
   - Set up alerts for high error rates or prolonged processing times.
   - Integrate with incident management systems like PagerDuty for immediate notification.

4. **Dashboard for Visualization:**
   - Create a Grafana dashboard to visualize:
     - Post-processing success rates
     - Average processing times
     - Error rates by type
     - Resource utilization during processing

## 🔄 Continuous Improvement Strategies

To ensure the post-processing system evolves and improves over time:

1. **A/B Testing Framework:**
   - Implement a system to test new post-processing algorithms or configurations.
   - Compare results against existing methods for accuracy and performance.

2. **User Feedback Loop:**
   - Collect user feedback on post-processing results and incorporate it into the improvement process.
   - Implement a system for users to report issues or provide suggestions for improvement.

3. **Automated Testing:**
   - Develop a suite of automated tests to validate the accuracy and performance of the post-processing system.
   - Regularly run these tests to ensure the system remains reliable and up-to-date.

4. **Continuous Learning:**
   - Implement a system to continuously learn and improve the post-processing algorithms based on new data and techniques.
   - Regularly update the system to leverage the latest advancements in speech recognition and natural language processing.

5. **Scalability and Resilience:**
   - Design the post-processing system to handle increasing volumes of data and traffic.
   - Implement fault-tolerant mechanisms to ensure the system remains available and reliable even under heavy loads.

By following this detailed post-processing workflow, Omi ensures that each memory is accurately transcribed, enriched with valuable metadata, and optimized for efficient retrieval and use in AI-powered interactions.
