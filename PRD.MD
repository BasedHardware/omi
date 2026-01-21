# PRD: Show Speech Sample Transcripts in People Settings

## Problem Statement

PR #4291 adds speaker sample quality verification that already transcribes audio samples using Deepgram to verify:
- Minimum 5 words transcribed
- Single speaker dominance ≥70%
- Text similarity ≥60% with expected segment text

However, the transcript is only used for validation and then **discarded**. Users should be able to see what was said in each speech sample in the Settings > People page.

## Current State

### Backend (`backend/models/other.py`)
```python
class Person(BaseModel):
    speech_samples: List[str] = []  # Just URLs
```

### Frontend (`app/lib/backend/schema/person.dart`)
```dart
class Person {
  final List<String>? speechSamples;  // Just URLs
}
```

### UI (`app/lib/pages/settings/people.dart`)
- Shows "Speech Profile" or "Sample #X" labels
- Play/pause button for audio playback
- No transcript displayed

## Proposed Solution

Store the transcript alongside each speech sample when it's saved. This leverages the transcription already being done in PR #4291's verification flow.

### Data Model Change (Backwards Compatible)

Keep `speech_samples` as `List[str]` to avoid breaking existing apps. Add a **separate field** for transcripts:

```python
# Firestore storage - no change to speech_samples
speech_samples: ["gcs/path/1.wav", "gcs/path/2.wav"]  # Unchanged
speech_sample_transcripts: ["Hello, my name is John", "I work at Anthropic"]  # NEW parallel array

# API response - add new optional field
{
    "speech_samples": ["signed_url_1", "signed_url_2"],  # Unchanged (older apps work)
    "speech_sample_transcripts": ["Hello...", "I work..."]  # NEW (older apps ignore)
}
```

### Backwards Compatibility

- **Older apps**: Continue to work - they receive `speech_samples` and ignore unknown fields
- **Newer apps**: Read both `speech_samples` and `speech_sample_transcripts`

---

## Technical Implementation

### 1. Backend Database (`backend/database/users.py`)

#### Update `add_person_speech_sample()`
Accept and store transcript in the new field:
```python
def add_person_speech_sample(uid, person_id, sample_path, transcript=None, max_samples=5):
    # Append to both speech_samples and speech_sample_transcripts arrays
```

#### Update `remove_person_speech_sample()` - CRITICAL
Current code uses `firestore.ArrayRemove([sample_path])` which removes by **value**. With parallel arrays, we need to remove by **index** to keep them in sync:

```python
def remove_person_speech_sample(uid: str, person_id: str, sample_path: str) -> bool:
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_doc = person_ref.get()

    if not person_doc.exists:
        return False

    person_data = person_doc.to_dict()
    samples = person_data.get('speech_samples', [])
    transcripts = person_data.get('speech_sample_transcripts', [])

    # Find index of sample to remove
    try:
        idx = samples.index(sample_path)
    except ValueError:
        return False  # Sample not found

    # Remove from both arrays by index
    samples.pop(idx)
    if idx < len(transcripts):
        transcripts.pop(idx)

    person_ref.update({
        'speech_samples': samples,
        'speech_sample_transcripts': transcripts,
        'updated_at': datetime.now(timezone.utc),
    })
    return True
```

#### Add migration functions
```python
def set_person_speech_sample_transcript(uid, person_id, sample_index, transcript):
    # Update transcript at specific index

def update_person_speech_samples_after_migration(uid, person_id, samples, transcripts, version, speaker_embedding=None):
    """Replace all samples/transcripts/embedding and set version atomically."""

def clear_person_speaker_embedding(uid, person_id):
    """Clear speaker embedding when samples are dropped."""

def update_person_speech_samples_version(uid, person_id, version):
    """Update just the version field."""
```

---

### 2. Backend Models (`backend/models/other.py`)

Add new fields to Person:
```python
class Person(BaseModel):
    # ... existing fields ...
    speech_samples: List[str] = []  # Unchanged
    speech_sample_transcripts: Optional[List[str]] = None  # NEW
    speech_samples_version: int = 1  # NEW - version tracking for future migrations
```

**Version definitions:**
- `v1` (default/legacy): Only `speech_samples` exists, uses v1 speaker embedding
- `v2` (current): Both `speech_samples` and `speech_sample_transcripts` exist, uses v2 speaker embedding

---

### 3. Centralized Migration Utility (`backend/utils/speaker_sample_migration.py`) - NEW FILE

```python
from utils.stt.pre_recorded import deepgram_prerecorded_from_bytes
from utils.text_utils import compute_text_similarity
from database.users import (
    set_person_speech_sample_transcript,
    update_person_speech_samples_version,
)

MIN_WORDS = 5
MIN_SIMILARITY = 0.6
MIN_DOMINANT_SPEAKER_RATIO = 0.7

async def verify_and_transcribe_sample(audio_bytes: bytes, sample_rate: int, expected_text: str = None):
    """
    Transcribe audio and verify quality using PR #4291 rules.
    Returns (transcript, is_valid, reason)
    """
    words = await asyncio.to_thread(deepgram_prerecorded_from_bytes, audio_bytes, sample_rate, True)

    if len(words) < MIN_WORDS:
        return None, False, f"insufficient_words: {len(words)}/{MIN_WORDS}"

    # Speaker dominance check
    speaker_counts = {}
    for word in words:
        speaker = word.get('speaker', 'SPEAKER_00')
        speaker_counts[speaker] = speaker_counts.get(speaker, 0) + 1

    total_words = len(words)
    dominant_count = max(speaker_counts.values()) if speaker_counts else 0
    dominant_ratio = dominant_count / total_words if total_words > 0 else 0

    if dominant_ratio < MIN_DOMINANT_SPEAKER_RATIO:
        return None, False, f"multi_speaker: ratio={dominant_ratio:.2f}"

    transcript = ' '.join(w.get('text', '') for w in words)

    # Text similarity check (only if expected_text provided)
    if expected_text:
        similarity = compute_text_similarity(transcript, expected_text)
        if similarity < MIN_SIMILARITY:
            return transcript, False, f"text_mismatch: similarity={similarity:.2f}"

    return transcript, True, "ok"

async def migrate_person_samples_v1_to_v2(uid: str, person: dict):
    """
    Migrate person's speech samples from v1 to v2.
    Samples that fail PR #4291 quality rules are DROPPED along with speaker_embedding.
    """
    version = person.get('speech_samples_version', 1)
    if version >= 2:
        return person  # Already migrated

    samples = person.get('speech_samples', [])
    valid_samples = []
    valid_transcripts = []

    for sample_path in samples:
        # Download and transcribe
        audio_bytes = await download_sample_audio(sample_path)
        transcript, is_valid, reason = await verify_and_transcribe_sample(audio_bytes, 16000)

        if is_valid:
            valid_samples.append(sample_path)
            valid_transcripts.append(transcript)
        else:
            # DROP sample that fails quality check
            print(f"Dropping sample {sample_path}: {reason}", uid, person['id'])
            await delete_sample_from_storage(sample_path)

    # Re-extract speaker embedding for remaining valid samples
    new_embedding = None
    if valid_samples:
        first_sample_audio = await download_sample_audio(valid_samples[0])
        new_embedding = await extract_speaker_embedding_v2(first_sample_audio)

    # Update Firestore
    update_person_speech_samples_after_migration(
        uid, person['id'],
        samples=valid_samples,
        transcripts=valid_transcripts,
        version=2,
        speaker_embedding=new_embedding
    )

    person['speech_samples'] = valid_samples
    person['speech_sample_transcripts'] = valid_transcripts
    person['speech_samples_version'] = 2
    person['speaker_embedding'] = new_embedding

    return person
```

---

### 4. Backend Speaker Identification (`backend/utils/speaker_identification.py`)

Refactor to use centralized migration utility:
```python
from utils.speaker_sample_migration import verify_and_transcribe_sample

async def extract_speaker_samples(...):
    # ... existing sample extraction code ...

    # Use centralized verification (instead of inline _verify_sample_quality)
    transcript, is_valid, reason = await verify_and_transcribe_sample(
        wav_bytes, sample_rate, expected_text=seg.get('text', '')
    )

    if not is_valid:
        print(f"Sample failed quality check: {reason}", uid, conversation_id)
        continue

    # Pass transcript to storage function
    success = users_db.add_person_speech_sample(
        uid, person_id, path, transcript=transcript
    )
```

---

### 5. Backend API (`backend/routers/users.py`)

Use centralized migration utility for lazy migration:
```python
from utils.speaker_sample_migration import migrate_person_samples_v1_to_v2

@router.get('/v1/users/people', tags=['v1'], response_model=List[Person])
async def get_all_people(include_speech_samples: bool = True, uid: str = Depends(auth.get_current_user_uid)):
    people = get_people(uid)

    if include_speech_samples:
        for person in people:
            # Run lazy migration for v1 samples
            person = await migrate_person_samples_v1_to_v2(uid, person)
            # Convert GCS paths to signed URLs
            stored_paths = person.get('speech_samples', [])
            person['speech_samples'] = get_speech_sample_signed_urls(stored_paths)

    return people

@router.get('/v1/users/people/{person_id}', tags=['v1'], response_model=Person)
async def get_single_person(person_id: str, include_speech_samples: bool = False, uid: str = Depends(auth.get_current_user_uid)):
    person = get_person(uid, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    if include_speech_samples:
        person = await migrate_person_samples_v1_to_v2(uid, person)
        stored_paths = person.get('speech_samples', [])
        person['speech_samples'] = get_speech_sample_signed_urls(stored_paths)

    return person
```

**Note:** These endpoints become async to support the migration.

---

### 6. Flutter Model (`app/lib/backend/schema/person.dart`)

Add transcript and version fields:
```dart
class Person {
  final String id;
  final String name;
  final DateTime createdAt;
  final DateTime updatedAt;
  final List<String>? speechSamples;  // Unchanged
  final List<String>? speechSampleTranscripts;  // NEW
  final int speechSamplesVersion;  // NEW - default to 1
  final int? colorIdx;

  Person({
    required this.id,
    required this.name,
    required this.createdAt,
    required this.updatedAt,
    this.speechSamples,
    this.speechSampleTranscripts,
    this.speechSamplesVersion = 1,
    this.colorIdx,
  });

  factory Person.fromJson(Map<String, dynamic> json) {
    return Person(
      id: json['id'],
      name: json['name'],
      createdAt: DateTime.parse(json['created_at']).toLocal(),
      updatedAt: DateTime.parse(json['updated_at']).toLocal(),
      speechSamples: json['speech_samples'] != null ? List<String>.from(json['speech_samples']) : [],
      speechSampleTranscripts: json['speech_sample_transcripts'] != null
          ? List<String>.from(json['speech_sample_transcripts'])
          : null,
      speechSamplesVersion: json['speech_samples_version'] ?? 1,
      colorIdx: json['color_idx'] ?? json['id'].hashCode % speakerColors.length,
    );
  }
}
```

---

### 7. Flutter UI (`app/lib/pages/settings/people.dart`)

Display transcript below each sample:
```dart
...person.speechSamples!.mapIndexed((j, sample) => ListTile(
  // ... existing play/pause button ...
  title: Text(j == 0 ? 'Speech Profile' : 'Sample #$j'),
  subtitle: Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      if (person.speechSampleTranscripts != null &&
          j < person.speechSampleTranscripts!.length)
        Text(
          '"${person.speechSampleTranscripts![j]}"',
          style: TextStyle(fontSize: 14, fontStyle: FontStyle.italic),
        ),
      Text('Tap to delete', style: TextStyle(fontSize: 12, color: Colors.grey)),
    ],
  ),
)),
```

---

## UI Design

Display **full transcript** text for each sample:

```
Person Name [Delete]
  [Play] Speech Profile
         "Hello, my name is John and I work at Anthropic.
          I've been here for two years now."
         Tap to delete

  [Play] Sample #1
         "I really enjoy working on AI safety research
          and collaborating with the team."
         Tap to delete
```

For samples being migrated (transcription in progress), show a loading indicator.

---

## Verification Checklist

1. **New samples**: Create a new person, tag a speaker segment, verify:
   - Transcript is stored and displayed
   - `speech_samples_version = 2`
   - `speaker_embedding` uses v2 embedding API

2. **Lazy migration (valid)**: Use an existing v1 sample that passes quality check, verify:
   - Transcript is extracted and stored
   - Version updated to 2
   - `speaker_embedding` is re-extracted using v2 API

3. **Lazy migration (invalid)**: Use a v1 sample that fails quality check (e.g., too short, multi-speaker), verify:
   - Sample is dropped from `speech_samples`
   - Sample file is deleted from GCS
   - `speaker_embedding` is cleared (no valid samples) or re-extracted (if other samples remain)
   - Version is still updated to 2

4. **API response**: Check that GET /v1/users/people returns `speech_samples`, `speech_sample_transcripts`, and `speech_samples_version`

5. **Delete sample**: Delete a specific sample, verify both arrays stay in sync (same length, correct items)

6. **Delete person**: Delete entire person, verify all data is cleaned up

7. **Version check**: Verify v2 samples skip migration (no unnecessary Deepgram calls or embedding re-extraction)

8. **Backwards compatibility**: Test with an older app version that only reads `speech_samples`

9. **Run tests**: `backend/test.sh` and `app/test.sh`

10. **Manual test**: Play audio and verify transcript matches what you hear

---

## Key Files to Modify

| File | Changes |
|------|---------|
| `backend/utils/speaker_sample_migration.py` | NEW - Centralized migration utility |
| `backend/models/other.py` | Add `speech_sample_transcripts`, `speech_samples_version` fields |
| `backend/database/users.py` | Update `add_person_speech_sample()`, `remove_person_speech_sample()`, add migration functions |
| `backend/utils/speaker_identification.py` | Use centralized verification, pass transcript to storage |
| `backend/routers/users.py` | Add lazy migration, make endpoints async |
| `app/lib/backend/schema/person.dart` | Add `speechSampleTranscripts`, `speechSamplesVersion` fields |
| `app/lib/pages/settings/people.dart` | Display transcript in UI |

---

## Pre-requisite

This implementation is based on branch `e8w2h_speaker_identification` which contains:
- `_verify_sample_quality()` in `backend/utils/speaker_identification.py`
- `deepgram_prerecorded_from_bytes()` in `backend/utils/stt/pre_recorded.py`
- `compute_text_similarity()` in `backend/utils/text_utils.py`
