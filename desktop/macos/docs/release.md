# Desktop release

Normal path: merge `main` → `Build Desktop Release Candidate` waits a bounded time for the three exact-SHA source checks. If it consolidates changelog fragments, it regular-merges the generated changelog PR first, then creates and natively pushes one immutable lightweight tag on that exact fresh `origin/main` merge SHA; the separately retained planner source-identity artifact binds that tag to its SHA and changelog provenance. Without changelog changes, the planner tags only the unchanged fresh `main` SHA. Trusted qualification then promotes that exact artifact to Beta automatically. If an immutable `v*-macos` tag already owns the selected source SHA, the planner exits without another tag; an active or published normal candidate is preserved, and an anomalous lifecycle remains blocked rather than duplicated.

`omi-desktop-swift-release` starts only from Codemagic's native `v*-macos` tag trigger. Never start the normal candidate lane with a direct Codemagic `/builds` API POST; that API is reserved for the isolated preview workflow. For bounded, read-only candidate status polling, run from the repository root:

```bash
python3 .github/scripts/plan-desktop-release.py \
  --repository BasedHardware/omi \
  --watch-source-sha <40-character-source-sha> \
  --watch-max-polls 5 \
  --watch-poll-seconds 30
```

The watcher reports only lifecycle transitions and never creates tags or builds, dispatches qualification, promotes channels, or changes release pointers.

If a signed, qualified candidate did not reach Beta, run **Recover Qualified Desktop Beta** with `release_tag`, `confirm=recover-beta`, and a short `reason`. The backend rechecks immutable evidence, qualification, admission state, and the pointer transaction; the workflow run is the recovery audit record.

To make that exact current Beta candidate Stable, run **Promote Qualified Desktop Stable** with `release_tag` and `confirm=promote-stable`. It reads the current pointer, uses its generation for the atomic transition, and verifies the published pointer, hashes, and appcast. It only changes the desktop Stable channel; backend production deployment remains a separate approval plane.

Do not edit release bodies, pointers, static routes, or legacy bridges manually.
