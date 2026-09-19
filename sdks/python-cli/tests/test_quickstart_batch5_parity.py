"""Test suite verifying structural and semantic parity of Batch 5 CLI quickstart guides."""

import re
import unittest
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

LANGUAGES = ["bn", "ur", "ta", "mr", "gu", "kn", "ml", "or"]


def parse_guide(path: Path):
    content = path.read_text(encoding="utf-8")
    h2s = re.findall(r"^## [^\n]+", content, re.MULTILINE)
    code_fences = re.findall(r"^\s*```[a-z]*", content, re.MULTILINE)
    return {
        "h2_count": len(h2s),
        "code_fences": len(code_fences),
        "content": content,
    }


class QuickstartBatch5ParityTest(unittest.TestCase):
    def test_all_guides_exist_and_conform(self):
        for lang in LANGUAGES:
            guide_path = EXAMPLES_DIR / f"quickstart.{lang}.md"
            self.assertTrue(guide_path.exists(), f"Guide missing: {guide_path}")
            data = parse_guide(guide_path)
            with self.subTest(lang=lang):
                self.assertEqual(data["h2_count"], 5, f"{lang} expected 5 H2 headers, got {data['h2_count']}")
                self.assertEqual(data["code_fences"], 20, f"{lang} expected 10 code blocks (20 fences), got {data['code_fences']}")

                content = data["content"]
                # Essential command invariants
                self.assertIn("pipx install omi-cli", content)
                self.assertIn("omi --help", content)
                self.assertIn("python -m pip install omi-cli", content)
                self.assertIn("omi auth login", content)
                self.assertIn("omi auth login --browser", content)
                self.assertIn("omi auth status", content)
                self.assertIn("omi auth whoami", content)
                self.assertIn("omi memory list --limit 5", content)
                self.assertIn("omi conversation list --limit 5", content)
                self.assertIn("omi action-item list --open", content)
                self.assertIn("omi goal list", content)
                self.assertIn("omi memory list --help", content)
                self.assertIn("omi action-item list --help", content)
                self.assertIn("omi --json memory list --limit 25 --offset 0", content)
                self.assertIn("omi --json memory list --limit 25 --offset 25", content)
                self.assertIn("omi auth logout", content)
                self.assertIn("[../README.md](../README.md)", content)


if __name__ == "__main__":
    unittest.main()
