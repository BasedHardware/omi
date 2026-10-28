"""Shaped app/channel execution with bounded, cacheable context assembly."""

import json
import logging
from dataclasses import replace
from typing import Any, Optional

from utils.messaging.projection import surface_runtime
from utils.llm.shaped_agent import Turn
from utils.llm.prompt_cache import chat_cache_options, model_supports_explicit_cache
from utils.retrieval.chat_mount import chat_request_messages
from utils.retrieval.turn_refs import initialize_turn_refs
from utils.retrieval.transcript_recall import UNVERIFIED_TRANSCRIPT_ANSWER, transcript_recall_unverified

logger = logging.getLogger(__name__)


class _ShapedToolsStopped(Exception):
    pass


async def run_shaped_chat_stream(
    system_prompt,
    messages,
    tool_schemas,
    tool_registry,
    callback,
    full_response,
    safety_guard,
    configurable,
    *,
    shadow=False,
) -> Optional[str]:
    from utils.retrieval import agentic as a
    from utils.messaging.context import prepare as prepare_context, assemble, schedule_refresh, degraded, take_prepared

    if 'turn_refs' not in configurable:
        initialize_turn_refs(configurable)
    mount = a.chat_mount(tool_schemas, deadline_seconds=a.AGENT_STREAM_MAX_DURATION_SECONDS)
    runtime = surface_runtime.get()
    if runtime is not None:
        mount = replace(mount, skills=(*mount.skills, runtime.skill))
    model = a.get_llm('chat_agent', streaming=True)
    cache_enabled = a.gpt56_explicit_cache_enabled() and model_supports_explicit_cache(model)
    options = chat_cache_options() if cache_enabled else None
    cache_enabled = cache_enabled and options is not None
    context = {'summary': '', 'digest': ''}
    if not shadow:
        try:
            prepared = await take_prepared(configurable['user_id'], configurable.get('chat_session_id'))
            if prepared is None:
                prepared = await prepare_context(
                    configurable['user_id'],
                    configurable.get('chat_session_id'),
                    configurable.get('context_message_ids', ()),
                )
            context = prepared
        except Exception as error:
            degraded(error)
    evidence = assemble(
        messages,
        runtime=runtime,
        timezone_name=configurable.get('user_timezone'),
        request_context={
            'selected_app': configurable.get('shaped_selected_app'),
        },
        summary=context['summary'],
        digest=context['digest'],
        explicit_cache=cache_enabled,
        stable_prefix=mount.prefix() + json.dumps(list(mount.tools), default=str),
    )
    evidence = chat_request_messages(evidence, configurable)
    surface = runtime.channel if runtime is not None and runtime.channel else 'app'
    usage_token = a.set_usage_context(
        configurable['user_id'],
        'chat_agent',
        surface=surface,
        turn_id=configurable.get('thread_id') or (runtime.turn_id if runtime else None),
    )
    try:
        params: dict[str, Any] = {'tools': list(mount.tools), 'tool_choice': 'auto', 'max_completion_tokens': 8192}
        if cache_enabled:
            params['extra_body'] = {'prompt_cache_options': options}
        model = model.bind(**params)

        async def model_turn(shape, history):
            chunks, text_parts = [], []
            hold_unverified_recall = transcript_recall_unverified(configurable)
            async for chunk in model.astream(history):
                chunks.append(chunk)
                text = a.openai_content_text(getattr(chunk, 'content', ''))
                if text:
                    if hold_unverified_recall:
                        text_parts.append(text)
                        continue
                    if not text_parts and full_response:
                        await a.put_answer_text(callback, full_response, '\n\n')
                    text_parts.append(text)
                    await a.put_answer_text(callback, full_response, text)
            calls = a.openai_tool_calls(chunks)
            if not calls and hold_unverified_recall:
                text_parts = [UNVERIFIED_TRANSCRIPT_ANSWER]
                prefix = '\n\n' if full_response else ''
                await a.put_answer_text(callback, full_response, prefix + UNVERIFIED_TRANSCRIPT_ANSWER)
            assistant = {
                'role': 'assistant',
                'content': ''.join(text_parts),
                'tool_calls': [
                    {
                        'id': call['id'],
                        'type': 'function',
                        'function': {'name': call['name'], 'arguments': json.dumps(call['input'])},
                    }
                    for call in calls
                ],
            }
            return Turn(value=''.join(text_parts), tool_calls=tuple(calls), messages=(assistant,))

        async def execute_tools(calls):
            if shadow:
                # All shadow tool effects, including device callbacks and read-side
                # persistence, are simulated. No user-owned config is mutated.
                return [
                    {
                        'role': 'tool',
                        'tool_call_id': call['id'],
                        'content': 'Shadow evaluation: tool execution suppressed.',
                    }
                    for call in calls
                ]
            results = await a.execute_independent_tool_calls(
                list(calls),
                name_of=lambda c: c['name'],
                input_of=lambda c: c['input'],
                id_of=lambda c: c['id'],
                tool_registry=tool_registry,
                configurable=configurable,
                safety_guard=safety_guard,
                callback=callback,
                full_response=full_response,
                result_factory=lambda c, result: {'role': 'tool', 'tool_call_id': c['id'], 'content': result},
            )
            if results is None:
                raise _ShapedToolsStopped
            return results

        result = await a.run_loop(mount, evidence, model_turn, execute_tools, explicit_cache=cache_enabled)
        if result.reason != 'stopped':
            await a.end_with_answer_guarantee(callback, full_response, 'shaped')
            return result.reason
        return await a.end_with_answer_guarantee(callback, full_response, 'shaped')
    except _ShapedToolsStopped:
        return 'tool_safety_stop'
    except TimeoutError:
        raise
    except Exception as error:
        if shadow:
            logger.warning('Shaped chat shadow failed error_type=%s', type(error).__name__)
            return 'shadow_failure'
        await a.handle_llm_error_async(error, 'openai', feature='chat_agent', model='omi:auto:chat-agent')
        await a.put_outcome_text(callback, full_response, a.AGENT_STREAM_FAILURE_MESSAGE)
        await callback.end()
        return f'provider_{type(error).__name__}'
    finally:
        a.reset_usage_context(usage_token)
        if not shadow:
            schedule_refresh(
                configurable['user_id'],
                configurable.get('chat_session_id'),
                configurable.get('context_message_ids', ()),
            )
