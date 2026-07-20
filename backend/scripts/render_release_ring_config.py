#!/usr/bin/env python3
"""Render a ring-specific immutable values/config object from a checked-in base.

Beta intentionally reuses the production datastore and the existing GPU
endpoints in v1. Only the stateless release names, endpoints, and runtime stage
are rewritten here. GPU routing is deliberately not changed by this renderer;
see #10057 before treating the full transcription path as beta-safe.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

BETA_REPLACEMENTS = (
    ("prod-omi-backend", "beta-omi-backend"),
    ("prod-omi", "beta-omi"),
    ("pusher.omi.me", "pusher-beta.omi.me"),
    ("agent.omi.me", "agent-beta.omi.me"),
    ("api.omi.me", "api-beta.omi.me"),
    ("prod-pusher-ilb-ip-address", "beta-pusher-ilb-ip-address"),
    ("prod-agent-proxy-ip-address", "beta-agent-proxy-ip-address"),
    ("agent-proxy-cert", "beta-agent-proxy-cert"),
    ("prod-omi-self-hosted-llm-ip-address", "beta-omi-self-hosted-llm-ip-address"),
)


def render(value: Any, *, ring: str) -> Any:
    if ring == "prod":
        return value
    if isinstance(value, dict):
        return {key: render(item, ring=ring) for key, item in value.items()}
    if isinstance(value, list):
        return [render(item, ring=ring) for item in value]
    if not isinstance(value, str):
        return value
    if value == "prod":
        return "beta"
    rendered = value
    for old, new in BETA_REPLACEMENTS:
        rendered = rendered.replace(old, new)
    return rendered


def render_manifest(value: Any, *, ring: str) -> Any:
    """Render a source-controlled config and make beta a real env lane.

    The source manifest keeps dev/prod as its hand-maintained declarations.
    The release record stores the fully materialized beta declaration, so the
    beta lane is reviewable and rollbackable without maintaining a second
    mutable copy of thousands of runtime settings.
    """
    rendered = render(value, ring=ring)
    if ring == "beta" and isinstance(rendered, dict):
        environments = rendered.get("environments")
        if isinstance(environments, dict) and "prod" in environments:
            environments["beta"] = environments.pop("prod")
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ring", choices=("beta", "prod"), required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        source = yaml.safe_load(args.source.read_text(encoding="utf-8"))
        if source is None:
            raise ValueError("source config is empty")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            yaml.safe_dump(render_manifest(source, ring=args.ring), sort_keys=False), encoding="utf-8"
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
