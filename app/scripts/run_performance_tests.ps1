param(
  [string]$DeviceId,
  [string]$Flavor = "dev",
  [string]$PackageName,
  [string]$OutputDir,
  [switch]$SkipBuild,
  [switch]$KeepGoing
)

$ErrorActionPreference = "Stop"

function Require-Command {
  param([string]$Name)
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Required command '$Name' was not found in PATH."
  }
}

function Get-RepoRoot {
  param([string]$StartDir)
  $current = Get-Item -LiteralPath $StartDir
  while ($null -ne $current) {
    if (Test-Path (Join-Path $current.FullName "pubspec.yaml")) {
      return $current.FullName
    }
    $current = $current.Parent
  }
  throw "Unable to locate Flutter app root from '$StartDir'."
}

function Get-AndroidApplicationId {
  param(
    [string]$AppRoot,
    [string]$Flavor
  )

  $gradlePath = Join-Path $AppRoot "android\app\build.gradle"
  if (-not (Test-Path -LiteralPath $gradlePath)) {
    throw "Unable to resolve Android applicationId because '$gradlePath' was not found."
  }

  $gradleText = Get-Content -LiteralPath $gradlePath -Raw
  $escapedFlavor = [regex]::Escape($Flavor)
  $flavorPattern = "(?ms)^\s*$escapedFlavor\s*\{.*?applicationId\s+""(?<id>[^""]+)"""
  $defaultPattern = '(?ms)defaultConfig\s*\{.*?applicationId\s+"(?<id>[^"]+)"'

  $flavorMatch = [regex]::Match($gradleText, $flavorPattern)
  if ($flavorMatch.Success) {
    return $flavorMatch.Groups["id"].Value
  }

  $defaultMatch = [regex]::Match($gradleText, $defaultPattern)
  if ($defaultMatch.Success) {
    return $defaultMatch.Groups["id"].Value
  }

  throw "Unable to resolve Android applicationId for flavor '$Flavor' from '$gradlePath'."
}

function Get-ConnectedDevice {
  $lines = adb devices | Select-Object -Skip 1
  foreach ($line in $lines) {
    if ($line -match "^(?<id>\S+)\s+device$") {
      return $matches["id"]
    }
  }
  throw "No connected Android device detected. Connect a device or pass -DeviceId."
}

function New-RunDirectory {
  param([string]$AppRoot, [string]$RequestedOutputDir)
  if ($RequestedOutputDir) {
    $dir = $RequestedOutputDir
  } else {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $dir = Join-Path $AppRoot "test_reports\performance\$timestamp"
  }
  New-Item -ItemType Directory -Path $dir -Force | Out-Null
  return (Resolve-Path $dir).Path
}

function Invoke-TestCommand {
  param(
    [string]$Command,
    [string]$WorkingDirectory,
    [string]$LogPath
  )

  $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = "powershell"
  $psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -Command `$ErrorActionPreference = 'Stop'; $Command"
  $psi.WorkingDirectory = $WorkingDirectory
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true

  $process = New-Object System.Diagnostics.Process
  $process.StartInfo = $psi
  $null = $process.Start()
  $stdout = $process.StandardOutput.ReadToEnd()
  $stderr = $process.StandardError.ReadToEnd()
  $process.WaitForExit()
  $stopwatch.Stop()

  $combined = @(
    "COMMAND: $Command"
    "WORKDIR: $WorkingDirectory"
    "EXIT_CODE: $($process.ExitCode)"
    "DURATION_SECONDS: $([Math]::Round($stopwatch.Elapsed.TotalSeconds, 2))"
    ""
    "STDOUT:"
    $stdout
    ""
    "STDERR:"
    $stderr
  ) -join [Environment]::NewLine
  Set-Content -LiteralPath $LogPath -Value $combined

  return [PSCustomObject]@{
    ExitCode = $process.ExitCode
    DurationSeconds = [Math]::Round($stopwatch.Elapsed.TotalSeconds, 2)
    StdOut = $stdout
    StdErr = $stderr
  }
}

function Get-Highlights {
  param([string]$Text)
  if ([string]::IsNullOrWhiteSpace($Text)) {
    return @()
  }

  $patterns = @(
    "Average",
    "P50",
    "P90",
    "P99",
    "frames",
    "Frame",
    "CPU",
    "battery",
    "Battery",
    "rebuild",
    "jank",
    "raster",
    "build time"
  )

  $lines = $Text -split "`r?`n"
  $highlightMatches = New-Object System.Collections.Generic.List[string]
  foreach ($line in $lines) {
    foreach ($pattern in $patterns) {
      if ($line -match [regex]::Escape($pattern)) {
        $trimmed = $line.Trim()
        if ($trimmed.Length -gt 0 -and -not $highlightMatches.Contains($trimmed)) {
          $highlightMatches.Add($trimmed)
        }
        break
      }
    }
  }
  return $highlightMatches | Select-Object -First 12
}

Require-Command "adb"
Require-Command "flutter"

$appRoot = Get-RepoRoot -StartDir $PSScriptRoot
Push-Location $appRoot

try {
  if (-not $DeviceId) {
    $DeviceId = Get-ConnectedDevice
  }

  if ([string]::IsNullOrWhiteSpace($PackageName)) {
    $PackageName = Get-AndroidApplicationId -AppRoot $appRoot -Flavor $Flavor
  }

  $resolvedOutputDir = New-RunDirectory -AppRoot $appRoot -RequestedOutputDir $OutputDir

  $tests = @(
    [PSCustomObject]@{
      Name = "app_performance"
      Target = "integration_test/app_performance_test.dart"
      Description = "Profiles end-to-end app navigation, animation stability, and frame timing."
    }
    [PSCustomObject]@{
      Name = "animation_performance"
      Target = "integration_test/animation_performance_test.dart"
      Description = "Captures animation-heavy screens to inspect frame pacing and rendering cost."
    }
    [PSCustomObject]@{
      Name = "shimmer_cpu"
      Target = "integration_test/shimmer_cpu_test.dart"
      Description = "Compares static vs shimmer rendering to expose idle CPU cost."
    }
    [PSCustomObject]@{
      Name = "widget_rebuild"
      Target = "integration_test/widget_rebuild_profiling_test.dart"
      Description = "Measures rebuild churn from provider updates and selector boundaries."
    }
  )

  if (-not $SkipBuild) {
    Write-Host "Building profile APK for flavor '$Flavor'..."
    & flutter build apk --profile --flavor $Flavor
  }

  $results = New-Object System.Collections.Generic.List[object]

  foreach ($test in $tests) {
    $command = "flutter drive --driver=test_driver/integration_test.dart --target=$($test.Target) --profile --flavor $Flavor -d $DeviceId"
    $logPath = Join-Path $resolvedOutputDir "$($test.Name).log"

    Write-Host ""
    Write-Host "Running $($test.Name) on $DeviceId"
    $run = Invoke-TestCommand -Command $command -WorkingDirectory $appRoot -LogPath $logPath
    $status = if ($run.ExitCode -eq 0) { "passed" } else { "failed" }
    $highlights = Get-Highlights -Text ($run.StdOut + [Environment]::NewLine + $run.StdErr)

    $results.Add([PSCustomObject]@{
      Name = $test.Name
      Target = $test.Target
      Description = $test.Description
      Status = $status
      ExitCode = $run.ExitCode
      DurationSeconds = $run.DurationSeconds
      DeviceId = $DeviceId
      Flavor = $Flavor
      PackageName = $PackageName
      Command = $command
      LogPath = $logPath
      Highlights = $highlights
    }) | Out-Null

    if ($run.ExitCode -ne 0 -and -not $KeepGoing) {
      break
    }
  }

  $summary = [PSCustomObject]@{
    GeneratedAt = (Get-Date).ToString("o")
    DeviceId = $DeviceId
    Flavor = $Flavor
    PackageName = $PackageName
    AppRoot = $appRoot
    OutputDir = $resolvedOutputDir
    Tests = $results
  }

  $jsonPath = Join-Path $resolvedOutputDir "summary.json"
  $mdPath = Join-Path $resolvedOutputDir "summary.md"

  $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $jsonPath

  $md = New-Object System.Text.StringBuilder
  [void]$md.AppendLine("# Omi Performance Test Report")
  [void]$md.AppendLine("")
  [void]$md.AppendLine("- Generated: $($summary.GeneratedAt)")
  [void]$md.AppendLine(('- Device: `{0}`' -f $DeviceId))
  [void]$md.AppendLine(('- Flavor: `{0}`' -f $Flavor))
  [void]$md.AppendLine(('- Package: `{0}`' -f $PackageName))
  [void]$md.AppendLine(('- Output Directory: `{0}`' -f $resolvedOutputDir))
  [void]$md.AppendLine("")
  [void]$md.AppendLine("| Test | Status | Duration (s) | Log |")
  [void]$md.AppendLine("| --- | --- | ---: | --- |")
  foreach ($result in $results) {
    $logName = Split-Path -Leaf $result.LogPath
    [void]$md.AppendLine(('| {0} | {1} | {2} | `{3}` |' -f $result.Name, $result.Status, $result.DurationSeconds, $logName))
  }
  foreach ($result in $results) {
    [void]$md.AppendLine("")
    [void]$md.AppendLine("## $($result.Name)")
    [void]$md.AppendLine("")
    [void]$md.AppendLine(('- Target: `{0}`' -f $result.Target))
    [void]$md.AppendLine(('- Status: `{0}`' -f $result.Status))
    [void]$md.AppendLine(('- Duration: `{0}s`' -f $result.DurationSeconds))
    [void]$md.AppendLine(('- Command: ``{0}``' -f $result.Command))
    [void]$md.AppendLine(('- Log: `{0}`' -f $result.LogPath))
    if ($result.Highlights.Count -gt 0) {
      [void]$md.AppendLine("- Highlights:")
      foreach ($highlight in $result.Highlights) {
        [void]$md.AppendLine("  - $highlight")
      }
    }
  }
  $md.ToString() | Set-Content -LiteralPath $mdPath

  Write-Host ""
  Write-Host "Performance test report written to:"
  Write-Host "  $jsonPath"
  Write-Host "  $mdPath"

  if (($results | Where-Object { $_.Status -eq "failed" }).Count -gt 0) {
    exit 1
  }
} finally {
  Pop-Location
}
