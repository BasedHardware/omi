"""Hermetic regression tests for the Twitter recording accumulator.

The production module initializes FastAPI, OAuth clients and storage at import
time, so these tests load only the production ``TweetDetector`` and
``process_segments`` definitions.  All network and posting boundaries are
small in-memory fakes; no credentials or services are touched.
"""

from __future__ import annotations

import ast
import asyncio
import re
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PLUGIN_DIR = Path(__file__).resolve().parent

if hasattr(sys.stdout, "reconfigure"):
    # Production logging uses emoji; keep the hermetic test portable on the
    # Windows code-page runners used by contributors as well as UTF-8 CI.
    sys.stdout.reconfigure(encoding="utf-8")


def _load_definition(path: Path, name: str, namespace: Dict[str, Any]) -> Any:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    node = next(
        node for node in tree.body if getattr(node, "name", None) == name
    )
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[name]


class _SessionStorage:
    """Minimal seam with the same methods used by ``process_segments``."""

    sessions: Dict[str, dict] = {}

    @classmethod
    def update_session(cls, session_id: str, **kwargs: Any) -> None:
        cls.sessions[session_id].update(kwargs)

    @classmethod
    def reset_session(cls, session_id: str) -> None:
        cls.sessions[session_id].update(
            tweet_mode="idle",
            tweet_content="",
            segments_count=0,
            accumulated_text="",
        )


class _TwitterClient:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, str]] = []

    async def post_tweet(self, access_token: str, content: str) -> dict:
        self.calls.append((access_token, content))
        return {"success": True, "tweet_id": "fixture-1"}


class _Detector:
    """Use the production trigger/extraction logic with a deterministic AI seam."""

    def __init__(self, detector_cls: Any) -> None:
        self._detector = detector_cls()

    def detect_trigger(self, text: str) -> bool:
        return self._detector.detect_trigger(text)

    def extract_tweet_content(self, text: str) -> Optional[str]:
        return self._detector.extract_tweet_content(text)

    async def ai_extract_tweet_from_segments(self, text: str) -> str:
        # The real method is an OpenAI boundary.  Returning deterministic text
        # exercises the production posting/reset path without network access.
        return "A useful update"


def _load_process_segments() -> Tuple[Any, _TwitterClient]:
    detector_ns: Dict[str, Any] = {
        "re": re,
        "Optional": Optional,
        "Tuple": Tuple,
    }
    detector_cls = _load_definition(
        PLUGIN_DIR / "tweet_detector.py", "TweetDetector", detector_ns
    )
    twitter_client = _TwitterClient()
    detector = _Detector(detector_cls)
    process_ns: Dict[str, Any] = {
        "List": List,
        "Dict": Dict,
        "Any": Any,
        "SimpleSessionStorage": _SessionStorage,
        "tweet_detector": detector,
        "twitter_client": twitter_client,
    }
    process = _load_definition(
        PLUGIN_DIR / "main_simple.py", "process_segments", process_ns
    )
    return process, twitter_client


PROCESS_SEGMENTS, TWITTER_CLIENT = _load_process_segments()


def _session(**overrides: Any) -> dict:
    value = {
        "session_id": "fixture",
        "tweet_mode": "idle",
        "segments_count": 0,
        "accumulated_text": "",
    }
    value.update(overrides)
    _SessionStorage.sessions[value["session_id"]] = value
    return value


class RecordingAccumulatorTests(unittest.TestCase):
    def setUp(self) -> None:
        _SessionStorage.sessions.clear()
        TWITTER_CLIENT.calls.clear()

    def run_async(self, awaitable: Any) -> Any:
        return asyncio.run(awaitable)

    def test_bare_trigger_stores_empty_string(self) -> None:
        session = _session()
        result = self.run_async(
            PROCESS_SEGMENTS(session, [{"text": "Tweet now"}], {"access_token": "fixture"})
        )
        self.assertEqual(result, "collecting_1")
        self.assertEqual(session["accumulated_text"], "")
        self.assertIs(type(session["accumulated_text"]), str)

    def test_trigger_content_is_preserved(self) -> None:
        session = _session()
        self.run_async(
            PROCESS_SEGMENTS(
                session,
                [{"text": "Tweet now A useful update"}],
                {"access_token": "fixture"},
            )
        )
        self.assertEqual(session["accumulated_text"], "A useful update")

    def test_null_legacy_accumulator_can_resume(self) -> None:
        session = _session(
            tweet_mode="recording", segments_count=1, accumulated_text=None
        )
        result = self.run_async(
            PROCESS_SEGMENTS(session, [{"text": "A useful update"}], {"access_token": "fixture"})
        )
        self.assertEqual(result, "collecting_2")
        self.assertEqual(session["accumulated_text"].strip(), "A useful update")

    def test_missing_legacy_accumulator_can_resume(self) -> None:
        session = _session(tweet_mode="recording", segments_count=1)
        del session["accumulated_text"]
        result = self.run_async(
            PROCESS_SEGMENTS(session, [{"text": "A useful update"}], {"access_token": "fixture"})
        )
        self.assertEqual(result, "collecting_2")
        self.assertEqual(session["accumulated_text"].strip(), "A useful update")

    def test_empty_string_accumulator_can_resume(self) -> None:
        session = _session(tweet_mode="recording", segments_count=1, accumulated_text="")
        result = self.run_async(
            PROCESS_SEGMENTS(session, [{"text": "A useful update"}], {"access_token": "fixture"})
        )
        self.assertEqual(result, "collecting_2")
        self.assertEqual(session["accumulated_text"].strip(), "A useful update")

    def test_second_segment_does_not_post_early(self) -> None:
        session = _session(tweet_mode="recording", segments_count=1, accumulated_text="Start")
        result = self.run_async(
            PROCESS_SEGMENTS(session, [{"text": "middle"}], {"access_token": "fixture"})
        )
        self.assertEqual(result, "collecting_2")
        self.assertEqual(TWITTER_CLIENT.calls, [])

    def test_third_segment_posts_and_resets(self) -> None:
        session = _session(tweet_mode="recording", segments_count=2, accumulated_text="Start middle")
        result = self.run_async(
            PROCESS_SEGMENTS(session, [{"text": "final"}], {"access_token": "fixture"})
        )
        self.assertTrue(result.startswith("✅ Tweet posted:"))
        self.assertEqual(TWITTER_CLIENT.calls, [("fixture", "A useful update")])
        self.assertEqual(session["tweet_mode"], "idle")
        self.assertEqual(session["segments_count"], 0)
        self.assertEqual(session["accumulated_text"], "")

    def test_non_trigger_is_passive(self) -> None:
        session = _session()
        before = session.copy()
        result = self.run_async(
            PROCESS_SEGMENTS(session, [{"text": "ordinary speech"}], {"access_token": "fixture"})
        )
        self.assertEqual(result, "listening")
        self.assertEqual(session, before)
        self.assertEqual(TWITTER_CLIENT.calls, [])

    def test_trigger_only_phrase_is_the_nullable_detector_case(self) -> None:
        session = _session()
        # The detector intentionally returns None for an empty body; the
        # recording transition must normalize that value before persistence.
        self.assertIsNone(PROCESS_SEGMENTS.__globals__["tweet_detector"].extract_tweet_content("Tweet now"))
        self.run_async(
            PROCESS_SEGMENTS(session, [{"text": "Tweet now"}], {"access_token": "fixture"})
        )
        self.assertNotIn(None, session.values())

    def test_multiple_segments_accumulate_without_type_error(self) -> None:
        session = _session()
        for text in ("Tweet now", "A useful", "update"):
            self.run_async(
                PROCESS_SEGMENTS(session, [{"text": text}], {"access_token": "fixture"})
            )
        self.assertEqual(len(TWITTER_CLIENT.calls), 1)


if __name__ == "__main__":
    unittest.main()
