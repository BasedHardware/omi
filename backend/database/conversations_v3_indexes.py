"""Pure index declarations for filtered recording/Home layer counts."""

from itertools import combinations
from database.firestore_query_types import FirestoreIndexField, FirestoreIndexRequirement


def layer_count_indexes():
    """Date-filtered layer aggregates need the same optional list predicates.

    Pure equality queries use index merging; date ranges require composites.
    """
    optional = ('discarded', 'status', 'source', 'structured.category', 'folder_id', 'starred')
    for layer in (('recording',), ('home_hidden',), ('recording', 'home_hidden')):
        for count in range(len(optional) + 1):
            for selected in combinations(optional, count):
                fields = tuple(sorted((*layer, *selected)))
                yield FirestoreIndexRequirement(
                    'conversation_layer_count_' + '_'.join(fields),
                    'conversations',
                    'COLLECTION',
                    tuple(
                        FirestoreIndexField(field, order='ASCENDING') for field in (*fields, 'created_at', '__name__')
                    ),
                )
