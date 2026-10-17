import unittest

from database.account_deletion_policy import (
    ACCOUNT_DELETION_ACCESS_ALLOWED_STATUSES,
    ACCOUNT_DELETION_INVALID_STATUS,
    account_deletion_blocks_access,
    normalize_account_deletion_status,
)


class TestAccountDeletionPolicy(unittest.TestCase):
    def test_normalize_account_deletion_status_non_existent_marker(self):
        self.assertIsNone(normalize_account_deletion_status(marker_exists=False, raw_status=None))
        self.assertIsNone(normalize_account_deletion_status(marker_exists=False, raw_status="active"))
        self.assertIsNone(normalize_account_deletion_status(marker_exists=False, raw_status=""))

    def test_normalize_account_deletion_status_existing_marker_valid(self):
        self.assertEqual(
            normalize_account_deletion_status(marker_exists=True, raw_status="cancelled"),
            "cancelled",
        )
        self.assertEqual(
            normalize_account_deletion_status(marker_exists=True, raw_status="  pending  "),
            "pending",
        )
        self.assertEqual(
            normalize_account_deletion_status(marker_exists=True, raw_status="billing_failed"),
            "billing_failed",
        )

    def test_normalize_account_deletion_status_existing_marker_invalid_or_malformed(self):
        self.assertEqual(
            normalize_account_deletion_status(marker_exists=True, raw_status=""),
            ACCOUNT_DELETION_INVALID_STATUS,
        )
        self.assertEqual(
            normalize_account_deletion_status(marker_exists=True, raw_status="   "),
            ACCOUNT_DELETION_INVALID_STATUS,
        )
        self.assertEqual(
            normalize_account_deletion_status(marker_exists=True, raw_status=None),
            ACCOUNT_DELETION_INVALID_STATUS,
        )
        self.assertEqual(
            normalize_account_deletion_status(marker_exists=True, raw_status=12345),
            ACCOUNT_DELETION_INVALID_STATUS,
        )
        self.assertEqual(
            normalize_account_deletion_status(marker_exists=True, raw_status={"status": "bad"}),
            ACCOUNT_DELETION_INVALID_STATUS,
        )

    def test_account_deletion_blocks_access_allowed_statuses(self):
        for allowed in ACCOUNT_DELETION_ACCESS_ALLOWED_STATUSES:
            self.assertFalse(account_deletion_blocks_access(allowed))

    def test_account_deletion_blocks_access_denied_or_invalid_statuses(self):
        self.assertFalse(account_deletion_blocks_access(None))
        self.assertTrue(account_deletion_blocks_access(ACCOUNT_DELETION_INVALID_STATUS))
        self.assertTrue(account_deletion_blocks_access("pending"))
        self.assertTrue(account_deletion_blocks_access("in_progress"))
        self.assertTrue(account_deletion_blocks_access("deleted"))
        self.assertTrue(account_deletion_blocks_access("failed"))


if __name__ == "__main__":
    unittest.main()
