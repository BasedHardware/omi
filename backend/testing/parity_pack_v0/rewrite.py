"""Descriptor-only slot for an optional external cassette rewrite binary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RewriteLaunchDescriptor:
    command: tuple[str, ...]
    input_manifest: Path
    output_manifest: Path
    available: bool


def rewrite_launch_descriptor(
    input_manifest: Path, output_manifest: Path, binary: str = "omi-replay-rewrite"
) -> RewriteLaunchDescriptor:
    """Describe, but never silently invoke, the optional rewrite integration."""
    return RewriteLaunchDescriptor(
        command=(binary, "--manifest", str(input_manifest), "--output", str(output_manifest)),
        input_manifest=input_manifest,
        output_manifest=output_manifest,
        available=False,
    )
