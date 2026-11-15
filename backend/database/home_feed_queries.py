"""Indexed feed streams; standalone filtering happens before page limits."""

from database.firestore_query_types import FirestoreIndexField as I, FirestoreQueryFilter as F, FirestoreQuerySpec as Q

EPISODES = Q(
    'home_feed_episodes',
    'episodes',
    'COLLECTION',
    (F('home_visible', '==', 'visible'),),
    (
        I('home_visible', order='ASCENDING'),
        I('home_sort_at', order='DESCENDING'),
        I('__name__', order='DESCENDING'),
    ),
)
CONVERSATIONS = Q(
    'home_feed_conversations',
    'conversations',
    'COLLECTION',
    (F('home_visible', '==', 'visible'),),
    (
        I('home_visible', order='ASCENDING'),
        I('home_sort_at', order='DESCENDING'),
        I('__name__', order='DESCENDING'),
    ),
)
STANDALONE = Q(
    'home_feed_standalone',
    'conversations',
    'COLLECTION',
    (
        F('home_visible', '==', 'visible'),
        F('home_standalone', '==', 'standalone'),
    ),
    (
        I('home_visible', order='ASCENDING'),
        I('home_standalone', order='ASCENDING'),
        I('home_sort_at', order='DESCENDING'),
        I('__name__', order='DESCENDING'),
    ),
)
HOME_FEED_QUERY_SPECS = (EPISODES, CONVERSATIONS, STANDALONE)
