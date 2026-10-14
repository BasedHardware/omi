import unittest
from pydantic import ValidationError

from models.dev_api_key import DevApiKeyCreate
from models.mcp_api_key import McpApiKeyCreate


class TestDevApiKeyCreateValidation(unittest.TestCase):
    def test_valid_name(self):
        key = DevApiKeyCreate(name="My CLI Key")
        self.assertEqual(key.name, "My CLI Key")
        self.assertIsNone(key.scopes)

    def test_valid_name_with_scopes(self):
        key = DevApiKeyCreate(name="Scoped Key", scopes=["memories:read"])
        self.assertEqual(key.name, "Scoped Key")
        self.assertEqual(key.scopes, ["memories:read"])

    def test_strips_surrounding_whitespace(self):
        key = DevApiKeyCreate(name="  Trimmed Key  ")
        self.assertEqual(key.name, "Trimmed Key")

    def test_rejects_empty_string(self):
        with self.assertRaises(ValidationError):
            DevApiKeyCreate(name="")

    def test_rejects_whitespace_only(self):
        for blank in ["   ", "\t", "\n\r  \t"]:
            with self.subTest(blank=blank):
                with self.assertRaises(ValidationError):
                    DevApiKeyCreate(name=blank)

    def test_maximum_length_100(self):
        name = "k" * 100
        key = DevApiKeyCreate(name=name)
        self.assertEqual(key.name, name)

    def test_rejects_over_100_characters(self):
        with self.assertRaises(ValidationError):
            DevApiKeyCreate(name="k" * 101)


class TestMcpApiKeyCreateValidation(unittest.TestCase):
    def test_valid_name(self):
        key = McpApiKeyCreate(name="My MCP Key")
        self.assertEqual(key.name, "My MCP Key")
        self.assertIsNone(key.scopes)

    def test_valid_name_with_scopes(self):
        key = McpApiKeyCreate(name="MCP Key", scopes=["people.cleanup"])
        self.assertEqual(key.name, "MCP Key")
        self.assertEqual(key.scopes, ["people.cleanup"])

    def test_strips_surrounding_whitespace(self):
        key = McpApiKeyCreate(name="  MCP Trimmed  ")
        self.assertEqual(key.name, "MCP Trimmed")

    def test_rejects_empty_string(self):
        with self.assertRaises(ValidationError):
            McpApiKeyCreate(name="")

    def test_rejects_whitespace_only(self):
        for blank in ["   ", "\t", "\n\r  \t"]:
            with self.subTest(blank=blank):
                with self.assertRaises(ValidationError):
                    McpApiKeyCreate(name=blank)

    def test_maximum_length_100(self):
        name = "m" * 100
        key = McpApiKeyCreate(name=name)
        self.assertEqual(key.name, name)

    def test_rejects_over_100_characters(self):
        with self.assertRaises(ValidationError):
            McpApiKeyCreate(name="m" * 101)


if __name__ == "__main__":
    unittest.main()
