"""Gateway-only outline and notes clients; existing notes prompts stay authoritative."""

import json
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable

from langchain_core.callbacks import BaseCallbackHandler

from utils.llm.gateway_client import feature_auto_lane_id
from utils.llm.usage_tracker import track_usage
from utils.generated_compute import require_current_generated_compute
from utils.conversations.v3 import metrics


def get_or_create_omi_gateway_llm(*args, **kwargs):
    """Gateway model, with LangChain providers loaded on first use.

    process_conversation imports v3 at module load; that import must not pull in
    every chat-model provider.
    """
    from utils.llm.providers import get_or_create_omi_gateway_llm as gateway_llm

    return gateway_llm(*args, **kwargs)


_notes_mode: ContextVar[tuple[str, bool, Callable[[str], None] | None] | None] = ContextVar(
    'v3_notes_mode', default=None
)


class CallEvents(BaseCallbackHandler):
    def __init__(self, kind):
        self.kind = kind

    def on_chat_model_start(self, serialized, messages, **kwargs):
        metrics.MODEL_CALLS.labels(self.kind).inc()


class SectionEvents(BaseCallbackHandler):
    def __init__(self, emit):
        self.emit = emit
        self.text = ''
        self.sent = set()

    def on_llm_new_token(self, token, **kwargs):
        self.text += token
        decoder = json.JSONDecoder()
        for index, char in enumerate(self.text):
            if char != '{' or index in self.sent:
                continue
            try:
                row, _ = decoder.raw_decode(self.text[index:])
            except ValueError:
                continue
            if isinstance(row, dict) and isinstance(row.get('body_markdown'), str) and row.get('heading'):
                self.sent.add(index)
                self.emit('## ' + row['heading'] + '\n\n' + row['body_markdown'])


@contextmanager
def notes_mode(uid, *, foreground=False, emit=None):
    token = _notes_mode.set((uid, foreground, emit))
    try:
        yield
    finally:
        _notes_mode.reset(token)


def active():
    return _notes_mode.get() is not None


def notes_client():
    mode = _notes_mode.get()
    if mode is None:
        return None
    uid, foreground, emit = mode
    feature = 'conversation_v3_summary_open' if foreground else 'conversation_v3_summary'
    require_current_generated_compute(feature, uid=uid, provider='openai', allow_byok=False)
    options = {'request_timeout': 90, 'max_retries': 0}
    model = get_or_create_omi_gateway_llm(
        feature_auto_lane_id(feature), streaming=bool(emit), options=options, feature=feature
    )
    inherited = model.callbacks
    callbacks = list(inherited if isinstance(inherited, list) else inherited.handlers if inherited else [])
    callbacks.append(CallEvents('summary_open' if foreground else 'summary_background'))
    if emit:
        callbacks.append(SectionEvents(emit))
    return model.model_copy(update={'callbacks': callbacks})


def outline(uid, messages):
    require_current_generated_compute('conversation_v3_outline', uid=uid, provider='openai', allow_byok=False)
    with track_usage(uid, 'conversation_v3_outline'):
        model = get_or_create_omi_gateway_llm(
            feature_auto_lane_id('conversation_v3_outline'),
            streaming=True,
            options={'request_timeout': 30, 'max_retries': 0},
            feature='conversation_v3_outline',
        )
        return ''.join(
            str(chunk.content or '')
            for chunk in model.bind(reasoning_effort='none', response_format={'type': 'json_object'}).stream(messages)
        )


def foreground():
    mode = _notes_mode.get()
    return bool(mode and mode[1])


def short_tasks(uid, conversation):
    """Keep the existing task extraction rules without buying a short summary."""
    from utils.llm.conversation_notes_prompts import ACTION_ITEM_EXTRACTION_RULES
    from models.structured_extraction import ExtractedActionItem

    if foreground():
        return conversation.structured
    require_current_generated_compute('conv_action_items', uid=uid, provider='openai', allow_byok=False)
    from utils.speakers.display import display_participants

    participants = display_participants(conversation.transcript_segments)
    transcript = '\n'.join(
        f'{s.start:.1f} {participants.for_segment(s).label}: {s.text}' for s in conversation.transcript_segments
    )
    messages = [
        (
            'system',
            ACTION_ITEM_EXTRACTION_RULES
            + '\nReturn JSON {"action_items": [...]} with items conforming to: '
            + json.dumps(ExtractedActionItem.model_json_schema()),
        ),
        ('human', transcript),
    ]
    with track_usage(uid, 'conv_action_items'):
        model = get_or_create_omi_gateway_llm(
            feature_auto_lane_id('conv_action_items'),
            options={'request_timeout': 30, 'max_retries': 0},
            feature='conv_action_items',
        )
        metrics.MODEL_CALLS.labels('short_tasks').inc()
        # No response_format: the conv_action_items gateway lane declares no structured output and
        # rejects json_object with 400 capability_not_supported, which failed every short v3 tile
        # (2026-11-18). The prompt asks for JSON; _action_items parses it defensively.
        response = model.bind(reasoning_effort='low').invoke(messages)
    if not isinstance(response.content, str):
        raise ValueError('short_tasks_non_text_response')
    structured = conversation.structured.model_copy(deep=True)
    structured.action_items = [
        ExtractedActionItem.model_validate(item).to_action_item() for item in _action_items(response.content)
    ]
    return structured


def _action_items(text):
    """The action items from the first complete JSON value in the reply.

    Tolerates a code fence or prose around it. An object must carry an ``action_items`` list; a bare
    array is taken as the list. Anything else raises so the task retries.
    """
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in '{[':
            continue
        try:
            value, _ = decoder.raw_decode(text, index)
        except ValueError:
            continue
        items = value.get('action_items') if isinstance(value, dict) else value
        if not isinstance(items, list):
            raise ValueError('short_tasks_action_items_not_list')
        return items
    raise ValueError('short_tasks_no_json')
