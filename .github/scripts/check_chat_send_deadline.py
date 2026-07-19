#!/usr/bin/env python3
"""Direct provider sends in routes/chat/ must go through send_with_deadline.

Caught class (FC-per-hop-timeout): #8640, #8911, #9135, and #9644 each moved a
per-hop timeout because a raw send owned its own clock. The request budget seam
in `desktop/macos/Backend-Rust/src/request_deadline.rs` is the single owner of
outbound provider waits on the Anthropic chat path (#9835). Signatures alone do
not cover raw reqwest builders, so this STATIC TRIPWIRE rejects new direct
`.send()` calls in the chat module; behavioral coverage lives in the
`tokio::time::pause` deadline tests in `routes/chat/tests/all.rs`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHAT_DIR = ROOT / "desktop" / "macos" / "Backend-Rust" / "src" / "routes" / "chat"
DIRECT_SEND_RE = re.compile(r"\.send\(\)")


def find_direct_sends(chat_dir: Path) -> list[str]:
    violations: list[str] = []
    for path in sorted(chat_dir.rglob("*.rs")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if DIRECT_SEND_RE.search(line):
                try:
                    shown = path.relative_to(ROOT)
                except ValueError:
                    shown = path
                violations.append(f"{shown}:{lineno}: direct `.send()` bypasses send_with_deadline")
    return violations


def main() -> int:
    violations = find_direct_sends(CHAT_DIR)
    if violations:
        print("\n".join(violations), file=sys.stderr)
        print(
            "Chat provider sends must consume the request budget via "
            "crate::request_deadline::send_with_deadline (#9835, FC-per-hop-timeout).",
            file=sys.stderr,
        )
        return 1
    print("chat send-deadline contract: no direct provider sends in routes/chat/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
