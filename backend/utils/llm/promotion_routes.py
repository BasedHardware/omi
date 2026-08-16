import logging
import re
from collections.abc import Callable, Sequence
from typing import Any, Dict, Optional, Protocol, cast

from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, ValidationError

from models.memory_contracts import PromotionRoute
from utils.memory_ingestion.ids import canonical_json

GetLlm = Callable[[str], object]


class LlmInvoker(Protocol):
    def invoke(self, messages: Sequence[BaseMessage]) -> object: ...


try:
    from .clients import get_llm as _imported_get_llm

    get_llm: GetLlm | None = _imported_get_llm
    _client_import_error: Exception | None = None
except Exception as exc:
    # Benchmark/product-module tests may run without Firestore ADC or optional provider deps.
    get_llm = None
    _client_import_error = exc

CLIENT_IMPORT_ERROR = _client_import_error
_CLIENT_IMPORT_ERROR = CLIENT_IMPORT_ERROR

logger = logging.getLogger(__name__)

_QUOTE_WRAPPER_RE = re.compile(r"^\s*User\s+(said|mentioned|stated|talked about|noted)\s+['\"]", re.IGNORECASE)
QUOTE_WRAPPER_RE = _QUOTE_WRAPPER_RE


class PromotionRouteResponse(BaseModel):
    route: PromotionRoute = Field(...)


# Backward-compatible alias for callers/tests that still use the L2 name.
L2MemoryRouteResponse = PromotionRouteResponse


promotion_route_prompt = cast(Any, ChatPromptTemplate).from_messages(
    cast(
        Any,
        [
            (
                "system",
                """
You are Omi Layer 2 memory routing.

Your only job is to classify one L2 evidence packet as exactly one route:
- durable: a standalone, future-useful long-term memory about the primary user, their project/work, explicit plan, preference, relationship context, constraint, or durable intent.
- review: potentially useful but uncertain, ambiguous, or needing human/model review.
- discard: not durable memory: ephemeral chatter, UI/OCR context, third-party/unknown speaker, duplicate, unsupported/noisy, missing user tie, or not future-useful.
- hidden: secret/security-sensitive material.

Do NOT output patch operations, lifecycle states, IDs, predicates, graph fields, or ledger details.
Do NOT output `working`, `active`, `context_only`, `add`, `merge`, `update`, or `skip_duplicate`.

Rules:
- durable/review require a concise memory_text and at least one exact source quote copied from the packet.
- discard/hidden require drop_reason.
- hidden requires drop_reason=secret_or_security_sensitive.
- Reject quote wrappers like "User said ..."; rewrite into a durable abstraction or discard/review.
- UI/OCR state, assistant filler, task-switching chatter, and non-primary-speaker/unknown-subject content should usually be discard unless there is a strong explicit user tie.
- Existing/custom search results are context only and are not primary evidence for new claims.

Return JSON matching:
{format_instructions}
""".strip(),
            ),
            (
                "human",
                """
Observed head commit id: {observed_head_commit_id}

L2 evidence packet:
{packet_json}

Custom search replay artifact:
{custom_search_json}
""".strip(),
            ),
        ],
    )
)

# Backward-compatible alias for callers/tests that still use the L2 name.
l2_memory_route_prompt = promotion_route_prompt


def _content_from_response(response: object) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, list):
        return "\n".join(str(part) for part in cast(list[object], content))
    return str(content)


content_from_response = _content_from_response


_canonical_json = canonical_json


def _is_quote_wrapper(memory_text: Optional[str]) -> bool:
    if not memory_text:
        return False
    return bool(_QUOTE_WRAPPER_RE.match(memory_text))


is_quote_wrapper = _is_quote_wrapper


def classify_l2_memory_route(
    *,
    packet: Dict[str, Any],
    custom_search_artifact: Dict[str, Any],
    observed_head_commit_id: Optional[str],
    llm: LlmInvoker | None = None,
) -> Optional[PromotionRoute]:
    parser = PydanticOutputParser(pydantic_object=PromotionRouteResponse)
    messages = promotion_route_prompt.format_messages(
        observed_head_commit_id=observed_head_commit_id or "unknown",
        packet_json=_canonical_json(packet),
        custom_search_json=_canonical_json(custom_search_artifact),
        format_instructions=parser.get_format_instructions(),
    )
    if llm is not None:
        model: LlmInvoker = llm
    elif get_llm is not None:
        model = cast(LlmInvoker, get_llm("memory_l2"))
    else:
        logger.error("Error classifying memory L2 memory route: missing_llm_client")
        return None

    try:
        response = model.invoke(messages)
        parsed = parser.parse(_content_from_response(response))
        route = parsed.route
        if _is_quote_wrapper(route.memory_text):
            return PromotionRoute(
                route="review",
                memory_text=route.memory_text,
                evidence_quotes=route.evidence_quotes,
                confidence="low",
                reason="Quote-wrapper memory text requires review/rewrite before durable export.",
            )
        return route
    except (ValidationError, Exception) as exc:
        logger.error("Error classifying memory L2 memory route: %s", type(exc).__name__)
        return None
