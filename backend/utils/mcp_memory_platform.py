from typing import Any

from utils.memory.platform import build_memory_platform_capability


def build_mcp_memory_platform_payload() -> dict[str, Any]:
    return build_memory_platform_capability().model_dump(mode="json")
