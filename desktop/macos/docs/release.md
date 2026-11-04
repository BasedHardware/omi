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

## Release train mechanics

`desktop_auto_release.yml` runs on an hourly `schedule` (plus manual `workflow_dispatch` retries — there is no `push` trigger). Each run tags the newest releasable `desktop/macos/**`/`codemagic.yaml` change since the last tag, coalescing every merge in the window and binding the immutable tag to the Codemagic config that builds it. A candidate reaches Beta automatically after Codemagic finishes the signed release build:

1. **GitHub Actions** (`desktop_auto_release.yml`) — the planner auto-increments the version and pushes a timestamped annotated `v*-macos` tag. Every invocation passes `--min-tag-interval-seconds 3600`, so scheduled and manual retries create at most one candidate per hour, measured from the previous candidate's GitHub-release `createdAt` after publication or its annotated-tag creation time while still building. A ~60s quiet window (`AUTO_RELEASE_QUIET_SECONDS`) coalesces near-simultaneous merges; the one-active-release fence (Codemagic build status on the latest tag) admits one candidate at a time. GitHub compile queues do not gate tagging: the tag stays on the exact newest source, or its mechanically verified changelog-only child, while later macOS merges remain queued for the next hourly candidate. The workflow immediately API-dispatches exactly one same-tag `omi-desktop-swift-release` build, verifies its immutable source identity, and retains JSON intake evidence; retries reuse an existing exact-tag build instead of duplicating it.
2. **Codemagic** (`codemagic.yaml`, workflow `omi-desktop-swift-release`) — API-dispatched with the immutable tag, runs on Mac mini M4 and owns compile/release admission:
   - Builds the universal app and dSYM, UUID-checks the dSYM against the executable, and always publishes the verified dSYM with the release so crashes stay symbolicable offline
   - Signs with Developer ID, notarizes with Apple
   - Creates DMG + Sparkle ZIP
   - Runs `scripts/smoke-signed-desktop-artifact.sh` (signed app, Sparkle ZIP, DMG) before publishing, with a mandatory in-app Keychain write/read/delete canary
   - Publishes an immutable GitHub candidate with stable and Beta signed-smoke evidence
   - Calls the internal-only Beta admission endpoint with the exact tag; the backend independently verifies the merged tag, GitHub asset digests, and Beta signed-smoke evidence, then atomically registers the immutable manifest and advances the explicit Beta pointer

The self-hosted T2/fault harness remains available for engineering QA, but it is not a Beta release gate. The signed-artifact rehearsal below is the release-path diagnostic for Codemagic failures. If Codemagic exhausts its bounded promotion retries, the candidate remains non-live; recover with `desktop_recover_beta.yml` using the exact tag, `confirm=recover-beta`, and a reason.

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

To make that exact current Beta candidate Stable, run **Promote Desktop Beta to Stable** with `release_tag` and `confirm=promote-stable`. It reads the current pointer, uses its generation for the atomic transition, advances only that pointer, updates the existing legacy/static bridges, and verifies the published pointer, hashes, and appcast. It only changes the desktop Stable channel; backend production deployment remains a separate approval plane. Stable promotion checks live desktop chat-contract compatibility but does not deploy the backend. The promotion records the live backend SHAs it observed on the pointer (`serving_backends`) and prints a drift table against `origin/main` in the run summary. That table is provenance, not a new promotion block.

Do not edit release bodies, pointers, static routes, or legacy bridges manually.

## Signed artifact smoke scope

- Always-on release audit covers bundle identity, version/tag alignment, signing/Keychain entitlements, Sparkle metadata, backend URL leakage, helper/runtime packaging, artifact readability, and local storage package surface.
- Stable artifacts are fixed to production Python/Rust services. The separately-installable Beta artifact is fixed to development Python/Rust services, while desktop-login OAuth plus Firebase Auth/Firestore remain production; signed smoke proves the artifact routing. Exercise a real human OAuth sign-in separately before broad rollout.
- Codemagic uploads stable and Beta smoke results with artifact digests and completed checks; the backend fetches both results concurrently and compares them to the exact immutable release assets before changing channels.
- The synthetic `--auth-storage-canary` is mandatory before beta publication and runs inside the exact signed app without real credentials. Optional broader live probes (`--launch --network --auth --chat --permissions --storage`) require an isolated release runner and explicit canary env vars; production-bundle launch is fail-closed unless `OMI_SIGNED_ARTIFACT_SMOKE_ALLOW_PRODUCTION_LAUNCH=1`, and `--auth` requires `OMI_SIGNED_ARTIFACT_SMOKE_AUTH_PROOF_COMMAND` to prove app-level persistence rather than a raw bearer-token curl.
- Artifact creation and user visibility are split: create/upload the immutable candidate first, then advance Beta visibility only after its digest-matched signed smoke passes.
- Automatic Beta is fail-closed: any signed-smoke, reservation, digest, manifest, admission-generation, or pointer failure leaves the candidate non-live. Operators pause/resume only through the ADMIN_KEY-protected backend admission control; workflow variables are not pause authority. When a served Beta is concretely broken, `desktop_rollback_beta.yml` and `desktop_breakglass_rollout_beta.yml` retain their audited incident-only behavior. Rollback does not downgrade already-updated clients; follow it with a higher-build repair.

Stable is manual: Codemagic never promotes Stable. `desktop_promote_prod.yml` remains `workflow_dispatch` only and protected by the `prod` environment.

## Backend deployment workflows

The shared Python backend must contain the manifest/pointer endpoints before the first beta promotion. Deploy it separately with `gcp_backend.yml`; `desktop_backend_auto_dev.yml` owns development Python desktop-backend delivery, while `desktop_backend_prod.yml` and `desktop_backend_recover_prod.yml` own protected production delivery and retained-revision recovery. Merging desktop code does not deploy either production backend. Static GCS/CDN feed ownership remains follow-up work and is not the channel source of truth.

## Codemagic CLI & API

- Token: `$CODEMAGIC_API_TOKEN` (set in `~/.zshrc`)
- App ID: `66c95e6ec76853c447b8bcbb`
- List builds: `curl -s -H "x-auth-token: $CODEMAGIC_API_TOKEN" "https://api.codemagic.io/builds?appId=66c95e6ec76853c447b8bcbb" | python3 -c "import json,sys; [print(f\"{b.get('status','?'):12} tag={b.get('tag','-'):30} start={(b.get('startedAt') or '-')[:19]}\") for b in json.load(sys.stdin).get('builds',[])[:5]]"`
