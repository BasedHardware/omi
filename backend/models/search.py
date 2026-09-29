from typing import List, Optional

from pydantic import BaseModel, Field


class SearchOverviewFolder(BaseModel):
    """One conversation folder with its non-discarded conversation count (null when it could not be counted)."""

    id: str
    name: str
    icon: str = 'folder'
    color: str = '#6B7280'
    count: Optional[int] = None


class SearchOverviewResponse(BaseModel):
    """Counts behind the global-search tiles shown before the user types.

    Every count is decoration: a failed aggregation reports null (never a
    false 0) instead of failing the response.
    """

    starred: Optional[int] = None
    folders: List[SearchOverviewFolder] = Field(default_factory=list)
    recaps: Optional[int] = None
    memories: Optional[int] = None
    people: Optional[int] = None
    places: Optional[int] = None
