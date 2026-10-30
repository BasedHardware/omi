"""Build, probe, measure and publish the plan B role images from one SHA (B2).

The role images are every ``runtime_images.json`` image built from
``backend/Dockerfile.roles`` plus the ``native_images`` (the Rust listen-edge).
Steps share one JSON manifest so a workflow can run them as separate steps:

  role_images.py build   --sha SHA --manifest M [--registry gcr.io/P] [--base IMAGE] [--baseline]
  role_images.py verify  --manifest M   # dependency probe (Python) or HTTP probe (native)
  role_images.py measure --manifest M   # image size and cold-start import per image
  role_images.py publish --manifest M   # train only: push, refuse a tag of another SHA, record digests
  role_images.py summary --manifest M   # markdown table and the service_images opt-in line

``verify`` runs ``runtime_image_contracts.py smoke --dockerfile backend/Dockerfile.roles
--target <target>`` for each Python role image; that probe is the gate before publish.
``--baseline`` also builds today's fat ``backend/Dockerfile`` image, measured only,
so the report compares each role against the image it replaces. Nothing here
deploys: ``service_images`` is consumed by deploy-backend-stack only when a deploy
passes it.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

SCRIPTS_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPTS_DIR.parents[1]
REGISTRY_PATH = REPOSITORY_ROOT / "backend" / "runtime_images.json"
ROLE_DOCKERFILE = "backend/Dockerfile.roles"
BASELINE = {"name": "backend", "dockerfile": "backend/Dockerfile", "entrypoints": ["main"]}
# Import-time guards in first-party modules (runtime_image_contracts.IMPORT_TIME_REQUIRED_ENVIRONMENT)
# need a non-production placeholder; the cold-start import runs with no network.
COLD_START_ENVIRONMENT = {
    "ENCRYPTION_SECRET": "0123456789abcdef0123456789abcdef",
    "OPENAI_API_KEY": "sk-runtime-image-contract-test",
}
COLD_START_TIMEOUT_SECONDS = 300
NATIVE_READY_TIMEOUT_SECONDS = 60
# Services deploy-backend-stack can move onto a role image by digest (service_images).
STACK_SERVICES = (
    "backend",
    "backend-sync",
    "backend-sync-backfill",
    "backend-integration",
    "backend-listen",
    "llm-gateway",
)

Runner = Callable[..., subprocess.CompletedProcess]


class RoleImageError(RuntimeError):
    pass


def _run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    print("+ " + " ".join(command), flush=True)
    return subprocess.run(command, check=False, **kwargs)


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def role_image_entries(registry: dict[str, Any]) -> list[dict[str, Any]]:
    """Every role image one train builds, in build order (shared layers first)."""
    roles = {image: role for role, spec in registry["roles"].items() for image in spec["images"]}
    entries: list[dict[str, Any]] = []
    for image in registry["images"]:
        if image["dockerfile"] != ROLE_DOCKERFILE:
            continue
        if image["name"] not in roles:
            raise RoleImageError(f"{image['name']} is built from {ROLE_DOCKERFILE} but belongs to no role")
        entries.append(
            {
                "name": image["name"],
                "kind": "python",
                "role": roles[image["name"]],
                "dockerfile": ROLE_DOCKERFILE,
                "target": image["target"],
                "context": image["build_context"],
                "entrypoints": image["entrypoints"],
                "smoke_environment": image.get("smoke_environment", {}),
            }
        )
    for name, spec in registry.get("native_images", {}).items():
        entries.append(
            {
                "name": name,
                "kind": "native",
                "role": spec["role"],
                "dockerfile": spec["dockerfile"],
                "target": None,
                "context": spec["build_context"],
                "probe": spec["probe"],
            }
        )
    return entries


def image_tag(name: str, sha: str, registry: str | None) -> str:
    # 12 hex chars: a fixed 7-char slice can collide, which publish would refuse.
    # Deploys consume digests, so the tag is only a human-readable handle.
    if registry:
        return f"{registry.rstrip('/')}/{name}:{sha[:12]}"
    return f"omi-role-{name}:{sha[:12]}"


def build_command(entry: dict[str, Any], tag: str, sha: str, base: str | None) -> list[str]:
    command = ["docker", "build", "--file", entry["dockerfile"]]
    if entry.get("target"):
        command += ["--target", entry["target"]]
    command += ["--build-arg", f"OMI_RELEASE_SHA={sha}"]
    if base and entry["kind"] != "native":
        command += ["--build-arg", f"PYTHON_BASE_IMAGE={base}"]
    return command + ["--tag", tag, entry["context"]]


def build(args: argparse.Namespace, run: Runner = _run) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", args.sha):
        raise RoleImageError("--sha must be a full 40-character commit SHA")
    entries = role_image_entries(load_registry())
    if args.images:
        wanted = set(args.images.split(","))
        unknown = wanted - {entry["name"] for entry in entries} - {BASELINE["name"]}
        if unknown:
            raise RoleImageError(f"unknown role images: {sorted(unknown)}")
        entries = [entry for entry in entries if entry["name"] in wanted]
    if args.baseline:
        entries.append({**BASELINE, "kind": "baseline", "role": "-", "target": None, "context": "."})
    manifest = {"sha": args.sha, "registry": args.registry, "base": args.base, "images": []}
    for entry in entries:
        tag = image_tag(entry["name"], args.sha, args.registry if entry["kind"] != "baseline" else None)
        started = time.monotonic()
        result = run(build_command(entry, tag, args.sha, args.base), cwd=args.context)
        if result.returncode:
            raise RoleImageError(f"docker build failed for {entry['name']} (exit {result.returncode})")
        manifest["images"].append({**entry, "tag": tag, "build_seconds": round(time.monotonic() - started, 1)})
    return manifest


def _smoke_command(entry: dict[str, Any]) -> list[str]:
    return [
        sys.executable,
        str(SCRIPTS_DIR / "runtime_image_contracts.py"),
        "smoke",
        "--dockerfile",
        entry["dockerfile"],
        "--target",
        entry["target"],
        "--image",
        entry["tag"],
    ]


def _http_get(url: str, timeout: float = 2.0) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - local probe URL
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, ""
    except (urllib.error.URLError, OSError):
        return 0, ""


def probe_native(
    entry: dict[str, Any],
    sha: str,
    run: Runner = _run,
    http_get: Callable[[str], tuple[int, str]] = _http_get,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Start the edge with an unreachable upstream: health, readiness, build identity, clean drain."""
    started = run(
        [
            "docker",
            "run",
            "--detach",
            "--publish",
            "127.0.0.1::8080",
            "--env",
            "EDGE_UPSTREAM_URL=ws://127.0.0.1:9",
            "--env",
            "EDGE_DRAIN_READY_DELAY_MS=0",
            "--env",
            "EDGE_DRAIN_SPREAD_MS=0",
            entry["tag"],
        ],
        capture_output=True,
        text=True,
    )
    if started.returncode:
        raise RoleImageError(f"{entry['name']}: container did not start: {started.stderr.strip()}")
    container = started.stdout.strip()
    try:
        port = run(["docker", "port", container, "8080/tcp"], capture_output=True, text=True).stdout.strip()
        base = "http://" + port.splitlines()[0] if port else ""
        launched = clock()
        ready_seconds = None
        while clock() - launched < NATIVE_READY_TIMEOUT_SECONDS:
            if base and http_get(base + "/healthz")[0] == 200 and http_get(base + "/readyz")[0] == 200:
                ready_seconds = round(clock() - launched, 2)
                break
            sleep(0.25)
        if ready_seconds is None:
            run(["docker", "logs", container])
            raise RoleImageError(
                f"{entry['name']}: /healthz and /readyz not 200 within {NATIVE_READY_TIMEOUT_SECONDS}s"
            )
        status, metrics = http_get(base + "/metrics")
        # The edge bounds the label to 12 hex chars (sanitize_release_sha in backend/edge/src/metrics.rs).
        identity = f'omi_edge_build_info{{release_sha="{sha[:12].lower()}"}} 1'
        if status != 200 or identity not in metrics:
            raise RoleImageError(f"{entry['name']}: /metrics does not export {identity}")
        stopped = run(["docker", "stop", "--time", "30", container], capture_output=True, text=True)
        code = run(["docker", "wait", container], capture_output=True, text=True).stdout.strip()
        if stopped.returncode or code != "0":
            run(["docker", "logs", container])
            raise RoleImageError(f"{entry['name']}: SIGTERM drain exited {code or stopped.returncode}, expected 0")
        return {"ok": True, "ready_seconds": ready_seconds}
    finally:
        run(["docker", "rm", "--force", container], capture_output=True, text=True)


def verify(manifest: dict[str, Any], run: Runner = _run, **native_kwargs: Any) -> None:
    for entry in manifest["images"]:
        if entry["kind"] == "python":
            result = run(_smoke_command(entry))
            if result.returncode:
                raise RoleImageError(f"{entry['name']}: dependency probe failed (exit {result.returncode})")
            entry["probe"] = {"ok": True}
        elif entry["kind"] == "native":
            entry["probe"] = probe_native(entry, manifest["sha"], run=run, **native_kwargs)


def _cold_start_code(workdir: str, entrypoint: str) -> str:
    return (
        "import importlib, json, sys, time\n"
        f"sys.path.insert(0, {workdir!r})\n"
        "started = time.perf_counter()\n"
        "try:\n"
        f"    importlib.import_module({entrypoint!r})\n"
        "    error = None\n"
        "except BaseException as exc:\n"
        "    error = f'{type(exc).__name__}: {str(exc)[:200]}'\n"
        "print('OMI_COLD_START ' + json.dumps({'seconds': round(time.perf_counter() - started, 2), 'error': error}))\n"
    )


def cold_start(entry: dict[str, Any], run: Runner = _run, clock: Callable[[], float] = time.monotonic) -> dict:
    """Wall time of a fresh container importing the role's first entrypoint, offline.

    Report-only: an entrypoint that cannot import offline (it needs a credential or
    a network peer) records the error instead of failing the build; the dependency
    probe is the gate.
    """
    entrypoint = entry["entrypoints"][0]
    environment = {**COLD_START_ENVIRONMENT, **entry.get("smoke_environment", {})}
    command = ["docker", "run", "--rm", "--network=none", "--entrypoint", "python"]
    for key, value in sorted(environment.items()):
        command += ["--env", f"{key}={value}"]
    command += [entry["tag"], "-I", "-c", _cold_start_code("/app", entrypoint)]
    started = clock()
    try:
        result = run(command, capture_output=True, text=True, timeout=COLD_START_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return {"entrypoint": entrypoint, "error": f"timeout after {COLD_START_TIMEOUT_SECONDS}s"}
    wall = round(clock() - started, 2)
    marker = [line for line in (result.stdout or "").splitlines() if line.startswith("OMI_COLD_START ")]
    if not marker:
        tail = (result.stderr or "").strip().splitlines()[-1:] or [f"exit {result.returncode}"]
        return {"entrypoint": entrypoint, "container_seconds": wall, "error": tail[0][:200]}
    measured = json.loads(marker[-1][len("OMI_COLD_START ") :])
    return {
        "entrypoint": entrypoint,
        "container_seconds": wall,
        "import_seconds": measured["seconds"],
        "error": measured["error"],
    }


def measure(manifest: dict[str, Any], run: Runner = _run) -> None:
    for entry in manifest["images"]:
        size = run(
            ["docker", "image", "inspect", "--format", "{{.Size}}", entry["tag"]], capture_output=True, text=True
        )
        entry["size_bytes"] = int(size.stdout.strip()) if size.returncode == 0 and size.stdout.strip() else None
        if entry["kind"] in ("python", "baseline"):
            entry["cold_start"] = cold_start(entry, run=run)


def _remote_digest(ref: str, run: Runner) -> str | None:
    """Digest of an existing remote tag, None when absent; any other error fails closed."""
    result = run(
        ["gcloud", "container", "images", "describe", ref, "--format=value(image_summary.digest)"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    if f"[{ref}] is not found or is not a valid name" in (result.stderr or ""):
        return None
    raise RoleImageError(f"could not determine whether {ref} exists: {(result.stderr or '').strip()}")


def publish(manifest: dict[str, Any], run: Runner = _run) -> None:
    if not manifest.get("registry"):
        raise RoleImageError("publish needs a manifest built with --registry")
    for entry in manifest["images"]:
        if entry["kind"] == "baseline":
            continue
        if not (entry.get("probe") or {}).get("ok"):
            raise RoleImageError(f"{entry['name']}: refusing to publish an image that has not passed verify")
        ref = entry["tag"]
        existing = _remote_digest(ref, run)
        if existing:
            revision = run(
                [
                    "docker",
                    "buildx",
                    "imagetools",
                    "inspect",
                    ref,
                    "--format",
                    '{{ index .Image.Config.Labels "org.opencontainers.image.revision" }}',
                ],
                capture_output=True,
                text=True,
            ).stdout.strip()
            if revision != manifest["sha"]:
                raise RoleImageError(f"{ref} already exists labelled revision {revision!r}, not {manifest['sha']}")
            entry["pushed"] = False
        else:
            if run(["docker", "push", ref]).returncode:
                raise RoleImageError(f"docker push failed for {ref}")
            entry["pushed"] = True
        digest = _remote_digest(ref, run)
        if not digest or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise RoleImageError(f"registry returned no digest for {ref}")
        entry["digest"] = digest
        entry["ref"] = f"{ref.rsplit(':', 1)[0]}@{digest}"


def service_images_line(manifest: dict[str, Any], registry: dict[str, Any] | None = None) -> str:
    """The deploy-backend-stack ``service_images`` value that opts every stack service in."""
    registry = registry or load_registry()
    refs = {entry["name"]: entry.get("ref") for entry in manifest["images"]}
    pairs = []
    for service in STACK_SERVICES:
        ref = refs.get(registry["services"][service]["image"])
        if ref:
            pairs.append(f"{service}={ref}")
    return " ".join(pairs)


def _megabytes(size: int | None) -> str:
    return f"{size / 1_000_000:.0f}" if size else "?"


def summary(manifest: dict[str, Any]) -> str:
    lines = [
        f"### Role images at `{manifest['sha']}`",
        "",
        f"Base: `{manifest.get('base') or 'Dockerfile default (private forky base)'}`",
        "",
        "| Image | Role | Size (MB) | Cold start: container s / import s | Probe | Digest |",
        "|---|---|---|---|---|---|",
    ]
    for entry in manifest["images"]:
        cold = entry.get("cold_start") or {}
        if entry["kind"] == "native":
            ready = (entry.get("probe") or {}).get("ready_seconds")
            start = f"ready in {ready} s" if ready is not None else "?"
        elif cold.get("error"):
            start = f"{cold.get('container_seconds', '?')} / failed offline: {cold['error']}"
        else:
            start = (
                f"{cold.get('container_seconds', '?')} / {cold.get('import_seconds', '?')} (`{cold.get('entrypoint')}`)"
            )
        probe = (
            "baseline (not probed)"
            if entry["kind"] == "baseline"
            else ("ok" if (entry.get("probe") or {}).get("ok") else "-")
        )
        lines.append(
            f"| `{entry['name']}` | {entry['role']} | {_megabytes(entry.get('size_bytes'))} | {start} | {probe} | "
            f"{('`' + entry['digest'] + '`') if entry.get('digest') else '-'} |"
        )
    line = service_images_line(manifest)
    if line:
        lines += [
            "",
            "Nothing was deployed. To move stack services onto these images, dispatch `gcp_backend.yml` "
            "(mode=deploy, same release_sha) with `service_images` set to any subset of:",
            "",
            f"`{line}`",
        ]
    return "\n".join(lines) + "\n"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--sha", required=True)
    build_parser.add_argument("--registry", help="gcr.io/<project>: tag <registry>/<image>:<short sha> for publish")
    build_parser.add_argument("--base", help="PYTHON_BASE_IMAGE override (PRs: public python:3.11-slim)")
    build_parser.add_argument("--images", help="comma-separated subset of role image names")
    build_parser.add_argument("--baseline", action="store_true", help="also build and measure backend/Dockerfile")
    build_parser.add_argument("--context", default=".", help="repository root of the source being built")
    for name in ("build", "verify", "measure", "publish", "summary"):
        command = build_parser if name == "build" else sub.add_parser(name)
        command.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "build":
            _write(args.manifest, build(args))
            return 0
        manifest = _read(args.manifest)
        if args.command == "summary":
            print(summary(manifest), end="")
            return 0
        {"verify": verify, "measure": measure, "publish": publish}[args.command](manifest)
        _write(args.manifest, manifest)
        return 0
    except RoleImageError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
