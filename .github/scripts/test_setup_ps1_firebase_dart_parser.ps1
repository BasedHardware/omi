# PowerShell StrictMode fixture for Get-FirebaseProjectIdFromPrebuilt (#9404 / #11135).
# A single unique Dart projectId Match pipeline is a scalar string; .Count throws
# unless the result is forced to an array with @(...).
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "../..")
. (Join-Path $RepoRoot "app/setup/scripts/setup.ps1")

$fixture = @"
const FirebaseOptions android = FirebaseOptions(
  projectId: 'demo-omi-local',
);
const FirebaseOptions ios = FirebaseOptions(
  projectId: 'demo-omi-local',
);
"@
$temp = New-TemporaryFile
try {
    Set-Content -Path $temp.FullName -Value $fixture -Encoding utf8
    # Rename so the *.dart branch is selected.
    $dartPath = [System.IO.Path]::ChangeExtension($temp.FullName, ".dart")
    Move-Item -Force $temp.FullName $dartPath
    $project = Get-FirebaseProjectIdFromPrebuilt $dartPath
    if ($project -ne "demo-omi-local") {
        throw "expected demo-omi-local, got '$project'"
    }
    Write-Host "OK: PowerShell Dart Firebase parser under Set-StrictMode"
}
finally {
    if (Test-Path $dartPath) { Remove-Item -Force $dartPath }
}
