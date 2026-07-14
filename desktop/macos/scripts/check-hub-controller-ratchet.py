#!/usr/bin/env python3
"""Static tripwire: keep RealtimeHubController from regrowing extracted policies.

INV-VOICE-1 / PTT Phase 2: pure close/commit/lifecycle/owner/reconnect/barge-in,
input-admission, turn-persistence, spawn-receipt, and tool-authority types were
extracted out of RealtimeHubController.swift. History shows that file regrows
two ways — (1) pasting an extracted declaration back into the hub, and (2)
accreting new inline logic until the file is huge again.

This is an anti-regression ratchet, not a full architecture linter:

  Guard 1 — ownership boundary. Explicit extracted top-level type names must not
  reappear as top-level declarations in RealtimeHubController.swift. Update
  EXTRACTED_TYPE_NAMES in the same commit that moves a type.

  Guard 2 — line-count ratchet. RealtimeHubController.swift may not exceed
  LINE_COUNT_BASELINE (post-extraction count + 10% headroom). Raise the baseline
  only in the same PR that justifies the growth in the PR body; prefer extracting
  new logic into one of the policy files instead.

Static tripwire by design (AGENTS.md): this checker reads production source and
asserts declaration/line contracts. It is not behavioral coverage.

Wiring (see also `scripts/pre-push` and `.github/checks-manifest.yaml`):
  - Pre-push / CI: run when the hub or this script changes.
  - Manually:  python3 desktop/macos/scripts/check-hub-controller-ratchet.py
  - Self-test: ... --self-test
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

# Relative to the repository root.
HUB_RELATIVE = "desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeHubController.swift"

# Post-Phase-2 hub line count (4532) + 10% headroom. MAY ONLY INCREASE with an
# explicit PR justification; prefer extracting new logic into a policy file.
LINE_COUNT_BASELINE = 4985

# Top-level types extracted in Phase 2. Keep in sync with the policy files.
EXTRACTED_TYPE_NAMES: frozenset[str] = frozenset(
    {
        # RealtimeHubSessionPolicies.swift
        "RealtimeHubCloseCategory",
        "RealtimeHubSessionRotationPlan",
        "RealtimeHubCloseClassifier",
        "RealtimeHubCommitResult",
        "RealtimeHubCommitOwnershipPolicy",
        "RealtimeProviderToolResult",
        "RealtimeProviderToolResultPolicy",
        "RealtimeHubLifecycleSnapshot",
        "RealtimeHubLifecyclePolicy",
        "RealtimeHubOwnerScope",
        "RealtimeHubOwnerBoundarySnapshot",
        "RealtimeLocalProfileTransportAuthority",
        "RealtimeHubOwnerFence",
        "RealtimeNativeAudioScheduleFailureAction",
        "RealtimeHubToolFailureKind",
        "RealtimeHubToolFailure",
        "RealtimeHubReconnectIdentityPolicy",
        "RealtimeHubEventOwnership",
        "VoiceAudioIngressOwnership",
        "RealtimeHubErrorOwnership",
        "RealtimeHubBargeInAction",
        "RealtimeProviderTurnDoneDisposition",
        "RealtimeHubBargeInContinuity",
        # RealtimeHubInputAdmission.swift
        "RealtimeReconnectAudioBuffer",
        "RealtimeReplacementAudioBuffer",
        "RealtimeInputAdmissionDecision",
        "RealtimeInputAdmissionPolicy",
        "RealtimeVoiceContextRefreshPolicy",
        "RealtimeInputPreparationResult",
        # RealtimeTurnPersistence.swift
        "RealtimeTurnPersistenceReceipt",
        "RealtimeTurnPersistenceLedger",
        "RealtimeTurnJournalAuthority",
        "RealtimeProviderFailureContinuity",
        "RealtimeHubContinuityRestore",
        "RealtimeHubTranscriptResolution",
        "RealtimeHubTranscriptPolicy",
        "InterruptedTurnPayload",
        # RealtimeSpawnReceipt.swift
        "RealtimeSpawnJournalReceipt",
        "RealtimeSpawnAgentToolOutcome",
        # RealtimeToolAuthority.swift
        "RealtimeAuthorizedToolInvocation",
        "RealtimeAuthorizedToolOwnership",
        "RealtimeExternalRunTerminalPolicy",
        "RealtimeExternalRunPromptPolicy",
        "RealtimePermissionToolIdentityPolicy",
        "RealtimeAutomationTranscriptOverridePolicy",
        "RealtimeAutomationTurnHarness",
        "RealtimePermissionTranscriptSettlementPolicy",
        "RealtimeToolTurnOwnership",
        "RealtimeExternalToolInvocationIdentity",
        "RealtimeAuthorizedInvocationReplayGate",
    }
)

DECL_RE = re.compile(
    r"^(?:public |internal |private |fileprivate |package )?"
    r"(?:enum|struct|final class|class|actor|protocol|typealias) (\w+)\b",
    re.MULTILINE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Repository root (default: inferred from this script's location).",
    )
    parser.add_argument(
        "--print",
        dest="print_status",
        action="store_true",
        help="Print hub line count and any ownership violations, then exit 0.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run in-memory fixtures proving both fail modes, then exit.",
    )
    return parser.parse_args()


def repo_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    # scripts/ -> desktop/macos -> desktop -> repo root
    return Path(__file__).resolve().parents[3]


def top_level_declarations(source: str) -> list[str]:
    return DECL_RE.findall(source)


def ownership_violations(source: str) -> list[str]:
    return sorted({name for name in top_level_declarations(source) if name in EXTRACTED_TYPE_NAMES})


def line_count(source: str) -> int:
    # Match `wc -l`: count newline-terminated lines; a final non-newline chunk counts.
    if not source:
        return 0
    return source.count("\n") + (0 if source.endswith("\n") else 1)


def check_source(source: str, *, path_label: str) -> list[str]:
    errors: list[str] = []
    for name in ownership_violations(source):
        errors.append(
            f"{path_label}: extracted type {name!r} must not be redeclared here "
            f"(owning file is one of RealtimeHubSessionPolicies / "
            f"RealtimeHubInputAdmission / RealtimeTurnPersistence / "
            f"RealtimeSpawnReceipt / RealtimeToolAuthority)."
        )
    count = line_count(source)
    if count > LINE_COUNT_BASELINE:
        errors.append(
            f"{path_label}: line count {count} exceeds baseline {LINE_COUNT_BASELINE}. "
            "RealtimeHubController grew past the ratchet. Extract the new logic into "
            "one of the policy files, or raise the baseline in this script in the same "
            "PR and justify it in the PR body."
        )
    return errors


def run_self_test() -> None:
    """Prove both fail modes without touching the real hub file."""
    clean = "import Foundation\n\nfinal class RealtimeHubController {}\n"
    clean_errors = check_source(clean, path_label="fixture-clean.swift")
    if clean_errors:
        raise SystemExit(f"self-test false positive on clean fixture: {clean_errors}")

    ownership_fail = (
        "import Foundation\n\n"
        "enum RealtimeHubCloseCategory: String { case expectedIdleTeardown }\n"
        "final class RealtimeHubController {}\n"
    )
    ownership_errors = check_source(ownership_fail, path_label="fixture-ownership.swift")
    if not any("RealtimeHubCloseCategory" in error for error in ownership_errors):
        raise SystemExit(
            f"self-test missed ownership fail mode; errors={ownership_errors!r}"
        )

    # Force a line-count failure without an ownership violation.
    with tempfile.TemporaryDirectory() as tmp:
        fat = "import Foundation\n" + ("// pad\n" * (LINE_COUNT_BASELINE + 5))
        fat += "final class RealtimeHubController {}\n"
        fat_path = Path(tmp) / "fat.swift"
        fat_path.write_text(fat, encoding="utf-8")
        fat_errors = check_source(fat_path.read_text(encoding="utf-8"), path_label=str(fat_path))
    if not any("line count" in error for error in fat_errors):
        raise SystemExit(f"self-test missed line-count fail mode; errors={fat_errors!r}")
    if any("RealtimeHubCloseCategory" in error for error in fat_errors):
        raise SystemExit(f"self-test line-count fixture had ownership noise: {fat_errors!r}")


def main() -> int:
    args = parse_args()
    if args.self_test:
        run_self_test()
        print("OK: hub-controller ratchet self-test passed (ownership + line-count fail modes).")
        return 0

    root = repo_root(args.root)
    hub_path = root / HUB_RELATIVE
    if not hub_path.is_file():
        print(f"FAIL: hub file not found: {hub_path}", file=sys.stderr)
        return 1

    source = hub_path.read_text(encoding="utf-8")
    count = line_count(source)
    violations = ownership_violations(source)

    if args.print_status:
        print(f"{HUB_RELATIVE}: {count} lines (baseline {LINE_COUNT_BASELINE})")
        if violations:
            print("ownership violations:")
            for name in violations:
                print(f"  - {name}")
        else:
            print("ownership violations: none")
        return 0

    errors = check_source(source, path_label=HUB_RELATIVE)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(
        f"OK: RealtimeHubController ownership boundary clean; "
        f"line count {count} within baseline {LINE_COUNT_BASELINE}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
