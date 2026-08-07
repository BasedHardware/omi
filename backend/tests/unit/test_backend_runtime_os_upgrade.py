"""Contract: Debian-based backend runtime Dockerfiles patch OS packages (#7136)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# Final-stage images that ship from a Debian/Ubuntu apt base (not NVIDIA NeMo).
RUNTIME_DOCKERFILES = (
    ROOT / "backend" / "Dockerfile",
    ROOT / "backend" / "Dockerfile.desktop_backend",
    ROOT / "backend" / "pusher" / "Dockerfile",
    ROOT / "backend" / "agent-proxy" / "Dockerfile",
    ROOT / "backend" / "agent_vm" / "Dockerfile",
    ROOT / "backend" / "modal" / "Dockerfile",
    ROOT / "backend" / "modal" / "Dockerfile.notifications_job",
    ROOT / "backend" / "modal" / "Dockerfile.memory_maintenance_job",
    ROOT / "backend" / "diarizer" / "Dockerfile",
    ROOT / "backend" / "nllb_translation" / "Dockerfile",
    ROOT / "plugins" / "Dockerfile",
)


def _final_stage(text: str) -> str:
    """Return the last Dockerfile stage (after the final FROM line)."""
    lines = text.splitlines()
    last_from = max(i for i, line in enumerate(lines) if line.startswith("FROM "))
    return "\n".join(lines[last_from:])


def test_runtime_dockerfiles_upgrade_os_packages_in_final_stage():
    missing = []
    for path in RUNTIME_DOCKERFILES:
        assert path.is_file(), f"missing dockerfile: {path}"
        stage = _final_stage(path.read_text(encoding="utf-8"))
        if "apt-get -y upgrade --no-install-recommends" not in stage:
            missing.append(str(path.relative_to(ROOT)))
    assert missing == [], (
        "final stage must run apt-get -y upgrade --no-install-recommends "
        f"before shipping (#7136); missing: {missing}"
    )
