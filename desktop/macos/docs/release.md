# Desktop release

Normal path: merge `main` → `Build Desktop Release Candidate` waits a bounded time for the three exact-SHA source checks. If it consolidates changelog fragments, it regular-merges the generated changelog PR first, then creates and natively pushes one immutable lightweight tag on that exact fresh `origin/main` merge SHA; the separately retained planner source-identity artifact binds that tag to its SHA and changelog provenance. Without changelog changes, the planner tags only the unchanged fresh `main` SHA. Codemagic builds, signs, notarizes, smokes, and publishes that immutable candidate, then promotes Beta to the exact tag through the server-owned admission endpoint. If an immutable `v*-macos` tag already owns the selected source SHA, the planner exits without another tag; an active or published normal candidate is preserved, and an anomalous lifecycle remains blocked rather than duplicated.

`omi-desktop-swift-release` starts only from Codemagic's native `v*-macos` tag trigger. Never start the normal candidate lane with a direct Codemagic `/builds` API POST; that API is reserved for the isolated preview workflow. For bounded, read-only candidate status polling, run from the repository root:

```bash
python3 .github/scripts/plan-desktop-release.py \
  --repository BasedHardware/omi \
  --watch-source-sha <40-character-source-sha> \
  --watch-max-polls 5 \
  --watch-poll-seconds 30
```

The watcher reports only lifecycle transitions and never creates tags or builds, promotes channels, or changes release pointers.

The self-hosted T2/fault harness remains available for engineering QA, but it is not a Beta release gate. The signed-artifact rehearsal below is the release-path diagnostic for Codemagic failures.

## Failed Codemagic build rehearsal

A failed canonical Codemagic check triggers **Desktop Release Recovery Required**. Its job summary and retained JSON capsule bind the build ID, immutable tag, source SHA, failed step, sanitized diagnostics, and whether the step is locally reproducible. This is the just-in-time handoff for operators and agents; do not infer a fix from the generic Codemagic check title alone.

For a locally reproducible bundle-audit or signed-smoke failure, run the capsule's exact command manually. On a managed Omi Mac:

```bash
. "$HOME/.config/omi/codemagic-env.sh"
desktop/macos/scripts/rehearse-desktop-release.sh \
  --codemagic-build-id <24-character-build-id> \
  --clean \
  --failed-step <failure-profile>
```

The rehearsal validates the provider build identity, workflow, tag, source SHA, terminal failure, failed-step log URL, and artifact URL before downloading anything. `--clean` performs an isolated arm64 release compile of the caller's current source (the proposed fix, not the failed tag), then the command replays the exact signed Stable or Beta Sparkle archive from the failed build, including the Keychain and UserNotifications canaries. Evidence records both identities plus current dirty state and a tracked-diff digest, and is retained under Ephemeral scratch by default. It cannot dispatch Codemagic, create or move a tag, publish a release, or update Beta/Stable. Universal assembly, Developer ID signing, notarization/stapling, and DMG packaging remain provider-only gates.

Run this loop only in response to a failed Codemagic build. Do not create a replacement candidate until the rehearsal passes or the recovery capsule classifies the failure as provider-only.

If a signed candidate did not reach Beta, rerun the same Codemagic tag build. Candidate publication and Beta promotion are idempotent; the backend rechecks immutable signed-smoke evidence, admission state, and the pointer transaction.

To make that exact current Beta candidate Stable, run **Promote Desktop Beta to Stable** with `release_tag` and `confirm=promote-stable`. It reads the current pointer, uses its generation for the atomic transition, and verifies the published pointer, hashes, and appcast. It only changes the desktop Stable channel; backend production deployment remains a separate approval plane. The promotion records the live backend SHAs it observed on the pointer (`serving_backends`) and prints a drift table against `origin/main` in the run summary. That table is provenance, not a new promotion block.

Do not edit release bodies, pointers, static routes, or legacy bridges manually.
