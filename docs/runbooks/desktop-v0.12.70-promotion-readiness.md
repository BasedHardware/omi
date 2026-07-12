# Desktop v0.12.70 Promotion Readiness

Read-only snapshot taken July 11, 2026. This pack distinguishes artifact
readiness, beta visibility, canonical channel state, stable nomination, and
stable promotion. Those are separate gates. No workflow or Firestore mutation
was performed while preparing this record. A second live read at `23:26 UTC`
found no drift in any canonical, legacy, appcast, redirect, GitHub, or desktop
backend surface. A third read at `00:40 UTC` on July 12, after the Python backend
cutover, again found no drift; that deploy did not mutate desktop release state.

## Decision summary

`.70` is already visible to beta clients through legacy GitHub/Firestore and
static beta surfaces. It is **not** canonically registered: the immutable `.70`
manifest and both explicit Firestore channel pointers are absent. Stable remains
`.0`. The immediate operation, if product still chooses `.70`, is therefore
manual canonical beta convergence, not first beta exposure and not stable
promotion.

A newer `v0.12.71+12071-macos` tag exists but is non-live, unqualified, and has a
failed Codemagic check. `.70` is the newest live beta but not the newest tag, so
`automatic=true` will correctly reject `.70`. Before stable nomination, make an
explicit product decision between shipping the qualified `.70` or fixing and
qualifying `.71` first.

## Immutable `.70` identity

| Item | Verified value |
| --- | --- |
| Tag | `v0.12.70+12070-macos` |
| Source SHA | `2bdd18a7e397b4c7aab8199443def178c0e9b0e0` |
| Bundle ID | `com.omi.computer-macos` |
| Version / build | `0.12.70` / `12070` |
| `Omi.zip` SHA-256 | `5904314bb6a26a9466e0cfb4cce1cdc72aeaa556d26c959141b671b939acd0cc` |
| `omi.dmg` SHA-256 | `24db5a53c7c32db9a7b9e20a02b061171d7ccf7b6a7948ae633c03951075883a` |
| Qualification evidence | `qualification-evidence-0.12.70+12070-20260711T060737Z.json`, Tier 2, passed, exact source SHA |
| Qualification evidence SHA-256 | `cbf38fa79938bbd2bc869412e1674d1ee03e0afb88fbc6561475ffbe12cdc9b0` |

Local verification against the published artifacts showed:

- both hashes exactly match GitHub release digests and qualification evidence;
- the ZIP expands to a universal arm64/x86_64 app with hardened runtime;
- deep/strict nested signature verification passes;
- the app and DMG both pass Gatekeeper as notarized Developer ID artifacts;
- stapler validation passes for both app and DMG;
- the signing identity is Based Hardware INC, team `9536L8KLMP`;
- the declared microphone, screen-capture, and Apple Events entitlements are
  present, and App Sandbox is intentionally disabled.

The GitHub release is published, live beta, and qualified. Its title still says
`(candidate)` and its body contains older beta-waiver/stable-blocked prose that
predates the later Tier-2 qualification; the convergence workflow should make
the title/metadata coherent. Do not mutate the ZIP or DMG.

Codemagic build `6a51ab4a8cfd15fd9002cec4` is red after the signed,
notarized, stapled artifacts and release were produced. The exact later failing
step was not available from the public API, so this record does not invent a
cause. The separately published Tier-2 evidence passed.

The product owner has explicitly accepted `.70` as the good code version and
waived another local app retest. Do not rebuild, repackage, or repeat UI/code
validation while promoting this exact artifact. Remaining work is release-state
convergence, current telemetry review, and exact channel verification.

## Current channel truth

| Surface | Beta | Stable |
| --- | --- | --- |
| Python appcast | `.70` via legacy fallback | `.0` |
| Rust desktop-backend appcast | `.70` | `.0` |
| Static beta redirect | `.70` | Not applicable |
| Legacy Firestore release | `.70`, beta, live | `.0`, stable, live |
| Canonical immutable manifest | Missing for `.70` | No canonical stable manifest/pointer |
| Explicit channel pointer | `macos-beta` missing | `macos-stable` missing |
| Desktop backend health/tracking tag | Not a beta decision surface | `.0` at `51a88843b2301ad7bb13599b08d8fbfe7a5bef6f` |

The failed `.70` stable nomination run was GitHub Actions `29142470735`; it
stopped because the beta pointer was missing. No `.70` stable promotion has
succeeded.

The Python backend contention hotfix is an operational prerequisite for this
release sequence, not part of the macOS artifact identity. Backend prepare and
resume deploy source `f92baff14418bfa46b64ac84f1eb64715855d32e`; canonical
macOS registration must still preserve desktop source
`2bdd18a7e397b4c7aab8199443def178c0e9b0e0` and the published `.70` asset
digests above. Neither backend phase writes the immutable `.70` manifest or the
`macos-beta` pointer, and `.70` remains beta-visible through the legacy surfaces
while backend rollout is in progress. The Python `backend` service is also
distinct from the Rust `desktop-backend`: the latter's `.0` health and traffic
identity are a later stable-promotion gate, not part of canonical beta
registration.

## Gate 1: canonical beta convergence

This is state-changing and requires explicit release authorization. If `.70`
remains the intended target, the Python backend prerequisite is now satisfied:
guarded resume run `29173381925` succeeded and its bounded production soak was
clean. The post-cutover release-state refresh still found the canonical
manifest and `macos-beta` pointer absent. Dispatch exactly:

```bash
gh workflow run desktop_promote_beta.yml \
  --repo BasedHardware/omi \
  --ref main \
  -f release_tag='v0.12.70+12070-macos' \
  -f automatic=false
```

The workflow should register the immutable manifest, advance `macos-beta`,
normalize GitHub beta metadata, reconcile the legacy bridge/static redirect, and
clear caches. Because `.71` is newer, do not change `automatic` to true.

After success, require all of these to agree before nomination:

- immutable manifest source SHA and both asset digests match this document;
- qualification tier/evidence remain attached and passed;
- `macos-beta` references the exact `.70` manifest and has a valid generation;
- `macos-stable` is still absent and stable clients still resolve `.0`;
- legacy `.70` remains live beta;
- Python and Rust appcasts resolve `.70` beta + `.0` stable;
- static beta redirect still resolves the exact `.70` DMG;
- GitHub title/body/channel are coherent and assets/digests are unchanged.

The convergence workflow is idempotent. If it fails after manifest creation but
before pointer promotion, rerun the exact workflow. If the pointer advanced,
rerun remaining idempotent steps; do not point beta backward.

## Gate 2: choose `.70` or `.71`, then nominate

Do not reuse the July 11 06:14 UTC nomination prose as current evidence. Refresh:

1. beta soak duration, cohort size, updater success/failure, and crash-free rate;
2. auth persistence, microphone, screen capture, chat/agent, voice, and PTT
   telemetry, calling out low sample sizes;
3. beta/stable updater resolution and exact asset-digest evidence without
   rebuilding or locally retesting the accepted `.70` app;
4. stable release-note rollup from `.0` through the chosen candidate;
5. the explicit reason to prefer qualified `.70` over newer unqualified `.71`,
   or the decision to stop and qualify `.71` instead.

Only after that review, nominate with the exact input names:

```bash
gh workflow run desktop_nominate_stable_candidate.yml \
  --repo BasedHardware/omi \
  --ref main \
  -f release_tag='v0.12.70+12070-macos' \
  -f rationale='<current product and risk rationale>' \
  -f soak_review='<current soak evidence>' \
  -f telemetry_review='<current crash/update/health evidence>' \
  -f release_notes_review='<current stable rollup review>'
```

Nomination must change metadata only. Reverify that beta remains `.70` and
stable remains `.0` afterward.

## Gate 3: separately authorize stable promotion

Stable promotion is a distinct, high-blast-radius decision. With a successful
nomination and separate explicit approval, inputs are:

```text
release_tag=v0.12.70+12070-macos
confirm=promote-stable
break_glass=false
break_glass_confirm=
break_glass_reason=
```

Before dispatch, snapshot:

- `desktop-backend-00883-tcp`, its image, 100% traffic, `.0` health identity,
  and tracking tag;
- both legacy release documents, canonical pointers/manifests, GitHub release
  metadata, asset hashes, static redirects, and both appcasts.

The last simple rollback boundary is before the workflow promotes the legacy
Firestore release stable. If backend traffic moved but health identity fails
before feed mutation, restore 100% to `desktop-backend-00883-tcp`, verify `.0`
health/SHA/channel, and stop. After either legacy `.70` or the explicit stable
pointer advances, the release system is intentionally roll-forward-only: retry
remaining idempotent steps for a good artifact, or qualify and promote a newer
fixed build. Do not try to move stable back to `.0`.

Final stable acceptance requires:

- desktop-backend health reports exact `.70` tag, SHA, and stable channel;
- exact new revision/image serves 100%, and the tracking tag matches the `.70`
  source SHA;
- canonical beta and stable pointers reference the exact immutable manifest;
- legacy `.70` is stable/live and nomination metadata remains preserved;
- Python/Rust appcasts and beta/stable downloads resolve intended exact assets;
- no digest drift, cache mismatch, updater regression, or telemetry regression.

## Follow-up debt

- Resolve why the `.70` and `.71` Codemagic checks failed after artifact stages,
  and make the failing step available in durable qualification evidence.
- Convert legacy plaintext secret values preserved in the desktop-backend Cloud
  Run template to explicit Secret Manager bindings through a reviewed migration;
  do not mix that change into incident-time stable promotion.
- Add one read-only release-state command that reports GitHub metadata, exact
  hashes, canonical pointers/manifests, legacy bridge, appcasts, backend health,
  and tracking tag in one deterministic snapshot.
