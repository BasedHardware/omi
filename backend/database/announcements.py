from datetime import datetime, timezone
from typing import List, Optional

from google.cloud.firestore_v1 import FieldFilter

from ._client import db
from models.announcement import Announcement, AnnouncementType, version_to_numeric


def get_announcement_by_id(announcement_id: str) -> Optional[Announcement]:
    """Get a single announcement by ID."""
    doc_ref = db.collection("announcements").document(announcement_id)
    doc = doc_ref.get()
    if doc.exists:
        return Announcement.from_dict(doc.to_dict())
    return None


def get_app_changelogs(from_version: str, to_version: str) -> List[Announcement]:
    """
    Get all app changelog announcements between two versions.
    Returns changelogs where from_version < app_version <= to_version.
    Sorted by app_version descending (newest first).
    """
    from_version_numeric = version_to_numeric(from_version)
    to_version_numeric = version_to_numeric(to_version)

    announcements_ref = db.collection("announcements")
    query = announcements_ref.where(filter=FieldFilter("type", "==", AnnouncementType.CHANGELOG.value)).where(
        filter=FieldFilter("active", "==", True)
    )

    if from_version_numeric is not None and to_version_numeric is not None:
        query = query.where(filter=FieldFilter("app_version_numeric", ">", from_version_numeric))
        query = query.where(filter=FieldFilter("app_version_numeric", "<=", to_version_numeric))

    docs = query.stream()
    changelogs = []

    for doc in docs:
        data = doc.to_dict()
        app_version = data.get("app_version")
        if app_version:
            changelogs.append(Announcement.from_dict(data))

    # Sort by version descending (newest first)
    changelogs.sort(key=lambda x: x.app_version_numeric or 0, reverse=True)
    return changelogs


def get_recent_changelogs(limit: int = 5, max_version: Optional[str] = None) -> List[Announcement]:
    """
    Get the most recent app changelog announcements.
    Returns up to `limit` changelogs sorted by version descending.
    If max_version is provided, only returns changelogs with app_version <= max_version.
    """
    announcements_ref = db.collection("announcements")
    query = announcements_ref.where(filter=FieldFilter("type", "==", AnnouncementType.CHANGELOG.value)).where(
        filter=FieldFilter("active", "==", True)
    )

    if max_version:
        max_version_numeric = version_to_numeric(max_version)
        if max_version_numeric is not None:
            query = query.where(filter=FieldFilter("app_version_numeric", "<=", max_version_numeric))

    docs = query.stream()
    changelogs = []

    for doc in docs:
        data = doc.to_dict()
        app_version = data.get("app_version")
        if app_version:
            changelogs.append(Announcement.from_dict(data))

    # Sort by version descending
    changelogs.sort(key=lambda x: x.app_version_numeric or 0, reverse=True)

    # Return only the most recent N changelogs
    return changelogs[:limit]


def get_firmware_features(firmware_version: str, device_model: Optional[str] = None) -> List[Announcement]:
    """
    Get feature announcements for a specific firmware version.
    Optionally filter by device model.
    """
    firmware_version_numeric = version_to_numeric(firmware_version)
    if firmware_version_numeric is None:
        return []

    announcements_ref = db.collection("announcements")
    query = (
        announcements_ref.where(filter=FieldFilter("type", "==", AnnouncementType.FEATURE.value))
        .where(filter=FieldFilter("active", "==", True))
        .where(filter=FieldFilter("firmware_version_numeric", "==", firmware_version_numeric))
    )

    docs = query.stream()
    features = []

    for doc in docs:
        data = doc.to_dict()
        announcement = Announcement.from_dict(data)

        # Filter by device model if specified
        if device_model and announcement.device_models:
            if device_model not in announcement.device_models:
                continue

        features.append(announcement)

    return features


def get_app_features(app_version: str) -> List[Announcement]:
    """
    Get feature announcements for a specific app version.
    """
    app_version_numeric = version_to_numeric(app_version)
    if app_version_numeric is None:
        return []

    announcements_ref = db.collection("announcements")
    query = (
        announcements_ref.where(filter=FieldFilter("type", "==", AnnouncementType.FEATURE.value))
        .where(filter=FieldFilter("active", "==", True))
        .where(filter=FieldFilter("app_version_numeric", "==", app_version_numeric))
    )

    docs = query.stream()
    return [Announcement.from_dict(doc.to_dict()) for doc in docs]


def get_general_announcements(last_checked_at: Optional[datetime] = None) -> List[Announcement]:
    """
    Get active, non-expired general announcements.
    If last_checked_at is provided, only returns announcements created after that time.
    """
    now = datetime.now(timezone.utc)
    announcements_ref = db.collection("announcements")
    query = announcements_ref.where(filter=FieldFilter("type", "==", AnnouncementType.ANNOUNCEMENT.value)).where(
        filter=FieldFilter("active", "==", True)
    )

    docs = query.stream()
    announcements = []

    for doc in docs:
        data = doc.to_dict()
        announcement = Announcement.from_dict(data)

        # Skip if created before last check
        if last_checked_at and announcement.created_at <= last_checked_at:
            continue

        # Skip if expired
        if announcement.expires_at and announcement.expires_at < now:
            continue

        announcements.append(announcement)

    # Sort by created_at descending
    announcements.sort(key=lambda x: x.created_at, reverse=True)
    return announcements


def get_all_announcements(
    announcement_type: Optional[AnnouncementType] = None,
    active_only: bool = False,
) -> List[Announcement]:
    """
    Get all announcements with optional filtering.

    Args:
        announcement_type: Filter by type (changelog, feature, announcement)
        active_only: If True, only return active announcements
    """
    announcements_ref = db.collection("announcements")
    query = announcements_ref

    if announcement_type:
        query = query.where(filter=FieldFilter("type", "==", announcement_type.value))

    if active_only:
        query = query.where(filter=FieldFilter("active", "==", True))

    docs = query.stream()
    announcements = [Announcement.from_dict(doc.to_dict()) for doc in docs]

    # Sort by created_at descending
    announcements.sort(key=lambda x: x.created_at, reverse=True)
    return announcements


def create_announcement(announcement: Announcement) -> Announcement:
    """Create a new announcement."""
    if announcement.app_version and not announcement.app_version_numeric:
        announcement.app_version_numeric = version_to_numeric(announcement.app_version)
    if announcement.firmware_version and not announcement.firmware_version_numeric:
        announcement.firmware_version_numeric = version_to_numeric(announcement.firmware_version)

    doc_ref = db.collection("announcements").document(announcement.id)
    doc_ref.set(announcement.to_dict())
    return announcement


def update_announcement(announcement_id: str, updates: dict) -> Optional[Announcement]:
    """Update an existing announcement."""
    doc_ref = db.collection("announcements").document(announcement_id)
    doc = doc_ref.get()
    if not doc.exists:
        return None
        
    if 'app_version' in updates:
        updates['app_version_numeric'] = version_to_numeric(updates['app_version'])
    if 'firmware_version' in updates:
        updates['firmware_version_numeric'] = version_to_numeric(updates['firmware_version'])

    doc_ref.update(updates)
    return get_announcement_by_id(announcement_id)


def delete_announcement(announcement_id: str) -> bool:
    """Delete an announcement."""
    doc_ref = db.collection("announcements").document(announcement_id)
    doc = doc_ref.get()
    if not doc.exists:
        return False

    doc_ref.delete()
    return True


def deactivate_announcement(announcement_id: str) -> bool:
    """Soft delete - set active to False."""
    doc_ref = db.collection("announcements").document(announcement_id)
    doc = doc_ref.get()
    if not doc.exists:
        return False

    doc_ref.update({"active": False})
    return True
