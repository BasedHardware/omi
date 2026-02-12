"""
Pydantic models for Dropbox Omi plugin.
"""
from datetime import datetime, timedelta
from typing import List, Optional

from pydantic import BaseModel, Field


class DropboxUserSettings(BaseModel):
    """User preferences for Dropbox sync."""
    folder_name: str = "Omi Conversations"
    save_summary: bool = True
    save_transcript: bool = True
    save_audio: bool = True


class TranscriptSegment(BaseModel):
    """Transcript segment from Omi."""
    text: str
    speaker: Optional[str] = "SPEAKER_00"
    speaker_id: Optional[int] = None
    is_user: bool
    start: float
    end: float

    def __init__(self, **data):
        super().__init__(**data)
        if self.speaker:
            try:
                self.speaker_id = int(self.speaker.split("_")[1])
            except (IndexError, ValueError):
                self.speaker_id = 0
        else:
            self.speaker_id = 0

    def get_timestamp_string(self) -> str:
        """Format start-end as timestamp string."""
        start_duration = timedelta(seconds=int(self.start))
        end_duration = timedelta(seconds=int(self.end))
        return f"{str(start_duration).split('.')[0]} - {str(end_duration).split('.')[0]}"


class ActionItem(BaseModel):
    """Action item from conversation."""
    description: str
    completed: bool = False


class Structured(BaseModel):
    """Structured summary from Omi."""
    title: str
    overview: str
    emoji: str = ""
    category: str = "other"
    action_items: List[ActionItem] = []


class PluginResult(BaseModel):
    """Result from another plugin."""
    plugin_id: Optional[str] = None
    content: str


class Conversation(BaseModel):
    """Conversation data from Omi webhook."""
    id: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    transcript_segments: List[TranscriptSegment] = []
    structured: Structured
    plugins_results: List[PluginResult] = []
    discarded: bool = False

    def get_transcript(self, include_timestamps: bool = True, user_name: str = "User") -> str:
        """Format transcript as readable string."""
        if not self.transcript_segments:
            return ""

        lines = []
        for segment in self.transcript_segments:
            text = segment.text.strip()
            if not text:
                continue

            speaker = user_name if segment.is_user else f"Speaker {segment.speaker_id}"

            if include_timestamps:
                timestamp = segment.get_timestamp_string()
                lines.append(f"[{timestamp}] {speaker}: {text}")
            else:
                lines.append(f"{speaker}: {text}")

        return "\n\n".join(lines)

    def get_duration(self) -> Optional[str]:
        """Calculate conversation duration from segments."""
        if not self.transcript_segments:
            return None

        start = min(s.start for s in self.transcript_segments)
        end = max(s.end for s in self.transcript_segments)
        duration = timedelta(seconds=int(end - start))
        return str(duration).split(".")[0]


class EndpointResponse(BaseModel):
    """Standard response for Omi webhooks."""
    message: str = Field(
        description="A short message to be sent as notification to the user, if needed.",
        default=""
    )
