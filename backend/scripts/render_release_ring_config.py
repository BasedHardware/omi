#!/usr/bin/env python3
"""Render the immutable production release configuration without substitution."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

PRODUCTION_RING = "prod"


def render(value: Any, *, ring: str) -> Any:
    """Return the production configuration and reject retired backend rings."""
    if ring != PRODUCTION_RING:
        raise ValueError(f"unsupported backend deploy target: {ring}")
    return value


def render_manifest(value: Any, *, ring: str) -> Any:
    return render(value, ring=ring)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ring", choices=(PRODUCTION_RING,), required=True)
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
