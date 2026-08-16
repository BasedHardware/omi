# Local Code Signing

How `run.sh` signs a local dev or named test bundle, and why the entitlements it
generates depend on the signing identity's Team ID. The one-line rule lives in
[`../AGENTS.md`](../AGENTS.md) → Development Workflow → Building & Running.

## Identity resolution order

`run.sh` (`resolve_signing_identity`) picks the first that exists:

1. `OMI_SIGN_IDENTITY` — explicit override.
2. `Apple Development` — preferred, because local permissions stay stable.
3. `Developer ID Application`.
4. `Omi Local Dev Signing` — the stable self-signed local identity.
5. Ad-hoc (`-`) — only with **both** a named bundle and `OMI_ALLOW_ADHOC_SIGN=1`.

### Creating `Omi Local Dev Signing`

Do this once on a machine with no Apple certificate; `run.sh` then finds it with
no environment variable:

Keychain Access → Certificate Assistant → *Create a Certificate…*

- **Name**: `Omi Local Dev Signing` (exact — `run.sh` matches on this)
- **Identity Type**: Self Signed Root
- **Certificate Type**: Code Signing

Confirm it is visible to codesign:

```bash
security find-identity -v -p codesigning
```

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
