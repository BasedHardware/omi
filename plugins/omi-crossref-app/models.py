from typing import Any, Optional

from pydantic import BaseModel


class ChatToolResponse(BaseModel):
    """标准 Omi 工具返回结构。"""

    result: Optional[str] = None
    error: Optional[str] = None


class SearchWorksInput(BaseModel):
    """搜索作品输入参数。"""

    query: Optional[Any] = ""
    max_results: Optional[Any] = 5


class GetWorkInput(BaseModel):
    """根据 DOI 查询作品输入参数。"""

    doi: Optional[Any] = ""


class AuthorWorksInput(BaseModel):
    """根据作者查询作品输入参数。"""

    author: Optional[Any] = ""
    max_results: Optional[Any] = 5
