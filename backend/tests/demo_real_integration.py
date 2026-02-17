"""
OMI Speaker Identification — Live Integration Demo
===================================================
Runs against a real OpenAI-compatible API (Groq or self-hosted vLLM)
to produce end-to-end evidence for PR review.

Usage:
    export GROQ_API_KEY='your_key'
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
API_BASE = os.environ.get("GROQ_API_BASE", "https://api.groq.com/openai/v1")
API_KEY = os.environ.get("GROQ_API_KEY", "")
MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

if not API_KEY:
    print("ERROR: GROQ_API_KEY environment variable not set.")
    print("  export GROQ_API_KEY='your_key'")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Test cases — each declares the expected outcome so we can auto-validate
# ---------------------------------------------------------------------------
TEST_CASES = [
    # --- Regex path (self-identification, no LLM call) ---
    {
        "input": "I am David",
        "expect_speakers": ["David"],
        "expect_method": "regex",
        "description": "Self-identification (regex)",
    },
    {
        "input": "My name is Alice",
        "expect_speakers": ["Alice"],
        "expect_method": "regex",
        "description": "Self-identification variant (regex)",
    },
    # --- LLM path: addressed speakers ---
    {
        "input": "Hey Alice, could you send me that file?",
        "expect_speakers": ["Alice"],
        "expect_method": "llm",
        "description": "Single addressee",
    },
    {
        "input": "Bob, Sarah, please join the meeting room.",
        "expect_speakers": ["Bob", "Sarah"],
        "expect_method": "llm",
        "description": "Multiple addressees",
    },
    # --- LLM path: mentions (should return null) ---
    {
        "input": "I was talking to Mike yesterday about the project.",
        "expect_speakers": None,
        "expect_method": "llm",
        "description": "Mention — 'talking to' (must be null)",
    },
    {
        "input": "I told Alice about the meeting.",
        "expect_speakers": None,
        "expect_method": "llm",
        "description": "Mention — 'told' (must be null)",
    },
    {
        "input": "I saw Bob at the store.",
        "expect_speakers": None,
        "expect_method": "llm",
        "description": "Mention — 'saw' (must be null)",
    },
    # --- LLM path: no names at all ---
    {
        "input": "Um, like, basically, I think we should, uh, start now.",
        "expect_speakers": None,
        "expect_method": "llm",
        "description": "No names, filler-heavy (must be null + cleaned)",
    },
]


def run_regex(text: str):
    """Run the legacy regex path and return result + timing."""
    t0 = time.perf_counter()
    name = detect_speaker_from_text(text)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    speakers = [name] if name else None
    return speakers, elapsed_ms


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
    speakers = data.get("speakers")
    # Normalize empty list to None for comparison
    if speakers is not None and len(speakers) == 0:
        speakers = None
    cleaned = data.get("cleaned_transcript", "")
    return speakers, cleaned, elapsed_ms


def speakers_match(actual, expected):
    """Compare speaker lists, treating None and [] as equivalent."""
    if expected is None:
        return actual is None or actual == []
    if actual is None:
        return False
    return sorted(actual) == sorted(expected)


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
        expected = tc["expect_speakers"]
        method = tc["expect_method"]
        desc = tc["description"]

        print(f"[TEST {i}] {desc}")
        print(f"  Input   : \"{text}\"")

        if method == "regex":
            speakers, ms = run_regex(text)
            print(f"  Method  : Regex (local)")
            print(f"  Time    : {ms:.0f} ms")
            print(f"  Result  : {speakers}")
        else:
            speakers, cleaned, ms = run_llm(client, text)
            print(f"  Method  : LLM (API)")
            print(f"  Time    : {ms:.0f} ms")
            print(f"  Speakers: {speakers}")
            print(f"  Cleaned : \"{cleaned}\"")

        ok = speakers_match(speakers, expected)
        if ok:
            print(f"  Status  : PASS")
            passed += 1
        else:
            print(f"  Status  : FAIL (expected {expected}, got {speakers})")
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
