from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class AnnouncementType(str, Enum):
    CHANGELOG = "changelog"
    FEATURE = "feature"
    ANNOUNCEMENT = "announcement"


class TriggerType(str, Enum):
    IMMEDIATE = "immediate"  # Check every app launch
    VERSION_UPGRADE = "version_upgrade"  # Check only when app version changes
    FIRMWARE_UPGRADE = "firmware_upgrade"  # Check only when firmware version changes


class Targeting(BaseModel):
    """Controls who sees the announcement"""

    app_version_min: Optional[str] = None  # Show to users >= this version
    app_version_max: Optional[str] = None  # Show to users <= this version
    firmware_version_min: Optional[str] = None
    firmware_version_max: Optional[str] = None
    device_models: Optional[List[str]] = None  # ["Omi DevKit 2", "Omi Pro"]
    platforms: Optional[List[str]] = None  # ["ios", "android"]
    trigger: TriggerType = TriggerType.VERSION_UPGRADE
    test_uids: Optional[List[str]] = None  # If set, only these users see the announcement (for testing)

    def to_dict(self) -> dict:
        return {
            "app_version_min": self.app_version_min,
            "app_version_max": self.app_version_max,
            "firmware_version_min": self.firmware_version_min,
            "firmware_version_max": self.firmware_version_max,
            "device_models": self.device_models,
            "platforms": self.platforms,
            "trigger": self.trigger.value,
            "test_uids": self.test_uids,
        }


class Display(BaseModel):
    """Controls how/when the announcement is displayed"""

    priority: int = 0  # Higher = show first
    start_at: Optional[datetime] = None  # Don't show before this time
    expires_at: Optional[datetime] = None  # Don't show after this time
    dismissible: bool = True  # Can user skip?
    show_once: bool = True  # Only show once per user

    def to_dict(self) -> dict:
        return {
            "priority": self.priority,
            "start_at": self.start_at,
            "expires_at": self.expires_at,
            "dismissible": self.dismissible,
            "show_once": self.show_once,
        }


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

    # Legacy version triggers (for backward compatibility with existing announcements)
    app_version: Optional[str] = None
    firmware_version: Optional[str] = None
    device_models: Optional[List[str]] = None

    # Legacy expiration (for backward compatibility)
    expires_at: Optional[datetime] = None

    # New flexible targeting and display options (optional)
    targeting: Optional[Targeting] = None
    display: Optional[Display] = None

    # Content - will be one of ChangelogContent, FeatureContent, or AnnouncementContent
    content: dict

    def get_changelog_content(self) -> ChangelogContent:
        return ChangelogContent(**self.content)

    def get_feature_content(self) -> FeatureContent:
        return FeatureContent(**self.content)

    def get_announcement_content(self) -> AnnouncementContent:
        return AnnouncementContent(**self.content)

    def get_effective_targeting(self) -> Targeting:
        """Get targeting config, falling back to legacy fields if not set."""
        if self.targeting:
            return self.targeting
        # Build targeting from legacy fields
        return Targeting(
            app_version_min=self.app_version,
            app_version_max=self.app_version,
            firmware_version_min=self.firmware_version,
            firmware_version_max=self.firmware_version,
            device_models=self.device_models,
            trigger=TriggerType.VERSION_UPGRADE,
        )

    def get_effective_display(self) -> Display:
        """Get display config, falling back to legacy fields if not set."""
        if self.display:
            return self.display
        # Build display from legacy fields
        return Display(
            expires_at=self.expires_at,
        )

    @staticmethod
    def from_dict(data: dict) -> "Announcement":
        targeting_data = data.get("targeting")
        display_data = data.get("display")

        return Announcement(
            id=data.get("id"),
            type=AnnouncementType(data.get("type")),
            created_at=data.get("created_at"),
            active=data.get("active", True),
            app_version=data.get("app_version"),
            firmware_version=data.get("firmware_version"),
            device_models=data.get("device_models"),
            expires_at=data.get("expires_at"),
            targeting=Targeting(**targeting_data) if targeting_data else None,
            display=Display(**display_data) if display_data else None,
            content=data.get("content", {}),
        )

    def to_dict(self) -> dict:
        result = {
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
        if self.targeting:
            result["targeting"] = self.targeting.to_dict()
        if self.display:
            result["display"] = self.display.to_dict()
        return result


# API Response models
class ChangelogResponse(BaseModel):
    changelogs: List[Announcement]


class FeatureResponse(BaseModel):
    features: List[Announcement]


class AnnouncementListResponse(BaseModel):
    announcements: List[Announcement]
