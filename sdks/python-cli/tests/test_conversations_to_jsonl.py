import json
import tempfile
import unittest
from pathlib import Path
import sys

# Add parent directories to import path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from conversations_to_jsonl import (
    convert,
    format_record,
    parse_datetime,
    read_conversations,
)


class TestConversationsToJsonl(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.sample_convs = [
            {
                "id": "conv_1",
                "structured": {
                    "title": "Quarterly Architecture Review",
                    "category": "work",
                    "overview": "Discussed migration to distributed micro-services.",
                    "action_items": ["Finalize spec", "Draft migration plan"],
                },
                "transcript": "Alice: Welcome everyone. Bob: Let us discuss architecture.",
                "source": "friend",
                "started_at": "2026-09-20T14:00:00Z",
                "created_at": "2026-09-20T15:00:00Z",
                "updated_at": "2026-09-20T15:30:00Z",
            },
            {
                "id": "conv_2",
                "structured": {
                    "title": "Weekend Hiking Planning",
                    "category": "personal",
                    "overview": "Selected trails in Banff.",
                    "action_items": [],
                },
                "transcript": "Alice: Where should we hike? Bob: Lake Louise is great.",
                "source": "omi",
                "started_at": "2026-09-21T10:00:00Z",
                "created_at": "2026-09-21T10:30:00Z",
                "updated_at": "2026-09-21T10:30:00Z",
            },
        ]
        self.input_file = self.dir_path / "conversations.json"
        self.input_file.write_text(json.dumps(self.sample_convs), encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_datetime(self):
        self.assertEqual(parse_datetime("2026-09-20T14:00:00Z"), "2026-09-20T14:00:00+00:00")
        self.assertIsNone(parse_datetime(None))
        self.assertEqual(parse_datetime("raw-string"), "raw-string")

    def test_convert_standard_mode(self):
        out_file = self.dir_path / "standard.jsonl"
        count = convert([str(self.input_file)], str(out_file), mode="standard")
        self.assertEqual(count, 2)

        lines = [json.loads(line) for line in out_file.read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["id"], "conv_1")
        self.assertEqual(lines[0]["title"], "Quarterly Architecture Review")
        self.assertEqual(lines[0]["category"], "work")
        self.assertIn("Finalize spec", lines[0]["action_items"])
        self.assertIn("Bob: Let us discuss architecture", lines[0]["transcript"])

    def test_convert_fine_tune_mode(self):
        out_file = self.dir_path / "fine_tune.jsonl"
        count = convert([str(self.input_file)], str(out_file), mode="fine_tune")
        self.assertEqual(count, 2)

        lines = [json.loads(line) for line in out_file.read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(lines[0]["conversation_id"], "conv_1")
        messages = lines[0]["messages"]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertIn("Quarterly Architecture Review", messages[0]["content"])
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertIn("Bob: Let us discuss architecture", messages[1]["content"])

    def test_convert_rag_mode(self):
        out_file = self.dir_path / "rag.jsonl"
        count = convert([str(self.input_file)], str(out_file), mode="rag")
        self.assertEqual(count, 2)

        lines = [json.loads(line) for line in out_file.read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(lines[0]["id"], "conv_1")
        self.assertIn("Title: Quarterly Architecture Review", lines[0]["text"])
        self.assertIn("Transcript:\nAlice: Welcome everyone", lines[0]["text"])
        self.assertEqual(lines[0]["metadata"]["category"], "work")
        self.assertEqual(lines[0]["metadata"]["source"], "friend")

    def test_category_filter(self):
        out_file = self.dir_path / "work_only.jsonl"
        count = convert([str(self.input_file)], str(out_file), category_filter="work")
        self.assertEqual(count, 1)

        line = json.loads(out_file.read_text(encoding="utf-8").strip())
        self.assertEqual(line["id"], "conv_1")
        self.assertEqual(line["title"], "Quarterly Architecture Review")

    def test_deduplication(self):
        dup_items = self.sample_convs + [self.sample_convs[0]]
        dup_file = self.dir_path / "dups.json"
        dup_file.write_text(json.dumps(dup_items), encoding="utf-8")

        out_file = self.dir_path / "deduped.jsonl"
        count = convert([str(dup_file)], str(out_file), dedupe=True)
        self.assertEqual(count, 2)

        out_raw = self.dir_path / "raw.jsonl"
        count_raw = convert([str(dup_file)], str(out_raw), dedupe=False)
        self.assertEqual(count_raw, 3)

    def test_unwrapped_keys(self):
        wrapped = {"conversations": self.sample_convs}
        wrap_file = self.dir_path / "wrapped.json"
        wrap_file.write_text(json.dumps(wrapped), encoding="utf-8")

        items = read_conversations([str(wrap_file)])
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["id"], "conv_1")

    def test_path_traversal_safety(self):
        with self.assertRaises(ValueError):
            convert([str(self.input_file)], str(self.dir_path / "../escape.jsonl"))

    def test_missing_id_raises(self):
        bad_items = [{"title": "No ID conv"}]
        bad_file = self.dir_path / "bad.json"
        bad_file.write_text(json.dumps(bad_items), encoding="utf-8")

        with self.assertRaises(ValueError):
            convert([str(bad_file)], str(self.dir_path / "out.jsonl"))


if __name__ == "__main__":
    unittest.main()
