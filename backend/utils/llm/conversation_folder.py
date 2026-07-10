"""Conversation folder assignment LLM route.

Folder assignment has route-specific safety semantics: returned folder IDs must
exist in the user's folder list, and low-confidence assignments fall back to the
user's default folder. Keeping that logic in one small module makes it safe to
change providers/models through ``get_llm('conv_folder')`` without duplicating
validation in each experiment or callsite.
"""

import logging
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple, cast

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from .clients import get_llm

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

        # Format: folder_id | "Folder Name" → Description
        if description:
            line = f'- {folder_id} | "{name}" → {description}'
        else:
            line = f'- {folder_id} | "{name}"'

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


def validate_folder_assignment(
    response: FolderAssignment,
    user_folders: Sequence[FolderRecord],
    default_folder_id: Optional[str],
    confidence_threshold: float = 0.7,
) -> FolderAssignmentResult:
    """Apply route-specific safety checks to a parsed folder assignment."""

    valid_folder_ids = {_optional_str(f.get('id')) for f in user_folders}
    if response.folder_id not in valid_folder_ids:
        return FolderAssignmentResult(
            folder_id=default_folder_id,
            confidence=0.3,
            reasoning="Invalid folder ID returned, using default",
            validation_status='invalid_folder_id_defaulted',
        )

    if response.confidence < confidence_threshold and default_folder_id:
        return FolderAssignmentResult(
            folder_id=default_folder_id,
            confidence=response.confidence,
            reasoning=f"Low confidence ({response.confidence:.2f}), using default folder",
            validation_status='low_confidence_defaulted',
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
) -> Tuple[Optional[str], float, str]:
    """
    Use AI to assign a conversation to the most appropriate folder.

    Args:
        title: The conversation title
        overview: The conversation overview/summary
        category: The conversation category
        user_folders: List of user's folders with id, name, description, is_default

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
- Only assign to a non-default folder if the theme clearly matches
- When in doubt, use the DEFAULT folder

Provide:
- folder_id: The best matching folder ID from the list above
- confidence: Match strength (0.0-1.0). Use 0.9+ only for clear thematic matches, below 0.7 means use DEFAULT
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
        result = validate_folder_assignment(response, user_folders, default_folder_id)
        return result.folder_id, result.confidence, result.reasoning

    except Exception as e:
        logger.error(f'Error assigning conversation to folder: {e}')
        return default_folder_id, 0.0, f"Error: {str(e)}"
