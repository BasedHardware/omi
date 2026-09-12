"""Hermetic regression tests for omi_plugin_sdk.models.combine_segments.

Standard library only: pydantic is replaced with a minimal stub before
importing the module under test so the suite runs without site-packages
(the manifest lane runs plain python3). The stub covers only the surface
models.py needs: BaseModel accepts kwargs, Field returns its
default/default_factory(), and the validators pass through unapplied.

Covers the whitespace-corruption bug: the SDK copy of combine_segments
normalized double spaces with .replace("  ", "") — deleting them entirely
and joining words ("hello  world" -> "helloworld"). The backend reference
implementation (backend/models/transcript_segment.py) collapses them to a
single space with .replace("  ", " ").
"""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))


def _install_pydantic_stub():
    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)

    def Field(*args, **kwargs):
        if "default_factory" in kwargs:
            return kwargs["default_factory"]()
        if "default" in kwargs:
            return kwargs["default"]
        return args[0] if args else None

    def _passthrough_decorator(*args, **kwargs):
        def wrap(fn):
            return fn

        return wrap

    pydantic.BaseModel = BaseModel
    pydantic.Field = Field
    pydantic.field_validator = _passthrough_decorator
    pydantic.model_validator = _passthrough_decorator
    sys.modules["pydantic"] = pydantic


_saved_pydantic = sys.modules.get("pydantic")
_install_pydantic_stub()
try:
    from omi_plugin_sdk.models import TranscriptSegment
finally:
    if _saved_pydantic is None:
        sys.modules.pop("pydantic", None)
    else:
        sys.modules["pydantic"] = _saved_pydantic
    del _saved_pydantic


def _seg(text, speaker="SPEAKER_00", is_user=False, start=0.0, end=1.0):
    return TranscriptSegment(text=text, speaker=speaker, is_user=is_user, start=start, end=end)


class CombineSegmentsTests(unittest.TestCase):
    def test_double_spaces_collapse_not_deleted(self):
        out = TranscriptSegment.combine_segments([], [_seg("hello  world")])
        self.assertEqual(out[0].text, "hello world")

    def test_double_space_after_sentence_boundary(self):
        out = TranscriptSegment.combine_segments([], [_seg("First sentence.  Second sentence.")])
        self.assertEqual(out[0].text, "First sentence. Second sentence.")

    def test_existing_spacing_fixups_preserved(self):
        out = TranscriptSegment.combine_segments([], [_seg("one , two . three ?")])
        self.assertEqual(out[0].text, "one, two. three?")

    def test_same_speaker_segments_merge_with_space(self):
        out = TranscriptSegment.combine_segments([], [_seg("hello", end=1.0), _seg("world", start=1.0, end=2.0)])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].text, "hello world")
        self.assertEqual(out[0].end, 2.0)

    def test_no_new_segments_returns_existing(self):
        existing = [_seg("keep me")]
        out = TranscriptSegment.combine_segments(existing, [])
        self.assertIs(out, existing)
        self.assertEqual(out[0].text, "keep me")

    def test_different_speakers_stay_split(self):
        out = TranscriptSegment.combine_segments(
            [], [_seg("hello", speaker="SPEAKER_00"), _seg("hi", speaker="SPEAKER_01", start=1.0, end=2.0)]
        )
        self.assertEqual(len(out), 2)
        self.assertEqual([s.text for s in out], ["hello", "hi"])


if __name__ == "__main__":
    unittest.main()
