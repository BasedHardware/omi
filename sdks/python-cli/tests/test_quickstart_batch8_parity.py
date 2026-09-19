import re
import unittest
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
BATCH8_LANGS = ["scn", "br", "fy", "oc", "gn", "ug", "tw", "ban"]

class TestQuickstartBatch8Parity(unittest.TestCase):
    def test_structural_parity(self):
        for lang in BATCH8_LANGS:
            path = EXAMPLES_DIR / f"quickstart.{lang}.md"
            self.assertTrue(path.exists(), f"Missing file {path}")
            content = path.read_text(encoding="utf-8")

            # Check H2 count (exactly 5)
            h2_headers = re.findall(r"^##\s+(.+)$", content, re.MULTILINE)
            self.assertEqual(len(h2_headers), 5, f"Expected 5 H2 headers in {lang}, found {len(h2_headers)}: {h2_headers}")

            # Check code blocks count (exactly 10)
            code_blocks = re.findall(r"^```sh\s*$", content, re.MULTILINE)
            self.assertEqual(len(code_blocks), 10, f"Expected 10 ```sh blocks in {lang}, found {len(code_blocks)}")

            # Check canonical warning callout
            self.assertIn("omi-cli", content)
            self.assertIn("`omi`", content)

            # Check relative link to README
            self.assertIn("[../README.md](../README.md)", content)

if __name__ == "__main__":
    unittest.main()
