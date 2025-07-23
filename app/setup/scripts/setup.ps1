# Set up the Omi Mobile Project(iOS/Android).
#
# Prerequisites (stable versions, use these or higher):
#
# Common for all developers:
# - Flutter SDK (v3.32.4)
# - Opus Codec: https://opus-codec.org
#
# For iOS Developers:
# - Xcode (v16.4)
# - CocoaPods (v1.16.2)
#
# For Android Developers:
# - Android Studio (Iguana | 2024.3)
# - Android SDK Platform (API 35)
# - JDK (v21)
# - Gradle (v8.10)
# - NDK (27.0.12077973)

# Enable strict mode
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "👋 Yo folks! Welcome to the OMI Mobile Project - We're hiring! Join us on Discord: http://discord.omi.me"
Write-Host "Prerequisites (stable versions, use these or higher):"
Write-Host ""
Write-Host "Common for all developers:"
Write-Host "- Flutter SDK (v3.32.4)"
Write-Host "- Opus Codec: https://opus-codec.org"
Write-Host ""
Write-Host "For iOS Developers:"
Write-Host "- Xcode (v16.4)"
Write-Host "- CocoaPods (v1.16.2)"
Write-Host ""
Write-Host "For Android Developers:"
Write-Host "- Android Studio (Iguana | 2024.3)"
Write-Host "- Android SDK Platform (API 35)"
Write-Host "- JDK (v21)"
Write-Host "- Gradle (v8.10)"
Write-Host "- NDK (27.0.12077973)"
Write-Host ""


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
}


function SetupFirebaseWithServiceAccount {
    dart pub global activate flutterfire_cli
    
    # Dev configuration
    flutterfire config `
        --platforms="android,ios,web" `
        --out="lib/firebase_options_dev.dart" `
        --ios-bundle-id="com.friend-app-with-wearable.ios12.development" `
        --android-app-id="com.friend.ios.dev" `
        --android-out="android/app/src/dev/" `
        --ios-out="ios/Config/Dev/" `
        --service-account="$env:FIREBASE_SERVICE_ACCOUNT_KEY" `
        --project="based-hardware-dev" `
        --ios-target="Runner" `
        --yes

    # Prod configuration
    flutterfire config `
        --platforms="android,ios,web" `
        --out="lib/firebase_options_prod.dart" `
        --ios-bundle-id="com.friend-app-with-wearable.ios12" `
        --android-app-id="com.friend.ios.dev" `
        --android-out="android/app/src/prod/" `
        --ios-out="ios/Config/Prod/" `
        --service-account="$env:FIREBASE_SERVICE_ACCOUNT_KEY" `
        --project="based-hardware-dev" `
        --ios-target="Runner" `
        --yes
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
    $API_BASE_URL = "https://api.omiapi.com/"
    # Using Set-Content with UTF8 encoding
    $content = "API_BASE_URL=$API_BASE_URL"
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
