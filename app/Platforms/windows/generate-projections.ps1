# Runs ON WINDOWS with the Windows SDK + swift-winrt installed.
# Generates the Swift projections declared in projections.yaml into ./Generated.
#
# swift-winrt status (be honest when briefing people): The Browser Company
# archived the repo (https://github.com/thebrowsercompany/swift-winrt) in
# early 2025 — the tool still works for the namespaces we need, and the
# last release remains downloadable from GitHub Releases, but it receives
# no maintenance. Long-term options: pin the last release, fork, or adopt
# the community continuation if one matures. Document whichever you pin.

$ErrorActionPreference = "Stop"

$swiftWinrt = Get-Command swift-winrt.exe -ErrorAction SilentlyContinue
if (-not $swiftWinrt) {
    Write-Error "swift-winrt.exe not found on PATH. Install the last release: " +
                "https://github.com/thebrowsercompany/swift-winrt/releases"
}

# Generate Swift projections from the WinRT metadata shipped with the SDK.
swift-winrt generate --config (Resolve-Path "$PSScriptRoot/projections.yaml")

Write-Host "Projections generated into $PSScriptRoot/Generated"
Write-Host "Next: build the host with CMake (see CMakeLists.txt) or via SPM:"
Write-Host "  swift build $PSScriptRoot"
