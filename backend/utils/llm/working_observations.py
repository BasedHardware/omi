import logging
from collections.abc import Callable, Sequence
from typing import Any, List, Optional, Protocol, cast

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from database.memory_non_active_routes import (
    NonActiveRoute,
    NonActiveRouteOutcome,
    persist_non_active_route_outcome,
)
from models.memory_contracts import WorkingObservationArchiveItem, deterministic_contract_id

GetLlm = Callable[[str], object]
ChatMessage = tuple[str, str]


class LlmInvoker(Protocol):
    def invoke(self, messages: Sequence[ChatMessage]) -> object: ...


try:
    from .clients import get_llm as _imported_get_llm

    get_llm: GetLlm | None = _imported_get_llm
    _client_import_error: Exception | None = None
except Exception as exc:
    get_llm = None
    _client_import_error = exc

CLIENT_IMPORT_ERROR = _client_import_error
_CLIENT_IMPORT_ERROR = CLIENT_IMPORT_ERROR

logger = logging.getLogger(__name__)


def _empty_archive_items() -> list[WorkingObservationArchiveItem]:
    return []


class WorkingObservationBatch(BaseModel):
    items: List[WorkingObservationArchiveItem] = Field(default_factory=_empty_archive_items)


# Backward-compatible alias for callers/tests that still use the L1 name.
L1MemoryArchiveItems = WorkingObservationBatch


def _source_type_instructions(source_type: str, user_name: str) -> str:
    """Return source-type-specific guidance for the L1 archive extractor."""
    type_hint = (source_type or "unknown").lower()

    if "voice" in type_hint or "transcript" in type_hint:
        return (
            f"This is a voice transcript. Multiple people may be speaking, and speaker labels "
            f"such as speaker_0/speaker_1 are source-local, not stable identities. "
            f"Extract memorable facts, decisions, plans, names, relationships, and project context, "
            f"but do not assume every speaker is {user_name}. "
            f"Treat a statement as about {user_name} only when source role, first-person context, "
            f"or surrounding evidence supports that attribution. "
            f"For unidentified non-primary speakers, preserve the source-local speaker label and archive "
            f"the item as about that speaker or their relationship/context, not as a user fact. "
            f"Ignore background noise, transcription errors, and long passages where nothing memorable happens."
        )
    elif "ocr" in type_hint or "screenshot" in type_hint or "desktop" in type_hint:
        return (
            f"This is text from a screenshot or screen capture on {user_name}'s computer. "
            f"It might show a chat window, code editor, document, email, or app interface. "
            f"Extract visible facts: what they're working on, who they're talking to, "
            f"what's on their screen that reveals preferences or context. "
            f"Ignore transient UI elements (scroll position, loading spinners) unless "
            f"they reveal something meaningful."
        )
    elif "chat" in type_hint or "message" in type_hint or "conversation" in type_hint:
        return (
            f"This is a conversation between {user_name} and an AI assistant (and possibly others). "
            f"Extract what {user_name} said, decided, or revealed about themselves or their life. "
            f"Ignore generic assistant messages, praise, nudges, and conversational filler. "
            f"Only extract assistant content when it confirms something {user_name} stated."
        )
    else:
        return f"This is a {source_type} from {user_name}'s digital life. Extract what's worth remembering."


def _build_l1_messages(
    user_name: str,
    source_type: str,
    text: str,
    format_instructions: str,
    language_instruction: str = "",
) -> list[ChatMessage]:
    """Build L1 extraction messages with source-type-aware system prompt."""
    source_context = _source_type_instructions(source_type, user_name)

    system = (
        f"You are looking at something from {user_name}'s life — a conversation, voice transcript,\n"
        f"screenshot, or document on their computer. Extract what they might want to remember later.\n\n"
        f"{source_context}\n\n"
        f"What to extract:\n"
        f"- Facts about {user_name}: their decisions, plans, preferences, constraints, health, finances.\n"
        f"- Facts about people {user_name} cares about: family, partner, friends, teammates, coworkers.\n"
        f"- Facts about projects or ongoing endeavors {user_name} is invested in.\n"
        f"- Facts about recurring places, pets, or entities in {user_name}'s life.\n"
        f"- Each item must be grounded in a quote from the source.\n\n"
        f"What NOT to extract:\n"
        f"- AI assistant chatter, nudges, generic praise (\"great job!\", \"you can do it!\")\n"
        f"- Third-party storytelling, movie plots, game narration, article content {user_name}\n"
        f"  didn't engage with.\n"
        f"- Transient UI states (\"page loading\", scroll position) unless revealing a preference.\n\n"
        f"Speaker and attribution rules:\n"
        f"- The primary user is the owner of this memory account, referred to here as {user_name}.\n"
        f"- Do NOT infer that every transcript speaker is the primary user.\n"
        f"- Speaker labels like speaker_0, speaker_1, ent_speaker_0, or human are source/session-local labels.\n"
        f"- Preserve the source-local label in `speaker_label` when present; keep `speaker_scope` as session-local/source-local.\n"
        f"- Use `about` = \"the user\" only for facts clearly about the primary user.\n"
        f"- If an unidentified non-primary speaker says or reveals something, set `about` to a neutral description such as \"unidentified non-primary speaker (speaker_1)\" or to the person's stated name/role if known.\n"
        f"- Facts about family, friends, teammates, projects, or pets are valid, but keep them about that person/entity; do not rewrite them as facts about the user unless the quote supports that.\n"
        f"- Do not extract a user's name from assistant-only generic nudges or name-only mentions.\n\n"
        f"For each item, note who/what it's about in the `about` field:\n"
        f"- \"the user\" or \"{user_name}\" → only when the evidence is clearly about the primary user\n"
        f"- A source-local unidentified speaker → e.g. \"unidentified non-primary speaker (speaker_1)\"\n"
        f"- A person's name or role → e.g. \"Sarah\", \"Mom\", \"Dr. Patel\", \"teammate\"\n"
        f"- A project → e.g. \"Omi project\", \"house renovation\"\n"
        f"- An entity → e.g. \"Milo (cat)\", \"neighborhood coffee shop\"\n"
        f"- If attribution is uncertain, say so in the item text/about field rather than assigning it to the user.\n"
        f"- Use class=\"sensitive\" for credentials, health details, finances, family matters.\n\n"
        f"{language_instruction + chr(10) + chr(10) if language_instruction else ''}"
        f"Return JSON:\n{format_instructions}"
    )

    human = f"Source ({source_type}):\n{text}"

    return [
        ("system", system),
        ("human", human),
    ]


def _content_from_response(response: object) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, list):
        return "\n".join(str(part) for part in cast(list[object], content))
    return str(content)


def _with_deterministic_archive_ids(
    items: List[WorkingObservationArchiveItem], uid: str, source_id: str, source_type: str
) -> List[WorkingObservationArchiveItem]:
    normalized: list[WorkingObservationArchiveItem] = []
    for index, item in enumerate(items):
        updates = {
            "user_id": item.user_id or uid,
            "source_id": item.source_id or source_id,
            "source_type": item.source_type or source_type,
        }
        if not item.archive_id:
            payload = {
                "uid": uid,
                "source_id": source_id,
                "source_type": source_type,
                "index": index,
                "text": item.text,
                "evidence_quotes": item.evidence_quotes,
            }
            updates["archive_id"] = "l1_" + deterministic_contract_id("l1-archive-item", payload)[:20]
        normalized.append(item.model_copy(update=updates))
    return normalized


def extract_l1_memory_archive_items_from_text(
    *,
    uid: str,
    source_id: str,
    source_type: str,
    text: str,
    user_name: Optional[str] = None,
    language_instruction: str = "",
    run_id: Optional[str] = None,
    persist_route_outcomes: bool = True,
    db_client: Any = None,
    llm: LlmInvoker | None = None,
) -> List[WorkingObservationArchiveItem]:
    stripped_text = text.strip() if text else ""
    low_text_is_security_relevant = source_type in {"screenshot_ocr", "ocr_screenshot_text", "desktop_rewind"}
    if not stripped_text or (len(stripped_text) < 25 and not low_text_is_security_relevant):
        return []

    name = user_name or "the user"
    parser = PydanticOutputParser(pydantic_object=WorkingObservationBatch)
    messages = _build_l1_messages(
        name,
        source_type,
        text,
        parser.get_format_instructions(),
        language_instruction=language_instruction,
    )

    if llm is not None:
        model = llm
    elif get_llm is not None:
        model = cast(LlmInvoker, get_llm("memory_l1"))
    else:
        logger.error("Error extracting memory L1 archive items: missing_llm_client")
        return []

    try:
        response = model.invoke(messages)
        parsed = parser.parse(_content_from_response(response))
        items = _with_deterministic_archive_ids(parsed.items, uid, source_id, source_type)
    except Exception as exc:
        logger.error("Error extracting memory L1 archive items: %s", type(exc).__name__)
        return []

    if persist_route_outcomes:
        _persist_l1_archive_route_outcomes(
            uid=uid,
            source_id=source_id,
            source_type=source_type,
            run_id=run_id,
            items=items,
            db_client=db_client,
        )
    return items


def _persist_l1_archive_route_outcomes(
    *,
    uid: str,
    source_id: str,
    source_type: str,
    run_id: Optional[str],
    items: List[WorkingObservationArchiveItem],
    db_client: Any = None,
) -> None:
    for item in items:
        outcome = NonActiveRouteOutcome(
            uid=uid,
            route=NonActiveRoute.archive,
            idempotency_key=f"l1-archive:{source_id}:{item.archive_id}",
            source_ids=[source_id],
            reason="l1_archive_extractor_emitted_archive_item",
            run_id=run_id or f"l1-archive:{source_id}",
            patch_id=item.archive_id,
            audit_metadata={
                "source": "utils.llm.working_memory.extract_l1_memory_archive_items_from_text",
                "source_type": source_type,
                "archive_id": item.archive_id,
                "archive_class": item.archive_class.value,
                "allowed_use": item.allowed_use,
                "normal_search_allowed": item.normal_search_allowed,
                "preserved": True,
                "observable_loss": False,
                "remediation_state": "archive_product_tier",
            },
        )
        if db_client is not None:
            persist_non_active_route_outcome(outcome, db_client=db_client)
        else:
            persist_non_active_route_outcome(outcome)
