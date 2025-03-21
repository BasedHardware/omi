# Set up the Omi Mobile Project(iOS/Android).
# Prerequisites same as original script

# Enable strict mode
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "👋 Yo folks! Welcome to the OMI Mobile Project - We're hiring! Join us on Discord: http://discord.omi.me"
Write-Host "Prerequisites:"
Write-Host "- Flutter SDK"
Write-Host "- Dart SDK"
Write-Host "- Xcode (for iOS)"
Write-Host "- CocoaPods (for iOS dependencies)"
Write-Host "- Android Studio (for Android)"
Write-Host "- NDK 26.3.11579264 or above (to build Opus for ARM Devices)"
Write-Host "- Opus Codec: https://opus-codec.org"
Write-Host "Usages:"
Write-Host "- .\setup.ps1 ios"
Write-Host "- .\setup.ps1 android"
Write-Host ""

$API_BASE_URL = "https://backend-dt5lrfkkoa-uc.a.run.app/"

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
    "API_BASE_URL=$API_BASE_URL" | Out-File -FilePath ".dev.env"
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