from typing import List

from pydantic import BaseModel, Field


class SearchOverviewFolder(BaseModel):
    """One conversation folder with its non-discarded conversation count."""

    id: str
    name: str
    icon: str = 'folder'
    color: str = '#6B7280'
    count: int = 0


class SearchOverviewResponse(BaseModel):
    """Counts behind the global-search tiles shown before the user types.

    Every count is decoration: a failed aggregation reports 0 instead of
    failing the response.
    """

    starred: int = 0
    folders: List[SearchOverviewFolder] = Field(default_factory=list)
    recaps: int = 0
    memories: int = 0
    people: int = 0
    places: int = 0
