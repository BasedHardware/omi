<content>
import unittest

from omi.plugins.arxiv.main import ArxivPlugin


class TestArxivPluginLimitAndAuthorCoercion(unittest.TestCase):
    """Test cases for boolean input handling in ArxivPlugin."""

    def setUp(self):
        self.plugin = ArxivPlugin()

    def test_clean_text_with_boolean(self):
        """Test _clean_text returns empty string for boolean inputs."""
        self.assertEqual(self.plugin._clean_text(True), "")
        self.assertEqual(self.plugin._clean_text(False), "")

    def test_clean_text_with_none(self):
        """Test _clean_text returns empty string for None input."""
        self.assertEqual(self.plugin._clean_text(None), "")

    def test_clean_text_with_string(self):
        """Test _clean_text works correctly with string inputs."""
        self.assertEqual(self.plugin._clean_text("  test  "), "test")
        self.assertEqual(self.plugin._clean_text("test"), "test")

    def test_safe_limit_with_boolean(self):
        """Test _safe_limit returns default for boolean inputs."""
        self.assertEqual(self.plugin._safe_limit(True, default=10), 10)
        self.assertEqual(self.plugin._safe_limit(False, default=10), 10)

    def test_safe_limit_with_valid_integer(self):
        """Test _safe_limit works correctly with valid integer inputs."""
        self.assertEqual(self.plugin._safe_limit(5), 5)
        self.assertEqual(self.plugin._safe_limit(1), 1)
        self.assertEqual(self.plugin._safe_limit(300), 300)

    def test_safe_limit_with_invalid_integer(self):
        """Test _safe_limit returns default for invalid integer inputs."""
        self.assertEqual(self.plugin._safe_limit("invalid", default=10), 10)
        self.assertEqual(self.plugin._safe_limit(None, default=10), 10)
        self.assertEqual(self.plugin._safe_limit([], default=10), 10)

    def test_safe_limit_with_out_of_bounds(self):
        """Test _safe_limit clamps values to valid bounds."""
        self.assertEqual(self.plugin._safe_limit(0), 1)
        self.assertEqual(self.plugin._safe_limit(301), 300)
        self.assertEqual(self.plugin._safe_limit(-10), 1)

    def test_safe_paper_id_with_boolean(self):
        """Test _safe_paper_id returns empty string for boolean inputs via _clean_text."""
        self.assertEqual(self.plugin._safe_paper_id(True), "")
        self.assertEqual(self.plugin._safe_paper_id(False), "")

    def test_execute_action_with_boolean_author(self):
        """Test execute_action fails correctly with boolean author."""
        # This should now return "Missing required field: author" instead of searching for "False"
        result = self.plugin.execute_action("search_author", {"author": False})
        self.assertEqual(result, "Missing required field: author")

    def test_execute_action_with_boolean_limit(self):
        """Test execute_action uses default limit with boolean limit."""
        # This should now use default limit (5) instead of 1
        result = self.plugin.execute_action("search_author", {"author": "test", "limit": False})
        self.assertEqual(result, "Searching for papers by author: test with limit: 5")

    def test_execute_action_with_valid_author_and_limit(self):
        """Test execute_action works correctly with valid inputs."""
        result = self.plugin.execute_action("search_author", {"author": "test", "limit": 10})
        self.assertEqual(result, "Searching for papers by author: test with limit: 10")


if __name__ == "__main__":
    unittest.main()
</content>