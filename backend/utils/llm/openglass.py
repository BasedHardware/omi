from typing import Any, Protocol, cast

from utils.llm.clients import get_llm
from utils.llm.usage_tracker import track_usage, Features

MessagePart = dict[str, object]
ChatMessage = dict[str, object]


class AsyncVisionLlm(Protocol):
    async def ainvoke(self, input: object, *, config: dict[str, Any] | None = None) -> object: ...


def _response_text(response: object) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in cast(list[object], content):
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                block = cast(dict[str, object], item)
                text = block.get("text") or block.get("content") or ""
                if text:
                    parts.append(str(text))
            elif item is not None:
                parts.append(str(item))
        return "".join(parts)
    return "" if content is None else str(content)


async def describe_image(uid: str, base64_data: str) -> str:
    """
    Generates a description for a base64 encoded image using a vision model via LangChain.
    """
    prompt = (
        "You are my AI assistant, seeing the world through my smart glasses. In a single, descriptive paragraph, "
        "tell me what's happening from a first-person perspective. Focus on the most important aspects of the scene: "
        "the people, their actions, the key objects, and the overall environment. What is the general mood or atmosphere?"
    )

    content: list[MessagePart] = [
        {"type": "text", "text": prompt},
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64_data}"},
        },
    ]
    message: ChatMessage = {
        "role": "user",
        "content": content,
    }

    with track_usage(uid, Features.OPENGLASS):
        response = await cast(AsyncVisionLlm, get_llm('openglass')).ainvoke([message], config={"max_tokens": 150})
    description = _response_text(response).strip()
    return description if description != '""' else ""
