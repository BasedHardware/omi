import fnmatch
import unittest
from pathlib import Path


def is_path_ignored(relative_path: str, dockerignore_lines: list[str]) -> bool:
    """Simulate Dockerignore path matching according to Go filepath.Match rules.

    In Dockerignore / gitignore:
    - If a pattern has a slash at the start or in the middle (e.g. '/app/', '.github/workflows/'),
      it is anchored to the root of the build context.
    - If a pattern is a single name with no internal slash (e.g. '__pycache__/', '*.env'),
      it matches at any directory level.
    """
    clean_path = relative_path.strip("/")
    path_parts = clean_path.split("/")
    ignored = False

    for raw_line in dockerignore_lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        negated = line.startswith("!")
        pattern = line[1:].strip() if negated else line
        is_dir_only = pattern.endswith("/")
        clean_pattern = pattern.strip("/")

        # If pattern has '/' in middle or was leading-slash, it's root-anchored
        has_internal_slash = "/" in clean_pattern
        anchored = pattern.startswith("/") or has_internal_slash

        matched = False
        if anchored:
            if is_dir_only:
                pattern_parts = clean_pattern.split("/")
                if len(path_parts) >= len(pattern_parts):
                    matched = all(fnmatch.fnmatch(path_parts[i], pattern_parts[i]) for i in range(len(pattern_parts)))
            else:
                matched = fnmatch.fnmatch(clean_path, clean_pattern)
        else:
            if is_dir_only:
                matched = any(fnmatch.fnmatch(part, clean_pattern) for part in path_parts[:-1])
            else:
                matched = any(fnmatch.fnmatch(part, clean_pattern) for part in path_parts) or fnmatch.fnmatch(
                    clean_path, clean_pattern
                )

        if matched:
            ignored = not negated

    return ignored


class TestDockerignore(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[3]
        self.root_dockerignore = self.repo_root / ".dockerignore"
        self.backend_dockerignore = self.repo_root / "backend" / ".dockerignore"
        self.root_lines = self.root_dockerignore.read_text(encoding="utf-8").splitlines()

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

    def test_root_dockerignore_anchors_platform_subtrees(self):
        # Must be anchored with '/' to avoid over-matching inside backend/
        content = self.root_dockerignore.read_text(encoding="utf-8")
        self.assertIn("/docs/", content)
        self.assertIn("/contracts/", content)
        self.assertIn("/app/", content)
        self.assertIn("/desktop/", content)

    def test_build_critical_paths_are_not_excluded(self):
        # 1. web/ builds with context '.' in gcp_app.yml, gcp_frontend.yml, gcp_personas.yml
        self.assertFalse(is_path_ignored("web/app/Dockerfile", self.root_lines))
        self.assertFalse(is_path_ignored("web/app/package.json", self.root_lines))
        self.assertFalse(is_path_ignored("web/frontend/Dockerfile", self.root_lines))
        self.assertFalse(is_path_ignored("web/personas-open-source/Dockerfile", self.root_lines))

        # 2. plugins/ builds with context '.' in gcp_plugins.yml
        self.assertFalse(is_path_ignored("plugins/Dockerfile", self.root_lines))
        self.assertFalse(is_path_ignored("plugins/requirements.txt", self.root_lines))
        self.assertFalse(is_path_ignored("plugins/omi-plugin-sdk/pyproject.toml", self.root_lines))

        # 3. backend/docs/ and backend/testing/contracts/ must NOT be stripped by anchored /docs/ or /contracts/
        self.assertFalse(is_path_ignored("backend/docs/openapi.json", self.root_lines))
        self.assertFalse(is_path_ignored("backend/testing/contracts/parity.py", self.root_lines))

        # 4. Audio release fixtures must not be stripped
        self.assertFalse(is_path_ignored("backend/testing/release_fixtures/parakeet-canary-pt.wav", self.root_lines))
        self.assertFalse(
            is_path_ignored("backend/testing/release_fixtures/transcription-release-probe.wav", self.root_lines)
        )

        # 5. Build required manifest script
        self.assertFalse(is_path_ignored(".github/scripts/desktop_release_manifest.py", self.root_lines))

    def test_backend_dockerignore_exists_and_protects_credentials(self):
        self.assertTrue(self.backend_dockerignore.is_file(), "backend/.dockerignore must exist")
        content = self.backend_dockerignore.read_text(encoding="utf-8")
        self.assertIn("google-credentials.json", content)
        self.assertIn("*.env", content)
        self.assertIn("__pycache__/", content)


if __name__ == "__main__":
    unittest.main()
