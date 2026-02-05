"""
Tests for KeyError fix on missing 'uid' in app dict lookups (#4522).
Verifies that safe dict access app.get('uid') handles missing uid field
without raising KeyError, matching the fix in utils/apps.py.
"""


def _check_private_app_access(app: dict, uid: str | None) -> bool:
    """Extracted access-check logic from get_available_app_by_id (line 260).
    Returns True if access should be denied (app is private and uid doesn't match)."""
    return app['private'] and app.get('uid') != uid


def _check_private_app_access_old(app: dict, uid: str | None) -> bool:
    """Old (buggy) access-check logic that raises KeyError on missing uid."""
    return app['private'] and app['uid'] != uid


class TestSafeUidAccess:
    """Test that app.get('uid') handles missing uid without KeyError."""

    def test_private_app_missing_uid_no_keyerror(self):
        """Private app with no 'uid' key should not raise KeyError."""
        app = {'id': 'app1', 'private': True}
        result = _check_private_app_access(app, 'user1')
        assert result is True  # Access denied (uid=None != 'user1')

    def test_old_pattern_raises_keyerror(self):
        """Demonstrate the old pattern raises KeyError on missing uid."""
        app = {'id': 'app1', 'private': True}
        try:
            _check_private_app_access_old(app, 'user1')
            assert False, "Should have raised KeyError"
        except KeyError as e:
            assert str(e) == "'uid'"

    def test_private_app_uid_matches_owner(self):
        """Private app where uid matches should allow access."""
        app = {'id': 'app1', 'private': True, 'uid': 'user1'}
        result = _check_private_app_access(app, 'user1')
        assert result is False  # Access allowed

    def test_private_app_uid_mismatch(self):
        """Private app where uid doesn't match should deny access."""
        app = {'id': 'app1', 'private': True, 'uid': 'other_user'}
        result = _check_private_app_access(app, 'user1')
        assert result is True  # Access denied

    def test_public_app_missing_uid_allows_access(self):
        """Public app with no uid key should allow access (private=False short-circuits)."""
        app = {'id': 'app1', 'private': False}
        result = _check_private_app_access(app, 'user1')
        assert result is False  # Access allowed (private=False)

    def test_public_app_with_uid_allows_access(self):
        """Public app should allow access regardless of uid."""
        app = {'id': 'app1', 'private': False, 'uid': 'other_user'}
        result = _check_private_app_access(app, 'user1')
        assert result is False  # Access allowed (private=False)

    def test_private_app_uid_none_requesting_none(self):
        """Private app with uid=None and requesting uid=None should allow access."""
        app = {'id': 'app1', 'private': True, 'uid': None}
        result = _check_private_app_access(app, None)
        assert result is False  # Access allowed (None == None)

    def test_private_app_missing_uid_requesting_none(self):
        """Private app missing uid, requesting uid=None: get('uid') returns None == None."""
        app = {'id': 'app1', 'private': True}
        result = _check_private_app_access(app, None)
        assert result is False  # Access allowed (None == None)
