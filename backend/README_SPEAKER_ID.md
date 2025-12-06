# Speaker Identification Module

Self-hosted LLM-based speaker identification for the Omi wearable project.

**Fix for:** [Issue #3039](https://github.com/BasedHardware/omi/issues/3039) - Improve speaker detection using self-hosted LLM

## Overview

Replaces the regex-based speaker detection with a Qwen2.5-1.5B-Instruct LLM that can distinguish between:
- **Addressed**: "Hey Alice, can you help?" → `["Alice"]`
- **Mentioned**: "I told Alice about it" → `None`

## Setup

### 1. Install Dependency

```bash
pip install llama-cpp-python
```

For GPU acceleration:
```bash
# Mac (Metal)
CMAKE_ARGS="-DGGML_METAL=on" pip install llama-cpp-python --force-reinstall

# NVIDIA (CUDA)  
CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --force-reinstall
```

### 2. Download Model

```bash
curl -L -o backend/utils/qwen_1.5b_speaker.gguf \
  https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf
```

## Usage

```python
from backend.utils.speaker_identification import identify_speaker_from_transcript

# Returns list of speakers or None
speakers = identify_speaker_from_transcript("Hey Alice and Bob, can you help?")
# Result: ['Alice', 'Bob']

speakers = identify_speaker_from_transcript("I told Alice about the meeting")
# Result: None

# Legacy function (returns single string)
from backend.utils.speaker_identification import detect_speaker_from_text
name = detect_speaker_from_text("Hey Alice, help me")
# Result: 'Alice'
```

## Performance

| Metric | Value |
|--------|-------|
| Accuracy | 100% on test suite |
| Avg Latency | ~300ms (GPU) |
| Model Size | 1.1 GB |
| License | Apache 2.0 |

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SPEAKER_MODEL_PATH` | `backend/utils/qwen_1.5b_speaker.gguf` | Path to GGUF model |

## Files

```
backend/utils/
├── speaker_identification.py  # Main module
└── qwen_1.5b_speaker.gguf     # Model file (not in git)
```

## Testing

```bash
python3 -c "
from backend.utils.speaker_identification import identify_speaker_from_transcript
print(identify_speaker_from_transcript('Hey Alice, can you help?'))
"
# Output: ['Alice']
```
