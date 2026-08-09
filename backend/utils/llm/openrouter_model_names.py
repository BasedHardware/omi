"""OpenRouter vendor-prefixed model name helpers.

OpenRouter expects vendor-scoped model IDs (e.g. ``google/gemini-…``,
``openai/gpt-…``). Product routing keeps bare model names in model_config; this
module is the shared place that adds the vendor prefix at the API boundary.
"""


def openrouter_provider_model_name(provider: str, model: str) -> str:
    """Return the OpenRouter API model id for a provider/model pair.

    - openrouter + gemini* → google/{model}
    - openrouter + gpt-* or o1/o3/o4* → openai/{model}
    - otherwise leave model unchanged
    """
    if provider != 'openrouter' or not model:
        return model
    if model.startswith('gemini'):
        return f'google/{model}'
    if model.startswith('gpt-') or model.startswith(('o1', 'o3', 'o4')):
        return f'openai/{model}'
    return model
