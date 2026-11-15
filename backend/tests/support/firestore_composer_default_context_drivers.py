"""Runtime witnesses for the composer's fixed single-field candidate windows."""

from tests.support.firestore_query_drivers import (
    FROZEN_LATER,
    FROZEN_NOW,
    SHAPE_UID,
    CoveredByEntry,
    DriverEntry,
)
from utils.episodes.composer_default_context import ReadBudget

PREFIX = 'utils.episodes.composer_default_context_io.'
MEMBERS = [{'id': 'current', 'started_at': FROZEN_NOW, 'finished_at': FROZEN_LATER}]


def entries():
    budget = lambda: (ReadBudget(10**30), 'fixed 48-read allowance and deadline affect RPC/window only')
    return [
        DriverEntry(PREFIX + 'calendar', base={'uid': SHAPE_UID, 'members': MEMBERS}, neutrals={'budget': budget()}),
        DriverEntry(
            PREFIX + 'prior',
            base={'uid': SHAPE_UID, 'members': MEMBERS, 'ids': ['person-1']},
            neutrals={'budget': budget()},
        ),
        DriverEntry(
            PREFIX + 'actions',
            base={
                'uid': SHAPE_UID,
                'ids': ['person-1'],
                'people_rows': [],
                'prior_rows': [{'conversation_id': 'prior'}],
            },
            domains={'member_ids': [[], ['current'], [f'member-{i}' for i in range(65)]]},
            neutrals={'budget': budget()},
        ),
        CoveredByEntry(
            PREFIX + '_query',
            covered_by=tuple(PREFIX + name for name in ('calendar', 'prior', 'actions')),
            reason='The common bounded terminal runs under each named section driver.',
        ),
    ]
