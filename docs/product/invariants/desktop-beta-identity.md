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
  result (`desktop-smoke-result-beta.json`) held to the same qualification
  contract as stable, and its own appcast EdDSA signature (`betaEdSignature`).
- The update feed is identity-aware: `identity=beta` serves beta-channel items
  with beta-identity enclosures only, and must never offer a stable-identity
  artifact to the beta app (Sparkle in-place replacement would corrupt the
  install's identity). Releases without beta artifacts are omitted from the
  beta-identity feed.
- Single-artifact or same-byte promotion refactors may reorganize how stable is
  promoted, but they must not remove the beta identity, its packaged artifacts,
  or the identity-aware feed. Retiring this invariant is a product decision that
  requires the founder's explicit sign-off in the PR — it is not an available
  simplification for release-pipeline hardening (this happened once:
  `dba3af2522` reverted the feature and was re-landed).

## Guard tests

- `desktop/macos/Desktop/Tests/AppBuildBetaIdentityTests.swift` — identity,
  gating, storage, log-path, manual-download identity contracts
- `desktop/macos/Desktop/Tests/DesktopStorageIdentityTests.swift` — isolated
  "Omi Beta" storage root
- `.github/scripts/test_check_desktop_auto_beta_candidate.py` — beta smoke held
  to the stable qualification contract; codemagic beta invocation produces every
  piece of gate-required evidence
- `backend/tests/unit/test_desktop_updates.py::TestBetaIdentityServing` —
  identity-aware appcast/download serving, stable feed unchanged

## Path globs

- `desktop/macos/Desktop/Sources/AppBuild.swift`
- `desktop/macos/Desktop/Sources/OmiSupport/DesktopLocalProfile.swift`
- `desktop/macos/scripts/create-omi-beta-variant.sh`
- `backend/routers/updates.py`
- `codemagic.yaml`
