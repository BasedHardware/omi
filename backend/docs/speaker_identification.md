# Speaker Name Identification with NER

## Overview

Enhanced speaker name identification using Stanza NER (Named Entity Recognition) for improved multilingual speaker name detection.

## What Changed

- **Before**: Regex-based detection (poor quality)
- **After**: Stanza NER + regex fallback (high quality)

## Features

- Multilingual support (English, Spanish, French, Chinese)
- Fast processing suitable for live transcripts
- Low cost with open-source Stanza
- Self-hostable solution for Omi
- Graceful fallback to regex if NER fails

## Setup

### Prerequisites

- Python 3.8+
- Stanza library installed

### Installation

```bash
pip install stanza==1.8.2
```

### Environment Variables

No additional environment variables required.

## Usage

### Basic Usage

```python
from utils.speaker_identification import detect_speaker_from_text

# English
name = detect_speaker_from_text("Hi, I'm Alice and I'll be your guide today.", "en")
# Returns: "Alice"

# Spanish
name = detect_speaker_from_text("Hola, me llamo Carlos y soy el doctor.", "es")
# Returns: "Carlos"

# French
name = detect_speaker_from_text("Je vous présente Marie, notre experte.", "fr")
# Returns: "Marie"

# Chinese
name = detect_speaker_from_text("王伟会为大家解答问题。", "zh")
# Returns: "王伟"
```

### Integration

The function is automatically integrated into the transcription pipeline in `backend/routers/transcribe.py`.

## Performance Considerations

- **Fast processing**: Suitable for live transcripts
- **Low memory footprint**: Efficient model loading
- **Thread-safe**: Cached pipelines per language
- **Graceful fallback**: Falls back to regex if NER fails

## Supported Languages

- English (en)
- Spanish (es)
- French (fr)
- Chinese (zh)

## Error Handling

- Graceful fallback to regex if NER fails
- Thread-safe pipeline caching
- Exception handling for model loading

## Testing

Run the test suite:

```bash
python -m pytest backend/utils/test_speaker_identification.py -v
```

## Troubleshooting

- If NER fails, the system automatically falls back to regex
- Models are downloaded automatically on first use
- Check logs for any model loading errors
