"""
OMI Speaker Identification — Live Integration Demo
===================================================
Runs against a real OpenAI-compatible API (Groq or self-hosted vLLM)
to produce end-to-end evidence for PR review.

Usage:
    export GROQ_API_BASE='https://api.groq.com/openai/v1'
    export GROQ_API_KEY='your_key'
    export GROQ_MODEL='provider_model_name'
    python backend/tests/demo_real_integration.py
"""

import json
import os
import sys
import time

from openai import OpenAI

# ---------------------------------------------------------------------------
# Path setup — allow running from repo root or backend/tests/
# ---------------------------------------------------------------------------
_here = os.path.dirname(os.path.abspath(__file__))
_backend = os.path.abspath(os.path.join(_here, ".."))
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from utils.text_speaker_detection import (
    SYSTEM_PROMPT,
    detect_speaker_from_text,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_BASE = os.environ.get("GROQ_API_BASE", "")
API_KEY = os.environ.get("GROQ_API_KEY", "")
MODEL = os.environ.get("GROQ_MODEL", "")

if not API_BASE:
    print("ERROR: GROQ_API_BASE environment variable not set.")
    print("  export GROQ_API_BASE='https://api.groq.com/openai/v1'")
    print("  # Or any OpenAI-compatible endpoint URL")
    sys.exit(1)
if not API_KEY:
    print("ERROR: GROQ_API_KEY environment variable not set.")
    print("  export GROQ_API_KEY='your_key'")
    sys.exit(1)
if not MODEL:
    print("ERROR: GROQ_MODEL environment variable not set.")
    print("  export GROQ_MODEL='provider_model_name'")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Test cases — each declares the expected outcome so we can auto-validate
# ---------------------------------------------------------------------------
TEST_CASES = [
    # --- Regex path (self-identification, no LLM call) ---
    {
        "input": "I am David",
        "expect_speaker": "David",
        "expect_method": "regex",
        "description": "Self-identification (regex)",
    },
    {
        "input": "My name is Alice",
        "expect_speaker": "Alice",
        "expect_method": "regex",
        "description": "Self-identification variant (regex)",
    },
    # --- LLM path: speaker self-identification ---
    {
        "input": "Hey, it's Alice from support.",
        "expect_speaker": "Alice",
        "expect_method": "llm",
        "description": "Self-identification with casual intro",
    },
    {
        "input": "This is Dr. Jane Smith speaking.",
        "expect_speaker": "Dr. Jane Smith",
        "expect_method": "llm",
        "description": "Self-identification with title",
    },
    # --- LLM path: addressees / mentions (should return null) ---
    {
        "input": "Hey Alice, could you send me that file?",
        "expect_speaker": None,
        "expect_method": "guard",
        "description": "Addressee — 'Hey Alice' (must be null)",
    },
    {
        "input": "Bob, Sarah, please join the meeting room.",
        "expect_speaker": None,
        "expect_method": "guard",
        "description": "Multiple addressees (must be null)",
    },
    {
        "input": "I was talking to Mike yesterday about the project.",
        "expect_speaker": None,
        "expect_method": "guard",
        "description": "Mention — 'talking to' (must be null)",
    },
    {
        "input": "I told Alice about the meeting.",
        "expect_speaker": None,
        "expect_method": "guard",
        "description": "Mention — 'told' (must be null)",
    },
    {
        "input": "I saw Bob at the store.",
        "expect_speaker": None,
        "expect_method": "guard",
        "description": "Mention — 'saw' (must be null)",
    },
    # --- LLM path: no names at all ---
    {
        "input": "Um, like, basically, I think we should, uh, start now.",
        "expect_speaker": None,
        "expect_method": "llm",
        "description": "No names, filler-heavy (must be null)",
    },
]


def run_regex(text: str):
    """Run the legacy regex path and return result + timing."""
    t0 = time.perf_counter()
    speaker = detect_speaker_from_text(text)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return speaker, elapsed_ms


def run_llm(client: OpenAI, text: str):
    """Run the LLM path and return parsed result + timing."""
    t0 = time.perf_counter()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f'Transcript: "{text}"'},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
        max_tokens=256,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000

    content = response.choices[0].message.content
    data = json.loads(content)
    speaker = data.get("speaker")
    if speaker is None and isinstance(data.get("speakers"), list) and len(data["speakers"]) == 1:
        speaker = data["speakers"][0]
    return speaker, elapsed_ms


def run_guard(text: str):
    """Run the local text speaker detection guard for non-speaker contexts."""
    speaker, elapsed_ms = run_regex(text)
    return speaker, elapsed_ms


def speaker_match(actual, expected):
    """Compare detected speaker names, treating empty strings as None."""
    return (actual or None) == expected


def main():
    client = OpenAI(base_url=API_BASE, api_key=API_KEY)

    print()
    print("=" * 60)
    print("  OMI SPEAKER IDENTIFICATION — LIVE INTEGRATION DEMO")
    print("=" * 60)
    print(f"  Endpoint : {API_BASE}")
    print(f"  Model    : {MODEL}")
    print("=" * 60)
    print()

    passed = 0
    failed = 0

    for i, tc in enumerate(TEST_CASES, 1):
        text = tc["input"]
        expected = tc["expect_speaker"]
        method = tc["expect_method"]
        desc = tc["description"]

        print(f"[TEST {i}] {desc}")
        print(f"  Input   : \"{text}\"")

        if method == "regex":
            speaker, ms = run_regex(text)
            print(f"  Method  : Regex (local)")
            print(f"  Time    : {ms:.0f} ms")
            print(f"  Result  : {speaker}")
        elif method == "guard":
            speaker, ms = run_guard(text)
            print(f"  Method  : Guard (local, no LLM)")
            print(f"  Time    : {ms:.0f} ms")
            print(f"  Result  : {speaker}")
        else:
            speaker, ms = run_llm(client, text)
            print(f"  Method  : LLM (API)")
            print(f"  Time    : {ms:.0f} ms")
            print(f"  Speaker : {speaker}")

        ok = speaker_match(speaker, expected)
        if ok:
            print(f"  Status  : PASS")
            passed += 1
        else:
            print(f"  Status  : FAIL (expected {expected}, got {speaker})")
            failed += 1

        print("-" * 60)

    print()
    print("=" * 60)
    total = passed + failed
    print(f"  RESULTS: {passed}/{total} passed, {failed} failed")
    if failed == 0:
        print("  ALL TESTS PASSED")
    print("=" * 60)
    print()

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
