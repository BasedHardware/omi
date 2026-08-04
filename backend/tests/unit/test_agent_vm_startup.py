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
        "curl": "case \"$*\" in\n  *'/instance/attributes/auth-token'*) printf '%s\\n' omi-token ;;\n  *'/instance/service-accounts/default/token'*) printf '%s\\n' '{\"access_token\":\"metadata-token\"}' ;;\n  *'/project/project-id'*) printf '%s\\n' based-hardware-dev ;;\n  *'secretmanager.googleapis.com'*) printf '%s\\n' '{\"payload\":{\"data\":\"c2VjcmV0LXZhbHVl\"}}' ;;\n  *) exit 1 ;;\nesac\n",
        "docker": "printf 'docker %s\\n' \"$*\" >> \"$COMMAND_LOG\"\n",
    }.items():
        path = bin_dir / name
        path.write_text(f"#!/bin/bash\n{body}", encoding="utf-8")
        path.chmod(0o755)

    environment = {
        **os.environ,
        "AGENT_VM_IMAGE": "gcr.io/project/agent-vm:abcdef0",
        "AGENT_VM_GEMINI_SECRET_NAME": "GEMINI_API_KEY",
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
    assert "gcloud" not in commands
    assert "docker login --username oauth2accesstoken --password-stdin https://gcr.io" in commands
    assert "docker pull gcr.io/project/agent-vm:abcdef0" in commands
    assert "--env ANTHROPIC_API_KEY=secret-value" in commands
    assert "--env AUTH_TOKEN=omi-token" in commands
    assert "--env GEMINI_API_KEY=secret-value" in commands
    assert "--env PLAYWRIGHT_MCP_COMMAND=playwright-mcp" in commands
    assert (
        "--env PLAYWRIGHT_MCP_ARGS=[\"--user-data-dir\", \"/app/chrome-profile\", \"--headless\", \"--no-sandbox\"]"
        in commands
    )


def test_startup_publishers_substitute_only_the_image() -> None:
    workflows = {
        "desktop_backend_auto_dev.yml": "GCE_SERVICE_ACCOUNT=omi-agent-vm-bootstrap@based-hardware-dev.iam.gserviceaccount.com",
        "desktop_backend_prod.yml": "GCE_SERVICE_ACCOUNT=omi-agent-vm-bootstrap@based-hardware.iam.gserviceaccount.com",
    }
    for workflow, service_account in workflows.items():
        content = (ROOT.parent / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
        assert "envsubst '$AGENT_VM_IMAGE $AGENT_VM_GEMINI_SECRET_NAME' < backend/agent_vm/startup.sh" in content
        assert "envsubst < backend/agent_vm/startup.sh" not in content
        assert service_account in content
