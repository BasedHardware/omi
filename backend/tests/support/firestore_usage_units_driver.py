"""Query profile for the internal UTC-month shadow usage reader."""

from tests.support.firestore_query_drivers import DriverEntry, FROZEN_NOW, SHAPE_UID

DRIVER = DriverEntry(
    'database.usage_units.get_usage_units',
    base={'uid': SHAPE_UID, 'period': FROZEN_NOW},
    neutrals={
        'entitlements': (None, 'budget metadata only; does not change the query'),
        'session_cache': (
            None,
            'session cache changes query frequency only; every full refresh uses the same month builder; warm refreshes use document get_all',
        ),
        'rate_card_version': (None, 'selects which shadow_v* map to total; projection only, same query shape'),
    },
)
