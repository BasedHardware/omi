"""Hermetic regression: TweetDetector.extract_tweet_content() must anchor
the content slice in the ORIGINAL text.

The trigger phrase is located inside normalize_text(text)
(= text.lower().strip()), but the old code applied that index to the
original string, so every character of leading whitespace shifted the
cut one character back into the trigger phrase:

    "  Tweet now hello"   ->  "ow hello"   (expected "hello")
    "\\n\\nTweet this AI is cool end tweet" ->  "is AI is cool"
    " Tweet now shipping" ->  "w shipping the voice poster today"

The webhook joins segment texts with " ".join(...), so a leading-space
or empty first segment makes this reachable in production.

Run: python3 plugins/test_tweet_content_offsets.py
"""

import sys
import types
from pathlib import Path
from unittest import mock

# tweet_detector imports the OpenAI client and python-dotenv at module
# load; stub both so the suite stays hermetic (no SDK, no network, no
# environment-specific dependencies).
_openai = types.ModuleType("openai")
_openai.AsyncOpenAI = lambda *a, **k: mock.MagicMock(name="AsyncOpenAI")
sys.modules.setdefault("openai", _openai)

_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *a, **k: None
sys.modules.setdefault("dotenv", _dotenv)

# the detector lives inside the plugin dir; the manifest runs this test
# from the repository root
sys.path.insert(0, str(Path(__file__).resolve().parent / "omi-twitter-app"))

from tweet_detector import TweetDetector  # noqa: E402

CASES = [
    # (transcript, expected content) — exact repros from the issue
    ("  Tweet now hello", "hello"),
    ("\n\nTweet this AI is cool end tweet", "AI is cool"),
    (" Tweet now shipping the voice poster today", "shipping the voice poster today"),
    # trigger matching must stay case-insensitive and case-preserving
    ("Tweet NOW Mixed Case Content", "Mixed Case Content"),
    ("\tPost Tweet  alpha beta", "alpha beta"),
    # end-phrase stripping still applies
    ("tweet now my update end tweet", "my update"),
    # multiple triggers: the first occurrence still anchors the slice
    # (the comma is retained — strip() removes whitespace only, matching
    # the pre-existing behavior)
    ("tweet now, tweet now second call", ", tweet now second call"),
    # no trigger -> None (existing contract)
    ("just a normal sentence", None),
    # trigger with nothing after it -> None (existing contract)
    ("tweet now", None),
]


def run():
    failures = []
    for text, expected in CASES:
        got = TweetDetector.extract_tweet_content(text)
        status = "PASS" if got == expected else "FAIL"
        print(f"{status} extract({text!r}) -> {got!r} (expected {expected!r})")
        if got != expected:
            failures.append((text, expected, got))

    # whitespace-only content after the trigger still yields None
    got = TweetDetector.extract_tweet_content("tweet now    ")
    print(f"{'PASS' if got is None else 'FAIL'} extract('tweet now    ') -> {got!r} (expected None)")
    if got is not None:
        failures.append(("tweet now    ", None, got))

    if failures:
        print(f"\n{len(failures)} FAILED")
        sys.exit(1)
    print(f"\n{len(CASES) + 1} passed")


if __name__ == "__main__":
    run()
