"""Provider/derived leaves only; no admission, relevance, dedupe or minimum stubs."""

from unittest.mock import patch


def noop(*args, **kwargs):
    return None


async def async_noop(*args, **kwargs):
    return None


def install_leaves(stack, processing, finalizer, cassette):
    from utils.conversations.memory_extraction_telemetry import ConversationMemoryExtractionResult, PATH_CANONICAL

    for name, value in {
        'get_conversation_notes': cassette,
        # Vendor relevance scores are fixed to keep; deterministic rule
        # relevance and every minimum/dedupe decision remain real.
        'should_discard_conversation': lambda *a, **kw: False,
        'jev_discard_probability': lambda *a, **kw: 0.0,
        '_extract_memories_canonical': lambda *a, **kw: ConversationMemoryExtractionResult(
            count=0, source='replay', path=PATH_CANONICAL
        ),
        'trigger_conversation_apps': noop,
        'assign_conversation_to_folder': lambda *a, **kw: (None, 0.0, 'offline_provider_leaf'),
        'save_structured_vector': noop,
        '_save_action_items': noop,
        'update_goal_progress': noop,
        'conversation_created_webhook': async_noop,
    }.items():
        stack.enter_context(patch.object(processing, name, value))
    stack.enter_context(
        patch.object(processing.conversations_db, 'create_audio_files_from_chunks', lambda *a, **kw: [])
    )
    stack.enter_context(patch.object(finalizer, 'trigger_external_integrations', async_noop))
    stack.enter_context(patch.object(finalizer, '_save_summary_vector_fail_soft', noop))
