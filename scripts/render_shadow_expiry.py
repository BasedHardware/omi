#!/usr/bin/env python3
"""Write backend/config/shadow_expiry.py from the shadow blocks in config/feature-flags.yaml.

usage: python3 scripts/render_shadow_expiry.py [--root ROOT]
Deterministic; scripts/check_feature_flag_registry.py fails when the committed table drifts.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from feature_flag_registry import ROOT, SHADOW_EXPIRY_PATH, load_registry, render_shadow_expiry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    target = root / SHADOW_EXPIRY_PATH
    target.write_text(render_shadow_expiry(load_registry(root / "config/feature-flags.yaml")), encoding="utf-8")
    print(f"wrote {target.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
