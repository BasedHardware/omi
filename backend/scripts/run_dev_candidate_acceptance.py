#!/usr/bin/env python3
"""Run source-owned smoke commands against exact no-traffic Cloud Run candidate URLs.

The evidence report deliberately contains only service names, bounded contract
categories, and outcomes. Candidate URLs, identity tokens, request data, and
subprocess output never enter the report or workflow logs from this runner.

Failure diagnostics are bounded on purpose: each failure carries only a stage
name, an integer returncode or HTTP status, and a short failure-class enum.
Raw subprocess stderr, token material, URLs, and response bodies never enter
the report even when diagnostics are attached.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / 'backend/deploy/dev_candidate_acceptance.json'
IDENTITY_TOKEN_ENV = 'CLOUD_RUN_IDENTITY_TOKEN'

# Diagnostic classes are enum strings only; never carry raw stderr, tokens,
# URLs, or response bodies into evidence documents or raised errors.
MINT_STAGE = 'mint'
PROBE_STAGE = 'probe'
CLASS_AUTH_NO_CREDENTIALS = 'auth_no_credentials'
CLASS_FEDERATED_TOKEN_ERROR = 'federated_token_error'
CLASS_TIMEOUT = 'timeout'
CLASS_TOKEN_OVERSIZED = 'token_oversized'
CLASS_HTTP_FAILURE = 'http_failure'
CLASS_CONN_ERROR = 'conn_error'
CLASS_UNKNOWN = 'unknown'

# Bounded probe failure markers matched (lowercased) in smoke stderr text; the
# matched fragments themselves never enter diagnostics, only the class enum does.
_HTTP_FAILURE_PATTERN = 'received http '
_TIMEOUT_PATTERN = 'could not reach the '


@dataclass(frozen=True)
class CandidateCheck:
    service: str
    contract: str
    command: tuple[str, ...]


@dataclass(frozen=True)
class CheckOutcome:
    service: str
    contract: str
    status: str
    diagnostics: Mapping[str, Any] | None = None


def _absolute_https_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != 'https' or not parsed.netloc or value != value.strip():
        raise ValueError('candidate URL must be an absolute HTTPS URL')
    return value.rstrip('/')


def load_manifest(path: Path) -> list[CandidateCheck]:
    try:
        document = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError('candidate acceptance manifest is unreadable') from error
    if not isinstance(document, Mapping) or document.get('schema_version') != 1:
        raise ValueError('candidate acceptance manifest has an unsupported schema')
    services = document.get('services')
    if not isinstance(services, Mapping) or not services:
        raise ValueError('candidate acceptance manifest must contain services')
    checks: list[CandidateCheck] = []
    for service, raw_check in sorted(services.items()):
        if not isinstance(service, str) or not service or not isinstance(raw_check, Mapping):
            raise ValueError('candidate acceptance manifest contains an invalid service entry')
        contract = raw_check.get('contract')
        command = raw_check.get('command')
        if (
            not isinstance(contract, str)
            or not contract
            or not isinstance(command, list)
            or not command
            or not all(isinstance(part, str) and part for part in command)
            or '{base_url}' not in command
        ):
            raise ValueError(f'candidate acceptance manifest has an invalid command for {service}')
        checks.append(CandidateCheck(service=service, contract=contract, command=tuple(command)))
    return checks


def parse_candidate_urls(values: Sequence[str], *, expected_services: set[str]) -> dict[str, str]:
    urls: dict[str, str] = {}
    for value in values:
        service, separator, raw_url = value.partition('=')
        if not separator or service not in expected_services or service in urls:
            raise ValueError('candidate URL inputs must map every declared service exactly once')
        urls[service] = _absolute_https_url(raw_url)
    if set(urls) != expected_services:
        raise ValueError('candidate URL inputs must map every declared service exactly once')
    return urls


def _classify_mint_stderr(stderr: str) -> str:
    lowered = (stderr or '').lower()
    if 'no authorized account' in lowered or 'credentials could not be found' in lowered:
        return CLASS_AUTH_NO_CREDENTIALS
    if 'invalid_grant' in lowered or 'refresh token' in lowered or 'token endpoint' in lowered:
        return CLASS_FEDERATED_TOKEN_ERROR
    if 'timed out' in lowered or 'timeout' in lowered:
        return CLASS_TIMEOUT
    return CLASS_UNKNOWN


def mint_cloud_run_identity_token(*, audience: str, impersonate: str | None = None) -> str:
    # Under a WIF-federated session the caller has no private key, so the
    # default self-signing mint fails (observed: rc=1, class=unknown in bake
    # 35340203517). Explicit impersonation routes the mint through the IAM
    # signJwt API, which the federated credential CAN call when it holds
    # roles/iam.serviceAccountTokenCreator on the target SA.
    command = ['gcloud', 'auth', 'print-identity-token', f'--audiences={audience}']
    if impersonate:
        command += [f'--impersonate-service-account={impersonate}']
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    token = result.stdout.strip()
    if result.returncode != 0 or not token or len(token) > 8192:
        if result.returncode == 0 and len(token) > 8192:
            mint_class = CLASS_TOKEN_OVERSIZED
        else:
            mint_class = _classify_mint_stderr(result.stderr)
        raise RuntimeError(
            'candidate identity-token acquisition failed',
            {
                'stage': MINT_STAGE,
                'rc': int(result.returncode),
                'class': mint_class,
            },
        ) from None
    return token


def _classify_probe_stderr(stderr: str) -> str:
    lowered = (stderr or '').lower()
    if _TIMEOUT_PATTERN in lowered or 'timed out' in lowered or 'timeout' in lowered:
        return CLASS_TIMEOUT
    if _HTTP_FAILURE_PATTERN in lowered:
        return CLASS_HTTP_FAILURE
    if 'connection refused' in lowered:
        return 'conn_refused'
    if (
        'name or service not known' in lowered
        or 'temporary failure in name resolution' in lowered
        or 'nodename nor servname' in lowered
    ):
        return 'conn_dns'
    if 'connection reset' in lowered:
        return 'conn_reset'
    if 'certificate verify failed' in lowered or 'ssl' in lowered:
        return 'conn_tls'
    if (
        'no route to host' in lowered
        or 'network is unreachable' in lowered
        or 'cannot assign requested address' in lowered
    ):
        return 'conn_unreachable'
    return CLASS_UNKNOWN


def _parse_probe_http_status(stderr: str) -> int | None:
    lowered = (stderr or '').lower()
    marker = lowered.rfind(_HTTP_FAILURE_PATTERN)
    if marker == -1:
        return None
    digits = ''
    for char in lowered[marker + len(_HTTP_FAILURE_PATTERN) :]:
        if char.isdigit():
            digits += char
        else:
            break
    if not digits:
        return None
    status = int(digits)
    return status if 100 <= status <= 599 else None


def run_check(check: CandidateCheck, *, base_url: str, audience: str, impersonate: str | None = None) -> CheckOutcome:
    identity_token = ''
    try:
        identity_token = mint_cloud_run_identity_token(audience=audience, impersonate=impersonate)
        environment = dict(os.environ)
        environment[IDENTITY_TOKEN_ENV] = identity_token
        command = [part.replace('{base_url}', base_url) for part in check.command]
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        if result.returncode == 0:
            return CheckOutcome(service=check.service, contract=check.contract, status='PASS')
        http_status = _parse_probe_http_status(result.stderr)
        diagnostics: dict[str, Any] = {
            'stage': PROBE_STAGE,
            'service': check.service,
            'http_status': http_status,
            'class': _classify_probe_stderr(result.stderr),
        }
        if http_status is not None:
            diagnostics['class'] = CLASS_HTTP_FAILURE
        return CheckOutcome(
            service=check.service,
            contract=check.contract,
            status='FAIL',
            diagnostics=diagnostics,
        )
    except (OSError, RuntimeError) as exc:
        diagnostics: dict[str, Any] = {
            'stage': PROBE_STAGE,
            'service': check.service,
            'http_status': None,
            'class': CLASS_CONN_ERROR,
        }
        # A mint failure raises RuntimeError with its own diagnostics payload
        # (stage=mint); surface that verbatim instead of mislabeling it as a
        # probe connection error.
        if len(exc.args) > 1 and isinstance(exc.args[1], dict):
            diagnostics = dict(exc.args[1])
        return CheckOutcome(
            service=check.service,
            contract=check.contract,
            status='FAIL',
            diagnostics=diagnostics,
        )
    finally:
        identity_token = ''


def evidence_document(outcomes: Sequence[CheckOutcome]) -> dict[str, Any]:
    status = 'PASS' if outcomes and all(outcome.status == 'PASS' for outcome in outcomes) else 'FAIL'
    checks: list[dict[str, Any]] = []
    for outcome in outcomes:
        entry: dict[str, Any] = {'service': outcome.service, 'contract': outcome.contract, 'status': outcome.status}
        if outcome.status == 'FAIL' and outcome.diagnostics:
            entry['diagnostics'] = dict(outcome.diagnostics)
        checks.append(entry)
    return {
        'schema_version': 1,
        'status': status,
        'checks': checks,
    }


def write_evidence(path: Path, outcomes: Sequence[CheckOutcome]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence_document(outcomes), indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--candidate', action='append', default=[], metavar='SERVICE=URL')
    parser.add_argument('--audience', action='append', default=[], metavar='SERVICE=URL')
    parser.add_argument(
        '--mint-impersonate',
        default=os.environ.get('CLOUD_RUN_IDENTITY_MINT_IMPERSONATE') or None,
        help='Service account to impersonate when minting identity tokens '
        '(required under WIF-federated sessions, which hold no signing key).',
    )
    parser.add_argument('--evidence-path', type=Path, required=True)
    args = parser.parse_args(argv)
    outcomes: list[CheckOutcome] = []
    try:
        checks = load_manifest(args.manifest)
        expected_services = {check.service for check in checks}
        candidate_urls = parse_candidate_urls(args.candidate, expected_services=expected_services)
        audiences = parse_candidate_urls(args.audience, expected_services=expected_services)
        for index, check in enumerate(checks):
            outcome = run_check(
                check,
                base_url=candidate_urls[check.service],
                audience=audiences[check.service],
                impersonate=args.mint_impersonate,
            )
            outcomes.append(outcome)
            if outcome.status != 'PASS':
                outcomes.extend(
                    CheckOutcome(service=skipped.service, contract=skipped.contract, status='NOT_RUN')
                    for skipped in checks[index + 1 :]
                )
                break
    except ValueError:
        outcomes.append(CheckOutcome(service='candidate-acceptance', contract='configuration', status='FAIL'))
    finally:
        write_evidence(args.evidence_path, outcomes)
    document = evidence_document(outcomes)
    print(
        f"Candidate acceptance {document['status']}: "
        + ', '.join(f'{outcome.service}/{outcome.contract}={outcome.status}' for outcome in outcomes)
    )
    return 0 if document['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
