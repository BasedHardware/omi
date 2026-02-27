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
    wf = b.get('workflowId') or '-'
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
