#!/bin/bash

# omi-cli release script
# Builds the omi-cli package and (optionally) uploads to PyPI.
#
# Usage:
#   ./release.sh                    # interactive: build, twine check, prompt before upload
#   ./release.sh --build-only       # build + twine check only, no upload, no tag prompt
#
# Tag scheme: omi-cli-vX.Y.Z (does NOT collide with the omi-sdk's vX.Y.Z scheme).

set -e

BUILD_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --build-only)
            BUILD_ONLY=1
            ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "❌ Unknown argument: $arg"
            exit 1
            ;;
    esac
done

echo "🚀 Starting omi-cli release process..."

if [ ! -f "pyproject.toml" ]; then
    echo "❌ Error: pyproject.toml not found. Run from sdks/python-cli/."
    exit 1
fi

if ! command -v python &> /dev/null; then
    echo "❌ Error: python not found"
    exit 1
fi

if ! python -m pip show build &> /dev/null; then
    echo "📦 Installing build tools..."
    python -m pip install --quiet build twine
fi

CURRENT_VERSION=$(python -c "
import sys
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib
print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])
")
echo "📋 Current version: ${CURRENT_VERSION}"

echo "🔍 Checking if version exists on PyPI..."
if pip index versions omi-cli 2>/dev/null | grep -q "${CURRENT_VERSION}"; then
    echo "❌ Error: Version ${CURRENT_VERSION} already exists on PyPI."
    echo "💡 Bump the version in pyproject.toml first."
    exit 1
fi

if ! git diff-index --quiet HEAD --; then
    echo "⚠️  Warning: uncommitted changes present."
    if [ "$BUILD_ONLY" -eq 0 ]; then
        read -p "🤔 Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "❌ Release cancelled."
            exit 1
        fi
    fi
fi

CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
echo "🌿 Branch: ${CURRENT_BRANCH}"

echo "🧹 Cleaning previous builds..."
rm -rf dist/ build/ *.egg-info/

echo "📦 Building package..."
python -m build

echo "🔍 Verifying package metadata..."
python -m twine check dist/*

echo "📋 Built artifacts:"
ls -la dist/

echo
echo "🎯 Release Summary"
echo "   Package: omi-cli"
echo "   Version: ${CURRENT_VERSION}"
echo "   Branch:  ${CURRENT_BRANCH}"
echo

if [ "$BUILD_ONLY" -eq 1 ]; then
    echo "✅ Build complete (build-only mode — no upload, no tag)."
    echo "💡 To upload manually: python -m twine upload dist/*"
    echo "💡 To tag: git tag omi-cli-v${CURRENT_VERSION}"
    exit 0
fi

read -p "🤔 Upload to PyPI? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "⬆️  Uploading to PyPI..."
    python -m twine upload dist/*
    echo "✅ Uploaded."

    read -p "🏷️  Create git tag omi-cli-v${CURRENT_VERSION}? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        git tag "omi-cli-v${CURRENT_VERSION}"
        echo "✅ Tag created locally. Push with: git push origin omi-cli-v${CURRENT_VERSION}"
    fi

    echo "🎉 omi-cli v${CURRENT_VERSION} released!"
    echo "📦 https://pypi.org/project/omi-cli/${CURRENT_VERSION}/"
else
    echo "❌ Upload cancelled."
    echo "💡 To upload later: python -m twine upload dist/*"
fi

echo "🧹 Cleaning intermediate build dirs..."
rm -rf build/ *.egg-info/
