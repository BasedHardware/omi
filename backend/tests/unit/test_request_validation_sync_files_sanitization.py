"""Hermetic error sanitization tests for backend/utils/request_validation.py and backend/utils/sync/files.py.

Verifies that:
1. parse_form_json sanitizes Pydantic ValidationError and ValueError without leaking internal schema dumps into HTTPException details.
2. save_files in sync/files.py sanitizes file writing exceptions into a clean HTTPException detail without leaking OS paths or errno traces.
3. AST structural audit confirms no raw {e} or str(e) reflections remain.
"""

import ast
from pathlib import Path
import unittest

REQ_VAL_PATH = Path(__file__).resolve().parents[2] / "utils" / "request_validation.py"
SYNC_FILES_PATH = Path(__file__).resolve().parents[2] / "utils" / "sync" / "files.py"


class RequestValidationSyncFilesSanitizationTests(unittest.TestCase):
    def setUp(self):
        self.req_val_text = REQ_VAL_PATH.read_text(encoding="utf-8")
        self.sync_files_text = SYNC_FILES_PATH.read_text(encoding="utf-8")

    def test_parse_form_json_sanitized(self):
        self.assertIn("detail=f'Invalid {field_name}: malformed JSON or validation failed'", self.req_val_text)
        self.assertNotIn("detail=f'Invalid {field_name}: {e}'", self.req_val_text)

    def test_save_files_sanitized(self):
        self.assertIn('detail=f"Failed to write file {filename}"', self.sync_files_text)
        self.assertNotIn('detail=f"Failed to write file {filename}: {str(e)}"', self.sync_files_text)
        self.assertIn("Failed to write file {filename}: {type(e).__name__}", self.sync_files_text)

    def test_ast_audit_no_exception_leak(self):
        for path in (REQ_VAL_PATH, SYNC_FILES_PATH):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                    func = node.exc.func
                    if (isinstance(func, ast.Name) and func.id == "HTTPException") or (
                        isinstance(func, ast.Attribute) and func.attr == "HTTPException"
                    ):
                        for kw in node.exc.keywords:
                            if kw.arg == "detail" and isinstance(kw.value, ast.JoinedStr):
                                for part in kw.value.values:
                                    if isinstance(part, ast.FormattedValue):
                                        val = ast.unparse(part.value)
                                        self.assertNotIn(
                                            val,
                                            {"e", "str(e)", "exc", "str(exc)"},
                                            f"Raw exception reflection found in {path.name}: {val}",
                                        )


if __name__ == "__main__":
    unittest.main()
