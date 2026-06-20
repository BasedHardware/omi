# Publishes the win-update-helper as a self-contained single-file exe into
# resources/win-update-helper/ (gitignored). Ships via electron-builder's
# `asarUnpack: resources/**` and is resolved at runtime by resolveHelperPath.ts.
# This is the native Task-Dialog progress UI for auto-update.
$ErrorActionPreference = 'Stop'
$proj = Join-Path $PSScriptRoot '..\src\main\update\win-update-helper'
$out = Join-Path $PSScriptRoot '..\resources\win-update-helper'

dotnet publish $proj `
  -c Release `
  -r win-x64 `
  --self-contained true `
  -p:PublishSingleFile=true `
  -o $out

if (-not (Test-Path (Join-Path $out 'win-update-helper.exe'))) {
  throw 'build-update-helper: win-update-helper.exe was not produced'
}
Write-Host "build-update-helper: published to $out"
