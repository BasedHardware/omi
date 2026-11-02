#!/usr/bin/env python3
"""Hermetic fixtures for check_docs_volatile_facts.py — each pattern class must
fire on a violating page, allowlisted pages must be exempt, and api-reference
(generated) pages must be exempt."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

SCRIPT = pathlib.Path(__file__).resolve().parent / "check_docs_volatile_facts.py"


def run(docs_root: pathlib.Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--docs", str(docs_root)],
        capture_output=True, text=True,
    )
    return result.returncode, result.stdout + result.stderr


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)

        violations = {
            "price.mdx": "Costs $5 per month.\n",
            "sla.mdx": "Apps are reviewed within 24 hours.\n",
            "count.mdx": "Omi ships 22+ integrations.\n",
            "retired.mdx": "See https://omi.me/bounties and ping @josancamon19.\n",
            "vendor.mdx": "Audio goes to Deepgram Nova-3.\n",
            "model.mdx": "Powered by gpt-4o and claude-sonnet.\n",
            "pin.mdx": "Requires Python 3.11 and macOS 14.4.\n",
            "search.mdx": "Vectors live in Pinecone.\n",
            "sunset.mdx": "Keys are retired (2026-08-27).\n",
            "emoji.mdx": "## \U0001F680 Quick Start\n",
            # Emoji inside code fences and the bounty label name are allowed.
            "emoji_ok.mdx": '```json\n{"emoji": "\U0001F4BC"}\n```\nIssues labeled "Paid Bounty \U0001F4B0".\n',
        }
        for rel, body in violations.items():
            path = root / rel
            path.write_text(body)
        # Allowlisted page and generated api-reference page must not fire.
        (root / "api-reference").mkdir()
        (root / "api-reference" / "endpoint.mdx").write_text("Uses $5 and Deepgram.\n")

        code, out = run(root)
        assert code == 1, f"violations should fail:\n{out}"
        for name, label in [
            ("price.mdx", "price"),
            ("sla.mdx", "review-turnaround promise"),
            ("count.mdx", "rotting count"),
            ("retired.mdx", "retired bounty flow"),
            ("vendor.mdx", "stt vendor"),
            ("model.mdx", "llm model name"),
            ("pin.mdx", "tool version pin"),
            ("search.mdx", "stt/search vendor"),
            ("sunset.mdx", "dated retirement note"),
            ("emoji.mdx", "emoji"),
        ]:
            if not any(name in line and label in line for line in out.splitlines()):
                raise SystemExit(f"expected {name} flagged as {label}:\n{out}")
            print(f"  ok: {name} -> {label}")
        if "emoji_ok.mdx" in out:
            raise SystemExit(f"fenced payload emoji and bounty label must pass:\n{out}")
        print("  ok: fenced/label emoji exempt")
        if "api-reference" in out:
            raise SystemExit(f"api-reference must be exempt:\n{out}")
        print("  ok: api-reference exempt")

        # Allowlist path: build the same violation under an allowlisted rel path.
        allowed = root / "doc" / "get_started"
        allowed.mkdir(parents=True)
        (allowed / "byok_and_custom_transcription.mdx").write_text("Deepgram $5 reviewed within 24 hours.\n")
        root2 = tempfile.TemporaryDirectory()
        try:
            clean = pathlib.Path(root2.name)
            page = clean / "doc" / "get_started" / "byok_and_custom_transcription.mdx"
            page.parent.mkdir(parents=True)
            page.write_text("Deepgram $5 reviewed within 24 hours.\n")
            code, out = run(clean)
            assert code == 0, f"allowlisted page must pass:\n{out}"
            print("  ok: allowlisted page exempt")
        finally:
            root2.cleanup()

    print("test_check_docs_volatile_facts: all fixtures passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
