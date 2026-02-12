import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from database.announcements import (
    create_announcement,
    deactivate_announcement,
    delete_announcement,
    dismiss_announcement,
    get_all_announcements,
    get_announcement_by_id,
    get_app_changelogs,
    get_app_features,
    get_firmware_features,
    get_general_announcements,
    get_pending_announcements,
    get_recent_changelogs,
    update_announcement,
)
from models.announcement import Announcement, AnnouncementType, Display, Targeting, TriggerType
from utils.other import endpoints as auth_endpoints

router = APIRouter()


@router.get("/v1/announcements/changelogs", response_model=List[Announcement])
async def get_changelogs(
    from_version: Optional[str] = Query(None, description="Previous app version (before upgrade)"),
    to_version: Optional[str] = Query(None, description="Current app version (after upgrade)"),
    max_version: Optional[str] = Query(None, description="Maximum version to include (filters out future versions)"),
    limit: int = Query(5, description="Maximum number of changelogs to return"),
):
    """
    Get app changelog announcements.

    If from_version and to_version are provided:
        Returns changelogs where from_version < app_version <= to_version.

    If max_version is provided (without from/to):
        Returns the most recent `limit` changelogs where app_version <= max_version.

    If none provided:
        Returns the most recent `limit` changelogs.

    Sorted by version descending (newest first).
    User sees the latest version's changelog first, can swipe to see older versions.
    """
    if from_version and to_version:
        changelogs = get_app_changelogs(from_version, to_version)
    else:
        changelogs = get_recent_changelogs(limit=limit, max_version=max_version)
    return changelogs


@router.get("/v1/announcements/features", response_model=List[Announcement])
async def get_features(
    version: str = Query(..., description="Version user upgraded to"),
    version_type: str = Query(..., description="Type: 'app' or 'firmware'"),
    device_model: Optional[str] = Query(None, description="Device model (for firmware features)"),
):
    """
    Get feature announcements for a specific version.

    For firmware updates: returns features explaining new device behavior.
    For app updates: returns features explaining major new app functionality.
    """
    if version_type == "firmware":
        features = get_firmware_features(version, device_model)
    else:
        features = get_app_features(version)

    return features


@router.get("/v1/announcements/general", response_model=List[Announcement])
async def get_announcements(
    last_checked_at: Optional[str] = Query(
        None, description="ISO timestamp of last check (only returns newer announcements)"
    ),
):
    """
    Get active, non-expired general announcements.
    If last_checked_at is provided, only returns announcements created after that time.

    These are time-based announcements (promotions, notices) not tied to versions.
    """
    checked_at = None
    if last_checked_at:
        try:
            checked_at = datetime.fromisoformat(last_checked_at.replace("Z", "+00:00"))
        except ValueError:
            pass

    announcements = get_general_announcements(checked_at)
    return announcements


# ----------------------------
# Authenticated User Endpoints
# ----------------------------


@router.get("/v1/announcements/pending", response_model=List[Announcement], tags=["announcements"])
async def get_pending_announcements_endpoint(
    app_version: str = Query(..., description="Current app version (e.g., '1.0.522+240')"),
    platform: str = Query(..., description="Platform: 'ios' or 'android'"),
    trigger: str = Query(..., description="Trigger: 'app_launch', 'version_upgrade', or 'firmware_upgrade'"),
    firmware_version: Optional[str] = Query(None, description="Current firmware version (optional)"),
    device_model: Optional[str] = Query(None, description="Device model name (optional)"),
    uid: str = Depends(auth_endpoints.get_current_user_uid),
):
    """
    Get all pending announcements for a user.

    This is the new unified endpoint that replaces the separate changelogs/features/general endpoints.
    It supports flexible targeting and per-user dismissal tracking.

    Filtering logic:
    1. active == True
    2. Not in user's dismissed_announcements (if show_once == True)
    3. Within time window (start_at <= now <= expires_at)
    4. Matches targeting rules (version range, device, platform)
    5. Matches trigger type
    6. Sorted by priority (descending)

    Triggers:
    - app_launch: Check every app launch (for immediate announcements)
    - version_upgrade: Check only when app version changed
    - firmware_upgrade: Check only when firmware version changed
    """
    if platform not in ["ios", "android"]:
        raise HTTPException(status_code=400, detail="Platform must be 'ios' or 'android'")

    if trigger not in ["app_launch", "version_upgrade", "firmware_upgrade"]:
        raise HTTPException(
            status_code=400, detail="Trigger must be 'app_launch', 'version_upgrade', or 'firmware_upgrade'"
        )

    announcements = get_pending_announcements(
        uid=uid,
        app_version=app_version,
        platform=platform,
        trigger=trigger,
        firmware_version=firmware_version,
        device_model=device_model,
    )
    return announcements


class DismissAnnouncementRequest(BaseModel):
    """Request body for dismissing an announcement."""

    cta_clicked: bool = False


@router.post("/v1/announcements/{announcement_id}/dismiss", tags=["announcements"])
async def dismiss_announcement_endpoint(
    announcement_id: str,
    data: DismissAnnouncementRequest,
    uid: str = Depends(auth_endpoints.get_current_user_uid),
):
    """
    Mark an announcement as dismissed for the current user.

    This prevents the announcement from being shown again if show_once is True.
    The cta_clicked field can be used to track whether the user engaged with the call-to-action.
    """
    # Verify announcement exists
    announcement = get_announcement_by_id(announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    success = dismiss_announcement(uid, announcement_id, data.cta_clicked)
    return {"success": success, "message": "Announcement dismissed"}


# ----------------------------
# Admin CRUD Endpoints
# ----------------------------


def _verify_admin_key(secret_key: str):
    """Verify the secret key matches the ADMIN_KEY environment variable."""
    admin_key = os.getenv("ADMIN_KEY")
    if not admin_key or secret_key != admin_key:
        raise HTTPException(status_code=403, detail="You are not authorized to perform this action")


class CreateAnnouncementRequest(BaseModel):
    """Request body for creating an announcement."""

    id: str
    type: AnnouncementType
    active: bool = True
    # Legacy fields (for backward compatibility)
    app_version: Optional[str] = None
    firmware_version: Optional[str] = None
    device_models: Optional[List[str]] = None
    expires_at: Optional[datetime] = None
    # New flexible targeting and display options
    targeting: Optional[Targeting] = None
    display: Optional[Display] = None
    content: dict


class UpdateAnnouncementRequest(BaseModel):
    """Request body for updating an announcement."""

    active: Optional[bool] = None
    # Legacy fields
    app_version: Optional[str] = None
    firmware_version: Optional[str] = None
    device_models: Optional[List[str]] = None
    expires_at: Optional[datetime] = None
    # New fields
    targeting: Optional[Targeting] = None
    display: Optional[Display] = None
    content: Optional[dict] = None


@router.get("/v1/announcements/all", response_model=List[Announcement], tags=["admin"])
async def list_all_announcements(
    secret_key: str = Header(..., description="Admin secret key"),
    announcement_type: Optional[AnnouncementType] = Query(None, description="Filter by type"),
    active_only: bool = Query(False, description="Only return active announcements"),
):
    """
    List all announcements with optional filtering.
    Requires admin authentication via secret-key header.

    Useful for admin dashboard to see all announcements.
    """
    _verify_admin_key(secret_key)

    announcements = get_all_announcements(
        announcement_type=announcement_type,
        active_only=active_only,
    )
    return announcements


@router.get("/v1/announcements/{announcement_id}", response_model=Announcement, tags=["admin"])
async def get_announcement(
    announcement_id: str,
    secret_key: str = Header(..., description="Admin secret key"),
):
    """
    Get a single announcement by ID.
    Requires admin authentication via secret-key header.
    """
    _verify_admin_key(secret_key)

    announcement = get_announcement_by_id(announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return announcement


@router.post("/v1/announcements", response_model=Announcement, tags=["admin"])
async def create_announcement_endpoint(
    data: CreateAnnouncementRequest,
    secret_key: str = Header(..., description="Admin secret key"),
):
    """
    Create a new announcement.
    Requires admin authentication via secret-key header.

    Content structure depends on type:
    - changelog: {"title": "...", "changes": [{"title": "...", "description": "...", "icon": "🔀"}, ...]}
    - feature: {"title": "...", "steps": [{"title": "...", "description": "...", "image_url": "...", "highlight_text": "..."}, ...]}
    - announcement: {"title": "...", "body": "...", "image_url": "...", "cta": {"text": "...", "action": "..."}}
    """
    _verify_admin_key(secret_key)

    # Check if announcement with this ID already exists
    existing = get_announcement_by_id(data.id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Announcement with ID '{data.id}' already exists")

    announcement = Announcement(
        id=data.id,
        type=data.type,
        created_at=datetime.now(timezone.utc),
        active=data.active,
        app_version=data.app_version,
        firmware_version=data.firmware_version,
        device_models=data.device_models,
        expires_at=data.expires_at,
        targeting=data.targeting,
        display=data.display,
        content=data.content,
    )

    created = create_announcement(announcement)
    return created


@router.put("/v1/announcements/{announcement_id}", response_model=Announcement, tags=["admin"])
async def update_announcement_endpoint(
    announcement_id: str,
    data: UpdateAnnouncementRequest,
    secret_key: str = Header(..., description="Admin secret key"),
):
    """
    Update an existing announcement.
    Requires admin authentication via secret-key header.
    Only provided fields will be updated.
    """
    _verify_admin_key(secret_key)

    existing = get_announcement_by_id(announcement_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    # Build updates dict with only non-None values
    updates = {}
    if data.active is not None:
        updates["active"] = data.active
    if data.app_version is not None:
        updates["app_version"] = data.app_version
    if data.firmware_version is not None:
        updates["firmware_version"] = data.firmware_version
    if data.device_models is not None:
        updates["device_models"] = data.device_models
    if data.expires_at is not None:
        updates["expires_at"] = data.expires_at
    if data.targeting is not None:
        updates["targeting"] = data.targeting.to_dict()
    if data.display is not None:
        updates["display"] = data.display.to_dict()
    if data.content is not None:
        updates["content"] = data.content

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updated = update_announcement(announcement_id, updates)
    return updated


@router.delete("/v1/announcements/{announcement_id}", tags=["admin"])
async def delete_announcement_endpoint(
    announcement_id: str,
    secret_key: str = Header(..., description="Admin secret key"),
    soft_delete: bool = Query(True, description="If true, deactivates instead of permanently deleting"),
):
    """
    Delete an announcement.
    Requires admin authentication via secret-key header.

    By default, performs a soft delete (sets active=false).
    Set soft_delete=false to permanently remove the announcement.
    """
    _verify_admin_key(secret_key)

    existing = get_announcement_by_id(announcement_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    if soft_delete:
        success = deactivate_announcement(announcement_id)
        return {"success": success, "message": "Announcement deactivated"}
    else:
        success = delete_announcement(announcement_id)
        return {"success": success, "message": "Announcement permanently deleted"}
