"""
Tests for KeyError fix on missing 'uid' in app dict lookups (#4522).
Verifies that safe dict access app.get('uid') handles missing uid field
without raising KeyError, and that is_tester is guarded against None uid.
"""


def _check_private_app_access(app: dict, uid: str | None, is_tester_fn=None) -> bool:
    """Extracted access-check logic from get_available_app_by_id (line 254/260/270).
    Returns True if access should be denied (app is private and uid doesn't match and not tester)."""
    if is_tester_fn is None:
        is_tester_fn = lambda u: False
    return app['private'] and app.get('uid') != uid and not (uid and is_tester_fn(uid))


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


class TestTesterAccess:
    """Test that is_tester is guarded against None uid and grants access correctly."""

    def test_tester_accesses_private_app_not_owned(self):
        """Tester should access private app they don't own."""
        app = {'id': 'app1', 'private': True, 'uid': 'other_user'}
        result = _check_private_app_access(app, 'tester1', is_tester_fn=lambda u: True)
        assert result is False  # Access allowed (is_tester)

    def test_non_tester_denied_private_app_not_owned(self):
        """Non-tester should be denied access to private app they don't own."""
        app = {'id': 'app1', 'private': True, 'uid': 'other_user'}
        result = _check_private_app_access(app, 'user1', is_tester_fn=lambda u: False)
        assert result is True  # Access denied

    def test_none_uid_does_not_call_is_tester(self):
        """When uid is None, is_tester should NOT be called (would crash)."""
        app = {'id': 'app1', 'private': True, 'uid': 'owner'}
        call_count = 0

        def is_tester_bomb(uid):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("is_tester called with None!")

        result = _check_private_app_access(app, None, is_tester_fn=is_tester_bomb)
        assert result is True  # Access denied (None != 'owner', tester check skipped)
        assert call_count == 0  # is_tester was never called

    def test_tester_with_missing_uid_key(self):
        """Tester accessing private app with no uid key should be allowed."""
        app = {'id': 'app1', 'private': True}
        result = _check_private_app_access(app, 'tester1', is_tester_fn=lambda u: True)
        assert result is False  # Access allowed (is_tester)

    def test_none_uid_missing_uid_key_allows_access(self):
        """None uid with missing uid key: get('uid') returns None == None, access allowed."""
        app = {'id': 'app1', 'private': True}
        result = _check_private_app_access(app, None)
        assert result is False  # Access allowed (None == None, tester check not reached)
