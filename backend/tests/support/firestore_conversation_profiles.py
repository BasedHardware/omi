from __future__ import annotations

import ast
import hashlib
import os
import re
from pathlib import Path
from typing import Any

from tests.support.firestore_query_drivers import CallerProfile, FROZEN_LATER, FROZEN_NOW

TARGETS = frozenset(
    f'database.conversations.{name}'
    for name in ('get_conversations', 'get_conversations_count', 'get_conversations_without_photos')
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
    return CallerProfile(name, {**fixed, **domains})


_DATES = {'start_date': [None, FROZEN_NOW], 'end_date': [None, FROZEN_LATER]}
_SELECTORS = {'include_discarded': [False, True], 'folder_id': [None, 'folder-1'], 'starred': [None, False, True]}
_MULTI_STATUS = [['processing', 'completed']]
_SOURCES = [None, ['omi'], ['friend', 'omi']]

COUNT_PROFILES = (
    _profile('main-count-all-statuses', statuses=[None], sources=_SOURCES, **_DATES, **_SELECTORS),
    _profile('main-count-single-status', statuses=[['completed']], sources=_SOURCES, **_DATES, **_SELECTORS),
    _profile('main-count-multi-status', statuses=_MULTI_STATUS, sources=[None, ['omi']], **_DATES, **_SELECTORS),
    _profile('search-overview-starred', statuses=[None], starred=[True]),
    _profile('search-overview-folder', statuses=[None], folder_id=['folder-1']),
)

WITHOUT_PHOTOS_PROFILES = (
    _profile('main-list-single-status', statuses=[['completed']], sources=_SOURCES, **_DATES, **_SELECTORS),
    _profile(
        'main-list-default-or-multi-status', statuses=_MULTI_STATUS, sources=[None, ['omi']], **_DATES, **_SELECTORS
    ),
    _profile('people-stats'),
    _profile('speaker-search-fallback', include_discarded=[False, True], **_DATES),
    _profile('prior-meeting-context', start_date=[FROZEN_NOW], end_date=[FROZEN_LATER]),
    _profile('wrapped-2025', statuses=[['completed']], start_date=[FROZEN_NOW], end_date=[FROZEN_LATER]),
)

PHOTO_PROFILES = (
    _profile(
        'developer-list',
        photo=True,
        statuses=[['completed']],
        categories=[None, ['one'], ['one', 'two']],
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
    _profile('mentor-notification', photo=True),
    _profile('goal-context', photo=True, statuses=[['completed']]),
    _profile('fair-use-classification', photo=True, start_date=[FROZEN_NOW]),
    _profile('speaker-prompts', photo=True, start_date=[FROZEN_NOW], end_date=[FROZEN_LATER]),
)

PROFILES = {
    'database.conversations.get_conversations': PHOTO_PROFILES,
    'database.conversations.get_conversations_count': COUNT_PROFILES,
    'database.conversations.get_conversations_without_photos': WITHOUT_PHOTOS_PROFILES,
}


def discover_conversation_callers(root: Path) -> dict[str, dict[str, Any]]:
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
        if not re.search(r'\bget_conversations(?:_count|_without_photos)?\b', source):
            continue
        tree = ast.parse(source)
        imports = (
            {target.rsplit('.', 1)[1]: target for target in TARGETS}
            if relative.as_posix() == 'database/conversations.py'
            else {}
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
            if isinstance(node, ast.Assign) and resolve(node.value) in TARGETS:
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
                    if target not in TARGETS:
                        continue
                    owner = owners[0] if owners else tree
                    owner_name = '.'.join(item.name for item in owners) or '<module>'
                    key = f'{relative.as_posix()}:{owner_name}:{target}'
                    digest = hashlib.sha256(ast.dump(owner, include_attributes=False).encode()).hexdigest()
                    record = found.setdefault(key, {'target': target, 'digest': digest, 'references': 0})
                    record['references'] += 1
            for child in ast.iter_child_nodes(node):
                visit(child, owners)

        visit(tree)
    return found
