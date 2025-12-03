from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class MergeHistory(BaseModel):
    """
    Tracks conversation merge operations for rollback capability.

    Stored in Firestore collection: merge_history
    TTL: 24 hours from merge_time (configurable)
    """
    merge_id: str = Field(..., description="Unique merge operation ID (UUID)")
    uid: str = Field(..., description="User ID who performed the merge")
    merged_conversation_id: str = Field(..., description="ID of the newly created merged conversation")

    # Full snapshots of source conversations for rollback
    source_conversations: List[Dict] = Field(
        ...,
        description="Complete snapshots of all source conversations (before merge)"
    )

    # Merge operation timestamps
    merge_time: datetime = Field(..., description="When the merge was performed")
    rollback_expiration: datetime = Field(
        ...,
        description="When rollback capability expires (merge_time + 24 hours)"
    )

    # Rollback tracking
    rolled_back: bool = Field(default=False, description="Whether this merge has been rolled back")
    rollback_time: Optional[datetime] = Field(
        default=None,
        description="When the rollback was performed (if rolled_back=True)"
    )
    rollback_reason: Optional[str] = Field(
        default=None,
        description="Optional reason for rollback (user-provided or system-generated)"
    )

    # Metadata
    merge_metadata: Dict = Field(
        default_factory=dict,
        description="Additional merge operation metadata (count, total_duration, etc.)"
    )
    user_agent: Optional[str] = Field(
        default=None,
        description="Client user agent string (mobile, desktop, API)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "merge_id": "550e8400-e29b-41d4-a716-446655440000",
                "uid": "user-abc-123",
                "merged_conversation_id": "conv-merged-456",
                "source_conversations": [
                    {
                        "id": "conv-1",
                        "created_at": "2025-11-29T10:00:00Z",
                        "structured": {"title": "Morning Meeting"}
                    },
                    {
                        "id": "conv-2",
                        "created_at": "2025-11-29T11:00:00Z",
                        "structured": {"title": "Follow-up Discussion"}
                    }
                ],
                "merge_time": "2025-11-29T12:00:00Z",
                "rollback_expiration": "2025-11-30T12:00:00Z",
                "rolled_back": False,
                "rollback_time": None,
                "rollback_reason": None,
                "merge_metadata": {
                    "source_count": 2,
                    "total_segments": 45,
                    "total_duration_seconds": 3600
                },
                "user_agent": "Omi/iOS/1.0"
            }
        }
