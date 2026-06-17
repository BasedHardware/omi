import logging
from typing import List, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from models.v17_memory_contracts import WorkingMemoryObservation, deterministic_contract_id

try:
    from .clients import get_llm

    _CLIENT_IMPORT_ERROR = None
except Exception as exc:
    # Benchmark/product-module tests may run without Firestore ADC or optional provider deps.
    # Keep the L1 prompt/parser/validation importable so callers can inject an equivalent llm.
    get_llm = None
    _CLIENT_IMPORT_ERROR = exc

logger = logging.getLogger(__name__)


class WorkingMemoryObservations(BaseModel):
    observations: List[WorkingMemoryObservation] = Field(default_factory=list)


working_memory_observation_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
You are the Layer 1 working-memory extractor for Omi.

Your job is broad, source-backed short-term memory capture. Extract observations that may be useful to an agent or to Layer 2 durable synthesis later. Do not decide long-term durability, do not deduplicate against existing memories, and do not create durable memory IDs.

Required behavior:
- Preserve source evidence with exact quotes and source refs.
- Use status="working" for ordinary short-term observations.
- Use status="context_only" for local context that is useful but not a user/profile fact.
- Use status="review" for ambiguous subject, weak evidence, or potentially risky observations.
- Use status="hidden" or risk_flags including "secret" for credentials/secrets/security-sensitive material.
- Keep unidentified non-primary speakers out of durable/user facts: mark them context_only or review unless the user explicitly identifies them.
- Do not suppress broad topics; Layer 2 handles merge/update/reject.
- Do not output durable memory IDs, active memory status, supersession, merge decisions, or patch decisions.

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


def _with_deterministic_observation_ids(
    observations: List[WorkingMemoryObservation], uid: str, source_id: str
) -> List[WorkingMemoryObservation]:
    normalized = []
    for index, observation in enumerate(observations):
        if observation.observation_id:
            normalized.append(observation)
            continue
        payload = {
            "uid": uid,
            "source_id": source_id,
            "index": index,
            "content": observation.content,
            "evidence_ids": observation.evidence_ids,
        }
        normalized.append(
            observation.model_copy(update={"observation_id": deterministic_contract_id("l1-observation", payload)})
        )
    return normalized


def extract_working_memory_observations_from_text(
    *,
    uid: str,
    source_id: str,
    source_type: str,
    text: str,
    user_name: Optional[str] = None,
    language_instruction: str = "",
    llm=None,
) -> List[WorkingMemoryObservation]:
    stripped_text = text.strip() if text else ""
    low_text_is_security_relevant = source_type in {"screenshot_ocr", "ocr_screenshot_text", "desktop_rewind"}
    if not stripped_text or (len(stripped_text) < 25 and not low_text_is_security_relevant):
        return []

    parser = PydanticOutputParser(pydantic_object=WorkingMemoryObservations)
    messages = working_memory_observation_prompt.format_messages(
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
        logger.error("Error extracting V17 working-memory observations: missing_llm_client")
        return []

    try:
        response = model.invoke(messages)
        parsed = parser.parse(_content_from_response(response))
        return _with_deterministic_observation_ids(parsed.observations, uid, source_id)
    except Exception as exc:
        logger.error("Error extracting V17 working-memory observations: %s", type(exc).__name__)
        return []
