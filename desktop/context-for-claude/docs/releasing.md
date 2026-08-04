# Releasing Context for Claude

How a new version reaches people who already have the old one.

The app updates itself with [Sparkle](https://sparkle-project.org), the same mechanism
`desktop/macos` uses. It shares none of that app's identity: its own feed, its own signing key, its
own bundle. A user of this app must never see Omi's name, icon or release notes in an update prompt,
and the way that is guaranteed is that Sparkle draws all three from the running bundle and from
[`../appcast.xml`](../appcast.xml) — neither of which is Omi's.

---

## The invariant that matters more than the rest of this document

**Every release must be signed with the same Developer ID certificate and the same Team ID as the
release before it.**

macOS attaches Screen Recording, Microphone and System Audio consent to a code signature, not to a
path or a bundle identifier. This app is worth nothing without all three. An update replaces the
signed bundle, so an update signed by a different identity — a renewed certificate from a different
team, a second developer's cert, a build that fell back to the local dev identity — silently revokes
every grant every user has given. The app comes back looking healthy: menu bar item present, audio
still recording, screen capture returning nothing, forever, with no error anywhere.

That is not a hypothetical. On the machine this was written on, the installed bundle was re-signed at
14:33 and the last screen frame it ever captured was stamped 14:20 — thirteen minutes earlier — with
a day of launches after it and not one complaint from the app. An auto-updater is a way to do that to
everyone at once.

Two things enforce it:

- **`scripts/build.sh` prints the signing identity of every bundle it builds.** Compare it with the
  previous release before publishing (below).
- **`UpdatePolicy` refuses to update any bundle whose signature has no Team ID.** Locally built
  copies are signed with `Omi Local Dev Signing`, a self-signed certificate with no team, so a
  developer's build can never pull a real release down over itself. That is
  `UpdatePolicyTests.testALocallySignedCopyWithNoTeamIdentifierRefusesToUpdateItself`.

### Checking it

```sh
codesign -dv --verbose=2 "/Applications/Context for Claude.app" 2>&1 \
  | grep -E '^(Identifier|Authority|TeamIdentifier)='
```

All four of these must be identical to the previous release:

| Field | Must be |
|---|---|
| `Identifier` | `com.omi.context-for-claude` |
| `Authority` (leaf) | `Developer ID Application: <name> (<TEAMID>)` — the same certificate |
| `TeamIdentifier` | the same 10-character team, and **never** `not set` |
| `Runtime Version` | present, i.e. the hardened runtime is on |

`TeamIdentifier=not set` means a self-signed certificate. It is fine locally and must never ship.

If the certificate genuinely has to change — expiry, a team migration — that release cannot go out
through Sparkle. Ship it as a manual download with a note, because every user will have to re-grant
permissions and they need to be told beforehand, not discover it a week later.

---

## One-time setup

### 1. Generate the update key pair

Sparkle signs each update with EdDSA (Ed25519) and the app verifies it with the public half baked
into `Resources/Info.plist`. This is a **different** key from the code-signing certificate and does a
different job: the certificate says who built the app, this says who authorised this particular
download.

Get Sparkle's tools — the SwiftPM dependency does not ship them, so take them from the release
tarball for the version in `Package.resolved`:

```sh
# https://github.com/sparkle-project/Sparkle/releases → Sparkle-<version>.tar.xz
tar xf Sparkle-2.9.4.tar.xz
./bin/generate_keys
```

`generate_keys` does two things:

- Stores the **private key in your login keychain** as `Private key for signing Sparkle updates`. It
  is never written to a file and must never be committed, pasted into an issue, printed in CI logs,
  or copied to a second machine except through the deliberate export below.
- Prints the **public key**, a 44-character base64 string.

Put the public key in `Resources/Info.plist`, replacing the placeholder:

```xml
<key>SUPublicEDKey</key>
<string>REPLACE_WITH_SUPublicEDKey_FROM_generate_keys</string>
```

Until that is replaced, the updater is off. That is enforced, not incidental: `UpdatePolicy` treats
the placeholder as "not configured" and never starts Sparkle. It has to, because
`SPUStandardUpdaterController(startingUpdater: true, …)` calls `abort()` — a process kill — when it
is started in a bundle whose key it cannot use.

**Back the private key up before you need it.** Losing it means no existing install can ever be
updated again; there is no recovery, only a new key, a new build, and a manual reinstall for every
user.

```sh
./bin/generate_keys -x /Volumes/<somewhere-offline>/context-for-claude-eddsa.key   # export
./bin/generate_keys -f /Volumes/<somewhere-offline>/context-for-claude-eddsa.key   # import elsewhere
```

Keep that file off this machine and out of any repository. `.gitignore` will not save you from
`git add -f`.

### 2. Get a Developer ID certificate and a notary profile

Both are required — Gatekeeper refuses an unnotarized download with "damaged and can't be opened",
which users read as a broken app.

```sh
xcrun notarytool store-credentials "context-notary" \
  --apple-id you@example.com --team-id TEAMID --password <app-specific-password>
```

---

## Cutting a release

### 1. Bump the version

`Resources/Info.plist`:

- `CFBundleShortVersionString` — what people see (`1.1.0`)
- `CFBundleVersion` — a monotonically increasing integer. **Sparkle compares this, not the display
  version.** A build number that does not increase is an update nobody receives.

### 2. Build, sign, notarize, package

```sh
cd desktop/context-for-claude
CFC_SIGN_IDENTITY='Developer ID Application: <name> (<TEAMID>)' \
CFC_NOTARY_PROFILE='context-notary' \
  ./scripts/package-dmg.sh
```

This builds the app, embeds and re-signs `Sparkle.framework` inside-out, notarizes and staples both
the app and the image, and emits two artifacts in `dist/`:

- `ContextForClaude-<version>.dmg` — the manual download
- `ContextForClaude-<version>.zip` — **the Sparkle enclosure**, made with `ditto -c -k --keepParent`
  because that is the only zipper on macOS that preserves the symlinks inside a framework

It refuses to build the image at all if `Sparkle.framework` is missing from the bundle or if
`codesign --verify --deep --strict` fails, because both produce an app that will not launch on
somebody else's Mac and neither is visible in a DMG.

Confirm the verdict it prints says `Gatekeeper: ACCEPTED`, then re-check the signing identity against
the previous release using the table above.

### 3. Sign the enclosure

```sh
./bin/sign_update dist/ContextForClaude-1.1.0.zip
```

It prints the two attributes the appcast needs:

```
sparkle:edSignature="…" length="12345678"
```

It reads the private key straight out of the keychain. macOS will ask for permission the first time.

### 4. Publish the artifacts

Create a GitHub release tagged `context-for-claude-v<version>` — the prefix keeps it out of the way
of Omi's own `omi-desktop-*` tags — and attach both the `.zip` and the `.dmg`.

### 5. Append the appcast item

Edit [`../appcast.xml`](../appcast.xml), add an `<item>` (the shape is in the comment at the top of
that file), and merge it to `main`. Because the feed is served from the repository, **the merge is
the publish** — there is nothing else to deploy.

```xml
<item>
  <title>1.1.0</title>
  <sparkle:version>2</sparkle:version>
  <sparkle:shortVersionString>1.1.0</sparkle:shortVersionString>
  <sparkle:minimumSystemVersion>14.4</sparkle:minimumSystemVersion>
  <pubDate>Mon, 03 Aug 2026 12:00:00 +0000</pubDate>
  <description><![CDATA[<ul><li>What changed.</li></ul>]]></description>
  <enclosure
    url="https://github.com/BasedHardware/omi/releases/download/context-for-claude-v1.1.0/ContextForClaude-1.1.0.zip"
    length="12345678"
    type="application/octet-stream"
    sparkle:edSignature="…" />
</item>
```

The release notes users read are the `<description>` — write them for a person, not a changelog
generator. This is the only text in the update prompt that is not drawn from the bundle, so it is the
only place Omi's name could ever leak into this app's UI. Do not put it there.

### 6. Verify against a real install

Installed copies check every six hours; force one:

```sh
open "/Applications/Context for Claude.app"
# Settings › General › About › Updates › Check Now
```

The sheet must say **Context for Claude**, show this app's icon, and list the notes you wrote. If it
says Omi anything, stop and fix the feed before telling anyone the release is out.

Then confirm the thing that actually breaks: after installing, check that screen capture is still
running. `Settings › Capture`, or:

```sh
log show --last 10m --predicate 'subsystem == "com.omi.context-for-claude"' | grep -i update
```

---

## Rolling back

There is no server-side kill switch — that is the price of a feed served from git. To stop a bad
release reaching anyone who has not taken it yet, revert the `<item>` out of `appcast.xml` and merge.
The CDN holds the old response for about five minutes.

Anyone who already installed it has to be moved forward, not back: Sparkle will not install a lower
`sparkle:version`. Publish a fix with a higher build number.

---

## Feed hosting, and when to change it

The feed is a file in the repository, served by `raw.githubusercontent.com`. It was chosen over a
backend route (`backend/routers/updates.py`, which serves Omi's `v2/desktop/appcast.xml`) for three
reasons: shipping a fix must not require a production backend deploy for a service this app has
nothing else to do with; the signature is reviewable in the pull request that publishes it; and there
is no environment where the running configuration differs from what is in git.

Move it when any of these becomes true:

- **Two channels are needed.** Sparkle supports `<sparkle:channel>` in a static feed, so this alone
  is not yet a reason — but a beta identity with separate enclosures, as Omi has, is.
- **A kill switch is needed.** A five-minute CDN TTL and a revert commit is the current answer.
- **Download volume outgrows raw.githubusercontent.com.** It has no SLA and rate-limits
  unauthenticated traffic.

Whichever replaces it, changing `SUFeedURL` requires a new build, because it is read from the bundle.
The migration is therefore: ship one release through the old feed whose bundle points at the new one,
keep the old feed answering until the tail of installs has moved, and only then retire it.
