import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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
from models.announcement import Announcement, AnnouncementType, Display, Targeting
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth_endpoints

router = APIRouter()
logger = logging.getLogger(__name__)

# Firestore rejects document ids that are empty, that contain a path separator,
# that use a reserved __name__ form, or that exceed 1500 bytes.
MAX_ANNOUNCEMENT_ID_BYTES = 1500
MAX_CHANGELOG_LIMIT = 100


class AnnouncementDeleteResponse(BaseModel):
    success: bool
    message: str


@router.get("/v1/announcements/changelogs", response_model=List[Announcement])
def get_changelogs(
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
    # Validate in the handler, not with Query(ge=...): adding a `minimum` bound to the
    # published schema is a breaking change for the released app-client contract, while a
    # non-positive limit only needs to stop reaching the negative-slice path below.
    if limit < 1:
        raise HTTPException(status_code=422, detail="limit must be at least 1")
    # Upper clamp stays in the handler as well, so the published query schema keeps its
    # current shape and only the effective page size is bounded.
    effective_limit = min(limit, MAX_CHANGELOG_LIMIT)
    try:
        if from_version and to_version:
            changelogs = get_app_changelogs(from_version, to_version)
        else:
            changelogs = get_recent_changelogs(limit=effective_limit, max_version=max_version)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to load changelogs: {sanitize(str(exc))}")
        raise HTTPException(status_code=500, detail="Failed to load changelogs")
    return changelogs


@router.get("/v1/announcements/features", response_model=List[Announcement])
def get_features(
    version: str = Query(..., description="Version user upgraded to"),
    version_type: str = Query(..., description="Type: 'app' or 'firmware'"),
    device_model: Optional[str] = Query(None, description="Device model (for firmware features)"),
):
    """
    Get feature announcements for a specific version.

    For firmware updates: returns features explaining new device behavior.
    For app updates: returns features explaining major new app functionality.
    """
    if not (version or "").strip():
        raise HTTPException(status_code=400, detail="version must not be empty")
    # version_type is a closed set. Silently treating an unknown value as 'app'
    # hides client bugs behind plausible looking feature lists.
    if version_type not in ("app", "firmware"):
        raise HTTPException(status_code=400, detail="version_type must be 'app' or 'firmware'")
    try:
        if version_type == "firmware":
            features = get_firmware_features(version, device_model)
        else:
            features = get_app_features(version)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to load features: {sanitize(str(exc))}")
        raise HTTPException(status_code=500, detail="Failed to load features")
    return features


@router.get("/v1/announcements/general", response_model=List[Announcement])
def get_announcements(
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
            if checked_at.tzinfo is None:
                checked_at = checked_at.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    try:
        announcements = get_general_announcements(checked_at)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to load announcements: {sanitize(str(exc))}")
        raise HTTPException(status_code=500, detail="Failed to load announcements")
    return announcements


# ----------------------------
# Authenticated User Endpoints
# ----------------------------


@router.get("/v1/announcements/pending", response_model=List[Announcement], tags=["announcements"])
def get_pending_announcements_endpoint(
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

    if not (app_version or "").strip():
        raise HTTPException(status_code=400, detail="app_version must not be empty")

    try:
        announcements = get_pending_announcements(
            uid=uid,
            app_version=app_version,
            platform=platform,
            trigger=trigger,
            firmware_version=firmware_version,
            device_model=device_model,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to load pending announcements: {sanitize(str(exc))}")
        raise HTTPException(status_code=500, detail="Failed to load pending announcements")
    return announcements


class DismissAnnouncementRequest(BaseModel):
    """Request body for dismissing an announcement."""

    cta_clicked: bool = False


class DismissAnnouncementResponse(BaseModel):
    success: bool
    message: str


@router.post(
    "/v1/announcements/{announcement_id}/dismiss",
    tags=["announcements"],
    response_model=DismissAnnouncementResponse,
)
def dismiss_announcement_endpoint(
    announcement_id: str,
    data: DismissAnnouncementRequest,
    uid: str = Depends(auth_endpoints.get_current_user_uid),
):
    """
    Mark an announcement as dismissed for the current user.

    This prevents the announcement from being shown again if show_once is True.
    The cta_clicked field can be used to track whether the user engaged with the call-to-action.
    """
    announcement_id = _require_announcement_id(announcement_id)
    try:
        # Verify announcement exists
        announcement = get_announcement_by_id(announcement_id)
        if not announcement:
            raise HTTPException(status_code=404, detail="Announcement not found")

        success = dismiss_announcement(uid, announcement_id, data.cta_clicked)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to dismiss announcement: {sanitize(str(exc))}")
        raise HTTPException(status_code=500, detail="Failed to dismiss announcement")
    return {"success": success, "message": "Announcement dismissed"}


# ----------------------------
# Admin CRUD Endpoints
# ----------------------------


def _verify_admin_key(secret_key: str):
    """Verify the secret key matches the ADMIN_KEY environment variable."""
    admin_key = os.getenv("ADMIN_KEY")
    # An unset or whitespace only ADMIN_KEY must never authorize anyone, and the
    # comparison itself is constant time so the key cannot be recovered by timing.
    if not admin_key or not admin_key.strip():
        raise HTTPException(status_code=403, detail="You are not authorized to perform this action")
    try:
        matched = hmac.compare_digest(secret_key, admin_key)
    except TypeError:
        # compare_digest refuses non ASCII strings, so fall back to the encoded
        # forms instead of turning a misconfigured key into a server error.
        matched = hmac.compare_digest(secret_key.encode("utf-8"), admin_key.encode("utf-8"))
    if not matched:
        raise HTTPException(status_code=403, detail="You are not authorized to perform this action")


def _require_announcement_id(announcement_id: str) -> str:
    """Validate an announcement id before it reaches Firestore as a document id."""
    candidate = (announcement_id or "").strip()
    if not candidate:
        raise HTTPException(status_code=400, detail="announcement_id must not be empty")
    if candidate in (".", "..") or "/" in candidate:
        raise HTTPException(status_code=400, detail="announcement_id must not contain path segments")
    if candidate.startswith("__") and candidate.endswith("__"):
        raise HTTPException(status_code=400, detail="announcement_id must not use a reserved document name")
    if len(candidate.encode("utf-8")) > MAX_ANNOUNCEMENT_ID_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"announcement_id must be at most {MAX_ANNOUNCEMENT_ID_BYTES} bytes",
        )
    return candidate


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
    content: Dict[str, Any]


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
    content: Optional[Dict[str, Any]] = None


@router.get("/v1/announcements/all", response_model=List[Announcement], tags=["admin"])
def list_all_announcements(
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

    try:
        announcements = get_all_announcements(
            announcement_type=announcement_type,
            active_only=active_only,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to list announcements: {sanitize(str(exc))}")
        raise HTTPException(status_code=500, detail="Failed to list announcements")
    return announcements


@router.get("/v1/announcements/{announcement_id}", response_model=Announcement, tags=["admin"])
def get_announcement(
    announcement_id: str,
    secret_key: str = Header(..., description="Admin secret key"),
):
    """
    Get a single announcement by ID.
    Requires admin authentication via secret-key header.
    """
    _verify_admin_key(secret_key)
    announcement_id = _require_announcement_id(announcement_id)

    try:
        announcement = get_announcement_by_id(announcement_id)
        if not announcement:
            raise HTTPException(status_code=404, detail="Announcement not found")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to load announcement: {sanitize(str(exc))}")
        raise HTTPException(status_code=500, detail="Failed to load announcement")

    return announcement


@router.post("/v1/announcements", response_model=Announcement, tags=["admin"])
def create_announcement_endpoint(
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
    announcement_id = _require_announcement_id(data.id)

    try:
        # Check if announcement with this ID already exists
        existing = get_announcement_by_id(announcement_id)
        if existing:
            raise HTTPException(status_code=409, detail=f"Announcement with ID '{announcement_id}' already exists")

        announcement = Announcement(
            id=announcement_id,
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
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to create announcement: {sanitize(str(exc))}")
        raise HTTPException(status_code=500, detail="Failed to create announcement")
    return created


@router.put("/v1/announcements/{announcement_id}", response_model=Announcement, tags=["admin"])
def update_announcement_endpoint(
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
    announcement_id = _require_announcement_id(announcement_id)

    try:
        existing = get_announcement_by_id(announcement_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Announcement not found")

        # Build updates dict with only non-None values
        updates: Dict[str, Any] = {}
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
        if updated is None:
            raise HTTPException(status_code=404, detail="Announcement not found")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to update announcement: {sanitize(str(exc))}")
        raise HTTPException(status_code=500, detail="Failed to update announcement")
    return updated


@router.delete("/v1/announcements/{announcement_id}", tags=["admin"], response_model=AnnouncementDeleteResponse)
def delete_announcement_endpoint(
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
    announcement_id = _require_announcement_id(announcement_id)

    try:
        existing = get_announcement_by_id(announcement_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Announcement not found")

        if soft_delete:
            success = deactivate_announcement(announcement_id)
            return {"success": success, "message": "Announcement deactivated"}
        else:
            success = delete_announcement(announcement_id)
            return {"success": success, "message": "Announcement permanently deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to delete announcement: {sanitize(str(exc))}")
        raise HTTPException(status_code=500, detail="Failed to delete announcement")
