from typing import List

from models.conversation import ConversationPhoto, Structured
from utils.llm.clients import llm_mini


async def describe_image(base64_data: str) -> str:
    """
    Generates a description for a base64 encoded image using a vision model via LangChain.
    """
    prompt = (
        "You are my AI assistant, seeing the world through my smart glasses. In a single, descriptive paragraph, "
        "tell me what's happening from a first-person perspective. Focus on the most important aspects of the scene: "
        "the people, their actions, the key objects, and the overall environment. What is the general mood or atmosphere?"
    )

    message = {
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_data}"},
            },
        ],
    }

    response = await llm_mini.ainvoke([message], config={"max_tokens": 150})
    description = response.content
    return description.strip() if description is not None and description != '""' else ""
