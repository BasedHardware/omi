"""Hermetic tests for the deploy ancestry verifier.

Every network path is exercised through the injectable ``opener`` (or a stubbed
``fetch_compare`` for exit-code mapping), so the suite never reaches GitHub.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import urllib.error
from urllib.request import Request

import pytest

from scripts import verify_deploy_ancestry as verifier

REPOSITORY = 'BasedHardware/omi'
RELEASE_SHA = 'b' * 40
CONTAINS_SHA = 'a' * 40
TOKEN = 'ghp_' + 'c' * 36


class FakeResponse:
    def __init__(self, payload: dict | bytes):
        self._body = payload if isinstance(payload, bytes) else json.dumps(payload).encode('utf-8')

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> 'FakeResponse':
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


def compare_payload(status: str, *, ahead_by: int = 0, behind_by: int = 0, total_commits: int = 0) -> dict:
    return {
        'status': status,
        'ahead_by': ahead_by,
        'behind_by': behind_by,
        'total_commits': total_commits,
        'merge_base_commit': {'sha': 'd' * 40},
    }


def http_error(code: int, body: dict | str) -> urllib.error.HTTPError:
    raw = body if isinstance(body, str) else json.dumps(body)
    return urllib.error.HTTPError(
        'https://api.github.com/compare', code, 'error', {}, io.BytesIO(raw.encode('utf-8'))
    )


def run_main(argv: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> int:
    """Invoke the CLI with a token-free environment and no ambient GITHUB_TOKEN."""
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)
    monkeypatch.delenv('GH_TOKEN', raising=False)
    return verifier.main(argv)


def base_argv(tmp_path: Path, *extra: str) -> list[str]:
    return [
        '--repository',
        REPOSITORY,
        '--release',
        RELEASE_SHA,
        '--contains',
        CONTAINS_SHA,
        '--summary-file',
        str(tmp_path / 'summary.md'),
        *extra,
    ]


@pytest.fixture
def compare_result(monkeypatch: pytest.MonkeyPatch):
    """Stub the network call and record the arguments main() passes to it."""

    calls: list[dict] = []
    state: dict[str, object] = {'result': verifier.CompareResult('ahead', 3, 0, 3, 'd' * 40)}

    def fake_fetch(**kwargs):
        calls.append(kwargs)
        result = state['result']
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(verifier, 'fetch_compare', fake_fetch)
    return state, calls


def test_validate_sha_accepts_full_hex_and_normalizes_case():
    assert verifier.validate_sha(RELEASE_SHA, '--release') == RELEASE_SHA
    assert verifier.validate_sha('A' * 40, '--release') == 'a' * 40
    assert verifier.validate_sha(f'  {RELEASE_SHA}  ', '--release') == RELEASE_SHA


@pytest.mark.parametrize(
    'value',
    [
        '',
        '   ',
        'abc1234',
        'a' * 39,
        'a' * 41,
        'z' * 40,
        'a' * 39 + 'g',
        '0' * 40,
        'HEAD',
    ],
)
def test_validate_sha_rejects_malformed_and_nil_inputs(value: str):
    with pytest.raises(verifier.AncestryInputError):
        verifier.validate_sha(value, '--contains')


@pytest.mark.parametrize('value', ['', 'omi', 'BasedHardware/omi/extra', 'Based Hardware/omi', '/omi'])
def test_validate_repository_rejects_malformed_values(value: str):
    with pytest.raises(verifier.AncestryInputError):
        verifier.validate_repository(value)


def test_sanitize_redacts_explicit_token_literal():
    message = f'request failed for Authorization: Bearer {TOKEN} while calling api'
    assert TOKEN not in verifier.sanitize(message, TOKEN)
    assert verifier.REDACTED in verifier.sanitize(message, TOKEN)


def test_sanitize_redacts_authorization_and_bearer_headers_without_explicit_token():
    message = 'GET /repos/o/r Authorization: token abcdef123456 Bearer xyz789'
    sanitized = verifier.sanitize(message)
    assert 'abcdef123456' not in sanitized
    assert 'xyz789' not in sanitized


def test_sanitize_redacts_known_github_token_prefixes():
    payload = f'bad credentials: {TOKEN} and github_pat_{"e" * 30}'
    sanitized = verifier.sanitize(payload)
    assert TOKEN not in sanitized
    assert 'github_pat_' not in sanitized


def test_fetch_compare_requests_the_contains_to_release_comparison():
    seen: list[Request] = []

    def opener(request: Request, timeout: float) -> FakeResponse:
        seen.append(request)
        assert timeout == 5.0
        return FakeResponse(compare_payload('ahead', ahead_by=2, total_commits=2))

    result = verifier.fetch_compare(
        repository=REPOSITORY,
        contains_sha=CONTAINS_SHA,
        release_sha=RELEASE_SHA,
        token=TOKEN,
        timeout=5.0,
        opener=opener,
    )

    assert result == verifier.CompareResult('ahead', 2, 0, 2, 'd' * 40)
    assert result.contains is True
    request = seen[0]
    assert request.full_url == (
        f'https://api.github.com/repos/{REPOSITORY}/compare/{CONTAINS_SHA}...{RELEASE_SHA}'
    )
    assert request.get_header('Authorization') == f'Bearer {TOKEN}'
    assert request.get_header('Accept') == 'application/vnd.github+json'
    assert request.get_header('User-agent') == verifier.DEFAULT_USER_AGENT


def test_fetch_compare_omits_authorization_when_no_token_is_configured():
    seen: list[Request] = []

    def opener(request: Request, timeout: float) -> FakeResponse:
        seen.append(request)
        return FakeResponse(compare_payload('identical'))

    result = verifier.fetch_compare(
        repository=REPOSITORY,
        contains_sha=CONTAINS_SHA,
        release_sha=CONTAINS_SHA,
        opener=opener,
    )

    assert result.status == 'identical'
    assert seen[0].get_header('Authorization') is None


@pytest.mark.parametrize(
    ('status', 'expected_contains'),
    [('ahead', True), ('identical', True), ('behind', False), ('diverged', False)],
)
def test_compare_status_maps_to_ancestry(status: str, expected_contains: bool):
    def opener(request: Request, timeout: float) -> FakeResponse:
        return FakeResponse(compare_payload(status, ahead_by=1, behind_by=1, total_commits=1))

    result = verifier.fetch_compare(
        repository=REPOSITORY,
        contains_sha=CONTAINS_SHA,
        release_sha=RELEASE_SHA,
        opener=opener,
    )
    assert result.contains is expected_contains


def test_fetch_compare_rejects_unrecognized_status():
    def opener(request: Request, timeout: float) -> FakeResponse:
        return FakeResponse({'status': 'unknown', 'ahead_by': 0, 'behind_by': 0})

    with pytest.raises(verifier.AncestryLookupError):
        verifier.fetch_compare(
            repository=REPOSITORY,
            contains_sha=CONTAINS_SHA,
            release_sha=RELEASE_SHA,
            opener=opener,
        )


def test_fetch_compare_rejects_non_json_body():
    def opener(request: Request, timeout: float) -> FakeResponse:
        return FakeResponse(b'<html>proxy error</html>')

    with pytest.raises(verifier.AncestryLookupError):
        verifier.fetch_compare(
            repository=REPOSITORY,
            contains_sha=CONTAINS_SHA,
            release_sha=RELEASE_SHA,
            opener=opener,
        )


def test_fetch_compare_sanitizes_http_error_bodies():
    def opener(request: Request, timeout: float) -> FakeResponse:
        raise http_error(401, {'message': f'Bad credentials for Authorization: Bearer {TOKEN}'})

    with pytest.raises(verifier.AncestryLookupError) as excinfo:
        verifier.fetch_compare(
            repository=REPOSITORY,
            contains_sha=CONTAINS_SHA,
            release_sha=RELEASE_SHA,
            token=TOKEN,
            opener=opener,
        )

    message = str(excinfo.value)
    assert '401' in message
    assert TOKEN not in message
    assert verifier.REDACTED in message


def test_fetch_compare_wraps_transport_errors():
    def opener(request: Request, timeout: float) -> FakeResponse:
        raise urllib.error.URLError('connection refused')

    with pytest.raises(verifier.AncestryLookupError):
        verifier.fetch_compare(
            repository=REPOSITORY,
            contains_sha=CONTAINS_SHA,
            release_sha=RELEASE_SHA,
            opener=opener,
        )


@pytest.mark.parametrize('status', ['ahead', 'identical'])
def test_main_exits_zero_when_release_contains_expected_ancestor(
    status: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, compare_result, capsys
):
    state, calls = compare_result
    state['result'] = verifier.CompareResult(status, 1, 0, 1, 'd' * 40)

    assert run_main(base_argv(tmp_path), monkeypatch, tmp_path) == verifier.EXIT_CONTAINED

    assert calls[0]['repository'] == REPOSITORY
    assert calls[0]['contains_sha'] == CONTAINS_SHA
    assert calls[0]['release_sha'] == RELEASE_SHA
    assert 'result: verified' in capsys.readouterr().out
    summary = (tmp_path / 'summary.md').read_text(encoding='utf-8')
    assert 'Deploy ancestry check' in summary
    assert 'verified' in summary


@pytest.mark.parametrize('status', ['behind', 'diverged'])
def test_main_exits_one_when_release_does_not_contain_expected_ancestor(
    status: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, compare_result, capsys
):
    state, _ = compare_result
    state['result'] = verifier.CompareResult(status, 0, 4, 4, 'd' * 40)

    assert run_main(base_argv(tmp_path), monkeypatch, tmp_path) == verifier.EXIT_NOT_CONTAINED

    assert 'result: not_contained' in capsys.readouterr().out
    assert 'NOT CONTAINED' in (tmp_path / 'summary.md').read_text(encoding='utf-8')


def test_main_returns_machine_readable_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, compare_result, capsys):
    state, _ = compare_result
    state['result'] = verifier.CompareResult('ahead', 2, 0, 2, 'd' * 40)

    assert run_main(base_argv(tmp_path, '--json'), monkeypatch, tmp_path) == verifier.EXIT_CONTAINED

    record = json.loads(capsys.readouterr().out.strip())
    assert record['contains_expected_ancestor'] is True
    assert record['result'] == 'verified'
    assert record['status'] == 'ahead'
    assert record['release_sha'] == RELEASE_SHA
    assert record['expected_ancestor_sha'] == CONTAINS_SHA


def test_main_rejects_malformed_input_without_calling_github(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, compare_result, capsys
):
    _, calls = compare_result

    assert verifier.main(['--repository', REPOSITORY, '--release', 'HEAD', '--contains', CONTAINS_SHA]) == (
        verifier.EXIT_UNVERIFIED
    )
    assert calls == []
    assert 'ERROR' in capsys.readouterr().err


def test_main_rejects_nil_sentinel(monkeypatch: pytest.MonkeyPatch, compare_result, capsys):
    assert (
        verifier.main(['--repository', REPOSITORY, '--release', RELEASE_SHA, '--contains', '0' * 40])
        == verifier.EXIT_UNVERIFIED
    )
    assert 'nil sentinel' in capsys.readouterr().err


def test_main_returns_unverified_when_github_cannot_answer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, compare_result, capsys
):
    state, _ = compare_result
    state['result'] = verifier.AncestryLookupError(f'GitHub compare request failed with HTTP 404: Not Found {TOKEN}')

    assert run_main(base_argv(tmp_path), monkeypatch, tmp_path) == verifier.EXIT_UNVERIFIED

    captured = capsys.readouterr()
    assert 'UNVERIFIED' in captured.err
    summary = (tmp_path / 'summary.md').read_text(encoding='utf-8')
    assert 'UNVERIFIED' in summary


def test_main_never_prints_the_configured_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, compare_result, capsys
):
    state, calls = compare_result
    state['result'] = verifier.AncestryLookupError(f'Bad credentials for token {TOKEN}')

    argv = [
        '--repository',
        REPOSITORY,
        '--release',
        RELEASE_SHA,
        '--contains',
        CONTAINS_SHA,
        '--token',
        TOKEN,
        '--summary-file',
        str(tmp_path / 'summary.md'),
    ]
    assert verifier.main(argv) == verifier.EXIT_UNVERIFIED

    captured = capsys.readouterr()
    assert TOKEN not in captured.err
    assert TOKEN not in captured.out
    assert TOKEN not in (tmp_path / 'summary.md').read_text(encoding='utf-8')
    assert calls[0]['token'] == TOKEN


def test_main_falls_back_to_github_token_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, compare_result):
    _, calls = compare_result
    monkeypatch.setenv('GITHUB_TOKEN', TOKEN)

    assert verifier.main(base_argv(tmp_path)) == verifier.EXIT_CONTAINED
    assert calls[0]['token'] == TOKEN


def test_main_appends_summary_without_truncating_existing_content(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, compare_result
):
    summary_path = tmp_path / 'summary.md'
    summary_path.write_text('existing step output\n', encoding='utf-8')

    assert run_main(base_argv(tmp_path), monkeypatch, tmp_path) == verifier.EXIT_CONTAINED

    summary = summary_path.read_text(encoding='utf-8')
    assert summary.startswith('existing step output\n')
    assert 'Deploy ancestry check' in summary


def test_main_requires_arguments(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)
    with pytest.raises(SystemExit) as excinfo:
        verifier.main([])
    assert excinfo.value.code == verifier.EXIT_UNVERIFIED
