"""Query profile for the internal UTC-month shadow usage reader."""

from tests.support.firestore_query_drivers import DriverEntry, FROZEN_NOW, SHAPE_UID

DRIVER = DriverEntry(
    'database.usage_units.get_usage_units',
    base={'uid': SHAPE_UID, 'period': FROZEN_NOW},
    neutrals={'entitlements': (None, 'budget metadata only; does not change the query')},
)
