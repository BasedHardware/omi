from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LANE_BACKEND = REPO_ROOT / "scripts" / "dev-harness" / "lane-backend.sh"
BOOTSTRAP = REPO_ROOT / "scripts" / "dev-harness" / "bootstrap-lane-worktree.sh"
MAKEFILE = REPO_ROOT / "Makefile"


def _makefile_target(name: str) -> str:
    text = MAKEFILE.read_text(encoding="utf-8")
    lines = text.splitlines()
    collecting = False
    body: list[str] = []
    prefix = f"{name}:"
    for line in lines:
        if line.startswith(prefix):
            collecting = True
            body.append(line)
            continue
        if collecting:
            if line.startswith("\t") or line.startswith(" "):
                body.append(line)
            elif line.endswith(":") and not line.startswith("\t"):
                break
            elif line == "":
                break
            else:
                break
    return "\n".join(body)


def test_lane_backend_uses_requirements_wheels_not_pylock_sync() -> None:
    text = LANE_BACKEND.read_text(encoding="utf-8")
    assert "uv pip install" in text
    assert "requirements.txt" in text
    assert "uv pip sync" in text
    assert "pylock" in text
    assert "not lock-hash identical" in text
    for module in ("uvicorn", "pyright", "yaml", "dotenv", "google.auth"):
        assert module in text
    assert "already complete, skipped pip" in text


def test_makefile_setup_backend_stays_the_locked_sync() -> None:
    recipe = _makefile_target("setup-backend")
    assert "backend/scripts/sync-python-deps.sh" in recipe
    assert "lane-backend.sh" not in recipe
    assert "setup-backend.sh" not in recipe
    lock = REPO_ROOT / "backend" / "scripts" / "sync-python-deps.sh"
    assert lock.is_file()
    assert "uv pip sync" in lock.read_text(encoding="utf-8")


def test_makefile_lane_backend_runs_the_fast_script() -> None:
    recipe = _makefile_target("lane-backend")
    assert "scripts/dev-harness/lane-backend.sh" in recipe


def test_lane_bootstrap_closing_message_names_typecheck_and_pub_get() -> None:
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert "make lane-backend" in text
    assert "check_backend_typecheck_if_needed" in text
    assert "flutter pub get" in text
    assert "generated-output" in text
    assert "generate-app-env.sh" in text
    assert "--delete-conflicting-outputs" not in text
    assert "--build-filter" not in text
