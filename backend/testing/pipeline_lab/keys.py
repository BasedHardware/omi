"""Stage cache keys (DESIGN L12).

key = sha256 over the canonical JSON of:

- the stage name and the stage's schema version (bump it when a driver's output shape changes);
- the input artifact hashes, by name (upstream stage outputs, corpus files);
- the git **tree** hash of ``backend/`` at the ref, not the commit sha, so refs whose
  backend is byte-identical share cache entries;
- the overlay hash (env and pinned serving decisions; key order does not matter);
- the resolved model configuration hash.

Anything not listed here does not invalidate a cache entry: the run id, the
commit sha, wall-clock time, the worktree path, and changes outside ``backend/``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping

from testing.pipeline_lab.contracts import STAGES, canonical_json

KEY_VERSION = 1


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_json(value: Any) -> str:
    """sha256 of canonical JSON (sorted keys, no whitespace, UTF-8)."""
    return sha256_hex(canonical_json(value).encode('utf-8'))


def hash_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def overlay_hash(overlay: Mapping[str, Any] | None) -> str:
    return hash_json(dict(overlay or {}))


def model_config_hash(model_config: Mapping[str, Any] | None) -> str:
    return hash_json(dict(model_config or {}))


@dataclass(frozen=True)
class CacheKey:
    stage: str
    backend_tree: str
    inputs: Mapping[str, str] = field(default_factory=dict)
    overlay: Mapping[str, Any] = field(default_factory=dict)
    model_config: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def material(self) -> dict[str, Any]:
        if not self.backend_tree:
            raise ValueError('cache key needs the backend tree hash')
        return {
            'key_version': KEY_VERSION,
            'stage': self.stage,
            'schema_version': self.schema_version,
            'inputs': {str(name): str(value) for name, value in self.inputs.items()},
            'backend_tree': self.backend_tree,
            'overlay': overlay_hash(self.overlay),
            'model_config': model_config_hash(self.model_config),
        }

    def hexdigest(self) -> str:
        return hash_json(self.material())


def stage_key(
    stage: str,
    *,
    backend_tree: str,
    inputs: Mapping[str, str] | None = None,
    overlay: Mapping[str, Any] | None = None,
    model_config: Mapping[str, Any] | None = None,
    schema_version: int = 1,
) -> str:
    """The L12 key for one stage (or one item inside a stage; namespace the stage name, e.g. ``notes``)."""
    base = stage.split(':', 1)[0]
    if base not in STAGES:
        raise ValueError(f'unknown stage {stage!r}')
    return CacheKey(
        stage=stage,
        backend_tree=backend_tree,
        inputs=dict(inputs or {}),
        overlay=dict(overlay or {}),
        model_config=dict(model_config or {}),
        schema_version=schema_version,
    ).hexdigest()
