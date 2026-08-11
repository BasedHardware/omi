from utils.llm.file_chat import (
    FILE_CHAT_ASSISTANT_INSTRUCTIONS,
    get_file_chat_assistant_create_params,
    get_file_chat_vision_model,
)
from utils.llm.model_config import get_direct_openai_surface_model


def test_file_chat_models_resolve_from_the_direct_openai_surface_configuration():
    assert get_file_chat_vision_model() == get_direct_openai_surface_model('file_chat_vision')
    assert get_file_chat_assistant_create_params(timeout=30.0)['model'] == get_direct_openai_surface_model(
        'file_chat_assistant'
    )


def test_file_chat_assistant_params_preserve_the_retrieval_contract():
    params = get_file_chat_assistant_create_params(timeout=30.0)

    assert params == {
        'name': 'File Reader',
        'instructions': FILE_CHAT_ASSISTANT_INSTRUCTIONS,
        'model': 'gpt-5.6-luna',
        'tools': [{'type': 'file_search'}],
        'timeout': 30.0,
    }
