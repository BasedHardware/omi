"""L3 output-language authority at the episode prompt boundary.

Adapts the existing invoke seam, leaving the incremental prompt module owned by
L3 untouched. Shadow performs no additional model or preference call.
"""

from config.refactor_modes import serving_for


def resolved_invoke(uid, conversation_language, invoke):
    if not serving_for('LIFECYCLE_V2_MODE', uid):
        return invoke
    try:
        from utils.llm.output_language import resolve_output_language
    except ImportError:
        # L3 is integrated independently; until then retain the current prompt.
        return invoke
    language = resolve_output_language(uid, conversation_language)
    if invoke is None:
        from utils.episodes.incremental import invoke_model

        invoke = invoke_model

    def with_language(account, messages):
        return invoke(account, [*messages, ('system', f'Write all episode output in {language}.')])

    return with_language
