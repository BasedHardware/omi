import logging
from typing import List, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from models.v17_memory_contracts import L1MemoryArchiveItem, deterministic_contract_id

try:
    from .clients import get_llm

    _CLIENT_IMPORT_ERROR = None
except Exception as exc:
    # Benchmark/product-module tests may run without Firestore ADC or optional provider deps.
    # Keep the L1 prompt/parser/validation importable so callers can inject an equivalent llm.
    get_llm = None
    _CLIENT_IMPORT_ERROR = exc

logger = logging.getLogger(__name__)


class L1MemoryArchiveItems(BaseModel):
    items: List[L1MemoryArchiveItem] = Field(default_factory=list)


l1_memory_archive_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
You are the Layer 1 archive extractor for Omi.

Your job is broad, Base-Omi-like searchable memory capture. Persist source-backed archive items that may be useful for later agent search or Layer 2 durable synthesis. Do not decide durability, do not deduplicate against existing memories, and do not create durable memory IDs.

Required behavior:
- Extract broadly from the source. No topic denylists.
- Preserve exact source evidence with evidence_quotes and source_refs whenever available.
- Use simple archive classes only: class="general" for normal searchable archive evidence, class="sensitive" for credentials, secrets, security-sensitive, medical/immigration/family/privacy-sensitive, or other high-risk material.
- Do not output L1 lifecycle/routes such as working, working_note, context_only, review, hidden, active, rejected, or discard.
- L1 archive items are not stable profile facts. Layer 2 decides durable/review/discard/hidden promotion later.
- Keep text source-faithful and useful for search. It may be noisy/current/incidental like old Omi memory, but it must be grounded in the source.
- Keep speaker labels source-local when present; do not globalize unidentified speakers.

Return only JSON matching these format instructions:
{format_instructions}
""".strip(),
        ),
        (
            "human",
            """
User name: {user_name}
User id: {uid}
Source id: {source_id}
Source type: {source_type}
Language instruction: {language_instruction}

Source text:
{text}
""".strip(),
        ),
    ]
)


def _content_from_response(response) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, list):
        return "\n".join(str(part) for part in content)
    return str(content)


def _with_deterministic_archive_ids(
    items: List[L1MemoryArchiveItem], uid: str, source_id: str, source_type: str
) -> List[L1MemoryArchiveItem]:
    normalized = []
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
    llm=None,
) -> List[L1MemoryArchiveItem]:
    stripped_text = text.strip() if text else ""
    low_text_is_security_relevant = source_type in {"screenshot_ocr", "ocr_screenshot_text", "desktop_rewind"}
    if not stripped_text or (len(stripped_text) < 25 and not low_text_is_security_relevant):
        return []

    parser = PydanticOutputParser(pydantic_object=L1MemoryArchiveItems)
    messages = l1_memory_archive_prompt.format_messages(
        user_name=user_name or "the user",
        uid=uid,
        source_id=source_id,
        source_type=source_type,
        language_instruction=language_instruction or "Use the source language where needed.",
        text=text,
        format_instructions=parser.get_format_instructions(),
    )
    if llm is not None:
        model = llm
    elif get_llm is not None:
        model = get_llm("memory_l1")
    else:
        logger.error("Error extracting V17 L1 archive items: missing_llm_client")
        return []

    try:
        response = model.invoke(messages)
        parsed = parser.parse(_content_from_response(response))
        return _with_deterministic_archive_ids(parsed.items, uid, source_id, source_type)
    except Exception as exc:
        logger.error("Error extracting V17 L1 archive items: %s", type(exc).__name__)
        return []
