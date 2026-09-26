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
    paths = set(result.stdout.strip().split())
    assert "backend/charts/pusher" in paths
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


def test_source_closure_excludes_builder_stage_copies() -> None:
    """Multi-stage --from= copies reference builder artifacts, not repo source."""
    import tempfile

    module = _load_module()
    with tempfile.NamedTemporaryFile(mode="w", suffix="Dockerfile", delete=False) as f:
        f.write(
            "FROM base AS builder\n"
            "COPY backend/pusher/pylock.toml /tmp/pylock.toml\n"
            "FROM base\n"
            "COPY --from=builder /opt/venv /opt/venv\n"
            "COPY backend/config/ ./config/\n"
            "COPY backend/pusher/ ./pusher/\n"
        )
        f.flush()
        sources = module.final_stage_copy_sources(Path(f.name))
    assert "backend/config/" in sources
    assert "backend/pusher/" in sources
    # Builder-stage copies must NOT be included.
    assert "/opt/venv" not in sources
    assert "backend/pusher/pylock.toml" not in sources


def test_runtime_uses_a_non_root_user_with_writable_working_directories() -> None:
    dockerfile = (REPO / "backend/pusher/Dockerfile").read_text(encoding="utf-8")
    assert "mkdir -p _temp _samples _segments _speech_profiles" in dockerfile
    assert "chown -R 10001:10001 _temp _samples _segments _speech_profiles" in dockerfile
    assert "USER 10001:10001" in dockerfile
