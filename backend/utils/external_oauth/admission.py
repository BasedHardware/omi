"""Fail-closed admission for production OAuth clients and scope evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from utils.external_oauth.contracts import Connector
from utils.external_oauth.scopes import GRANT_FAMILIES, SCOPE_REGISTRY_REVISION, scope_digest


class AdmissionDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class DeploymentFacts:
    environment: str
    project_number: str
    oauth_client_id: str
    redirect_uri: str


@dataclass(frozen=True)
class AdmittedClient:
    connector: Connector
    project_alias: str
    client_alias: str
    redirect_uri: str


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def load_manifest(path: Path) -> Mapping[str, object]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise AdmissionDenied('oauth admission manifest is not an object')
    return data


def admit_connector(
    manifest: Mapping[str, object], connector: Connector, facts: DeploymentFacts, *, now_iso_date: str
) -> AdmittedClient:
    if facts.environment != 'production':
        raise AdmissionDenied('external OAuth runtime is production-admitted only through explicit evidence')
    if manifest.get('schema_version') != 1 or manifest.get('scope_registry_revision') != SCOPE_REGISTRY_REVISION:
        raise AdmissionDenied('oauth admission manifest revision mismatch')
    connectors = manifest.get('connectors')
    if not isinstance(connectors, dict):
        raise AdmissionDenied('oauth admission manifest has no connectors')
    entry = connectors.get(connector.value)
    if not isinstance(entry, dict) or entry.get('enabled') is not True:
        raise AdmissionDenied('connector kill switch is closed')

    required_strings = ('project_alias', 'client_alias', 'project_number_sha256', 'client_id_sha256', 'redirect_uri')
    if any(not isinstance(entry.get(name), str) or not entry[name] for name in required_strings):
        raise AdmissionDenied('oauth admission identity evidence is incomplete')
    expected_alias = GRANT_FAMILIES[connector].client_alias
    if entry['project_alias'] != expected_alias or entry['client_alias'] != expected_alias:
        raise AdmissionDenied('oauth project/client alias mismatch')
    if entry['project_number_sha256'] != _digest(facts.project_number):
        raise AdmissionDenied('oauth project evidence mismatch')
    if entry['client_id_sha256'] != _digest(facts.oauth_client_id):
        raise AdmissionDenied('oauth client evidence mismatch')
    if entry['redirect_uri'] != facts.redirect_uri:
        raise AdmissionDenied('oauth redirect evidence mismatch')
    if entry.get('scope_digest') != scope_digest(GRANT_FAMILIES[connector].scopes):
        raise AdmissionDenied('oauth scope evidence mismatch')

    verification = entry.get('verification')
    if not isinstance(verification, dict) or verification.get('approved') is not True:
        raise AdmissionDenied('Google verification is not proven')
    if not isinstance(verification.get('evidence_id'), str) or not verification['evidence_id']:
        raise AdmissionDenied('Google verification evidence is missing')
    if not isinstance(verification.get('valid_through'), str) or verification['valid_through'] < now_iso_date:
        raise AdmissionDenied('Google verification evidence is stale')

    if connector == Connector.GMAIL:
        casa = entry.get('casa')
        if not isinstance(casa, dict) or casa.get('approved') is not True:
            raise AdmissionDenied('Gmail CASA is not proven')
        if not isinstance(casa.get('evidence_id'), str) or not casa['evidence_id']:
            raise AdmissionDenied('Gmail CASA evidence is missing')
        if not isinstance(casa.get('valid_through'), str) or casa['valid_through'] < now_iso_date:
            raise AdmissionDenied('Gmail CASA evidence is stale')

    return AdmittedClient(
        connector=connector,
        project_alias=str(entry['project_alias']),
        client_alias=str(entry['client_alias']),
        redirect_uri=str(entry['redirect_uri']),
    )
