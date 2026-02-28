---
name: codemagic
description: Check Codemagic build status, trigger builds, view logs, and manage the CI/CD pipeline. Use when user asks about build status, CI, Codemagic, deploy, or pipeline.
allowed-tools: Bash, Read, WebFetch
---

# Codemagic CI/CD Pipeline

Monitor and manage Codemagic builds for the OMI Desktop app.

## Quick Reference

```bash
# Check latest builds (default — use this)
curl -s -H "x-auth-token: $CODEMAGIC_API_TOKEN" \
  "https://api.codemagic.io/builds?appId=66c95e6ec76853c447b8bcbb&limit=5" | \
  python3 -c "
import json,sys
builds = json.load(sys.stdin).get('builds',[])[:5]
for b in builds:
    s = b.get('status','?')
    tag = b.get('tag') or '-'
    start = (b.get('startedAt') or '-')[:19]
    branch = b.get('branch') or '-'
    print(f'{s:12} tag={tag:35} branch={branch:20} start={start}')
"

# Check a specific build by ID
curl -s -H "x-auth-token: $CODEMAGIC_API_TOKEN" \
  "https://api.codemagic.io/builds/<BUILD_ID>" | python3 -m json.tool

# Cancel a build
curl -s -X POST -H "x-auth-token: $CODEMAGIC_API_TOKEN" \
  "https://api.codemagic.io/builds/<BUILD_ID>/cancel"
```

## Configuration

- **API Token**: `$CODEMAGIC_API_TOKEN` (set in `~/.zshrc`)
- **App ID**: `66c95e6ec76853c447b8bcbb`
- **Codemagic config**: `codemagic.yaml` (in repo root)
- **Release workflow**: `omi-desktop-swift-release`

## How Releases Are Triggered

1. Merging `desktop/**` changes to `main` triggers GitHub Actions (`desktop_auto_release.yml`)
2. GitHub Actions auto-increments the version, pushes a `v*-macos` tag
3. Codemagic picks up the tag and runs `omi-desktop-swift-release` workflow
4. Codemagic builds universal binary (arm64 + x86_64), signs, notarizes, creates DMG + Sparkle ZIP
5. Publishes GitHub release, uploads to GCS, registers in Firestore
6. **Deploys Rust backend to Cloud Run** (step "Deploy Rust backend to Cloud Run" in codemagic.yaml)

**IMPORTANT**: The Rust backend (`Backend-Rust/`) is deployed as part of every desktop release build. If you change backend code, you MUST merge to `main` and wait for the Codemagic build to finish for the backend changes to go live. There is no separate backend deploy — it's bundled with the desktop release.

## Build Statuses

| Status | Meaning |
|--------|---------|
| `queued` | Waiting for a build machine |
| `building` | Currently building |
| `finished` | Completed successfully |
| `failed` | Build failed |
| `canceled` | Manually or automatically canceled |
| `skipped` | Skipped (e.g., no matching workflow) |

## Common Operations

### Check if a release build succeeded

```bash
# Get the latest tagged build
curl -s -H "x-auth-token: $CODEMAGIC_API_TOKEN" \
  "https://api.codemagic.io/builds?appId=66c95e6ec76853c447b8bcbb&limit=10" | \
  python3 -c "
import json,sys
builds = json.load(sys.stdin).get('builds',[])
for b in builds:
    tag = b.get('tag') or ''
    if tag and 'macos' in tag:
        s = b.get('status','?')
        dur = ''
        if b.get('startedAt') and b.get('finishedAt'):
            from datetime import datetime
            start = datetime.fromisoformat(b['startedAt'].replace('Z','+00:00'))
            end = datetime.fromisoformat(b['finishedAt'].replace('Z','+00:00'))
            dur = f'  duration={int((end-start).total_seconds()//60)}m'
        print(f'{s:12} {tag}{dur}')
        break
"
```

### View build logs for a failed build

```bash
BUILD_ID="<build-id>"
curl -s -H "x-auth-token: $CODEMAGIC_API_TOKEN" \
  "https://api.codemagic.io/builds/$BUILD_ID" | \
  python3 -c "
import json,sys
b = json.load(sys.stdin)
# Print build steps and their status
for step in b.get('buildActions', []):
    name = step.get('name','?')
    status = step.get('status','?')
    print(f'  {status:10} {name}')
"
```

### Get build artifacts (download URLs)

```bash
BUILD_ID="<build-id>"
curl -s -H "x-auth-token: $CODEMAGIC_API_TOKEN" \
  "https://api.codemagic.io/builds/$BUILD_ID" | \
  python3 -c "
import json,sys
b = json.load(sys.stdin)
for a in b.get('artefacts', []):
    print(f'{a.get(\"name\",\"?\"):40} {a.get(\"url\",\"-\")}')
"
```

### Trigger a manual build

```bash
curl -s -X POST -H "x-auth-token: $CODEMAGIC_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "appId": "66c95e6ec76853c447b8bcbb",
    "workflowId": "omi-desktop-swift-release",
    "branch": "main",
    "tag": "v0.X.Y+BUILD-macos"
  }' \
  "https://api.codemagic.io/builds"
```

## Promote a Release

After a build finishes, the release starts on the `staging` channel. Promote through channels:

```bash
# staging → beta → stable
./scripts/promote_release.sh <tag>
```

**IMPORTANT**: The Firestore doc ID format is `v{version} {build}` (with a space), NOT `v{version}`. To find the correct doc ID:

```bash
cd /path/to/backend && source venv/bin/activate && python3 -c "
import firebase_admin
from firebase_admin import credentials, firestore
cred = credentials.Certificate('google-credentials.json')
try: firebase_admin.initialize_app(cred)
except ValueError: pass
db = firestore.client()
docs = db.collection('desktop_releases').where('version', '==', '<VERSION>').get()
for doc in docs:
    d = doc.to_dict()
    print(f'doc_id: {doc.id}  channel: {d.get(\"channel\")}  is_live: {d.get(\"is_live\")}')
"
```

If `promote_release.sh` fails with 404, use the full doc ID with build number:
```bash
./scripts/promote_release.sh "v0.11.26 11026"
```

## Sparkle Update Channels

Releases are delivered to users via Sparkle auto-update. The appcast serves one item per channel.

### Channel hierarchy
`staging` → `beta` → `stable` (default)

### How channels work in Sparkle
- Items with `<sparkle:channel>staging</sparkle:channel>` → only visible to staging users
- Items with `<sparkle:channel>beta</sparkle:channel>` → visible to beta and staging users
- Items with **no channel tag** → visible to ALL users (this is the "stable" default)
- **BUG**: Items tagged `<sparkle:channel>stable</sparkle:channel>` are NOT the same as no-tag. They're treated as a named channel called "stable" that nobody subscribes to. The Rust backend currently emits this tag for stable releases — they should have no tag instead.

### User's channel is stored in TWO places
1. **Firestore** `users/{uid}.desktop_update_channel` — server-authoritative, set by admin
2. **UserDefaults** `update_channel` — local on the user's machine, synced from Firestore

The app syncs `desktop_update_channel` from the user profile API (`GET /v1/users/profile`) on:
- App activate
- Settings page load
- Auth state change

### Check a user's channel

```bash
# Check Firestore value
cd /path/to/backend && source venv/bin/activate && python3 -c "
from firebase_admin import auth, firestore
# (init firebase first)
user = auth.get_user_by_email('<email>')
doc = firestore.client().collection('users').document(user.uid).get()
d = doc.to_dict()
print(f'desktop_update_channel: {d.get(\"desktop_update_channel\")}')
print(f'update_channel: {d.get(\"update_channel\")}')
"
```

### Change a user's channel

```bash
# Set the authoritative field (desktop_update_channel)
db.collection('users').document(uid).update({'desktop_update_channel': 'staging'})
```

**NOTE**: There is also an `update_channel` field on user docs used by the legacy assistant settings sync path. If changing channels, update BOTH fields to avoid confusion:
```python
db.collection('users').document(uid).update({
    'desktop_update_channel': 'staging',
    'update_channel': 'staging'
})
```

### Check what the appcast is serving

```bash
curl -s https://desktop-backend-hhibjajaja-uc.a.run.app/appcast.xml | \
  python3 -c "
import sys, xml.etree.ElementTree as ET
ns = {'sparkle': 'http://www.andymatuschak.org/xml-namespaces/sparkle'}
root = ET.parse(sys.stdin).getroot()
for item in root.findall('.//item'):
    ver = item.find('sparkle:shortVersionString', ns)
    ch = item.find('sparkle:channel', ns)
    print(f'v{ver.text if ver is not None else \"?\"} channel={ch.text if ch is not None else \"(default/stable)\"}')
"
```

## Troubleshooting

### Build stuck in `queued`
- Another build may be using the Mac mini. Check active builds.
- Codemagic has limited Mac mini M2 concurrency.

### Build failed
- Check build logs (see "View build logs" above)
- Common causes: code signing issues, Swift build errors, notarization failures
- Fix the issue and either push a new commit or trigger a manual build

### Tag not picked up
- Verify the tag format: `v{major}.{minor}.{patch}+{build}-macos`
- Check GitHub Actions ran: `gh run list --workflow=desktop_auto_release.yml --limit=3`
- Check Codemagic webhook: the tag push event must reach Codemagic

### Appcast not serving new version
```bash
curl -s https://desktop-backend-hhibjajaja-uc.a.run.app/appcast.xml | grep shortVersionString
```
If the version doesn't match, check Firestore `desktop_releases` collection.

### User not seeing update despite correct channel
1. Check the appcast serves the version for that channel (see above)
2. Check the user's local channel: `defaults read com.omi.computer-macos update_channel`
3. Check Firestore has `desktop_update_channel` set correctly
4. Check the Rust backend returns `desktop_update_channel` in `GET /v1/users/profile`
5. Check app logs: `grep "Sparkle:" /private/tmp/omi.log | tail -10`
6. If the user has both "Omi Dev" and "Omi Beta" running, they may be checking updates in the wrong app
