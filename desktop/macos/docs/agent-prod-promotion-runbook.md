# Desktop Stable Pointer Promotion

Stable promotion is a protected distribution-pointer operation. It never deploys a desktop backend or creates a second backend environment.

1. Read the current `macos-beta` and `macos-stable` pointer release IDs and generations.
2. Confirm the requested tag is the current qualified Beta release and has the exact signed ZIP/DMG evidence.
3. Run `desktop_promote_prod.yml` in the protected `prod` environment with `confirm=promote-stable`, the observed Stable `expected_current_release_id` and `expected_generation`, and `operation=promote`.
4. The workflow registers the exact immutable manifest, preserves/publishes the immutable repair artifact, advances the Stable pointer, updates the legacy appcast/static bridge, and verifies pointer identity, hashes, and feed output.

For a controlled repoint, use `operation=repoint` with the exact currently observed Stable release ID and generation. The target must be a retained qualified manifest. Repointing stops future rollout; Sparkle does not downgrade clients already on a higher build, so ship a higher-version hotfix for those clients.

The GitHub Actions run is the audit trail. Do not edit a release body, Firestore pointer, static route, or legacy bridge manually. Backend deployments remain separate established workflows.
