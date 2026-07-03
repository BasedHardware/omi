"""
Tests for the per-file local-file import guard.

Regression goal: the desktop onboarding scan historically emitted one memory
per indexed file (up to 2800 "The user's local projects include <path>"
entries per scan). Those buried users' real memories and were bulk-purged in
July 2026. `is_per_file_local_import_tags` is the server-side backstop that
keeps clients released before the fix from recreating the spam, while letting
the aggregate local_files facts (profile/project/technology) through.
"""

from utils.memory.import_write_guard import is_per_file_local_import_tags


class TestIsPerFileLocalImportTags:
    def test_per_file_folder_variants_are_dropped(self):
        for folder in ("projects", "documents", "downloads"):
            assert is_per_file_local_import_tags(["local_files", "onboarding", folder, "py"]) is True

    def test_recent_file_variant_is_dropped(self):
        assert is_per_file_local_import_tags(["local_files", "onboarding", "recent_file"]) is True

    def test_aggregate_local_file_facts_pass(self):
        for aggregate in ("profile", "project", "technology"):
            assert is_per_file_local_import_tags(["local_files", "onboarding", aggregate]) is False

    def test_requires_both_import_markers(self):
        # "projects" alone (e.g. a conversation memory about the user's
        # projects) must not be treated as a file-import item.
        assert is_per_file_local_import_tags(["projects", "py"]) is False
        assert is_per_file_local_import_tags(["local_files", "projects"]) is False
        assert is_per_file_local_import_tags(["onboarding", "projects"]) is False

    def test_other_import_sources_pass(self):
        assert is_per_file_local_import_tags(["gmail", "onboarding", "profile"]) is False
        assert is_per_file_local_import_tags(["calendar", "onboarding", "profile"]) is False

    def test_normalization_of_case_and_separators(self):
        assert is_per_file_local_import_tags(["Local_Files", "Onboarding", "Recent-File"]) is True
        assert is_per_file_local_import_tags([" local_files ", "onboarding", "Projects", "PY"]) is True

    def test_non_list_and_empty_inputs_pass(self):
        assert is_per_file_local_import_tags(None) is False
        assert is_per_file_local_import_tags("local_files") is False
        assert is_per_file_local_import_tags([]) is False
        assert is_per_file_local_import_tags([None, 42]) is False
