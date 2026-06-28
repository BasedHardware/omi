"""Shared orchestration for the folder MCP tools (REST + SSE).

Wraps ``database.folders`` with the same validation the REST folders router uses,
so the MCP REST endpoints (``routers/mcp.py``) and the SSE dispatch
(``routers/mcp_sse.py``) share one implementation and cannot drift. This lets an
assistant organize a user's conversations into folders for the two-way memory
bank (issue #4862).
"""

from typing import List, Optional

import database.conversations as conversations_db
import database.folders as folders_db

# Mirrors the custom-folder cap enforced by the REST folders router.
MAX_CUSTOM_FOLDERS = 50


class FolderError(Exception):
    """Base error for folder operations."""


class FolderNotFound(FolderError):
    """A folder (or move target) does not exist."""


class ConversationNotFound(FolderError):
    """The conversation to move does not exist."""


class ConversationLocked(FolderError):
    """The conversation requires a paid plan."""


class SystemFolderProtected(FolderError):
    """System folders (Work / Personal / Social) cannot be deleted."""


class FolderLimitReached(FolderError):
    """The custom-folder cap has been reached."""


class InvalidFolderRequest(FolderError):
    """The request is missing or has invalid fields."""


def list_folders(uid: str) -> List[dict]:
    return folders_db.get_folders(uid)


def create_folder(
    uid: str,
    name: str,
    description: Optional[str] = None,
    color: Optional[str] = None,
    icon: Optional[str] = None,
) -> dict:
    name = (name or "").strip()
    if not name:
        raise InvalidFolderRequest("Folder name is required")
    custom_count = len([f for f in folders_db.get_folders(uid) if not f.get("is_system")])
    if custom_count >= MAX_CUSTOM_FOLDERS:
        raise FolderLimitReached(f"Maximum folder limit reached ({MAX_CUSTOM_FOLDERS} custom folders)")
    return folders_db.create_folder(uid, name=name, description=description, color=color, icon=icon)


def update_folder(
    uid: str,
    folder_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    color: Optional[str] = None,
    icon: Optional[str] = None,
) -> dict:
    if not folders_db.get_folder(uid, folder_id):
        raise FolderNotFound("Folder not found")
    update_data: dict = {}
    if name is not None:
        name = name.strip()
        if not name:
            raise InvalidFolderRequest("Folder name cannot be empty")
        update_data["name"] = name
    if description is not None:
        update_data["description"] = description
    if color is not None:
        update_data["color"] = color
    if icon is not None:
        update_data["icon"] = icon
    if not update_data:
        raise InvalidFolderRequest("No fields to update")
    folders_db.update_folder(uid, folder_id, update_data)
    return folders_db.get_folder(uid, folder_id)


def delete_folder(uid: str, folder_id: str, move_to_folder_id: Optional[str] = None) -> None:
    folder = folders_db.get_folder(uid, folder_id)
    if not folder:
        raise FolderNotFound("Folder not found")
    if folder.get("is_system"):
        raise SystemFolderProtected("Cannot delete a system folder")
    if move_to_folder_id:
        if move_to_folder_id == folder_id:
            raise InvalidFolderRequest("Cannot move conversations to the folder being deleted")
        if not folders_db.get_folder(uid, move_to_folder_id):
            raise FolderNotFound("Target folder not found")
    folders_db.delete_folder(uid, folder_id, move_to_folder_id=move_to_folder_id)


def move_conversation(uid: str, conversation_id: str, folder_id: Optional[str]) -> None:
    """Assign a conversation to a folder. ``folder_id=None`` removes it from any folder."""
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if conversation is None:
        raise ConversationNotFound("Conversation not found")
    if conversation.get("is_locked", False):
        raise ConversationLocked("A paid plan is required to access this conversation.")
    if folder_id and not folders_db.get_folder(uid, folder_id):
        raise FolderNotFound("Folder not found")
    folders_db.move_conversation_to_folder(uid, conversation_id, folder_id)
