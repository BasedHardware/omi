
# Speaker Identification Module

Integration with an external self-hosted vLLM OpenAI-compatible endpoint for speaker self-identification.

**Fix for:** [Issue #3039](https://github.com/BasedHardware/omi/issues/3039) - Improve speaker detection using self-hosted LLM

## Overview

This module (`utils/text_speaker_detection.py`) adds optional LLM-based speaker self-identification alongside the existing regex-based self-identification.

**Pipeline:**
1. **Regex first** (0 ms, 0 tokens): Catches self-introductions like "I am Alice" instantly.
2. **Cue guard** (0 ms, 0 tokens): Skips LLM calls unless the segment looks like it may identify the current speaker.
3. **LLM fallback** (~200-300 ms): Uses Llama 3.1 8B via vLLM to detect the current speaker's own name.
4. **Background application**: The live transcription loop queues vLLM candidates instead of awaiting the network call inline.

**Key distinction — Speaker vs. Addressee/Mention:**
- "Hey, it's Alice" → `"Alice"` (speaker self-identification)
- "Hey Alice, can you help?" → `null` (Alice is addressed, not the speaker)
- "I was talking to Alice about the project" → `null` (Alice is mentioned, not the speaker)

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `VLLM_API_BASE` | unset | URL of the OpenAI-compatible vLLM endpoint. If unset, only the regex path runs. |
| `VLLM_API_KEY` | `EMPTY` | API Key (if required by the endpoint) |
| `VLLM_MODEL_NAME` | `meta-llama/Meta-Llama-3.1-8B-Instruct` | Model name to request |

## Usage

```python
from utils.text_speaker_detection import identify_speaker_from_transcript

# Regex path (instant):
speaker = await identify_speaker_from_transcript("I am Alice")
# 'Alice'

# LLM path (speaker self-identification):
speaker = await identify_speaker_from_transcript("Hey, it's Bob.")
# 'Bob'

# LLM path (addressee / mention → null):
speaker = await identify_speaker_from_transcript("I told Bob about it")
# None
```

## Testing

Run unit tests (mocked, no API key needed):
```bash
cd backend
python3 -m pytest tests/test_text_speaker_detection.py -v
```

Run the optional live integration demo against any OpenAI-compatible endpoint.
Groq is not required by the PR; it is just one possible smoke-test endpoint.

```bash
export GROQ_API_BASE='https://api.groq.com/openai/v1'
export GROQ_API_KEY='your_key'
export GROQ_MODEL='provider_model_name'
python3 tests/demo_real_integration.py
```

The demo intentionally requires an explicit `GROQ_MODEL` so it does not silently
depend on a provider-specific hosted model default.
