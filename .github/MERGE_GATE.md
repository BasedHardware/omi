# Omi merge gate

`Omi Merge Gate` is the single status that branch protection should require.
It is produced by the trusted default-branch
[`pr-merge-gate.yml`](workflows/pr-merge-gate.yml) controller from the explicit
[`merge-gate-manifest.json`](merge-gate-manifest.json) inventory. The controller
observes exact-head Actions metadata; it never executes pull-request content.

The desired protection settings are recorded in
[`required-branch-policy.json`](required-branch-policy.json). That file is a
reviewable policy contract, **not** a GitHub REST request body and not proof that
the live repository is protected.

## Bootstrap and activation

An administrator must perform these steps in order:

1. Merge the controller without making its not-yet-existing status required.
2. Open one same-repository canary PR and one fork canary PR. On each exact head,
   verify that `Omi Merge Gate` starts pending and becomes successful only after
   every applicable workflow succeeds.
3. Rerun one required workflow. Verify that the aggregate returns to pending on
   `workflow_run` reconciliation, then follows the rerun to failure or success.
4. In repository or organization rules, prefer **Require workflows to pass** for
   `.github/workflows/pr-merge-gate.yml` when that control is available. Otherwise
   require the exact `Omi Merge Gate` context and select GitHub Actions as its
   expected source. Require the strict/up-to-date mode.
5. Apply the remaining review, code-owner, conversation-resolution, admin, and
   no-bypass settings from `required-branch-policy.json`. Use evaluate mode first
   when a ruleset provides it; activate only after the canaries pass.
6. Read the live settings back. Do not infer activation from a successful API
   response or from this file existing:

   ```bash
   gh api repos/BasedHardware/omi/branches/main/protection
   gh api repos/BasedHardware/omi/rulesets --paginate
   ```

Confirm that exactly one intended rule stack governs `main`, the required gate
has the expected source, administrators do not bypass it, review settings match
the policy contract, and no actor has an ordinary merge bypass.

## Recovery

- Fix and rerun the failed underlying workflow. Its requested/in-progress/
  completed lifecycle automatically reconciles the aggregate.
- If GitHub did not deliver a reconciliation event, rerun the trusted merge-gate
  controller or make a harmless PR metadata edit to trigger a new exact-head
  evaluation. Never post or override the status manually.
- If the status reports event-association, manifest, or unknown-evidence errors,
  treat that as a control-plane incident. Repair the evidence path; do not weaken
  branch protection to clear the PR.
- Before changing a PR workflow name, trigger, or path filter, update the merge
  manifest and reconciler list in the same PR. The local contract check enforces
  this for canonical workflow syntax.

After activation, a periodic audit should compare the two live API responses
above with `required-branch-policy.json`; configuration drift is a failure, not
an advisory warning.
