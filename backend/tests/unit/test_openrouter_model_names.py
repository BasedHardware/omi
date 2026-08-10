"""Unit tests for shared OpenRouter vendor model-name prefixing."""

from utils.llm.openrouter_model_names import openrouter_provider_model_name


def test_openrouter_prefixes_gemini_with_google():
    assert openrouter_provider_model_name('openrouter', 'gemini-3-flash-preview') == 'google/gemini-3-flash-preview'


def test_openrouter_prefixes_gpt_with_openai():
    assert openrouter_provider_model_name('openrouter', 'gpt-5.6-luna') == 'openai/gpt-5.6-luna'
    assert openrouter_provider_model_name('openrouter', 'gpt-5-nano') == 'openai/gpt-5-nano'


def test_openrouter_prefixes_o_series_with_openai():
    assert openrouter_provider_model_name('openrouter', 'o1-preview') == 'openai/o1-preview'
    assert openrouter_provider_model_name('openrouter', 'o3-mini') == 'openai/o3-mini'
    assert openrouter_provider_model_name('openrouter', 'o4-mini') == 'openai/o4-mini'


def test_openrouter_leaves_other_models_unchanged():
    assert openrouter_provider_model_name('openrouter', 'anthropic/claude-3.5-sonnet') == 'anthropic/claude-3.5-sonnet'
    assert openrouter_provider_model_name('openrouter', 'sonar-pro') == 'sonar-pro'


def test_non_openrouter_providers_leave_model_unchanged():
    assert openrouter_provider_model_name('openai', 'gpt-5.6-luna') == 'gpt-5.6-luna'
    assert openrouter_provider_model_name('gemini', 'gemini-2.5-flash-lite') == 'gemini-2.5-flash-lite'
