# INV-BETA-1: Omi Beta is a separate app that runs beside stable

**Status:** locked
**Statement:** The macOS beta channel ships as a separately-installable app
identity (`com.omi.computer-macos.beta`, display name "Omi Beta") that runs
side-by-side with the stable app (`com.omi.computer-macos`) on the same machine.
This is an explicit product decision by the founder (Nik, 2026-07-22): users —
including the team dogfooding beta — must be able to run beta and stable at the
same time, and the beta app must auto-update from a beta-identity artifact.

Consequences that must hold:

- The Swift app treats both identifiers as production-family
  (`AppBuild.productionFamilyBundleIdentifiers`): production gating, isolated
  "Omi Beta" storage root, per-identity production log path, pinned beta update
  channel on the beta identity.
- Every macOS candidate release packages the beta variant (`Omi.Beta.zip`,
  `omi-beta.dmg`) from the same build, signed/notarized, with its own smoke
  result (`desktop-smoke-result-beta.json`) held to the same structural
  signed-smoke contract as stable plus launch, Keychain, and notification
  callback probes, and its own appcast EdDSA signature (`betaEdSignature`).
- The update feed is identity-aware: `identity=beta` serves beta-channel items
  with beta-identity enclosures only, and must never offer a stable-identity
  artifact to the beta app (Sparkle in-place replacement would corrupt the
  install's identity). Releases without beta artifacts are omitted from the
  beta-identity feed. The default (stable-identity) feed serves only the stable
  channel: Stable.app must not Sparkle-install beta-channel `Omi.zip`. Early
  access is the separately-installable Omi Beta app, not an in-place channel
  switch. Stable-identity clients already on a newer-than-stable build freeze
  until `macos-stable` surpasses them.
- Single-artifact or same-byte promotion refactors may reorganize how stable is
  promoted, but they must not remove the beta identity, its packaged artifacts,
  or the identity-aware feed. Retiring this invariant is a product decision that
  requires the founder's explicit sign-off in the PR — it is not an available
  simplification for release-pipeline hardening (this happened once:
  `dba3af2522` reverted the feature and was re-landed).

## Guard tests

- `desktop/macos/Desktop/Tests/AppBuildBetaIdentityTests.swift` — identity,
  gating, storage, log-path, identity-bound Sparkle channel, Get Omi Beta URL
- `desktop/macos/Desktop/Tests/DesktopStorageIdentityTests.swift` — isolated
  "Omi Beta" storage root
- `.github/scripts/check-release-process-guards.py` — Codemagic still smokes
  both identities via `desktop/macos/scripts/smoke-signed-desktop-artifact.sh`; the retired
  qualification lane cannot be reintroduced
- `backend/tests/unit/test_desktop_updates.py::TestBetaIdentityServing` —
  identity-aware appcast/download serving
- `backend/tests/unit/test_desktop_updates.py::TestAppcastEndpoint` —
  stable-identity feed omits beta-channel items

## Path globs

- `desktop/macos/Desktop/Sources/AppBuild.swift`
- `desktop/macos/Desktop/Sources/UpdaterViewModel.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/Settings/Components/SettingsContentView+Controls.swift`
- `desktop/macos/Desktop/Sources/OmiSupport/DesktopLocalProfile.swift`
- `desktop/macos/scripts/create-omi-beta-variant.sh`
- `backend/routers/updates.py`
- `codemagic.yaml`
