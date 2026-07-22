#!/usr/bin/env python3
"""Cross-resource shared-config migration guard — the 2026-07-22 incident root fix.

The production Pusher outage was a *non-atomic cross-resource migration*: a
shared key (``REDIS_DB_HOST``) stopped materializing in its source while live
workloads still referenced the old source/key. New/replaced pods failed before
startup until capacity reached zero, while public ``/health`` stayed green and
masked the real-time outage.

This guard fails CLOSED before any mutation when a serving workload still
references a ConfigMap/Secret source or key that the proposed state removes or
reclassifies. It reads only object and key NAMES — it never reads, prints, or
stores ConfigMap/Secret VALUES.

It scans BOTH binding styles a pod uses to consume shared config:

* explicit per-key refs (``env[].valueFrom.configMapKeyRef`` / ``secretKeyRef``);
* whole-object bulk loads (``envFrom[].configMapRef`` / ``secretRef``) — every
  key in a bulk-loaded object becomes a pod env var, so removing ANY key from a
  bulk-loaded object is the same outage class and is flagged when a previous
  inventory is supplied to model the transition.

Inputs (all name-only, value-free):
  * ``--rendered`` (repeatable): Helm ``template`` output (one or more YAML
    documents; every pod-template workload — Deployment/StatefulSet/DaemonSet/
    Job/CronJob/ReplicaSet — is scanned, including ``initContainers``).
  * ``--source-inventory``: proposed state — which keys each ConfigMap/Secret
    object will carry after the change.
  * ``--previous-inventory`` (optional): current live source key names. Required
    to detect a key *removed* from a bulk-loaded (``envFrom``) object.

Exit 0 only when every reference resolves to a key present in the proposed
inventory and no key was removed from a bulk-loaded object. Anything ambiguous
or missing fails closed.

Run as::

  python -m backend.scripts.verify_shared_config_migration \\
      --rendered <helm-template.yaml> \\
      --source-inventory <proposed-keys.yaml>

Stdlib-only: runs in the pre-push lane before backend dependencies install.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

# An explicit per-key ConfigMap/Secret reference extracted from a container env.
# (env_name, kind, object_name, key) — kind is "configmap" or "secret".
Reference = tuple[str, str, str, str]
_ENVFROM_KIND_BY_FIELD = {"configMapRef": "configmap", "secretRef": "secret"}
_VALUEFROM_KIND_BY_FIELD = {"configMapKeyRef": "configmap", "secretKeyRef": "secret"}

# Workload kinds that carry a pod template we know how to reach.
POD_TEMPLATE_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "ReplicaSet"}
# Container lists inside a pod spec that may declare env bindings.
_CONTAINER_LIST_KEYS = ("initContainers", "containers", "ephemeralContainers")


class MigrationGuardError(ValueError):
    """Raised when rendered references are inconsistent with proposed sources."""


def _documents(path: str) -> list[dict[str, Any]]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise MigrationGuardError(f"could not read {path}: {exc}") from exc
    docs = [doc for doc in yaml.safe_load_all(text) if isinstance(doc, dict)]
    if not docs:
        raise MigrationGuardError(f"{path} contained no YAML documents")
    return docs


def _pod_spec(doc: dict[str, Any]) -> dict[str, Any] | None:
    """Return the pod-template spec for a workload kind, or None."""
    if doc.get("kind") == "CronJob":
        return doc.get("spec", {}).get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec")
    return doc.get("spec", {}).get("template", {}).get("spec")


def workload_references(doc: dict[str, Any]) -> tuple[list[Reference], set[tuple[str, str]]]:
    """Return (explicit valueFrom refs, envFrom bulk-loaded object sources).

    Rejects ambiguous/malformed identity (missing name or key, a valueFrom that
    carries both sources) loudly — partial or malformed bindings are exactly the
    drift this guard exists to catch. Scans initContainers too.
    """
    name = doc.get("metadata", {}).get("name", "<unnamed>")
    pod_spec = _pod_spec(doc)
    refs: list[Reference] = []
    envfrom_sources: set[tuple[str, str]] = set()
    if not isinstance(pod_spec, dict):
        return refs, envfrom_sources
    for list_key in _CONTAINER_LIST_KEYS:
        for container in pod_spec.get(list_key, []) or []:
            if not isinstance(container, dict):
                continue
            container_name = container.get("name", "?")
            # envFrom: whole-object bulk loads. No per-key binding, so we track
            # the consumed object and detect key *removal* from it in validate().
            for entry in container.get("envFrom", []) or []:
                if not isinstance(entry, dict):
                    continue
                for field, kind in _ENVFROM_KIND_BY_FIELD.items():
                    ref = entry.get(field)
                    if ref is None:
                        continue
                    if not isinstance(ref, dict) or not isinstance(ref.get("name"), str) or not ref["name"]:
                        raise MigrationGuardError(
                            f"{name}/{container_name}: envFrom {field} must declare a non-empty name"
                        )
                    envfrom_sources.add((kind, ref["name"]))
            for entry in container.get("env", []) or []:
                if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                    continue
                env_name = entry["name"]
                value_from = entry.get("valueFrom")
                if not isinstance(value_from, dict):
                    continue
                found: list[Reference] = []
                for field, kind in _VALUEFROM_KIND_BY_FIELD.items():
                    ref = value_from.get(field)
                    if ref is None:
                        continue  # an explicit ``null`` clears a historical source — not a binding.
                    if not isinstance(ref, dict):
                        raise MigrationGuardError(f"{name}/{env_name}: {field} is not a mapping")
                    obj_name, key = ref.get("name"), ref.get("key")
                    if not isinstance(obj_name, str) or not isinstance(key, str) or not obj_name or not key:
                        raise MigrationGuardError(
                            f"{name}/{container_name}/{env_name}: {field} must declare a non-empty name and key"
                        )
                    found.append((env_name, kind, obj_name, key))
                if len(found) > 1:
                    raise MigrationGuardError(f"{name}/{env_name}: declares multiple binding sources")
                refs.extend(found)
    return refs, envfrom_sources


def all_references(rendered_paths: list[str]) -> tuple[list[Reference], set[tuple[str, str]]]:
    refs: list[Reference] = []
    envfrom: set[tuple[str, str]] = set()
    for path in rendered_paths:
        for doc in _documents(path):
            if doc.get("kind") in POD_TEMPLATE_KINDS:
                doc_refs, doc_envfrom = workload_references(doc)
                refs.extend(doc_refs)
                envfrom.update(doc_envfrom)
    return refs, envfrom


def _load_inventory(path: str) -> dict[tuple[str, str], set[str]]:
    """Load {kind: {object_name: [key, ...]}} → {(kind, object_name): {keys}}.

    Key names only. Validates shape and rejects empty/malformed entries so a
    broken inventory can never masquerade as an empty-but-valid one.
    """
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise MigrationGuardError(f"could not read inventory {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise MigrationGuardError(f"inventory {path} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise MigrationGuardError(f"inventory {path} must be a mapping of configmaps/secrets")
    available: dict[tuple[str, str], set[str]] = {}
    for kind in ("configmaps", "secrets"):
        section = raw.get(kind)
        if section is None:
            continue
        if not isinstance(section, dict):
            raise MigrationGuardError(f"inventory {path}: '{kind}' must be a mapping of object → keys")
        short = kind[: -len("s")]  # configmaps -> configmap, secrets -> secret
        for obj_name, keys in section.items():
            if not isinstance(obj_name, str) or not obj_name:
                raise MigrationGuardError(f"inventory {path}: {kind} has an empty object name")
            if not isinstance(keys, list):
                raise MigrationGuardError(f"inventory {path}: {kind}/{obj_name} keys must be a list")
            key_set = set()
            for key in keys:
                if not isinstance(key, str) or not key:
                    raise MigrationGuardError(f"inventory {path}: {kind}/{obj_name} has an empty key name")
                key_set.add(key)
            available[(short, obj_name)] = key_set
    if not available:
        raise MigrationGuardError(f"inventory {path} declares no configmaps or secrets")
    return available


def _moved_keys(
    previous: dict[tuple[str, str], set[str]], proposed: dict[tuple[str, str], set[str]]
) -> dict[str, tuple[tuple[str, str], tuple[str, str]]]:
    """Keys that relocate between objects: {key: (old_source, new_source)}."""
    moved: dict[str, tuple[tuple[str, str], tuple[str, str]]] = {}
    old_by_key: dict[str, tuple[str, str]] = {}
    for source, keys in previous.items():
        for key in keys:
            old_by_key.setdefault(key, source)
    new_by_key: dict[str, tuple[str, str]] = {}
    for source, keys in proposed.items():
        for key in keys:
            new_by_key.setdefault(key, source)
    for key, old_source in old_by_key.items():
        new_source = new_by_key.get(key)
        if new_source is not None and new_source != old_source:
            moved[key] = (old_source, new_source)
    return moved


def validate(
    refs: list[Reference],
    envfrom_sources: set[tuple[str, str]],
    proposed: dict[tuple[str, str], set[str]],
    previous: dict[tuple[str, str], set[str]] | None,
) -> list[str]:
    """Return failure lines. Empty list ⇒ every reference resolves safely."""
    failures: list[str] = []
    moved = _moved_keys(previous, proposed) if previous else {}

    # Explicit per-key refs: each must resolve to a present key.
    for env_name, kind, obj_name, key in sorted(refs):
        source = (kind, obj_name)
        keys = proposed.get(source)
        if keys is None:
            failures.append(
                f"{env_name} references {kind}/{obj_name} which is absent from the proposed source inventory"
            )
            continue
        if key not in keys:
            # The incident root cause: a serving workload references a key the
            # proposed state removed or reclassified. Never pass this.
            note = ""
            if key in moved and moved[key][0] == source:
                new_kind, new_name = moved[key][1]
                note = f" (key moved to {new_kind}/{new_name}; update the consumer before removing the old source)"
            failures.append(
                f"{env_name} references {kind}/{obj_name}#{key} which is not present in the proposed source inventory{note}"
            )

    # envFrom bulk loads: the consumed object must still exist, and — when a
    # previous inventory models the transition — no key may have been removed
    # from it. Removing a key from a bulk-loaded ConfigMap is the exact shape of
    # the 2026-07-22 outage (an env var the pod depends on silently disappears).
    for kind, obj_name in sorted(envfrom_sources):
        source = (kind, obj_name)
        keys = proposed.get(source)
        if keys is None:
            failures.append(f"envFrom bulk-loads {kind}/{obj_name} which is absent from the proposed source inventory")
            continue
        if previous is not None:
            removed = sorted((previous.get(source) or set()) - keys)
            if removed:
                failures.append(
                    f"envFrom bulk-loads {kind}/{obj_name} but key(s) {removed} were removed from it; "
                    "a pod env var the workload depends on may disappear — the 2026-07-22 outage class"
                )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--rendered",
        action="append",
        required=True,
        metavar="PATH",
        help="Helm template output to scan (repeatable); every pod-template workload is checked",
    )
    parser.add_argument(
        "--source-inventory",
        required=True,
        metavar="PATH",
        help="proposed ConfigMap/Secret KEY NAMES (no values) after the change",
    )
    parser.add_argument(
        "--previous-inventory",
        metavar="PATH",
        help="current live source key names; required to detect a key removed from a bulk-loaded (envFrom) object",
    )
    args = parser.parse_args(argv)

    try:
        refs, envfrom_sources = all_references(args.rendered)
        proposed = _load_inventory(args.source_inventory)
        previous = _load_inventory(args.previous_inventory) if args.previous_inventory else None
    except MigrationGuardError as exc:
        print(f"FAIL: {exc}")
        return 1
    failures = validate(refs, envfrom_sources, proposed, previous)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        f"shared-config migration guard passed: {len(refs)} per-key reference(s) and "
        f"{len(envfrom_sources)} envFrom source(s) resolve to the proposed source key inventory "
        "(ConfigMap/Secret values were never read)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
