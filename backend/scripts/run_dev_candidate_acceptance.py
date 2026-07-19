#!/usr/bin/env python3
"""Run source-owned smoke commands against exact no-traffic Cloud Run candidate URLs.

The evidence report deliberately contains only service names, bounded contract
categories, and outcomes. Candidate URLs, identity tokens, request data, and
subprocess output never enter the report or workflow logs from this runner.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / 'backend/deploy/dev_candidate_acceptance.json'
IDENTITY_TOKEN_ENV = 'CLOUD_RUN_IDENTITY_TOKEN'


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


def mint_cloud_run_identity_token(*, audience: str) -> str:
    result = subprocess.run(
        ['gcloud', 'auth', 'print-identity-token', f'--audiences={audience}'],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    token = result.stdout.strip()
    if result.returncode != 0 or not token or len(token) > 8192:
        raise RuntimeError('candidate identity-token acquisition failed')
    return token


def run_check(check: CandidateCheck, *, base_url: str, audience: str) -> CheckOutcome:
    identity_token = ''
    try:
        identity_token = mint_cloud_run_identity_token(audience=audience)
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
        return CheckOutcome(
            service=check.service, contract=check.contract, status='PASS' if result.returncode == 0 else 'FAIL'
        )
    except (OSError, RuntimeError):
        return CheckOutcome(service=check.service, contract=check.contract, status='FAIL')
    finally:
        identity_token = ''


def evidence_document(outcomes: Sequence[CheckOutcome]) -> dict[str, Any]:
    status = 'PASS' if outcomes and all(outcome.status == 'PASS' for outcome in outcomes) else 'FAIL'
    return {
        'schema_version': 1,
        'status': status,
        'checks': [
            {'service': outcome.service, 'contract': outcome.contract, 'status': outcome.status} for outcome in outcomes
        ],
    }


def write_evidence(path: Path, outcomes: Sequence[CheckOutcome]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence_document(outcomes), indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--candidate', action='append', default=[], metavar='SERVICE=URL')
    parser.add_argument('--audience', action='append', default=[], metavar='SERVICE=URL')
    parser.add_argument('--evidence-path', type=Path, required=True)
    args = parser.parse_args(argv)
    outcomes: list[CheckOutcome] = []
    try:
        checks = load_manifest(args.manifest)
        expected_services = {check.service for check in checks}
        candidate_urls = parse_candidate_urls(args.candidate, expected_services=expected_services)
        audiences = parse_candidate_urls(args.audience, expected_services=expected_services)
        for index, check in enumerate(checks):
            outcome = run_check(check, base_url=candidate_urls[check.service], audience=audiences[check.service])
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
