from __future__ import annotations

import importlib.util
import json
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


def test_workflows_resolve_before_rebuild_and_keep_the_compare_gate():
    resolve = load_resolve()
    for workflow_name in ('desktop_backend_prod.yml', 'desktop_backend_auto_dev.yml'):
        text = (REPO_DIR / '.github/workflows' / workflow_name).read_text(encoding='utf-8')
        assert 'resolve_agent_vm_sha_release.py' in text
        assert 'gcloud storage cp --no-clobber "$rendered_startup" "$startup_uri_gs"' in text
        assert 'cmp -s "$rendered_startup" "$startup_readback"' in text
        assert 'cmp -s "$manifest" "$manifest_readback"' in text
        assert text.index('resolve_agent_vm_sha_release.py') < text.index('docker build --tag "$agent_image"')
        assert '32012710785' in resolve.INCIDENT


def test_production_workflow_stages_the_resolver_with_immutable_controls():
    workflow = (REPO_DIR / '.github/workflows/desktop_backend_prod.yml').read_text(encoding='utf-8')
    stage = 'cp .workflow-source/backend/scripts/resolve_agent_vm_sha_release.py ' '"$controls/backend/scripts/"'
    invoke = 'python3 "$DESKTOP_BACKEND_CONTROLS/backend/scripts/resolve_agent_vm_sha_release.py"'
    assert stage in workflow
    assert invoke in workflow
    assert workflow.index(stage) < workflow.index('rm -rf .workflow-source')
