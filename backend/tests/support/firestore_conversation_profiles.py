from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any

from database.conversation_scan import PEOPLE_STATS_FIELD_PATHS
from tests.support.firestore_query_drivers import CallerProfile, FROZEN_LATER, FROZEN_NOW

TARGETS = frozenset(
    {
        f'database.conversations.{name}'
        for name in ('get_conversations', 'get_conversations_count', 'get_conversations_without_photos')
    }
    | {
        'database.conversation_scan.iter_conversations',
        'database.conversation_scan.people_stats_scan',
        'database.conversation_scan.speaker_browse_scan',
    }
)


def _profile(name: str, *, photo: bool = False, **domains) -> CallerProfile:
    fixed = {
        'include_discarded': [False],
        'statuses': [[]],
        'start_date': [None],
        'end_date': [None],
        'categories': [None],
        'folder_id': [None],
        'starred': [None],
    }
    fixed['date_field' if photo else 'sources'] = ['created_at'] if photo else [None]
    if photo:
        fixed['metadata_only'] = [False]
    return CallerProfile(name, {**fixed, **domains})


_DATES = {'start_date': [None, FROZEN_NOW], 'end_date': [None, FROZEN_LATER]}


def _scan_profile(name: str, **domains) -> CallerProfile:
    """``iter_conversations`` caller domain row — its parameter surface is the
    scan reader's, not the retired ``get_conversations*`` signature."""
    return CallerProfile(name, {**domains})


_SELECTORS = {'include_discarded': [False, True], 'folder_id': [None, 'folder-1'], 'starred': [None, False, True]}
_MULTI_STATUS = [['processing', 'completed']]
_ROUTE_SOURCES = [[], ['omi'], ['friend', 'omi']]

COUNT_PROFILES = (
    _profile('main-count-all-statuses', statuses=[[]], sources=_ROUTE_SOURCES, **_DATES, **_SELECTORS),
    _profile('main-count-single-status', statuses=[['completed']], sources=_ROUTE_SOURCES, **_DATES, **_SELECTORS),
    _profile('main-count-multi-status', statuses=_MULTI_STATUS, sources=[[], ['omi']], **_DATES, **_SELECTORS),
    _profile('search-overview-starred', statuses=[None], starred=[True]),
    _profile('search-overview-folder', statuses=[None], folder_id=['folder-1']),
)

WITHOUT_PHOTOS_PROFILES = (
    _profile('main-list-single-status', statuses=[['completed']], sources=_ROUTE_SOURCES, **_DATES, **_SELECTORS),
    _profile(
        'main-list-default-or-multi-status', statuses=_MULTI_STATUS, sources=[[], ['omi']], **_DATES, **_SELECTORS
    ),
    _profile('prior-meeting-context', start_date=[FROZEN_NOW], end_date=[FROZEN_LATER]),
    _profile('wrapped-2025', statuses=[['completed']], start_date=[FROZEN_NOW], end_date=[FROZEN_LATER]),
)

SCAN_PROFILES = (
    _scan_profile(
        'people-stats',
        include_discarded=[False],
        start_date=[None],
        end_date=[None],
        field_paths=[PEOPLE_STATS_FIELD_PATHS],
    ),
    _scan_profile(
        'speaker-search-fallback',
        include_discarded=[False, True],
        start_date=[None, FROZEN_NOW],
        end_date=[None, FROZEN_LATER],
        field_paths=[None],
    ),
)

# The recipe helpers' own parameter surface: people_stats_scan carries no
# caller-facing filter dims; speaker_browse_scan forwards only the filter args.
RECIPE_PROFILES = (
    _scan_profile('people-stats-recipe'),
    _scan_profile(
        'speaker-search-fallback-recipe',
        include_discarded=[False, True],
        start_date=[None, FROZEN_NOW],
        end_date=[None, FROZEN_LATER],
    ),
)

PHOTO_PROFILES = (
    _profile(
        'support-trace',
        photo=True,
        metadata_only=[True],
        date_field=['started_at'],
        include_discarded=[True],
        start_date=[FROZEN_NOW],
        end_date=[FROZEN_LATER],
    ),
    _profile(
        'developer-list',
        photo=True,
        statuses=[['completed']],
        categories=[[], ['personal'], ['personal', 'technology']],
        folder_id=[None, 'folder-1'],
        starred=[None, False, True],
        **_DATES,
    ),
    _profile(
        'integration-list',
        photo=True,
        include_discarded=[False, True],
        statuses=[[], ['completed'], *_MULTI_STATUS],
        **_DATES,
    ),
    _profile(
        'tool-service',
        photo=True,
        include_discarded=[False, True],
        statuses=[[], ['completed'], *_MULTI_STATUS],
        **_DATES,
    ),
    _profile(
        'chat-retrieval',
        photo=True,
        include_discarded=[False, True],
        statuses=[[], ['completed'], *_MULTI_STATUS],
        **_DATES,
    ),
    _profile(
        'daily-summary-test', photo=True, date_field=['started_at'], start_date=[FROZEN_NOW], end_date=[FROZEN_LATER]
    ),
    _profile(
        'daily-summary-regenerate',
        photo=True,
        date_field=['started_at'],
        start_date=[FROZEN_NOW],
        end_date=[FROZEN_LATER],
    ),
    _profile(
        'daily-summary-generation',
        photo=True,
        date_field=['started_at'],
        start_date=[FROZEN_NOW],
        end_date=[FROZEN_LATER],
    ),
    _profile(
        'calendar-capture-gaps',
        photo=True,
        date_field=['started_at'],
        include_discarded=[True],
        start_date=[FROZEN_NOW],
        end_date=[FROZEN_LATER],
    ),
    _profile(
        'limitless-legacy-lookup',
        photo=True,
        date_field=['started_at'],
        include_discarded=[True],
        start_date=[FROZEN_NOW],
        end_date=[FROZEN_NOW],
    ),
    _profile('persona-create', photo=True),
    _profile('persona-update', photo=True),
    _profile('goal-context', photo=True, statuses=[['completed']]),
    _profile('fair-use-classification', photo=True, start_date=[FROZEN_NOW]),
    _profile('speaker-prompts', photo=True, start_date=[FROZEN_NOW], end_date=[FROZEN_LATER]),
    _profile('speaker-voice-matches', photo=True, start_date=[FROZEN_NOW], end_date=[FROZEN_LATER]),
)

PROFILES = {
    'database.conversations.get_conversations': PHOTO_PROFILES,
    'database.conversations.get_conversations_count': COUNT_PROFILES,
    'database.conversations.get_conversations_without_photos': WITHOUT_PHOTOS_PROFILES,
    'database.conversation_scan.iter_conversations': SCAN_PROFILES,
    'database.conversation_scan.people_stats_scan': (RECIPE_PROFILES[0],),
    'database.conversation_scan.speaker_browse_scan': (RECIPE_PROFILES[1],),
}


def discover_callers(root: Path, targets: frozenset[str]) -> dict[str, dict[str, Any]]:
    """Statically find call sites of ``targets`` under ``root`` (detection only)."""
    target_modules = {target.rsplit('.', 1)[0].replace('.', '/') + '.py' for target in targets}
    attr_names = {target.rsplit('.', 1)[1] for target in targets}
    found = {}
    paths = []
    for directory, folders, files in os.walk(root):
        folders[:] = sorted(
            name
            for name in folders
            if name not in {'tests', 'testing', 'scripts', '__pycache__'} and not name.startswith('.')
        )
        paths.extend(Path(directory) / name for name in files if name.endswith('.py'))
    for path in sorted(paths):
        relative = path.relative_to(root)
        source = path.read_text()
        if not re.search(r'\b(?:' + '|'.join(sorted(attr_names)) + r')\b', source):
            continue
        tree = ast.parse(source)
        imports = (
            {target.rsplit('.', 1)[1]: target for target in targets} if relative.as_posix() in target_modules else {}
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports[alias.asname or alias.name.split('.')[0]] = (
                        alias.name if alias.asname else alias.name.split('.')[0]
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    imports[alias.asname or alias.name] = f'{node.module}.{alias.name}'

        def resolve(node):
            if isinstance(node, ast.Name):
                return imports.get(node.id, node.id)
            if isinstance(node, ast.Attribute):
                return f'{resolve(node.value)}.{node.attr}'
            return ''

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and resolve(node.value) in targets:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        imports[target.id] = resolve(node.value)

        def visit(node, owners=()):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                owners = (*owners, node)
            if isinstance(node, ast.Call):
                references = [node.func, *node.args, *(kw.value for kw in node.keywords)]
                for reference in references:
                    target = resolve(reference)
                    if target not in targets:
                        continue
                    owner_name = '.'.join(item.name for item in owners) or '<module>'
                    key = f'{relative.as_posix()}:{owner_name}:{target}'
                    record = found.setdefault(key, {'target': target, 'references': 0})
                    record['references'] += 1
            for child in ast.iter_child_nodes(node):
                visit(child, owners)

        visit(tree)
    return found


def discover_conversation_callers(root: Path) -> dict[str, dict[str, Any]]:
    return discover_callers(root, TARGETS)
