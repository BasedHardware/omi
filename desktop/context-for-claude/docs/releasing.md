# Releasing Context for Claude

Context for Claude has its own product identity, Developer ID bundle signature, Sparkle EdDSA key
pair, artifact names, and release tag namespace. The release path is separate from the Omi Desktop
release workflow, while reusing the same Apple certificate import and App Store Connect
notarization inputs in Codemagic.

The entry point is `scripts/release-context.sh`. It delegates common tag validation, version
injection, Sparkle ZIP signing, and GitHub publication to the config-driven
`scripts/release-micro-app.sh`. The package script remains responsible for assembling and signing the
Context app, nested Sparkle code, DMG, and ZIP enclosure.

## One-time setup

### Sparkle update key pair

Use the Sparkle tools matching the pinned dependency (`2.9.4` in `Package.resolved`):

```sh
tar xf Sparkle-2.9.4.tar.xz
./bin/generate_keys
```

Store the generated values in the Codemagic secret group `context_for_claude_release`:

- `CONTEXT_SPARKLE_PUBLIC_KEY`: the 44-character base64 public key printed by `generate_keys`.
- `CONTEXT_SPARKLE_PRIVATE_KEY`: the private key exported with
  `./bin/generate_keys -x /secure/offline/context-for-claude-eddsa.key`.

The private value is read through standard input by Sparkle's `sign_update`; it is never printed,
written to the repository, or included in a release artifact. Keep an offline backup. Rotating this
key makes every existing installation unable to verify future updates, so a rotation requires a
manual reinstall and a coordinated updater change.

The source `Resources/Info.plist` intentionally retains its placeholder public key. Release builds
inject `CONTEXT_SPARKLE_PUBLIC_KEY` into the copied bundle plist. Release mode fails closed if the
key is absent or still the placeholder; ordinary local development builds continue to work without
release secrets and remain unable to auto-update.

### GitHub publication

Create `CONTEXT_GITHUB_TOKEN` as a fine-grained token scoped to `BasedHardware/omi` with repository
Contents write permission (including releases) and Metadata read permission. Store it only in the
`context_for_claude_release` group. The helper uses it through `GH_TOKEN`, never as a command-line
argument.

### Apple signing and notarization

Add the existing `appstore_credentials` group to the Context workflow. It supplies the Apple inputs
shared safely with Omi's notarization machinery:

- `MACOS_DEVELOPER_ID_P12` and `MACOS_DEVELOPER_ID_P12_PASSWORD` for the Developer ID Application
  certificate.
- `APP_STORE_CONNECT_PRIVATE_KEY`, `APP_STORE_CONNECT_KEY_IDENTIFIER`, and
  `APP_STORE_CONNECT_ISSUER_ID` for `xcrun notarytool`.

Context does not use Omi's Sparkle private key, bundle identifier, artifact names, or release
metadata. Codemagic maps the App Store Connect values to the package script's `CFC_ASC_*` variables
without logging them. No provisioning profile is needed for this Developer ID distribution bundle.

For a local release rehearsal, a keychain notary profile may be used instead:

```sh
xcrun notarytool store-credentials "context-notary" \
  --apple-id you@example.com --team-id TEAMID --password <app-specific-password>
```

Then set `CFC_NOTARY_PROFILE=context-notary` and use a local Developer ID identity. Do not use a
self-signed identity for a release.

## Release flow

The tag convention is:

```text
context-for-claude-v<major>.<minor>.<patch>
```

For example, `context-for-claude-v1.1.0` publishes:

- `ContextForClaude-1.1.0.dmg` for manual installation.
- `ContextForClaude-1.1.0.zip` as the Sparkle enclosure.

The helper derives a deterministic numeric Sparkle build number from the tag (`major * 1,000,000 +
minor * 1,000 + patch`) and injects both version fields into the built plist. This keeps the source
template untouched while ensuring Sparkle sees an increasing numeric build for increasing stable
versions.

Before creating a tag, run the no-secret local validation:

```sh
cd desktop/context-for-claude
./scripts/test-release-path.sh
./scripts/release-context.sh \
  --tag context-for-claude-v1.1.0 \
  --dry-run
```

This validates the tag, artifact names, package entry point, and any supplied public/private key
presence without building, notarizing, signing, publishing, or changing source files.

A maintainer then creates and pushes the tag:

```sh
git tag context-for-claude-v1.1.0
git push origin context-for-claude-v1.1.0
```

Codemagic workflow `context-for-claude-release` accepts only that tag prefix. It performs this
sequence:

1. Imports the existing Developer ID certificate into the Codemagic keychain.
2. Resolves SwiftPM and builds ContextApp plus `context-for-claude-mcp`.
3. Injects the Context public key and tag-derived versions into the built `Info.plist`.
4. Signs the app, MCP executable, Sparkle framework, and every present nested Sparkle XPC/helper
   component inside-out with the Context Developer ID identity.
5. Notarizes and staples the app, creates the DMG, then signs, notarizes, and staples the DMG.
6. Creates the Sparkle ZIP from the stapled app and signs that ZIP with
   `CONTEXT_SPARKLE_PRIVATE_KEY`.
7. Publishes both artifacts to the GitHub release at the exact tag. The release body contains a
   generated `KEY_VALUE_START` block with the product slug, numeric build, artifact name, and EdDSA
   signature.

The generic backend feed reads that GitHub release metadata and the `ContextForClaude-*.zip` asset.
Do not hand-edit an appcast XML file and do not add an appcast commit to a Context release. The helper's
GitHub release publication is the release operation.

## Verification before announcing a release

Check the exact shipped identity and Team ID against the preceding release:

```sh
codesign -dv --verbose=2 "dist/Context for Claude.app" 2>&1 \
  | grep -E '^(Identifier|Authority|TeamIdentifier|Runtime Version)='
xcrun stapler validate "dist/ContextForClaude-1.1.0.dmg"
codesign --verify --deep --strict "dist/Context for Claude.app"
unzip -t "dist/ContextForClaude-1.1.0.zip"
```

`Identifier` must be `com.omi.context-for-claude`. The leaf authority and Team ID must match the
previous public release, and `TeamIdentifier` must not be `not set`. A changed Team ID silently
revokes Screen Recording, Microphone, and System Audio consent after Sparkle replaces the bundle;
stop the release if it differs.

The GitHub release must contain exactly the Context DMG and Context Sparkle ZIP, with no Omi Desktop
asset. Confirm that the release body has a non-empty `edSignature` and numeric `build` metadata. A
missing signature or a placeholder public key is a hard release failure, not a warning.

## First-install upgrade constraint

Sparkle can update only a Context installation that already has the same product identity and signing
continuity:

- The first public installation must be the notarized Developer ID Context DMG or an equivalent
  manually installed bundle signed by the same Apple Team.
- A local `Omi Local Dev Signing` build, a self-signed build, a placeholder-key build, or a build
  signed by another Team cannot receive the public release through Sparkle. Install the first public
  release manually, then future releases can update it.
- Never point Context at an Omi feed or reuse Omi's EdDSA key. The bundle ID, feed scope, certificate
  Team ID, and EdDSA key are separate trust boundaries.

## Rollback and recovery

If a release is bad before users install it, stop it at the GitHub release source: remove or unpublish
the offending GitHub release using the repository's release-operator procedure. The generic feed
will stop selecting a deleted/draft release after its cache window; do not edit an XML appcast.
Preserve the tag and incident evidence where policy requires it, and do not reuse the tag for a
different ZIP.

If users have already installed the bad release, Sparkle will not install a lower numeric build.
Publish a repaired release with the same Context identity and a higher version/build, then verify the
new DMG and ZIP before announcing it. A rollback is therefore a feed withdrawal for not-yet-installed
clients followed by a higher-build forward fix for installed clients; it is not a downgrade.

## Local commands

Normal development remains independent of release secrets:

```sh
./scripts/build.sh --no-install
```

For a local package smoke test with the development identity and no Finder automation:

```sh
./scripts/package-dmg.sh --no-style
```

This is not a distributable release. It must not be uploaded or used as a Sparkle update.
