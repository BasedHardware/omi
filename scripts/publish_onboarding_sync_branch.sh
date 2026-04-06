#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <bundle-dir> [branch]" >&2
  exit 1
fi

BUNDLE_DIR=$1
TARGET_BRANCH=${2:-figma-onboarding-sync}

if [[ ! -d "$BUNDLE_DIR" ]]; then
  echo "bundle directory not found: $BUNDLE_DIR" >&2
  exit 1
fi

if [[ -z "${GITHUB_REPOSITORY:-}" ]]; then
  echo "GITHUB_REPOSITORY must be set" >&2
  exit 1
fi

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "GITHUB_TOKEN must be set" >&2
  exit 1
fi

TMP_DIR=$(mktemp -d)
PUBLISH_DIR="$TMP_DIR/publish"
mkdir -p "$PUBLISH_DIR/onboarding/latest"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

cp -R "$BUNDLE_DIR"/. "$PUBLISH_DIR/onboarding/latest/"
touch "$PUBLISH_DIR/.nojekyll"

cd "$PUBLISH_DIR"

git init -q
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git checkout -b "$TARGET_BRANCH" >/dev/null 2>&1
git add .
git commit -m "Update onboarding sync bundle" >/dev/null
git remote add origin "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
git push --force origin "HEAD:${TARGET_BRANCH}"
