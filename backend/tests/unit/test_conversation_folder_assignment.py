"""
Regression coverage for validate_folder_assignment's low-confidence fallback.

Users created after the 'Other' system folder was removed have no folder with
is_default=True, so default_folder_id is None. The old guard
(`confidence < threshold and default_folder_id`) was dead for them: every
low-confidence LLM guess was accepted verbatim and conversations were filed
into whichever folder the model half-liked. Low confidence must fall back to
the default folder — or to None (unfiled), which beats misfiled.
"""

from utils.llm.conversation_folder import FolderAssignment, validate_folder_assignment

FOLDERS = [
    {'id': 'work', 'name': 'Work'},
    {'id': 'personal', 'name': 'Personal'},
]


def test_low_confidence_falls_back_even_without_default_folder():
    result = validate_folder_assignment(
        FolderAssignment(folder_id='work', confidence=0.4),
        FOLDERS,
        default_folder_id=None,
    )

    assert result.validation_status == 'low_confidence_defaulted'
    assert result.folder_id is None


def test_low_confidence_uses_default_folder_when_present():
    result = validate_folder_assignment(
        FolderAssignment(folder_id='work', confidence=0.4),
        FOLDERS,
        default_folder_id='personal',
    )

    assert result.validation_status == 'low_confidence_defaulted'
    assert result.folder_id == 'personal'


def test_confident_assignment_is_accepted():
    result = validate_folder_assignment(
        FolderAssignment(folder_id='work', confidence=0.9),
        FOLDERS,
        default_folder_id=None,
    )

    assert result.validation_status == 'accepted'
    assert result.folder_id == 'work'


def test_omitted_confidence_defaults_low_and_falls_back():
    # The LLM omitting confidence parses as the schema default (0.5) — that is
    # a guess, not a match, and must not be filed as one.
    result = validate_folder_assignment(
        FolderAssignment(folder_id='work'),
        FOLDERS,
        default_folder_id=None,
    )

    assert result.validation_status == 'low_confidence_defaulted'
    assert result.folder_id is None
