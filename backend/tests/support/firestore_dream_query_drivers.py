"""Executable query profiles for bounded dream worker and feedback reads."""

from types import SimpleNamespace

from config.dream_agent import Caps
from tests.support.firestore_query_drivers import DriverEntry, SHAPE_UID as UID
from tests.support import firestore_review_query_drivers as review


def entries():
    return (
        DriverEntry('database.dream_store.candidates', domains={'limit': [1, 100]}),
        DriverEntry(
            'database.dream_store.events',
            base={'uid': UID},
            domains={'lease': [{'watermark': 0, 'sequence': 5}, {'watermark': 10, 'sequence': 20}]},
        ),
        DriverEntry(
            'database.dream_store.demoted_types',
            base={'uid': UID},
            neutrals={'caps': (Caps(), 'post-query policy only')},
        ),
        DriverEntry('database.dream_feedback.read_patterns', neutrals={'k': (20, 'post-query threshold only')}),
    )


registry_extension = SimpleNamespace(
    DRIVERS={**review.registry_extension.DRIVERS, **{entry.function: entry for entry in entries()}},
    COVERED_BY=review.registry_extension.COVERED_BY,
    SKIPS=review.registry_extension.SKIPS,
)
