---
name: codesign-debug
description: "Debug code signing, notarization, and entitlement issues. Use when the app 'can't be opened', notarization fails, signing identity errors, entitlement mismatches, or provisioning profile issues. Triggers: 'can't be opened', 'notarization', 'code signing', 'entitlements', 'Developer ID'."
---

# Code Signing & Notarization Debug

## Signing Identity

- **Identity**: `Developer ID Application: Matthew Diakonov (S6DP5HF77G)`
- **Team ID**: `S6DP5HF77G`
- **Apple ID** (for notarization): `matthew.heartful@gmail.com`
- **Notarization password**: Stored in `.env` as `NOTARIZE_PASSWORD` (app-specific password)

## Bundle Identifiers

| Context | Bundle ID | Used By |
|---------|-----------|---------|
| **Production/Release** | `com.omi.computer-macos` | `release.sh`, `build.sh`, `distribute.sh`, `build-local-prod.sh` |
| **Development** | `com.omi.desktop-dev` | `run.sh`, `dev.sh`, `reset-and-run.sh` |

The app name is `Omi Beta` and the binary name is `Omi Computer`.

## Entitlement Files

Three entitlement files in `Desktop/`:

### `Omi.entitlements` -- Development builds (`run.sh`, `dev.sh`)
- `com.apple.security.app-sandbox` = **false**
- `com.apple.security.automation.apple-events` = true
- `com.apple.security.get-task-allow` = **true** (allows debugging)
- `com.apple.security.device.audio-input` = true
- `com.apple.security.device.screen-capture` = true
- `com.apple.developer.applesignin` = Default (Sign In with Apple)

### `Omi-Release.entitlements` -- Release builds (`release.sh`, `build-local-prod.sh`)
- `com.apple.security.app-sandbox` = **false**
- `com.apple.security.automation.apple-events` = true
- `com.apple.security.device.audio-input` = true
- `com.apple.security.device.screen-capture` = true
- **No** `get-task-allow` (would break notarization)
- **No** `applesignin` (would require provisioning profile for Gatekeeper)

### `Node.entitlements` -- Bundled Node.js binary (for Claude Agent Bridge)
- `com.apple.security.cs.allow-jit` = true
- `com.apple.security.cs.allow-unsigned-executable-memory` = true

Node.js requires JIT entitlements for V8 and WebAssembly. Without these, Hardened Runtime blocks MAP_JIT causing SIGTRAP on launch.

## Provisioning Profiles

Two profiles in `Desktop/`:
- `embedded.provisionprofile` -- Production (used by `release.sh`)
- `embedded-dev.provisionprofile` -- Development (used by `run.sh`)

Copied into `$APP_BUNDLE/Contents/embedded.provisionprofile`. Required for native Sign In with Apple. Dev builds prefer the dev profile; release builds use the production profile.

## Release Signing Pipeline

Full pipeline in `release.sh` (12 steps). Signing-relevant steps:

1. **Step 1.5-1.6**: Prepare universal ffmpeg and Node.js binaries (ad-hoc signed with `codesign -f -s -`)
2. **Step 2**: Build universal binary (arm64 + x86_64) via `lipo`
3. **Step 3**: Sign app with Developer ID
   - `xattr -cr` to remove extended attributes first
   - Sign ffmpeg (no special entitlements)
   - Sign node with `Node.entitlements` (JIT permissions)
   - Sign native `.node`/`.dylib`/`rg` binaries in agent-bridge node_modules
   - Sign Sparkle framework components (innermost first: XPC services, Autoupdate, Updater.app, framework)
   - Sign main app with `Omi-Release.entitlements` and `--options runtime --timestamp`
4. **Step 4**: Notarize app (`xcrun notarytool submit --wait`)
5. **Step 5**: Staple notarization ticket (`xcrun stapler staple`)
6. **Step 6**: Create DMG using `create-dmg`, copy app with `ditto` (preserves extended attributes/stapling ticket)
7. **Step 7**: Sign DMG with Developer ID
8. **Step 8**: Notarize DMG
9. **Step 9**: Staple DMG

## Dev Build Signing

`run.sh` and `dev.sh` auto-detect signing identity:
1. Prefer **Apple Development** (matches Mac Development provisioning profile for native Sign In with Apple)
2. Fall back to **Developer ID Application**
3. Last resort: ad-hoc (`--sign -`) -- TCC permissions reset every build with ad-hoc

Dev builds use `Omi.entitlements` (includes `get-task-allow` for debugging).

## Diagnostic Commands

```bash
# Check app signature details
codesign -dvv /Applications/Omi\ Beta.app

# Verify signature integrity (deep checks frameworks/helpers)
codesign --verify --deep --strict /Applications/Omi\ Beta.app

# Check entitlements on the signed app
codesign -d --entitlements :- /Applications/Omi\ Beta.app

# Gatekeeper assessment (what users experience)
spctl --assess --verbose=2 /Applications/Omi\ Beta.app

# Gatekeeper assessment for DMG
spctl --assess --verbose=2 --type open --context context:primary-signature build/Omi\ Beta.dmg

# Verify notarization stapling
xcrun stapler validate /Applications/Omi\ Beta.app

# Check notarization history
xcrun notarytool history --apple-id "matthew.heartful@gmail.com" --team-id "S6DP5HF77G"

# Get notarization log for a submission
xcrun notarytool log <submission-id> --apple-id "matthew.heartful@gmail.com" --team-id "S6DP5HF77G"

# List available signing identities
security find-identity -v -p codesigning

# Check what the system sees for the app (Launch Services)
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -dump | grep -A20 "com.omi.computer-macos"

# Check embedded entitlements vs provisioning profile
codesign -d --entitlements - /Applications/Omi\ Beta.app 2>/dev/null | grep -c "com.apple.application-identifier"
```

## Common Issues

### "App can't be opened" / "damaged" / Gatekeeper rejection

**Causes (most to least common):**
1. **Missing notarization stapling ticket** -- The DMG was created with `cp -R` instead of `ditto`, which strips extended attributes including the stapling ticket. Fix: always use `ditto` to copy the app before creating DMG. This was a real bug (see CHANGELOG: "Fixed missing notarization stapling ticket in DMG").
2. **`com.apple.application-identifier` in entitlements** -- If this entitlement is present without a matching provisioning profile, Gatekeeper rejects with EPOLICY 163. The release entitlements (`Omi-Release.entitlements`) intentionally omit `applesignin` to avoid this. The `verify-release.sh` script checks for this.
3. **`get-task-allow` in release entitlements** -- This entitlement is rejected by notarization. Only `Omi.entitlements` (dev) has it, not `Omi-Release.entitlements`.
4. **Quarantine attribute** -- Remove with `xattr -cr /Applications/Omi\ Beta.app`.
5. **Stale Launch Services registration** -- Multiple copies of the app confuse Launch Services. Reset with: `/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -kill -r -domain local -domain user`

### Node.js / Agent Bridge crash (SIGTRAP)

Node.js requires JIT entitlements under Hardened Runtime. The node binary in the resource bundle must be signed with `Node.entitlements` (allows JIT and unsigned executable memory). Without this, V8 crashes on launch with SIGTRAP due to MAP_JIT being blocked.

```bash
# Verify node has JIT entitlements
codesign -d --entitlements :- /Applications/Omi\ Beta.app/Contents/Resources/Omi\ Computer_Omi\ Computer.bundle/node
# Should show: com.apple.security.cs.allow-jit = true
```

### Notarization Rejection

Common reasons:
- **Unsigned binaries** inside the app bundle (ffmpeg, node, .node native modules, .dylib files). All must be signed with the Developer ID.
- **Missing `--options runtime`** -- Hardened Runtime is required for notarization.
- **Missing `--timestamp`** -- Secure timestamp required for notarization.
- **Third-party frameworks** not properly signed -- Sparkle components must be signed innermost-first (XPC services before framework).

Check the notarization log for specifics:
```bash
xcrun notarytool log <submission-id> --apple-id "matthew.heartful@gmail.com" --team-id "S6DP5HF77G"
```

### Keychain Access Prompts During Build

If `codesign` prompts for keychain access repeatedly:
```bash
# Unlock keychain for the session
security unlock-keychain -p "$(security find-generic-password -a $USER -s login-keychain -w 2>/dev/null || echo '')" ~/Library/Keychains/login.keychain-db

# Or allow codesign to access the key without prompt
security set-key-partition-list -S apple-tool:,apple:,codesign: -s ~/Library/Keychains/login.keychain-db
```

### TCC Permission Reset After Rebuild

Ad-hoc signed builds (`--sign -`) generate a new CDHash each build, causing macOS to reset Screen Recording, Accessibility, and Notification permissions. Use a stable identity (Apple Development or Developer ID) to avoid this. The `run.sh` script auto-detects available identities for this reason.

### Dev vs Release Entitlement Mismatch

If Sign In with Apple works in dev but not release (or vice versa):
- Dev builds use `Omi.entitlements` which includes `com.apple.developer.applesignin` and the dev provisioning profile
- Release builds use `Omi-Release.entitlements` which omits `applesignin` to avoid Gatekeeper issues
- Release builds fall back to web-based OAuth for Apple Sign-In (see `AuthService.swift` line 219)

## Post-Release Verification

Run `./verify-release.sh` to automatically verify:
1. Appcast is serving the correct version
2. Download URL works
3. Code signature is valid (deep verification)
4. Gatekeeper accepts the app
5. No provisioning-profile-dependent entitlements
6. App launches successfully
7. DMG download endpoint works

CI also runs `.github/workflows/test-install.yml` which verifies code signature, Gatekeeper assessment, and notarization stapling on a clean macOS runner.
