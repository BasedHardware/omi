#!/usr/bin/env python3
"""Prove that a deployed release SHA actually contains an expected ancestor SHA.

Deploy workflows dispatch an immutable release SHA. Operators sometimes expect a
specific merge/commit to be in that release (for example the commit that fixed
the incident being hotfixed) and today can only eyeball a branch listing. This
CLI answers that question mechanically through GitHub's Commits Compare API, so
the check needs no git checkout of either commit and works from any runner with
only a read-only token.

Exit codes are the contract:

* ``0`` -- ``--contains`` is an ancestor of ``--release`` (or they are the same
  commit). The release verifiably includes the expected work.
* ``1`` -- the two commits are unrelated by ancestry (``behind``/``diverged``),
  so the release does NOT contain the expected commit.
* ``2`` -- the question could not be answered: malformed input, missing
  repository/commit, auth or rate-limit failure, transport error, or a response
  that does not carry a compare status. Treat ``2`` as "unverified", never as
  "verified".

Every diagnostic path is sanitized: an authorization token can never be echoed
into workflow logs, step summaries, or exception text.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable, Mapping, Sequence
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_API_URL = 'https://api.github.com'
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_USER_AGENT = 'omi-verify-deploy-ancestry'

EXIT_CONTAINED = 0
EXIT_NOT_CONTAINED = 1
EXIT_UNVERIFIED = 2

# Compare statuses where the compare base (``--contains``) is reachable from the
# compare head (``--release``). ``identical`` is a release that *is* the expected
# commit; it contains the expected work by definition.
CONTAINED_STATUSES = frozenset({'ahead', 'identical'})
KNOWN_STATUSES = frozenset({'ahead', 'behind', 'diverged', 'identical'})

FULL_SHA_PATTERN = re.compile(r'^[0-9a-f]{40}$')
REPOSITORY_PATTERN = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')
NIL_SHA = '0' * 40
REDACTED = '***'

# Order matters: the more specific patterns run first so a partially redacted
# header cannot leave the credential behind. Patterns here keep the scheme label
# in group 1 and the credential in group 2.
_LABELLED_SECRET_PATTERNS = (
    re.compile(r'(?i)(authorization\s*[:=]\s*(?:bearer|token|basic)\s+)([^\s"\',;}]+)'),
    re.compile(r'(?i)(authorization\s*[:=]\s*)([^\s"\',;}]+)'),
    re.compile(r'(?i)(\bbearer\s+)([^\s"\',;}]+)'),
    re.compile(r'(?i)(\b(?:access_)?token\s*[:=]\s*)([^\s"\',;}]+)'),
)

# These match the credential itself, so the whole match is replaced.
_BARE_SECRET_PATTERNS = (
    re.compile(r'\bgh[pousr]_[A-Za-z0-9]{16,}\b'),
    re.compile(r'\bgithub_pat_[A-Za-z0-9_]{16,}\b'),
)


class AncestryInputError(ValueError):
    """An argument is malformed; the ancestry question was never asked."""


class AncestryLookupError(RuntimeError):
    """GitHub could not answer the ancestry question."""


@dataclass(frozen=True)
class CompareResult:
    """The ancestry-relevant slice of a GitHub compare response."""

    status: str
    ahead_by: int
    behind_by: int
    total_commits: int
    merge_base_sha: str | None

    @property
    def contains(self) -> bool:
        return self.status in CONTAINED_STATUSES


def sanitize(text: str, token: str | None = None) -> str:
    """Remove credentials from text destined for a log or summary.

    A caller-supplied token is redacted literally (it may not match any known
    prefix), then the generic Authorization/Bearer/token patterns run so a token
    embedded in a response body or URL is redacted too.
    """
    sanitized = text
    if token:
        # Longest first so overlapping tokens cannot leave a suffix behind.
        for candidate in sorted({token, token.strip()}, key=len, reverse=True):
            if candidate:
                sanitized = sanitized.replace(candidate, REDACTED)
    for pattern in _LABELLED_SECRET_PATTERNS:
        sanitized = pattern.sub(lambda match: f'{match.group(1)}{REDACTED}', sanitized)
    for pattern in _BARE_SECRET_PATTERNS:
        sanitized = pattern.sub(REDACTED, sanitized)
    return sanitized


def validate_sha(value: str, label: str) -> str:
    """Return a normalized full commit SHA or raise AncestryInputError."""
    candidate = (value or '').strip().lower()
    if not candidate:
        raise AncestryInputError(f'{label} is required')
    if candidate == NIL_SHA:
        raise AncestryInputError(f'{label} is the nil sentinel, not a commit')
    if not FULL_SHA_PATTERN.fullmatch(candidate):
        raise AncestryInputError(f'{label} must be one full 40-character hex commit SHA')
    return candidate


def validate_repository(value: str) -> str:
    candidate = (value or '').strip()
    if not candidate:
        raise AncestryInputError('--repository is required (owner/name)')
    if not REPOSITORY_PATTERN.fullmatch(candidate):
        raise AncestryInputError('--repository must look like owner/name')
    return candidate


def build_compare_url(api_url: str, repository: str, contains_sha: str, release_sha: str) -> str:
    base = (api_url or DEFAULT_API_URL).rstrip('/')
    if urllib.parse.urlparse(base).scheme not in ('http', 'https'):
        raise AncestryInputError('--api-url must be an http(s) URL')
    return f'{base}/repos/{repository}/compare/{contains_sha}...{release_sha}'


def _extract_compare_payload(payload: Any) -> CompareResult:
    if not isinstance(payload, Mapping):
        raise AncestryLookupError('compare response is not a JSON object')
    status = payload.get('status')
    if not isinstance(status, str) or status not in KNOWN_STATUSES:
        raise AncestryLookupError('compare response carried no recognized status')
    merge_base = payload.get('merge_base_commit')
    merge_base_sha = merge_base.get('sha') if isinstance(merge_base, Mapping) else None
    if merge_base_sha is not None and not isinstance(merge_base_sha, str):
        merge_base_sha = None
    return CompareResult(
        status=status,
        ahead_by=_as_int(payload.get('ahead_by')),
        behind_by=_as_int(payload.get('behind_by')),
        total_commits=_as_int(payload.get('total_commits')),
        merge_base_sha=merge_base_sha,
    )


def _as_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def fetch_compare(
    *,
    repository: str,
    contains_sha: str,
    release_sha: str,
    token: str | None = None,
    api_url: str = DEFAULT_API_URL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> CompareResult:
    """Ask GitHub whether ``contains_sha`` is an ancestor of ``release_sha``.

    ``opener`` is injectable so unit tests never touch the network.
    """
    url = build_compare_url(api_url, repository, contains_sha, release_sha)
    headers = {
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': DEFAULT_USER_AGENT,
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'
    request = urllib.request.Request(url, headers=headers, method='GET')
    try:
        with opener(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = _read_error_detail(exc)
        raise AncestryLookupError(
            sanitize(f'GitHub compare request failed with HTTP {exc.code}: {detail}', token)
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, 'reason', exc)
        raise AncestryLookupError(sanitize(f'GitHub compare request failed: {reason}', token)) from None

    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        raise AncestryLookupError('GitHub compare response was not valid JSON') from None
    return _extract_compare_payload(payload)


def _read_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read()
    except Exception:  # pragma: no cover - defensive: a broken error stream is not worth raising
        return '<no response body>'
    if not raw:
        return '<no response body>'
    text = raw.decode('utf-8', errors='replace').strip()
    try:
        payload = json.loads(text)
    except ValueError:
        return text[:500]
    if isinstance(payload, Mapping) and isinstance(payload.get('message'), str):
        return payload['message'][:500]
    return text[:500]


def describe_result(result: CompareResult, *, contains_sha: str, release_sha: str, repository: str) -> dict[str, Any]:
    """Build the machine-readable record shared by stdout and the step summary."""
    return {
        'repository': repository,
        'release_sha': release_sha,
        'expected_ancestor_sha': contains_sha,
        'status': result.status,
        'ahead_by': result.ahead_by,
        'behind_by': result.behind_by,
        'total_commits': result.total_commits,
        'merge_base_sha': result.merge_base_sha,
        'contains_expected_ancestor': result.contains,
        'result': 'verified' if result.contains else 'not_contained',
    }


def render_text(record: Mapping[str, Any]) -> str:
    lines = [
        f"repository: {record['repository']}",
        f"release: {record['release_sha']}",
        f"expected_ancestor: {record['expected_ancestor_sha']}",
        f"compare_status: {record['status']}",
        f"ahead_by: {record['ahead_by']}",
        f"behind_by: {record['behind_by']}",
        f"merge_base: {record['merge_base_sha'] or 'unknown'}",
        f"result: {record['result']}",
    ]
    return '\n'.join(lines)


def render_summary(record: Mapping[str, Any]) -> str:
    verdict = (
        '**verified** — the release contains the expected ancestor'
        if record['contains_expected_ancestor']
        else '**NOT CONTAINED** — the release does not contain the expected ancestor'
    )
    return '\n'.join(
        [
            '### Deploy ancestry check',
            '',
            '| Field | Value |',
            '| --- | --- |',
            f"| Repository | `{record['repository']}` |",
            f"| Release SHA | `{record['release_sha']}` |",
            f"| Expected ancestor | `{record['expected_ancestor_sha']}` |",
            f"| Compare status | `{record['status']}` |",
            f"| Ahead / behind | {record['ahead_by']} / {record['behind_by']} |",
            f"| Merge base | `{record['merge_base_sha'] or 'unknown'}` |",
            f'| Result | {verdict} |',
            '',
        ]
    )


def append_summary(path: Path, block: str) -> None:
    with path.open('a', encoding='utf-8') as handle:
        handle.write(block)
        if not block.endswith('\n'):
            handle.write('\n')


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Exit 0 iff --contains is an ancestor of --release (GitHub Commits Compare API).',
    )
    parser.add_argument('--repository', required=True, help='GitHub repository as owner/name')
    parser.add_argument('--release', required=True, help='Full 40-hex release commit SHA that was deployed')
    parser.add_argument('--contains', required=True, help='Full 40-hex commit SHA the release must contain')
    parser.add_argument('--token', default=None, help='GitHub token. Defaults to GITHUB_TOKEN, then GH_TOKEN.')
    parser.add_argument('--api-url', default=DEFAULT_API_URL, help=f'GitHub API base URL (default {DEFAULT_API_URL})')
    parser.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT_SECONDS, help='Request timeout in seconds')
    parser.add_argument('--json', action='store_true', help='Emit the machine-readable record instead of text')
    parser.add_argument('--summary-file', type=Path, default=None, help='Append a Markdown block, e.g. $GITHUB_STEP_SUMMARY')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    token = args.token or os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN') or None

    try:
        repository = validate_repository(args.repository)
        contains_sha = validate_sha(args.contains, '--contains')
        release_sha = validate_sha(args.release, '--release')
        url = build_compare_url(args.api_url, repository, contains_sha, release_sha)
    except AncestryInputError as exc:
        print(f'ERROR: {sanitize(str(exc), token)}', file=sys.stderr)
        return EXIT_UNVERIFIED

    if args.timeout <= 0:
        print('ERROR: --timeout must be positive', file=sys.stderr)
        return EXIT_UNVERIFIED

    try:
        result = fetch_compare(
            repository=repository,
            contains_sha=contains_sha,
            release_sha=release_sha,
            token=token,
            api_url=args.api_url,
            timeout=args.timeout,
        )
    except AncestryLookupError as exc:
        message = sanitize(f'UNVERIFIED: {exc}', token)
        print(message, file=sys.stderr)
        if args.summary_file is not None:
            append_summary(
                args.summary_file,
                '\n'.join(
                    [
                        '### Deploy ancestry check',
                        '',
                        f"UNVERIFIED for release `{release_sha}` against expected ancestor `{contains_sha}`.",
                        '',
                        f'`{message}`',
                        '',
                    ]
                ),
            )
        return EXIT_UNVERIFIED

    record = describe_result(result, contains_sha=contains_sha, release_sha=release_sha, repository=repository)
    if args.json:
        print(json.dumps(record, sort_keys=True))
    else:
        print(render_text(record))
        print(f'compared: {sanitize(url, token)}', file=sys.stderr)

    if args.summary_file is not None:
        append_summary(args.summary_file, render_summary(record))

    return EXIT_CONTAINED if result.contains else EXIT_NOT_CONTAINED


if __name__ == '__main__':
    sys.exit(main())
