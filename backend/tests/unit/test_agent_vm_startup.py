import json
import os
import sqlite3
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
        "curl": "case \"$*\" in\n  *'omi-agent-state-required'*) printf '\\n404\\n' ;;\n  *'/instance/attributes/auth-token'*) printf '%s\\n' omi-token ;;\n  *'/instance/service-accounts/default/token'*) printf '%s\\n' '{\"access_token\":\"metadata-token\"}' ;;\n  *'/project/project-id'*) printf '%s\\n' based-hardware-dev ;;\n  *'secretmanager.googleapis.com'*) printf '%s\\n' '{\"payload\":{\"data\":\"c2VjcmV0LXZhbHVl\"}}' ;;\n  *) exit 1 ;;\nesac\n",
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
    assert "--env DB_PATH=/root/omi-agent/data/omi.db" in commands
    assert "--env AGENT_VM_WORKSPACE=/root/omi-agent/workspace" in commands
    assert "--tmpfs /app/chrome-profile:rw,exec" in commands
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


def test_startup_bootstraps_read_only_state_tooling_contract() -> None:
    source = STARTUP.read_text(encoding="utf-8")

    assert "for tool in mount findmnt blkid wipefs mkfs.ext4" in source
    assert "DEBIAN_FRONTEND=noninteractive apt-get install -y util-linux e2fsprogs" in source
    assert 'wipefs --noheadings "$device"' in source
    assert 'wipefs --noheadings --all' not in source


def _write_fake_command(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text(f"#!/bin/bash\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _state_startup_environment(
    tmp_path: Path, *, corrupt_copy: bool = False
) -> tuple[dict[str, str], Path, Path, Path]:
    log = tmp_path / "commands"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state_device = tmp_path / "state-device"
    state_device.touch()
    state_mount = tmp_path / "state-mount"
    state_mount.mkdir()
    source_device = tmp_path / "source-device"
    source_device.touch()
    source_mount = tmp_path / "source-mount"
    legacy_state = source_mount / "var/lib/omi-agent"
    (legacy_state / "data").mkdir(parents=True)
    connection = sqlite3.connect(legacy_state / "data/omi.db")
    connection.execute("CREATE TABLE state (value TEXT)")
    connection.execute("INSERT INTO state VALUES ('persisted')")
    connection.commit()
    connection.close()
    (legacy_state / "legacy.txt").write_text("legacy", encoding="utf-8")
    fs_marker = tmp_path / "formatted"

    _write_fake_command(
        bin_dir,
        "curl",
        "case \"$*\" in\n"
        "  *'omi-agent-state-required'*)\n"
        "    case \"$STATE_REQUIRED_MODE\" in\n"
        "      missing) printf '\\n404\\n' ;;\n"
        "      error) exit 1 ;;\n"
        "      *) printf 'true\\n200\\n' ;;\n"
        "    esac ;;\n"
        "  *'omi-agent-migration'*) if [[ \"$MIGRATION_MODE\" == fallback ]]; then exit 1; else printf '%s\\n' migration-test-1; fi ;;\n"
        "  *'/instance/name'*) printf '%s\\n' vm-instance-name ;;\n"
        "  *'/instance/attributes/auth-token'*) printf '%s\\n' omi-token ;;\n"
        "  *'/instance/service-accounts/default/token'*) printf '%s\\n' '{\"access_token\":\"metadata-token\"}' ;;\n"
        "  *'/project/project-id'*) printf '%s\\n' based-hardware-dev ;;\n"
        "  *'secretmanager.googleapis.com'*) printf '%s\\n' '{\"payload\":{\"data\":\"c2VjcmV0LXZhbHVl\"}}' ;;\n"
        "  *) exit 1 ;;\n"
        "esac",
    )
    _write_fake_command(bin_dir, "docker", "printf 'docker %s\\n' \"$*\" >> \"$COMMAND_LOG\"")
    _write_fake_command(
        bin_dir,
        "systemctl",
        "printf 'systemctl %s\\n' \"$*\" >> \"$COMMAND_LOG\"\n"
        "case \"$1\" in cat|disable) exit 0 ;; *) exit 1 ;; esac",
    )
    _write_fake_command(bin_dir, "blkid", "if [[ -f \"$FS_MARKER\" ]]; then printf '%s\\n' ext4; fi")
    _write_fake_command(bin_dir, "wipefs", "printf 'wipefs %s\\n' \"$*\" >> \"$COMMAND_LOG\"\nexit 0")
    _write_fake_command(
        bin_dir,
        "mkfs.ext4",
        "touch \"$FS_MARKER\"\n" "printf 'mkfs.ext4 %s\\n' \"$*\" >> \"$COMMAND_LOG\"",
    )
    _write_fake_command(bin_dir, "mountpoint", "exit 1")
    _write_fake_command(bin_dir, "mount", "printf 'mount %s\\n' \"$*\" >> \"$COMMAND_LOG\"")
    _write_fake_command(
        bin_dir,
        "findmnt",
        "if [[ \"$3\" == SOURCE ]]; then\n"
        "  if [[ \"$5\" == \"$STATE_MOUNT\" ]]; then printf '%s\\n' \"$STATE_DEVICE\"; else printf '%s\\n' \"$STATE_SOURCE_DEVICE\"; fi\n"
        "else\n  printf '%s\\n' ro\nfi",
    )
    _write_fake_command(bin_dir, "umount", "printf 'umount %s\\n' \"$*\" >> \"$COMMAND_LOG\"")
    if corrupt_copy:
        _write_fake_command(
            bin_dir,
            "cp",
            "/bin/cp \"$@\"\n" "target=\"${@: -1}\"\n" "touch \"$target/.copy-mismatch\"",
        )

    environment = {
        **os.environ,
        "AGENT_VM_IMAGE": "gcr.io/project/agent-vm:abcdef0",
        "AGENT_VM_GEMINI_SECRET_NAME": "GEMINI_API_KEY",
        "AGENT_VM_RELEASE_ID": "",
        "AGENT_VM_IMAGE_DIGEST": "",
        "AGENT_VM_BACKEND_URL": "",
        "AGENT_VM_STOP_AUDIENCE": "",
        "AGENT_VM_STATE_DEVICE": bash_path(state_device, cwd=ROOT),
        "AGENT_VM_STATE_SOURCE_DEVICE": bash_path(source_device, cwd=ROOT),
        "AGENT_VM_STATE_MOUNT": bash_path(state_mount, cwd=ROOT),
        "AGENT_VM_STATE_SOURCE_MOUNT": bash_path(source_mount, cwd=ROOT),
        "MIGRATION_MODE": "metadata",
        "STATE_REQUIRED_MODE": "required",
        "COMMAND_LOG": bash_path(log, cwd=ROOT),
        "FS_MARKER": bash_path(fs_marker, cwd=ROOT),
        "STATE_DEVICE": bash_path(state_device, cwd=ROOT),
        "STATE_SOURCE_DEVICE": bash_path(source_device, cwd=ROOT),
        "STATE_MOUNT": bash_path(state_mount, cwd=ROOT),
        "OMI_TEST_FAKE_BIN": bash_path(bin_dir, cwd=ROOT),
    }
    return environment, state_mount, source_mount, log


def _run_state_startup(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        bash_command(
            "-c",
            'export PATH="$OMI_TEST_FAKE_BIN:$PATH"\nexec "$BASH" "$@"',
            "bash",
            STARTUP,
            cwd=ROOT,
        ),
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_startup_migrates_legacy_state_and_writes_receipt(tmp_path: Path) -> None:
    environment, state_mount, _, log = _state_startup_environment(tmp_path)
    result = _run_state_startup(environment)

    assert result.returncode == 0, result.stderr
    receipt = json.loads((state_mount / "state-receipt.json").read_text(encoding="utf-8"))
    assert receipt["schemaVersion"] == 1
    assert receipt["migrationId"] == "migration-test-1"
    assert receipt["tree"]["count"] == 2
    assert receipt["tree"]["bytes"] > 0
    assert receipt["db"]["integrity"] == "ok"
    assert (state_mount / "legacy.txt").read_text(encoding="utf-8") == "legacy"
    commands = log.read_text(encoding="utf-8")
    assert "mount -o ro" in commands
    assert "umount" in commands
    assert "wipefs --noheadings" in commands
    assert "--all" not in commands


def test_startup_falls_back_to_instance_name_for_migration_id(tmp_path: Path) -> None:
    environment, state_mount, _, _ = _state_startup_environment(tmp_path)
    environment["MIGRATION_MODE"] = "fallback"
    result = _run_state_startup(environment)

    assert result.returncode == 0, result.stderr
    receipt = json.loads((state_mount / "state-receipt.json").read_text(encoding="utf-8"))
    assert receipt["migrationId"] == "vm-instance-name"


def test_startup_revalidates_and_rewrites_a_valid_prior_migration_receipt(tmp_path: Path) -> None:
    environment, state_mount, _, log = _state_startup_environment(tmp_path)
    first = _run_state_startup(environment)
    assert first.returncode == 0, first.stderr
    receipt_path = state_mount / "state-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["migrationId"] = "prior-migration"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    second = _run_state_startup(environment)

    assert second.returncode == 0, second.stderr
    rewritten = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert rewritten["migrationId"] == "migration-test-1"
    assert log.read_text(encoding="utf-8").count("mount -o ro") == 1


def test_startup_fails_closed_on_a_symlink_in_durable_state(tmp_path: Path) -> None:
    environment, _, source_mount, _ = _state_startup_environment(tmp_path)
    legacy_state = source_mount / "var/lib/omi-agent"
    (legacy_state / "state-link").symlink_to("legacy.txt")

    result = _run_state_startup(environment)

    assert result.returncode != 0
    assert "symlink is not allowed in durable state" in result.stderr


def test_startup_is_idempotent_for_the_same_migration(tmp_path: Path) -> None:
    environment, _, _, log = _state_startup_environment(tmp_path)
    first = _run_state_startup(environment)
    second = _run_state_startup(environment)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert log.read_text(encoding="utf-8").count("mount -o ro") == 1


def test_startup_reconstructs_an_interrupted_unreceipted_copy(tmp_path: Path) -> None:
    environment, state_mount, _, _ = _state_startup_environment(tmp_path)
    (state_mount / "partial.txt").write_text("interrupted", encoding="utf-8")
    (state_mount / ".migration-staging").mkdir()
    (state_mount / ".migration-staging" / "partial.db").write_text("partial", encoding="utf-8")

    result = _run_state_startup(environment)

    assert result.returncode == 0, result.stderr
    assert not (state_mount / "partial.txt").exists()
    assert not (state_mount / ".migration-staging").exists()
    assert (state_mount / "legacy.txt").read_text(encoding="utf-8") == "legacy"


def test_startup_rejects_loss_of_a_previously_durable_database(tmp_path: Path) -> None:
    environment, state_mount, _, _ = _state_startup_environment(tmp_path)
    first = _run_state_startup(environment)
    assert first.returncode == 0, first.stderr
    (state_mount / "data/omi.db").unlink()

    second = _run_state_startup(environment)

    assert second.returncode != 0
    assert "previously durable state database is missing" in second.stderr


def test_startup_fails_closed_when_required_state_device_is_missing(tmp_path: Path) -> None:
    environment, _, _, _ = _state_startup_environment(tmp_path)
    environment["AGENT_VM_STATE_DEVICE"] = bash_path(tmp_path / "missing-state-device", cwd=ROOT)
    result = _run_state_startup(environment)

    assert result.returncode != 0
    assert "required state device is missing" in result.stderr


def test_startup_distinguishes_absent_legacy_metadata_from_metadata_outage(tmp_path: Path) -> None:
    environment, _, _, _ = _state_startup_environment(tmp_path)
    environment["STATE_REQUIRED_MODE"] = "error"

    result = _run_state_startup(environment)

    assert result.returncode != 0
    assert "state requirement metadata is unavailable" in result.stderr


def test_startup_fails_closed_when_source_and_destination_manifests_differ(tmp_path: Path) -> None:
    environment, _, _, _ = _state_startup_environment(tmp_path, corrupt_copy=True)
    result = _run_state_startup(environment)

    assert result.returncode != 0
    assert "source and destination state differ" in result.stderr
