param(
  [string]$Root = (Join-Path $PSScriptRoot '..\dist\win-unpacked\resources\app.asar.unpacked\resources')
)

$ErrorActionPreference = 'Stop'
$helpers = @('win-ocr-helper', 'win-automation-helper')

foreach ($helper in $helpers) {
  $exe = Join-Path $Root "$helper\$helper.exe"
  if (-not (Test-Path -LiteralPath $exe)) {
    throw "verify-native-helpers: missing $exe"
  }

  & $exe --selftest
  if ($LASTEXITCODE -ne 0) {
    throw "verify-native-helpers: $helper selftest exited $LASTEXITCODE"
  }
}

Write-Host 'verify-native-helpers: packaged OCR and automation helpers passed selftest'
