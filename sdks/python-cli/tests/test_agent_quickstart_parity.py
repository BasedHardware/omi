"""Test suite verifying structural and semantic parity of localized agent quickstart guides."""

import re
import unittest
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
CANONICAL = EXAMPLES_DIR / "agent_quickstart.md"

EXPECTED_H2_COUNT = 7
EXPECTED_H3_COUNT = 5
EXPECTED_CODE_FENCE_COUNT = 11


def parse_guide_structure(path: Path):
    content = path.read_text(encoding="utf-8")
    h2s = re.findall(r"^## [^\n]+", content, re.MULTILINE)
    h3s = re.findall(r"^### [^\n]+", content, re.MULTILINE)
    code_fences = re.findall(r"^\s*```[a-z]*", content, re.MULTILINE)
    return {
        "h2s": len(h2s),
        "h3s": len(h3s),
        "code_fences": len(code_fences),
        "content": content,
    }


class AgentQuickstartParityTest(unittest.TestCase):
    def test_canonical_structure(self):
        struct = parse_guide_structure(CANONICAL)
        self.assertEqual(struct["h2s"], EXPECTED_H2_COUNT)
        self.assertEqual(struct["h3s"], EXPECTED_H3_COUNT)
        self.assertEqual(struct["code_fences"], EXPECTED_CODE_FENCE_COUNT * 2)

    def check_localized_guide(self, path: Path):
        struct = parse_guide_structure(path)
        self.assertEqual(
            struct["h2s"],
            EXPECTED_H2_COUNT,
            f"{path.name} has {struct['h2s']} H2s, expected {EXPECTED_H2_COUNT}",
        )
        self.assertEqual(
            struct["h3s"],
            EXPECTED_H3_COUNT,
            f"{path.name} has {struct['h3s']} H3s, expected {EXPECTED_H3_COUNT}",
        )
        self.assertEqual(
            struct["code_fences"],
            EXPECTED_CODE_FENCE_COUNT * 2,
            f"{path.name} has {struct['code_fences']} fence markers, expected {EXPECTED_CODE_FENCE_COUNT * 2}",
        )

        content = struct["content"]
        # Essential command invariants
        self.assertIn("omi auth login", content)
        self.assertIn("export OMI_API_KEY=", content)
        self.assertIn("omi memory list --json --limit 50", content)
        self.assertIn("omi memory create --json", content)
        self.assertIn("omi conversation list --json", content)
        self.assertIn("omi action-item list --json --open", content)
        self.assertIn("omi action-item complete --json", content)
        self.assertIn("omi local configure", content)
        self.assertIn("omi --json local status", content)
        self.assertIn("omi --json local task complete task_123", content)
        self.assertIn("omi --json local task delete task_123 --yes", content)
        self.assertIn("screenshot_pending", content)
        self.assertIn("def omi(*args: str)", content)
        self.assertIn("meeting_notes.md", content)

    def test_batch4_languages(self):
        languages = ["sv", "cs", "ro", "el", "lv", "sr", "sw"]
        for lang in languages:
            guide_path = EXAMPLES_DIR / f"agent_quickstart.{lang}.md"
            self.assertTrue(guide_path.exists(), f"Missing guide: {guide_path}")
            with self.subTest(lang=lang):
                self.check_localized_guide(guide_path)


if __name__ == "__main__":
    unittest.main()
