"""Tests for the Pusher image source-closure derivation used in prod promotion.

The prod freshness gate must compare the full Dockerfile COPY source closure,
not a hardcoded two-directory subset, so that a post-qualification change to any
shared backend module (e.g. ``backend/utils/apps.py``) forces a new dev bake.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "backend/scripts/verify_pusher_source_closure.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_pusher_source_closure", SCRIPT)
    assert spec and spec.loader, "could not load verify_pusher_source_closure.py"
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_pusher_source_closure"] = module
    spec.loader.exec_module(module)
    return module


def test_source_closure_includes_all_dockerfile_copy_dirs() -> None:
    module = _load_module()
    dockerfile = REPO / "backend/pusher/Dockerfile"
    sources = module.final_stage_copy_sources(dockerfile)
    # Every directory the final-stage COPY copies into the runtime image.
    assert sorted(sources) == sorted(
        [
            "backend/config/",
            "backend/database/",
            "backend/models/",
            "backend/routers/",
            "backend/services/",
            "backend/testing/parity_pack_v0/",
            "backend/utils/",
            "backend/pusher/",
            # Shared structured-logging setup pusher/main.py imports (plan B B2).
            "backend/omi_logging.py",
        ]
    )


def test_source_closure_cli_output_includes_chart_dir() -> None:
    """The CLI output (used by the workflow) must also include the Helm chart dir."""
    import subprocess

    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(REPO),
    )
    paths = set(result.stdout.splitlines())
    assert "backend/charts/pusher" in paths
    # .dockerignore shapes the build context for both images (Codex round 2).
    assert ".dockerignore" in paths
    # Must cover all Dockerfile COPY source dirs.
    for expected in [
        "backend/config/",
        "backend/database/",
        "backend/models/",
        "backend/routers/",
        "backend/services/",
        "backend/testing/parity_pack_v0/",
        "backend/utils/",
        "backend/pusher/",
    ]:
        assert expected in paths, f"source closure missing {expected}"


def test_role_image_closure_covers_the_role_dockerfile_and_its_lock() -> None:
    """Plan B B3 review: a backend-pusher qualification must not survive a change
    to backend/Dockerfile.roles (the image definition that built it) or the
    role venv lock, which sit outside the fat Dockerfile's COPY closure."""
    import subprocess

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--image-repository", "gcr.io/based-hardware-dev/backend-pusher"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(REPO),
    )
    paths = set(result.stdout.splitlines())
    assert "backend/Dockerfile.roles" in paths
    assert "backend/pusher/pylock.toml" in paths
    assert "backend/charts/pusher" in paths
    assert ".dockerignore" in paths
    # The pusher target's COPY closure (same copied source dirs as the fat image).
    for expected in [
        "backend/config/",
        "backend/database/",
        "backend/models/",
        "backend/routers/",
        "backend/services/",
        "backend/testing/parity_pack_v0/",
        "backend/utils/",
        "backend/pusher/",
        "backend/omi_logging.py",
    ]:
        assert expected in paths, f"role-image closure missing {expected}"


def test_role_image_closure_detects_role_dockerfile_drift(tmp_path) -> None:
    """A change to backend/Dockerfile.roles after a backend-pusher qualification
    must fail the freshness gate, not slip through the fat image's closure."""
    import subprocess

    # Build a scratch repo containing the closure as tracked paths.
    repo = tmp_path / "repo"
    (repo / "backend").mkdir(parents=True)
    (repo / "docs").mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "backend" / "Dockerfile.roles").write_text("FROM base AS pusher\n", encoding="utf-8")
    (repo / "docs" / "notes.md").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "qualified"], cwd=repo, check=True
    )
    qualified = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()

    gate = (
        'paths=(); while IFS= read -r path; do paths+=("$path"); '
        'done < <("$1" "$2" --image-repository "$3"); '
        'git diff --quiet "$4" HEAD -- "${paths[@]}"'
    )
    # Unrelated docs change: gate stays quiet (exit 0).
    (repo / "docs" / "notes.md").write_text("two\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "docs"], cwd=repo, check=True)
    gate_args = [
        "bash",
        "-c",
        gate,
        "gate",
        sys.executable,
        str(SCRIPT),
        "gcr.io/based-hardware-dev/backend-pusher",
        qualified,
    ]
    quiet = subprocess.run(gate_args, cwd=repo, check=False)
    assert quiet.returncode == 0

    # Role Dockerfile change: gate must fire (exit 1).
    (repo / "backend" / "Dockerfile.roles").write_text("FROM base AS pusher\nRUN apt-get update\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "roles"], cwd=repo, check=True)
    fired = subprocess.run(gate_args, cwd=repo, check=False)
    assert fired.returncode == 1


def test_fat_repository_still_selects_the_fat_closure() -> None:
    """A fat pusher qualification must not suddenly compare the role closure."""
    module = _load_module()
    fat = set(module.closure_paths("gcr.io/based-hardware-dev/pusher"))
    role = set(module.closure_paths("gcr.io/based-hardware-dev/backend-pusher"))
    assert "backend/Dockerfile.roles" not in fat
    assert "backend/Dockerfile.roles" in role
    assert "backend/pusher/Dockerfile" not in fat  # covered by backend/pusher/
    assert fat & role == fat  # the fat closure is a subset of the role closure


def test_source_closure_excludes_builder_stage_copies(tmp_path) -> None:
    """Multi-stage --from= copies reference builder artifacts, not repo source."""
    module = _load_module()
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        "FROM base AS builder\n"
        "COPY backend/pusher/pylock.toml /tmp/pylock.toml\n"
        "FROM base\n"
        "COPY --from=builder /opt/venv /opt/venv\n"
        "COPY backend/config/ ./config/\n"
        "COPY backend/pusher/ ./pusher/\n"
    )
    sources = module.final_stage_copy_sources(dockerfile)
    assert "backend/config/" in sources
    assert "backend/pusher/" in sources
    # Builder-stage copies must NOT be included.
    assert "/opt/venv" not in sources
    assert "backend/pusher/pylock.toml" not in sources


def test_line_framed_workflow_consumer_detects_shared_source_drift(tmp_path) -> None:
    import subprocess

    source = tmp_path / "backend/utils/apps.py"
    source.parent.mkdir(parents=True)
    source.write_text("version = 1\n", encoding="utf-8")
    docs = tmp_path / "README.md"
    docs.write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "add", "backend/utils/apps.py", "README.md"], cwd=tmp_path, check=True)
    # Bash read preserves one path per line, matching the workflow's mapfile.
    gate = (
        'paths=(); while IFS= read -r path; do paths+=("$path"); '
        'done < <("$1" "$2"); git diff --quiet -- "${paths[@]}"'
    )
    command = ["bash", "-c", gate, "gate", sys.executable, str(SCRIPT)]
    docs.write_text("after\n", encoding="utf-8")
    assert subprocess.run(command, cwd=tmp_path, check=False).returncode == 0
    source.write_text("version = 2\n", encoding="utf-8")
    assert subprocess.run(command, cwd=tmp_path, check=False).returncode == 1


def test_runtime_uses_a_non_root_user_with_writable_working_directories() -> None:
    dockerfile = (REPO / "backend/pusher/Dockerfile").read_text(encoding="utf-8")
    assert "mkdir -p _temp _samples _segments _speech_profiles" in dockerfile
    assert "chown -R 10001:10001 _temp _samples _segments _speech_profiles" in dockerfile
    assert "USER 10001:10001" in dockerfile
