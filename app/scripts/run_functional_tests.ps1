[CmdletBinding()]
param(
  [string]$AppId = "com.friend.ios.dev",
  [string]$FlowsDir = ".maestro\\flows",
  [string]$ReportsDir = ".\\test-results\\functional",
  [string]$FlowFilter = "",
  [switch]$StopOnFailure
)

$ErrorActionPreference = "Stop"

function New-DirectoryIfMissing {
  param([string]$Path)

  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

function Get-FlowName {
  param([string]$FlowPath)

  return [System.IO.Path]::GetFileNameWithoutExtension($FlowPath)
}

$maestro = Get-Command maestro -ErrorAction SilentlyContinue
if (-not $maestro) {
  throw "Maestro CLI was not found in PATH. Install Maestro before running the functional suite."
}

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$resolvedFlowsDir = Join-Path $workspaceRoot $FlowsDir
$resolvedReportsDir = Join-Path $workspaceRoot $ReportsDir

if (-not (Test-Path -LiteralPath $resolvedFlowsDir)) {
  throw "Flow directory not found: $resolvedFlowsDir"
}

New-DirectoryIfMissing -Path $resolvedReportsDir

$flowFiles = Get-ChildItem -Path $resolvedFlowsDir -Filter *.yaml | Sort-Object Name
if ($FlowFilter) {
  $flowFiles = $flowFiles | Where-Object { $_.Name -like "*$FlowFilter*" }
}

if (-not $flowFiles) {
  throw "No Maestro flow files matched the current filter."
}

$env:APP_ID = $AppId
$runStartedAt = Get-Date
$results = @()

foreach ($flowFile in $flowFiles) {
  $flowName = Get-FlowName -FlowPath $flowFile.FullName
  $logPath = Join-Path $resolvedReportsDir "$flowName.log"
  $startedAt = Get-Date

  Write-Host "Running $flowName against $AppId"

  try {
    & $maestro.Source test $flowFile.FullName 2>&1 | Tee-Object -FilePath $logPath
    $exitCode = $LASTEXITCODE
  } catch {
    $_ | Out-String | Set-Content -Path $logPath
    $exitCode = 1
  }

  $finishedAt = Get-Date
  $passed = $exitCode -eq 0

  $results += [pscustomobject]@{
    name = $flowName
    file = $flowFile.FullName
    passed = $passed
    exitCode = $exitCode
    startedAt = $startedAt.ToString("o")
    finishedAt = $finishedAt.ToString("o")
    durationSeconds = [math]::Round(($finishedAt - $startedAt).TotalSeconds, 2)
    logPath = $logPath
  }

  if (-not $passed -and $StopOnFailure) {
    break
  }
}

$summary = [pscustomobject]@{
  appId = $AppId
  runStartedAt = $runStartedAt.ToString("o")
  runFinishedAt = (Get-Date).ToString("o")
  totalFlows = $results.Count
  passedFlows = ($results | Where-Object { $_.passed }).Count
  failedFlows = ($results | Where-Object { -not $_.passed }).Count
  reportsDir = $resolvedReportsDir
  results = $results
}

$jsonPath = Join-Path $resolvedReportsDir "functional-test-results.json"
$mdPath = Join-Path $resolvedReportsDir "functional-test-results.md"

$summary | ConvertTo-Json -Depth 5 | Set-Content -Path $jsonPath

$markdown = @(
  "# Functional Test Results"
  ""
  "- App ID: ``$AppId``"
  "- Started: $($summary.runStartedAt)"
  "- Finished: $($summary.runFinishedAt)"
  "- Passed: $($summary.passedFlows)/$($summary.totalFlows)"
  ""
  "| Flow | Result | Duration (s) | Log |"
  "| --- | --- | ---: | --- |"
)

foreach ($result in $results) {
  $status = if ($result.passed) { "PASS" } else { "FAIL" }
  $markdown += "| $($result.name) | $status | $($result.durationSeconds) | $($result.logPath) |"
}

$markdown -join [Environment]::NewLine | Set-Content -Path $mdPath

Write-Host ""
Write-Host "Functional test summary written to:"
Write-Host "  $jsonPath"
Write-Host "  $mdPath"

if (($results | Where-Object { -not $_.passed }).Count -gt 0) {
  exit 1
}
