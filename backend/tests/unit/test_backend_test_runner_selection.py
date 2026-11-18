"""Selection and worker-count behaviour of backend/test.sh, run hermetically.

Each test copies test.sh and scripts/changed-files into a throwaway repository
with a stub selector and a fake pytest, so nothing here runs real backend tests
or depends on the state of the checkout that runs it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from testing.shell import bash_command, bash_path

REPO_ROOT = Path(__file__).resolve().parents[3]
TEST_RUNNER_SOURCE = REPO_ROOT / 'backend' / 'test.sh'
CHANGED_FILES_SOURCE = REPO_ROOT / 'scripts' / 'changed-files'

pytestmark = pytest.mark.skipif(os.name == 'nt', reason='fixture repository uses POSIX executables')

STUB_SELECTOR = '''
import os
import sys
from pathlib import Path

args = sys.argv[1:]
with open(os.environ['SELECTOR_LOG'], 'a', encoding='utf-8') as log:
    log.write(' '.join(args) + '\\n')
if '--changed-files' in args:
    changed = Path(args[args.index('--changed-files') + 1]).read_text(encoding='utf-8')
    Path(os.environ['SELECTOR_CHANGED']).write_text(changed, encoding='utf-8')
    selected = 'tests/unit/test_unique.py\\ntesting/e2e/test_contract_e2e.py\\n'
    reason = 'fixture changed selection'
else:
    selected = 'tests/unit/test_unique.py\\ntests/unit/test_dup.py\\ntesting/e2e/test_contract_e2e.py\\n'
    reason = 'full backend unit suite'
if os.environ.get('SELECTOR_SELECTED'):
    selected = os.environ['SELECTOR_SELECTED'].replace(',', '\\n') + '\\n'
output = Path(args[args.index('--output') + 1])
output.write_text(selected, encoding='utf-8')
if '--reason-output' in args:
    Path(args[args.index('--reason-output') + 1]).write_text(reason + '\\n', encoding='utf-8')
'''


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ['git', '-c', 'user.email=t@t', '-c', 'user.name=t', '-c', 'commit.gpgsign=false', *args],
        cwd=repo,
        env=_clean_environment(),
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _clean_environment() -> dict[str, str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith('GIT_') and not name.startswith('BACKEND_') and name not in {'CI', 'GITHUB_ACTIONS'}
    }
    # The fixture repository must not inherit hooks, signing or templates from the
    # developer's configuration.
    environment['GIT_CONFIG_NOSYSTEM'] = '1'
    environment['GIT_CONFIG_GLOBAL'] = os.devnull
    return environment


class FixtureRepo:
    def __init__(self, root: Path):
        self.root = root
        self.repo = root / 'repo'
        self.backend = self.repo / 'backend'
        self.pytest_log = root / 'pytest.log'
        self.selector_log = root / 'selector.log'
        self.selector_changed = root / 'selector-changed.txt'
        self.bin_dir = root / 'bin'

        (self.repo / 'scripts').mkdir(parents=True)
        shutil.copy2(CHANGED_FILES_SOURCE, self.repo / 'scripts' / 'changed-files')
        (self.backend / 'scripts').mkdir(parents=True)
        shutil.copy2(TEST_RUNNER_SOURCE, self.backend / 'test.sh')
        (self.backend / 'scripts' / 'select_backend_unit_tests.py').write_text(STUB_SELECTOR, encoding='utf-8')
        for relative in (
            'tests/unit/test_unique.py',
            'tests/unit/test_dup.py',
            'tests/services/test_dup.py',
            'testing/e2e/test_contract_e2e.py',
            'utils/module.py',
            'utils/other.py',
        ):
            path = self.backend / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('def test_placeholder():\n    pass\n', encoding='utf-8')

        self.bin_dir.mkdir()
        fake_python = self.bin_dir / 'fake-python'
        fake_python.write_text(
            '#!/usr/bin/env bash\n'
            'if [[ "$1" == "-m" && "$2" == "pytest" ]]; then\n'
            '  shift 2\n'
            '  printf "%s\\n" "${@: -1}" >> "$PYTEST_LOG"\n'
            '  exit 0\n'
            'fi\n'
            f'exec {sys.executable!s} "$@"\n',
            encoding='utf-8',
        )
        fake_python.chmod(0o755)

        subprocess.run(['git', 'init', '-q', str(self.repo)], env=_clean_environment(), check=True)
        _git(self.repo, 'add', '.')
        _git(self.repo, 'commit', '-qm', 'base')
        _git(self.repo, 'update-ref', 'refs/remotes/origin/main', 'HEAD')

    def fake_getconf(self, cores: int) -> None:
        getconf = self.bin_dir / 'getconf'
        getconf.write_text(f'#!/usr/bin/env bash\necho {cores}\n', encoding='utf-8')
        getconf.chmod(0o755)

    def run(self, *args: str, cwd: Path | None = None, **env: str) -> subprocess.CompletedProcess[str]:
        environment = _clean_environment() | {
            'PATH': f'{self.bin_dir}{os.pathsep}{os.environ.get("PATH", "")}',
            'PYTHON': bash_path(self.bin_dir / 'fake-python', cwd=self.backend),
            'PYTEST_LOG': str(self.pytest_log),
            'SELECTOR_LOG': str(self.selector_log),
            'SELECTOR_CHANGED': str(self.selector_changed),
            'BACKEND_PYTEST_WORKERS': '1',
        }
        environment.update(env)
        return subprocess.run(
            bash_command(self.backend / 'test.sh', *args, cwd=self.backend),
            cwd=cwd or self.backend,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )

    def pytest_targets(self) -> list[str]:
        return sorted(self.pytest_log.read_text().splitlines()) if self.pytest_log.exists() else []

    def selector_calls(self) -> list[str]:
        return self.selector_log.read_text().splitlines() if self.selector_log.exists() else []


@pytest.fixture
def fixture_repo(tmp_path):
    return FixtureRepo(tmp_path)


def test_named_files_run_exactly_those_files_in_every_accepted_form(fixture_repo):
    result = fixture_repo.run(
        'tests/unit/test_unique.py',
        'backend/tests/services/test_dup.py',
        'testing/e2e/test_contract_e2e.py::test_placeholder',
        cwd=fixture_repo.backend,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert fixture_repo.pytest_targets() == [
        'testing/e2e/test_contract_e2e.py::test_placeholder',
        'tests/services/test_dup.py',
        'tests/unit/test_unique.py',
    ]
    assert fixture_repo.selector_calls() == [], 'named files must not consult the selector'


def test_bare_names_and_caller_relative_paths_resolve_from_any_directory(fixture_repo):
    from_root = fixture_repo.run('test_unique.py', 'backend/tests/unit/test_dup.py', cwd=fixture_repo.repo)
    assert from_root.returncode == 0, from_root.stdout + from_root.stderr
    from_tests = fixture_repo.run('../services/test_dup.py', cwd=fixture_repo.backend / 'tests' / 'unit')
    assert from_tests.returncode == 0, from_tests.stdout + from_tests.stderr
    assert fixture_repo.pytest_targets() == [
        'tests/services/test_dup.py',
        'tests/unit/test_dup.py',
        'tests/unit/test_unique.py',
    ]


@pytest.mark.parametrize(
    ('arguments', 'expected'),
    [
        (('tests/unit/test_missing.py',), 'tests/unit/test_missing.py: no such file'),
        (('test_missing.py',), 'test_missing.py: no file of that name under backend/tests/'),
        (('test_dup.py',), 'test_dup.py is ambiguous; 2 files'),
        (('tests/unit',), 'tests/unit is a directory'),
        (('../scripts/changed-files',), 'is outside backend/'),
    ],
)
def test_unresolvable_paths_fail_by_name_and_never_fall_back_to_the_suite(fixture_repo, arguments, expected):
    result = fixture_repo.run('tests/unit/test_unique.py', *arguments)
    assert result.returncode == 2
    assert expected in result.stderr
    assert 'no tests were run' in result.stderr
    assert fixture_repo.pytest_targets() == []
    assert fixture_repo.selector_calls() == []


def test_ambiguous_name_lists_every_candidate(fixture_repo):
    result = fixture_repo.run('test_dup.py')
    assert result.returncode == 2
    assert '  tests/services/test_dup.py\n  tests/unit/test_dup.py\n' in result.stderr


@pytest.mark.parametrize(
    'arguments',
    [('--frobnicate',), ('-k', 'name'), ('--all', 'tests/unit/test_unique.py'), ('--all', '--changed'), ('--base',)],
)
def test_unknown_options_and_conflicting_selections_fail_loudly(fixture_repo, arguments):
    result = fixture_repo.run(*arguments)
    assert result.returncode == 2
    assert result.stderr.startswith('test.sh: ')
    assert fixture_repo.pytest_targets() == []
    assert fixture_repo.selector_calls() == []


def test_file_list_environment_is_exclusive_with_other_selections(fixture_repo, tmp_path):
    selected = tmp_path / 'selected.txt'
    selected.write_text('tests/unit/test_dup.py\n', encoding='utf-8')
    conflict = fixture_repo.run('tests/unit/test_unique.py', BACKEND_UNIT_TEST_FILE_LIST=str(selected))
    assert conflict.returncode == 2
    assert 'BACKEND_UNIT_TEST_FILE_LIST is already a selection' in conflict.stderr
    assert fixture_repo.pytest_targets() == []

    alone = fixture_repo.run(BACKEND_UNIT_TEST_FILE_LIST=str(selected))
    assert alone.returncode == 0, alone.stdout + alone.stderr
    assert fixture_repo.pytest_targets() == ['tests/unit/test_dup.py']


def test_changed_selects_branch_commits_and_uncommitted_work_against_the_merge_base(fixture_repo):
    (fixture_repo.backend / 'utils' / 'module.py').write_text('VALUE = 1\n', encoding='utf-8')
    _git(fixture_repo.repo, 'commit', '-qam', 'branch change')
    (fixture_repo.backend / 'utils' / 'other.py').write_text('VALUE = 2\n', encoding='utf-8')
    (fixture_repo.backend / 'utils' / 'untracked.py').write_text('VALUE = 3\n', encoding='utf-8')
    _git(fixture_repo.repo, 'checkout', '-q', '-b', 'later-main', 'origin/main')
    (fixture_repo.repo / 'main-only.txt').write_text('main moved on\n', encoding='utf-8')
    _git(fixture_repo.repo, 'add', 'main-only.txt')
    _git(fixture_repo.repo, 'commit', '-qm', 'main moves')
    _git(fixture_repo.repo, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
    _git(fixture_repo.repo, 'checkout', '-q', '-')

    result = fixture_repo.run('--changed')

    assert result.returncode == 0, result.stdout + result.stderr
    assert fixture_repo.selector_changed.read_text().splitlines() == [
        'backend/utils/module.py',
        'backend/utils/other.py',
        'backend/utils/untracked.py',
    ], 'main-only commits must not count; staged, unstaged and untracked work must'
    assert [call.split()[0] for call in fixture_repo.selector_calls()] == ['--changed-files']
    # CI hands the PR selection to test.sh as an explicit list, which keeps
    # contract-selected hermetic E2E files; --changed must not run less.
    assert fixture_repo.pytest_targets() == ['testing/e2e/test_contract_e2e.py', 'tests/unit/test_unique.py']
    assert 'fixture changed selection' in result.stderr


def test_list_prints_the_selection_without_running_it(fixture_repo):
    result = fixture_repo.run('--list', 'test_unique.py', 'tests/unit/test_unique.py')
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'tests/unit/test_unique.py\n'
    assert fixture_repo.pytest_targets() == []


def test_changed_without_a_resolvable_base_fails_instead_of_running_everything(fixture_repo):
    result = fixture_repo.run('--changed', '--base', 'origin/no-such-branch')
    assert result.returncode == 2
    assert 'cannot resolve origin/no-such-branch' in result.stderr
    assert fixture_repo.selector_calls() == []
    assert fixture_repo.pytest_targets() == []


def test_an_empty_diff_selects_nothing_instead_of_the_full_suite(fixture_repo):
    # The selector maps an empty path list to the full suite; a clean local
    # checkout must not inherit that.
    result = fixture_repo.run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'no changes since' in result.stderr
    assert 'No backend unit tests selected.' in result.stdout
    assert fixture_repo.selector_calls() == []
    assert fixture_repo.pytest_targets() == []


def test_no_selection_runs_changed_locally_and_the_full_suite_in_ci(fixture_repo):
    (fixture_repo.backend / 'utils' / 'module.py').write_text('VALUE = 1\n', encoding='utf-8')
    local = fixture_repo.run()
    assert local.returncode == 0, local.stdout + local.stderr
    assert 'no selection given, so running --changed' in local.stderr
    assert [call.split()[0] for call in fixture_repo.selector_calls()] == ['--changed-files']

    fixture_repo.selector_log.unlink()
    fixture_repo.pytest_log.unlink()
    ci = fixture_repo.run(CI='true')
    assert ci.returncode == 0, ci.stdout + ci.stderr
    assert fixture_repo.selector_calls()[0].startswith('--all')
    # Unchanged CI behaviour: the automatic full selection leaves E2E to its own job.
    assert fixture_repo.pytest_targets() == ['tests/unit/test_dup.py', 'tests/unit/test_unique.py']
    assert 'FULL backend unit suite' not in ci.stderr


def test_explicit_full_suite_locally_prints_the_cheaper_commands_first(fixture_repo):
    result = fixture_repo.run('--all')
    assert result.returncode == 0, result.stdout + result.stderr
    assert '==> test.sh: running the FULL backend unit suite (2 files)' in result.stderr
    assert "bash test.sh --changed" in result.stderr


@pytest.mark.parametrize(
    ('workers', 'ci', 'expected'),
    [
        ('auto', None, '8 file(s) at a time'),
        (None, None, '8 file(s) at a time'),
        ('auto', 'true', '18 file(s) at a time'),
        (None, 'true', '18 file(s) at a time'),
        ('13', None, '13 file(s) at a time'),
        ('13', 'true', '13 file(s) at a time'),
    ],
)
def test_auto_workers_are_bounded_locally_and_keep_every_core_in_ci(fixture_repo, workers, ci, expected):
    fixture_repo.fake_getconf(18)
    environment = {}
    if ci is not None:
        environment['GITHUB_ACTIONS'] = ci
    if workers is None:
        result = fixture_repo.run('tests/unit/test_unique.py', BACKEND_PYTEST_WORKERS='', **environment)
    else:
        result = fixture_repo.run('tests/unit/test_unique.py', BACKEND_PYTEST_WORKERS=workers, **environment)
    assert result.returncode == 0, result.stdout + result.stderr
    assert expected in result.stderr


@pytest.mark.parametrize(('cores', 'expected'), [(10, 5), (3, 2), (2, 2), (1, 1)])
def test_local_auto_is_half_the_cores_but_at_least_two(fixture_repo, cores, expected):
    fixture_repo.fake_getconf(cores)
    result = fixture_repo.run('tests/unit/test_unique.py', BACKEND_PYTEST_WORKERS='auto')
    assert result.returncode == 0, result.stdout + result.stderr
    assert f'test.sh: {expected} file(s) at a time' in result.stderr


def test_invalid_worker_counts_fail_before_running(fixture_repo):
    invalid = fixture_repo.run('tests/unit/test_unique.py', BACKEND_PYTEST_WORKERS='0')
    assert invalid.returncode == 2
    assert 'BACKEND_PYTEST_WORKERS must be a positive integer or auto' in invalid.stderr
    assert fixture_repo.pytest_targets() == []


def _outside_test(fixture_repo) -> Path:
    outside = fixture_repo.root / 'outside'
    outside.mkdir(exist_ok=True)
    target = outside / 'outside_test.py'
    target.write_text('def test_outside():\n    pass\n', encoding='utf-8')
    return target


@pytest.mark.parametrize(
    'argument', ['tests/unit/test_link.py', 'backend/tests/unit/test_link.py', 'tests/unit/linked_dir/outside_test.py']
)
def test_symlinks_that_leave_backend_are_rejected_before_pytest(fixture_repo, argument):
    target = _outside_test(fixture_repo)
    (fixture_repo.backend / 'tests' / 'unit' / 'test_link.py').symlink_to(target)
    (fixture_repo.backend / 'tests' / 'unit' / 'linked_dir').symlink_to(target.parent, target_is_directory=True)
    cwd = fixture_repo.repo if argument.startswith('backend/') else fixture_repo.backend
    result = fixture_repo.run(argument, cwd=cwd)
    assert result.returncode == 2
    assert 'outside backend/' in result.stderr
    assert fixture_repo.pytest_targets() == []


def test_symlink_chain_to_an_outside_file_is_rejected(fixture_repo):
    target = _outside_test(fixture_repo)
    hop = fixture_repo.backend / 'tests' / 'unit' / 'hop.py'
    hop.symlink_to(target)
    (fixture_repo.backend / 'tests' / 'unit' / 'test_chain.py').symlink_to('hop.py')
    result = fixture_repo.run('tests/unit/test_chain.py')
    assert result.returncode == 2
    assert f'resolves through a symlink to {target.resolve()}' in result.stderr
    assert fixture_repo.pytest_targets() == []


def test_bare_name_of_an_outside_symlink_is_not_resolved(fixture_repo):
    (fixture_repo.backend / 'tests' / 'unit' / 'test_link.py').symlink_to(_outside_test(fixture_repo))
    result = fixture_repo.run('test_link.py')
    assert result.returncode == 2
    assert fixture_repo.pytest_targets() == []


def test_symlink_inside_backend_still_runs(fixture_repo):
    (fixture_repo.backend / 'tests' / 'unit' / 'test_alias.py').symlink_to('test_unique.py')
    result = fixture_repo.run('tests/unit/test_alias.py')
    assert result.returncode == 0, result.stdout + result.stderr
    assert fixture_repo.pytest_targets() == ['tests/unit/test_alias.py']


@pytest.mark.parametrize('mode', ['--changed', '--all'])
@pytest.mark.parametrize('selected', ['tests/unit/test_link.py', 'tests/unit/linked_dir/outside_test.py'])
def test_selector_output_that_leaves_backend_through_a_symlink_fails(fixture_repo, mode, selected):
    target = _outside_test(fixture_repo)
    (fixture_repo.backend / 'tests' / 'unit' / 'test_link.py').symlink_to(target)
    (fixture_repo.backend / 'tests' / 'unit' / 'linked_dir').symlink_to(target.parent, target_is_directory=True)
    result = fixture_repo.run(mode, SELECTOR_SELECTED=f'tests/unit/test_unique.py,{selected}')
    assert result.returncode == 2
    assert f'selected {selected} resolves through a symlink to outside backend/' in result.stderr
    assert fixture_repo.pytest_targets() == []


def test_explicit_file_list_keeps_naming_files_anywhere(fixture_repo, tmp_path):
    # BACKEND_UNIT_TEST_FILE_LIST is the caller's own statement; existing callers
    # pass absolute paths outside backend/ and must keep working.
    target = _outside_test(fixture_repo)
    selected = tmp_path / 'selected.txt'
    selected.write_text(f'{target}\n', encoding='utf-8')
    result = fixture_repo.run(BACKEND_UNIT_TEST_FILE_LIST=str(selected))
    assert result.returncode == 0, result.stdout + result.stderr
    assert fixture_repo.pytest_targets() == [str(target)]
