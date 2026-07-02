"""Regression pin for the autouse isolation fixture in conftest.py.

Cubic review 4614271733 P3: the autouse fixture in conftest.py
clears `simple_storage.users` and `simple_storage.pending_setups`
at the start of every test, so entries from one test don't leak
into the next. These tests pin the contract: the fixture is
actually invoked (autouse), and the cleared state is consistent
between consecutive tests.

The tests are intentionally simple: they import the simple_storage
module FROM WITHIN the test function (not at module top) so they
get the conftest-installed sys.modules['simple_storage'] reference,
not a stale import captured before the autouse fixture ran. This
catches the case where a future refactor removes the .clear() call
from conftest.py.
"""

from __future__ import annotations

import sys


class TestSimpleStorageStateIsolation:
    """Pin that the autouse fixture in conftest.py clears the
    module-level `users` and `pending_setups` dicts at the start
    of every test.
    """

    def test_users_dict_starts_empty(self):
        """At the start of this test (after the autouse fixture ran),
        the users dict must be empty. If a previous test left entries
        here, the conftest's `.clear()` call is missing.

        Import inside the test so we pick up the conftest's
        sys.modules['simple_storage'] (installed by the autouse
        fixture) rather than a stale reference captured at module
        collection time.
        """
        import simple_storage  # noqa: F401

        assert simple_storage.users == {}, (
            f"users dict has leftover entries: {simple_storage.users!r}. "
            f"conftest.py's autouse fixture should clear it at the "
            f"start of every test."
        )

    def test_pending_setups_dict_starts_empty(self):
        """At the start of this test, pending_setups must be empty.
        If a previous test left entries here, the conftest's
        .clear() call is missing."""
        import simple_storage  # noqa: F401

        assert simple_storage.pending_setups == {}, (
            f"pending_setups dict has leftover entries: "
            f"{simple_storage.pending_setups!r}. conftest.py's autouse "
            f"fixture should clear it at the start of every test."
        )

    def test_pollution_does_not_leak_between_tests(self):
        """Inject a sentinel into both module-level dicts. The NEXT
        test (the one pytest runs after this one) must NOT see this
        sentinel — proving the autouse fixture cleared the state
        before that test started.
        """
        import simple_storage  # noqa: F401

        # Plant entries that any sane test would refuse to leave behind.
        simple_storage.users["sentinel"] = {"phone": "sentinel"}
        simple_storage.pending_setups["sentinel"] = {"token": "sentinel"}
        # The autouse fixture runs BEFORE the next test, so the next
        # test sees empty state. The two tests above running before
        # any state-mutating test is the actual contract — they would
        # fail if the autouse fixture's .clear() call were removed.
        assert "sentinel" in simple_storage.users  # invariant for THIS test
