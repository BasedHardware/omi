#!/bin/bash
set -e

# =============================================================================
# OMI Remote Release Script
# Syncs omi-desktop to omi/desktop/ in the monorepo, then triggers Codemagic CI.
#
# Usage: ./release-remote.sh [version]
# Example: ./release-remote.sh 11.6
# If no version specified, auto-increments patch version from latest tag.
#
# What this does:
#   1. Forward-syncs omi-desktop -> omi/desktop/ (creates PR, auto-merges)
#   2. Computes version + build number
#   3. Pushes a v{version}+{build}-macos tag to BasedHardware/omi
#   4. Codemagic picks up the tag and runs the full release pipeline
#      (build, sign, notarize, DMG, Sparkle, GitHub release, Firestore)
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OMI_MONOREPO="/Users/matthewdi/omi"
GITHUB_REPO="BasedHardware/omi"

echo "=============================================="
echo "  OMI Remote Release (Codemagic CI)"
echo "=============================================="
echo ""

# -----------------------------------------------------------------------------
# Pre-flight checks
# -----------------------------------------------------------------------------
echo "[1/5] Pre-flight checks..."

# Check we're in omi-desktop
if [ ! -f "$SCRIPT_DIR/Desktop/Package.swift" ]; then
    echo "  Error: Must be run from omi-desktop repo root"
    exit 1
fi

# Check monorepo exists
if [ ! -d "$OMI_MONOREPO/.git" ]; then
    echo "  Error: Monorepo not found at $OMI_MONOREPO"
    exit 1
fi

# Check gh CLI
if ! command -v gh &>/dev/null; then
    echo "  Error: GitHub CLI (gh) not found. Install with: brew install gh"
    exit 1
fi

# Check both repos are clean
if [ -n "$(cd "$SCRIPT_DIR" && git status --porcelain)" ]; then
    echo "  Error: omi-desktop has uncommitted changes. Commit or stash first."
    exit 1
fi

if [ -n "$(cd "$OMI_MONOREPO" && git status --porcelain)" ]; then
    echo "  Error: omi monorepo has uncommitted changes. Commit or stash first."
    exit 1
fi

echo "  ✓ All checks passed"

# -----------------------------------------------------------------------------
# Version handling
# -----------------------------------------------------------------------------
echo ""
echo "[2/5] Determining version..."

if [ -n "$1" ]; then
    VERSION="$1"
    echo "  Using specified version: $VERSION"
else
    # Get latest version from omi-desktop tags
    LATEST=$(cd "$SCRIPT_DIR" && git tag -l 'v*' 2>/dev/null | grep -E '^v[0-9]+\.[0-9]+' | sort -V | tail -1 | sed 's/^v//' || echo "")

    if [ -z "$LATEST" ]; then
        LATEST="0.0.0"
        echo "  No previous version found, starting at 0.0.1"
    else
        echo "  Latest version: $LATEST"
    fi

    # Parse and increment patch version
    MAJOR=$(echo "$LATEST" | cut -d. -f1)
    MINOR=$(echo "$LATEST" | cut -d. -f2)
    PATCH=$(echo "$LATEST" | cut -d. -f3 | cut -d+ -f1)
    PATCH=$((PATCH + 1))
    VERSION="$MAJOR.$MINOR.$PATCH"
    echo "  Auto-incremented to: $VERSION"
fi

# Build number: converts "11.6" → 11006, "1.2.3" → 1002003
BUILD_NUMBER=$(echo "$VERSION" | tr '.' '\n' | awk '{s=s*1000+$1}END{print s}')
RELEASE_TAG="v${VERSION}+${BUILD_NUMBER}-macos"

echo "  Version: $VERSION"
echo "  Build: $BUILD_NUMBER"
echo "  Tag: $RELEASE_TAG"

# Check tag doesn't already exist in monorepo
if cd "$OMI_MONOREPO" && git tag -l "$RELEASE_TAG" | grep -q .; then
    echo "  Error: Tag $RELEASE_TAG already exists in monorepo"
    echo "  Delete it first: cd $OMI_MONOREPO && git tag -d $RELEASE_TAG && git push origin :refs/tags/$RELEASE_TAG"
    exit 1
fi

# -----------------------------------------------------------------------------
# Forward sync: omi-desktop -> omi/desktop/
# -----------------------------------------------------------------------------
echo ""
echo "[3/5] Syncing omi-desktop -> omi/desktop/..."

# Remember monorepo's current branch
ORIGINAL_BRANCH=$(cd "$OMI_MONOREPO" && git rev-parse --abbrev-ref HEAD)

# Fetch latest monorepo
cd "$OMI_MONOREPO"
git fetch origin

# Create sync branch from origin/main
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OMI_DESKTOP_SHA=$(cd "$SCRIPT_DIR" && git rev-parse HEAD)
SHORT_SHA="${OMI_DESKTOP_SHA:0:8}"
SYNC_BRANCH="sync/desktop-${TIMESTAMP}"

git checkout -b "$SYNC_BRANCH" origin/main

# rsync omi-desktop into omi/desktop/
DESKTOP_DIR="$OMI_MONOREPO/desktop"
mkdir -p "$DESKTOP_DIR"

rsync -a --delete \
    --exclude=.git \
    --exclude=monorepo \
    "$SCRIPT_DIR/" \
    "$DESKTOP_DIR/"

# Check for changes
if [ -z "$(git status --porcelain -- desktop/)" ]; then
    echo "  No changes to sync (omi/desktop/ is already up to date)"
    git checkout "$ORIGINAL_BRANCH"
    git branch -D "$SYNC_BRANCH" 2>/dev/null
else
    # Commit, push, create PR, merge
    git add desktop/
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git commit -m "Sync desktop/ from omi-desktop ($SHORT_SHA)"

    echo "  Pushing sync branch..."
    git push -u origin "$SYNC_BRANCH"

    echo "  Creating PR..."
    PR_URL=$(gh pr create \
        --title "Sync desktop/ from omi-desktop ($SHORT_SHA)" \
        --body "Automated sync from omi-desktop at $SHORT_SHA for release $VERSION." \
        --base main \
        --head "$SYNC_BRANCH")
    echo "  PR: $PR_URL"

    echo "  Merging PR..."
    gh pr merge "$SYNC_BRANCH" --merge --admin --delete-branch

    # Wait for merge to complete
    echo "  Waiting for merge..."
    for i in $(seq 1 6); do
        sleep 5
        PR_STATE=$(gh pr view "$SYNC_BRANCH" --json state --jq '.state' 2>/dev/null || echo "MERGED")
        if [ "$PR_STATE" = "MERGED" ]; then
            break
        fi
        echo "    Still waiting... (attempt $i/6)"
    done
fi

# Return to original branch and fetch
git checkout "$ORIGINAL_BRANCH" 2>/dev/null || git checkout main
git fetch origin main

echo "  ✓ Sync complete"

# -----------------------------------------------------------------------------
# Tag omi-desktop for version tracking
# -----------------------------------------------------------------------------
echo ""
echo "[4/5] Tagging version..."

cd "$SCRIPT_DIR"
git tag "v$VERSION" 2>/dev/null && echo "  ✓ Tagged omi-desktop: v$VERSION" || echo "  Tag v$VERSION already exists locally"
git push origin "v$VERSION" 2>/dev/null && echo "  ✓ Pushed tag to omi-desktop" || echo "  Tag already on remote"

# -----------------------------------------------------------------------------
# Push release tag to monorepo (triggers Codemagic)
# -----------------------------------------------------------------------------
echo ""
echo "[5/5] Triggering Codemagic release..."

cd "$OMI_MONOREPO"
git fetch origin main
git tag "$RELEASE_TAG" origin/main
git push origin "$RELEASE_TAG"

echo "  ✓ Pushed tag: $RELEASE_TAG"
echo ""
echo "=============================================="
echo "  Release $VERSION triggered on Codemagic!"
echo "=============================================="
echo ""
echo "  Tag: $RELEASE_TAG"
echo "  Codemagic will now build, sign, notarize, and publish."
echo ""
echo "  Monitor build:"
echo "    https://codemagic.io/apps (look for omi-desktop-swift-release)"
echo ""
echo "  When complete, the release will appear at:"
echo "    https://github.com/$GITHUB_REPO/releases"
echo ""
