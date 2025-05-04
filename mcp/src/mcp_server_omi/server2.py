from enum import Enum
import json
from typing import List
import requests
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from pydantic import BaseModel
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("omi")

class MemoryCategoryEnum(str, Enum):
    personal = "personal"
    education = "education"
    health = "health"
    finance = "finance"
    legal = "legal"
    philosophy = "philosophy"
    spiritual = "spiritual"
    science = "science"
    entrepreneurship = "entrepreneurship"
    parenting = "parenting"
    romance = "romantic"
    travel = "travel"
    inspiration = "inspiration"
    technology = "technology"
    business = "business"
    social = "social"
    work = "work"
    sports = "sports"
    politics = "politics"
    literature = "literature"
    history = "history"
    architecture = "architecture"
    # Added at 2024-01-23
    music = "music"
    weather = "weather"
    news = "news"
    entertainment = "entertainment"
    psychology = "psychology"
    real = "real"
    design = "design"
    family = "family"
    economics = "economics"
    environment = "environment"
    other = "other"


base_url = "http://127.0.0.1:8000/v1/mcp/"


@mcp.tool()
def get_memories(
    uid: str,
    limit: int = 100,
    categories: List[MemoryCategoryEnum] = [],
) -> List:
    """Retrieve a list of user memories.
    Memories are pieces of information about the user's life accross different domains.

    Args:
        uid (str): The user's unique identifier.
        limit (int, optional): The maximum number of memories to retrieve. Defaults to 100.
        categories (List[MemoryCategoryEnum], optional): The categories of memories to retrieve. Defaults to [].

    Returns:
        str: A JSON object containing the list of memories.
    """
    response = requests.get(
        f"{base_url}memories",
        # params={"limit": limit, "categories": categories},
        headers={"uid": uid},
    )
    return response.json()

if __name__ == "__main__":
    mcp.run(transport="stdio")
