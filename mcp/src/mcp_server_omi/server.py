from enum import Enum
import json
from typing import List, Optional
from datetime import datetime
import requests
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from pydantic import BaseModel

# TODO: can use pydantic Fields on descriptions?


class MemoryCategory(str, Enum):
    core = "core"
    hobbies = "hobbies"
    lifestyle = "lifestyle"
    interests = "interests"
    habits = "habits"
    work = "work"
    skills = "skills"
    learnings = "learnings"
    other = "other"


class ConversationCategory(str, Enum):
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


base_url = "https://backend-208440318997.us-central1.run.app/v1/mcp/"
# base_url = "http://127.0.0.1:8000/v1/mcp/"

# TODO: get conversation by id (with transcript segments) endpoint


class OmiTools(str, Enum):
    GET_MEMORIES = "get_memories"
    CREATE_MEMORY = "create_memory"
    DELETE_MEMORY = "delete_memory"
    EDIT_MEMORY = "edit_memory"
    GET_CONVERSATIONS = "get_conversations"
    CREATE_USER = "create_user"


class UserCredentials(BaseModel):
    """User credentials for signup.

    Args:
        email (str): User's email address
        password (str): User's password
        name (str, optional): User's name. Defaults to None.

    Returns:
        dict: Status of the signup operation. Including the user's unique identifier. (uid)
    """

    email: str
    password: str
    name: str


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
    categories: List[MemoryCategory] = []


class CreateMemory(BaseModel):
    """Create a new memory for the user.
    A memory is a piece of information about the user's life accross different domains.

    Args:
        uid (str): The user's unique identifier.
        content (str): The content of the memory.
        category (MemoryCategory): The category of the memory.

    Returns:
        dict: The created memory object.
    """

    uid: str
    content: str
    category: MemoryCategory


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
        start_date (datetime, optional): Filter conversations after this date
        end_date (datetime, optional): Filter conversations before this date
        categories (List[str], optional): Filter by categories. Defaults to [].
        limit (int, optional): The maximum number of conversations to retrieve. Defaults to 25.
        offset (int, optional): Number of conversations to skip. Defaults to 0.

    Returns:
        List: A list of conversation objects.
    """

    uid: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    categories: List[ConversationCategory] = []
    # limit: int = 25
    # offset: int = 0


def create_user(email: str, password: str, name: str) -> dict:
    response = requests.post(
        f"{base_url}users",
        json={"email": email, "password": password, "name": name},
    )
    return response.json()


def get_memories(
    uid: str,
    limit: int = 100,
    categories: List[MemoryCategory] = [],
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


def create_memory(uid: str, content: str, category: MemoryCategory) -> dict:
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
    logger: logging.Logger,
    uid: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    categories: List[ConversationCategory] = [],
    # limit: int = 25,
    # offset: int = 0,
) -> List:
    params = {"limit": 10, "offset": 0, "include_transcript_segments": False}
    if start_date:
        params["start_date"] = start_date.isoformat()
    if end_date:
        params["end_date"] = end_date.isoformat()
    if categories:
        params["categories"] = ",".join(categories)

    logger.info(f"Getting conversations with params: {params}")
    response = requests.get(
        f"{base_url}conversations",
        params=params,
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
                name=OmiTools.CREATE_USER,
                description="Create a new user",
                inputSchema=UserCredentials.model_json_schema(),
            ),
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

        if name == OmiTools.CREATE_USER:
            result = create_user(
                email=arguments["email"],
                password=arguments["password"],
                name=arguments.get("name"),
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

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
            # return [TextContent(type="text", text=json.dumps(arguments, indent=2))]
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
                logger,
                _uid,
                start_date=arguments.get("start_date"),
                end_date=arguments.get("end_date"),
                categories=arguments.get("categories", []),
                # limit=arguments.get("limit", 25),
                # offset=arguments.get("offset", 0),
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        raise ValueError(f"Unknown tool: {name}")

    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)
