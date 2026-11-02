"""Run the production deterministic functions offline without account imports.

The serving module still imports database/executor clients. Extract only named
pure first-party definitions and their pure dependencies, using the same source
isolation as contracts.production_projection. No provider/client initialization,
metrics registration, env policy, or other module top-level code is executed.
"""

from __future__ import annotations

import ast
import re
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from types import SimpleNamespace
from typing import Any

from evals.dream_verifier.contracts import BACKEND
from models.agent_refs import cited_value
from models.person_confidence import AUTO_CONFIRMED, CARD_CONFIRMS, CARD_PICKS, MANUAL_LABELS, evidence_count
from utils.agent_capabilities.guards import timestamp
from utils.agent_capabilities.registry import KINDS
from utils.agent_capabilities.text_edits import replace_term
from utils.conversations.fragment_visibility import is_completed_rule_discard, is_user_curated


def definitions(relative: str, names: set[str], namespace: dict[str, Any]) -> None:
    path = BACKEND / relative
    source = ast.parse(path.read_text())
    selected: list[ast.stmt] = [ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)]
    found = set()
    for node in source.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            selected.append(node)
            found.add(node.name)
        elif isinstance(node, ast.Assign):
            bound = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if bound & names:
                selected.append(node)
                found.update(bound & names)
    if found != names:
        raise ValueError('production_pure_dependency_contract_changed')
    module = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    exec(compile(module, str(path), 'exec'), namespace)


@lru_cache(maxsize=1)
def production_namespace() -> dict[str, Any]:
    namespace: dict[str, Any] = {
        '__name__': __name__,
        'dataclass': dataclass,
        'time': time,
        're': re,
        'unicodedata': unicodedata,
        'SequenceMatcher': SequenceMatcher,
        'timestamp': timestamp,
        'is_user_curated': is_user_curated,
        'is_completed_rule_discard': is_completed_rule_discard,
        'cited_value': cited_value,
        'replace_term': replace_term,
        'KINDS': KINDS,
        'Any': Any,
        'AUTO_CONFIRMED': AUTO_CONFIRMED,
        'CARD_CONFIRMS': CARD_CONFIRMS,
        'CARD_PICKS': CARD_PICKS,
        'MANUAL_LABELS': MANUAL_LABELS,
        'evidence_count': evidence_count,
    }
    definitions('database/conversations.py', {'is_soft_deleted', 'is_visible_conversation'}, namespace)
    namespace['conversations'] = SimpleNamespace(is_visible_conversation=namespace['is_visible_conversation'])
    definitions('utils/agent_capabilities/cleanup_edits.py', {'speech', 'require_duplicate_capture'}, namespace)
    definitions(
        'utils/llm/known_spellings.py',
        {'trusted_people_spellings', '_trusted_people_spellings', '_name', '_SINGLE_TOKEN_NOISE', 'MAX_TERMS'},
        namespace,
    )
    definitions(
        'utils/agent_capabilities/verifiers.py',
        {
            'VerifierStep',
            'Verdict',
            'item_kind',
            'run_deterministic',
            '_deterministic',
            '_registry_checks',
            '_run_check',
            '_check_spelling',
            '_check_duplicate',
            '_check_language',
            '_operation',
            '_text',
            '_records',
            '_row',
            '_cited_texts',
            '_trusted_forms',
            '_attested',
            '_error_reason',
            '_REASON',
        },
        namespace,
    )
    return namespace
