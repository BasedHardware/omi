#!/bin/bash
set -e

# =============================================================================
# DEPRECATED — DO NOT USE FOR MANUAL RELEASES
# =============================================================================
#
# The source of truth for desktop releases is the automated pipeline:
#
# 1. GitHub Actions: .github/workflows/desktop_auto_release.yml
#    https://github.com/BasedHardware/omi/blob/main/.github/workflows/desktop_auto_release.yml
#    - Triggers on push to main (desktop/** paths)
#    - Deploys Rust backend to Cloud Run
#    - Auto-increments version, creates git tag
#
# 2. Codemagic: codemagic.yaml (workflow: omi-desktop-swift-release)
#    https://github.com/BasedHardware/omi/blob/main/codemagic.yaml
#    - Triggered by v*-macos tag from GitHub Actions
#    - Builds universal binary (arm64 + x86_64) on Mac mini M2
#    - Signs with Developer ID, notarizes with Apple
#    - Creates DMG + Sparkle ZIP
#    - Publishes GitHub release, uploads to GCS, registers in Firestore
#    - Sparkle auto-update delivers to users
#
# How to release:
#   Merge your desktop changes to main. That's it.
#   The pipeline handles everything else automatically.
#   Builds default to the beta channel and go live immediately.
#
# To promote to stable:
#   Update the GitHub release manually to mark it as the stable channel.
#
# DO NOT run this script manually. Manual releases cause:
#   - Version conflicts with the automated pipeline
#   - Missing changelog consolidation
#   - Inconsistent signing/notarization
#   - Env var drift between local and CI
#
# =============================================================================

echo ""
echo "ERROR: Manual releases are deprecated."
echo ""
echo "The release pipeline is fully automated:"
echo "  1. Merge desktop changes to main"
echo "  2. GitHub Actions deploys backend + creates version tag"
echo "  3. Codemagic builds, signs, notarizes, and publishes"
echo ""
echo "Workflows:"
echo "  https://github.com/BasedHardware/omi/blob/main/.github/workflows/desktop_auto_release.yml"
echo "  https://github.com/BasedHardware/omi/blob/main/codemagic.yaml"
echo ""
echo "Builds default to beta channel. To promote to stable,"
echo "update the GitHub release manually."
echo ""
exit 1
