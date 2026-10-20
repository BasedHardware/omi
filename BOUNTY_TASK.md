# Bounty Objective: Bounty Proposal: Reusable Deploy Ancestry Guard & CI Pipeline Hardening ($100 - $125 USD)
Target: BasedHardware/omi Issue #22860
URL: https://github.com/BasedHardware/omi/issues/22860

## Issue Description
### Bounty Proposal: Reusable Deploy Ancestry Guard & CI Pipeline Hardening ($100 - $125 USD)

**Pull Request:** https://github.com/BasedHardware/omi/pull/21192
**Closes Issue:** https://github.com/BasedHardware/omi/issues/20941
**Target Maintainers:** @kodjima33 @nikpetrovic @josancamon19

#### Description
Implements an end-to-end reusable ancestry guard and verification CLI for backend deployments as requested in #20941. Mechanically verifies whether a given release SHA actually contains the intended merge/commit SHA using GitHub's Commits Compare API (avoiding heavy git checkouts).

#### Key Improvements Delivered
1. **Ancestry Verification CLI (`backend/scripts/verify_deploy_ancestry.py`)**:
   - Exit code `0` iff `<contains>` is a true ancestor of `<release>`.
   - Defensive validation: rejects non-40-hex inputs, nil sentinels, and sanitizes authorization tokens from all diagnostic logs.
2. **Workflow Wiring (`.github/workflows/gcp_backend_pusher.yml` & `gcp_backend.yml`)**:
   - Integrated optional `expected_ancestor_sha` input into workflow dispatch.
   - Non-blocking advisory warnings on verification mismatches, recording structured release metadata into `$GITHUB_STEP_SUMMARY`.
3. **Hermetic Test Suite (`backend/tests/unit/test_verify_deploy_ancestry.py`)**:
   - 14/14 unit tests passing hermetically with full network/API mocking.
   - Re-verified and dismissed previous changes-requested review; confirmed `mergeable: true` with zero conflicts.
4. **Runbook Documentation (`backend/docs/runbooks/backend-deploy-rollout-safety.md`)**:
   - Added operator documentation on CLI usage flags, exit codes (0/1/2), and emergency release verification protocols.

#### Designated Payout Rail
- **EVM (Base / Arbitrum / Polygon USDC)**: `0x2821d6003ceE245C4997Ff908029aa0116177b69`


## Instructions for Kuro (Autonomous Solver):
1. Use skills: `systematic-debugging` and `code-review-and-quality`.
2. Inspect the repository structure, locate relevant files, and understand the bug/feature.
3. Apply the minimal, robust fix or implementation.
4. Run any existing test suites or linters in the workspace.
5. Ensure the fix adheres to the project's existing code style.
6. When done, output a summary of files modified and verification results.
