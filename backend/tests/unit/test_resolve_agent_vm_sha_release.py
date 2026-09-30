from __future__ import annotations

import importlib.util
import json
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent
SCRIPT = BACKEND_DIR / 'scripts' / 'resolve_agent_vm_sha_release.py'
SOURCE_SHA = '99dbbb26c18efdb3b896aba3eb91d66302ba008f'
DIGEST_A = 'gcr.io/based-hardware/agent-vm@sha256:' + 'a' * 64
DIGEST_B = 'gcr.io/based-hardware/agent-vm@sha256:' + 'b' * 64
BOOT_IMAGE = 'projects/based-hardware/global/images/omi-agent-20260805'


def load_resolve():
    spec = importlib.util.spec_from_file_location('resolve_agent_vm_sha_release', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def startup_for(digest: str) -> str:
    return f'image="{digest}"\nimage_digest="{digest}"\n'


def manifest_for(digest: str, *, source_sha: str = SOURCE_SHA) -> str:
    return json.dumps(
        {
            'schemaVersion': 1,
            'environment': 'production',
            'sourceSha': source_sha,
            'imageDigest': digest,
            'startupUri': f'gs://based-hardware-agent/agent-vm/releases/{source_sha}/startup.sh',
            'startupSha256': 'c' * 64,
            'bootImage': BOOT_IMAGE,
            'serviceAccount': 'omi-agent-vm-bootstrap@based-hardware.iam.gserviceaccount.com',
        }
    )


class FakeGcloud:
    def __init__(self, objects: dict[str, str]) -> None:
        self.objects = objects
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str]) -> SimpleNamespace:
        self.commands.append(command)
        if command[1:4] == ['storage', 'objects', 'describe']:
            uri = command[4]
            if uri in self.objects:
                return SimpleNamespace(returncode=0, stdout='present\n', stderr='')
            return SimpleNamespace(returncode=1, stdout='', stderr='NOT_FOUND')
        if command[1:3] == ['storage', 'cp']:
            uri, dest = command[3], command[4]
            if uri not in self.objects:
                return SimpleNamespace(returncode=1, stdout='', stderr='NOT_FOUND')
            Path(dest).write_text(self.objects[uri], encoding='utf-8')
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        raise AssertionError(f'unexpected gcloud command: {command}')


def test_missing_artifacts_allow_a_first_publish():
    resolve = load_resolve()
    plan = resolve.plan_from_existing(startup=None, manifest_text=None, expected_source_sha=SOURCE_SHA)
    assert plan.reuse is False
    assert plan.image_digest is None


def test_existing_manifest_and_startup_reuse_that_digest():
    resolve = load_resolve()
    plan = resolve.plan_from_existing(
        startup=startup_for(DIGEST_A),
        manifest_text=manifest_for(DIGEST_A),
        expected_source_sha=SOURCE_SHA,
    )
    assert plan.reuse is True
    assert plan.image_digest == DIGEST_A
    assert plan.boot_image == BOOT_IMAGE
    assert '32012710785' in resolve.INCIDENT


def test_orphan_startup_reuses_embedded_digest_without_a_competing_rebuild():
    resolve = load_resolve()
    plan = resolve.plan_from_existing(
        startup=startup_for(DIGEST_A),
        manifest_text=None,
        expected_source_sha=SOURCE_SHA,
    )
    assert plan.reuse is True
    assert plan.image_digest == DIGEST_A
    assert plan.boot_image is None
    assert plan.manifest_present is False


def test_manifest_without_startup_fails_closed():
    resolve = load_resolve()
    with pytest.raises(resolve.ResolveError, match='inconsistent'):
        resolve.plan_from_existing(
            startup=None,
            manifest_text=manifest_for(DIGEST_A),
            expected_source_sha=SOURCE_SHA,
        )


def test_startup_and_manifest_digest_mismatch_fails_closed():
    resolve = load_resolve()
    with pytest.raises(resolve.ResolveError, match='does not match manifest'):
        resolve.plan_from_existing(
            startup=startup_for(DIGEST_A),
            manifest_text=manifest_for(DIGEST_B),
            expected_source_sha=SOURCE_SHA,
        )


def test_object_exists_fails_closed_on_non_not_found_errors():
    resolve = load_resolve()

    def deny_access(_command: list[str]) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stdout='', stderr='PERMISSION_DENIED: access denied')

    with pytest.raises(resolve.ResolveError, match='could not inspect'):
        resolve.object_exists('gs://bucket/object', runner=deny_access)


def test_live_resolve_reuses_existing_objects(tmp_path: Path):
    resolve = load_resolve()
    startup_uri = f'gs://based-hardware-agent/agent-vm/releases/{SOURCE_SHA}/startup.sh'
    manifest_uri = f'gs://based-hardware-agent/agent-vm/releases/{SOURCE_SHA}/manifest.json'
    runner = FakeGcloud(
        {
            startup_uri: startup_for(DIGEST_A),
            manifest_uri: manifest_for(DIGEST_A),
        }
    )
    plan = resolve.resolve_sha_release(
        startup_uri=startup_uri,
        manifest_uri=manifest_uri,
        expected_source_sha=SOURCE_SHA,
        workdir=tmp_path,
        runner=runner,
    )
    assert plan.reuse is True
    assert plan.image_digest == DIGEST_A
    assert any(command[1:4] == ['storage', 'objects', 'describe'] for command in runner.commands)


BROKEN_REUSE_SHELL = (
    'reuse="$(python3 -c \'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["reuse"])\' '
    '"$PLAN")"'
)
FIXED_REUSE_SHELL = (
    'reuse="$(python3 -c \'import json,sys; print(json.dumps(json.load(open(sys.argv[1], encoding="utf-8"))["reuse"]))\' '
    '"$PLAN")"'
)
HELPER_REUSE_SHELL = 'reuse="$(python3 "$REPO/.github/scripts/workflow_json_field_for_shell.py" "$PLAN" reuse)"'


def _reuse_branch_taken(*, extract_snippet: str, plan_path: Path) -> bool:
    script = f"""
set -euo pipefail
PLAN={shlex.quote(str(plan_path))}
{extract_snippet}
if [[ "$reuse" == "true" ]]; then
  echo reuse-branch
else
  echo rebuild-branch
fi
"""
    completed = subprocess.run(['bash', '-c', script], capture_output=True, text=True, check=True)
    return completed.stdout.strip() == 'reuse-branch'


def test_workflow_reuse_shell_contract_takes_reuse_branch_when_resolver_reuses(tmp_path: Path):
    resolve = load_resolve()
    plan_path = tmp_path / 'agent-vm-sha-release.json'
    plan_path.write_text(
        json.dumps(
            {
                'reuse': True,
                'image_digest': DIGEST_A,
                'boot_image': BOOT_IMAGE,
                'manifest_present': True,
                'startup_present': True,
                'reason': 'existing SHA-keyed manifest and startup.sh; reuse that digest',
            }
        ),
        encoding='utf-8',
    )
    assert not _reuse_branch_taken(extract_snippet=BROKEN_REUSE_SHELL, plan_path=plan_path)
    assert _reuse_branch_taken(extract_snippet=FIXED_REUSE_SHELL, plan_path=plan_path)
    helper_snippet = HELPER_REUSE_SHELL.replace('$REPO', str(REPO_DIR))
    assert _reuse_branch_taken(extract_snippet=helper_snippet, plan_path=plan_path)
    assert '32012710785' in resolve.INCIDENT


def test_desktop_backend_workflows_do_not_use_python_repr_for_reuse_boolean():
    broken = 'print(json.load(open(sys.argv[1], encoding="utf-8"))["reuse"])'
    for workflow_name in ('desktop_backend_prod.yml', 'desktop_backend_auto_dev.yml'):
        text = (REPO_DIR / '.github/workflows' / workflow_name).read_text(encoding='utf-8')
        assert broken not in text
