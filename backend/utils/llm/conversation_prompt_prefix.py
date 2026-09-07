"""One canonical, reusable prompt prefix for conversation-wide LLM work."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, List, Optional
from zoneinfo import ZoneInfo

from models.calendar_context import CalendarMeetingContext
from models.conversation_photo import ConversationPhoto
from utils.llm.prompt_cache import EXPLICIT_CACHE_BREAKPOINT, has_cacheable_prefix
from utils.llm.gateway_client import should_route_features_through_gateway
from utils.llm.model_config import get_model_config

SHARED_CONVERSATION_PREAMBLE = """You are analyzing one Omi conversation for the account owner.
Treat the supplied transcript and capture metadata as the sole source of truth. Preserve attribution and uncertainty.
The conversation context below is shared by several independent tasks. Do not perform a task until you read the
task-specific instructions that follow it."""


def shared_conversation_cache_supported() -> bool:
    """Return true only when notes and L1 memory reach the same OpenAI model cache."""
    if should_route_features_through_gateway():
        # generated_route_overrides.yaml pins both lanes to OpenAI gpt-5.6-luna.
        return True
    note_route = get_model_config('conv_structure')
    memory_route = get_model_config('memory_l1')
    return note_route == memory_route and note_route[1] == 'openai' and note_route[0].startswith('gpt-5.6')


@dataclass(frozen=True)
class ConversationPromptPrefix:
    """Rendered prefix bytes plus the per-conversation routing key.

    Consumers append their own instructions after these messages. Keeping this
    value immutable prevents feature-specific text from leaking before the
    explicit cache breakpoint.
    """

    conversation_id: str
    context: str

    @property
    def cache_key(self) -> str:
        return f'omi-conv-{self.conversation_id}'

    @property
    def cache_eligible(self) -> bool:
        return has_cacheable_prefix(f'{SHARED_CONVERSATION_PREAMBLE}\n{self.context}')

    def messages(self, *, cache_enabled: bool) -> List[dict[str, Any]]:
        context_block: dict[str, Any] = {'type': 'text', 'text': self.context}
        if cache_enabled and self.cache_eligible:
            context_block['prompt_cache_breakpoint'] = EXPLICIT_CACHE_BREAKPOINT
        return [
            {'role': 'system', 'content': SHARED_CONVERSATION_PREAMBLE},
            {'role': 'system', 'content': [context_block]},
        ]


def build_conversation_prompt_prefix(
    *,
    conversation_id: str,
    transcript: str,
    started_at: datetime,
    timezone_name: str,
    language_code: str,
    calendar_context: Optional[CalendarMeetingContext] = None,
    photos: Optional[List[ConversationPhoto]] = None,
) -> ConversationPromptPrefix:
    try:
        user_tz = ZoneInfo(timezone_name) if timezone_name else timezone.utc
    except Exception:
        user_tz = timezone.utc
    aware_started_at = started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
    started_at_local = aware_started_at.astimezone(user_tz).replace(tzinfo=None).isoformat()
    metadata_lines = [
        f'- Captured at: {started_at_local} ({timezone_name or "UTC"})',
    ]
    if calendar_context:
        participants = ', '.join(
            filter(
                None,
                [
                    (
                        f'{participant.name} <{participant.email}>'
                        if participant.name and participant.email
                        else participant.name or participant.email
                    )
                    for participant in calendar_context.participants
                ],
            )
        )
        metadata_lines.extend(
            [
                f'- Meeting title: {calendar_context.title}',
                f'- Participants: {participants or "Not specified"}',
                f'- Platform: {calendar_context.platform or "Not specified"}',
                f'- Meeting notes: {calendar_context.notes or "Not specified"}',
            ]
        )

        placeholder_ids = set(re.findall(r'(?m)^(?:\[segment:[^\]]+\] )?Speaker (\d+):', transcript))
        named_labels = {
            match.casefold()
            for match in re.findall(r'(?m)^(?:\[segment:[^\]]+\] )?([^:\n]+):', transcript)
            if not match.startswith('Speaker ')
        }
        remaining_names = [
            participant.name
            for participant in calendar_context.participants
            if participant.name and participant.name.casefold() not in named_labels
        ]
        if len(placeholder_ids) == 1 and len(remaining_names) == 1:
            speaker_id = next(iter(placeholder_ids))
            transcript = re.sub(
                rf'(?m)^((?:\[segment:[^\]]+\] )?)Speaker {re.escape(speaker_id)}:',
                rf'\1{remaining_names[0]}:',
                transcript,
            )

    context_parts = ['CONVERSATION METADATA\n' + '\n'.join(metadata_lines), f'FULL TRANSCRIPT\n{transcript.strip()}']
    if photos:
        photo_descriptions = ConversationPhoto.photos_as_string(photos, include_timestamps=True)
        if photo_descriptions != 'None':
            context_parts.append(f'CAPTURED PHOTO DESCRIPTIONS\n{photo_descriptions}')

    return ConversationPromptPrefix(conversation_id=conversation_id, context='\n\n'.join(context_parts))
