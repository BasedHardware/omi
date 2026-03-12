---
name: release
description: Release a new version of OMI Desktop. Analyzes changes since last release, generates changelog, and runs the full release pipeline.
allowed-tools: Bash, Read, Edit, Grep
---

# OMI Desktop Release Skill

Release a new version of the OMI Desktop app with auto-generated changelog.

## CRITICAL RULES

**NEVER run release.sh more than once.** Each run generates a unique EdDSA signature for the Sparkle ZIP. If you run it twice, the second run creates a new ZIP with a different signature but GitHub keeps the old ZIP — causing "improperly signed" errors for all users.

**NEVER run release steps manually.** Always use `./release.sh` for the entire pipeline.

If `release.sh` fails mid-way:
1. **DO NOT** manually run the remaining steps (staple, DMG, upload, etc.)
2. **DO NOT** edit `release.sh` during a release to fix the issue
3. **INVESTIGATE** why it failed
4. **PROPOSE** changes to `release.sh` for the user to approve
5. **RE-RUN** `./release.sh [version]` from the beginning after fixes

**Why?** Manual steps lead to errors (wrong entitlements, wrong endpoints, missing signatures). The script is designed to run as a complete unit.

**Exception:** If the failure is in the project code itself (not release.sh), fix the project code, then re-run release.sh.

## Monitoring a Release

release.sh logs all output to `/private/tmp/omi-release.log`. Use this to check progress:

```bash
# Check current step
tail -20 /private/tmp/omi-release.log

# Watch live progress
tail -f /private/tmp/omi-release.log

# Check if release.sh is still running
ps aux | grep 'release.sh' | grep -v grep

# Check if release was published to GitHub
gh release list --repo BasedHardware/omi --limit 3

# Check if appcast is serving the new version
curl -s https://desktop-backend-hhibjajaja-uc.a.run.app/appcast.xml | grep shortVersionString
```

**If the Bash tool sends release.sh to background** (long-running command), do NOT re-run it. Instead:
1. Check `/private/tmp/omi-release.log` to see progress
2. Check `ps aux | grep release.sh` to confirm it's still running
3. Wait for completion — the full pipeline takes ~10-15 minutes

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

### Step 3: Verify changelog entries

Changelog entries are auto-accumulated by agents in the `unreleased` array of `CHANGELOG.json`. Before releasing, verify entries exist and add any missing ones:

```bash
# Check current unreleased entries
python3 -c "import json; data=json.load(open('CHANGELOG.json')); print('\n'.join(data.get('unreleased', [])) or '(empty — add entries before releasing)')"
```

If `unreleased` is empty, review the commits from Step 1 and add entries:

```python
python3 -c "
import json
with open('CHANGELOG.json', 'r') as f:
    data = json.load(f)
data.setdefault('unreleased', []).extend([
    'Your changelog item 1',
    'Your changelog item 2'
])
with open('CHANGELOG.json', 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
"
```

The GitHub Actions workflow (`desktop_auto_release.yml`) consolidates these into a versioned release entry when the tag is created. The release script reads `releases[0]` for both GitHub release notes and Sparkle appcast.

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

**MANDATORY** — Run verification immediately after release completes:

```bash
./verify-release.sh [version]
```

This script automatically:
1. Checks the appcast serves the correct version
2. Downloads the Sparkle ZIP (what auto-update users get)
3. Verifies Gatekeeper acceptance and code signature
4. Checks entitlements don't require a provisioning profile
5. Launches the app and confirms it starts
6. Checks the DMG download endpoint

If verification fails, **immediately roll back** using the rollback skill (`.claude/skills/rollback/SKILL.md`).

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

## Rollback

If verification fails or a broken release is discovered post-release, use the **rollback skill** (`.claude/skills/rollback/SKILL.md`). The key steps are:

1. Set `is_live=False` in Firestore `desktop_releases` collection (stops appcast from serving broken version)
2. Delete the GitHub release
3. Delete the local git tag
4. Fix the issue, then re-run `./release.sh [same-version]`

**Why speed matters:** Users who auto-updated to a broken build are stuck — the app can't launch, so Sparkle can't check for fixes. They must manually re-download the DMG.

## Key Files

- **Release script**: `/Users/matthewdi/omi-desktop/release.sh`
- **Verification script**: `/Users/matthewdi/omi-desktop/verify-release.sh` - Post-release download + launch test
- **Rollback skill**: `/Users/matthewdi/omi-desktop/.claude/skills/rollback/SKILL.md`
- **Changelog**: `/Users/matthewdi/omi-desktop/CHANGELOG.json` - Version history with all release notes
- **Entitlements**: `/Users/matthewdi/omi-desktop/Desktop/Omi-Release.entitlements` - Must NOT have provisioning-profile-dependent keys
