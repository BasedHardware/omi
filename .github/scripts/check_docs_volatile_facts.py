#!/usr/bin/env python3
"""Deterministic volatile-facts lint for hand-written docs pages.

docs.omi.me should stay timeless: no prices, no review-turnaround promises, no
counts that rot, no STT/LLM vendor or model names, no personal social handles,
no tool version pins. Pages whose topic legitimately requires such facts
(provider/transcription guides, SDK pages, setup guides that mirror repo pins,
generated reference pages, legacy hardware pages) are allowlisted below — the
allowlist is the escape hatch, keep it honest.

Stdlib only, no network. Exit 1 with one line per violation.
"""

from __future__ import annotations

import pathlib
import re
import sys

DOCS = pathlib.Path(__file__).resolve().parents[2] / "docs"

# Pages exempt from the lint. Generated reference output, provider-topic and
# setup guides whose pins mirror the repo, and legacy/community hardware pages.
ALLOWLIST = {
    # generated / reference
    "doc/reference/changelog",          # historical entries name versions by design
    "doc/developer/cli/commands",       # generated sections + flag/env reference
    "doc/developer/mcp/tools",          # generated from the tool registry
    # provider-topic pages (vendors and pins are the content)
    "doc/get_started/byok_and_custom_transcription",
    "doc/developer/sdk/sdk",
    "doc/developer/sdk/python",
    "doc/developer/sdk/swift",
    "doc/developer/sdk/ReactNative",
    "doc/developer/mcp/setup",
    "doc/developer/mcp/examples",
    "doc/developer/mcp/troubleshooting",
    # setup guides mirroring pins owned by the repo (.python-version, CMakePresets, setup.sh)
    "doc/developer/AppSetup",
    "doc/developer/backend/Backend_Setup",
    "doc/developer/cli/install",
    "doc/developer/firmware/Compile_firmware",
    "doc/contribute/desktop-setup",
    "onboarding/omi-macos",
    "doc/hardware/omiGlass",            # build recipe pins the model it pulls
    # legacy / community hardware pages
    "doc/hardware/DevKit1",
    "doc/hardware/DevKit2",
    "doc/hardware/SpeakerMod",
    "doc/hardware/PaintingOMI",
    "doc/hardware/omiglass/flash-firmware",
    "doc/hardware/omiglass/monitoring",
    "doc/assembly/introduction",
    "doc/assembly/Buying_Guide",
    "doc/assembly/Build_the_device",
}

PATTERNS: list[tuple[str, str]] = [
    ("price", re.compile(r"\$\d")),
    ("review-turnaround promise", re.compile(r"reviewed within", re.IGNORECASE)),
    ("rotting count", re.compile(r"\b\d+\+\s+(integrations|apps|tools|devices|users)\b", re.IGNORECASE)),
    ("retired bounty flow", re.compile(r"omi\.me/bounties|amzn\.to|josancamon19|kodjima33")),
    ("stt vendor", re.compile(r"\bDeepgram\b|\bNova-3\b")),
    ("llm model name", re.compile(r"\bgpt-\d|\bclaude-[a-z0-9]|\bgemini-\d")),
    ("stt/search vendor", re.compile(r"\b(Pinecone|Soniox|Modulate|Parakeet)\b|text-embedding-")),
    ("dated retirement note", re.compile(r"retired[^.\n]{0,20}\d{4}-\d{2}-\d{2}", re.IGNORECASE)),
    ("tool version pin", re.compile(r"\b(Python|macOS|iOS|Android|Xcode|Flutter|NCS|nRF Connect SDK)\s\d+\.\d+")),
]


# Emoji are checked in prose only: code blocks carry real payloads (conversation
# emoji fields) and the bounty label's name contains one.
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")
EMOJI_EXEMPT = ("Paid Bounty",)


def main() -> int:
    problems: list[str] = []
    docs_root = DOCS
    if len(sys.argv) > 2 and sys.argv[1] == "--docs":
        docs_root = pathlib.Path(sys.argv[2]).resolve()
    for path in sorted(docs_root.rglob("*.mdx")):
        rel = path.relative_to(docs_root).with_suffix("").as_posix()
        if rel in ALLOWLIST or rel.startswith("api-reference/"):
            continue
        in_fence = False
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
            elif not in_fence and EMOJI.search(line) and not any(x in line for x in EMOJI_EXEMPT):
                problems.append(f"{rel}.mdx:{lineno}: emoji: {line.strip()[:100]}")
            for label, pattern in PATTERNS:
                if pattern.search(line):
                    problems.append(f"{rel}.mdx:{lineno}: {label}: {line.strip()[:100]}")
    if problems:
        print(f"docs volatile-facts lint: {len(problems)} violation(s)")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("docs volatile-facts lint: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
