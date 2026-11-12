# #25024 integration record — 2026-11-10

Workspace: `/Volumes/scratch/worktrees/omi/omi-lane-processingtoday-upstream-keep-clean`,
branch `lane/processingtoday` on m1-mac-studio. Code checkpoint:
`7e9c6f6af99faae6f2445eeeee81e072a5931a8a` (later commits may only add evidence docs).
PR: https://github.com/BasedHardware/omi/pull/25024.

## Revert dependency resolved

Main revert #25037 landed as `d24d101cae0239838413bf537a80d5d68cf52018`. Fresh main
`35e63b5d701f94396cd166ef22db8df37aa947d4` was merged (no rebase) in `474edfb1b3efe9e6902e005c0699df9bee8627c1`.
All wanted #25013 source/test/changelog files exactly match the pre-merge
checkpoint `86b59df35fb11e878527d72c1869a9cd88688ce5`; no independent post-revert
edits existed on those paths. Rejected Home screenshots were left removed.
The steps below document the integration procedure; steps 1–3 are complete.
Schema regression, integrated preflight and the single normal full-hook push
are recorded in #25024's final body. No PR merge is authorized.

## Prepared implementation

- Mobile Home processes only today's local recorded day and excludes failures
  from every Home insertion/group/search/filter path. Activity owns failures
  with retry; completion updates the shared provider. Pending optionally echoes
  home_step; failed flag reads restore previous Home. episodeId is parsed and
  immediately owns Home rows before episode fetch.
- Web /conversations adds Activity; /home remains chat/tasks/goals. Native
  Conversations routes failures to existing Memory hub Activity and excludes
  them from the spine. Both require explicit pending-work confirmation.
- Loaded/list/search failures survive Home filters in account-scoped memory.
  Completion, local deletion and account resets clear them. Web retry updates
  list/search/cache immediately and fences older reads. Native observes shared
  data and passes the emitted flag value to the spine.
- Wanted #25013 parsing, reconciliation, terminal watcher stop and authoritative
  retry replacement remain. Its failed rows on default Home are dropped;
  previous rendering remains available for kill-switch rollback/direct detail.
- Main's schema inventory failure is fixed in conversations.dart: direct
  GeneratedSearchConversationsResponse decode, passed into the part helper.
  No schema assertion/allowlist or PCM guard was weakened.

## Finish once the revert lands

1. Fetch main and the feature branch; inspect unseen commits. Confirm the main
   revert in the log. Save the current local HEAD as the pre-merge checkpoint.
2. Merge fresh main without committing immediately. Inspect its changes to the
   #25013 paths before restoring wanted changes. Obtain the source with
   `gh pr diff 25013 -R BasedHardware/omi`; the existing scratch source diff and
   path list are `.agent-artifacts/pr25013-source.diff` and
   `.agent-artifacts/pr25013-source-paths.txt`.
3. Preserve the checkpoint versions of the wanted #25013 source/test/changelog
   files, resolving revert conflicts with these adapted versions. Inspect any
   independent fresh-main edits rather than overwriting them. Do not restore
   `.agent-artifacts/ui-evidence/lane-homestep-client/` rejected-Home screenshots;
   this directory has the replacement evidence. Commit the merge/re-land and
   record exact order/SHAs in the PR body and disposition record.
4. Run the schema inventory regression and required preflight/full push hook on
   the integrated tree. Tests/commands are in README.md. The ignored prepared
   PR body is `.agent-artifacts/processingtoday-pr-body.md`; rewrite its pending
   integration paragraph and pin every render URL to the final containing SHA.
   Fetch again before the normal push. Use OMI_PR_BODY_FILE for the full hook.
5. Update #25024's title/body around the final mobile/web/macOS Activity policy,
   post the commit-pinned raw render URLs, and report head + every disposition.
   Skip anx: refactor-lead records the outcome. Do not merge.

## Verification and evidence

Latest focused runs: 1,039 web Vitest tests plus typecheck/smoke; 103 selected
native tests; 14 schema inventory; 146 backend; 313 expanded Flutter and an
84-test search/reconciliation rerun; 35 tests in each of New York, Kiritimati
and Pago Pago; analyzer ratchet and generated Dart wire check. Final repository preflight passed all 88 checks after the filter supplement
at 13:34Z. Post-revert validation and the normal full push hook are reported in the final PR body.

Manifest: evidence.json, images 001–018. README contains reproduction commands.
Mobile captures real pages; web/native capture real production components.
Native manual mounted-destination flow is declared but not run as a signed app
session. No production endpoint/account, cloud change, merge or deploy.

Deferred limits: bounded historical discovery, episode-only debt outside the
loaded range, unstamped old empty captures, capped earliest-due ordering,
unmeasured live latency and physical/signed-session behavior. PCM CPU-duration
guard remains untouched; its pre-existing main failure is documented in the
prepared PR body and prereview-dispositions.md.


Latest follow-up: Luna 6206927c's web off-page remembered-failure retry is fixed;
see prereview-dispositions.md for implementation and cross-client validation.
The PNGs are unchanged. PR #25024 remains on hold for David's render verdict;
never merge from this handoff. Full-hook push and head are recorded in the PR body.
