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
