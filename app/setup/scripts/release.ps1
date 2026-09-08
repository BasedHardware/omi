$ErrorActionPreference = "Stop"

$AppDir = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
Set-Location $AppDir

$EnvFile = Join-Path $AppDir ".env"
if (-not (Test-Path $EnvFile)) {
    throw "Missing .env; prepare the mobile beta environment before releasing."
}
$EnvSettings = @{}
Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^([^#][^=]*)=(.*)$') {
        $EnvSettings[$Matches[1]] = $Matches[2]
    }
}
foreach ($Key in @("USE_WEB_AUTH", "USE_AUTH_CUSTOM_TOKEN")) {
    if ($EnvSettings[$Key] -ne "true") {
        throw ".env must contain $Key=true for the prod/mobile_beta release."
    }
}

$Profile = "mobile_beta"
flutter clean
flutter pub get
dart run build_runner build --delete-conflicting-outputs
flutter build appbundle --release --flavor prod -t lib/main_prod.dart `
  --dart-define=OMI_APP_PROFILE=$Profile
flutter build apk --release --flavor prod -t lib/main_prod.dart `
  --dart-define=OMI_APP_PROFILE=$Profile
