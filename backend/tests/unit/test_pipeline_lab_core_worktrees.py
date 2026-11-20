"""Pipeline-lab pinned worktrees, tree hashes and the arm runner, on a throwaway git repo. Synthetic only."""

import json
import os
import shutil
import subprocess
import sys

import pytest

from testing.pipeline_lab import worktrees as w

PROBE = '''
import json, os, sys
import testing.pipeline_lab.contracts as contracts
print(json.dumps({
    "lab_x": os.environ.get("LAB_X"),
    "gac": os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
    "pins": [k for k in os.environ if k.endswith("_SERVE_UID_SHA256S")],
    "isolated": sys.flags.isolated,
    "cwd": os.getcwd(),
    "lab_from_arm": contracts.__file__.startswith(os.getcwd()),
    "argv": sys.argv[1:],
}))
'''


def _plain_git():
    """A git binary that is not a host wrapper (some hosts confine worktree destinations)."""
    candidates = [os.path.join(d, 'git') for d in os.environ.get('PATH', '').split(os.pathsep)]
    for candidate in [*candidates, '/usr/bin/git', '/opt/homebrew/bin/git']:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            with open(candidate, 'rb') as stream:
                if b'managed git wrapper' not in stream.read(4096):
                    return candidate
    return shutil.which('git')


def _git(repo, *args):
    subprocess.run(
        ['git', '-C', str(repo), '-c', 'user.name=Lab Test', '-c', 'user.email=lab@example.invalid', *args],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path, monkeypatch):
    # The host's managed git wrapper only allows worktrees under $OMI_WORKTREES.
    monkeypatch.setenv('OMI_WORKTREES', str(tmp_path / 'wt'))
    monkeypatch.setenv(w.GIT_ENV, _plain_git())
    monkeypatch.delenv(w.WORKTREES_ENV, raising=False)
    root = tmp_path / 'repo'
    (root / 'backend').mkdir(parents=True)
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    (root / 'backend' / 'labprobe.py').write_text(PROBE)
    (root / 'backend' / 'requirements.txt').write_text('fake==1\n')
    (root / 'README.md').write_text('one\n')
    _git(root, 'add', '-A')
    _git(root, 'commit', '-qm', 'one')
    _git(root, 'tag', 'v1')
    (root / 'README.md').write_text('two\n')  # outside backend/
    _git(root, 'commit', '-qam', 'two')
    _git(root, 'tag', 'v2')
    (root / 'backend' / 'other.py').write_text('X = 1\n')
    _git(root, 'add', '-A')
    _git(root, 'commit', '-qm', 'three')
    _git(root, 'tag', 'v3')
    return root


def test_tree_hash_ignores_changes_outside_backend(repo):
    assert w.resolve_ref(repo, 'v1') != w.resolve_ref(repo, 'v2')
    assert w.tree_hash(repo, 'v1') == w.tree_hash(repo, 'v2')
    assert w.tree_hash(repo, 'v3') != w.tree_hash(repo, 'v2')


def test_bad_refs_are_refused(repo):
    with pytest.raises(w.WorktreeError):
        w.resolve_ref(repo, 'no-such-ref')
    with pytest.raises(w.WorktreeError):
        w.resolve_ref(repo, '--upload-pack=x')


def test_ensure_is_idempotent_and_detached(repo, tmp_path):
    first = w.ensure_worktree(repo, 'v1')
    again = w.ensure_worktree(repo, 'v1')
    assert first == again
    assert first.path == tmp_path / 'wt' / 'omi' / f'pipeline-lab-{first.sha[:12]}'
    assert first.backend_tree == w.tree_hash(repo, 'v1')
    branch = subprocess.run(
        ['git', '-C', str(first.path), 'symbolic-ref', '-q', 'HEAD'], capture_output=True, text=True
    )
    assert branch.returncode != 0  # detached


def test_verify_refuses_moved_head_and_dirty_backend(repo):
    tree = w.ensure_worktree(repo, 'v1')
    with pytest.raises(w.WorktreeError):
        w.verify_worktree(tree.path, w.resolve_ref(repo, 'v3'))
    (tree.backend / 'labprobe.py').write_text('# edited\n')
    with pytest.raises(w.WorktreeError):
        w.ensure_worktree(repo, 'v1')


def test_verify_refuses_untracked_source_under_backend(repo):
    tree = w.ensure_worktree(repo, 'v1')
    (tree.backend / 'notes.txt').write_text('inert\n')
    w.verify_worktree(tree.path, w.resolve_ref(repo, 'v1'))
    (tree.backend / 'shadow.py').write_text('# not in the pin\n')
    with pytest.raises(w.WorktreeError, match='untracked source'):
        w.verify_worktree(tree.path, w.resolve_ref(repo, 'v1'))


def test_worktrees_never_under_home_workspace(repo, tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    with pytest.raises(w.WorktreeError):
        w.ensure_worktree(repo, 'v1', root=tmp_path / 'home' / 'workspace' / 'omi')
    monkeypatch.setenv(w.WORKTREES_ENV, str(tmp_path / 'home' / 'workspace'))
    with pytest.raises(w.WorktreeError):
        w.worktree_root()


def test_arm_env_scrubs_credentials_and_applies_overlay():
    env = w.arm_env(
        {'LAB_X': '1', 'PYTHONPATH': 'explicit'},
        base={'GOOGLE_APPLICATION_CREDENTIALS': '/k', 'NOTES_SERVE_UID_SHA256S': 'x', 'PYTHONPATH': '/p', 'KEEP': 'y'},
    )
    assert env == {'LAB_X': '1', 'PYTHONPATH': 'explicit', 'KEEP': 'y'}


def test_run_arm_uses_arm_product_code_and_vendored_lab(repo, monkeypatch):
    tree = w.ensure_worktree(repo, 'v1')
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', '/tmp/should-not-pass')
    monkeypatch.setenv('FOO_SERVE_UID_SHA256S', 'abc')
    result = w.run_arm(tree.backend, 'labprobe', ['--flag', 'v'], overlay={'LAB_X': 'on'}, timeout=50)
    assert result.returncode == 0, result.stderr
    probe = json.loads(result.stdout)
    assert probe['lab_x'] == 'on'
    assert probe['gac'] is None and probe['pins'] == []
    assert probe['isolated'] == 1
    assert probe['cwd'] == str(tree.backend.resolve())
    assert probe['lab_from_arm'] is False  # lab package comes from the harness, product code from the arm
    assert probe['argv'] == ['--flag', 'v']
    assert result.command[0] == sys.executable


def test_lockfile_check(tmp_path):
    a, b = tmp_path / 'a', tmp_path / 'b'
    a.mkdir()
    b.mkdir()
    (a / 'pylock.toml').write_text('x')
    (b / 'pylock.toml').write_text('x')
    w.check_lockfile(a, b)
    (b / 'pylock.toml').write_text('y')
    with pytest.raises(w.WorktreeError):
        w.check_lockfile(a, b)
