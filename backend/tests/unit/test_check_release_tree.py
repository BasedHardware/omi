"""Promotion identity: the main merge tree must equal the staging-qualified OMI_RELEASE_TREE."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))

import check_release_tree as crt  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    _git(tmp_path, 'init', '-q', '-b', 'main')
    _git(tmp_path, 'config', 'user.email', 't@example.com')
    _git(tmp_path, 'config', 'user.name', 't')
    (tmp_path / 'a.txt').write_text('one\n')
    _git(tmp_path, 'add', 'a.txt')
    _git(tmp_path, 'commit', '-qm', 'one')
    _git(tmp_path, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_equal_tree_passes_even_when_commit_differs(repo, capsys):
    """A squash merge has a new commit SHA but the same tree as the qualified integration SHA."""

    sha = _git(repo, 'rev-parse', 'HEAD')
    tree = _git(repo, 'rev-parse', 'HEAD^{tree}')
    _git(repo, 'commit', '-q', '--allow-empty', '-m', 'squash of the same tree')
    merge = _git(repo, 'rev-parse', 'HEAD')
    _git(repo, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
    assert merge != sha
    assert crt.main(['verify', '--sha', merge, '--qualified-tree', tree]) == 0
    assert f'TREE_EQUAL {merge} {tree}' in capsys.readouterr().out


def test_main_moved_after_qualification_fails(repo, capsys):
    tree = _git(repo, 'rev-parse', 'HEAD^{tree}')
    (repo / 'a.txt').write_text('two\n')
    _git(repo, 'commit', '-qam', 'main moved')
    _git(repo, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
    assert crt.main(['verify', '--sha', _git(repo, 'rev-parse', 'HEAD'), '--qualified-tree', tree]) == 1
    assert 're-sync integration' in capsys.readouterr().err


def test_sha_not_on_main_fails(repo):
    _git(repo, 'checkout', '-qb', 'side')
    _git(repo, 'commit', '-q', '--allow-empty', '-m', 'side')
    side = _git(repo, 'rev-parse', 'HEAD')
    assert crt.main(['verify', '--sha', side, '--qualified-tree', _git(repo, 'rev-parse', 'HEAD^{tree}')]) == 1


def test_bad_qualified_tree_is_unreadable(repo):
    assert crt.main(['verify', '--sha', 'HEAD', '--qualified-tree', 'abc']) == 2


def _staging_runner(trees: dict[str, str | None], *, split: str | None = None):
    def runner(args):
        if args[0] == 'git':
            return crt.run(args)
        name = args[4]
        if args[2] == 'services':
            traffic = [{'revisionName': f'{name}-r1', 'percent': 100}]
            if name == split:
                traffic = [{'revisionName': f'{name}-r1', 'percent': 50}, {'revisionName': f'{name}-r2', 'percent': 50}]
            # The template carries a different value; only the serving revision counts.
            template = {
                'spec': {'containers': [{'ports': [1], 'env': [{'name': 'OMI_RELEASE_TREE', 'value': '0' * 40}]}]}
            }
            return json.dumps({'spec': {'template': template}, 'status': {'traffic': traffic}})
        service = name.rsplit('-r1', 1)[0]
        env = [] if trees[service] is None else [{'name': 'OMI_RELEASE_TREE', 'value': trees[service]}]
        sidecar = {'name': 'collector', 'env': [{'name': 'OMI_RELEASE_TREE', 'value': 'f' * 40}]}
        return json.dumps({'spec': {'containers': [sidecar, {'name': 'app', 'ports': [1], 'env': env}]}})

    return runner


def test_from_staging_reads_serving_revisions(repo):
    tree = _git(repo, 'rev-parse', 'HEAD^{tree}')
    runner = _staging_runner({name: tree for name in crt.STAGING_SERVICES})
    assert crt.main(['verify', '--sha', 'HEAD', '--from-staging'], runner=runner) == 0


def test_from_staging_requires_agreement_and_single_revision(repo):
    tree = _git(repo, 'rev-parse', 'HEAD^{tree}')
    trees = {name: tree for name in crt.STAGING_SERVICES}
    trees['backend-sync-backfill-staging'] = 'a' * 40
    assert crt.main(['verify', '--sha', 'HEAD', '--from-staging'], runner=_staging_runner(trees)) == 2
    trees['backend-sync-backfill-staging'] = None
    assert crt.main(['verify', '--sha', 'HEAD', '--from-staging'], runner=_staging_runner(trees)) == 2
    same = {name: tree for name in crt.STAGING_SERVICES}
    split = _staging_runner(same, split='backend-staging')
    assert crt.main(['verify', '--sha', 'HEAD', '--from-staging'], runner=split) == 2


def test_worker_digest_promotes_only_for_the_same_tree(repo, tmp_path, capsys):
    sha = _git(repo, 'rev-parse', 'HEAD')
    tree = _git(repo, 'rev-parse', 'HEAD^{tree}')
    labels = tmp_path / 'labels.json'
    labels.write_text(json.dumps({'omi.release.tree': tree, 'org.opencontainers.image.revision': sha}))
    assert crt.main(['image', '--labels-json', str(labels), '--sha', sha]) == 0
    (repo / 'a.txt').write_text('changed\n')
    _git(repo, 'commit', '-qam', 'later')
    assert crt.main(['image', '--labels-json', str(labels), '--sha', 'HEAD']) == 1


def test_worker_digest_falls_back_to_revision_label_and_refuses_unlabelled(repo, tmp_path):
    labels = tmp_path / 'labels.json'
    labels.write_text(json.dumps({'org.opencontainers.image.revision': _git(repo, 'rev-parse', 'HEAD')}))
    assert crt.main(['image', '--labels-json', str(labels), '--sha', 'HEAD']) == 0
    labels.write_text('null')
    assert crt.main(['image', '--labels-json', str(labels), '--sha', 'HEAD']) == 2


def test_diarizer_workflow_promotes_worker_digests_through_the_tree_check():
    import yaml

    workflow = yaml.safe_load((Path(__file__).resolve().parents[3] / '.github/workflows/gcp_diarizer.yml').read_text())
    on = workflow.get(True) or workflow['on']
    assert on['workflow_dispatch']['inputs']['image_digest']['default'] == ''
    steps = {step.get('name'): step for step in workflow['jobs']['deploy']['steps']}
    assert steps['Build and Push Docker image']['if'] == "github.event.inputs.image_digest == ''"
    assert 'omi.release.tree=' in steps['Build and Push Docker image']['run']
    promote = steps['Verify promoted worker digest']
    assert promote['if'] == "github.event.inputs.image_digest != ''"
    assert 'check_release_tree.py image' in promote['run']
    helm = steps['Deploy Diarizer to GKE cluster using Helm']['run']
    assert 'steps.build.outputs.image_digest || steps.promote.outputs.image_digest' in helm
