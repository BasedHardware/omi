"""Feed offline bundles through the production notes prompt builders."""

from datetime import datetime
from config.episode_writer import EpisodeWriterSettings

from langchain_core.output_parsers import PydanticOutputParser

from models.calendar_context import CalendarMeetingContext, MeetingParticipant
from models.episode_extraction import EpisodeStructuredExtraction
from models.structured_extraction import RichStructuredExtraction
from testing.episode_notes.schema import EpisodeFixture
from utils.conversations.episode_compaction import compact_episode_items
from utils.conversations.episode_evidence import EvidenceItem, render_episode_evidence
from utils.conversations.meeting_context_render import (
    MAX_SCREEN_CHARACTERS,
    MeetingContextPack,
    PriorMeetingNote,
    render_meeting_context_pack,
)
from utils.conversations.meeting_participants import normalize_meeting_participants
from utils.conversations.screen_text_digest import digest_screen_rows
from utils.llm.conversation_notes_prompts import (
    conversation_notes_static_instructions,
    conversation_notes_volatile_instructions,
)
from utils.llm.conversation_prompt_context import build_conversation_prompt_prefix
from utils.llm.episode_notes_prompts import (
    EPISODE_WAKE_WORD_RULES,
    episode_static_instructions,
    episode_volatile_instructions,
)
from utils.llm.meeting_notes_rich_prompts import rich_static_instructions, rich_volatile_instructions

CANDIDATE_MODEL = 'openai/gpt-6-luna'
SCORING_MODEL = 'openai/gpt-6-sol'
CANDIDATE_PROMPT = episode_static_instructions(
    PydanticOutputParser(pydantic_object=EpisodeStructuredExtraction).get_format_instructions(),
    conversation_notes_static_instructions,
)
BASELINE_PROMPT = rich_static_instructions(
    PydanticOutputParser(pydantic_object=RichStructuredExtraction).get_format_instructions(),
    conversation_notes_static_instructions,
)
SOURCE_FIELDS = {
    'transcript_segments': 'speech',
    'screen_moments': 'screen_frame',
    'screen_ocr': 'screen_ocr',
    'messages': 'message',
    'roster': 'roster',
    'calendar': 'calendar',
    'prior_conversations': 'prior_conversation',
    'open_tasks': 'open_task',
    'device_state': 'device_state',
}
APPROXIMATIONS = [
    'No image pixels, production retrieval, repair retries, task extraction or persistence.',
    'UTC output in English; capture end substitutes for generation time; task capture disabled.',
    'Actor labels define known speaker clusters; each unnamed turn remains a separate unresolved cluster.',
    'Flattened calendar and roster observations are retained as meeting notes; no inferred names/emails/organizations.',
    'No owner catalog, mixed remote-channel binding, or people/goals/memory context absent from the bundle.',
    'Baseline caps prior context at three 300-character gists and uses the production 6000-character background cap.',
    'Baseline OCR uses the production digest; unstructured rows lack app/window metadata, so messaging exclusion is approximate.',
    'Typed messages use Messages rows (body excluded by the baseline digest); screen moments are text, capped at 900 characters.',
]


def fixture_evidence_items(episode: EpisodeFixture) -> list[EvidenceItem]:
    return compact_episode_items(
        [
            EvidenceItem(source_kind=kind, **item.model_dump())
            for field, kind in SOURCE_FIELDS.items()
            for item in getattr(episode.evidence, field)
        ]
    )


def candidate_request(
    episode: EpisodeFixture, arm: str, *, settings: EpisodeWriterSettings | None = None, items=None
) -> tuple[str, dict]:
    bundle = episode.evidence
    words = sum(len(item.content.split()) for item in bundle.transcript_segments)
    density = (
        'Use 1-2 sections; target ~95 words across the entire note.'
        if words < 500
        else (
            'Use 2-4 sections; target ~240 words across the entire note.'
            if words < 2500
            else 'Use 4-6 sections; target ~480 words across the entire note.'
        )
    )
    common = dict(
        response_language='en',
        density=density,
        started_local_iso=bundle.started_at,
        current_local_iso=bundle.finished_at,
        tz_label='UTC',
        task_intelligence_capture=False,
    )
    if arm == 'episode':
        settings = settings or EpisodeWriterSettings(selection='compact', claims=True)
        items = fixture_evidence_items(episode) if items is None else items
        volatile = episode_volatile_instructions(
            **common,
            evidence_block=render_episode_evidence(items),
            wake_word_rules=EPISODE_WAKE_WORD_RULES if any(item.wake_word_invocation for item in items) else '',
            capture_finished_local_iso=bundle.finished_at,
        )
        prompt = (
            CANDIDATE_PROMPT
            if settings.claims
            else episode_static_instructions(
                PydanticOutputParser(pydantic_object=RichStructuredExtraction).get_format_instructions(),
                conversation_notes_static_instructions,
                include_claims=False,
            )
        )
        return prompt, {'instructions': volatile}
    if arm != 'baseline':
        raise ValueError('unknown generation arm')
    # The bundle preserves text observations, not raw CalendarMeetingContext fields.
    # Keep raw observations in notes rather than guessing identities or invite fields.
    calendar = CalendarMeetingContext(
        calendar_event_id='fixture-calendar',
        title='',
        start_time=datetime.fromisoformat(bundle.started_at),
        duration_minutes=0,
        calendar_source='fixture',
        participants=[MeetingParticipant(name=item.actor) for item in bundle.roster if item.actor],
        notes='\n'.join(item.content for item in [*bundle.calendar, *bundle.roster]) or None,
    )
    roster = normalize_meeting_participants(calendar, 'unknown', None, (), ())
    clusters = {}
    lines, speaker_map, segment_ids = [], {}, []
    for index, item in enumerate(bundle.transcript_segments):
        key = item.diarization_key or (item.actor if item.actor else f'unresolved:{index}')
        cluster = clusters.setdefault(key, len(clusters))
        speaker_map[cluster] = item.actor
        segment_id = item.source_ref or item.id
        segment_ids.append(segment_id)
        lines.append(f'[{segment_id} {cluster}] {item.content}')
    prefix = build_conversation_prompt_prefix(
        conversation_id=episode.id,
        transcript='\n\n'.join(lines),
        started_at=datetime.fromisoformat(bundle.started_at),
        timezone_name='UTC',
        language_code='en',
        calendar_context=calendar,
        roster=roster,
        speaker_map=speaker_map,
        transcript_segment_ids=segment_ids,
    )
    rows = [{'appName': '', 'windowTitle': '', 'ocrText': item.content} for item in bundle.screen_ocr]
    rows += [
        {'appName': 'Messages', 'windowTitle': 'Visible message thread', 'ocrText': item.content}
        for item in bundle.messages
    ]
    pack = MeetingContextPack(
        prior_meetings=tuple(
            PriorMeetingNote(
                title='Earlier conversation',
                date_label=item.time or 'Unknown date',
                gist=item.content[:300],
                source_id=item.source_ref,
            )
            for item in bundle.prior_conversations[:3]
        ),
        screen_text=digest_screen_rows(rows[:80], MAX_SCREEN_CHARACTERS),
        screen_moments=tuple(item.content for item in bundle.screen_moments[:7]),
    )
    existing_context = '\n'.join(f'- ID {item.source_ref or item.id}: {item.content}' for item in bundle.open_tasks)
    volatile = rich_volatile_instructions(
        **common,
        legacy_volatile=conversation_notes_volatile_instructions,
        conversation_context=prefix.context,
        meeting_context=render_meeting_context_pack(pack),
        existing_context=existing_context or 'None supplied.',
    )
    return BASELINE_PROMPT, {'instructions': volatile}
