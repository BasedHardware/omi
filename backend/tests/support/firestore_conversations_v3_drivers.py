"""Execute recording-builder and sweeper query shapes without external effects."""

from unittest.mock import patch

from tests.support.firestore_query_drivers import DriverEntry, SHAPE_UID, FROZEN_NOW


def _pending_source(client, combo, trial):
    client.queue_results(
        [
            client.snapshot(
                f'users/{SHAPE_UID}/conversations/source',
                {
                    'id': 'source',
                    'recording': True,
                    'started_at': FROZEN_NOW,
                    'finished_at': FROZEN_NOW,
                    'status': 'completed',
                },
            )
        ]
    )


def _decode(client):
    return patch('database.conversations_v3.decode_row', side_effect=lambda uid, snapshot: snapshot.to_dict())


def entries():
    return (
        DriverEntry(
            'database.conversations_v3.load', base={'uid': SHAPE_UID}, setup=_pending_source, patchers=(_decode,)
        ),
        DriverEntry('database.conversations_v3.load_derive', base={'uid': SHAPE_UID}),
        DriverEntry('utils.conversations.v3.service.has_pending', base={'uid': SHAPE_UID}),
        DriverEntry('utils.conversations.v3.service.pending_processing', base={'uid': SHAPE_UID}),
        DriverEntry('utils.conversations.v3.service.sweep'),
        DriverEntry('utils.conversations.v3.service.measure_legacy_users'),
    )
