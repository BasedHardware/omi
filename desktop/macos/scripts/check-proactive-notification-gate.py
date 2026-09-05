#!/usr/bin/env python3
"""Keep proactive notifications on the one path that consults the user's controls.

This is a **static checker**, not behavioral coverage. It exists because the hazard
it guards is invisible at runtime and invisible in review: a new delivery lane that
calls the presentation primitive directly still shows a card, still looks correct in
a demo, and simply ignores every control the user has. Nothing errors, nothing logs,
and the only symptom is a user being interrupted after asking not to be.

The gates live in `NotificationService.sendNotification`:

    master Notifications toggle   (#6778)
    frequency throttle
    snooze          — "Silence Notifications" for a bounded window
    presence        — screen share / in a call

`FloatingControlBarManager.showNotification` is the primitive underneath all of
them and enforces none. Two lanes were found bypassing it, which is why this
checker exists rather than a third copy of the guard:

  * `presentContextDirectorNotification` presented director cards straight through
    the primitive while marking them `isProactive: true`.
  * `NotchMomentsCoordinator.post` posted "Omi wrote this down" receipts the same
    way, while its own doc comment claimed it was "routed through the existing
    hardened notification path".

The rule enforced here is deliberately cheap and sound: only the files below may
name the primitive. Anything else must go through `NotificationService`, which is
where the decision about whether the user wants to be interrupted belongs.

Allowlisted callers, each because it is NOT proactive:

  ProactiveAssistants/Services/NotificationService.swift
      The gated path itself — this is where the primitive is supposed to be called.
  FloatingControlBar/FloatingControlBarWindow.swift
      The manager's own implementation; `showNotification` is defined here.
  TrialBannerService.swift
      Trial expiry and billing state. A user who silenced suggestions still has to
      learn their trial ended, or the silence costs them the product.
  Onboarding/OnboardingChatView.swift
      Permission help during onboarding. Suppressing the message that explains how
      to grant a permission is how a broken permission stays broken.

Comments and string literals are blanked before matching, so prose mentioning the
primitive (including this file's own rationale, quoted in a Swift comment) is not
reported.
"""

import argparse
import pathlib
import re
import sys

PRIMITIVE = "showNotification"
MANAGER = "FloatingControlBarManager"

ALLOWLIST = {
    "Sources/ProactiveAssistants/Services/NotificationService.swift",
    "Sources/FloatingControlBar/FloatingControlBarWindow.swift",
    "Sources/TrialBannerService.swift",
    "Sources/Onboarding/OnboardingChatView.swift",
}

CALL = re.compile(rf"{MANAGER}\s*\.\s*shared\s*\.\s*{PRIMITIVE}\s*\(")


def mask_comments_and_strings(source: str) -> str:
    """Blank out comments and string literals, preserving offsets and newlines."""
    out = []
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            j = source.find("\n", i)
            j = n if j == -1 else j
            out.append(" " * (j - i))
            i = j
        elif ch == "/" and nxt == "*":
            j = source.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append("".join(c if c == "\n" else " " for c in source[i:j]))
            i = j
        elif ch == '"':
            j = i + 1
            while j < n:
                if source[j] == "\\":
                    j += 2
                    continue
                if source[j] == '"':
                    j += 1
                    break
                if source[j] == "\n":
                    break
                j += 1
            out.append("".join(c if c == "\n" else " " for c in source[i:j]))
            i = j
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def violations(root: pathlib.Path):
    found = []
    for path in sorted(root.rglob("*.swift")):
        rel = path.relative_to(root.parent).as_posix()
        if rel in ALLOWLIST:
            continue
        if "/Tests/" in f"/{rel}" or rel.startswith("Tests/"):
            continue
        masked = mask_comments_and_strings(path.read_text(encoding="utf-8", errors="replace"))
        for match in CALL.finditer(masked):
            line = masked.count("\n", 0, match.start()) + 1
            found.append((rel, line))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--root",
        default="desktop/macos/Desktop/Sources",
        help="Swift sources root to scan",
    )
    args = parser.parse_args()

    root = pathlib.Path(args.root)
    if not root.is_dir():
        print(f"check-proactive-notification-gate: no such directory: {root}", file=sys.stderr)
        return 2

    found = violations(root)
    if not found:
        print("check-proactive-notification-gate: OK")
        return 0

    print(
        "check-proactive-notification-gate: proactive delivery must go through "
        "NotificationService.sendNotification, which applies the master toggle, frequency "
        "throttle, snooze and presence gates.\n",
        file=sys.stderr,
    )
    for rel, line in found:
        print(f"  {rel}:{line}: calls {MANAGER}.shared.{PRIMITIVE} directly", file=sys.stderr)
    print(
        "\nIf the notification is genuinely functional (billing, permissions, onboarding) and "
        "must reach a user who silenced suggestions, add it to ALLOWLIST in this script with "
        "the reason — do not relax the rule.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
