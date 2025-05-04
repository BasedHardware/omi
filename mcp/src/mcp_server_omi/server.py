from enum import Enum
import json
from typing import List
import requests
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from pydantic import BaseModel


class MemoryFilterOptions(str, Enum):
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
    CREATE_MEMORY = "create_memory"
    DELETE_MEMORY = "delete_memory"
    EDIT_MEMORY = "edit_memory"
    GET_CONVERSATIONS = "get_conversations"


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
    categories: List[MemoryFilterOptions] = []


# TODO: why doesn't allow same list of categories?
class CreateMemory(BaseModel):
    """Create a new memory for the user.
    A memory is a piece of information about the user's life accross different domains.

    Args:
        uid (str): The user's unique identifier.
        content (str): The content of the memory.
        category (MemoryCategoryEnum): The category of the memory.

    Returns:
        dict: The created memory object.
    """

    uid: str
    content: str
    category: MemoryFilterOptions


class DeleteMemory(BaseModel):
    """Delete a memory by its ID.
    A memory is a piece of information about the user's life accross different domains.

    Args:
        uid (str): The user's unique identifier.
        memory_id (str): The ID of the memory to delete.

    Returns:
        dict: Status of the operation.
    """

    uid: str
    memory_id: str


class EditMemory(BaseModel):
    """Edit the content of an existing memory.

    Args:
        uid (str): The user's unique identifier.
        memory_id (str): The ID of the memory to edit.
        content (str): The new content for the memory.

    Returns:
        dict: Status of the operation.
    """

    uid: str
    memory_id: str
    content: str


class GetConversations(BaseModel):
    """Retrieve a list of user conversations.
    A conversation is the voice recording transcript of a conversation the user had.
    The conversation object contains the transcript segments, timestamps, geolocation, and a "structured" field, which summarizes the conversation.

    Args:
        uid (str): The user's unique identifier.
        include_discarded (bool, optional): Whether to include discarded conversations. Defaults to False.
        limit (int, optional): The maximum number of conversations to retrieve. Defaults to 25.

    Returns:
        List: A list of conversation objects.
    """

    uid: str
    include_discarded: bool = False
    limit: int = 25


def get_memories(
    uid: str,
    limit: int = 100,
    categories: List[MemoryFilterOptions] = [],
) -> List:
    params = {"limit": limit}
    if categories:
        params["categories"] = ",".join(categories)

    response = requests.get(
        f"{base_url}memories",
        params=params,
        headers={"uid": uid},
    )
    return response.json()


def create_memory(uid: str, content: str, category: MemoryFilterOptions) -> dict:
    response = requests.post(
        f"{base_url}memories",
        headers={"uid": uid},
        json={"content": content, "category": category},
    )
    return response.json()


def delete_memory(uid: str, memory_id: str) -> dict:
    response = requests.delete(f"{base_url}memories/{memory_id}", headers={"uid": uid})
    return response.json()


def edit_memory(uid: str, memory_id: str, content: str) -> dict:
    response = requests.patch(
        f"{base_url}memories/{memory_id}",
        headers={"uid": uid},
        params={"value": content},
    )
    return response.json()


def get_conversations(
    uid: str,
    include_discarded: bool = False,
    limit: int = 25,
) -> List:
    response = requests.get(
        f"{base_url}conversations",
        params={"include_discarded": include_discarded, "limit": limit},
        headers={"uid": uid},
    )
    return response.json()


async def serve(uid: str | None) -> None:
    logger = logging.getLogger(__name__)
    # if uid is not None:
    #     logger.info(f"Using uid: {uid}")

    server = Server("mcp-omi")
    logger.info("mcp-omi server started")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=OmiTools.GET_MEMORIES,
                description="Retrieve a list of memories",
                inputSchema=GetMemories.model_json_schema(),
            ),
            Tool(
                name=OmiTools.CREATE_MEMORY,
                description="Create a new memory",
                inputSchema=CreateMemory.model_json_schema(),
            ),
            Tool(
                name=OmiTools.DELETE_MEMORY,
                description="Delete a memory by ID",
                inputSchema=DeleteMemory.model_json_schema(),
            ),
            Tool(
                name=OmiTools.EDIT_MEMORY,
                description="Edit a memory's content",
                inputSchema=EditMemory.model_json_schema(),
            ),
            Tool(
                name=OmiTools.GET_CONVERSATIONS,
                description="Retrieve a list of conversations",
                inputSchema=GetConversations.model_json_schema(),
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        logger.info(f"Calling tool: {name} with arguments: {arguments}")

        # _uid = arguments["uid"] if not uid else uid
        # if _uid is None:
        #     raise ValueError(f"uid is required {arguments}")
        _uid = arguments["uid"]
        if name == OmiTools.GET_MEMORIES:
            result = get_memories(
                _uid,
                limit=arguments["limit"],
                categories=arguments["categories"],
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == OmiTools.CREATE_MEMORY:
            result = create_memory(
                _uid,
                content=arguments["content"],
                category=arguments["category"],
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == OmiTools.DELETE_MEMORY:
            result = delete_memory(_uid, memory_id=arguments["memory_id"])
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == OmiTools.EDIT_MEMORY:
            result = edit_memory(
                _uid,
                memory_id=arguments["memory_id"],
                content=arguments["content"],
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == OmiTools.GET_CONVERSATIONS:
            result = get_conversations(
                _uid,
                include_discarded=arguments["include_discarded"],
                limit=arguments["limit"],
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        raise ValueError(f"Unknown tool: {name}")

    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)
