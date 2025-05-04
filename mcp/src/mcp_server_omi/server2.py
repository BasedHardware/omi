from enum import Enum
from typing import List
import requests
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
    A memory is a piece of information about the user's life accross different domains.

    Args:
        uid (str): The user's unique identifier.
        limit (int, optional): The maximum number of memories to retrieve. Defaults to 100.
        categories (List[MemoryCategoryEnum], optional): The categories of memories to retrieve. Defaults to [].

    Returns:
        str: A JSON object containing the list of memories.
    """
    params = {"limit": limit}
    if categories:
        params["categories"] = ",".join(categories)

    response = requests.get(
        f"{base_url}memories",
        params=params,
        headers={"uid": uid},
    )
    return response.json()


@mcp.tool()
def create_memory(uid: str, content: str, category: MemoryCategoryEnum) -> dict:
    """Create a new memory for the user.
    A memory is a piece of information about the user's life accross different domains.

    Args:
        uid (str): The user's unique identifier.
        content (str): The content of the memory.
        category (MemoryCategoryEnum): The category of the memory.

    Returns:
        dict: The created memory object.
    """
    response = requests.post(
        f"{base_url}memories",
        headers={"uid": uid},
        json={"content": content, "category": category},
    )
    return response.json()


@mcp.tool()
def delete_memory(uid: str, memory_id: str) -> dict:
    """Delete a memory by its ID.
    A memory is a piece of information about the user's life accross different domains.

    Args:
        uid (str): The user's unique identifier.
        memory_id (str): The ID of the memory to delete.

    Returns:
        dict: Status of the operation.
    """
    response = requests.delete(f"{base_url}memories/{memory_id}", headers={"uid": uid})
    return response.json()


@mcp.tool()
def edit_memory(uid: str, memory_id: str, content: str) -> dict:
    """Edit the content of an existing memory.

    Args:
        uid (str): The user's unique identifier.
        memory_id (str): The ID of the memory to edit.
        content (str): The new content for the memory.

    Returns:
        dict: Status of the operation.
    """
    response = requests.patch(
        f"{base_url}memories/{memory_id}",
        headers={"uid": uid},
        params={"value": content},
    )
    return response.json()


@mcp.tool()
def get_conversations(
    uid: str,
    include_discarded: bool = False,
    limit: int = 25,
) -> List:  # TODO: output schema matters?
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
    response = requests.get(
        f"{base_url}conversations",
        params={"include_discarded": include_discarded, "limit": limit},
        headers={"uid": uid},
    )
    return response.json()


if __name__ == "__main__":
    mcp.run(transport="stdio")
