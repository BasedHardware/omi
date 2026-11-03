#!/usr/bin/env python3
"""Hermetic fixtures for check_docs_site.py — the docs gate must catch every
failure class it was written for (nav→file, orphans, broken links and images,
redirect shadowing and dead redirect targets)."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile

SCRIPT = pathlib.Path(__file__).resolve().parent / "check_docs_site.py"


def run(site_root: pathlib.Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--docs", str(site_root / "docs")],
        capture_output=True, text=True,
    )
    return result.returncode, result.stdout + result.stderr


def write_site(root: pathlib.Path, pages: dict[str, str], config: dict) -> None:
    (root / "docs").mkdir(parents=True, exist_ok=True)
    for rel, body in pages.items():
        target = root / "docs" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    (root / "docs" / "docs.json").write_text(json.dumps(config))
    (root / "docs" / "images").mkdir(exist_ok=True)
    (root / "docs" / "images" / "logo.png").write_bytes(b"png")


def base_config(pages: list[str], redirects: list[dict] | None = None) -> dict:
    return {
        "navigation": {"tabs": [{"tab": "Docs", "groups": [{"group": "G", "pages": pages}]}]},
        "redirects": redirects or [],
    }


def expect_failure(name: str, output: str, needle: str) -> None:
    if needle not in output:
        raise SystemExit(f"{name}: expected '{needle}' in output:\n{output}")
    print(f"  ok: {name}")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)

        # Clean site passes.
        site = root / "clean"
        write_site(site, {"index.mdx": "# hi\nSee [other](/other) and <img src=\"/images/logo.png\" />.\n", "other.mdx": "# other\n"},
                   base_config(["index", "other"]))
        code, out = run(site)
        assert code == 0, f"clean site should pass:\n{out}"
        print("  ok: clean site passes")

        # Nav entry points at a missing file.
        site = root / "missing"
        write_site(site, {"index.mdx": "# hi\n"}, base_config(["index", "ghost"]))
        code, out = run(site)
        assert code == 1
        expect_failure("missing nav file", out, "nav entry points to missing file: ghost")

        # Page not in nav (orphan).
        site = root / "orphan"
        write_site(site, {"index.mdx": "# hi\n", "island.mdx": "# island\n"}, base_config(["index"]))
        code, out = run(site)
        assert code == 1
        expect_failure("orphan page", out, "orphan): island")

        # Broken internal link, broken image, link to redirect source.
        site = root / "links"
        write_site(
            site,
            {"index.mdx": "[dead](/gone) ![](/images/missing.png) [old](/moved)\n"},
            base_config(["index"], [{"source": "/moved", "destination": "/index"}]),
        )
        code, out = run(site)
        assert code == 1
        expect_failure("broken link", out, "broken internal link /gone")
        expect_failure("broken image", out, "broken image reference /images/missing.png")
        expect_failure("link to redirect source", out, "links to a redirect source")

        # Redirect source that still exists as a file shadows the page.
        site = root / "shadow"
        write_site(site, {"index.mdx": "# hi\n", "moved.mdx": "# moved\n"},
                   base_config(["index", "moved"], [{"source": "/moved", "destination": "/index"}]))
        code, out = run(site)
        assert code == 1
        expect_failure("redirect shadow", out, "redirect source exists as a file")

        # Redirect to a dead internal target.
        site = root / "deadtarget"
        write_site(site, {"index.mdx": "# hi\n"},
                   base_config(["index"], [{"source": "/moved", "destination": "/nowhere"}]))
        code, out = run(site)
        assert code == 1
        expect_failure("dead redirect target", out, "redirect target does not resolve")

    print("test_check_docs_site: all fixtures passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
