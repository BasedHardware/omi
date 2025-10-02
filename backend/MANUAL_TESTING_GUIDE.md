# Manual Testing Guide - Speaker Name Identification

## Overview

This guide provides manual testing steps to verify the enhanced speaker name identification functionality.

## Prerequisites

- Python environment with Stanza installed
- Access to the Omi backend
- Test audio files (optional)

## Manual Testing Steps

### 1. Basic Functionality Test

#### Test NER Detection

```bash
# Navigate to backend directory
cd omi/backend

# Run Python interpreter
python

# Test basic functionality
from utils.speaker_identification import detect_speaker_from_text

# English test
result = detect_speaker_from_text("Hi, I'm Alice and I'll be your guide today.", "en")
print(f"English result: {result}")  # Should return "Alice"

# Spanish test
result = detect_speaker_from_text("Hola, me llamo Carlos y soy el doctor.", "es")
print(f"Spanish result: {result}")  # Should return "Carlos"

# French test
result = detect_speaker_from_text("Je vous présente Marie, notre experte.", "fr")
print(f"French result: {result}")  # Should return "Marie"

# Chinese test
result = detect_speaker_from_text("王伟会为大家解答问题。", "zh")
print(f"Chinese result: {result}")  # Should return "王伟"
```

#### Expected Results

- All tests should return the correct speaker names
- No errors should occur
- Processing should complete within 1 second

### 2. Fallback Testing

#### Test Regex Fallback

```python
# Test with text that should trigger regex fallback
result = detect_speaker_from_text("Let's get started with the meeting.", "en")
print(f"Fallback result: {result}")  # Should return None

# Test with text without names
result = detect_speaker_from_text("The weather is nice today.", "en")
print(f"No names result: {result}")  # Should return None
```

#### Expected Results

- Should gracefully fallback to regex
- Should return None for text without names
- No errors should occur

### 3. Error Handling Test

#### Test Invalid Inputs

```python
# Test with invalid language
result = detect_speaker_from_text("Hi, I'm Alice.", "invalid")
print(f"Invalid language result: {result}")  # Should handle gracefully

# Test with empty text
result = detect_speaker_from_text("", "en")
print(f"Empty text result: {result}")  # Should return None

# Test with None text
result = detect_speaker_from_text(None, "en")
print(f"None text result: {result}")  # Should return None
```

#### Expected Results

- Should handle invalid inputs gracefully
- Should not crash or throw exceptions
- Should return None for invalid inputs

### 4. Performance Testing

#### Test Processing Speed

```python
import time

# Test processing speed
start_time = time.time()
result = detect_speaker_from_text("Hi, I'm Alice and I'll be your guide today.", "en")
end_time = time.time()

processing_time = end_time - start_time
print(f"Processing time: {processing_time:.2f} seconds")  # Should be < 1 second
```

#### Expected Results

- Processing should complete within 1 second
- First run might be slower due to model loading
- Subsequent runs should be faster

### 5. Integration Testing

#### Test with Transcription Pipeline

```python
# Simulate transcript segments
segments = [
    {"text": "Hi, I'm Alice and I'll be your guide today.", "speaker": "SPEAKER_0"},
    {"text": "My name is Bob.", "speaker": "SPEAKER_1"},
    {"text": "Alice will now explain the next steps.", "speaker": "SPEAKER_0"},
]

# Test name detection on each segment
for segment in segments:
    result = detect_speaker_from_text(segment["text"], "en")
    print(f"Segment: {segment['text']}")
    print(f"Detected name: {result}")
    print("---")
```

#### Expected Results

- Should detect names correctly from transcript segments
- Should work with different speaker IDs
- Should handle various text formats

### 6. Multilingual Testing

#### Test All Supported Languages

```python
# Test all supported languages
test_cases = [
    ("Hi, I'm Alice.", "en", "Alice"),
    ("Hola, me llamo Carlos.", "es", "Carlos"),
    ("Je m'appelle Marie.", "fr", "Marie"),
    ("我是王伟。", "zh", "王伟"),
]

for text, lang, expected in test_cases:
    result = detect_speaker_from_text(text, lang)
    print(f"Language: {lang}")
    print(f"Text: {text}")
    print(f"Expected: {expected}")
    print(f"Result: {result}")
    print(f"Match: {expected in result if result else False}")
    print("---")
```

#### Expected Results

- Should work correctly for all supported languages
- Should return correct names for each language
- Should handle language-specific text formats

### 7. Edge Case Testing

#### Test Edge Cases

```python
# Test edge cases
edge_cases = [
    ("Hi, I'm A.", "en", None),  # Too short
    ("Hi, I'm Alice-Jane.", "en", "Alice-Jane"),  # Hyphenated name
    ("Hi, I'm O'Connor.", "en", "O'Connor"),  # Apostrophe
    ("Alice is here.", "en", "Alice"),  # Name at start
    ("Here is Alice.", "en", "Alice"),  # Name at end
    ("Alice, Bob, and Charlie are here.", "en", "Alice"),  # Multiple names
]

for text, lang, expected in edge_cases:
    result = detect_speaker_from_text(text, lang)
    print(f"Text: {text}")
    print(f"Expected: {expected}")
    print(f"Result: {result}")
    print(f"Match: {expected == result}")
    print("---")
```

#### Expected Results

- Should handle edge cases appropriately
- Should return None for invalid inputs
- Should handle special characters correctly

## Troubleshooting

### Common Issues

#### Model Loading Issues

- **Problem**: Stanza models not downloading
- **Solution**: Check internet connection and try again
- **Fallback**: System will use regex fallback

#### Performance Issues

- **Problem**: Slow processing
- **Solution**: First run is slower due to model loading
- **Expected**: Subsequent runs should be faster

#### Memory Issues

- **Problem**: High memory usage
- **Solution**: Models are cached per language
- **Expected**: Memory usage should stabilize after initial loading

### Verification Checklist

- [ ] Basic functionality works for all languages
- [ ] Fallback to regex works correctly
- [ ] Error handling works for invalid inputs
- [ ] Performance is acceptable (< 1 second)
- [ ] Integration with transcription pipeline works
- [ ] Edge cases are handled appropriately
- [ ] No memory leaks or excessive resource usage

```
