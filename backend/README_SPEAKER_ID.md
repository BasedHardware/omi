
# Speaker Identification Module

Integration with external self-hosted vLLM (OpenAI-compatible) for speaker identification and transcript cleaning.

**Fix for:** [Issue #3039](https://github.com/BasedHardware/omi/issues/3039) - Improve speaker detection using self-hosted LLM

## Overview

This module (`utils/text_speaker_detection.py`) adds LLM-based addressee detection alongside the existing regex-based self-identification.

**Pipeline:**
1. **Regex first** (0 ms, 0 tokens): Catches self-introductions like "I am Alice" instantly.
2. **LLM fallback** (~200-300 ms): Uses Llama 3.1 8B via vLLM to detect who is being *spoken to* and clean the transcript.

**Key distinction — Address vs. Mention:**
- "Hey Alice, can you help?" → `["Alice"]` (addressed)
- "I was talking to Alice about the project" → `null` (mentioned, not addressed)

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `VLLM_API_BASE` | `http://localhost:8000/v1` | URL of the OpenAI-compatible vLLM endpoint |
| `VLLM_API_KEY` | `EMPTY` | API Key (if required by the endpoint) |
| `VLLM_MODEL_NAME` | `meta-llama/Meta-Llama-3.1-8B-Instruct` | Model name to request |

## Usage

```python
from utils.text_speaker_detection import identify_speaker_from_transcript

# Regex path (instant):
speakers = await identify_speaker_from_transcript("I am Alice")
# ['Alice']

# LLM path (addressee detection):
speakers = await identify_speaker_from_transcript("Hey Bob, can you help?")
# ['Bob']

# LLM path (mention → null):
speakers = await identify_speaker_from_transcript("I told Bob about it")
# None
```

## Testing

Run unit tests (mocked, no API key needed):
```bash
cd backend
python3 -m pytest tests/test_text_speaker_detection.py -v
```

Run live integration demo against Groq (or any OpenAI-compatible endpoint):
```bash
export GROQ_API_KEY='your_key'
python3 tests/demo_real_integration.py
```
