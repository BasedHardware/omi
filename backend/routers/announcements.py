import hmac
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TypeVar

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

logger = logging.getLogger(__name__)

router = APIRouter()

# Firestore document ids: no separators, no relative segments, and the
# `__name__`-style names are reserved for internal use. The byte cap matches the
# Firestore key limit so an oversized id fails here instead of at the server.
MAX_ANNOUNCEMENT_ID_BYTES = 1500
MAX_CHANGELOG_LIMIT = 100
RESERVED_ID_PATTERN = re.compile(r'^__.*__$')
T = TypeVar('T')


def _require_announcement_id(value: Any, field: str = 'announcement_id') -> str:
    """Validate an announcement document id before it reaches Firestore.

    `announcement_id` and `data.id` were forwarded straight into
    `.document(...)`: a caller-supplied `/` retargeted the document path, `.`
    and `..` are rejected by Firestore as relative segments, and an
    `__name__`-style id collides with reserved names — each surfaced as an
    opaque 500 rather than a clean 400.
    """
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f'{field} must be a string')
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail=f'{field} must not be empty')
    if len(cleaned.encode('utf-8')) > MAX_ANNOUNCEMENT_ID_BYTES:
        raise HTTPException(status_code=400, detail=f'{field} is too long')
    if cleaned in ('.', '..') or any(char in cleaned for char in ('/', '\\', '\x00')):
        raise HTTPException(status_code=400, detail=f'{field} contains invalid characters')
    if RESERVED_ID_PATTERN.match(cleaned):
        raise HTTPException(status_code=400, detail=f'{field} uses a reserved name')
    return cleaned


def _require_text(value: Any, field: str) -> str:
    """Reject blank/whitespace-only required query parameters with a 400."""
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=400, detail=f'{field} must not be empty')
    return value.strip()


def _guarded(action: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a store call, translating failures into a sanitized 500.

    Every endpoint used to call the data layer bare, so a transient Firestore
    failure surfaced as an unhandled exception with the raw driver message in
    the response. HTTPException passes through untouched so 404/409 keep their
    meaning.
    """
    try:
        return action(*args, **kwargs)
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001 - boundary: never leak driver text
        logger.error('announcements store call failed: %s', sanitize(error), exc_info=True)
        raise HTTPException(status_code=500, detail='Announcement service unavailable')


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
    # Clamp the upper bound too: an unbounded limit turns a public read into an
    # arbitrary-size scan of the changelog collection.
    limit = min(limit, MAX_CHANGELOG_LIMIT)
    if from_version and to_version:
        changelogs = _guarded(get_app_changelogs, from_version, to_version)
    else:
        changelogs = _guarded(get_recent_changelogs, limit=limit, max_version=max_version)
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
    # Previously any value other than 'firmware' silently fell through to the
    # app branch, so `version_type=desktop` returned app features instead of
    # telling the caller it was wrong.
    version_type = _require_text(version_type, 'version_type').lower()
    if version_type not in ('app', 'firmware'):
        raise HTTPException(status_code=400, detail="version_type must be 'app' or 'firmware'")
    version = _require_text(version, 'version')

    if version_type == "firmware":
        features = _guarded(get_firmware_features, version, device_model)
    else:
        features = _guarded(get_app_features, version)

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

    announcements = _guarded(get_general_announcements, checked_at)
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

    # A blank app_version reached the targeting comparison as '' and matched
    # nothing, so the client silently got an empty list instead of an error.
    app_version = _require_text(app_version, 'app_version')

    announcements = _guarded(
        get_pending_announcements,
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

    # Verify announcement exists
    announcement = _guarded(get_announcement_by_id, announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    success = _guarded(dismiss_announcement, uid, announcement_id, data.cta_clicked)
    return {"success": success, "message": "Announcement dismissed"}


# ----------------------------
# Admin CRUD Endpoints
# ----------------------------


def _verify_admin_key(secret_key: str):
    """Verify the secret key matches the ADMIN_KEY environment variable.

    Compared in constant time. A whitespace-only ADMIN_KEY is treated as unset:
    it is a misconfiguration, and accepting it would let any caller who sends
    matching whitespace through the admin surface. The comparison is done on
    UTF-8 bytes because `hmac.compare_digest` raises TypeError on non-ASCII str
    input, which would turn a bad key into a 500 instead of a 403.
    """
    admin_key = os.getenv("ADMIN_KEY")
    if not admin_key or not admin_key.strip():
        raise HTTPException(status_code=403, detail="You are not authorized to perform this action")
    provided = secret_key
    expected = admin_key.strip()
    try:
        matches = hmac.compare_digest(provided, expected)
    except TypeError:
        # `compare_digest` rejects non-ASCII str, so fall back to UTF-8 bytes for
        # a non-ASCII ADMIN_KEY instead of turning a bad key into a 500.
        matches = hmac.compare_digest(provided.encode('utf-8'), expected.encode('utf-8'))
    if not matches:
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

    announcements = _guarded(
        get_all_announcements,
        announcement_type=announcement_type,
        active_only=active_only,
    )
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

    announcement = _guarded(get_announcement_by_id, announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

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
    announcement_id = _require_announcement_id(data.id, 'id')

    # Check if announcement with this ID already exists
    existing = _guarded(get_announcement_by_id, announcement_id)
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

    created = _guarded(create_announcement, announcement)
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

    existing = _guarded(get_announcement_by_id, announcement_id)
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

    updated = _guarded(update_announcement, announcement_id, updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="Announcement not found")
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

    existing = _guarded(get_announcement_by_id, announcement_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    if soft_delete:
        success = _guarded(deactivate_announcement, announcement_id)
        return {"success": success, "message": "Announcement deactivated"}
    else:
        success = _guarded(delete_announcement, announcement_id)
        return {"success": success, "message": "Announcement permanently deleted"}
