from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotesFrameImage:
    """One approved call screenshot, ready to attach to the notes call as an image part."""

    frame_id: str
    offset_label: str
    data_url: str


_RICH_NOTE_BODY_OPENING = (
    '- Open each section with a one-line takeaway bullet. Put supporting details in short, specific '
    'bullets (aim for at most 25 words each); use nested `  - ` sub-bullets for detail instead of '
    '40–60-word compound paragraphs. Preserve every supported commitment and concrete detail: '
    'coverage beats brevity.'
)
_RICH_SELECT_THREADS = (
    '- Select the main meaningful threads, including social experiences, problems, reasons, proposals, '
    'decisions, and unresolved questions. Put worthwhile tangents (tools, products, links, '
    'recommendations, memorable personal asides) in one side_notes section rather than dropping them. '
    'Still omit filler, logistics chatter, repetition, and unclear fragments. Understandable '
    'multilingual content is not noise.'
)
MEETING_PEOPLE_HEADING = 'MEETING TITLE AND PEOPLE'
MEETING_TITLE_RULE = '- The note title must be at most 70 characters. Never use a raw window title, meeting code, app name, or unread counter as the note title, and never put the account owner\'s name in it (the note is theirs). When a human counterpart is identified, lead with their name (for example, "Intro with Ash Kalb (via Boardy): founding engineer"); otherwise lead with the topic. Do not invent names.'
PERSON_NAME_RULE = "- A person's name may come only from the roster's display names, from the transcript (self-introductions, being addressed by name), or from background screen evidence that shows it in the call's participant list, on a video tile, in SCREEN MOMENTS, in an attached call screenshot, or in a profile or document opened during the call. Never turn an email address or handle into a name, and never assume a nameless roster email belongs to a name you saw elsewhere unless the conversation makes that link clear."
PERSON_REFERENCE_RULE = '- Refer to non-owner humans by name when known. Otherwise use a role grounded in this conversation (for example, "the candidate"), never a speaker key. Never infer anyone\'s gender from a name or voice: use their name or "they" unless the conversation itself states their pronouns.'
PERSON_ORGANIZATION_RULE = "- Set a participant's organization when the conversation, a non-freemail email domain, or background screen text (for example, a profile headline opened during the call) states it, and use that spelling in the note. Treat an AI agent as a separate speaker: attribute introductions, facilitation, and stepping out to that agent when the content supports it; never merge its words into a human's."
PARTICIPANT_RULE = '- Fill participants from the roster and transcript evidence. Exclude the account owner. Keep a roster-only human nameless when only an email is known; never guess their name. Set role to at most eight words grounded in this conversation.'
MEETING_TYPE_RULE = ' Set meeting_type only to interview, intro, sales, customer, one_on_one, team_sync, planning, demo, social, or other.'
COUNTERPART_TASK_RULE = '- A request the account owner makes of another participant that they accept (for example, "keep an eye out for introductions") is an action item owned by that participant.'
TASK_OWNER_RULE = '- When the transcript makes an action item\'s owner clear, set owner_name to that participant\'s name, including the account owner\'s name for their own commitments. If the owner is clear but has no known name, set owner_name to their short role from this conversation (for example, "Candidate").'
SIDE_NOTES_HEADING = 'SIDE NOTES AND BACKGROUND'
SIDE_NOTES_RULE = '- At most one section has kind side_notes: place it last with heading Side notes and 1–4 short bullets on worthwhile tangents. Keep main threads in main sections; do not put prior-meeting links or goals into sections.'
BACKGROUND_RULE = '- BACKGROUND CONTEXT (not part of this conversation) may help identify people, spell names/products/companies, and connect prior commitments; it was NOT said in this meeting. Never state a background fact as something said here. Do not summarize screen text that was not discussed: use it only to spell names/products correctly and identify what was shown.'
SCREEN_RULE = '- SCREEN MOMENTS and any attached call screenshots show what was on screen during this call (who was on the video tiles, what document or slide was shared). Use them to name participants and to say what was shown when the conversation refers to it ("this slide", "as you can see"); never present on-screen text as something someone said.'
INSIGHTS_RULE = '- Prior-meeting links and goal relevance go ONLY in insights, never in sections or overview. Insights are private: at most four, each at most 30 words, each grounded in supplied background context. An insight must be specific and useful to act on (an open item from a prior meeting with this person, a concrete link between what was said and a named goal or fact); never restate a goal generically or say a topic "aligns with" a goal. Return [] when nothing specific qualifies or no background context exists.'

_RICH_MEETING_RULES = '\n'.join(
    (
        MEETING_PEOPLE_HEADING,
        MEETING_TITLE_RULE,
        PERSON_NAME_RULE,
        PERSON_REFERENCE_RULE,
        PERSON_ORGANIZATION_RULE,
        PARTICIPANT_RULE + MEETING_TYPE_RULE,
        COUNTERPART_TASK_RULE,
        TASK_OWNER_RULE,
        SIDE_NOTES_HEADING,
        SIDE_NOTES_RULE,
        BACKGROUND_RULE,
        SCREEN_RULE,
        INSIGHTS_RULE,
    )
)

RICH_PERSON_RULES = '\n'.join(
    (
        PERSON_NAME_RULE,
        PERSON_REFERENCE_RULE,
        PERSON_ORGANIZATION_RULE,
        PARTICIPANT_RULE,
        COUNTERPART_TASK_RULE,
        TASK_OWNER_RULE,
    )
)


def rich_static_instructions(format_instructions: str, legacy_static: Callable[..., str]) -> str:
    return legacy_static(
        format_instructions,
        note_body_opening=_RICH_NOTE_BODY_OPENING,
        select_threads=_RICH_SELECT_THREADS,
        extra_rules=_RICH_MEETING_RULES + '\n\n',
    )


def screen_frames_message(frames: Sequence[NotesFrameImage], *, episode_mode: bool = False) -> dict[str, Any]:
    """The approved call screenshots as one user message: a caption line, then image parts.

    Every frame must reach the provider as an ``image_url`` part; a gateway or
    translator that drops image parts would silently produce a blind call, so
    tests pin the parts through the request payload.
    """
    labels = ', '.join(frame.offset_label for frame in frames)
    content: list[dict[str, Any]] = [
        {
            'type': 'text',
            'text': (
                f'CALL SCREENSHOTS ({len(frames)} approved frames, in capture order at {labels} from the start '
                'of the recording). They are evidence of what was on screen, not of what was said.'
            ),
        }
    ]
    for frame in frames:
        if episode_mode:
            content.append({'type': 'text', 'text': f'Evidence screen_frame:{frame.frame_id} at {frame.offset_label}'})
        content.append({'type': 'image_url', 'image_url': {'url': frame.data_url}})
    # A role/content dict: LangChain chat models accept it as a user message, and
    # this module stays free of client imports.
    return {'role': 'user', 'content': content}
