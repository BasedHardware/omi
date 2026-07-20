"""Regression: a mentor segment whose ``start`` is a legitimate 0.0 (the first utterance of a
capture) must keep that timestamp, not be stamped with wall-clock time and sorted to the end of the
chronologically ordered mentor context handed to the proactive-notification LLM.

``utils.mentor_notifications`` imports ``database.notifications`` (Firestore) at import time, so it
is loaded through the sanctioned ``stub_modules`` / ``load_module_fresh`` seam rather than imported
directly. Each load gets a fresh module-global ``message_buffer``, so no state leaks between tests.
"""

from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


@contextmanager
def _loaded_mentor(frequency: int = 3) -> Iterator[ModuleType]:
    stubs = {
        'database.notifications': _module(
            'database.notifications',
            get_mentor_notification_frequency=lambda _uid: frequency,
        ),
    }
    with stub_modules(stubs):
        mentor = load_module_fresh(
            'utils.mentor_notifications',
            str(BACKEND_DIR / 'utils' / 'mentor_notifications.py'),
        )
        yield mentor


def _spaced_segments(first_start: float) -> list[dict[str, Any]]:
    """Ten segments (== MIN_NEW_SEGMENTS_FOR_ANALYSIS) whose first starts at ``first_start``.

    Starts are 10s apart and ``is_user`` alternates so none coalesce (the buffer only merges
    consecutive same-speaker segments within 2s), yielding ten distinct messages that trigger a
    return.
    """
    segments = [{'text': 'opening line', 'start': first_start, 'is_user': True}]
    for i in range(1, 10):
        segments.append({'text': f'line {i}', 'start': float(i * 10), 'is_user': i % 2 == 0})
    return segments


def test_first_segment_start_zero_stays_first_in_sorted_context() -> None:
    with _loaded_mentor() as mentor:
        result = mentor.process_mentor_notification('user-zero-start', _spaced_segments(0.0))

        assert result is not None
        # Direct bug assertion: the opening line keeps its real capture start of 0.0. On the unfixed
        # ``... or current_time`` code this is wall-clock time (~1.78e9).
        opening = next(m for m in result if m['text'] == 'opening line')
        assert opening['timestamp'] == 0.0
        # And therefore stays first in the timestamp-sorted context handed to the mentor LLM.
        assert result[0]['text'] == 'opening line'


def test_missing_segment_start_still_falls_back_to_wall_clock() -> None:
    """The fix must preserve the original fallback: a segment with no ``start`` still gets a
    wall-clock timestamp (not 0.0, not a crash)."""
    with _loaded_mentor() as mentor:
        # No 'start' key at all; alternate is_user so the ten messages stay distinct.
        segments = [{'text': f'line {i}', 'is_user': i % 2 == 0} for i in range(10)]

        result = mentor.process_mentor_notification('user-missing-start', segments)

        assert result is not None
        # 1e9 seconds is ~year 2001; every real wall-clock stamp is well above it.
        assert all(m['timestamp'] > 1_000_000_000 for m in result)
