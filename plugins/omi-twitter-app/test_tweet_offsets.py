"""Regression test: extract_tweet_content must not shift its slice on leading whitespace.

`TweetDetector.extract_tweet_content()` located the trigger phrase inside a
normalized (lowered and stripped) copy of the text but applied that offset to
the original string. `normalize_text()` calls `.strip()`, so every leading
whitespace character moved the cut one character further back into the trigger
phrase, prepending the tail of the trigger to the tweet:

    "  Tweet now hello"  ->  "ow hello"   (expected "hello")

The webhook joins segment texts with `" ".join(...)`, so an empty first segment
(the common case for a streamed transcript) triggered this on the very first
"Tweet now".

Hermetic: stubs the module's non-stdlib imports (`openai`, `dotenv`) and loads
the real module, so it runs offline with the standard library only.
"""

import importlib.util
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))

# (text, expected tweet content) — the first four are the reported regressions.
CASES = [
    ("  Tweet now hello", "hello"),
    ("\n\nTweet this AI is cool end tweet", "AI is cool"),
    (" Tweet now shipping the voice poster today", "shipping the voice poster today"),
    ("   TWEET NOW Big News from OMI", "Big News from OMI"),
    # Controls: no leading whitespace, trailing whitespace, and no trigger at all.
    ("Tweet now hello", "hello"),
    ("Tweet now hello   ", "hello"),
    ("no trigger here", None),
]


def _stub(name, **attrs):
    if name not in sys.modules:
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module


def _load_detector():
    _stub("openai", AsyncOpenAI=type("AsyncOpenAI", (), {"__init__": lambda self, *a, **k: None}))
    _stub("dotenv", load_dotenv=lambda *a, **k: None)
    spec = importlib.util.spec_from_file_location(
        "tweet_detector", os.path.join(HERE, "tweet_detector.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["tweet_detector"] = module
    spec.loader.exec_module(module)
    return module


def test_leading_whitespace_does_not_shift_the_slice():
    detector = _load_detector().TweetDetector
    content = detector.extract_tweet_content("  Tweet now hello")
    assert content == "hello", f"got {content!r}, expected 'hello'"


def test_leading_newlines_with_end_phrase():
    detector = _load_detector().TweetDetector
    content = detector.extract_tweet_content("\n\nTweet this AI is cool end tweet")
    assert content == "AI is cool", f"got {content!r}, expected 'AI is cool'"


def test_webhook_join_with_empty_first_segment():
    detector = _load_detector().TweetDetector
    content = detector.extract_tweet_content(
        " Tweet now shipping the voice poster today"
    )
    assert content == "shipping the voice poster today", f"got {content!r}"


def test_mixed_case_trigger_keeps_content_case():
    detector = _load_detector().TweetDetector
    content = detector.extract_tweet_content("   TWEET NOW Big News from OMI")
    assert content == "Big News from OMI", f"got {content!r}"


def test_no_leading_whitespace_control():
    detector = _load_detector().TweetDetector
    assert detector.extract_tweet_content("Tweet now hello") == "hello"


def test_trailing_whitespace_is_trimmed():
    detector = _load_detector().TweetDetector
    assert detector.extract_tweet_content("Tweet now hello   ") == "hello"


def test_no_trigger_returns_none():
    detector = _load_detector().TweetDetector
    assert detector.extract_tweet_content("no trigger here") is None


def main():
    detector = _load_detector().TweetDetector
    failures = 0
    for text, expected in CASES:
        actual = detector.extract_tweet_content(text)
        ok = actual == expected
        failures += not ok
        print(
            f"{'PASS' if ok else 'FAIL'} {text!r} -> {actual!r}"
            + ("" if ok else f", expected {expected!r}")
        )
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
