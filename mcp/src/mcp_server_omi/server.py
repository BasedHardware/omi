"""
Example FastMCP server that uses Unicode characters in various places to help test
Unicode handling in tools and inspectors.
"""

from enum import Enum
import json
from typing import List, Optional
from mcp.server.fastmcp import FastMCP
from datetime import datetime
import requests
import logging
from pathlib import Path
from typing import Sequence
from mcp.server import Server
from mcp.server.session import ServerSession
from mcp.server.stdio import stdio_server
from mcp.types import (
    ClientCapabilities,
    TextContent,
    Tool,
    ListRootsResult,
    RootsCapability,
)
from enum import Enum
import git
from pydantic import BaseModel


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


class OmiTools(str, Enum):
    GET_MEMORIES = "get_memories"


class GetMemories(BaseModel):
    """Retrieve a list of user memories.
    Memories are pieces of information about the user's life accross different domains.

    Args:
        uid (str): The user's unique identifier.
        limit (int, optional): The maximum number of memories to retrieve. Defaults to 100.
        categories (List[MemoryCategoryEnum], optional): The categories of memories to retrieve. Defaults to [].

    Returns:
        str: A JSON object containing the list of memories.
    """
    uid: str
    limit: int = 100
    categories: List[MemoryCategoryEnum] = []


def get_memories(
    uid: str,
    limit: int = 100,
    categories: List[MemoryCategoryEnum] = [],
) -> List:

    response = requests.get(
        f"{base_url}/memories",
        # params={"limit": limit, "categories": categories},
        headers={"uid": uid},
    )
    return response.json()


async def serve(uid: str | None) -> None:
    logger = logging.getLogger(__name__)

    if uid is not None:
        logger.info(f"Using uid: {uid}")

    server = Server("mcp-omi")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=OmiTools.GET_MEMORIES,
                description="Retrieve a list of memories",
                inputSchema=GetMemories.model_json_schema(),
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        logger.info(f"Calling tool: {name} with arguments: {arguments}")

        # TODO: correct? both accept uid or env var?
        uid = arguments["uid"] if uid is None else uid  # noqa: F823
        if name == OmiTools.GET_MEMORIES:
            result = get_memories(
                uid,
                limit=arguments["limit"],
                categories=arguments["categories"],
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        raise ValueError(f"Unknown tool: {name}")

    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)
