"""Real allowance query builders across owner/global, cursor and stage profiles."""

from dataclasses import dataclass
from types import SimpleNamespace

from tests.support.firestore_query_drivers import DriverEntry, CoveredByEntry


@dataclass(frozen=True)
class StoreArgument:
    namespace: str

    def __deepcopy__(self, memo):
        # Bind only after the query runner installs RecordingFirestore.
        from database._client import get_data_plane_firestore_client

        return SimpleNamespace(client=get_data_plane_firestore_client(), namespace=self.namespace)


def seed_checkpoint(client, combo, trial):
    if trial:
        from database.batch_pipeline_allowance_migration import KEY

        client.documents[f'{combo["store"].namespace}_migrations/{KEY}'] = {'after': 'previous-row'}


def entries():
    namespaces = ['batch_pipeline_prod', 'batch_pipeline_dev']
    stores = [StoreArgument(namespace) for namespace in namespaces]
    return (
        DriverEntry(
            'database.batch_pipeline_store.FirestoreStore.allowance_owners',
            domains={'self': stores},
            neutrals={'now': (3000000.0, 'due clock operand only'), 'limit': (20, 'page bound only')},
        ),
        DriverEntry(
            'database.batch_pipeline_store.FirestoreStore.allowance_page',
            domains={'self': stores, 'owner_key': [None, 'synthetic-owner-hash'], 'after': [None, [1.0, 'previous']]},
            neutrals={'limit': (100, 'page bound only')},
        ),
        DriverEntry('database.batch_pipeline_store.allowance_held_count', domains={'namespace': namespaces}),
        DriverEntry('database.batch_pipeline_allowance_migration.counts', domains={'store': stores}),
        DriverEntry(
            'database.batch_pipeline_allowance_migration.apply_page',
            domains={'store': stores},
            neutrals={'now': (3000000.0, 'checkpoint clock only'), 'size': (100, 'page bound only')},
            trials=2,
            setup=seed_checkpoint,
        ),
        CoveredByEntry(
            'database.batch_pipeline_allowance_migration.candidates',
            covered_by=(
                'database.batch_pipeline_allowance_migration.counts',
                'database.batch_pipeline_allowance_migration.apply_page',
            ),
            reason='candidate builder returns a query; both drivers execute its count or ordered ID page',
            expect_observed=False,
            body_digest='04c9beae56ec6091544a2ec69a8ba170032dbe3670697b704db2f88d513bc5cb',
        ),
    )
