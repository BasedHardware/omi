#!/usr/bin/env python3
"""Reviewed, named subsets of the monitoring export (SCA-2119).

A production dispatch normally applies the whole dashboard allowlist and the
whole alert export. The stuck-state census only owns one dashboard and the
rules its registry renders, so it needs a reviewed subset instead of a second
copy of the provisioning logic: this module resolves a scope name to the exact
dashboard files and alert sources it selects.

Fail-closed rules, all enforced offline before any Grafana call:

* a scope must name at least one existing dashboard file and alert source;
* dashboard files are bare filenames resolved under the dashboards tree, and
  alert sources are paths under ``alerts/``; nothing is globbed or guessed;
* two scopes may not select the same dashboard file or alert source, so no
  object is written by two releases;
* unknown fields are rejected, so a misspelled key cannot silently select
  nothing.

The default provisioning path never loads this file, so existing behaviour and
every unrelated definition stay exactly as they were.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MONITORING = ROOT / 'backend' / 'charts' / 'monitoring'
SCOPES = MONITORING / 'provisioning-scopes.json'
DASHBOARDS = MONITORING / 'dashboards'
ALERTS = MONITORING / 'alerts'
NAME = re.compile(r'[a-z][a-z0-9-]*\Z')
FIELDS = ('description', 'dashboard_files', 'alert_sources')


@dataclass(frozen=True)
class Scope:
    name: str
    description: str
    dashboards: tuple[Path, ...]
    alert_sources: tuple[Path, ...]


def _names(value: object, field: str, name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f'{name}: {field} must be a nonempty list')
    if any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f'{name}: {field} entries must be nonempty strings')
    if len(set(value)) != len(value):
        raise ValueError(f'{name}: {field} entries must be unique')
    return list(value)


def _dashboard(filename: str, name: str, root: Path) -> Path:
    if '/' in filename or '\\' in filename or not filename.endswith('.json'):
        raise ValueError(f'{name}: dashboard entry {filename} must be a bare .json filename')
    matches = sorted(root.rglob(filename))
    if len(matches) != 1:
        raise ValueError(f'{name}: dashboard {filename} resolves to {len(matches)} files')
    return matches[0]


def _alert_source(source: str, name: str, root: Path) -> Path:
    if not source.startswith('alerts/') or '/' in source[len('alerts/') :] or not source.endswith('.json'):
        raise ValueError(f'{name}: alert source {source} must be a file directly under alerts/')
    path = root / source
    if not path.is_file():
        raise ValueError(f'{name}: alert source {source} is absent')
    return path


def load(path: Path = SCOPES, *, dashboards: Path = DASHBOARDS, monitoring: Path = MONITORING) -> dict[str, Scope]:
    paths = (Path(path), Path(dashboards), Path(monitoring))
    payload = json.loads(paths[0].read_text())
    if not isinstance(payload, dict) or not payload:
        raise ValueError('scopes must be a nonempty object')
    scopes: dict[str, Scope] = {}
    seen_dashboards: dict[Path, str] = {}
    seen_sources: dict[Path, str] = {}
    for name, entry in payload.items():
        if not isinstance(name, str) or not NAME.match(name):
            raise ValueError(f'invalid scope name {name!r}')
        if not isinstance(entry, dict) or set(entry) != set(FIELDS):
            raise ValueError(f'{name}: scope must declare exactly {",".join(FIELDS)}')
        if not isinstance(entry['description'], str) or not entry['description'].strip():
            raise ValueError(f'{name}: description must be a nonempty string')
        dashboards_in_scope = tuple(
            _dashboard(item, name, paths[1]) for item in _names(entry['dashboard_files'], 'dashboard_files', name)
        )
        sources = tuple(
            _alert_source(item, name, paths[2]) for item in _names(entry['alert_sources'], 'alert_sources', name)
        )
        for item in dashboards_in_scope:
            if item in seen_dashboards:
                raise ValueError(f'{name}: dashboard {item.name} is already selected by {seen_dashboards[item]}')
            seen_dashboards[item] = name
        for item in sources:
            if item in seen_sources:
                raise ValueError(f'{name}: alert source {item.name} is already selected by {seen_sources[item]}')
            seen_sources[item] = name
        scopes[name] = Scope(name, entry['description'], dashboards_in_scope, sources)
    return scopes


def resolve(name: str, path: Path = SCOPES, *, dashboards: Path = DASHBOARDS, monitoring: Path = MONITORING) -> Scope:
    scopes = load(path, dashboards=dashboards, monitoring=monitoring)
    if name not in scopes:
        raise ValueError(f'unknown monitoring scope {name!r}; known: {",".join(sorted(scopes))}')
    return scopes[name]


def source_rule_uids(source: Path) -> list[str]:
    """UIDs a split alert source contributes, in file order; no live read."""
    payload = json.loads(Path(source).read_text())
    if not isinstance(payload, list) or not payload:
        raise ValueError(f'{Path(source).name}: alert source must be a nonempty list')
    uids = []
    for rule in payload:
        if not isinstance(rule, dict) or not isinstance(rule.get('uid'), str) or not rule['uid']:
            raise ValueError(f'{Path(source).name}: alert source rule has no UID')
        if rule['uid'] in uids:
            raise ValueError(f'{Path(source).name}: duplicate rule UID {rule["uid"]}')
        uids.append(rule['uid'])
    return uids


def select_uids(scope: Scope) -> list[str]:
    """Every UID the scope owns, in source order, with duplicates rejected."""
    uids: list[str] = []
    for source in scope.alert_sources:
        for uid in source_rule_uids(source):
            if uid in uids:
                raise ValueError(f'{scope.name}: rule {uid} is selected by two sources')
            uids.append(uid)
    if not uids:
        raise ValueError(f'{scope.name}: scope selects no alert rules')
    return uids
