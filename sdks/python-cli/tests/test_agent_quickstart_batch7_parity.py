"""Test suite verifying structural and semantic parity of localized agent quickstart guides (Batch 7)."""

import re
import unittest
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

LANGUAGES = ["ko", "it", "tr", "id", "nl", "pl", "uk", "ar", "he"]


def parse_agent_guide(path: Path):
    content = path.read_text(encoding="utf-8")
    h2s = re.findall(r"^## [^\n]+", content, re.MULTILINE)
    h3s = re.findall(r"^### [^\n]+", content, re.MULTILINE)
    code_fences = re.findall(r"^\s*```[a-z]*", content, re.MULTILINE)
    return {
        "h2_count": len(h2s),
        "h3_count": len(h3s),
        "code_fences": len(code_fences),
        "content": content,
    }


class AgentQuickstartBatch7ParityTest(unittest.TestCase):
    def test_all_guides_exist_and_conform(self):
        for lang in LANGUAGES:
            guide_path = EXAMPLES_DIR / f"agent_quickstart.{lang}.md"
            self.assertTrue(guide_path.exists(), f"Agent guide missing: {guide_path}")
            data = parse_agent_guide(guide_path)
            with self.subTest(lang=lang):
                self.assertEqual(data["h2_count"], 7, f"{lang} expected 7 H2 headers, got {data['h2_count']}")
                self.assertEqual(data["h3_count"], 5, f"{lang} expected 5 H3 headers, got {data['h3_count']}")
                self.assertEqual(
                    data["code_fences"],
                    22,
                    f"{lang} expected 11 code blocks (22 fences), got {data['code_fences']}",
                )

                content = data["content"]
                # Must be LF only
                self.assertNotIn("\r\n", content, f"{lang} contains CRLF line endings")

                # CLI command invariants
                self.assertIn("omi auth login", content)
                self.assertIn("export OMI_API_KEY=omi_dev_...", content)
                self.assertIn("omi memory list --json --limit 50 | jq '.[] | {id, content, category}'", content)
                self.assertIn('omi memory create --json "User prefers dark mode" --category lifestyle', content)
                self.assertIn("omi action-item list --json --open", content)
                self.assertIn("omi action-item complete --json a1b2c3d4", content)
                self.assertIn("omi local configure --url http://127.0.0.1:47778 --token ...", content)
                self.assertIn("export OMI_LOCAL_API_URL=http://127.0.0.1:47778", content)
                self.assertIn("export OMI_LOCAL_TOKEN=...", content)
                self.assertIn("omi --json local status", content)
                self.assertIn("omi --json local tools", content)
                self.assertIn("omi --json local call search_screen_history --args-json '{\"query\":\"pricing page\",\"days\":7}'", content)
                self.assertIn('omi --json local search-screen "pricing page" --days 7 --app Safari', content)
                self.assertIn("omi --json local screenshot 123 --output /tmp/omi-shot.jpg", content)
                self.assertIn('omi --json local sql "SELECT COUNT(*) AS screenshots FROM screenshots"', content)
                self.assertIn('omi --json local task search "taxes" --include-completed', content)
                self.assertIn("omi --json local task complete task_123", content)
                self.assertIn("omi --json local task delete task_123 --yes", content)
                self.assertIn("cat meeting_notes.md | omi conversation create --text - --text-source other_text", content)

                # Python code invariants
                self.assertIn("def omi(*args: str) -> Any:", content)
                self.assertIn("result.returncode != 0", content)
                self.assertIn("result.returncode == 4", content)
                self.assertIn('timedelta(days=30)', content)

                # Exit codes and rate limits
                for code in ["0", "1", "2", "3", "4", "5"]:
                    self.assertIn(f"`{code}`", content)
                self.assertIn("120", content)
                self.assertIn("25", content)
                self.assertIn("15", content)


if __name__ == "__main__":
    unittest.main()
