"""Executable serving-query profiles owned by the Review feature."""

from types import SimpleNamespace
from unittest.mock import patch

from tests.support.firestore_query_drivers import DriverEntry, FROZEN_NOW as NOW, SHAPE_UID as UID


def _changes_seed(client, combo, trial):
    if combo.get('cursor'):
        from database.review_store import safe_id

        client.documents[f'users/{UID}/review_changes/{safe_id(combo["cursor"])}'] = {'created_at': NOW}


def _project_dependencies(client):
    from contextlib import ExitStack
    from utils import entity_pages

    stack = ExitStack()
    stack.enter_context(
        patch.object(
            entity_pages, 'resolve_entity', return_value={'entity_id': 'project', 'type': 'project', 'name': 'Launch'}
        )
    )
    stack.enter_context(patch.object(entity_pages, 'entity_facts', return_value=([], [], set())))
    stack.enter_context(patch.object(entity_pages.knowledge_graph, 'get_knowledge_edges', return_value=[]))
    stack.enter_context(patch.object(entity_pages.conversations, 'get_conversations', return_value=[]))
    stack.enter_context(patch.object(entity_pages.store, 'list_proposals', return_value=[]))
    return stack


def entries():
    return (
        DriverEntry('database.review_store.list_proposals', base={'uid': UID}),
        DriverEntry(
            'database.review_changes.list_changes',
            base={'uid': UID},
            domains={'cursor': [None, 'cursor']},
            neutrals={'now': (NOW, 'operand clock only')},
            setup=_changes_seed,
        ),
        DriverEntry('utils.entity_pages.project_refs', base={'uid': UID}),
        DriverEntry('utils.entity_pages.entity_facts', base={'uid': UID, 'entity_ids': ['org']}),
        DriverEntry(
            'utils.entity_pages.get_entity_page',
            base={'uid': UID, 'entity_id': 'project'},
            patchers=(_project_dependencies,),
        ),
    )


# Preserve the existing outside drivers by identity; add this feature's owned profiles.
from tests.support import firestore_outside_query_drivers as outside

registry_extension = SimpleNamespace(
    DRIVERS={**outside.DRIVERS, **{entry.function: entry for entry in entries()}},
    COVERED_BY=outside.COVERED_BY,
    SKIPS=outside.SKIPS,
)
