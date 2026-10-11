"""Conversation cache routing; prompt text is built by conversation_prompt_context."""

from utils.llm.gateway_client import should_route_features_through_gateway
from utils.llm.model_config import get_model_config, uses_explicit_cache_and_chat_sanitizer


def shared_conversation_cache_supported() -> bool:
    """Return true only when notes and L1 memory reach the same OpenAI model cache."""
    if should_route_features_through_gateway():
        # generated_route_overrides.yaml pins both lanes to OpenAI gpt-x-luna.
        return True
    note_route = get_model_config('conv_structure')
    memory_route = get_model_config('memory_l1')
    return (
        note_route == memory_route
        and note_route[1] == 'openai'
        and uses_explicit_cache_and_chat_sanitizer(note_route[0])
    )
