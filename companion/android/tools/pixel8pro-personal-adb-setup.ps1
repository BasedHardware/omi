param(
    [string]$PackageName = "com.omi.ambientcompanion"
)

Write-Host "Granting personal-use Android stability settings for $PackageName"
Write-Host "These commands are optional. The app must still work without them."

adb shell cmd appops set $PackageName RUN_ANY_IN_BACKGROUND allow
adb shell am set-standby-bucket $PackageName exempt
adb shell dumpsys deviceidle whitelist +$PackageName
adb shell cmd appops get $PackageName
adb shell am get-standby-bucket $PackageName

Write-Host "Open App Info > Battery and set Unrestricted if the OEM UI still throttles it."
