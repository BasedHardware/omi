---
layout: default
title: Memeory Store
parent: Backend
nav_order: 3
---

# 📚 Memory Storage Process

This document outlines the process of storing memory objects in the Friend AI system.

## 🔄 Overview of the Process

1. Memory object is processed
2. Object is converted to a dictionary
3. Data is organized into specific fields
4. Memory is saved to Firestore

   ![Backend Memory Storage](/images/memorystore.png)



## 🧠 Detailed Steps

### 1. 📥 Memory Object Received

- The `process_memory` function in `utils/memories/process_memory.py` processes a new or updated memory
- The complete Memory object is then sent to the `upsert_memory` function in `database/memories.py`

### 2. 🔄 Convert to Dictionary

- The `upsert_memory` function converts the Memory object into a Python dictionary
- This conversion is necessary because Firestore stores data in a JSON-like format

### 3. 📊 Data Fields

The dictionary contains the following key fields:

| Field | Description |
|-------|-------------|
| `id` | Unique ID of the memory |
| `created_at` | Timestamp of memory creation |
| `started_at` | Timestamp when the associated event started |
| `finished_at` | Timestamp when the associated event ended |
| `source` | Source of the memory (e.g., "friend", "openglass", "workflow") |
| `language` | Language code of the conversation |
| `structured` | Dictionary of structured information (see below) |
| `transcript_segments` | List of transcript segments (see below) |
| `geolocation` | Location data (if available) |
| `plugins_results` | Results from any plugins run on the memory |
| `external_data` | Additional data from external integrations |
| `postprocessing` | Information about post-processing status |
| `discarded` | Boolean indicating if the memory is low-quality |
| `deleted` | Boolean indicating if the memory has been deleted |
| `visibility` | Visibility setting of the memory |

#### 📋 Structured Information

The `structured` field contains:

- `title`: Topic of the memory
- `overview`: Summary of the memory
- `emoji`: Representing emoji
- `category`: Category (e.g., "personal", "business")
- `action_items`: List of derived action items
- `events`: List of extracted calendar events

#### 🗣️ Transcript Segments

Each segment in `transcript_segments` includes:

- `speaker`: Speaker label (e.g., "SPEAKER_00")
- `start`: Start time in seconds
- `end`: End time in seconds
- `text`: Transcribed text
- `is_user`: Boolean indicating if spoken by the user
- `person_id`: ID of a person from user's profiles (if applicable)

#### 🔄 Postprocessing Information

The `postprocessing` field contains:

- `status`: Current status (e.g., "not_started", "in_progress")
- `model`: Post-processing model used (e.g., "fal_whisperx")
- `fail_reason`: (Optional) Reason for failure

### 4. 💾 Save to Firestore

- `database/memories.py` uses the Firebase Firestore API to store the memory data dictionary
- Data is saved in the `memories` collection within the user's document

#### 📁 Firestore Structure
Users Collection
```└── User Document
└── memories Collection
├── Memory Document 1
├── Memory Document 2
└── ...
```
This structure allows for efficient querying and management of user-specific memory data.
