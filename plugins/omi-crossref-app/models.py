from typing import Optional

from pydantic import BaseModel


class ChatToolResponse(BaseModel):
    result: Optional[str] = None
    error: Optional[str] = None


class SearchWorksInput(BaseModel):
    query: str
    max_results: int = 5


class GetWorkInput(BaseModel):
    doi: str


class AuthorWorksInput(BaseModel):
    author: str
    max_results: int = 5
