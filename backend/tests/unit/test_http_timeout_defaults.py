"""Guard against the "silent default-drift" bug class in utils/.

Two outbound-call shapes inherit a provider/library default that either hangs
forever or drifts across versions when we don't pin it explicitly:

  * ``httpx.get/post/...`` one-shot calls with no ``timeout=`` block until the
    peer gives up (httpx applies its 5s default only to the client object, not
    to these module-level one-shots' underlying connection lifecycle the way we
    rely on) — a stalled peer can wedge conversation finalization.
  * bare ``OpenAI()`` / ``AsyncOpenAI()`` inherit the SDK default of a 10-minute
    timeout and 2 retries, so a single stalled call ties up the path for ~30min.

This is the same class as the Anthropic prompt-cache TTL regression (relying on
a provider default that changed under us). New code in utils/ must pass an
explicit ``timeout=``. If you have a legitimate unbounded call, set
``timeout=None`` explicitly so the intent is visible in review.
"""

import ast
from collections import deque
import os
import re
import shutil
import subprocess

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UTILS_DIR = os.path.join(BACKEND_DIR, 'utils')

_HTTPX_ONE_SHOT = {'get', 'post', 'put', 'delete', 'patch', 'request', 'head', 'options'}
_LLM_CLIENT_CTORS = {'OpenAI', 'AsyncOpenAI'}
_RELEVANT_CALL_REGEX = r'(?:httpx\s*\.\s*(?:get|post|put|delete|patch|request|head|options)|(?:Async)?OpenAI)\s*\('
_RELEVANT_CALL_PATTERN = re.compile(_RELEVANT_CALL_REGEX.encode())


def _has_timeout(node: ast.Call) -> bool:
    return any(kw.arg == 'timeout' for kw in node.keywords)


def _call_nodes(tree: ast.AST):
    """Keep every call and its order without walking names/constants/contexts."""
    pending = deque([tree])
    while pending:
        node = pending.popleft()
        if isinstance(node, ast.Call):
            yield node
        # These grammar leaves cannot contain another call. In particular,
        # keep all other expressions, decorators, annotations and defaults.
        pending.extend(
            child
            for child in ast.iter_child_nodes(node)
            if child._fields and not isinstance(child, (ast.Name, ast.Constant))
        )


def _violations_in_file(filepath: str) -> list:
    with open(filepath, 'rb') as f:
        source_bytes = f.read()

    if not _RELEVANT_CALL_PATTERN.search(source_bytes):
        return []

    source = source_bytes.decode('utf-8')
    tree = ast.parse(source, filename=filepath)

    found = []

    for node in _call_nodes(tree):
        if _has_timeout(node):
            continue
        func = node.func
        # httpx.<one-shot>(...) with no timeout
        if (
            isinstance(func, ast.Attribute)
            and func.attr in _HTTPX_ONE_SHOT
            and isinstance(func.value, ast.Name)
            and func.value.id == 'httpx'
        ):
            found.append((node.lineno, f'httpx.{func.attr}'))
        # OpenAI()/AsyncOpenAI() with no timeout
        elif isinstance(func, ast.Name) and func.id in _LLM_CLIENT_CTORS:
            found.append((node.lineno, f'{func.id}()'))

    return found


def _candidate_files():
    if shutil.which('rg'):
        result = subprocess.run(
            ['rg', '--files-with-matches', '--null', '--glob', '*.py', _RELEVANT_CALL_REGEX, UTILS_DIR],
            check=False,
            capture_output=True,
        )
        if result.returncode not in (0, 1):
            raise RuntimeError(result.stderr.decode('utf-8', errors='replace'))
        return [path.decode() for path in result.stdout.split(b'\0') if path]

    if shutil.which('git'):
        # Checkout runners always have Git but need not have ripgrep. Use its
        # native scanner rather than reading every Python file in this process.
        # --no-index also includes untracked/ignored files and works outside a
        # checkout; the broader name prefilter leaves the AST rule unchanged.
        result = subprocess.run(
            ['git', 'grep', '--no-index', '-l', '-z', '-E', 'httpx|OpenAI', '--', '*.py'],
            cwd=UTILS_DIR,
            check=False,
            capture_output=True,
        )
        if result.returncode not in (0, 1):
            raise RuntimeError(result.stderr.decode('utf-8', errors='replace'))
        return [os.path.join(UTILS_DIR, path.decode()) for path in result.stdout.split(b'\0') if path]

    return [
        os.path.join(root, name)
        for root, _dirs, files in os.walk(UTILS_DIR)
        if '__pycache__' not in root
        for name in files
        if name.endswith('.py')
    ]


def test_utils_outbound_calls_pin_timeout():
    offenders = {}
    for path in _candidate_files():
        hits = _violations_in_file(path)
        if hits:
            offenders[os.path.relpath(path, BACKEND_DIR)] = hits

    assert not offenders, (
        "Outbound calls missing an explicit timeout= (inherit a hang-prone provider "
        "default). Pass timeout=<seconds>, or timeout=None to opt out on purpose:\n"
        + "\n".join(f"  {f}: {hits}" for f, hits in sorted(offenders.items()))
    )


@pytest.mark.parametrize(
    'source, expected',
    [
        ('OpenAI()', [(1, 'OpenAI()')]),
        ('AsyncOpenAI(timeout=2)', []),
        ('httpx.get("url")', [(1, 'httpx.get')]),
        ('httpx.post("url", timeout=0.1)', []),
        ('def f():\n    return {"x": httpx.get("url")}', [(2, 'httpx.get')]),
        ('nested(OpenAI(), httpx.get("url"))', [(1, 'OpenAI()'), (1, 'httpx.get')]),
        ('text = "OpenAI()"\nnamespace.OpenAI()', []),
        ('hint = "httpx.get("\nℎttpx.get("url")', [(2, 'httpx.get')]),
        ('@decorator(OpenAI())\ndef f(x=AsyncOpenAI()):\n    return x', [(2, 'AsyncOpenAI()'), (1, 'OpenAI()')]),
    ],
)
def test_timeout_guard_retains_ast_call_coverage(tmp_path, source, expected):
    path = tmp_path / 'example.py'
    path.write_text(source, encoding='utf-8')
    assert _violations_in_file(str(path)) == expected


def test_git_fallback_includes_hidden_untracked_and_ignored_python(tmp_path, monkeypatch):
    directory = tmp_path / 'utils'
    (directory / '.hidden').mkdir(parents=True)
    (directory / 'sub dir').mkdir()
    (directory / '.gitignore').write_text('ignored.py\n', encoding='utf-8')
    expected = [directory / '.hidden' / 'client.py', directory / 'sub dir' / 'client.py', directory / 'ignored.py']
    for path in expected:
        path.write_text('OpenAI()\n', encoding='utf-8')
    (directory / 'notes.txt').write_text('OpenAI()\n', encoding='utf-8')
    (directory / 'plain.py').write_text('value = 1\n', encoding='utf-8')
    original_which = shutil.which
    monkeypatch.setattr(shutil, 'which', lambda name: None if name == 'rg' else original_which(name))
    monkeypatch.setitem(globals(), 'UTILS_DIR', str(directory))
    assert set(_candidate_files()) == {str(path) for path in expected}


def test_python_fallback_remains_available_without_search_binaries(tmp_path, monkeypatch):
    directory = tmp_path / 'utils'
    directory.mkdir()
    path = directory / 'client.py'
    path.write_text('OpenAI()\n', encoding='utf-8')
    monkeypatch.setattr(shutil, 'which', lambda name: None)
    monkeypatch.setitem(globals(), 'UTILS_DIR', str(directory))
    assert _candidate_files() == [str(path)]
