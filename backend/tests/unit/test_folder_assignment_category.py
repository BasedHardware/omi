"""Tests for category-aware folder assignment (issue #4043).

AI folder assignment used to rely purely on fuzzy LLM matching, so an uncertain
conversation was dropped into the catch-all default folder even though the codebase
already had an authoritative ``CATEGORY_TO_FOLDER_MAPPING`` folding every conversation
category onto one of the three system folders. This wires that mapping in: each folder's
category is surfaced to the model, and when the model is unsure or returns an invalid
folder, assignment now falls back to the category-aligned folder instead of the default.

Covers:
1. resolve_category_folder_id maps a category onto the user's system folder.
2. build_folders_context surfaces each folder's category.
3. validate_folder_assignment prefers the category-aligned folder over the default.
4. assign_conversation_to_folder threads the category folder through end to end.
"""

import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _pkg(name):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _load_module_from_file(module_name, file_path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Packages that must exist before the leaf stubs / real modules import.
for _p in ["google", "google.cloud", "database", "models", "langchain_core", "utils", "utils.llm"]:
    _pkg(_p)

# Stubs for database/folders.py imports.
_firestore = _mod("google.cloud.firestore")
sys.modules["google.cloud"].firestore = _firestore
_firestore_v1 = _mod("google.cloud.firestore_v1")
_firestore_v1.FieldFilter = MagicMock()
sys.modules["google.cloud"].firestore_v1 = _firestore_v1
_dbc = _mod("database._client")
_dbc.db = MagicMock()
_ddi = _mod("database.document_ids")
_ddi.system_folder_doc_id = MagicMock()
_mf = _mod("models.folder")
_mf.Folder = MagicMock()

# Stubs for utils/llm/conversation_folder.py imports.
_lop = _mod("langchain_core.output_parsers")
_lop.PydanticOutputParser = MagicMock()
_lpr = _mod("langchain_core.prompts")
_lpr.ChatPromptTemplate = MagicMock()
_clients = _mod("utils.llm.clients")
_clients.get_llm = MagicMock(return_value=MagicMock())

folders_db = _load_module_from_file("database.folders", BACKEND_DIR / "database" / "folders.py")
conv_folder = _load_module_from_file(
    "utils.llm.conversation_folder", BACKEND_DIR / "utils" / "llm" / "conversation_folder.py"
)

# A user with the three system folders plus one custom folder (no category_mapping).
SYSTEM = [
    {'id': 'w', 'name': 'Work', 'category_mapping': 'work', 'description': 'Work stuff'},
    {'id': 'p', 'name': 'Personal', 'category_mapping': 'personal', 'description': 'Personal stuff'},
    {'id': 's', 'name': 'Social', 'category_mapping': 'social', 'description': 'Social stuff'},
    {'id': 'c', 'name': 'Recipes'},
    {'id': 'def', 'name': 'Other', 'is_default': True},
]


class TestResolveCategoryFolderId:
    def test_exact_and_folded_categories_map_to_system_folder(self):
        assert folders_db.resolve_category_folder_id('work', SYSTEM) == 'w'
        assert folders_db.resolve_category_folder_id('finance', SYSTEM) == 'w'  # finance -> work
        assert folders_db.resolve_category_folder_id('health', SYSTEM) == 'p'  # health -> personal
        assert folders_db.resolve_category_folder_id('music', SYSTEM) == 's'  # music -> social

    def test_case_insensitive(self):
        assert folders_db.resolve_category_folder_id('FINANCE', SYSTEM) == 'w'

    def test_unknown_or_empty_category_returns_none(self):
        assert folders_db.resolve_category_folder_id('not_a_category', SYSTEM) is None
        assert folders_db.resolve_category_folder_id('', SYSTEM) is None
        assert folders_db.resolve_category_folder_id(None, SYSTEM) is None

    def test_other_catchall_returns_none_not_personal(self):
        # 'other' (and a missing category, which the caller maps to 'other') is the catch-all,
        # not a meaningful topic. It must NOT fold onto Personal; resolving to None lets an
        # uncertain conversation fall back to the default folder. Regression for #4043.
        assert folders_db.resolve_category_folder_id('other', SYSTEM) is None
        assert folders_db.resolve_category_folder_id('OTHER', SYSTEM) is None

    def test_returns_none_when_user_lacks_that_system_folder(self):
        only_work = [{'id': 'w', 'category_mapping': 'work'}]
        # 'music' folds onto social, which this user does not have.
        assert folders_db.resolve_category_folder_id('music', only_work) is None


class TestBuildFoldersContext:
    def test_surfaces_category_mapping(self):
        ctx = conv_folder.build_folders_context(SYSTEM)
        assert "[home for work conversations]" in ctx
        assert "[home for social conversations]" in ctx

    def test_custom_folder_has_no_category_annotation(self):
        ctx = conv_folder.build_folders_context([{'id': 'c', 'name': 'Recipes'}])
        assert "home for" not in ctx


def _resp(folder_id, confidence):
    return conv_folder.FolderAssignment(folder_id=folder_id, confidence=confidence)


class TestValidateFolderAssignment:
    def test_high_confidence_valid_pick_is_accepted(self):
        r = conv_folder.validate_folder_assignment(_resp('w', 0.95), SYSTEM, 'def', category_folder_id='w')
        assert r.folder_id == 'w' and r.validation_status == 'accepted'

    def test_low_confidence_prefers_category_folder_over_default(self):
        # Model unsure and picked Social, but the category folder is Work -> use Work, not Other.
        r = conv_folder.validate_folder_assignment(_resp('s', 0.3), SYSTEM, 'def', category_folder_id='w')
        assert r.folder_id == 'w' and r.validation_status == 'low_confidence_category_matched'

    def test_low_confidence_without_category_uses_default(self):
        r = conv_folder.validate_folder_assignment(_resp('s', 0.3), SYSTEM, 'def', category_folder_id=None)
        assert r.folder_id == 'def' and r.validation_status == 'low_confidence_defaulted'

    def test_invalid_folder_id_prefers_category_folder(self):
        r = conv_folder.validate_folder_assignment(_resp('ghost', 0.95), SYSTEM, 'def', category_folder_id='p')
        assert r.folder_id == 'p' and r.validation_status == 'invalid_folder_id_category_matched'

    def test_invalid_folder_id_without_category_uses_default(self):
        r = conv_folder.validate_folder_assignment(_resp('ghost', 0.95), SYSTEM, 'def', category_folder_id=None)
        assert r.folder_id == 'def' and r.validation_status == 'invalid_folder_id_defaulted'

    def test_category_folder_not_in_user_folders_is_ignored(self):
        r = conv_folder.validate_folder_assignment(_resp('s', 0.3), SYSTEM, 'def', category_folder_id='ghost')
        assert r.folder_id == 'def' and r.validation_status == 'low_confidence_defaulted'

    def test_other_category_low_confidence_routes_to_default_not_personal(self):
        # End-to-end of the missing/'other' path: resolve gives no category folder, so a
        # low-confidence pick lands in the default folder, not Personal. Before #4043's fix
        # 'other' folded onto Personal and this would have returned 'p'.
        cat_folder = folders_db.resolve_category_folder_id('other', SYSTEM)
        r = conv_folder.validate_folder_assignment(_resp('s', 0.3), SYSTEM, 'def', category_folder_id=cat_folder)
        assert r.folder_id == 'def' and r.validation_status == 'low_confidence_defaulted'


def _run_assign(llm_folder_id, confidence, category_folder_id):
    resp = _resp(llm_folder_id, confidence)
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = resp
    mock_chain.__or__ = MagicMock(return_value=mock_chain)
    mock_llm = MagicMock()
    mock_llm.__or__ = MagicMock(return_value=mock_chain)
    with patch.object(conv_folder, "get_llm", return_value=mock_llm), patch.object(
        conv_folder, "ChatPromptTemplate"
    ) as mock_prompt_cls, patch.object(conv_folder, "PydanticOutputParser", return_value=MagicMock()):
        mock_prompt = MagicMock()
        mock_prompt.__or__ = MagicMock(return_value=mock_chain)
        mock_prompt_cls.from_messages.return_value = mock_prompt
        return conv_folder.assign_conversation_to_folder(
            'Quarterly budget',
            'Talked through next quarter spend',
            'finance',
            SYSTEM,
            category_folder_id=category_folder_id,
        )


class TestAssignConversationToFolder:
    def test_uncertain_assignment_falls_back_to_category_folder(self):
        folder_id, confidence, _ = _run_assign('s', 0.3, category_folder_id='w')
        assert folder_id == 'w'

    def test_confident_assignment_is_not_overridden_by_category(self):
        folder_id, _, _ = _run_assign('s', 0.95, category_folder_id='w')
        assert folder_id == 's'
