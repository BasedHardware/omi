# Local Code Signing

How `run.sh` signs a local dev or named test bundle, and why the entitlements it
generates depend on the signing identity's Team ID. The one-line rule lives in
[`../AGENTS.md`](../AGENTS.md) → Development Workflow → Building & Running.

## Identity resolution order

`run.sh` (`resolve_signing_identity`) picks the first that exists:

1. `OMI_SIGN_IDENTITY` — explicit override.
2. `Apple Development` — preferred, because local permissions stay stable.
3. `Developer ID Application`.
4. `Omi Local Dev Signing` — the stable self-signed local identity, **created
   automatically** if it does not exist.
5. Ad-hoc (`-`) — only with **both** a named bundle and `OMI_ALLOW_ADHOC_SIGN=1`.

Each candidate is **probed, not merely found**: the script signs a throwaway file
with it before committing. An identity can be listed and still be unusable — see
§`errSecInternalComponent` — and choosing one on the strength of its existence
turns a two-second fallback into a build that fails a minute later, after the
compile and a 265 MB bundle copy.

### `Omi Local Dev Signing` is created automatically

`run.sh` creates it on demand when no Apple identity is usable. Nothing to do, no
GUI, no password, and it works in CI and over ssh where the wizard below cannot.
It is generated with `/usr/bin/openssl` (LibreSSL, stock on every Mac) into its
own keychain — `~/Library/Keychains/omi-local-dev-signing.keychain-db`, whose
password the script owns, which is what lets it grant `codesign` a partition
without a prompt. Set `OMI_SKIP_LOCAL_SIGN_IDENTITY=1` to opt out.

Two details worth knowing if you touch that code:

- The PKCS#12 must use the legacy encoding (`-certpbe PBE-SHA1-3DES -keypbe
  PBE-SHA1-3DES -macalg sha1`). OpenSSL 3's AES/SHA256 default imports as
  `MAC verification failed during PKCS12 import (wrong password?)`, which is
  not a password problem at all.
- The certificate needs `extendedKeyUsage = codeSigning` and `CA:false`, or
  `codesign` declines the identity.

**A self-signed identity does not appear in `security find-identity -v -p
codesigning`** — that list filters on policy trust — yet `codesign -s "Omi Local
Dev Signing"` works fine. Check usability by signing something, not by listing:

```bash
cp /usr/bin/true /tmp/probe && codesign --force --sign "Omi Local Dev Signing" /tmp/probe
```

To create it by hand instead (Keychain Access → Certificate Assistant → *Create a
Certificate…*): name `Omi Local Dev Signing` exactly, Identity Type *Self Signed
Root*, Certificate Type *Code Signing*.

## The entitlement decision keys on the Team ID

Hardened-runtime **library validation** only lets a process load third-party code
whose signature carries the *same Team ID*. The Team ID comes from the signing
certificate's Organizational Unit. A self-signed certificate has no OU, so
`codesign -dvv` reports `TeamIdentifier=not set` — putting it in exactly the same
position as ad-hoc signing, even though it is a real named identity.

`scripts/prepare-local-dev-entitlements.sh` therefore classifies identities by
resolved Team ID, not by identity string:

| Mode | When | `com.apple.security.cs.disable-library-validation` |
|---|---|---|
| `teamless` | ad-hoc (`-`), or any identity whose signature has no Team ID | granted |
| `team-scoped` | Apple Development, `Developer ID Application: Based Hardware INC (9536L8KLMP)` | **never** granted |

`--validate-identity` is the single authority: it rejects configurations that
must not be used and prints the mode that then selects the entitlements, so a
configuration that validates is exactly the one that gets signed. Resolve a Team
ID with `--identity-team-id "<identity>"`, which reads it back off a real
signature rather than guessing from the identity's name.

Production is unaffected. The release pipeline signs in Codemagic with the
Developer ID above (Team ID `9536L8KLMP`) against the checked-in
`Desktop/Omi.entitlements`, and never invokes this script. Even if it did, a
Team-ID identity classifies `team-scoped` and keeps full library validation.

## Symptom when it is wrong

Signing a bundle with a teamless identity but team-scoped entitlements produces
an app that cannot launch:

```
dyld: Library not loaded: @rpath/Sparkle.framework/Versions/B/Sparkle
  … mapping process and mapped file (non-platform) have different Team IDs
```

The same rule rejects the bundled Sentry and onnxruntime frameworks.

**The failure hides from the usual checks:**

- `codesign --verify` **passes** — the signature really is valid. What fails is a
  launch-time Team ID match, not signature integrity.
- `open -a` **exits 0** and nothing starts.

The only way to see the real reason is to run the executable directly:

```bash
"/Applications/omi-<feature>.app/Contents/MacOS/Omi Computer" 2>&1 | head
```

Confirm a good bundle instead with:

```bash
codesign -dvv "/Applications/omi-<feature>.app" 2>&1 | grep -E 'Authority|TeamIdentifier|flags'
codesign -d --entitlements :- "/Applications/omi-<feature>.app" | grep -o 'disable-library-validation'
```

## `errSecInternalComponent`: the session, not the certificate

An agent, a CI job, or any shell started outside the GUI login session hits this,
and it is the single most misdiagnosed failure in this file:

```
build/<app>.app/Contents/Frameworks/Sparkle.framework: replacing existing signature
build/<app>.app/Contents/Frameworks/Sparkle.framework: errSecInternalComponent
```

**The certificate is fine. The keychain is unlocked. You are the right user.** What
is missing is authorization to *use* the private key from a process that cannot be
shown a dialog.

macOS normally resolves an unlisted caller by having SecurityAgent ask — *"codesign
wants to use key X. Allow / Always Allow"*. A process whose `launchctl managername`
reports `Background` rather than `Aqua` has no window server connection, so that
dialog cannot be drawn and the Security framework fails the call immediately rather
than hanging. `security` reports the same condition as exit 36, and
`security show-keychain-info` says it outright: `User interaction is not allowed.`

Diagnose it in one line before assuming anything about the identity:

```bash
launchctl managername            # Aqua = can prompt; Background = cannot
```

Two checks that will mislead you if you skip the one above:

- `security find-identity -v -p codesigning` **lists the identity** — presence is not
  permission.
- `security unlock-keychain -p <deliberately-wrong-password> login.keychain-db`
  **returns 0** when the keychain is already unlocked, so a locked keychain is not
  the explanation.

### The fix, once, permanently

Grant `codesign` a standing partition on the key, from a terminal in the GUI session:

```bash
security set-key-partition-list -S apple-tool:,apple:,codesign: -s \
  -l "Apple Development: YOUR NAME (XXXXXXXXXX)" ~/Library/Keychains/login.keychain-db
```

Omit `-k` so it prompts for the keychain password rather than recording it in shell
history. After this, signing works from any session, including background ones.

`run.sh` detects this failure and prints this remedy with your identity already
substituted, so you should never have to find this section from a raw error.

### The same wall blocks auth seeding

`scripts/omi-auth-dump.sh` reads Firebase tokens from a team-scoped Keychain item.
From a background session it prints `WARNING: no auth_idToken found — is the source
bundle signed in?` **even when the source bundle is signed in** — the UserDefaults
half reads fine and the secret does not. Same cause, same shape of fix:

```bash
security set-generic-password-partition-list -S apple-tool:,apple:,security: \
  -s "com.omi.desktop.firebase-rest-session.v2.team.<TEAM>.bundle.com.omi.desktop-dev" \
  -a firebase-rest-tokens ~/Library/Keychains/login.keychain-db
```

## Do not "fix" a launch failure with ad-hoc signing

`OMI_ALLOW_ADHOC_SIGN=1` looks like it works, and it is worse. An ad-hoc
signature has no stable designated requirement, so it invalidates that bundle's
own Screen Recording TCC grant: Rewind silently stops capturing and the app
reports `0 screen moments` while still appearing in the Settings list. A stable
self-signed identity pins its certificate in the designated requirement, so
permissions survive rebuilds — that is the whole reason to prefer it.

## Tests

```bash
cd desktop/macos && bash tests/test-prepare-local-dev-entitlements.sh
```

Registered as manifest check `desktop-local-dev-entitlements` (macOS, `local`
and `ci` lanes). It drives the real classification through the script's CLI and
runs `run.sh`'s own `resolve_signing_identity` and
`local_entitlements_fallback_reason` function bodies against injected identity
metadata.
