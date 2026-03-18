from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class FairUseStage(str, Enum):
    """Graduated enforcement stages."""

    NONE = "none"
    WARNING = "warning"
    THROTTLE = "throttle"
    RESTRICT = "restrict"


class AbuseType(str, Enum):
    """Types of detected abuse."""

    NONE = "none"
    AUDIOBOOK = "audiobook"
    PODCAST = "podcast"
    PRERECORDED = "prerecorded"
    TV_MOVIE = "tv_movie"
    COMMERCIAL = "commercial"
    UNKNOWN = "unknown"


class SoftCapTrigger(str, Enum):
    """Which rolling window triggered the soft cap."""

    DAILY = "daily"
    THREE_DAY = "3day"
    WEEKLY = "weekly"


class ClassifierEvidence(BaseModel):
    """Evidence from a single conversation flagged by the LLM classifier."""

    conversation_id: str
    title: str = ""
    category: str = ""
    reason: str = ""


class ClassifierResult(BaseModel):
    """Result from the LLM abuse classifier."""

    model: str = ""
    prompt_version: str = "v2"
    abuse_score: float = 0.0
    abuse_type: AbuseType = AbuseType.NONE
    confidence: float = 0.0
    evidence: List[ClassifierEvidence] = Field(default_factory=list)


class FairUseState(BaseModel):
    """Per-user fair use enforcement state. Stored at users/{uid}/fair_use_state/current."""

    stage: FairUseStage = FairUseStage.NONE
    violation_count_7d: int = 0
    violation_count_30d: int = 0
    last_violation_at: Optional[datetime] = None
    throttle_until: Optional[datetime] = None
    restrict_until: Optional[datetime] = None
    last_classifier_score: float = 0.0
    last_classifier_type: AbuseType = AbuseType.NONE
    vad_threshold_delta: float = 0.0
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FairUseEvent(BaseModel):
    """A single fair-use violation event. Stored at users/{uid}/fair_use_events/{event_id}."""

    created_at: datetime = Field(default_factory=datetime.utcnow)
    session_id: str = ""
    trigger: SoftCapTrigger = SoftCapTrigger.DAILY
    window_speech_ms: dict = Field(default_factory=dict)  # {daily, three_day, weekly}
    thresholds_ms: dict = Field(default_factory=dict)  # snapshot of active thresholds
    classifier: Optional[ClassifierResult] = None
    enforcement_action: str = ""  # warning, throttle, restrict, none
    previous_stage: FairUseStage = FairUseStage.NONE
    new_stage: FairUseStage = FairUseStage.NONE
    admin_notes: str = ""
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: str = ""


class FairUseUserSummary(BaseModel):
    """Summary for admin dashboard."""

    uid: str
    stage: FairUseStage = FairUseStage.NONE
    violation_count_7d: int = 0
    violation_count_30d: int = 0
    last_violation_at: Optional[datetime] = None
    last_classifier_score: float = 0.0
    last_classifier_type: AbuseType = AbuseType.NONE
    speech_hours_today: float = 0.0
    speech_hours_7d: float = 0.0
