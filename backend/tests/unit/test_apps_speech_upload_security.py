"""Unit tests for path traversal prevention in apps/speech_profile uploads.

Mirrors backend/tests/unit/test_file_upload_security.py for the basename-sanitize
pattern used in:
  - backend/routers/apps.py (_temp/apps/{uuid}_{safe_suffix})
  - backend/routers/speech_profile.py (_temp/{uid}/{uuid}_{safe_suffix})
"""

import re
import unittest
import uuid
from pathlib import Path


def apps_safe_filename_logic(filename):
    """Extract the security-relevant logic from apps upload endpoints."""
    safe_suffix = Path(filename).name if filename else "upload"
    file_path = f"_temp/apps/{uuid.uuid4().hex}_{safe_suffix}"
    return safe_suffix, file_path


def speech_profile_safe_filename_logic(filename, uid="test-uid"):
    """Extract the security-relevant logic from speech_profile upload endpoint."""
    safe_suffix = Path(filename).name if filename else "upload"
    file_path = f"_temp/{uid}/{uuid.uuid4().hex}_{safe_suffix}"
    return safe_suffix, file_path


_HEX32 = re.compile(r"^[0-9a-f]{32}_")


class TestAppsUploadPathTraversal(unittest.TestCase):
    def test_none_filename_uses_default(self):
        safe_suffix, file_path = apps_safe_filename_logic(None)
        self.assertEqual(safe_suffix, "upload")
        self.assertTrue(file_path.startswith("_temp/apps/"))
        self.assertTrue(file_path.endswith("_upload"))

    def test_normal_filename_unchanged(self):
        safe_suffix, file_path = apps_safe_filename_logic("logo.png")
        self.assertEqual(safe_suffix, "logo.png")
        self.assertTrue(file_path.endswith("_logo.png"))

    def test_unix_path_traversal_stripped(self):
        safe_suffix, file_path = apps_safe_filename_logic("../../etc/passwd")
        self.assertEqual(safe_suffix, "passwd")
        self.assertNotIn("..", file_path)
        self.assertTrue(file_path.startswith("_temp/apps/"))

    def test_absolute_path_stripped(self):
        safe_suffix, _ = apps_safe_filename_logic("/etc/shadow")
        self.assertEqual(safe_suffix, "shadow")

    def test_nested_traversal_stripped(self):
        safe_suffix, _ = apps_safe_filename_logic("../../../tmp/../../../etc/hosts")
        self.assertEqual(safe_suffix, "hosts")

    def test_empty_string_filename(self):
        safe_suffix, file_path = apps_safe_filename_logic("")
        self.assertEqual(safe_suffix, "upload")
        self.assertTrue(file_path.endswith("_upload"))

    def test_uuid_prefix_present(self):
        _, file_path = apps_safe_filename_logic("a.png")
        name = Path(file_path).name
        self.assertRegex(name, _HEX32)


class TestSpeechProfileUploadPathTraversal(unittest.TestCase):
    def test_none_filename_uses_default(self):
        safe_suffix, file_path = speech_profile_safe_filename_logic(None, uid="u1")
        self.assertEqual(safe_suffix, "upload")
        self.assertTrue(file_path.startswith("_temp/u1/"))
        self.assertTrue(file_path.endswith("_upload"))

    def test_keeps_uid_directory(self):
        _, file_path = speech_profile_safe_filename_logic("sample.wav", uid="abc123")
        self.assertTrue(file_path.startswith("_temp/abc123/"))

    def test_unix_path_traversal_stripped(self):
        safe_suffix, file_path = speech_profile_safe_filename_logic("../../etc/passwd", uid="u1")
        self.assertEqual(safe_suffix, "passwd")
        self.assertNotIn("..", file_path)

    def test_absolute_path_stripped(self):
        safe_suffix, file_path = speech_profile_safe_filename_logic("/tmp/evil.wav", uid="u1")
        self.assertEqual(safe_suffix, "evil.wav")
        self.assertTrue(file_path.startswith("_temp/u1/"))
        self.assertNotIn("/tmp/", file_path)

    def test_uuid_prefix_present(self):
        _, file_path = speech_profile_safe_filename_logic("sample.wav", uid="u1")
        name = Path(file_path).name
        self.assertRegex(name, _HEX32)


if __name__ == '__main__':
    unittest.main()
