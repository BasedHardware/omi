import os
from enum import Enum
import json
from typing import List, Optional
from datetime import datetime
import requests
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from pydantic import BaseModel, Field


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


base_url = os.getenv("OMI_API_BASE_URL", "https://api.omi.me/v1/mcp/")
if not base_url or base_url == "":
    raise Exception("Base URL not found")


class OmiTools(str, Enum):
    GET_MEMORIES = "get_memories"
    CREATE_MEMORY = "create_memory"
    DELETE_MEMORY = "delete_memory"
    EDIT_MEMORY = "edit_memory"
    GET_CONVERSATIONS = "get_conversations"
    GET_CONVERSATION_BY_ID = "get_conversation_by_id"
    GET_ACTION_ITEMS = "get_action_items"
    CREATE_ACTION_ITEM = "create_action_item"
    UPDATE_ACTION_ITEM = "update_action_item"
    DELETE_ACTION_ITEM = "delete_action_item"


class GetMemories(BaseModel):
    api_key: Optional[str] = Field(
        description="The user's MCP API key. If not provided, it will be read from the OMI_API_KEY environment variable. For more details, see https://docs.omi.me/doc/developer/MCP",
        default=None,
    )
    categories: List[MemoryCategory] = Field(description="The categories of memories to filter by.", default=[])
    limit: int = Field(description="The number of memories to retrieve.", default=100)
    offset: int = Field(description="The offset of the memories to retrieve.", default=0)


class CreateMemory(BaseModel):
    api_key: Optional[str] = Field(
        description="The user's MCP API key. If not provided, it will be read from the OMI_API_KEY environment variable. For more details, see https://docs.omi.me/doc/developer/MCP",
        default=None,
    )
    content: str = Field(description="The content of the memory.")
    category: MemoryCategory = Field(description="The category of the memory to create.")


class DeleteMemory(BaseModel):
    api_key: Optional[str] = Field(
        description="The user's MCP API key. If not provided, it will be read from the OMI_API_KEY environment variable. For more details, see https://docs.omi.me/doc/developer/MCP",
        default=None,
    )
    memory_id: str = Field(description="The ID of the memory to delete.")


class EditMemory(BaseModel):
    api_key: Optional[str] = Field(
        description="The user's MCP API key. If not provided, it will be read from the OMI_API_KEY environment variable. For more details, see https://docs.omi.me/doc/developer/MCP",
        default=None,
    )
    memory_id: str = Field(description="The ID of the memory to edit.")
    content: str = Field(description="The new content for the memory.")


class GetConversations(BaseModel):
    api_key: Optional[str] = Field(
        description="The user's MCP API key. If not provided, it will be read from the OMI_API_KEY environment variable. For more details, see https://docs.omi.me/doc/developer/MCP",
        default=None,
    )
    start_date: Optional[str] = Field(description="Filter conversations after this date (yyyy-mm-dd)", default=None)
    end_date: Optional[str] = Field(description="Filter conversations before this date (yyyy-mm-dd)", default=None)
    categories: List[ConversationCategory] = Field(description="Filter by conversation categories.", default=[])
    limit: int = Field(description="The number of conversations to retrieve.", default=20)
    offset: int = Field(description="The offset of the conversations to retrieve.", default=0)


class GetConversationById(BaseModel):
    api_key: Optional[str] = Field(
        description="The user's MCP API key. If not provided, it will be read from the OMI_API_KEY environment variable. For more details, see https://docs.omi.me/doc/developer/MCP",
        default=None,
    )
    conversation_id: str = Field(description="The ID of the conversation to retrieve.")


class GetActionItems(BaseModel):
    api_key: Optional[str] = Field(
        description="The user's MCP API key. If not provided, it will be read from the OMI_API_KEY environment variable. For more details, see https://docs.omi.me/doc/developer/MCP",
        default=None,
    )
    completed: Optional[bool] = Field(description="Filter by completion status.", default=None)
    conversation_id: Optional[str] = Field(description="Filter by conversation ID.", default=None)
    start_date: Optional[str] = Field(description="Filter by creation start date (ISO 8601).", default=None)
    end_date: Optional[str] = Field(description="Filter by creation end date (ISO 8601).", default=None)
    due_start_date: Optional[str] = Field(description="Filter by due start date (ISO 8601).", default=None)
    due_end_date: Optional[str] = Field(description="Filter by due end date (ISO 8601).", default=None)
    limit: int = Field(description="The number of action items to retrieve.", default=50)
    offset: int = Field(description="The offset of the action items to retrieve.", default=0)


class CreateActionItem(BaseModel):
    api_key: Optional[str] = Field(
        description="The user's MCP API key. If not provided, it will be read from the OMI_API_KEY environment variable. For more details, see https://docs.omi.me/doc/developer/MCP",
        default=None,
    )
    description: str = Field(description="The action item description.")
    completed: bool = Field(description="Whether the action item is completed.", default=False)
    due_at: Optional[str] = Field(description="Due date (ISO 8601).", default=None)
    conversation_id: Optional[str] = Field(description="Associated conversation ID.", default=None)


class UpdateActionItem(BaseModel):
    api_key: Optional[str] = Field(
        description="The user's MCP API key. If not provided, it will be read from the OMI_API_KEY environment variable. For more details, see https://docs.omi.me/doc/developer/MCP",
        default=None,
    )
    action_item_id: str = Field(description="The ID of the action item to update.")
    description: Optional[str] = Field(description="Updated description.", default=None)
    completed: Optional[bool] = Field(description="Updated completion status.", default=None)
    due_at: Optional[str] = Field(description="Updated due date (ISO 8601, set to null to clear).", default=None)


class DeleteActionItem(BaseModel):
    api_key: Optional[str] = Field(
        description="The user's MCP API key. If not provided, it will be read from the OMI_API_KEY environment variable. For more details, see https://docs.omi.me/doc/developer/MCP",
        default=None,
    )
    action_item_id: str = Field(description="The ID of the action item to delete.")


def get_memories(
    logger: logging.Logger,
    api_key: str,
    offset: int = 0,
    limit: int = 100,
    categories: List[MemoryCategory] = [],
) -> List:
    logger.info(f"Getting memories with params: {offset}, {limit}, {categories}")
    params = {"offset": offset, "limit": limit}
    if categories:
        params["categories"] = ",".join([c.value for c in categories])
    logger.info(f"get_memories params: {params}")
    try:
        response = requests.get(
            f"{base_url}memories",
            params=params,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        logger.info(f"get_memories response: {response.json()}")
        return response.json()
    except Exception as e:
        logger.error(f"Error getting memories: {e}")
        raise e


def create_memory(api_key: str, content: str, category: MemoryCategory) -> dict:
    response = requests.post(
        f"{base_url}memories",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"content": content, "category": category},
    )
    return response.json()


def delete_memory(api_key: str, memory_id: str) -> dict:
    response = requests.delete(
        f"{base_url}memories/{memory_id}",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    return response.json()


def edit_memory(api_key: str, memory_id: str, content: str) -> dict:
    response = requests.patch(
        f"{base_url}memories/{memory_id}",
        headers={"Authorization": f"Bearer {api_key}"},
        params={"value": content},
    )
    return response.json()


def get_conversations(
    logger: logging.Logger,
    api_key: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    categories: List[ConversationCategory] = [],
    limit: int = 20,
    offset: int = 0,
) -> List:
    params = {"limit": limit, "offset": offset}
    if start_date:
        try:
            params["start_date"] = datetime.strptime(start_date, "%Y-%m-%d").isoformat()
        except ValueError:
            logger.warning(f"Could not parse start date: {start_date}")
    if end_date:
        try:
            params["end_date"] = datetime.strptime(end_date, "%Y-%m-%d").isoformat()
        except ValueError:
            logger.warning(f"Could not parse end date: {end_date}")
    if categories:
        params["categories"] = ",".join([c.value for c in categories])

    logger.info(f"Getting conversations with params: {params}")
    response = requests.get(
        f"{base_url}conversations",
        params=params,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    return response.json()


def get_conversation_by_id(api_key: str, conversation_id: str) -> dict:
    response = requests.get(
        f"{base_url}conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    return response.json()


def get_action_items(
    api_key: str,
    completed: Optional[bool] = None,
    conversation_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    due_start_date: Optional[str] = None,
    due_end_date: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    params = {"limit": limit, "offset": offset}
    if completed is not None:
        params["completed"] = completed
    if conversation_id:
        params["conversation_id"] = conversation_id
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    if due_start_date:
        params["due_start_date"] = due_start_date
    if due_end_date:
        params["due_end_date"] = due_end_date

    response = requests.get(
        f"{base_url}action-items",
        params=params,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    return response.json()


def create_action_item(
    api_key: str,
    description: str,
    completed: bool = False,
    due_at: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> dict:
    payload = {"description": description, "completed": completed}
    if due_at is not None:
        payload["due_at"] = due_at
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id

    response = requests.post(
        f"{base_url}action-items",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
    )
    return response.json()


def update_action_item(api_key: str, action_item_id: str, update_data: dict) -> dict:
    response = requests.patch(
        f"{base_url}action-items/{action_item_id}",
        headers={"Authorization": f"Bearer {api_key}"},
        json=update_data,
    )
    return response.json()


def delete_action_item(api_key: str, action_item_id: str) -> dict:
    response = requests.delete(
        f"{base_url}action-items/{action_item_id}",
        headers={"Authorization": f"Bearer {api_key}"},
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
                description="Retrieve a list of memories. A memory is a known fact about the user across multiple domains.",
                inputSchema=GetMemories.model_json_schema(),
            ),
            Tool(
                name=OmiTools.CREATE_MEMORY,
                description="Create a new memory. A memory is a known fact about the user across multiple domains.",
                inputSchema=CreateMemory.model_json_schema(),
            ),
            Tool(
                name=OmiTools.DELETE_MEMORY,
                description="Delete a memory by ID. A memory is a known fact about the user across multiple domains.",
                inputSchema=DeleteMemory.model_json_schema(),
            ),
            Tool(
                name=OmiTools.EDIT_MEMORY,
                description="Edit a memory's content. A memory is a known fact about the user across multiple domains.",
                inputSchema=EditMemory.model_json_schema(),
            ),
            Tool(
                name=OmiTools.GET_CONVERSATIONS,
                description="Retrieve a list of conversation metadata. To get full transcripts, use get_conversation_by_id.",
                inputSchema=GetConversations.model_json_schema(),
            ),
            Tool(
                name=OmiTools.GET_CONVERSATION_BY_ID,
                description="Retrieve a conversation by ID including each segment of the transcript.",
                inputSchema=GetConversationById.model_json_schema(),
            ),
            Tool(
                name=OmiTools.GET_ACTION_ITEMS,
                description="Retrieve a list of action items (tasks/to-dos).",
                inputSchema=GetActionItems.model_json_schema(),
            ),
            Tool(
                name=OmiTools.CREATE_ACTION_ITEM,
                description="Create a new action item (task/to-do).",
                inputSchema=CreateActionItem.model_json_schema(),
            ),
            Tool(
                name=OmiTools.UPDATE_ACTION_ITEM,
                description="Update an existing action item.",
                inputSchema=UpdateActionItem.model_json_schema(),
            ),
            Tool(
                name=OmiTools.DELETE_ACTION_ITEM,
                description="Delete an action item by ID.",
                inputSchema=DeleteActionItem.model_json_schema(),
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        logger.info(f"Calling tool: {name} with arguments: {arguments}")

        api_key = arguments.get("api_key") or os.getenv("OMI_API_KEY")
        if not api_key:
            raise ValueError("API key not provided and OMI_API_KEY environment variable not set.")

        if name == OmiTools.GET_MEMORIES:
            # return [TextContent(type="text", text=json.dumps(arguments, indent=2))]
            categories: List[str] = arguments.get("categories", [])
            if not isinstance(categories, list):
                raise ValueError(f"categories must be a list, got {type(categories)}")
            categories_enum = []
            for category in categories:
                try:
                    categories_enum.append(MemoryCategory(category))
                except ValueError:
                    logger.warning(f"Could not parse category: {category}")

            result = get_memories(
                logger,
                api_key,
                offset=arguments.get("offset", 0),
                limit=arguments.get("limit", 100),
                categories=categories_enum,
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == OmiTools.CREATE_MEMORY:
            # return [TextContent(type="text", text=json.dumps(arguments, indent=2))]
            result = create_memory(
                api_key,
                content=arguments["content"],
                category=arguments["category"],
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == OmiTools.DELETE_MEMORY:
            result = delete_memory(api_key, memory_id=arguments["memory_id"])
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == OmiTools.EDIT_MEMORY:
            result = edit_memory(
                api_key,
                memory_id=arguments["memory_id"],
                content=arguments["content"],
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == OmiTools.GET_CONVERSATIONS:
            result = get_conversations(
                logger,
                api_key,
                start_date=arguments.get("start_date"),
                end_date=arguments.get("end_date"),
                categories=arguments.get("categories", []),
                limit=arguments.get("limit", 20),
                offset=arguments.get("offset", 0),
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == OmiTools.GET_CONVERSATION_BY_ID:
            result = get_conversation_by_id(api_key, conversation_id=arguments["conversation_id"])
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == OmiTools.GET_ACTION_ITEMS:
            result = get_action_items(
                api_key,
                completed=arguments.get("completed"),
                conversation_id=arguments.get("conversation_id"),
                start_date=arguments.get("start_date"),
                end_date=arguments.get("end_date"),
                due_start_date=arguments.get("due_start_date"),
                due_end_date=arguments.get("due_end_date"),
                limit=arguments.get("limit", 50),
                offset=arguments.get("offset", 0),
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == OmiTools.CREATE_ACTION_ITEM:
            result = create_action_item(
                api_key,
                description=arguments["description"],
                completed=arguments.get("completed", False),
                due_at=arguments.get("due_at"),
                conversation_id=arguments.get("conversation_id"),
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == OmiTools.UPDATE_ACTION_ITEM:
            update_data = {}
            if "description" in arguments and arguments.get("description") is not None:
                update_data["description"] = arguments.get("description")
            if "completed" in arguments and arguments.get("completed") is not None:
                update_data["completed"] = arguments.get("completed")
            if "due_at" in arguments:
                update_data["due_at"] = arguments.get("due_at")
            result = update_action_item(
                api_key,
                action_item_id=arguments["action_item_id"],
                update_data=update_data,
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == OmiTools.DELETE_ACTION_ITEM:
            result = delete_action_item(api_key, action_item_id=arguments["action_item_id"])
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        raise ValueError(f"Unknown tool: {name}")

    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)


# TODO:
# - add get conversations by semantic search + reranking
