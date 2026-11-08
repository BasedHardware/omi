"""Folder entities and operations; wire validation belongs to the routers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol

from pydantic import BaseModel, ConfigDict

from .base import Page


class FolderEntity(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str
    name: str = ''
    description: str | None = None
    color: str = '#6B7280'
    icon: str = '📁'
    created_at: datetime | None = None
    updated_at: datetime | None = None
    order: int = 0
    is_default: bool = False
    is_system: bool = False
    category_mapping: str | None = None
    conversation_count: int = 0
    revision: int = 1


class FolderCreate(BaseModel):
    name: str
    description: str | None = None
    color: str | None = None
    icon: str | None = None


class FolderUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None
    order: int | None = None


class FoldersTx(Protocol):
    def create(self, draft: FolderCreate, *, mutation_id: str | None = None) -> FolderEntity: ...
    def update(
        self,
        folder_id: str,
        patch: FolderUpdate,
        *,
        expected_revision: int | None = None,
        mutation_id: str | None = None,
    ) -> FolderEntity | None: ...
    def delete(
        self,
        folder_id: str,
        *,
        move_to_folder_id: str | None = None,
        expected_revision: int | None = None,
        mutation_id: str | None = None,
    ) -> bool: ...
    def reorder(self, folder_ids: list[str], *, mutation_id: str | None = None) -> bool: ...
    def initialize_system(self, *, mutation_id: str | None = None) -> list[FolderEntity]: ...
    def refresh_conversation_count(
        self, folder_id: str, *, expected_revision: int | None = None, mutation_id: str | None = None
    ) -> int: ...
    def move_conversation(
        self, conversation_id: str, folder_id: str | None, *, mutation_id: str | None = None
    ) -> bool: ...
    def bulk_move_conversations(
        self, conversation_ids: list[str], folder_id: str, *, mutation_id: str | None = None
    ) -> int: ...


class FoldersRepo(FoldersTx, Protocol):
    def list(self, *, limit: int | None = None, cursor: str | None = None) -> Page[FolderEntity]: ...
    def get(self, folder_id: str) -> FolderEntity | None: ...
    def get_by_category_mapping(self, category_mapping: str) -> FolderEntity | None: ...

    # Cross-domain conversation read stays document-shaped and offset-based until A6.
    def conversations_in_folder(
        self, folder_id: str, *, limit: int = 100, offset: int = 0, include_discarded: bool = False
    ) -> list[dict]: ...


# System folders that are created for new users
SYSTEM_FOLDERS: List[Dict[str, Any]] = [
    {
        'name': 'Work',
        'category_mapping': 'work',
        'icon': '💼',
        'color': '#3B82F6',
        'description': 'Work, business, professional, and career-related conversations',
    },
    {
        'name': 'Personal',
        'category_mapping': 'personal',
        'icon': '👤',
        'color': '#10B981',
        'description': 'Personal life, family, health, hobbies, and self-improvement',
    },
    {
        'name': 'Social',
        'category_mapping': 'social',
        'icon': '👥',
        'color': '#8B5CF6',
        'description': 'Friends, social gatherings, entertainment, and casual conversations',
    },
]

# Map all categories to one of the 3 system folders
CATEGORY_TO_FOLDER_MAPPING: Dict[str, str] = {
    # Work folder - professional/business/career related
    'work': 'work',
    'business': 'work',
    'entrepreneurship': 'work',
    'technology': 'work',
    'finance': 'work',
    'economics': 'work',
    'legal': 'work',
    'education': 'work',  # Often career/learning related
    'science': 'work',
    'architecture': 'work',
    'design': 'work',
    # Personal folder - individual/self/family related
    'personal': 'personal',
    'health': 'personal',
    'family': 'personal',
    'parenting': 'personal',
    'romance': 'personal',
    'romantic': 'personal',
    'spiritual': 'personal',
    'inspiration': 'personal',
    'travel': 'personal',
    'sports': 'personal',
    'philosophy': 'personal',
    'psychology': 'personal',
    'literature': 'personal',
    'history': 'personal',
    # Social folder - friends/entertainment/casual related
    'social': 'social',
    'entertainment': 'social',
    'music': 'social',
    'politics': 'social',
    'news': 'social',
    'weather': 'social',
    'environment': 'social',
    'real': 'social',
    # 'other' is intentionally omitted: it is the catch-all category and routes to the
    # user's default folder, not a category bucket (handled in resolve_category_folder_id, #4043).
}


def resolve_category_folder_id(category: Optional[str], user_folders: List[FolderEntity]) -> Optional[str]:
    """Folder id of the system folder that owns a conversation's category.

    Every meaningful conversation category folds onto one of the three system buckets via
    ``CATEGORY_TO_FOLDER_MAPPING``; this returns the user's folder for that bucket so AI
    folder assignment can fall back to the category-aligned folder instead of the
    catch-all default when the model is unsure (issue #4043). Returns None for the
    catch-all ``other`` category (so genuinely uncertain conversations stay in the default
    folder rather than Personal), when the category is unknown, or when the user has no
    folder for that bucket (e.g. they deleted a system folder).
    """
    # 'other' is the catch-all category, not a meaningful topic. Treat it like a missing
    # category so an uncertain conversation falls back to the user's default folder rather
    # than the Personal bucket 'other' would otherwise fold onto (issue #4043).
    if not category or str(category).lower() == 'other':
        return None
    bucket = CATEGORY_TO_FOLDER_MAPPING.get(str(category).lower())
    if not bucket:
        return None
    for folder in user_folders or []:
        if folder.category_mapping == bucket:
            return folder.id
    return None
