"""Conversation folder assignment LLM route.

Folder assignment has route-specific safety semantics: returned folder IDs must
exist in the user's folder list, and low-confidence assignments fall back to the
user's default folder. Keeping that logic in one small module makes it safe to
change providers/models through ``get_llm('conv_folder')`` without duplicating
validation in each experiment or callsite.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, Tuple, cast

try:
    from langchain_core.exceptions import OutputParserException
except ImportError:  # bare-stub langchain_core in some test environments

    class OutputParserException(Exception):
        pass


from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, ValidationError, Field

from .clients import get_llm

try:
    from langchain_core.output_parsers.json import parse_partial_json
except ImportError:  # bare-stub langchain_core in some test environments

    def parse_partial_json(text: str, **_kwargs):
        import json as _json

        return _json.loads(text)


logger = logging.getLogger(__name__)

FolderRecord = Mapping[str, object]


class FolderAssignment(BaseModel):
    """Model for AI folder assignment response."""

    folder_id: str = Field(description="The ID of the best matching folder for this conversation")
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Confidence score for folder assignment (0.0 to 1.0)"
    )
    reasoning: str = Field(default="", description="Brief explanation of why this folder was chosen")


@dataclass(frozen=True)
class FolderAssignmentResult:
    folder_id: Optional[str]
    confidence: float
    reasoning: str
    validation_status: str


def _optional_str(value: object) -> Optional[str]:
    if isinstance(value, str):
        return value
    return None


def _str_or_empty(value: object) -> str:
    return value if isinstance(value, str) else ""


def _bool_or_false(value: object) -> bool:
    return value if isinstance(value, bool) else False


def build_folders_context(folders: Sequence[FolderRecord]) -> str:
    """
    Build context string for LLM folder assignment using natural language descriptions.

    Each folder's description explains what conversations belong in it,
    allowing the AI to match based on intent rather than keywords.
    """
    if not folders:
        return "No folders available. Use default assignment."

    lines: list[str] = []
    for folder in folders:
        folder_id = _str_or_empty(folder.get('id'))
        name = _str_or_empty(folder.get('name'))
        description = _str_or_empty(folder.get('description'))
        is_default = _bool_or_false(folder.get('is_default'))
        category_mapping = folder.get('category_mapping')

        # Format: folder_id | "Folder Name" → Description
        if description:
            line = f'- {folder_id} | "{name}" → {description}'
        else:
            line = f'- {folder_id} | "{name}"'

        if category_mapping:
            line += f" [home for {category_mapping} conversations]"

        if is_default:
            line += " (DEFAULT - use when no other folder matches)"

        lines.append(line)

    return "\n".join(lines)


def build_conversation_folder_context(title: str, overview: str, category: str) -> str:
    return f"""
Title: {title}
Category: {category}
Overview: {overview}
""".strip()


def get_default_folder_id(user_folders: Sequence[FolderRecord]) -> Optional[str]:
    default_folder = next((f for f in user_folders if _bool_or_false(f.get('is_default'))), None)
    return _optional_str(default_folder.get('id')) if default_folder else None


_JSON_SPAN_RE = re.compile(r'\{.*\}', re.DOTALL)


def _top_level_json_spans(text: str) -> List[str]:
    """Every top-level ``{...}`` span in the text, in order.

    String- and escape-aware, so a ``}`` inside a JSON string does not close a
    span. The last element may be unterminated (a truncated completion) — the
    caller decides whether to attempt truncation repair on it.
    """
    spans: List[str] = []
    depth = 0
    start: Optional[int] = None
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == '{':
            if depth == 0:
                start = index
            depth += 1
        elif char == '}':
            if depth:
                depth -= 1
                if depth == 0 and start is not None:
                    spans.append(text[start : index + 1])
                    start = None
    if depth > 0 and start is not None:
        spans.append(text[start:])
    return spans


def _salvage_raw_completion(exc: BaseException) -> str:
    """Recover the model's completion text from a parser failure.

    ``PydanticOutputParser`` reports both of its failure modes (json that did not
    ``json.loads``, and json that failed schema validation) as an
    ``OutputParserException`` that still carries the full completion in
    ``llm_output``. Older chains raise bare ``json.JSONDecodeError`` without it,
    where ``str(exc)`` is the only carrier. Either way the completion — which
    usually contains a well-formed assignment — must reach the salvage attempt
    instead of being discarded with the parser's verdict.
    """
    carried = getattr(exc, 'llm_output', None)
    if isinstance(carried, str) and carried.strip():
        return carried
    return str(exc)


def _salvage_candidate_payloads(completion: str) -> Any:
    """Best-effort decode of a completion the strict parser refused.

    Decodes each top-level ``{...}`` span in order (a prose lead-in, markdown
    fencing, or surrounding sentences are all skipped), then the raw text. A
    final unterminated span — a completion cut off mid-field — is repaired
    through langchain's ``parse_partial_json``, which closes open strings and
    braces. Raises the last decode error when nothing decodes, so the caller
    can distinguish salvageable completions from genuinely unusable ones.
    """
    last_error: Exception = ValueError('no candidate payloads')
    spans = _top_level_json_spans(completion)
    for span in spans:
        if not span.endswith('}'):
            continue
        try:
            return json.loads(span)
        except json.JSONDecodeError as decode_error:
            last_error = decode_error
    try:
        return json.loads(completion)
    except json.JSONDecodeError as decode_error:
        last_error = decode_error
    # Truncation repair: parse_partial_json closes open strings and braces.
    if spans and not spans[-1].endswith('}'):
        try:
            return parse_partial_json(spans[-1])
        except Exception as partial_error:
            last_error = partial_error
    raise last_error


def _assignment_from_salvaged_payload(payload: Any) -> Optional[FolderAssignment]:
    """Validate a salvage candidate against the same schema the parser enforces.

    Applies ``FolderAssignment`` exactly as the parser would: unusable payloads
    raise ``ValidationError``, and validated output flows through the same
    type/coercion rules (a string confidence of "0.72" parses where the schema
    says float). ``parse_partial_json`` candidates can omit fields the schema
    defaults, which is the same contract an absent key already has.
    """
    if not isinstance(payload, Mapping):
        return None
    try:
        return FolderAssignment.model_validate(dict(payload))
    except ValidationError:
        return None


def _best_assignment_from_salvage(completion: str) -> Optional[FolderAssignment]:
    """Validate salvage candidates until one matches the schema.

    A decode can return a payload that is valid JSON but not an assignment — a
    prose snippet's ``{}``, or the first of two objects — so each decode result
    goes through the schema before it is accepted; the first schema-matching
    payload wins. The fallback candidates after the primary decode are the
    remaining spans, then partial-JSON repair over the raw completion.
    """
    candidates: List[Any] = []
    try:
        candidates.append(_salvage_candidate_payloads(completion))
    except Exception:
        pass
    for span in _top_level_json_spans(completion):
        if not span.endswith('}'):
            continue
        try:
            candidates.append(json.loads(span))
        except json.JSONDecodeError:
            continue
    brace = completion.find('{')
    if brace != -1:
        try:
            candidates.append(parse_partial_json(completion[brace:]))
        except Exception:
            pass
    # Prose braces: a '{' inside surrounding text can poison the span start, so
    # also repair from each later '{' the completion contains.
    start = completion.find('{', brace + 1) if brace != -1 else completion.find('{')
    while start != -1:
        try:
            candidates.append(parse_partial_json(completion[start:]))
        except Exception:
            pass
        start = completion.find('{', start + 1)
    for payload in candidates:
        assignment = _assignment_from_salvaged_payload(payload)
        if assignment is not None:
            return assignment
    return None


def _salvage_folder_assignment(exc: BaseException) -> Optional[FolderAssignment]:
    """One salvage pass over a completion the strict parser rejected.

    The completion was already paid for; the parser's refusal is a verdict about
    wrapper text (a lead-in sentence, markdown fencing, truncation at the token
    limit), not about the assignment inside it. Extract the recoverable payload
    and validate it against the production schema; return None only when the
    completion genuinely carries no usable assignment.
    """
    completion = _salvage_raw_completion(exc)
    return _best_assignment_from_salvage(completion)


def validate_folder_assignment(
    response: FolderAssignment,
    user_folders: Sequence[FolderRecord],
    default_folder_id: Optional[str],
    category_folder_id: Optional[str] = None,
    confidence_threshold: float = 0.7,
) -> FolderAssignmentResult:
    """Apply route-specific safety checks to a parsed folder assignment.

    When the model returns an invalid folder or is below the confidence threshold, prefer
    the category-aligned folder (the system folder that owns the conversation's category)
    over the catch-all default, so an uncertain "finance" conversation still lands in Work
    rather than the default folder (issue #4043). Falls back to the default when there is
    no category-aligned folder.
    """

    valid_folder_ids = {_optional_str(f.get('id')) for f in user_folders}
    category_folder_id = category_folder_id if category_folder_id in valid_folder_ids else None
    fallback_id = category_folder_id or default_folder_id
    via_category = fallback_id is not None and fallback_id == category_folder_id

    if response.folder_id not in valid_folder_ids:
        return FolderAssignmentResult(
            folder_id=fallback_id,
            confidence=0.3,
            reasoning=(
                "Invalid folder ID returned, using category-aligned folder"
                if via_category
                else "Invalid folder ID returned, using default"
            ),
            validation_status='invalid_folder_id_category_matched' if via_category else 'invalid_folder_id_defaulted',
        )

    # default_folder_id/fallback_id may be None (users created after the 'Other'
    # system folder was removed have no default) — a low-confidence guess must
    # still fall back, leaving the conversation unfiled rather than misfiled.
    if response.confidence < confidence_threshold:
        return FolderAssignmentResult(
            folder_id=fallback_id,
            confidence=response.confidence,
            reasoning=(
                f"Low confidence ({response.confidence:.2f}), using category-aligned folder"
                if via_category
                else f"Low confidence ({response.confidence:.2f}), using default folder"
            ),
            validation_status='low_confidence_category_matched' if via_category else 'low_confidence_defaulted',
        )

    return FolderAssignmentResult(
        folder_id=response.folder_id,
        confidence=response.confidence,
        reasoning=response.reasoning,
        validation_status='accepted',
    )


def assign_conversation_to_folder(
    title: str,
    overview: str,
    category: str,
    user_folders: Sequence[FolderRecord],
    category_folder_id: Optional[str] = None,
) -> Tuple[Optional[str], float, str]:
    """
    Use AI to assign a conversation to the most appropriate folder.

    Args:
        title: The conversation title
        overview: The conversation overview/summary
        category: The conversation category
        user_folders: List of user's folders with id, name, description, is_default
        category_folder_id: The system folder that owns this conversation's category
            (see database.folders.resolve_category_folder_id). Used as the preferred
            fallback over the default folder when the model is unsure (issue #4043).

    Returns:
        Tuple of (folder_id, confidence, reasoning)
        Returns (None, 0.0, reason) if assignment fails or confidence is too low
    """
    if not user_folders:
        return None, 0.0, "No folders available"

    folders_context = build_folders_context(user_folders)
    default_folder_id = get_default_folder_id(user_folders)
    conversation_context = build_conversation_folder_context(title, overview, category)

    prompt_text = '''You are a folder assignment system. Match the conversation to the folder that best represents its overall theme.

FOLDERS:
{folders_context}

CONVERSATION:
{conversation_context}

INSTRUCTIONS:
- Match based on the dominant theme of the conversation (what it's fundamentally about)
- The folder should feel like a natural home for this conversation
- Folders annotated [home for X conversations] are the standard home for that category; when the conversation's Category matches one, prefer it unless a custom folder's description is a clearly better fit
- Only assign to a non-default folder if the theme clearly matches
- When no folder clearly matches, prefer the folder for the conversation's category if one is listed above, otherwise use the DEFAULT folder

Provide:
- folder_id: The best matching folder ID from the list above
- confidence: Match strength (0.0-1.0). Use 0.9+ only for clear thematic matches; below 0.7 routes to the conversation's category folder if one is listed, otherwise the DEFAULT folder
- reasoning: One sentence explaining the match

{format_instructions}'''

    folder_parser = PydanticOutputParser(pydantic_object=FolderAssignment)
    prompt = cast(Any, ChatPromptTemplate).from_messages([('system', prompt_text)])
    chain = prompt | get_llm('conv_folder') | folder_parser

    try:
        response = cast(
            FolderAssignment,
            chain.invoke(
                {
                    'folders_context': folders_context,
                    'conversation_context': conversation_context,
                    'format_instructions': folder_parser.get_format_instructions(),
                }
            ),
        )
        result = validate_folder_assignment(
            response, user_folders, default_folder_id, category_folder_id=category_folder_id
        )
        return result.folder_id, result.confidence, result.reasoning

    except OutputParserException as e:
        # The completion was already paid for. A strict parser refusal is most
        # often wrapper damage — a lead-in sentence before the JSON, markdown
        # fencing, or truncation at the token limit — not a missing assignment.
        # Prod pusher 2026-10 logged ~60 of these per 30 minutes as
        # ``Error assigning conversation to folder: Invalid json output:
        # {"folder_id": ..., "confidence": 0.72, ...}`` where the logged payload
        # was itself well-formed: every one of those was one wasted paid call
        # plus a spurious ERROR per conversation. Salvage once, validate against
        # the same schema the parser enforces, and only then fall back — exactly
        # like the out-of-vocabulary literal precedent (FC evidence PR #11871).
        salvaged = _salvage_folder_assignment(e)
        if salvaged is not None:
            logger.warning(
                'Recovered folder assignment from rejected completion (schema-validated after parse failure)'
            )
            result = validate_folder_assignment(
                salvaged, user_folders, default_folder_id, category_folder_id=category_folder_id
            )
            return result.folder_id, result.confidence, result.reasoning
        logger.error(f'Error assigning conversation to folder: {e}')
        return category_folder_id or default_folder_id, 0.0, f"Error: {str(e)}"
    except Exception as e:
        logger.error(f'Error assigning conversation to folder: {e}')
        return category_folder_id or default_folder_id, 0.0, f"Error: {str(e)}"
