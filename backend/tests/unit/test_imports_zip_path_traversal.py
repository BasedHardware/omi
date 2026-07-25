"""POST /v1/import/limitless must not honor path-traversal segments in the ZIP filename.

file.filename is client-supplied and, before this fix, was only checked for a ".zip"
suffix before being joined straight into the on-disk path:
    zip_path = os.path.join(TEMP_DIR, f"{job.id}_{file.filename}")
A filename such as "../../evil.zip" still ends in ".zip" and passes that check, so the
write could escape TEMP_DIR. The handler now reduces the filename to its basename
(os.path.basename) before building the path.

Source-level structural check: routers/imports.py has a heavy import graph (Firestore,
storage clients, background job orchestration), matching the approach already used by
test_payment_connect_account_user_guard.py and test_payment_stripe_refresh_idor.py.
"""

from pathlib import Path

IMPORTS_SOURCE = Path(__file__).resolve().parents[2] / "routers" / "imports.py"


def _source() -> str:
    return IMPORTS_SOURCE.read_text(encoding="utf-8")


def test_zip_path_uses_basename_of_filename():
    source = _source()
    start = source.index("async def import_limitless_data")
    end = source.index("\n@router.", start + 1)
    endpoint = source[start:end]

    assert "os.path.basename(file.filename)" in endpoint, (
        "import_limitless_data must reduce file.filename to its basename before joining it into "
        "zip_path, or a '../'-containing filename can write outside TEMP_DIR"
    )

    basename_pos = endpoint.index("os.path.basename(file.filename)")
    zip_path_pos = endpoint.index("zip_path = os.path.join(")
    assert basename_pos < zip_path_pos, "the basename reduction must happen before zip_path is built"

    # The sanitized variable, not the raw file.filename, must be what's interpolated
    # into zip_path.
    zip_path_line = endpoint[zip_path_pos : endpoint.index("\n", zip_path_pos)]
    assert "file.filename" not in zip_path_line, "zip_path must not interpolate the raw, unsanitized filename"
