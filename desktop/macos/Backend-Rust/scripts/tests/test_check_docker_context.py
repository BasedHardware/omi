from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIRECTORY))

import check_docker_context  # noqa: E402


class DockerContextContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.context = Path(self.temporary_directory.name)
        self._write(
            "src/routes/llm_stub.rs",
            'const DEFAULT: &str = include_str!("../../fixtures/llm/default.sse");\n',
        )
        self._write("fixtures/llm/default.sse", "data: fixture\n")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _write(self, relative_path: str, contents: str) -> None:
        path = self.context / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def _validate(self, dockerfile: str) -> list[str]:
        self._write("Dockerfile", dockerfile)
        return check_docker_context.validate_context(self.context, self.context / "Dockerfile")

    def test_accepts_directory_copy_for_compile_time_asset(self) -> None:
        errors = self._validate("COPY src ./src\nCOPY fixtures ./fixtures\n")

        self.assertEqual(errors, [])

    def test_rejects_asset_not_copied_into_build_stage(self) -> None:
        errors = self._validate("COPY src ./src\n")

        self.assertEqual(len(errors), 1)
        self.assertIn("fixtures/llm/default.sse", errors[0])
        self.assertIn("no local COPY/ADD", errors[0])

    def test_rejects_asset_excluded_by_dockerignore(self) -> None:
        self._write(".dockerignore", "fixtures/\n")
        errors = self._validate("COPY src ./src\nCOPY fixtures ./fixtures\n")

        self.assertEqual(len(errors), 1)
        self.assertIn("excluded by .dockerignore", errors[0])

    def test_does_not_treat_stage_copy_as_local_context_copy(self) -> None:
        errors = self._validate("COPY src ./src\nCOPY --from=builder /generated ./fixtures\n")

        self.assertEqual(len(errors), 1)
        self.assertIn("no local COPY/ADD", errors[0])

    def test_accepts_json_copy_syntax(self) -> None:
        errors = self._validate('COPY ["src", "./src"]\nCOPY ["fixtures", "./fixtures"]\n')

        self.assertEqual(errors, [])

    def test_accepts_source_root_inside_a_workspace_context(self) -> None:
        source_root = self.context / "macos/Backend-Rust/src"
        source = source_root / "routes/llm_stub.rs"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text('const DEFAULT: &str = include_str!("../../fixtures/llm/default.sse");\n', encoding="utf-8")
        self._write("macos/Backend-Rust/fixtures/llm/default.sse", "data: fixture\n")
        self._write(
            "Dockerfile",
            "COPY macos/Backend-Rust/src ./macos/Backend-Rust/src\n"
            "COPY macos/Backend-Rust/fixtures ./macos/Backend-Rust/fixtures\n",
        )

        errors = check_docker_context.validate_context(
            self.context,
            self.context / "Dockerfile",
            source_root,
        )

        self.assertEqual(errors, [])
