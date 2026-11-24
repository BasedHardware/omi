"""Executable profiles for compact serving and bounded explicit preparation."""

from config.episodes import home_step_projection_enabled
from tests.support.firestore_query_drivers import DriverEntry, SHAPE_UID


def _ready(client, combo, trial):
    client.documents[f'users/{SHAPE_UID}/episode_links/home_feed_control'] = {
        'schema': 1,
        'ready': True,
        'ready_members': home_step_projection_enabled(),
    }


def _phase(client, combo, trial):
    client.documents[f'users/{SHAPE_UID}/episode_links/home_feed_control'] = {
        'schema': 1,
        'ready': False,
        'ready_members': home_step_projection_enabled(),
        'phase': ('conversations', 'episodes', 'dirty')[trial],
        'cursor': None,
    }


def entries():
    return (
        DriverEntry(
            'database.home_feed.feed',
            base={'uid': SHAPE_UID},
            domains={'episodes_admitted': [True, False]},
            neutrals={
                'limit': (50, 'bounded page size only'),
                'cursor': (None, 'value continuation does not alter filters'),
            },
            setup=_ready,
        ),
        DriverEntry('database.home_feed.prepare', base={'uid': SHAPE_UID}, setup=_phase, trials=3),
    )
