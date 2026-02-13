---
name: release
description: Release a new version of OMI Desktop. Analyzes changes since last release, generates changelog, and runs the full release pipeline.
allowed-tools: Bash, Read, Edit, Grep
---

# OMI Desktop Release Skill

Release a new version of the OMI Desktop app with auto-generated changelog.

## CRITICAL RULES

**NEVER run release steps manually.** Always use `./release.sh` for the entire pipeline.

If `release.sh` fails mid-way:
1. **DO NOT** manually run the remaining steps (staple, DMG, upload, etc.)
2. **DO NOT** edit `release.sh` during a release to fix the issue
3. **INVESTIGATE** why it failed
4. **PROPOSE** changes to `release.sh` for the user to approve
5. **RE-RUN** `./release.sh [version]` from the beginning after fixes

**Why?** Manual steps lead to errors (wrong entitlements, wrong endpoints, missing signatures). The script is designed to run as a complete unit.

**Exception:** If the failure is in the project code itself (not release.sh), fix the project code, then re-run release.sh.

## Release Process

### Step 1: Get commits since last release

```bash
LAST_TAG=$(git tag -l 'v*' | sort -V | tail -1)
echo "Last release: $LAST_TAG"
git log ${LAST_TAG}..HEAD --oneline --no-merges
```

### Step 2: Analyze changes and create changelog

Review the commits and create a concise changelog. Group changes by category:
- **New Features**: New functionality added
- **Improvements**: Enhancements to existing features
- **Bug Fixes**: Issues that were resolved

Keep it user-friendly - focus on what users will notice, not internal changes.

### Step 3: Update CHANGELOG.json

Add a new entry at the **top** of the `releases` array in `CHANGELOG.json`:

```json
{
  "releases": [
    {
      "version": "X.Y.Z",
      "date": "YYYY-MM-DD",
      "changes": [
        "Your changelog item 1",
        "Your changelog item 2"
      ]
    },
    // ... previous releases remain below
  ]
}
```

The release script reads the first entry and uses it for both GitHub release notes and Sparkle appcast.

### Step 4: Pre-flight checks

Before running release.sh, verify prerequisites are ready:

```bash
# Docker must be running (needed for Cloud Run backend deploy)
if ! docker info &>/dev/null; then
  open -a Docker
  echo "Waiting for Docker to start..."
  for i in {1..30}; do docker info &>/dev/null && break; sleep 2; done
fi
```

### Step 5: Run the release

```bash
./release.sh [version]
```

If no version specified, it auto-increments the patch version.

### Step 6: Verify the release

After release completes successfully:
1. Download the DMG from GitHub
2. Install and launch to verify it works
3. Check the appcast shows correct changelog:
   ```bash
   curl -s https://desktop-backend-hhibjajaja-uc.a.run.app/appcast.xml | head -30
   ```

## What release.sh Does (12 Steps)

1. Deploy Rust backend to Cloud Run
2. Build the Swift desktop app
3. Sign with Developer ID (including ffmpeg)
4. Notarize with Apple
5. Staple notarization ticket
6. Create DMG installer
7. Sign DMG
8. Notarize DMG
9. Staple DMG
10. Create Sparkle ZIP for auto-updates
11. Publish to GitHub and register in Firestore
12. Trigger installation test

## Handling Failures

### Stapling fails (CDN propagation delay)
This is common - Apple's CDN can be slow. **DO NOT** manually retry staple.
- Wait a few minutes
- Re-run `./release.sh [same-version]` from the beginning
- The rebuild is fast (cached), notarization may be quick too

### Notarization fails (unsigned binary)
- Check the notarization log for which binary is unsigned
- **Propose** adding signing for that binary in release.sh
- After user approves the change, re-run release.sh

### GitHub/GCloud auth expires
- Run `gh auth login` or `gcloud auth login`
- Re-run release.sh

### Docker not running
- release.sh step 1 deploys the Rust backend to Cloud Run via Docker
- Start Docker Desktop: `open -a Docker`
- Wait for it to be ready: `docker info`
- Re-run release.sh

### Build fails
- This is a project code issue, not release.sh
- Fix the code, then re-run release.sh

## Environment Requirements

The release requires these in `.env`:
- `NOTARIZE_PASSWORD` - Apple app-specific password
- `SPARKLE_PRIVATE_KEY` - EdDSA key for signing updates
- `RELEASE_SECRET` - Backend API secret
- `APPLE_PRIVATE_KEY` - For Apple Sign-In config
- Various Firebase/Google/Apple OAuth keys

## Key Files

- **Release script**: `/Users/matthewdi/omi-desktop/release.sh`
- **Changelog**: `/Users/matthewdi/omi-desktop/CHANGELOG.json` - Version history with all release notes
