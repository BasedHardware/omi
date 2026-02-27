---
name: rollback
description: Roll back a broken OMI Desktop release. Sets is_live=False in Firestore, deletes GitHub release and git tags, verifies appcast reverted.
allowed-tools: Bash, Read, Grep
---

# OMI Desktop Release Rollback Skill

Roll back a broken release and restore the previous live version.

## When to Use

- App crashes on launch after a release
- Notarization or entitlement issues discovered post-release
- Any critical bug that makes the app unusable
- User reports "app can't be opened" or "app is damaged"

## CRITICAL: Speed Matters

Users who auto-update to a broken release are **STUCK** — the app can't launch, so Sparkle can't check for the next update. They must manually re-download the DMG. Roll back as fast as possible to minimize the window of exposure.

## Rollback Procedure

### Step 1: Kill the live release in Firestore

This is the most important step — it stops the appcast from serving the broken version.

```bash
# Connect to Firebase and set is_live=False
cd ../omi/backend && source venv/bin/activate && python3 -c "
import firebase_admin
from firebase_admin import credentials, firestore
cred = credentials.Certificate('google-credentials.json')
try: firebase_admin.initialize_app(cred)
except ValueError: pass
db = firestore.client()

# Find the broken release document
releases = db.collection('desktop_releases').stream()
for doc in releases:
    data = doc.to_dict()
    print(f\"{doc.id}: v{data.get('version')} is_live={data.get('is_live')}\")

# Set the broken version to not live (replace DOC_ID)
# db.collection('desktop_releases').document('DOC_ID').update({'is_live': False})
"
```

The document ID format is `v{VERSION}+{BUILD_NUMBER}` (e.g., `v0.9.0+9000`).

### Step 2: Verify appcast reverted

```bash
curl -s https://desktop-backend-hhibjajaja-uc.a.run.app/appcast.xml | head -20
```

Should show the previous version, not the broken one.

### Step 3: Delete the GitHub release

```bash
# List releases to find the exact tag
gh release list --repo BasedHardware/omi --limit 5

# Delete the broken release
gh release delete "v{VERSION}+{BUILD_NUMBER}-macos" --repo BasedHardware/omi --yes
```

### Step 4: Delete the git tag

```bash
git tag -d v{VERSION}
```

### Step 5: Check user impact

Check if any users downloaded the broken version:

```bash
# GitHub download count
gh release view "v{VERSION}+{BUILD_NUMBER}-macos" --repo BasedHardware/omi --json assets --jq '.assets[] | "\(.name): \(.downloadCount) downloads"'
```

If users were affected, they need to manually download the DMG from:
- `https://desktop-backend-hhibjajaja-uc.a.run.app/download` (redirects to latest GCS DMG)
- Or the GitHub releases page

## Key Details

- **Firestore collection**: `desktop_releases`
- **Document ID format**: `v{VERSION}+{BUILD_NUMBER}` (e.g., `v0.9.0+9000`)
- **Appcast URL**: `https://desktop-backend-hhibjajaja-uc.a.run.app/appcast.xml`
- **Backend base URL**: `https://desktop-backend-hhibjajaja-uc.a.run.app`
- **GitHub repo**: `BasedHardware/omi`
- **Release tag format**: `v{VERSION}+{BUILD_NUMBER}-macos`

## After Rollback

1. Fix the root cause
2. Re-release with the same version number (release.sh handles overwrites)
3. Verify the new release works using `verify-release.sh`
