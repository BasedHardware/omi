#!/usr/bin/env python3
"""Return the LLM gateway image field to Helm when an out-of-band patch owns it.

An image-only ``kubectl patch`` leaves a ``kubectl-patch`` managed-fields entry that
owns ``.spec.template.spec.containers[name=<container>].image``. Helm applies with
server-side apply and refuses to change a field another manager owns, so every
ordinary rollout that changes the image fails until that ownership is gone.

This removes that one managed-fields entry, and only when it owns nothing but the
gateway image. It never forces a conflict, never clears the other entries and never
changes the Deployment spec: serving image, pod template and generation stay as they
are. Without ``--apply`` it only plans.

Exit codes: 0 done or nothing to hand off, 2 usage, 3 refused, 4 the cluster did not
match the plan.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

HELM_MANAGER = "helm"
PATCH_MANAGER = "kubectl-patch"
HANDOFF_MANAGER = "llm-gateway-image-ownership-handoff"
API_VERSION = "apps/v1"
IMAGE_LEAF = "f:image"

Kubectl = Callable[[list[str]], subprocess.CompletedProcess]


class Refused(Exception):
    """The live Deployment is not in the state this handoff is bounded to."""


class VerificationFailed(Exception):
    """The handoff ran but the cluster does not match the plan."""


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _at(value: Any, *keys: str) -> dict[str, Any]:
    for key in keys:
        value = _mapping(value).get(key)
    return _mapping(value)


def _leaves(tree: Any, prefix: str = "") -> set[str]:
    if not isinstance(tree, dict):
        return set()
    if not tree:
        return {prefix}
    return {leaf for key, branch in tree.items() for leaf in _leaves(branch, f"{prefix}.{key}" if prefix else key)}


def list_key(name: str) -> str:
    return "k:" + json.dumps({"name": name}, separators=(",", ":"))


def image_path(container: str) -> str:
    return f'.spec.template.spec.containers[name="{container}"].image'


def image_only_fields(container: str) -> dict[str, Any]:
    """The managed-fields tree of an entry that owns the container image and nothing else."""
    return {"f:spec": {"f:template": {"f:spec": {"f:containers": {list_key(container): {IMAGE_LEAF: {}}}}}}}


def managed_fields(deployment: dict[str, Any]) -> list[dict[str, Any]]:
    entries = _mapping(deployment.get("metadata")).get("managedFields")
    return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []


def describe(entry: dict[str, Any]) -> str:
    subresource = entry.get("subresource")
    return f"{entry.get('manager')}/{entry.get('operation')}" + (f" ({subresource})" if subresource else "")


def image_owner_indexes(deployment: dict[str, Any], container: str) -> list[int]:
    key = list_key(container)
    return [
        index
        for index, entry in enumerate(managed_fields(deployment))
        if IMAGE_LEAF in _at(entry, "fieldsV1", "f:spec", "f:template", "f:spec", "f:containers", key)
    ]


def container_image(deployment: dict[str, Any], container: str) -> str | None:
    containers = _at(deployment, "spec", "template", "spec").get("containers")
    for candidate in containers if isinstance(containers, list) else []:
        if isinstance(candidate, dict) and candidate.get("name") == container:
            return candidate.get("image")
    return None


def plan_handoff(deployment: dict[str, Any], container: str, manager: str) -> dict[str, Any] | None:
    """Return the removal plan for ``manager``'s image-only entry, or None when it owns no image."""
    entries = managed_fields(deployment)
    metadata = _mapping(deployment.get("metadata"))
    name = metadata.get("name")
    labels = _mapping(metadata.get("labels"))
    annotations = _mapping(metadata.get("annotations"))
    if "meta.helm.sh/release-name" not in annotations or labels.get("app.kubernetes.io/managed-by") != "Helm":
        raise Refused(f"{name} is not a Helm-managed object")
    if not any(entry.get("manager") == HELM_MANAGER and entry.get("operation") == "Apply" for entry in entries):
        raise Refused(
            f"Helm has no server-side apply entry on {name}; its ordinary rollout is not field manager 'helm'"
        )

    candidates = [
        index for index in image_owner_indexes(deployment, container) if entries[index].get("manager") == manager
    ]
    if not candidates:
        return None
    if len(candidates) > 1:
        raise Refused(f"{manager} owns the {container} image through {len(candidates)} managed-fields entries")
    index = candidates[0]
    entry = entries[index]
    expected = image_only_fields(container)
    problems = []
    if entry.get("operation") != "Update":
        problems.append(f"its operation is {entry.get('operation')!r}, not 'Update'")
    if entry.get("apiVersion") != API_VERSION:
        problems.append(f"its apiVersion is {entry.get('apiVersion')!r}, not {API_VERSION!r}")
    if entry.get("subresource"):
        problems.append(f"it targets the {entry.get('subresource')!r} subresource")
    if entry.get("fieldsV1") != expected:
        problems.append("it also owns " + ", ".join(sorted(_leaves(entry.get("fieldsV1")) - _leaves(expected))))
    if problems:
        raise Refused(f"{describe(entry)} owns more than the {container} image: " + "; ".join(problems))

    prefix = f"/metadata/managedFields/{index}"
    resource_version = metadata.get("resourceVersion")
    return {
        "index": index,
        "entry": entry,
        "resource_version": resource_version,
        "patch": [
            {"op": "test", "path": "/metadata/resourceVersion", "value": resource_version},
            {"op": "test", "path": f"{prefix}/manager", "value": manager},
            {"op": "test", "path": f"{prefix}/operation", "value": "Update"},
            {"op": "test", "path": f"{prefix}/apiVersion", "value": API_VERSION},
            {"op": "test", "path": f"{prefix}/fieldsV1", "value": expected},
            {"op": "remove", "path": prefix},
        ],
    }


def fingerprint(deployment: dict[str, Any]) -> dict[str, Any]:
    """Everything the handoff must leave exactly as it is."""
    metadata = _mapping(deployment.get("metadata"))
    return {
        "generation": metadata.get("generation"),
        "labels": metadata.get("labels"),
        "annotations": metadata.get("annotations"),
        "spec": deployment.get("spec"),
        "managedFields": metadata.get("managedFields"),
    }


def expected_after(deployment: dict[str, Any], index: int) -> dict[str, Any]:
    after = copy.deepcopy(deployment)
    del after["metadata"]["managedFields"][index]
    return after


def read_deployment(kubectl: Kubectl, namespace: str, name: str) -> dict[str, Any]:
    result = kubectl(["-n", namespace, "get", "deployment", name, "--show-managed-fields", "-o", "json"])
    if result.returncode:
        raise Refused(f"could not read deployment {namespace}/{name}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def ordinary_apply_dry_run(kubectl: Kubectl, namespace: str, manifest: Path) -> subprocess.CompletedProcess:
    return kubectl(
        [
            "-n",
            namespace,
            "apply",
            "--server-side",
            "--dry-run=server",
            f"--field-manager={HELM_MANAGER}",
            "-f",
            str(manifest),
        ]
    )


def _changed_sections(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    return [section for section in expected if actual.get(section) != expected[section]]


def _print_owners(deployment: dict[str, Any], container: str) -> None:
    entries = managed_fields(deployment)
    owners = [describe(entries[index]) for index in image_owner_indexes(deployment, container)]
    print(f"{container} image owners: {', '.join(owners) if owners else 'none'}")


def run_handoff(
    kubectl: Kubectl,
    namespace: str,
    name: str,
    container: str,
    manager: str,
    next_deployment: Path | None,
    apply: bool,
) -> int:
    live = read_deployment(kubectl, namespace, name)
    generation = _mapping(live.get("metadata")).get("generation")
    print(f"{namespace}/{name}: serving image {container_image(live, container)}, generation {generation}")
    _print_owners(live, container)

    if next_deployment is not None:
        preview = ordinary_apply_dry_run(kubectl, namespace, next_deployment)
        if preview.returncode:
            conflict = (
                f'Apply failed with 1 conflict: conflict with "{manager}" using {API_VERSION}: {image_path(container)}'
            )
            if conflict not in preview.stderr:
                raise Refused(f"the ordinary Helm apply fails for another reason:\n{preview.stderr.strip()}")
            print(f"ordinary Helm apply before handoff: conflicts with {manager} on {image_path(container)}")
        else:
            print("ordinary Helm apply before handoff: passes with this manifest (no conflict)")

    planned = plan_handoff(live, container, manager)
    if planned is None:
        print(f"nothing to hand off: {manager} does not own the {container} image")
        return 0

    index = planned["index"]
    expected = expected_after(live, index)
    print(
        f"plan: remove managed-fields entry {index} {describe(planned['entry'])}, "
        f"which owns only {image_path(container)}; image, spec, generation and every other entry stay unchanged"
    )
    for operation in planned["patch"]:
        print(f"  {operation['op']} {operation['path']}")

    patch = [
        "patch",
        "deployment",
        name,
        "--type=json",
        f"--field-manager={HANDOFF_MANAGER}",
    ]
    with tempfile.TemporaryDirectory() as directory:
        patch_file = Path(directory) / "handoff.json"
        patch_file.write_text(json.dumps(planned["patch"]), encoding="utf-8")
        patch.append(f"--patch-file={patch_file}")

        preview = kubectl(["-n", namespace, *patch, "--dry-run=server", "--show-managed-fields", "-o", "json"])
        if preview.returncode:
            raise Refused(f"the server rejected the planned patch; nothing was changed:\n{preview.stderr.strip()}")
        changed = _changed_sections(fingerprint(json.loads(preview.stdout)), fingerprint(expected))
        if changed:
            raise Refused(f"server dry-run of the patch would change {', '.join(changed)}; nothing was changed")

        print("server dry-run of the patch: image, spec, generation and all other entries match the plan")
        if not apply:
            print("plan only; rerun with --apply to execute")
            return 0

        applied = kubectl(["-n", namespace, *patch])
        if applied.returncode:
            raise Refused(f"the patch was not applied:\n{applied.stderr.strip()}")

    after = read_deployment(kubectl, namespace, name)
    changed = _changed_sections(fingerprint(after), fingerprint(expected))
    if changed:
        raise VerificationFailed(f"the Deployment changed outside the plan after the patch: {', '.join(changed)}")
    print(
        f"handoff done: serving image {container_image(after, container)}, generation "
        f"{_mapping(after.get('metadata')).get('generation')}; image, spec and all other entries are unchanged"
    )
    _print_owners(after, container)

    if next_deployment is not None:
        preview = ordinary_apply_dry_run(kubectl, namespace, next_deployment)
        if preview.returncode:
            raise VerificationFailed(f"the ordinary Helm apply still fails:\n{preview.stderr.strip()}")
        print("ordinary Helm apply after handoff: passes")
    return 0


def kubectl_command(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["kubectl", *command], capture_output=True, text=True, check=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--namespace", default="prod-omi-backend")
    parser.add_argument("--deployment", default="prod-omi-llm-gateway")
    parser.add_argument("--container", default="llm-gateway")
    parser.add_argument("--manager", default=PATCH_MANAGER, help="manager whose image-only entry is removed")
    parser.add_argument(
        "--next-deployment",
        type=Path,
        help="Helm-rendered Deployment the next ordinary rollout applies; proves the conflict before and its absence after",
    )
    parser.add_argument("--apply", action="store_true", help="execute the plan; the default only plans")
    args = parser.parse_args(argv)

    try:
        return run_handoff(
            kubectl_command,
            args.namespace,
            args.deployment,
            args.container,
            args.manager,
            args.next_deployment,
            args.apply,
        )
    except Refused as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 3
    except VerificationFailed as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
