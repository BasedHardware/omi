"""Legacy POST /v1/files must guard thumbnail cleanup with an existence check, like /v2.

upload_file_chat (the pre-#CLEANUP legacy handler, kept for old app builds) called
thumb_file.unlink() unconditionally after uploading thumbnails to storage, while the
newer /v2 handler (upload_multi_files_chat) guards the same cleanup with
`if thumb_file.exists(): thumb_file.unlink()`. If the thumbnail was already removed or
never created for a given file, the unconditional unlink() raised FileNotFoundError
*after* the files/DB record were already persisted, turning a successful upload into a
spurious 500 for the client.

Source-level structural check: routers/chat.py has a very heavy import graph (Firestore,
LLM/agent tooling, storage clients).
"""

from pathlib import Path

CHAT_SOURCE = Path(__file__).resolve().parents[2] / "routers" / "chat.py"


def _source() -> str:
    return CHAT_SOURCE.read_text(encoding="utf-8")


def _function_body(source: str, def_line: str) -> str:
    start = source.index(def_line)
    end = source.index("\n@router.", start + 1)
    return source[start:end]


def test_legacy_v1_upload_guards_thumb_unlink_with_exists_check():
    source = _source()
    body = _function_body(source, "def upload_file_chat(")

    assert "thumb_file.unlink()" in body
    unlink_pos = body.index("thumb_file.unlink()")
    preceding = body[:unlink_pos]
    # The nearest preceding line must be the exists() guard, matching the v2 handler.
    last_lines = preceding.strip().splitlines()[-1]
    assert "if thumb_file.exists():" in last_lines, (
        "upload_file_chat must guard thumb_file.unlink() with `if thumb_file.exists():`, "
        "matching the v2 handler (upload_multi_files_chat) - otherwise an already-cleaned-up "
        "or never-created thumbnail raises FileNotFoundError after the upload already succeeded"
    )
