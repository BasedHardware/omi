"""Executable profiles for D's erasure/retention query boundaries."""

from datetime import datetime, timezone
from tests.support.firestore_query_drivers import DriverEntry


def entries():
    namespaces = ['batch_pipeline_prod', 'batch_pipeline_dev']
    return (
        DriverEntry(
            'database.batch_pipeline_privacy_queries.owner_documents',
            base={'key': 'synthetic-owner-hash'},
            domains={'namespace': namespaces, 'table': ['jobs', 'results', 'artifacts', 'projections', 'intakes']},
            neutrals={'after': (None, 'document cursor only; filters unchanged')},
        ),
        DriverEntry(
            'database.batch_pipeline_privacy_queries.artifacts_by_owner_id',
            base={'uid': 'synthetic-owner'},
            domains={'namespace': namespaces},
            neutrals={'after': (None, 'document cursor only; filters unchanged')},
        ),
        DriverEntry(
            'database.batch_pipeline_privacy_queries.predecessor_documents',
            base={'segment_id': 'synthetic-segment'},
            domains={'namespace': namespaces},
            neutrals={'transaction': (None, 'transaction binding only')},
        ),
        DriverEntry(
            'database.batch_pipeline_privacy_queries.segment_artifacts',
            base={'segment_id': 'synthetic-segment'},
            domains={'namespace': namespaces},
            neutrals={'transaction': (None, 'transaction binding only')},
        ),
        DriverEntry(
            'database.batch_pipeline_privacy_queries.due_artifacts',
            domains={'namespace': namespaces},
            neutrals={
                'now': (datetime(2026, 10, 15, tzinfo=timezone.utc), 'timestamp operand only'),
                'limit': (100, 'bounded page size only'),
            },
        ),
    )
