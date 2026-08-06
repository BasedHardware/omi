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
        "systemctl": "printf 'systemctl %s\\n' \"$*\" >> \"$COMMAND_LOG\"\ncase \"$1\" in\n  cat) exit 0 ;;\n  disable) exit 0 ;;\n  *) exit 1 ;;\nesac\n",
    }.items():
        path = bin_dir / name
        path.write_text(f"#!/bin/bash\n{body}", encoding="utf-8")
        path.chmod(0o755)

    environment = {
        **os.environ,
        "AGENT_VM_IMAGE": "gcr.io/project/agent-vm:abcdef0",
        "AGENT_VM_GEMINI_SECRET_NAME": "GEMINI_API_KEY",
        "AGENT_VM_RELEASE_ID": "",
        "AGENT_VM_IMAGE_DIGEST": "",
        "AGENT_VM_BACKEND_URL": "",
        "AGENT_VM_STOP_AUDIENCE": "",
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
    assert "systemctl cat omi-agent.service" in commands
    assert "systemctl disable --now omi-agent.service" in commands
    assert "docker login --username oauth2accesstoken --password-stdin https://gcr.io" in commands
    assert "docker pull gcr.io/project/agent-vm:abcdef0" in commands
    assert commands.index("docker container inspect omi-agent-vm") < commands.index("docker rm -f omi-agent-vm")
    assert commands.index("docker rm -f omi-agent-vm") < commands.index("docker run --detach")
    assert "--env ANTHROPIC_API_KEY=secret-value" in commands
    assert "--env AUTH_TOKEN=omi-token" in commands
    assert "--env GEMINI_API_KEY=secret-value" in commands
    assert "--env PLAYWRIGHT_MCP_COMMAND=playwright-mcp" in commands
    assert (
        "--env PLAYWRIGHT_MCP_ARGS=[\"--user-data-dir\", \"/app/chrome-profile\", \"--headless\", \"--no-sandbox\"]"
        in commands
    )


def test_startup_publishers_render_image_and_secret_name_without_shell_defaults() -> None:
    workflows = {
        "desktop_backend_auto_dev.yml": "GCE_SERVICE_ACCOUNT=omi-agent-vm-bootstrap@based-hardware-dev.iam.gserviceaccount.com",
        "desktop_backend_prod.yml": "GCE_SERVICE_ACCOUNT=omi-agent-vm-bootstrap@based-hardware.iam.gserviceaccount.com",
    }
    publisher_paths = sorted(
        path
        for path in (ROOT.parent / ".github" / "workflows").glob("desktop_backend_*.yml")
        if "backend/agent_vm/startup.sh" in path.read_text(encoding="utf-8")
    )
    assert {path.name for path in publisher_paths} == set(workflows)
    for path in publisher_paths:
        workflow = path.name
        service_account = workflows[workflow]
        content = path.read_text(encoding="utf-8")
        assert (
            'envsubst "\\$AGENT_VM_IMAGE \\$AGENT_VM_GEMINI_SECRET_NAME \\$AGENT_VM_RELEASE_ID '
            '\\$AGENT_VM_IMAGE_DIGEST \\$AGENT_VM_BACKEND_URL \\$AGENT_VM_STOP_AUDIENCE"'
        ) in content
        assert "envsubst < backend/agent_vm/startup.sh" not in content
        assert service_account in content
        assert 'gcloud storage cp "$rendered_startup" "gs://$AGENT_GCS_BUCKET/startup.sh"' not in content
        assert "AGENT_VM_ACTIVE_RELEASE_URI=${{ steps.agent-vm-release.outputs.active_manifest_uri }}" in content
        assert "AGENT_VM_RECONCILER_JOB" in content
        assert "GOOGLE_APPLICATION_CREDENTIALS=/secrets/reconciler/service-account.json" not in content

    rendered = subprocess.run(
        [
            "envsubst",
            "$AGENT_VM_IMAGE $AGENT_VM_GEMINI_SECRET_NAME $AGENT_VM_RELEASE_ID "
            "$AGENT_VM_IMAGE_DIGEST $AGENT_VM_BACKEND_URL $AGENT_VM_STOP_AUDIENCE",
        ],
        input=STARTUP.read_bytes(),
        env={
            **os.environ,
            "AGENT_VM_IMAGE": "gcr.io/project/agent-vm:abcdef0",
            "AGENT_VM_GEMINI_SECRET_NAME": "DESKTOP_GEMINI_API_KEY",
            "AGENT_VM_RELEASE_ID": "a" * 40,
            "AGENT_VM_IMAGE_DIGEST": "gcr.io/project/agent-vm@sha256:" + "b" * 64,
            "AGENT_VM_BACKEND_URL": "https://desktop.example.test",
            "AGENT_VM_STOP_AUDIENCE": "https://desktop.example.test",
        },
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    assert 'image="gcr.io/project/agent-vm:abcdef0"' in rendered
    assert 'gemini_secret_name="DESKTOP_GEMINI_API_KEY"' in rendered
    assert 'release_id="' + "a" * 40 + '"' in rendered
    assert 'image_digest="gcr.io/project/agent-vm@sha256:' + "b" * 64 + '"' in rendered
    assert "${AGENT_VM_GEMINI_SECRET_NAME}" not in rendered
    assert '${AGENT_VM_DATA_DIR:-/var/lib/omi-agent}' in rendered
    assert 'startup_sha256="$(sha256sum "${BASH_SOURCE[0]}"' in rendered
