"""Executable query shapes for canonical task membership and browse discovery."""

from itertools import product
from unittest.mock import patch

from models.conversation_tasks import TaskConversationPageRequest
from tests.support.firestore_query_drivers import DriverEntry, FROZEN_NOW, FROZEN_LATER, SHAPE_UID
from utils.other.list_budget import ListReadBudget


def entries():
    work = (
        ListReadBudget(deadline_monotonic=12, max_documents=2000, clock=lambda: 0.0),
        'request budget only; fresh deep copy per shape trial',
    )
    cache = lambda client: patch('database.conversation_task_links.get_action_items_list_version', return_value=None)
    return (
        DriverEntry(
            'database.conversation_task_links.linked_task_presence',
            base={'uid': SHAPE_UID},
            domains={'ids': [[], ['conv-1'], [f'conv-{i}' for i in range(31)]]},
            neutrals={'budget': work},
            patchers=(cache,),
        ),
        DriverEntry(
            'database.conversation_task_links.visible_task_presence',
            base={'uid': SHAPE_UID, 'ids': ['conv-1']},
            neutrals={'budget': work},
            patchers=(cache,),
            setup=lambda client, combo, trial: client.documents.update(
                {
                    f'users/{SHAPE_UID}/conversations/conv-1': {'is_locked': False, 'deleted': False},
                }
            ),
        ),
        DriverEntry(
            'database.conversation_task_links.browse_candidate_page',
            base={'uid': SHAPE_UID},
            domains={
                'filters': [
                    TaskConversationPageRequest(
                        include_discarded=discarded, folder_id=folder, starred=starred, start_date=start, end_date=end
                    )
                    for discarded, folder, starred, start, end in product(
                        (False, True), (None, 'work'), (None, False, True), (None, FROZEN_NOW), (None, FROZEN_LATER)
                    )
                ]
            },
            neutrals={
                'after': (None, 'opaque bookmark; ordering/filters unchanged'),
                'scope': ('task-filter-shape', 'cursor binding only'),
                'budget': work,
            },
        ),
    )
