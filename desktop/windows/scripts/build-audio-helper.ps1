# Publishes win-audio-helper as a self-contained single-file exe into
# resources/win-audio-helper/ (gitignored). Ships via electron-builder's
# `asarUnpack: resources/**`, resolved at runtime by
# src/main/audio/resolveHelperPath.ts. Mirrors build-automation-helper.ps1.
$ErrorActionPreference = 'Stop'
$proj = Join-Path $PSScriptRoot '..\src\main\audio\helper'
$out = Join-Path $PSScriptRoot '..\resources\win-audio-helper'

dotnet publish $proj `
  -c Release `
  -r win-x64 `
  --self-contained true `
  -p:PublishSingleFile=true `
  -o $out

if (-not (Test-Path (Join-Path $out 'win-audio-helper.exe'))) {
  throw 'build-audio-helper: win-audio-helper.exe was not produced'
}
Write-Host "build-audio-helper: published to $out"
