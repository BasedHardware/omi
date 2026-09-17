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
