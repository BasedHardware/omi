"""Tests for fair-use Pydantic models (models/fair_use.py)."""

from datetime import datetime

from models.fair_use import (
    AbuseType,
    ClassifierEvidence,
    ClassifierResult,
    FairUseEvent,
    FairUseStage,
    FairUseState,
    FairUseUserSummary,
    SoftCapTrigger,
)


class TestEnums:
    def test_fair_use_stages(self):
        assert FairUseStage.NONE.value == 'none'
        assert FairUseStage.WARNING.value == 'warning'
        assert FairUseStage.THROTTLE.value == 'throttle'
        assert FairUseStage.RESTRICT.value == 'restrict'

    def test_abuse_types(self):
        assert AbuseType.AUDIOBOOK.value == 'audiobook'
        assert AbuseType.PODCAST.value == 'podcast'
        assert AbuseType.COMMERCIAL.value == 'commercial'

    def test_soft_cap_triggers(self):
        assert SoftCapTrigger.DAILY.value == 'daily'
        assert SoftCapTrigger.THREE_DAY.value == '3day'
        assert SoftCapTrigger.WEEKLY.value == 'weekly'


class TestClassifierResult:
    def test_defaults(self):
        result = ClassifierResult()
        assert result.abuse_score == 0.0
        assert result.abuse_type == AbuseType.NONE
        assert result.confidence == 0.0
        assert result.evidence == []

    def test_with_evidence(self):
        evidence = ClassifierEvidence(conversation_id='conv-1', title='Chapter 12', reason='Book title')
        result = ClassifierResult(
            abuse_score=0.9,
            abuse_type=AbuseType.AUDIOBOOK,
            confidence=0.95,
            evidence=[evidence],
        )
        assert result.abuse_score == 0.9
        assert len(result.evidence) == 1
        assert result.evidence[0].conversation_id == 'conv-1'


class TestFairUseState:
    def test_defaults(self):
        state = FairUseState()
        assert state.stage == FairUseStage.NONE
        assert state.violation_count_7d == 0
        assert state.vad_threshold_delta == 0.0
        assert state.throttle_until is None
        assert state.restrict_until is None

    def test_throttled_state(self):
        state = FairUseState(
            stage=FairUseStage.THROTTLE,
            violation_count_7d=3,
            vad_threshold_delta=0.08,
            throttle_until=datetime(2026, 4, 1),
        )
        assert state.stage == FairUseStage.THROTTLE
        assert state.vad_threshold_delta == 0.08


class TestFairUseEvent:
    def test_defaults(self):
        event = FairUseEvent()
        assert event.enforcement_action == ''
        assert event.resolved is False
        assert event.trigger == SoftCapTrigger.DAILY


class TestFairUseUserSummary:
    def test_summary(self):
        summary = FairUseUserSummary(
            uid='user-123',
            stage=FairUseStage.WARNING,
            speech_hours_today=1.5,
            speech_hours_7d=8.0,
        )
        assert summary.uid == 'user-123'
        assert summary.speech_hours_today == 1.5
