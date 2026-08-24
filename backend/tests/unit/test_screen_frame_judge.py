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
