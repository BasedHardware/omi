"""Hermetic regression tests: extract_tweet_content must slice the same string
it searched.

TweetDetector.extract_tweet_content located the trigger phrase in a stripped,
lowercased copy of the transcript but used those offsets to slice the ORIGINAL
text, so every leading whitespace character moved the cut one character back
into the trigger phrase and the tail of the trigger was prepended to the
tweet: "  Tweet now hello" came back as "ow hello" and a transcript starting
with two newlines ("Tweet this AI is cool end tweet") as "is AI is cool".

Run: python3 plugins/omi-twitter-app/test_tweet_offsets.py
"""

import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

DETECTOR_PATH = Path(__file__).resolve().parent / "tweet_detector.py"


def _install_stubs():
    """Stub the OpenAI client and dotenv so tweet_detector.py imports offline."""
    openai = types.ModuleType("openai")
    openai.AsyncOpenAI = mock.Mock()
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None
    sys.modules["openai"] = openai
    sys.modules["dotenv"] = dotenv


def _load_detector():
    spec = importlib.util.spec_from_file_location("tweet_detector_under_test", DETECTOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TweetDetector


def _check(detector, text, expected):
    actual = detector.extract_tweet_content(text)
    assert actual == expected, f"{text!r} -> {actual!r}, expected {expected!r}"


def test_leading_spaces_do_not_shift_the_slice(detector):
    _check(detector, "  Tweet now hello", "hello")


def test_leading_newlines_with_end_phrase(detector):
    _check(detector, "\n\nTweet this AI is cool end tweet", "AI is cool")


def test_webhook_join_with_empty_first_segment(detector):
    # main_simple.py builds the detector input as " ".join(segment texts), so
    # an empty first segment puts a leading space in front of the trigger.
    text = " ".join(["", "Tweet now shipping the voice poster today"])
    _check(detector, text, "shipping the voice poster today")


def test_mixed_case_trigger_keeps_content_case(detector):
    _check(detector, "   TWEET NOW Big News from OMI", "Big News from OMI")


def test_no_leading_whitespace_control(detector):
    _check(detector, "Tweet now hello world", "hello world")


def test_trailing_whitespace_is_trimmed(detector):
    _check(detector, "Post tweet shipping today   \n", "shipping today")


def test_no_trigger_returns_none(detector):
    _check(detector, "  just chatting about lunch  ", None)


def main():
    _install_stubs()
    detector = _load_detector()
    tests = [
        test_leading_spaces_do_not_shift_the_slice,
        test_leading_newlines_with_end_phrase,
        test_webhook_join_with_empty_first_segment,
        test_mixed_case_trigger_keeps_content_case,
        test_no_leading_whitespace_control,
        test_trailing_whitespace_is_trimmed,
        test_no_trigger_returns_none,
    ]
    failures = 0
    for test in tests:
        try:
            test(detector)
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
    if failures:
        sys.exit(1)
    print(f"{len(tests)} tests passed")


if __name__ == "__main__":
    main()
