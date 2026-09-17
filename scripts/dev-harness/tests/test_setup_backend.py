from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SETUP_BACKEND = REPO_ROOT / "scripts" / "dev-harness" / "setup-backend.sh"
BOOTSTRAP = REPO_ROOT / "scripts" / "dev-harness" / "bootstrap-lane-worktree.sh"
MAKEFILE = REPO_ROOT / "Makefile"


def test_setup_backend_uses_requirements_wheels_not_pylock_sync() -> None:
    text = SETUP_BACKEND.read_text(encoding="utf-8")
    assert "uv pip install" in text
    assert "requirements.txt" in text
    assert "uv pip sync" in text
    assert "pylock" in text
    for module in ("uvicorn", "pyright", "yaml", "dotenv", "google.auth"):
        assert module in text
    assert "already complete, skipped pip" in text


def test_makefile_setup_backend_runs_the_fast_script() -> None:
    text = MAKEFILE.read_text(encoding="utf-8")
    assert "scripts/dev-harness/setup-backend.sh" in text
    lock = REPO_ROOT / "backend" / "scripts" / "sync-python-deps.sh"
    assert lock.is_file()
    assert "uv pip sync" in lock.read_text(encoding="utf-8")


def test_lane_bootstrap_closing_message_names_typecheck_and_pub_get() -> None:
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert "make setup-backend" in text
    assert "check_backend_typecheck_if_needed" in text
    assert "flutter pub get" in text
    assert "generated-output" in text
