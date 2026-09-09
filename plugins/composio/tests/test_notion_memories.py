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
