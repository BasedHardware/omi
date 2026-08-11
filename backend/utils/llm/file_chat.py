from typing import Any, BinaryIO, Dict

from openai import AsyncOpenAI, AssistantEventHandler, OpenAI
from openai.types.beta.threads import TextContentBlock
from openai.types.file_purpose import FilePurpose

from utils.llm.gateway_client import raise_if_gateway_feature_mode_blocks_direct_model_surface
from utils.llm.model_config import get_direct_openai_surface_model

FILE_CHAT_ASSISTANT_INSTRUCTIONS = (
    'You are a helpful assistant that answers questions about the provided file. '
    'Use the file_search tool to search the file contents when needed.'
)

_async_openai: AsyncOpenAI | None = None
_openai: OpenAI | None = None


def assert_direct_file_chat_allowed() -> None:
    raise_if_gateway_feature_mode_blocks_direct_model_surface('file_chat.openai_files_assistants_vision')


def get_file_chat_client() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI(timeout=120.0, max_retries=1)
    return _openai


def get_async_file_chat_client() -> AsyncOpenAI:
    global _async_openai
    if _async_openai is None:
        _async_openai = AsyncOpenAI(timeout=120.0, max_retries=1)
    return _async_openai


def upload_file(file: BinaryIO, *, purpose: FilePurpose) -> Any:
    return get_file_chat_client().files.create(file=file, purpose=purpose)


def get_file_chat_assistant_create_params(*, timeout: float) -> Dict[str, Any]:
    return {
        'name': 'File Reader',
        'instructions': FILE_CHAT_ASSISTANT_INSTRUCTIONS,
        'model': get_direct_openai_surface_model('file_chat_assistant'),
        'tools': [{'type': 'file_search'}],
        'timeout': timeout,
    }


def get_file_chat_vision_model() -> str:
    return get_direct_openai_surface_model('file_chat_vision')


def get_assistant_response_text(messages: Any) -> str:
    if messages.data and len(messages.data) > 0:
        first_block = messages.data[0].content[0]
        if isinstance(first_block, TextContentBlock):
            return first_block.text.value
        # Fall back to the original attribute access for any non-text block,
        # which raises AttributeError — matching the prior behavior.
        return first_block.text.value
    raise Exception('No response received from assistant')


def new_file_chat_stream_event_handler() -> AssistantEventHandler:
    return AssistantEventHandler()
