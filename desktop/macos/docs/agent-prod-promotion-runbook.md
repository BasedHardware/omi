# Desktop Stable Pointer Promotion

Stable promotion is a protected distribution-pointer operation. It never deploys a desktop backend or creates a second backend environment.

1. Read the current `macos-beta` and `macos-stable` pointer release IDs and generations.
2. Confirm the requested tag is the current qualified Beta release and retain the successful trusted `desktop_qualify_beta.yml` run ID. That GitHub Actions artifact records all four exact Stable/Beta ZIP/DMG URLs, hashes, and Sparkle signatures.
3. Run `desktop_promote_prod.yml` in the protected `prod` environment with that `qualification_run_id`, `confirm=promote-stable`, the observed Stable `expected_current_release_id` and `expected_generation`, and `operation=promote`.
4. The workflow reads the immutable manifest already retained by Beta, advances the Stable pointer, updates the legacy appcast/static bridge, and verifies pointer identity, hashes, and feed output.

For a controlled repoint, use `operation=repoint` with the target's exact currently observed Stable release ID and generation. The target may be any retained passed-T2 immutable manifest; it need not first become current Beta. Repointing reads that already-retained manifest; it does not require a `qualification_run_id` or register a manifest. Repointing stops future rollout; Sparkle does not downgrade clients already on a higher build, so ship a higher-version hotfix for those clients.

The GitHub Actions run is the audit trail. Do not edit a release body, Firestore pointer, static route, or legacy bridge manually. Backend deployments remain separate established workflows.

Qualification evidence is layered: source-built named-bundle T2/fault coverage is not signed-artifact T2. The exact signed artifact evidence is signing/notarization and signed-smoke proof. A real promotion record must additionally cover the signed `.89` upgrade, `.70` side-by-side install, core journeys, and soak using the same immutable manifest that Stable advances.
