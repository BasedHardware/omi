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


# Vendor prefix -> the BYOK key type that vendor's models are billed against. Mirrors
# ``utils.llm.clients._effective_byok_provider`` from the other side of the boundary:
# there a bare model picks the key, here a vendor-prefixed one does.
_VENDOR_PREFIX_TO_BYOK_PROVIDER = {
    'openai': 'openai',
    'google': 'gemini',
}


def openrouter_byok_vendor_route(provider: str, model: str) -> tuple[str, str] | None:
    """Vendor provider/model a BYOK caller's own key should serve, or None.

    An OpenRouter-hosted OpenAI-family model is billed to the user's OpenAI key, so the
    backend forwards ``X-Omi-Byok-OpenAI-Key`` for these lanes. Callers that check
    credentials or pick a provider by the route's literal provider need this mapping, or
    they fail closed on a key the user did supply.
    """
    if provider != 'openrouter' or not model:
        return None
    vendor, separator, bare_model = model.partition('/')
    if not separator or not bare_model:
        return None
    byok_provider = _VENDOR_PREFIX_TO_BYOK_PROVIDER.get(vendor)
    if byok_provider is None:
        return None
    return byok_provider, bare_model
