---
layout: default
title: Realtime Transcription
parent: Backend
nav_order: 4
---

# 🎙️ Real-Time Transcription Process

This document outlines the real-time audio transcription process in the Omi application.

![Post Processing](../../images/transcription-process.png)

## 📡 Audio Streaming

1. The Omi App initiates a real-time audio stream to the backend.
2. Audio data is sent via WebSocket to the `/listen` endpoint.
3. Audio can be in Opus or Linear16 encoding, depending on device settings.

## 🔌 WebSocket Handling

### `/listen` Endpoint

- Located in `routers/transcribe.py`
- `websocket_endpoint` function sets up the connection
- Calls `_websocket_util` function to manage the connection

### `_websocket_util` Function

- Accepts the WebSocket connection
- Checks for user speech profile
  - If exists, sends profile audio to Deepgram first
  - Uses `utils/other/storage.py` to retrieve profile from Google Cloud Storage
- Creates asynchronous tasks:
  - `receive_audio`: Receives audio chunks and sends to Deepgram
  - `send_heartbeat`: Sends periodic messages to keep connection alive

## 🔊 Deepgram Integration

### `process_audio_dg` Function

- Located in `utils/stt/streaming.py`
- Initializes Deepgram client using `DEEPGRAM_API_KEY`
- Defines `on_message` callback for handling transcripts
- Starts live transcription stream with Deepgram

### Deepgram Configuration

| Option | Value | Description |
|--------|-------|-------------|
| `language` | Variable | Audio language |
| `sample_rate` | 8000 or 16000 Hz | Audio sample rate |
| `codec` | Opus or Linear16 | Audio codec |
| `channels` | Variable | Number of audio channels |
| `punctuate` | True | Automatic punctuation |
| `no_delay` | True | Low-latency transcription |
| `endpointing` | 100 | Sentence boundary detection |
| `interim_results` | False | Only final transcripts sent |
| `smart_format` | True | Enhanced transcript formatting |
| `profanity_filter` | False | No profanity filtering |
| `diarize` | True | Speaker identification |
| `filler_words` | False | Remove filler words |
| `multichannel` | channels > 1 | Enable if multiple channels |
| `model` | 'nova-2-general' | Deepgram model selection |

## 🔄 Transcript Processing

1. Deepgram processes audio and triggers `on_message` callback
2. `on_message` receives raw transcript data
3. Callback formats transcript data:
   - Groups words into segments
   - Creates list of segment dictionaries
4. Formatted segments sent back to Omi App via WebSocket

### Segment Dictionary Structure

| Field | Description |
|-------|-------------|
| `speaker` | Speaker label (e.g., "SPEAKER_00") |
| `start` | Segment start time (seconds) |
| `end` | Segment end time (seconds) |
| `text` | Combined, punctuated text |
| `is_user` | Boolean indicating if segment is from the user |
| `person_id` | ID of matched person from user profiles (if applicable) |

## 🔑 Key Considerations

- Real-time, low-latency transcription
- Speaker diarization accuracy may vary
- Audio encoding choice (Opus vs. Linear16) may affect performance
- Deepgram model selection based on specific needs
- Implement proper error handling in `on_message`

This overview provides a comprehensive understanding of Omi's real-time transcription process, which can be adapted when integrating alternative audio transcription services.
