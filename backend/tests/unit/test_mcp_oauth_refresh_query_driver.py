"""Keep the refresh callback's query-driver contract independently executable."""

from tests.support.firestore_query_driver_registry import DRIVERS
from tests.support.firestore_query_drivers import run_driver


def test_refresh_rotation_query_driver_classifies_outcome_callback():
    result = run_driver(DRIVERS['database.mcp_oauth.rotate_refresh_token'])
    assert not result.errors, result.errors
    assert result.shapes  # The beyond-grace revoke must still record its queries.
