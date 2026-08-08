# Set up the Omi Mobile Project(iOS/Android).
#
# Prerequisites (stable versions, use these or higher):
#
# Common for all developers:
# - Flutter SDK (v3.41.9)
# - Opus Codec: https://opus-codec.org
#
# For iOS Developers:
# - Xcode (v16.4)
# - CocoaPods (v1.16.2)
#
# For Android Developers:
# - Android Studio (Iguana | 2024.3)
# - Android SDK Platform (API 36)
# - JDK (v21)
# - Gradle (v8.10)
# - NDK (28.2.13676358)

# Enable strict mode
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "👋 Yo folks! Welcome to the OMI Mobile Project - We're hiring! Join us on Discord: http://discord.omi.me"
Write-Host "Prerequisites (stable versions, use these or higher):"
Write-Host ""
Write-Host "Common for all developers:"
Write-Host "- Flutter SDK (v3.41.9)"
Write-Host "- Opus Codec: https://opus-codec.org"
Write-Host ""
Write-Host "For iOS Developers:"
Write-Host "- Xcode (v16.4)"
Write-Host "- CocoaPods (v1.16.2)"
Write-Host ""
Write-Host "For Android Developers:"
Write-Host "- Android Studio (Iguana | 2024.3)"
Write-Host "- Android SDK Platform (API 36)"
Write-Host "- JDK (v21)"
Write-Host "- Gradle (v8.10)"
Write-Host "- NDK (28.2.13676358)"
Write-Host ""

# Honor caller override so local-backend setup actually writes that URL to .dev.env
# (#9404 review). Default remains community remote staging.
if ([string]::IsNullOrWhiteSpace($env:API_BASE_URL)) {
    $script:API_BASE_URL = "https://api.omiapi.com/"
} else {
    $script:API_BASE_URL = $env:API_BASE_URL
}

function SetupFirebase {
    # Create directories if they don't exist
    New-Item -ItemType Directory -Force -Path "android/app/src/dev/", "ios/Config/Dev/", "ios/Runner/"
    
    # Copy files
    Copy-Item "setup/prebuilt/firebase_options.dart" -Destination "lib/firebase_options_dev.dart"
    Copy-Item "setup/prebuilt/google-services.json" -Destination "android/app/src/dev/"
    Copy-Item "setup/prebuilt/GoogleService-Info.plist" -Destination "ios/Config/Dev/"
    Copy-Item "setup/prebuilt/GoogleService-Info.plist" -Destination "ios/Runner/"

    # Mocking setup
    New-Item -ItemType Directory -Force -Path "android/app/src/prod/", "ios/Config/Prod/"
    Copy-Item "setup/prebuilt/firebase_options.dart" -Destination "lib/firebase_options_prod.dart"
    Copy-Item "setup/prebuilt/google-services.json" -Destination "android/app/src/prod/"
    Copy-Item "setup/prebuilt/GoogleService-Info.plist" -Destination "ios/Config/Prod/"

    Validate-FirebaseApiAlignment
}

# Fail closed when community remote-staging API cannot verify Firebase tokens
# (#9404 / #5939). Do not text-replace project IDs — regenerate via FlutterFire.
# Compares every prebuilt artifact the app copies (json + dart + plist).
function Get-FirebaseProjectIdFromPrebuilt {
    param([string]$Path)
    $text = Get-Content -Raw $Path
    if ($Path -like "*.json") {
        $match = [regex]::Match($text, '"project_id"\s*:\s*"([^"]+)"')
        if ($match.Success) { return $match.Groups[1].Value }
        return ""
    }
    if ($Path -like "*.plist") {
        $match = [regex]::Match($text, '<key>PROJECT_ID</key>\s*<string>([^<]+)</string>')
        if ($match.Success) { return $match.Groups[1].Value }
        return ""
    }
    if ($Path -like "*.dart") {
        $ids = [regex]::Matches($text, "projectId:\s*'([^']+)'") | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
        if ($ids.Count -eq 1) { return $ids[0] }
        return ""
    }
    return ""
}

function Validate-FirebaseApiAlignment {
    $jsonProj = Get-FirebaseProjectIdFromPrebuilt "setup/prebuilt/google-services.json"
    $dartProj = Get-FirebaseProjectIdFromPrebuilt "setup/prebuilt/firebase_options.dart"
    $plistProj = Get-FirebaseProjectIdFromPrebuilt "setup/prebuilt/GoogleService-Info.plist"

    if ([string]::IsNullOrWhiteSpace($jsonProj) -or [string]::IsNullOrWhiteSpace($dartProj) -or [string]::IsNullOrWhiteSpace($plistProj)) {
        Write-Host "ERROR: could not parse Firebase project id from app/setup/prebuilt/* (#9404)."
        Write-Host "  google-services.json → '$jsonProj'"
        Write-Host "  firebase_options.dart → '$dartProj'"
        Write-Host "  GoogleService-Info.plist → '$plistProj'"
        exit 1
    }
    if ($jsonProj -ne $dartProj -or $jsonProj -ne $plistProj) {
        Write-Host "ERROR: prebuilt Firebase configs disagree on project id (#9404)."
        Write-Host "  google-services.json → '$jsonProj'"
        Write-Host "  firebase_options.dart → '$dartProj'"
        Write-Host "  GoogleService-Info.plist → '$plistProj'"
        Write-Host "Regenerate the full trio via FlutterFire (do NOT text-replace — #5945)."
        exit 1
    }
    $project = $jsonProj

    if ($script:API_BASE_URL -eq "https://api.omiapi.com/" -and $project -ne "based-hardware") {
        Write-Host "ERROR: Firebase project '$project' cannot authenticate to $($script:API_BASE_URL)."
        Write-Host "Community remote staging requires Firebase project 'based-hardware' (#9404)."
        Write-Host "Tokens from '$project' are rejected with 401 by the live backend."
        Write-Host ""
        Write-Host "Maintainer action: regenerate app/setup/prebuilt/* via FlutterFire against"
        Write-Host "  based-hardware (do NOT text-replace project IDs — closed PR #5945)."
        Write-Host ""
        Write-Host "Isolated local backend / emulator workaround (honors API_BASE_URL override):"
        Write-Host "  `$env:API_BASE_URL='http://127.0.0.1:8000/'; then re-run setup.ps1"
        exit 1
    }
}

function SetupProvisioningProfile {
    # Check if fastlane exists
    if (!(Get-Command "fastlane" -ErrorAction SilentlyContinue)) {
        Write-Host "Installing fastlane..."
        brew install fastlane
    }
    
    $env:MATCH_PASSWORD = "omi"
    fastlane match development --readonly `
        --app_identifier "com.friend-app-with-wearable.ios12.development" `
        --git_url "git@github.com:BasedHardware/omi-community-certs.git"
}


function SetupAppEnv {
    # Using Set-Content with UTF8 encoding
    $content = "API_BASE_URL=$($script:API_BASE_URL)"
    [System.IO.File]::WriteAllText((Join-Path (Get-Location) ".dev.env"), $content, [System.Text.Encoding]::UTF8)
}

function SetupKeystoreAndroid {
    Copy-Item "setup/prebuilt/key.properties" -Destination "android/"
}

function Build {
    flutter pub get
    dart run build_runner build
}

function BuildiOS {
    flutter pub get
    Push-Location "ios"
    pod install --repo-update
    Pop-Location
    dart run build_runner build
}

function RunDev {
    flutter run --flavor dev
}

# Function to show menu and get platform choice
function Show-PlatformMenu {
    Write-Host "`nSelect platform to setup:"
    Write-Host "1. iOS"
    Write-Host "2. Android"
    Write-Host "3. Exit"
    
    $choice = Read-Host "`nEnter your choice (1-3)"
    
    switch ($choice) {
        "1" { return "ios" }
        "2" { return "android" }
        "3" { exit 0 }
        default { 
            Write-Host "Invalid choice. Please try again."
            return Show-PlatformMenu
        }
    }
}

# Get platform from argument or menu
$platform = if ($args.Count -eq 0) {
    Show-PlatformMenu
} else {
    $args[0]
}

# Replace the existing switch block with this:
switch ($platform.ToLower()) {
    "ios" {
        Write-Host "`nSetting up iOS platform..."
        SetupFirebase
        SetupAppEnv
        SetupProvisioningProfile
        BuildiOS
    }
    "android" {
        Write-Host "`nSetting up Android platform..."
        SetupKeystoreAndroid
        SetupFirebase
        SetupAppEnv
        Build
    }
    default {
        Write-Host "Unexpected platform '$platform'. Please use 'ios' or 'android'"
        exit 1
    }
} 
