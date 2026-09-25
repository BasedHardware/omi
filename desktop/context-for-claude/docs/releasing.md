# Releasing Context for Claude

Context for Claude has its own product identity, Developer ID bundle signature, Sparkle EdDSA key
pair, artifact names, and release tag namespace. The release path is separate from the Omi Desktop
release workflow.

**GitHub is the entire update backend.** No platform endpoint serves this app's feed, nothing has to
be deployed for an update to reach users, and the app talks only to `github.com`. The updater is
self-contained in the bundle: `SUFeedURL` points at a Sparkle appcast that lives as an asset on a
GitHub release, and `scripts/release-context.sh` is what puts it there.

The entry point is `scripts/release-context.sh`. It supplies this product's names and secret variable
names to `scripts/release-micro-app.sh`, which owns tag validation, version injection, Sparkle ZIP
signing, appcast generation, and GitHub publication. `scripts/package-dmg.sh` remains responsible for
assembling and signing the app, nested Sparkle code, DMG, and ZIP enclosure.
`scripts/generate-appcast.py` owns the feed XML.

## Where the feed lives

```text
https://github.com/BasedHardware/omi/releases/download/context-for-claude-appcast/appcast.xml
```

That URL must stay character-for-character equal to `SUFeedURL` in `Resources/Info.plist`. The
release helper reads the holder tag (`context-for-claude-appcast`) and the asset name (`appcast.xml`)
straight out of it, so there is one copy of the fact, and it refuses to publish when the built
bundle's `SUFeedURL` is not the feed the run is about to write.

Two properties of this arrangement are load-bearing:

- **The feed is not a tracked file.** An enclosure's EdDSA signature only exists once the ZIP has
  been packaged, so the feed can only be written after the build. A tracked `appcast.xml` would
  therefore mean a commit pushed on every release — which this repository forbids on `main` — and
  routing each release through its own PR would turn a one-command release into a two-step human
  process. So the feed is an asset on one fixed, mutable release instead, uploaded with `--clobber`.
- **The holder release is a prerelease.** Without `--prerelease` it claims the repository-wide
  "Latest release" pointer, and the repository front page starts offering an XML file as Omi's newest
  download. The helper creates it that way; never flip it.

The versioned releases (`context-for-claude-v<version>`) hold the artifacts and are immutable. The
holder release holds only the feed and is rewritten in place. Nothing else is ever uploaded to it.

`releases/latest/download/...` is never used, anywhere. It resolves to the newest release of the
whole repository, which ships Omi Desktop tags almost daily, so it would 404 or hand out another
product's bundle. Both the helper and the generator refuse that spelling.

### The one transient failure mode

`gh release upload --clobber` deletes the old asset and uploads the new one, so there is a sub-second
window where the feed URL 404s. A Sparkle check that lands in that window reports a feed error to the
user and retries on its next scheduled check; nothing is corrupted and no client installs anything
wrong. It is the accepted cost of a mutable asset at a stable URL.

## One-time setup

### Sparkle update key pair

Use the Sparkle tools matching the pinned dependency (`2.9.4` in `Package.resolved`); they are
already unpacked at `.build/artifacts/sparkle/Sparkle/bin/` after `swift package resolve`:

```sh
./.build/artifacts/sparkle/Sparkle/bin/generate_keys
```

`generate_keys` puts the private half in the releasing maintainer's **login keychain** and prints the
public half. That is where it should stay: `sign_update` finds it there with no arguments, so a local
release never moves the key, never puts it in an environment variable, and never writes it to disk.

- `CONTEXT_SPARKLE_PUBLIC_KEY`: the 44-character base64 public key. Not a secret, but it must be
  supplied for a release build — the source `Resources/Info.plist` keeps its placeholder on purpose,
  and `build.sh` injects the real key into the copied bundle plist.
- `CONTEXT_SPARKLE_PRIVATE_KEY`: **only** for a CI runner with no keychain. When it is set, the
  helper pipes it into `sign_update --ed-key-file -`; when it is not, `sign_update` reads the
  keychain. Export it with `generate_keys -x /secure/offline/context-for-claude-eddsa.key` and keep
  an offline backup.

The private value is never printed, written to the repository, or included in a release artifact.
Rotating this key makes every existing installation unable to verify future updates, so a rotation
requires a manual reinstall and a coordinated updater change.

Release mode fails closed if the public key is absent or still the placeholder. Ordinary local
development builds continue to work without release secrets and remain unable to auto-update.

### GitHub publication

Create `CONTEXT_GITHUB_TOKEN` as a fine-grained token scoped to the release repository with
repository Contents write permission (including releases) and Metadata read permission. The helper
uses it through `GH_TOKEN`, never as a command-line argument. `gh` must be on `PATH`.

### Apple signing and notarization

A distributable release needs a Developer ID Application certificate in the keychain and notarization
credentials:

- `CFC_SIGN_IDENTITY` — `Developer ID Application: NAME (TEAMID)`.
- `CFC_NOTARY_PROFILE` — a `notarytool` keychain profile, or the three `CFC_ASC_*` App Store Connect
  values (`CFC_ASC_PRIVATE_KEY`, `CFC_ASC_KEY_ID`, `CFC_ASC_ISSUER_ID`).

```sh
xcrun notarytool store-credentials "context-notary" \
  --apple-id you@example.com --team-id TEAMID --password <app-specific-password>
```

No provisioning profile is needed for this Developer ID distribution bundle. A self-signed identity
(`Omi Local Dev Signing`) can never produce a release; see *Rehearsals* below for what it can do.

### Running the release from CI

The scripts assume nothing about the CI provider: a plain macOS runner with Xcode, `git`, `gh`, and
`python3` can run them. What the job must provide is exactly:

| Variable | Purpose |
|---|---|
| `CONTEXT_SPARKLE_PUBLIC_KEY` | injected into the built bundle; release fails closed without it |
| `CONTEXT_SPARKLE_PRIVATE_KEY` | ZIP signing, because a CI runner has no login keychain |
| `CONTEXT_GITHUB_TOKEN` | creating the versioned release and updating the feed asset |
| `CFC_SIGN_IDENTITY` | set after importing the Developer ID `.p12` into the runner keychain |
| `CFC_ASC_PRIVATE_KEY`, `CFC_ASC_KEY_ID`, `CFC_ASC_ISSUER_ID` | `notarytool` credentials |
| `CONTEXT_RELEASE_REPO` | optional; defaults to `BasedHardware/omi` |

The job is: check out the tag, `xcrun swift package resolve`, import the certificate, then
`./scripts/release-context.sh --tag "$TAG" --publish` from `desktop/context-for-claude`.

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
./scripts/release-context.sh --tag context-for-claude-v1.1.0 --dry-run
```

This validates the tag, artifact names, feed URL, holder release, enclosure URL, package entry point,
and any supplied key material without building, notarizing, signing, publishing, or changing files.

A maintainer then creates and pushes the tag, and publishes:

```sh
git tag context-for-claude-v1.1.0
git push origin context-for-claude-v1.1.0
CONTEXT_SPARKLE_PUBLIC_KEY='<44-char public key>' \
CONTEXT_GITHUB_TOKEN='<token>' \
CFC_SIGN_IDENTITY='Developer ID Application: NAME (TEAMID)' \
CFC_NOTARY_PROFILE='context-notary' \
  ./scripts/release-context.sh --tag context-for-claude-v1.1.0 --publish
```

`--publish` performs this sequence, and refuses at the first step that cannot be vouched for:

1. Checks the token, that no release already exists at the tag, and that `HEAD` is the exact commit
   the tag names — before spending forty minutes on a build.
2. Builds ContextApp plus `context-for-claude-mcp`, injects the public key and tag-derived versions
   into the built `Info.plist`, and signs the app, MCP executable, Sparkle framework, and every
   nested Sparkle XPC/helper component inside-out with the Developer ID identity.
3. Notarizes and staples the app, creates the DMG, then signs, notarizes, and staples the DMG.
4. Creates the Sparkle ZIP from the stapled app and checks that the bundle's `SUFeedURL` is the feed
   this run is about to write.
5. Signs that ZIP with the EdDSA key, then **verifies the signature against the ZIP's bytes** —
   signing a file and publishing a feed that validates against it are two different claims.
6. Downloads the currently published `appcast.xml` from the holder release and appends the new item
   to it. A holder release or asset that does not exist yet is the first release and starts a new
   feed; an asset that exists but cannot be downloaded or parsed stops the release, because dropping
   the update history of every older client is never the safer branch.
7. Creates the GitHub release at the tag with the DMG and ZIP attached.
8. Creates the holder release with `--prerelease` (first release only) or uploads the regenerated
   `appcast.xml` to it with `--clobber`.

Artifacts go up before the feed does: an item is only publishable once the enclosure it names can
actually be downloaded.

Re-running a release is safe. The generator replaces the item with the same numeric build in place
and keeps its original `pubDate`, so a retried run does not reorder the feed or re-date an
already-published build. Regenerate rather than hand-editing the published asset — hand-editing is
how update history gets truncated.

## Rehearsals

There is no Developer ID certificate on every machine, and the release path still has to be
exercisable end to end. `--rehearsal` does that.

```sh
# local: build, package, sign the enclosure, generate a feed. No network, nothing published.
CONTEXT_SPARKLE_PUBLIC_KEY='<44-char public key>' \
  ./scripts/release-context.sh --tag context-for-claude-v1.1.0 --rehearsal

# same, but exercising the append path against a copy of the published feed
  ... --rehearsal --existing-appcast /path/to/published-appcast.xml

# publish the rehearsal to a fork, exercising gh release create and the feed upload
CONTEXT_RELEASE_REPO='you/omi' CONTEXT_GITHUB_TOKEN='<token>' \
CONTEXT_APPCAST_FEED_URL='https://github.com/you/omi/releases/download/context-for-claude-appcast/appcast.xml' \
  ./scripts/release-context.sh --tag context-for-claude-v1.1.0 --rehearsal --publish
```

A rehearsal **can**: build and package the real app, produce a real DMG, produce a genuinely signed
Sparkle ZIP, verify that signature, generate a valid appcast whose length/signature/version match the
artifact on disk, and exercise every GitHub step against a fork.

A rehearsal **cannot**: produce anything installable by another person, and cannot be mistaken for
something that is. Its artifacts are named `ContextForClaude-<version>-rehearsal.dmg` / `.zip`, its
feed is written to `dist/rehearsal/appcast.xml` with a `REHEARSAL FEED — NOT DISTRIBUTABLE` banner in
the file, a rehearsal GitHub release is marked as a prerelease and titled `(REHEARSAL — not
distributable)`, and `--rehearsal --publish` refuses to target `BasedHardware/omi` at all. It is not
notarized, so Gatekeeper refuses it on any machine but the one that built it, and Sparkle clients of
a real installation cannot install it.

Conversely, `--publish` without `--rehearsal` refuses to run at all without a Developer ID identity,
and `package-dmg.sh --release` fails the run if Gatekeeper rejects the result. The two cannot be
confused for one another.

`CONTEXT_RELEASE_REPO` retargets the artifacts and the feed together, so a fork rehearsal needs no
script edit. Note that a fork rehearsal's feed cannot be consumed by a production bundle: the app
reads the URL baked into `SUFeedURL`, which is the production one. Point `CONTEXT_APPCAST_FEED_URL`
at the fork to keep the helper's feed/artifact repository check satisfied.

## Verification before announcing a release

Check the exact shipped identity and Team ID against the preceding release:

```sh
codesign -dv --verbose=2 "build/Context for Claude.app" 2>&1 \
  | grep -E '^(Identifier|Authority|TeamIdentifier|Runtime Version)='
xcrun stapler validate "dist/ContextForClaude-1.1.0.dmg"
codesign --verify --deep --strict "build/Context for Claude.app"
unzip -t "dist/ContextForClaude-1.1.0.zip"
```

`Identifier` must be `com.omi.context-for-claude`. The leaf authority and Team ID must match the
previous public release, and `TeamIdentifier` must not be `not set`. **A changed Team ID silently
revokes Screen Recording, Microphone, and System Audio consent after Sparkle replaces the bundle** —
macOS keys those grants to the signing identity, so the app comes back from an update with no
permissions and no prompt explaining why. Stop the release if it differs.

Then check the feed the way a client sees it:

```sh
curl -fsSL "https://github.com/BasedHardware/omi/releases/download/context-for-claude-appcast/appcast.xml" \
  | xmllint --format -
curl -fsSLI "$(curl -fsSL "https://github.com/BasedHardware/omi/releases/download/context-for-claude-appcast/appcast.xml" \
  | xmllint --xpath 'string(/rss/channel/item[1]/enclosure/@url)' -)" | head -1
```

The newest item's `sparkle:version` must be the tag's numeric build, its `length` must equal the
published ZIP's byte size, its enclosure URL must resolve, and every previously published item must
still be present. The GitHub release must contain exactly the Context DMG and Context Sparkle ZIP,
with no Omi Desktop asset.

## First-install upgrade constraint

Sparkle can update only a Context installation that already has the same product identity and signing
continuity:

- The first public installation must be the notarized Developer ID Context DMG or an equivalent
  manually installed bundle signed by the same Apple Team.
- A local `Omi Local Dev Signing` build, a rehearsal build, a placeholder-key build, or a build signed
  by another Team cannot receive the public release through Sparkle. Install the first public release
  manually, then future releases can update it.
- Never point Context at an Omi feed or reuse Omi's EdDSA key. The bundle ID, feed URL, certificate
  Team ID, and EdDSA key are separate trust boundaries.

## Rollback and recovery

The feed is the withdrawal point. If a release is bad before users install it, regenerate the feed
without the bad item and upload it to the holder release with `--clobber`, then delete or unpublish
the versioned release. Clients stop being offered it as soon as their next check reads the new feed.
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
