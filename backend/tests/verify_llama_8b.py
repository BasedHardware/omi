
import sys
import os
import time
import json
import difflib
from typing import List, Optional
from openai import APIConnectionError, OpenAI

# Add backend to path to import existing utils
# Assuming this script run from omi/ (repo root) or omi/backend/tests/
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from backend.utils.text_speaker_detection import SYSTEM_PROMPT as FULL_SYSTEM_PROMPT
    from backend.utils.text_speaker_detection import identify_speaker_and_clean_transcript
except ImportError:
    try:
        from utils.text_speaker_detection import SYSTEM_PROMPT as FULL_SYSTEM_PROMPT
        from utils.text_speaker_detection import identify_speaker_and_clean_transcript
    except ImportError:
         # Fallback if run from omi/backend/tests/
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
        from utils.text_speaker_detection import SYSTEM_PROMPT as FULL_SYSTEM_PROMPT
        from utils.text_speaker_detection import identify_speaker_and_clean_transcript

# -------------------------------------------------------------------------
# 1. PROMPT
# -------------------------------------------------------------------------
# The SYSTEM_PROMPT from the module already includes cleaning instructions.
# No need to append anything.

# -------------------------------------------------------------------------
# 2. CONFIGURATION
# -------------------------------------------------------------------------
# Using Groq API as requested
VLLM_BASE_URL = "https://api.groq.com/openai/v1"
API_KEY = os.environ.get("GROQ_API_KEY", "")
MODEL_NAME = "llama-3.1-8b-instant"  # Groq's Llama 3.1 8B model

if not API_KEY:
    print("⚠️  WARNING: GROQ_API_KEY environment variable not set.")
    print("   Please run: export GROQ_API_KEY='your_key'")
    sys.exit(1)

def measure_semantic_accuracy(clean_text: str, expected_text: str) -> float:
    """Calculate similarity ratio between produced and expected clean text."""
    matcher = difflib.SequenceMatcher(None, clean_text, expected_text)
    return matcher.ratio() * 100

def run_tests():
    print(f"🚀 Connecting to Groq API at {VLLM_BASE_URL}...")
    
    client = OpenAI(
        base_url=VLLM_BASE_URL,
        api_key=API_KEY,
    )

    test_cases = [
        {
            "id": 1,
            "input": "Um, so, Alice... can you, uh, help me with the, you know, report?",
            "expected_speakers": ["Alice"],
            "expected_clean": "Alice, can you help me with the report?"
        },
        {
            "id": 2,
            "input": "I told Alice about the meeting.",
            "expected_speakers": None,
            "expected_clean": "I told Alice about the meeting."
        },
        {
            "id": 3,
            "input": "hey bob, uh, did you see the... the email?",
            "expected_speakers": ["Bob"],
            "expected_clean": "Hey Bob, did you see the email?"
        }
    ]

    print(f"\n📋 Running {len(test_cases)} stress tests with Llama-3.1-8B-Instruct\n")
    print("-" * 80)

    total_latency = 0
    passed = 0

    for test in test_cases:
        print(f"Test ID: {test['id']}")
        print(f"Input:   '{test['input']}'")
        
        start_time = time.perf_counter()
        
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": FULL_SYSTEM_PROMPT},
                    {"role": "user", "content": f'Transcript: "{test["input"]}"'}
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=1024
            )
            
            end_time = time.perf_counter()
            latency_ms = (end_time - start_time) * 1000
            total_latency += latency_ms
            
            # Metrics from API
            usage = response.usage
            prompt_tokens = usage.prompt_tokens if usage else 0
            completion_tokens = usage.completion_tokens if usage else 0
            
            # Parsing
            content = response.choices[0].message.content
            try:
                data = json.loads(content)
                speakers = data.get("speakers")
                clean_transcript = data.get("cleaned_transcript", "")
            except json.JSONDecodeError:
                print("❌ Failed to decode JSON response")
                print(f"Raw Output: {content}")
                continue

            # Validation
            # 1. Speakers
            match_speakers = False
            if test['expected_speakers'] is None:
                match_speakers = (speakers is None or speakers == [] or speakers == "null")
            else:
                match_speakers = (speakers == test['expected_speakers'])
            
            # 2. Semantic Accuracy
            acc_score = measure_semantic_accuracy(clean_transcript, test['expected_clean'])
            
            print(f"Result:  {json.dumps(data, indent=0)}")
            print(f"Latency: {latency_ms:.2f}ms")
            print(f"Tokens:  In={prompt_tokens} / Out={completion_tokens}")
            print(f"Acc:     {acc_score:.1f}% (Semantic Similarity)")
            
            if match_speakers and acc_score > 90.0:
                print("Status:  ✅ PASS")
                passed += 1
            else:
                print("Status:  ❌ FAIL")
                if not match_speakers:
                    print(f"  -> Speaker Mismatch: Expected {test['expected_speakers']}, Got {speakers}")
                if acc_score <= 90.0:
                    print(f"  -> Clean Text Mismatch: Expected '{test['expected_clean']}'")

        except APIConnectionError:
            print("❌ Connection Failed. Is vLLM running?")
            print(f"   Run: vllm serve {MODEL_NAME} --port 8000")
            return
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print("-" * 80)

    print(f"\nSummary: {passed}/{len(test_cases)} Passed")
    if passed > 0:
        print(f"Avg Latency: {total_latency / len(test_cases):.2f}ms")

if __name__ == "__main__":
    run_tests()
