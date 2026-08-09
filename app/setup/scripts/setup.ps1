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


function SetupFirebase {
    # Create directories if they don't exist
    New-Item -ItemType Directory -Force -Path "android/app/src/dev/", "ios/Config/Dev/", "ios/Runner/"
    
    # Copy files
    Copy-Item "setup/prebuilt/firebase_options_local.dart" -Destination "lib/firebase_options_dev.dart"
    Copy-Item "setup/prebuilt/google-services-local.json" -Destination "android/app/src/dev/google-services.json"
    Copy-Item "setup/prebuilt/GoogleService-Info-Local.plist" -Destination "ios/Config/Dev/GoogleService-Info.plist"
    Copy-Item "setup/prebuilt/GoogleService-Info-Local.plist" -Destination "ios/Runner/GoogleService-Info.plist"

    # Mocking setup
    New-Item -ItemType Directory -Force -Path "android/app/src/prod/", "ios/Config/Prod/"
    Copy-Item "setup/prebuilt/firebase_options_local.dart" -Destination "lib/firebase_options_prod.dart"
    Copy-Item "setup/prebuilt/google-services-local.json" -Destination "android/app/src/prod/google-services.json"
    Copy-Item "setup/prebuilt/GoogleService-Info-Local.plist" -Destination "ios/Config/Prod/GoogleService-Info.plist"
}


function SetupFirebaseWithServiceAccountAndroid {
    dart pub global activate flutterfire_cli

    flutterfire config `
        --platforms="android" `
        --out="lib/firebase_options_prod.dart" `
        --android-app-id="com.friend.ios" `
        --android-out="android/app/src/prod/" `
        --service-account="$env:FIREBASE_SERVICE_ACCOUNT_KEY" `
        --project="based-hardware" `
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
    param(
        [string]$Profile = "local_dev",
        [string]$ApiBaseUrl = ""
    )
    if ([string]::IsNullOrWhiteSpace($ApiBaseUrl)) {
        $devHost = if ($env:OMI_DEV_HOST) { $env:OMI_DEV_HOST } else { "127.0.0.1" }
        $ApiBaseUrl = "http://$devHost`:8000/"
    }
    if ($Profile -eq "mobile_beta") {
        $ApiBaseUrl = if ($env:OMI_BETA_API_BASE_URL) { $env:OMI_BETA_API_BASE_URL } else { "https://api.omiapi.com/" }
        $envFile = ".env"
    } else {
        $envFile = ".dev.env"
    }
    # Using Set-Content with UTF8 encoding
    $content = "API_BASE_URL=$ApiBaseUrl`nUSE_WEB_AUTH=true`nUSE_AUTH_CUSTOM_TOKEN=true"
    [System.IO.File]::WriteAllText((Join-Path (Get-Location) $envFile), $content, [System.Text.Encoding]::UTF8)
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
    $devHost = if ($env:OMI_DEV_HOST) { $env:OMI_DEV_HOST } else { "10.0.2.2" }
    $apiBaseUrl = if ($env:OMI_LOCAL_API_BASE_URL) { $env:OMI_LOCAL_API_BASE_URL } else { "http://$devHost`:8000/" }
    $flutterArgs = @(
        "run", "--flavor", "dev",
        "--dart-define=OMI_APP_PROFILE=local_dev",
        "--dart-define=OMI_API_BASE_URL=$apiBaseUrl",
        "--dart-define=OMI_FIREBASE_AUTH_EMULATOR_HOST=$devHost"
    )
    & flutter @flutterArgs
}

function RunAndroidBeta {
    $apiBaseUrl = if ($env:OMI_BETA_API_BASE_URL) { $env:OMI_BETA_API_BASE_URL } else { "https://api.omiapi.com/" }
    $flutterArgs = @(
        "run", "--flavor", "prod",
        "--dart-define=OMI_APP_PROFILE=mobile_beta",
        "--dart-define=OMI_API_BASE_URL=$apiBaseUrl"
    )
    & flutter @flutterArgs
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
        if ($args.Count -gt 1) {
            if ($args[1].ToLower() -eq "beta") {
                Write-Error "ios beta is only supported by bash setup.sh on macOS; use 'bash setup.sh ios beta'."
            } else {
                Write-Error "Unsupported iOS setup profile '$($args[1])'."
            }
            exit 1
        }
        Write-Host "`nSetting up iOS platform..."
        SetupFirebase
        SetupAppEnv
        SetupProvisioningProfile
        BuildiOS
    }
    "android" {
        Write-Host "`nSetting up Android platform..."
        if ($args.Count -gt 1 -and $args[1].ToLower() -eq "beta") {
            if ([string]::IsNullOrWhiteSpace($env:FIREBASE_SERVICE_ACCOUNT_KEY)) {
                Write-Error "android beta requires FIREBASE_SERVICE_ACCOUNT_KEY"
                exit 1
            }
            SetupKeystoreAndroid
            SetupFirebase
            SetupFirebaseWithServiceAccountAndroid
            SetupAppEnv -Profile "mobile_beta"
            Build
            RunAndroidBeta
        } else {
            SetupKeystoreAndroid
            SetupFirebase
            SetupAppEnv -Profile "local_dev"
            Build
            RunDev
        }
    }
    default {
        Write-Host "Unexpected platform '$platform'. Please use 'ios' or 'android'"
        exit 1
    }
} 
