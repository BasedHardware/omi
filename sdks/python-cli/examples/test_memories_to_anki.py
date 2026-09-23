"""
Hermetic unit tests for memories_to_anki.py (Omi memories to Anki TSV flashcard converter).
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Add parent directory to sys.path
SCRIPT_PATH = Path(__file__).parent / "memories_to_anki.py"


class TestMemoriesToAnki(unittest.TestCase):
    def setUp(self):
        self.sample_memories = [
            {
                "id": "mem_01",
                "content": "Python's functools.lru_cache memoizes function calls based on argument hashes.",
                "category": "learnings",
                "tags": ["python", "optimization"],
                "created_at": "2026-09-20T10:15:30Z",
                "visibility": "public",
            },
            {
                "id": "mem_02",
                "content": "Deploying the staging cluster requires setting KUBECONFIG to /etc/k8s/staging.conf.",
                "category": "work",
                "tags": ["k8s", "devops"],
                "created_at": "2026-09-21T14:20:00Z",
                "visibility": "public",
            },
            {
                "id": "mem_03",
                "content": "Personal secret access token note for test environment.",
                "category": "core",
                "tags": ["credentials"],
                "created_at": "2026-09-22T08:00:00Z",
                "visibility": "private",
            },
            {
                "id": "mem_04",
                "content": "Multiline fact:\nLine 1 summary.\nLine 2 details with \ttab indent and <b>HTML</b> markup.",
                "category": "skills",
                "tags": ["notes"],
                "created_at": "2026-09-22T09:00:00Z",
                "visibility": "public",
            },
        ]

    def test_json_list_conversion(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".json") as json_in:
            json.dump(self.sample_memories, json_in)
            json_in_path = json_in.name

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".tsv") as tsv_out:
            tsv_out_path = tsv_out.name

        try:
            cmd = [
                sys.executable,
                str(SCRIPT_PATH),
                json_in_path,
                "--output",
                tsv_out_path,
                "--deck",
                "Omi::Knowledge",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, f"Error: {result.stderr}")

            content = Path(tsv_out_path).read_text(encoding="utf-8")
            lines = content.strip().split("\n")

            # Check header directives
            self.assertIn("#separator:tab", lines)
            self.assertIn("#html:true", lines)
            self.assertIn("#deck:Omi::Knowledge", lines)
            self.assertIn("#tags column:3", lines)

            # Check cards count (4 cards)
            card_lines = [line for line in lines if not line.startswith("#")]
            self.assertEqual(len(card_lines), 4)

            # Check multiline formatting (<br> and no raw tabs)
            multiline_card = card_lines[3]
            self.assertIn("<br>", multiline_card)
            self.assertNotIn("\t\t", multiline_card)  # tabs are sanitized in content
            self.assertIn("&lt;b&gt;HTML&lt;/b&gt;", multiline_card)  # html markup is escaped
        finally:
            if os.path.exists(json_in_path):
                os.remove(json_in_path)
            if os.path.exists(tsv_out_path):
                os.remove(tsv_out_path)

    def test_dict_wrapper_and_category_filter(self):
        wrapper = {"memories": self.sample_memories}
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".json") as json_in:
            json.dump(wrapper, json_in)
            json_in_path = json_in.name

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".tsv") as tsv_out:
            tsv_out_path = tsv_out.name

        try:
            cmd = [
                sys.executable,
                str(SCRIPT_PATH),
                json_in_path,
                "--output",
                tsv_out_path,
                "--category",
                "learnings",
                "--template",
                "prompt",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0)

            content = Path(tsv_out_path).read_text(encoding="utf-8")
            card_lines = [line for line in content.strip().split("\n") if not line.startswith("#")]
            self.assertEqual(len(card_lines), 1)
            self.assertIn("What key insight was recorded", card_lines[0])
            self.assertIn("lru_cache", card_lines[0])
        finally:
            if os.path.exists(json_in_path):
                os.remove(json_in_path)
            if os.path.exists(tsv_out_path):
                os.remove(tsv_out_path)

    def test_exclude_private_and_custom_tags(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".json") as json_in:
            json.dump(self.sample_memories, json_in)
            json_in_path = json_in.name

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".tsv") as tsv_out:
            tsv_out_path = tsv_out.name

        try:
            cmd = [
                sys.executable,
                str(SCRIPT_PATH),
                json_in_path,
                "--output",
                tsv_out_path,
                "--exclude-private",
                "--tag",
                "custom_deck_tag",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0)

            content = Path(tsv_out_path).read_text(encoding="utf-8")
            card_lines = [line for line in content.strip().split("\n") if not line.startswith("#")]
            # 4 minus 1 private = 3 cards
            self.assertEqual(len(card_lines), 3)
            for card in card_lines:
                self.assertIn("custom_deck_tag", card)
                self.assertNotIn("credentials", card)
        finally:
            if os.path.exists(json_in_path):
                os.remove(json_in_path)
            if os.path.exists(tsv_out_path):
                os.remove(tsv_out_path)

    def test_stdin_pipe(self):
        json_bytes = json.dumps(self.sample_memories).encode("utf-8")
        cmd = [sys.executable, str(SCRIPT_PATH), "-"]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate(input=json_bytes)
        self.assertEqual(proc.returncode, 0)
        output_str = stdout.decode("utf-8")
        self.assertIn("#separator:tab", output_str)
        self.assertIn("functools.lru_cache", output_str)


if __name__ == "__main__":
    unittest.main()
