# Publishes the win-ocr-helper as a self-contained single-file exe into
# resources/win-ocr-helper/ (gitignored). Ships via electron-builder's
# `asarUnpack: resources/**` and is resolved at runtime by resolveHelperPath.ts.
$ErrorActionPreference = 'Stop'
$proj = Join-Path $PSScriptRoot '..\src\main\ocr\win-ocr-helper'
$out = Join-Path $PSScriptRoot '..\resources\win-ocr-helper'

dotnet publish $proj `
  -c Release `
  -r win-x64 `
  --self-contained true `
  -p:PublishSingleFile=true `
  -o $out

if (-not (Test-Path (Join-Path $out 'win-ocr-helper.exe'))) {
  throw 'build-ocr-helper: win-ocr-helper.exe was not produced'
}
Write-Host "build-ocr-helper: published to $out"
