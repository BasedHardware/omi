"""Static contract: shipped Debian/Ubuntu runtime stages patch OS packages (#7136)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# Final-stage Debian/Ubuntu apt-base images covered by this contract. NVIDIA
# NeMo/parakeet images remain out of scope because they use a separate owner/toolchain.
RUNTIME_DOCKERFILES = (
    ROOT / "backend" / "Dockerfile",
    ROOT / "backend" / "Dockerfile.desktop_backend",
    ROOT / "backend" / "pusher" / "Dockerfile",
    ROOT / "backend" / "modal" / "Dockerfile",
    ROOT / "backend" / "modal" / "Dockerfile.notifications_job",
    ROOT / "backend" / "modal" / "Dockerfile.memory_maintenance_job",
    ROOT / "backend" / "diarizer" / "Dockerfile",
    ROOT / "backend" / "nllb_translation" / "Dockerfile",
    ROOT / "plugins" / "Dockerfile",
    ROOT / "plugins" / "Dockerfile.datadog",
    ROOT / "plugins" / "composio" / "Dockerfile",
    ROOT / "plugins" / "hume-ai" / "Dockerfile",
    ROOT / "plugins" / "omi-github-app" / "Dockerfile",
)


def _final_stage_run_instructions(text: str) -> list[str]:
    """Return effective RUN instructions from the final Dockerfile stage."""
    lines = text.splitlines()
    last_from = max(i for i, line in enumerate(lines) if line.startswith("FROM "))
    instructions: list[str] = []
    current: list[str] = []
    for line in lines[last_from + 1 :]:
        if line.startswith("RUN "):
            if current:
                instructions.append(" ".join(current))
            current = [line]
        elif current and line.endswith("\\"):
            current.append(line)
        elif current:
            current.append(line)
            instructions.append(" ".join(current))
            current = []
    if current:
        instructions.append(" ".join(current))
    return instructions


def test_runtime_dockerfiles_dist_upgrade_os_packages_in_final_stage():
    missing = []
    for path in RUNTIME_DOCKERFILES:
        assert path.is_file(), f"missing dockerfile: {path}"
        run_instructions = _final_stage_run_instructions(path.read_text(encoding="utf-8"))
        if not any("apt-get update" in run and "apt-get -y dist-upgrade" in run for run in run_instructions):
            missing.append(str(path.relative_to(ROOT)))
    assert missing == [], f"final stage must run apt-get -y dist-upgrade (#7136); missing: {missing}"
