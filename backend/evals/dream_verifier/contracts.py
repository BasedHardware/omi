"""Offline snapshots using the production evidence projection without service imports."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from models.agent_refs import base_ref, cited_value

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parents[1]


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@lru_cache(maxsize=1)
def production_projection() -> dict[str, Any]:
    """Load ONLY pure definitions from trusted checked-out first-party source.

    Importing dream_verify normally imports the session, database, encryption and
    account clients. The eval needs its exact projector, not those services. AST
    extraction executes no imports, decorators, or unrelated top-level code.
    A contract test requires this extraction to keep matching known definitions.
    """
    path = BACKEND / 'utils/dream_verify.py'
    source = ast.parse(path.read_text())
    names = {'evidence', 'minimal_context', 'batches', 'disposition'}
    selected: list[ast.stmt] = [
        node
        for node in source.body
        if (isinstance(node, ast.FunctionDef) and node.name in names)
        or (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == 'INSTRUCTIONS' for target in node.targets)
        )
    ]
    if {node.name for node in selected if isinstance(node, ast.FunctionDef)} != names:
        raise ValueError('production_projection_contract_changed')
    namespace: dict[str, Any] = {
        'base_ref': base_ref,
        'cited_value': cited_value,
        'serialized_bytes': lambda value: len(
            json.dumps(value, ensure_ascii=False, default=str, separators=(',', ':')).encode()
        ),
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


@dataclass
class Snapshot:
    id: str
    kind: str
    operation_data: dict[str, Any]
    refs: tuple[str, ...]
    records: dict[str, Any]

    @property
    def operation(self) -> SimpleNamespace:
        return SimpleNamespace(**self.operation_data)

    def payload(self) -> dict[str, Any]:
        return {'id': self.id, 'kind': self.kind, 'operation': copy.deepcopy(self.operation_data)}

    @classmethod
    def from_item(cls, item: dict[str, Any]) -> Snapshot:
        staged = item['staged']
        return cls(item['id'], staged['kind'], staged['operation'], tuple(staged['refs']), staged['records'])


def project(snapshot: Snapshot) -> dict[str, Any]:
    return production_projection()['evidence'](snapshot)


def model_input(item: dict[str, Any]) -> dict[str, Any]:
    """Allowlist the immutable model-facing surface; never include gold or records."""
    row = copy.deepcopy(item['verifier_input'])
    if set(row) != {'id', 'kind', 'operation', 'evidence'} or row['id'] != item['id']:
        raise ValueError('invalid_verifier_input')
    if digest(row) != item['evidence_sha256'] or row != project(Snapshot.from_item(item)):
        raise ValueError('evidence_snapshot_mismatch')
    return row


def load_items(path: Path) -> list[dict[str, Any]]:
    items = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    ids = [item['id'] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate_item_ids')
    for item in items:
        model_input(item)
        if item['gold'] not in {'accept', 'reject'}:
            raise ValueError('invalid_gold')
    return items
