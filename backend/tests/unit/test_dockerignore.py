import unittest
from pathlib import Path


class TestDockerignore(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[3]
        self.root_dockerignore = self.repo_root / ".dockerignore"
        self.backend_dockerignore = self.repo_root / "backend" / ".dockerignore"

    def test_root_dockerignore_exists(self):
        self.assertTrue(self.root_dockerignore.is_file(), "Root .dockerignore must exist")

    def test_root_dockerignore_excludes_sensitive_credentials(self):
        content = self.root_dockerignore.read_text(encoding="utf-8")
        self.assertIn("backend/google-credentials.json", content)
        self.assertIn("*.env", content)
        self.assertIn(".env*", content)

    def test_root_dockerignore_excludes_git_and_caches(self):
        content = self.root_dockerignore.read_text(encoding="utf-8")
        self.assertIn(".git", content)
        self.assertIn("__pycache__/", content)
        self.assertIn(".venv/", content)
        self.assertIn("node_modules/", content)

    def test_root_dockerignore_excludes_non_backend_subtrees(self):
        content = self.root_dockerignore.read_text(encoding="utf-8")
        for subtree in ["app/", "desktop/", "web/", "omi/"]:
            self.assertIn(subtree, content)

    def test_root_dockerignore_preserves_desktop_release_manifest_script(self):
        content = self.root_dockerignore.read_text(encoding="utf-8")
        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
        # Ensure .github as a whole is not unconditionally excluded without preserving scripts
        self.assertNotIn(".github", lines)
        self.assertNotIn(".github/", lines)
        self.assertNotIn(".github/scripts/", lines)

    def test_backend_dockerignore_exists_and_protects_credentials(self):
        self.assertTrue(self.backend_dockerignore.is_file(), "backend/.dockerignore must exist")
        content = self.backend_dockerignore.read_text(encoding="utf-8")
        self.assertIn("google-credentials.json", content)
        self.assertIn("*.env", content)
        self.assertIn("__pycache__/", content)


if __name__ == "__main__":
    unittest.main()
