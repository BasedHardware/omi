#!/bin/bash

# Omi SDK Release Script
# This script handles version management, builds and uploads the omi-sdk package to PyPI

set -e  # Exit on any error

echo "🚀 Starting Omi SDK release process..."

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo "❌ Error: pyproject.toml not found. Make sure you're in the sdks/python directory."
    exit 1
fi

# Check if required tools are installed
if ! command -v python &> /dev/null; then
    echo "❌ Error: python not found"
    exit 1
fi

if ! python -m pip show build &> /dev/null; then
    echo "📦 Installing build tools..."
    python -m pip install build twine
fi

# Get current version from pyproject.toml
CURRENT_VERSION=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")
echo "📋 Current version: ${CURRENT_VERSION}"

# Check if this version already exists on PyPI
echo "🔍 Checking if version exists on PyPI..."
if pip index versions omi-sdk 2>/dev/null | grep -q "${CURRENT_VERSION}"; then
    echo "❌ Error: Version ${CURRENT_VERSION} already exists on PyPI!"
    echo "💡 Please update the version in pyproject.toml first."
    exit 1
fi

# Check for uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo "⚠️  Warning: You have uncommitted changes."
    read -p "🤔 Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Release cancelled. Please commit your changes first."
        exit 1
    fi
fi

# Check if we're on main branch (optional warning)
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
if [ "$CURRENT_BRANCH" != "main" ] && [ "$CURRENT_BRANCH" != "master" ]; then
    echo "⚠️  Warning: You're not on main/master branch (current: ${CURRENT_BRANCH})"
    read -p "🤔 Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Release cancelled."
        exit 1
    fi
fi

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf dist/ build/ *.egg-info/

# Build the package
echo "📦 Building package..."
python -m build

# Check the build
echo "🔍 Checking package..."
python -m twine check dist/*

# Display what will be uploaded
echo "📋 Package contents:"
ls -la dist/

# Show final summary
echo ""
echo "🎯 Release Summary:"
echo "   Package: omi-sdk"
echo "   Version: ${CURRENT_VERSION}"
echo "   Branch:  ${CURRENT_BRANCH}"
echo ""

# Ask for confirmation before uploading
read -p "🤔 Do you want to upload to PyPI? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "⬆️ Uploading to PyPI..."
    python -m twine upload dist/*
    echo "✅ Release complete!"
    
    # Create git tag for this release
    read -p "🏷️  Create git tag v${CURRENT_VERSION}? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        git tag "v${CURRENT_VERSION}"
        echo "✅ Git tag v${CURRENT_VERSION} created."
        echo "💡 Push the tag with: git push origin v${CURRENT_VERSION}"
    fi
    
    echo "🎉 omi-sdk v${CURRENT_VERSION} has been released!"
    echo "📦 Package URL: https://pypi.org/project/omi-sdk/${CURRENT_VERSION}/"
else
    echo "❌ Upload cancelled."
    echo "💡 To upload later, run: python -m twine upload dist/*"
fi

echo "🧹 Cleaning up..."
rm -rf build/ *.egg-info/