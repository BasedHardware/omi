"""Tests for utils/screen_frames/judge.py (contract §4 steps 3-4).

The core property under test: "malformed output, timeout, or any other
outcome fails closed" — judge_frame must raise ScreenFrameJudgeError (never
return something a caller could mistake for approval) whenever the
underlying model call doesn't produce a clean, self-consistent
ScreenFrameJudgement.
"""

from unittest.mock import MagicMock

import pytest

from models.screen_frame import ScreenFrameJudgement
from utils.screen_frames import judge as judge_mod
from utils.screen_frames import policy as policy_mod
from utils.screen_frames.judge import ScreenFrameJudgeError, judge_frame

UID = "user-1"


def _fake_llm(structured_output):
    """Build a fake get_llm(...) return value whose
    with_structured_output(...).invoke([...]) returns structured_output (or
    raises it, if it's an exception instance)."""
    llm = MagicMock()
    structured = MagicMock()
    if isinstance(structured_output, Exception):
        structured.invoke.side_effect = structured_output
    else:
        structured.invoke.return_value = structured_output
    llm.with_structured_output.return_value = structured
    return llm


class TestFailsClosedOnMalformedOutput:
    def test_raises_on_provider_exception(self, monkeypatch):
        monkeypatch.setattr(judge_mod, "get_llm", lambda feature: _fake_llm(RuntimeError("provider timeout")))
        with pytest.raises(ScreenFrameJudgeError):
            judge_frame(UID, b"fake-jpeg-bytes")

    def test_raises_when_response_is_not_a_judgement(self, monkeypatch):
        # e.g. the structured-output parser silently degrades to a raw dict
        # or string instead of raising.
        monkeypatch.setattr(judge_mod, "get_llm", lambda feature: _fake_llm({"outcome": "approved_clean"}))
        with pytest.raises(ScreenFrameJudgeError):
            judge_frame(UID, b"fake-jpeg-bytes")

    def test_raises_on_contradictory_approved_with_reject_reason(self, monkeypatch):
        # The exact failure mode contract §4 calls out (FINDINGS.md:100-108):
        # a decision that contradicts its own sensitivity/reason field.
        contradictory = ScreenFrameJudgement(
            outcome="approved_clean",
            reject_reason="credentials",
            caption="a screen",
            labels=[],
            source_badge=None,
            banner_suitability=0.5,
        )
        monkeypatch.setattr(judge_mod, "get_llm", lambda feature: _fake_llm(contradictory))
        with pytest.raises(ScreenFrameJudgeError):
            judge_frame(UID, b"fake-jpeg-bytes")

    def test_raises_on_rejected_with_no_reject_reason(self, monkeypatch):
        contradictory = ScreenFrameJudgement(
            outcome="rejected",
            reject_reason=None,
            caption="a screen",
            labels=[],
            source_badge=None,
            banner_suitability=0.1,
        )
        monkeypatch.setattr(judge_mod, "get_llm", lambda feature: _fake_llm(contradictory))
        with pytest.raises(ScreenFrameJudgeError):
            judge_frame(UID, b"fake-jpeg-bytes")


class TestCleanOutputPassesThrough:
    def test_approved_clean_is_returned(self, monkeypatch):
        clean = ScreenFrameJudgement(
            outcome="approved_clean",
            reject_reason=None,
            caption="a code editor",
            labels=["code"],
            source_badge="code",
            banner_suitability=0.7,
        )
        monkeypatch.setattr(judge_mod, "get_llm", lambda feature: _fake_llm(clean))
        result = judge_frame(UID, b"fake-jpeg-bytes")
        assert result.outcome == "approved_clean"
        assert result.banner_suitability == 0.7

    def test_rejected_with_reason_is_returned(self, monkeypatch):
        # Sample reason deliberately not identifiable_person: faces are published per David's
        # 2026-08-24 ruling, so using one here would pin an outcome the product no longer wants.
        rejected = ScreenFrameJudgement(
            outcome="rejected",
            reject_reason="credentials",
            caption="a login form with a filled password field",
            labels=[],
            source_badge=None,
            banner_suitability=0.0,
        )
        monkeypatch.setattr(judge_mod, "get_llm", lambda feature: _fake_llm(rejected))
        result = judge_frame(UID, b"fake-jpeg-bytes")
        assert result.outcome == "rejected"
        assert result.reject_reason == "credentials"


class TestFacePolicy:
    """David's ruling, 2026-08-24: faces are included.

    Pinned as two assertions rather than one because the policy lives in two halves of the
    prompt, and moving only one silently does nothing. Removing the identifiable_person
    reject rule while the approval criterion still demanded "no identifying information"
    would have left the model refusing faces with the flag already flipped — a gate that
    looks flipped and is not.
    """

    def test_a_face_is_not_a_reject_rule(self):
        assert policy_mod.REJECT_IDENTIFIABLE_PERSONS is False
        assert "identifiable_person" not in judge_mod._PRIVACY_PROMPT

    def test_the_approval_criterion_admits_people(self):
        prompt = judge_mod._PRIVACY_PROMPT
        assert "People are expected in a meeting screenshot" in prompt
        # The other half: the approve line must not re-forbid what the reject list allowed.
        assert "no private or identifying information" not in prompt

    def test_every_other_reject_reason_survives(self):
        prompt = judge_mod._PRIVACY_PROMPT
        for reason in ("credentials", "private_messages", "email", "banking", "medical", "personal_document"):
            assert f"- {reason}:" in prompt, f"{reason} must still reject"

    def test_a_face_does_not_rescue_an_otherwise_rejectable_frame(self):
        # The guidance has to say so explicitly, or "faces are fine" reads as "frames with
        # faces are fine" and a face on a banking screen becomes publishable.
        prompt = judge_mod._PRIVACY_PROMPT
        assert "A face never rescues a frame" in prompt


def test_prompt_tells_the_model_to_reject_when_it_was_sent_no_image():
    """Defence in depth against the exact fail-open found on 2026-08-25.

    The gateway's Vertex translator silently dropped image parts, so the judge's
    prompt arrived without its screenshot and the model returned a confident
    verdict about a frame it had never seen — which the caller then treated as a
    real decision. The provider bug is fixed (see
    tests/unit/test_llm_gateway_vertex_provider.py), but the provider is not the
    only thing that could drop an image, and nothing downstream of the model can
    tell the difference between "looked and approved" and "saw nothing and
    approved". So the prompt itself has to make a blind model fail closed.
    """
    from utils.screen_frames.judge import _PRIVACY_PROMPT

    assert "no image is attached" in _PRIVACY_PROMPT
    assert '"unreadable"' in _PRIVACY_PROMPT
    # The rule is worthless if it does not name the reject path the schema allows.
    tail = _PRIVACY_PROMPT.split("If no image is attached")[1]
    assert "unreadable" in tail and "reject" in tail


def test_overlong_caption_is_truncated_rather_than_dropping_the_frame():
    """Measured 2026-08-25 against real gemini-2.5-flash-lite via Vertex.

    Vertex treats a responseSchema `maxLength` as advisory, so the model overruns
    the 160-char caption limit in normal use even though the prompt states it.
    When ScreenFrameJudgement enforced max_length, that raised inside
    .with_structured_output(), judge_frame() mapped it to judge_call_failed, and a
    frame the judge had actually approved was silently discarded. Caption and
    labels are descriptive metadata with no part in the verdict, so normalising is
    strictly better than losing the frame.
    """
    from models.screen_frame import ScreenFrameJudgement

    judgement = ScreenFrameJudgement(
        outcome="approved_clean",
        caption="A screenshot of a dark-themed application interface. " * 8,
        labels=[f"label-{i}" for i in range(20)],
        banner_suitability=0.6,
    )

    assert len(judgement.caption) == 160
    assert len(judgement.labels) == 8
    assert judgement.outcome == "approved_clean"


def test_the_wire_frame_still_enforces_the_caption_contract():
    """The tolerance above is for the model's output only. The persisted/wire
    shape keeps its documented cap, so a relaxed judgement can never widen it."""
    import pytest as _pytest
    from pydantic import ValidationError

    from models.screen_frame import ConversationScreenFrame

    with _pytest.raises(ValidationError):
        ConversationScreenFrame.model_validate(
            {
                "id": "f1",
                "role": "strip",
                "rank": 0,
                "captured_at": "2026-01-01T00:00:00Z",
                "width": 10,
                "height": 10,
                "content_url": "https://example/c",
                "thumbnail_url": "https://example/t",
                "url_expires_at": "2026-01-01T00:00:00Z",
                "caption": "y" * 400,
                "labels": [],
                "ground": {"stops": ["#000000", "#ffffff"], "is_neutral": True},
                "banner_suitability": 0.5,
            }
        )
