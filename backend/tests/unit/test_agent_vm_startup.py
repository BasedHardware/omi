import os
import subprocess
from pathlib import Path

from testing.shell import bash_command, bash_path

ROOT = Path(__file__).resolve().parents[2]
STARTUP = ROOT / "agent_vm" / "startup.sh"


def test_startup_runs_the_published_python_runtime_with_instance_credentials(tmp_path: Path) -> None:
    log = tmp_path / "commands"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in {
        "curl": "printf '%s\\n' omi-token\n",
        "gcloud": "printf 'gcloud %s\\n' \"$*\" >> \"$COMMAND_LOG\"\ncase \"$1 $2\" in\n  'secrets versions') printf '%s\\n' secret-value ;;\nesac\n",
        "docker": "printf 'docker %s\\n' \"$*\" >> \"$COMMAND_LOG\"\n",
    }.items():
        path = bin_dir / name
        path.write_text(f"#!/bin/bash\n{body}", encoding="utf-8")
        path.chmod(0o755)

    environment = {
        **os.environ,
        "AGENT_VM_IMAGE": "gcr.io/project/agent-vm:abcdef0",
        "AGENT_VM_DATA_DIR": bash_path(tmp_path / "data", cwd=ROOT),
        "COMMAND_LOG": bash_path(log, cwd=ROOT),
        "OMI_TEST_FAKE_BIN": bash_path(bin_dir, cwd=ROOT),
    }
    subprocess.run(
        bash_command(
            "-c",
            'export PATH="$OMI_TEST_FAKE_BIN:$PATH"\nexec "$BASH" "$@"',
            "bash",
            STARTUP,
            cwd=ROOT,
        ),
        check=True,
        env=environment,
    )

    commands = log.read_text(encoding="utf-8")
    assert "gcloud secrets versions access latest --secret=DESKTOP_ANTHROPIC_API_KEY" in commands
    assert "gcloud secrets versions access latest --secret=GEMINI_API_KEY" in commands
    assert "gcloud auth configure-docker gcr.io --quiet" in commands
    assert "docker pull gcr.io/project/agent-vm:abcdef0" in commands
    assert "--env ANTHROPIC_API_KEY=secret-value" in commands
    assert "--env AUTH_TOKEN=omi-token" in commands
    assert "--env GEMINI_API_KEY=secret-value" in commands
    assert "--env PLAYWRIGHT_MCP_COMMAND=playwright-mcp" in commands
    assert (
        "--env PLAYWRIGHT_MCP_ARGS=[\"--user-data-dir\", \"/app/chrome-profile\", \"--headless\", \"--no-sandbox\"]"
        in commands
    )
