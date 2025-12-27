
# Speaker Identification Module

Integration with external self-hosted vLLM (OpenAI-compatible) for speaker identification and transcript cleaning.

**Fix for:** [Issue #3039](https://github.com/BasedHardware/omi/issues/3039) - Improve speaker detection using self-hosted LLM

## Overview

This module connects to an external LLM service (e.g., Llama-3.1-8B-Instruct hosted via vLLM) to:
1.  **Identify Addressees**: "Hey Alice" → `["Alice"]`
2.  **Clean Transcripts**: Removes fillers ("um", "uh") and fixes grammar.

## Configuration

The module uses environment variables to connect to the LLM service.

| Variable | Default | Description |
|----------|---------|-------------|
| `VLLM_API_BASE` | `http://localhost:8000/v1` | URL of the OpenAI-compatible vLLM endpoint |
| `VLLM_API_KEY` | `EMPTY` | API Key (if required by the endpoint) |
| `VLLM_MODEL_NAME` | `meta-llama/Meta-Llama-3.1-8B-Instruct` | Model name to request |

## Dependencies

- `openai`: Standard client for connecting to vLLM.

```bash
pip install openai
```

## Usage

```python
from backend.utils.speaker_identification import identify_speaker_and_clean_transcript

transcript = "Um, hey Alice... can you help?"
result = identify_speaker_and_clean_transcript(transcript)

print(result["speakers"])
# ['Alice']

print(result["cleaned_transcript"])
# "Hey Alice, can you help?"
```

## Testing

Run unit tests (mocked):
```bash
python3 -m pytest backend/tests/test_speaker_identification.py
```

Run verification script against live vLLM (or Groq):
```bash
python3 backend/tests/verify_llama_8b.py
```
