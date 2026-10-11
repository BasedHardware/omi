"""Active tests for the pending mechanism, not builder acceptance."""
import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('spine_check', ROOT / 'scripts/check_spine_contracts.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def test_marker_removal_is_the_only_permitted_diff():
    original = '@pending("V1")\ndef test_one():\n    assert actual() == 42\n'
    retired = 'def test_one():\n    assert actual() == 42\n'
    assert checker.allowed(original, original)
    assert checker.allowed(original, retired)
    for wrong in ('', retired.replace('42', '0'), retired + '    pass\n', '@pending("V2")\n' + retired):
        assert not checker.allowed(original, wrong)
    assert not checker.allowed(retired, original)
    dart = "contractTest('done', () {\n  pendingContract('C1');\n  body();\n});\n"
    assert checker.allowed(dart, "contractTest('done', () {\n  body();\n});\n")
    assert not checker.allowed(dart, dart.replace('body', 'empty'))


def test_quote_styles_share_listing_owner_and_marker_only_removal():
    for line in ('@pending("V1")', "@pending('V1')", "pendingContract('C1');", 'pendingContract("C1");'):
        match = checker.MARKER.fullmatch(line)
        assert match is not None
        assert next(value for value in match.groups() if value) == ('V1' if line.startswith('@') else 'C1')
        original = line + '\nassert actual() == 42\n'
        assert checker.allowed(original, 'assert actual() == 42\n')
        assert not checker.allowed(original, 'assert actual() == 0\n')
        assert not checker.allowed('assert actual() == 42\n', original)
    for line in ('@pending("V1\')', '@pending("V1") # comment', 'pendingContract(package);'):
        assert checker.MARKER.fullmatch(line) is None


def test_dynamic_marker_calls_are_only_for_active_mechanism_self_tests(tmp_path):
    import json
    def git(*args):
        return subprocess.check_output(['git', '-C', str(tmp_path), *args], text=True)
    git('init', '-q')
    git('config', 'user.name', 'Fixture')
    git('config', 'user.email', 'fixture@example.test')
    registry = {'app/test/spine/self.dart': 'MECHANISM', 'app/test/spine/builder.dart': 'B1'}
    for path in registry:
        file = tmp_path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('pendingContract(package);\n')
    file = tmp_path / checker.REGISTRY
    file.parent.mkdir(parents=True)
    file.write_text(json.dumps(registry))
    git('add', '.')
    git('commit', '-qm', 'fixture')
    git('branch', 'origin/main')
    errors = checker.check(tmp_path)
    assert errors == ['app/test/spine/builder.dart:1: pending markers must be a complete standalone literal call']


def test_pytest_runs_pending_and_xpass_is_red(tmp_path):
    helper = ROOT / 'scripts/dev-harness/tests/spine'
    path = tmp_path / 'test_pending.py'
    path.write_text(f'''import sys
sys.path.insert(0, {str(helper)!r})
from pending import pending
@pending("V1")
def test_pending():
    assert False
@pending("V1")
def test_unexpected_pass():
    pass
''')
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(path)], capture_output=True, text=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'XPASS(strict)' in result.stdout
    assert '1 xfailed' in result.stdout
    path.write_text(path.read_text().replace('assert False', "raise TypeError('bad fixture')"))
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert '2 failed' in result.stdout


def test_revision_pins_exact_bytes_and_preserves_marker_contract(tmp_path):
    import json
    import pytest
    def git(*args):
        return subprocess.check_output(['git', '-C', str(tmp_path), *args], text=True)
    git('init', '-q')
    git('config', 'user.name', 'Fixture')
    git('config', 'user.email', 'fixture@example.test')
    target = 'app/test/spine/example.dart'
    old = "pendingContract('B1');\nexpect(visible, true);\n"
    new = "pendingContract('B1');\nexpect(onstage, true);\n"
    file = tmp_path / target
    file.parent.mkdir(parents=True)
    file.write_text(old)
    registry = {target: 'B1'}
    (tmp_path / checker.REGISTRY).parent.mkdir(parents=True)
    (tmp_path / checker.REGISTRY).write_text(json.dumps(registry))
    git('add', '.')
    git('commit', '-qm', 'original spine')
    git('branch', 'origin/main')
    file.write_text(new)
    assert checker.check(tmp_path)  # body edit without a reviewed record fails
    record = dict(path=target, owner='B1', before=checker.digest(old), after=checker.digest(new), reason='reviewed visibility correction')
    revision = tmp_path / checker.REVISIONS / '001-visible.json'
    revision.parent.mkdir()
    revision.write_text(json.dumps(record))
    assert checker.check(tmp_path) == []
    git('add', '.')
    git('commit', '-qm', 'spine revision')
    assert checker.check(tmp_path) == []
    file.write_text(new.replace('true', 'false'))
    assert checker.check(tmp_path)
    file.write_text(new.replace("pendingContract('B1');\n", ''))
    assert checker.check(tmp_path) == []
    revision.write_text(json.dumps({**record, 'reason': 'builder altered record'}))
    with pytest.raises(ValueError, match='immutable'):
        checker.check(tmp_path)
    revision.unlink()
    with pytest.raises(ValueError, match='cannot be removed'):
        checker.check(tmp_path)
    with pytest.raises(ValueError, match='broken revision chain'):
        checker.revised_original(old, [({**record, 'before': '0' * 64}, new)])
    with pytest.raises(ValueError, match='preserve pending'):
        checker.revised_original(old, [({**record, 'after': checker.digest(new.replace("pendingContract('B1');\n", ''))}, new.replace("pendingContract('B1');\n", ''))])


def test_fake_flutter_advertises_only_b0_registered_extensions(tmp_path):
    import json
    command = [{'id': 1, 'method': 'app.callServiceExtension', 'params': {
        'appId': 'fixture', 'methodName': 'ext.omi.controls.capabilities'}}]
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/dev-harness/tests/spine/fake_flutter.py'),
                             'ok', str(tmp_path / 'wire.jsonl'), 'fixture', 'device'],
                            input=json.dumps(command) + '\n', capture_output=True, text=True, check=True)
    messages = [json.loads(line)[0] for line in result.stdout.splitlines()]
    response = next(message['result'] for message in messages if message.get('id') == 1)
    assert response == {'contract_version': 'semantic-controls/v1',
                        'capabilities': ['capabilities', 'state', 'wait_ready', 'navigate', 'fault']}


def test_revision_cannot_restore_one_marker_by_retiring_another():
    old = '@pending("V1")\ndef test_first():\n    assert visible\n@pending("V1")\ndef test_second():\n    assert ready\n'
    revised = old.replace('assert visible', 'assert onstage')
    base = old.replace('@pending("V1")\n', '', 1)
    wrong = revised.rsplit('@pending("V1")\n', 1)
    wrong = ''.join(wrong)
    assert checker.allowed(revised, wrong)
    assert not checker.retirement_allowed([old, revised], base, wrong)
    assert checker.retirement_allowed([old, revised], base, revised.replace('@pending("V1")\n', '', 1))
    assert checker.retirement_allowed([old, revised], base, revised.replace('@pending("V1")\n', ''))


def test_squashed_spine_revision_keeps_the_corrected_oracle(tmp_path):
    import json
    def git(*args):
        return subprocess.check_output(['git', '-C', str(tmp_path), *args], text=True)
    git('init', '-q')
    git('config', 'user.name', 'Fixture')
    git('config', 'user.email', 'fixture@example.test')
    target = 'app/test/spine/example.dart'
    old = 'assert absent;\n'
    intermediate = 'assert offstage;\n'
    revised = 'assert offstageAndRetained;\n'
    file = tmp_path / target
    file.parent.mkdir(parents=True)
    file.write_text(revised)
    (tmp_path / checker.REGISTRY).parent.mkdir(parents=True)
    (tmp_path / checker.REGISTRY).write_text(json.dumps({target: 'B1'}))
    directory = tmp_path / checker.REVISIONS
    directory.mkdir()
    for index, (before, after) in enumerate([(old, intermediate), (intermediate, revised)]):
        (directory / f'{index:03}.json').write_text(json.dumps(dict(
            path=target, owner='B1', before=checker.digest(before), after=checker.digest(after), reason='spine review')))
    git('add', '.')
    git('commit', '-qm', 'squash of spine plus reviewed corrections')
    git('branch', 'origin/main')
    assert checker.check(tmp_path) == []
    file.write_text(old)
    assert checker.check(tmp_path)  # the old assertion cannot be restored
    file.write_text(revised.replace('offstageAndRetained', 'true'))
    assert checker.check(tmp_path)


def scope_repo(root, grandfather=False):
    import json
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True, stderr=subprocess.DEVNULL)
    git('init', '-q', '-b', 'main')
    git('config', 'user.name', 'Fixture')
    git('config', 'user.email', 'fixture@example.test')
    path = 'app/test/spine/example.dart'
    file = root / path
    file.parent.mkdir(parents=True)
    old = "pendingContract('V1');\nexpect(profile, 'localDev');\n"
    new = old.replace('localDev', 'local_dev')
    file.write_text(old)
    (root / checker.REGISTRY).parent.mkdir(parents=True)
    (root / checker.REGISTRY).write_text(json.dumps({path: 'V1'}))
    runtime = root / 'app/lib/example.dart'
    runtime.parent.mkdir(parents=True)
    runtime.write_text('throw UnimplementedError();\n')
    policy = {'scaffolding': {'app/lib/example.dart': [checker.digest(runtime.read_text())]}}
    if grandfather:
        record = json.dumps(dict(path=path, owner='V1', before=checker.digest(old),
            after=checker.digest(new), reason='wire evidence'))
        policy['grandfathered_revisions'] = {checker.REVISIONS + '/001.json': [checker.digest(record)]}
    (root / checker.SCOPE).write_text(json.dumps(policy))
    git('add', '.')
    git('commit', '-qm', 'accepted contract')
    git('branch', 'origin/main')
    def revise():
        file.write_text(new)
        directory = root / checker.REVISIONS
        directory.mkdir()
        (directory / '001.json').write_text(json.dumps(dict(path=path, owner='V1', before=checker.digest(old),
            after=checker.digest(new), reason='wire evidence')))
    return git, file, runtime, old, new, revise


def test_revision_cannot_travel_with_implementation_even_in_separate_commits(tmp_path):
    git, file, runtime, old, new, revise = scope_repo(tmp_path)
    runtime.write_text('return 1;\n')
    file.write_text(old.replace("pendingContract('V1');\n", ''))
    assert checker.check(tmp_path) == []  # ordinary builder + marker retirement
    git('add', '.')
    git('commit', '-qm', 'implementation')
    revise()
    git('add', '.')
    git('commit', '-qm', 'self-approved revision in another commit')
    assert any('mixed with implementation' in error for error in checker.check(tmp_path))
    runtime.write_text('throw UnimplementedError();\n')
    assert checker.check(tmp_path) == []  # exact accepted skeleton, no implementation
    (tmp_path / checker.SCOPE).write_text('{"oracle_paths":["app/lib/example.dart"]}')
    assert any('immutable' in error for error in checker.check(tmp_path))


def test_real_squash_merge_and_child_merge_preserve_corrected_oracle(tmp_path):
    git, file, runtime, old, new, revise = scope_repo(tmp_path)
    git('switch', '-qc', 'spine')
    revise()
    git('add', '.')
    git('commit', '-qm', 'corrected oracle')
    git('branch', 'child')
    git('switch', '-q', 'main')
    git('merge', '--squash', 'spine')
    git('commit', '-qm', 'squash accepted spine')
    git('branch', '-f', 'origin/main', 'HEAD')  # isolated fixture ref, not the real repository
    assert checker.check(tmp_path) == []
    git('switch', '-q', 'child')
    git('merge', '--no-edit', 'main')
    assert checker.check(tmp_path) == []
    file.write_text(new.replace("pendingContract('V1');\n", ''))
    assert checker.check(tmp_path) == []
    file.write_text(old)
    assert checker.check(tmp_path)


def test_pinned_legacy_correction_survives_old_parent_merge_without_authorizing_new_revision(tmp_path):
    import json
    git, file, runtime, old, new, revise = scope_repo(tmp_path, grandfather=True)
    git('switch', '-qc', 'child')
    revise()
    git('add', '.')
    git('commit', '-qm', 'pinned reviewed correction')
    git('switch', '-q', 'main')
    (tmp_path / 'unrelated.md').write_text('new main work')
    git('add', '.')
    git('commit', '-qm', 'main retains older oracle')
    git('branch', '-f', 'origin/main', 'HEAD')  # isolated fixture only
    git('switch', '-q', 'child')
    git('merge', '--no-edit', 'main')
    runtime.write_text('return 1;\n')
    file.write_text(new.replace("pendingContract('V1');\n", ''))
    assert checker.check(tmp_path) == []
    changed = new.replace('local_dev', 'invented')
    file.write_text(changed)
    record = dict(path='app/test/spine/example.dart', owner='V1', before=checker.digest(new),
        after=checker.digest(changed), reason='builder self-authorization')
    (tmp_path / checker.REVISIONS / '002.json').write_text(json.dumps(record))
    git('add', '.')
    git('commit', '-qm', 'new self-approved revision')
    assert any('mixed with implementation' in error for error in checker.check(tmp_path))


def test_merge_parent_order_preserves_digest_and_marker_verdicts(tmp_path):
    """GitHub's base-first PR merge and the branch have identical oracle bytes."""
    import json
    git, file, runtime, old, revised, revise = scope_repo(tmp_path)
    git('switch', '-qc', 'spine')
    revise()
    git('add', '.')
    git('commit', '-qm', 'first correction')
    final = revised.replace('local_dev', 'verified_local_dev')
    file.write_text(final)
    record = dict(path='app/test/spine/example.dart', owner='V1',
                  before=checker.digest(revised), after=checker.digest(final), reason='second correction')
    (tmp_path / checker.REVISIONS / '002.json').write_text(json.dumps(record))
    git('add', '.')
    git('commit', '-qm', 'second correction')
    branch = git('rev-parse', 'HEAD').strip()
    git('switch', '-q', 'main')
    git('merge', '--squash', 'spine')
    git('commit', '-qm', 'squashed spine; first record payload differs here')
    base = git('rev-parse', 'HEAD').strip()
    git('branch', '-f', 'origin/main', base)  # temporary fixture repo only
    git('switch', '-q', 'spine')
    assert checker.check(tmp_path) == []
    tree = git('rev-parse', 'HEAD^{tree}').strip()
    for parents in [(branch, base), (base, branch)]:
        merge = git('commit-tree', tree, '-p', parents[0], '-p', parents[1], '-m', 'synthetic PR merge').strip()
        git('checkout', '-q', '--detach', merge)
        assert git('rev-parse', 'HEAD^{tree}').strip() == tree
        assert checker.check(tmp_path) == []
        file.write_text(final.replace("pendingContract('V1');\n", ''))
        assert checker.check(tmp_path) == []
        file.write_text(final.replace('verified_local_dev', 'wrong'))
        assert checker.check(tmp_path)  # no matching pinned assertion
        file.write_text(final.replace("pendingContract('V1');", "// pendingContract('V1');"))
        assert checker.check(tmp_path)  # comments are not marker retirement
        file.write_text(final)
    # Main retires the marker. Restoring it must fail in BOTH merge orders.
    git('switch', '-q', 'main')
    file.write_text(final.replace("pendingContract('V1');\n", ''))
    git('add', '.')
    git('commit', '-qm', 'builder retires marker')
    base = git('rev-parse', 'HEAD').strip()
    git('branch', '-f', 'origin/main', base)
    git('checkout', '-q', '--detach', branch)
    assert any('retired markers' in error for error in checker.check(tmp_path))
    for parents in [(branch, base), (base, branch)]:
        merge = git('commit-tree', tree, '-p', parents[0], '-p', parents[1], '-m', 'restored marker').strip()
        git('checkout', '-q', '--detach', merge)
        assert any('retired markers' in error for error in checker.check(tmp_path))


def test_shared_runner_changes_preserve_invocation_not_bytes(tmp_path):
    import json
    import pytest
    git, file, runtime, old, new, revise = scope_repo(tmp_path)
    # Deliberately NOT a repository runner's name: this is a category rule.
    runner = tmp_path / 'ci/ordinary-check.sh'
    runner.parent.mkdir()
    command = 'tool test suite/oracles'
    source = '#!/usr/bin/env bash\nset -euo pipefail\n' + command + '\n'
    runner.write_text(source)
    declaration = tmp_path / checker.RUNNERS
    declaration.write_text(json.dumps({'version': 1, 'runners': [
        {'path': 'ci/ordinary-check.sh', 'invocations': [{'argv': command.split()}]}]}))
    git('add', '.')
    git('commit', '-qm', 'spine invocation contract')
    git('branch', '-f', 'origin/main', 'HEAD')
    # An unrelated contributor adds a legitimate guard to main.
    runner.write_text(source.replace(command, 'echo checking prerequisites\n' + command))
    git('add', '.')
    git('commit', '-qm', 'ordinary shared runner maintenance')
    git('branch', '-f', 'origin/main', 'HEAD')
    assert checker.check(tmp_path) == []
    revise()
    git('add', '.')
    git('commit', '-qm', 'oracle-only revision')
    runner.write_text(runner.read_text() + 'echo done\n')
    assert checker.check(tmp_path) == []
    file.write_text(new.replace('local_dev', 'wrong'))
    assert checker.check(tmp_path)  # legitimate runner changes cannot launder weakening
    file.write_text(new)
    valid = runner.read_text()
    for mutation in [valid.replace(command, '# ' + command),
                     valid.replace(command, 'if false; then\n' + command + '\nfi'),
                     valid.replace(command, 'true || ' + command),
                     valid.replace(command, command + ' --exclude oracles'),
                     valid.replace(command, 'exit 0\n' + command),
                     valid.replace(command, 'if true; then\nexit 0\nfi\n' + command),
                     valid.replace(command, 'cat <<EOF\n' + command + '\nEOF'),
                     valid.replace(command, 'set -- suite/unit\n' + command),
                     valid.replace(command, 'tool() {\n true\n}\n' + command),
                     valid.replace('set -euo pipefail', 'set +e')]:
        runner.write_text(mutation)
        assert checker.check(tmp_path), mutation
    runner.write_text(valid)
    # A builder cannot turn another implementation path into a shared runner.
    declaration.write_text('{"runners":[]}')
    with pytest.raises(ValueError, match='immutable'):
        checker.check(tmp_path)
    # Nor may a committed deletion of a revision hide its historical oracle.
    declaration.write_text(git('show', f'HEAD:{checker.RUNNERS}'))
    file.write_text(old)
    (tmp_path / checker.REVISIONS / '001.json').unlink()
    git('add', '.')
    git('commit', '-qm', 'malicious removal and assertion rollback')
    with pytest.raises(ValueError, match='cannot be removed'):
        checker.check(tmp_path)


def test_rejected_revision_reversion_does_not_poison_builder(tmp_path):
    for separate_commits in (False, True):
        root = tmp_path / str(separate_commits)
        root.mkdir()
        git, file, runtime, old, new, revise = scope_repo(root)
        runtime.write_text('return 1;\n')
        if separate_commits:
            git('add', '.')
            git('commit', '-qm', 'implementation first')
        revise()
        git('add', '.')
        git('commit', '-qm', 'rejected self-authorization')
        assert any('mixed with implementation' in error for error in checker.check(root))
        # The correct remedy: restore the oracle and remove the rejected record.
        file.write_text(old)
        (root / checker.REVISIONS / '001.json').unlink()
        git('add', '.')
        git('commit', '-qm', 'comply with spine review')
        assert checker.check(root) == []
        file.write_text(old.replace("pendingContract('V1');\n", ''))
        assert checker.check(root) == []
        file.write_text(old.replace('expect(profile', '// expect(profile'))
        assert checker.check(root)  # reverting a record never relaxes oracle bytes


def test_authorized_revision_removal_fails_before_and_after_acceptance(tmp_path):
    import pytest
    git, file, runtime, old, new, revise = scope_repo(tmp_path)
    revise()
    git('add', '.')
    git('commit', '-qm', 'oracle-only authorized revision')
    authorized = git('rev-parse', 'HEAD').strip()
    assert checker.check(tmp_path) == []
    (tmp_path / checker.REVISIONS / '001.json').unlink()
    file.write_text(old)
    git('add', '.')
    git('commit', '-qm', 'illegitimate removal of authorized correction')
    with pytest.raises(ValueError, match='cannot be removed'):
        checker.check(tmp_path)
    git('branch', '-f', 'origin/main', authorized)
    with pytest.raises(ValueError, match='cannot be removed'):
        checker.check(tmp_path)


def test_explicit_retired_rendering_is_exact_and_cannot_restore_markers(tmp_path):
    import json
    git, file, runtime, old, new, revise = scope_repo(tmp_path)
    revise()
    retired = new.replace("pendingContract('V1');\n", '') + '\n'
    record_path = tmp_path / checker.REVISIONS / '001.json'
    record = json.loads(record_path.read_text())
    record['retired_sha256'] = checker.digest(retired)
    record_path.write_text(json.dumps(record))
    git('add', '.')
    git('commit', '-qm', 'review exact pending and retired renderings')
    assert checker.check(tmp_path) == []
    git('branch', '-f', 'origin/main', 'HEAD')
    runtime.write_text('return 1;\n')  # implementation may consume the accepted exact rendering
    # A second introduction models the builder copy meeting the spine history.
    git('rm', str(file.relative_to(tmp_path)))
    git('commit', '-qm', 'temporary absence before alternate introduction')
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(retired)
    git('add', '.')
    git('commit', '-qm', 'exact retired rendering from builder history')
    assert checker.check(tmp_path) == []
    file.write_text(retired.replace('local_dev', 'wrong'))
    assert checker.check(tmp_path)
    file.write_text("pendingContract('V1');\n" + retired)
    assert checker.check(tmp_path)
    file.write_text(retired)
    git('branch', '-f', 'origin/main', 'HEAD')
    file.write_text(new)
    assert any('retired markers cannot be restored' in error for error in checker.check(tmp_path))


def test_old_branch_consumes_accepted_squash_without_intermediate_payloads(tmp_path):
    """#14319: older introduction + accepted squash must not demand lost blobs."""
    import json
    import pytest
    for retire_on_main in (False, True):
        root = tmp_path / str(retire_on_main)
        root.mkdir()
        git, file, runtime, old, intermediate, revise = scope_repo(root)
        target = str(file.relative_to(root))
        git('switch', '-qc', 'builder')
        runtime.write_text('return 1;\n')
        git('add', '.')
        git('commit', '-qm', 'builder predates both corrections')
        builder = git('rev-parse', 'HEAD').strip()
        git('switch', '-qc', 'spine', 'main')
        revise()
        git('add', '.')
        git('commit', '-qm', 'first reviewed correction')
        final = intermediate.replace('local_dev', 'verified_local_dev')
        file.write_text(final)
        second = root / checker.REVISIONS / '002.json'
        second.write_text(json.dumps(dict(path=target, owner='V1', before=checker.digest(intermediate),
            after=checker.digest(final), reason='second reviewed correction')))
        git('add', '.')
        git('commit', '-qm', 'second reviewed correction')
        git('switch', '-q', 'main')
        git('merge', '--squash', 'spine')
        git('commit', '-qm', 'accepted squash contains only final payload')
        if retire_on_main:
            file.write_text(final.replace("pendingContract('V1');\n", ''))
            git('add', '.')
            git('commit', '-qm', 'main retires the marker')
        base = git('rev-parse', 'HEAD').strip()
        git('branch', '-f', 'origin/main', base)
        expected = file.read_text()
        # The intermediate exists on an unrelated ref, never in main/builder history.
        versions = git('log', '--full-history', '--format=%H', base, '--', target).splitlines()
        assert all(checker.digest(git('show', f'{sha}:{target}')) != checker.digest(intermediate) for sha in versions)
        for order in ('branch-first', 'base-first'):
            git('checkout', '-q', '--detach', builder if order == 'branch-first' else base)
            git('merge', '--no-ff', '--no-edit', base if order == 'branch-first' else builder)
            assert file.read_text() == expected
            assert checker.check(root) == []
            file.write_text(expected.replace('verified_local_dev', 'wrong'))
            assert checker.check(root)  # matching history cannot launder current assertion edits
            file.write_text(old)
            assert checker.check(root)  # the old introduction is not an acceptable current oracle
            file.write_text(expected.replace("pendingContract('V1');", "// pendingContract('V1');")
                            if not retire_on_main else final)
            assert checker.check(root)  # neither commented nor restored markers pass
            file.write_text(expected)
            if not retire_on_main:
                file.write_text(expected.replace("pendingContract('V1');\n", ''))
                assert checker.check(root) == []
                file.write_text(expected)
        # New records cannot borrow the accepted-prefix exception, even if a
        # cycle ends at the accepted digest again and leaves the current file identical.
        for name, before, after in [('003', final, final.replace('verified_local_dev', 'third')),
                                    ('004', final.replace('verified_local_dev', 'third'), final)]:
            (root / checker.REVISIONS / f'{name}.json').write_text(json.dumps(dict(
                path=target, owner='V1', before=checker.digest(before), after=checker.digest(after), reason='unaccepted batch')))
        file.write_text(final)
        git('add', '.')
        git('commit', '-qm', 'unaccepted revisions without intermediate payload')
        with pytest.raises(ValueError, match='revised bytes do not match pinned digest'):
            checker.check(root)


def test_shared_scaffold_prefix_preserves_target_body_without_authorizing_implementation(tmp_path):
    import json
    import pytest

    def git(*args):
        return subprocess.check_output(['git', '-C', str(tmp_path), *args], text=True, stderr=subprocess.DEVNULL)

    git('init', '-q', '-b', 'main')
    git('config', 'user.name', 'Fixture')
    git('config', 'user.email', 'fixture@example.test')
    path = 'app/lib/shared_owner.dart'  # category rule, not a production filename
    prefix = "export 'typed.dart';\n\n"
    body = "import 'legacy.dart';\n\n// Shared implementation.\n\nvoid existing() { oldBehavior(); }\n"
    runtime = tmp_path / path
    runtime.parent.mkdir(parents=True)
    runtime.write_text(body)
    oracle = 'app/test/spine/example.dart'
    file = tmp_path / oracle
    file.parent.mkdir(parents=True)
    old = "pendingContract('C7');\nexpect(legacy(), true);\n"
    new = old.replace('legacy()', 'typed()')
    file.write_text(old)
    declaration = tmp_path / checker.PREFIXES
    declaration.parent.mkdir(parents=True)
    (tmp_path / checker.REGISTRY).write_text(json.dumps({oracle: 'C7'}))
    (tmp_path / checker.SCOPE).write_text(json.dumps({'scaffolding': {path: [checker.digest(prefix + body)]}}))
    declaration.write_text(json.dumps({'prefixes': [dict(path=path, prefix=prefix,
        scaffold_sha256=checker.digest(prefix + body))]}))
    git('add', '.')
    git('commit', '-qm', 'declare shared scaffold and oracle')
    git('switch', '-qc', 'contract')
    runtime.write_text(prefix + body)
    git('add', '.')
    git('commit', '-qm', 'original frozen scaffold')
    git('switch', '-q', 'main')
    accepted_body = body.replace('oldBehavior', 'privacyFix')
    runtime.write_text(accepted_body)
    git('add', '.')
    git('commit', '-qm', 'independent accepted implementation fix')
    git('branch', 'origin/main')
    git('switch', '-q', 'contract')
    git('merge', '--no-edit', 'main')
    assert runtime.read_text() == prefix + accepted_body
    file.write_text(new)
    record = tmp_path / checker.REVISIONS / '001.json'
    record.parent.mkdir()
    record.write_text(json.dumps(dict(path=oracle, owner='C7', before=checker.digest(old),
        after=checker.digest(new), reason='reviewed direct API boundary')))
    git('add', '.')
    git('commit', '-qm', 'oracle-only revision over accepted shared body')
    assert checker.check(tmp_path) == []
    candidate = git('rev-parse', 'HEAD').strip()
    git('switch', '--detach', 'origin/main')
    git('merge', '--no-ff', '--no-edit', candidate)
    assert checker.check(tmp_path) == []  # BASE-first merge has the same verdict
    # Squash away the branch's original frozen shared-file payload. The reviewed
    # prefix and target body are sufficient; incidentally reachable history is not.
    tree = git('rev-parse', 'HEAD^{tree}').strip()
    squash = git('commit-tree', tree, '-p', 'origin/main', '-m', 'squashed oracle correction').strip()
    git('switch', '--detach', squash)
    assert checker.check(tmp_path) == []
    runtime.write_text(prefix + accepted_body.replace('privacyFix', 'newImplementation'))
    assert any('mixed with implementation' in e for e in checker.check(tmp_path))
    runtime.write_text(prefix + accepted_body)
    file.write_text(new.replace('true', 'false'))
    assert checker.check(tmp_path)  # source-body accommodation cannot weaken oracle pins
    file.write_text(new)
    original_declaration = declaration.read_text()
    declaration.write_text('{"prefixes":[]}')
    with pytest.raises(ValueError, match='immutable'):
        checker.check(tmp_path)
    declaration.unlink()
    with pytest.raises(ValueError, match='cannot be removed'):
        checker.check(tmp_path)
    declaration.write_text(original_declaration)
    assert checker.check(tmp_path) == []
