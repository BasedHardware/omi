from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class AnnouncementType(str, Enum):
    CHANGELOG = "changelog"
    FEATURE = "feature"
    ANNOUNCEMENT = "announcement"


# Changelog content models
class ChangelogItem(BaseModel):
    title: str
    description: str
    icon: Optional[str] = None


class ChangelogContent(BaseModel):
    title: str
    changes: List[ChangelogItem]


# Feature content models
class FeatureStep(BaseModel):
    title: str
    description: str
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    highlight_text: Optional[str] = None


class FeatureContent(BaseModel):
    title: str
    steps: List[FeatureStep]


# Announcement content models
class AnnouncementCTA(BaseModel):
    text: str
    action: str  # e.g., "navigate:/settings/premium" or "url:https://example.com"


class AnnouncementContent(BaseModel):
    title: str
    body: str
    image_url: Optional[str] = None
    cta: Optional[AnnouncementCTA] = None


# Main announcement model
class Announcement(BaseModel):
    id: str
    type: AnnouncementType
    created_at: datetime
    active: bool = True

    # Version triggers (optional, depends on type)
    app_version: Optional[str] = None
    firmware_version: Optional[str] = None
    device_models: Optional[List[str]] = None

    # For general announcements
    expires_at: Optional[datetime] = None

    # Content - will be one of ChangelogContent, FeatureContent, or AnnouncementContent
    content: dict

    def get_changelog_content(self) -> ChangelogContent:
        return ChangelogContent(**self.content)

    def get_feature_content(self) -> FeatureContent:
        return FeatureContent(**self.content)

    def get_announcement_content(self) -> AnnouncementContent:
        return AnnouncementContent(**self.content)

    @staticmethod
    def from_dict(data: dict) -> "Announcement":
        return Announcement(
            id=data.get("id"),
            type=AnnouncementType(data.get("type")),
            created_at=data.get("created_at"),
            active=data.get("active", True),
            app_version=data.get("app_version"),
            firmware_version=data.get("firmware_version"),
            device_models=data.get("device_models"),
            expires_at=data.get("expires_at"),
            content=data.get("content", {}),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "created_at": self.created_at,
            "active": self.active,
            "app_version": self.app_version,
            "firmware_version": self.firmware_version,
            "device_models": self.device_models,
            "expires_at": self.expires_at,
            "content": self.content,
        }


# API Response models
class ChangelogResponse(BaseModel):
    changelogs: List[Announcement]


class FeatureResponse(BaseModel):
    features: List[Announcement]


class AnnouncementListResponse(BaseModel):
    announcements: List[Announcement]
