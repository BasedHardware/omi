import importlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


class NotionMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.scratch.cleanup)
        environment = patch.dict(os.environ, {
            "DB_PATH": str(Path(cls.scratch.name) / "memories.db"),
            "OMI_APP_ID": "test-app",
            "OMI_API_KEY": "test-key",
        })
        environment.start()
        cls.addClassCleanup(environment.stop)
        cls.notion = importlib.import_module("src.notion")

    def test_first_person_keywords_ignore_case(self):
        for text, expected in (
            ("I like reading science fiction books on weekends", "User likes reading science fiction books on weekends"),
            ("i like reading science fiction books on weekends", "User likes reading science fiction books on weekends"),
            ("I LIKE reading science fiction books on weekends", "User likes reading science fiction books on weekends"),
            ("i'M learning to play the piano with a teacher", "User is learning to play the piano with a teacher"),
            ("i prefer reading books by Ursula Le Guin", "User prefers reading books by Ursula Le Guin"),
            ("my favorite author has always been Ursula Le Guin", "User's favorite author has always been Ursula Le Guin"),
        ):
            with self.subTest(text=text):
                self.assertTrue(self.notion.contains_personal_info(text))
                self.assertEqual(self.notion.extract_memories_from_text(text), [expected])

    def test_replacements_match_complete_words(self):
        for text, expected in (
            ("I liked reading science fiction books as a child", "User note: I liked reading science fiction books as a child"),
            ("I amassing books for the community library", "User note: I amassing books for the community library"),
            ("I LIKE reading, though I liked other genres before", "User likes reading, though I liked other genres before"),
            ("my friends enjoy reading science fiction together", "User's friends enjoy reading science fiction together"),
            ("MY FRIEND enjoys reading science fiction with me", "User's friend enjoys reading science fiction with me"),
            ("my friendship with Alex began many years ago", "User note: my friendship with Alex began many years ago"),
            ("Miami likes warm weather throughout the year", "User note: Miami likes warm weather throughout the year"),
            ("I don't like crowds at the library on weekends", "User doesn't like crowds at the library on weekends"),
        ):
            with self.subTest(text=text):
                self.assertEqual(self.notion.format_as_memory(text), expected)

    def test_nonpersonal_and_short_content_remain_excluded(self):
        self.assertEqual(self.notion.extract_memories_from_text(
            "The library opens every morning at nine o'clock"
        ), [])
        self.assertEqual(self.notion.extract_memories_from_text("I like books"), [])

    def test_extract_route_stores_first_person_memory(self):
        app = FastAPI()
        app.include_router(self.notion.router)
        response = Mock()
        response.json.return_value = {"results": [{
            "type": "paragraph",
            "paragraph": {"rich_text": [{
                "plain_text": "i LIKE reading science fiction books on weekends."
            }]},
        }]}
        with (
            patch.object(self.notion, "get_notion_credentials", return_value={
                "notion_access_token": "test-token"
            }),
            patch.object(self.notion.requests, "get", return_value=response),
            patch.object(self.notion, "store_memory", return_value="memory-1") as store,
            TestClient(app) as client,
        ):
            result = client.post(
                "/api/notion/extract-memories?uid=test-user",
                data={"block_type": "page", "block_id": "test-page"},
            )
        self.assertEqual(result.status_code, 200)
        expected = "User likes reading science fiction books on weekends"
        self.assertEqual(result.json()["memories"], [expected])
        self.assertEqual(result.json()["memory_ids"], ["memory-1"])
        store.assert_called_once_with("test-user", "notion_page", expected)


if __name__ == "__main__":
    unittest.main()
