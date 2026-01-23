from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


def version_to_numeric(version: Optional[str]) -> Optional[int]:
    """
    Convert version string to numeric for Firestore filtering.
    Format: major * 1000000000 + minor * 1000000 + patch * 1000 + build

    Examples:
    - "1.0.521+633" -> 1000521633
    - "v1.2.3" -> 1002003000
    - "2.5.10+100" -> 2005010100

    Returns None if version is invalid or None.
    """
    if not version:
        return None

    try:
        # Remove 'v' prefix if present
        version = version.lstrip('v').lstrip('V')

        # Extract build number if present
        build = 0
        if '+' in version:
            version, build_str = version.split('+', 1)
            build = int(build_str)

        # Parse semantic version
        parts = version.split('.')
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0

        # Compute numeric version
        return major * 1000000000 + minor * 1000000 + patch * 1000 + build
    except (ValueError, IndexError):
        return None


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

    app_version_numeric: Optional[int] = None
    firmware_version_numeric: Optional[int] = None

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
            app_version_numeric=data.get("app_version_numeric"),
            firmware_version_numeric=data.get("firmware_version_numeric"),
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
            "app_version_numeric": self.app_version_numeric,
            "firmware_version_numeric": self.firmware_version_numeric,
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
