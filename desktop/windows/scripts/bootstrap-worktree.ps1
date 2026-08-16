# bootstrap-worktree.ps1 - make a fresh linked worktree ready to run the Windows
# app: install deps (native modules rebuild per worktree), ensure .env exists,
# build the UI-automation helper if the .NET SDK is present, and print the
# instance's derived ports + next steps.
#
# ASCII-only on purpose: Windows PowerShell 5.1 reads this no-BOM UTF-8 file, and
# non-ASCII bytes get misparsed. Keep it plain ASCII.
#
# Run from the worktree's desktop/windows:  pnpm bootstrap   (or)
#   powershell -ExecutionPolicy Bypass -File scripts/bootstrap-worktree.ps1
$ErrorActionPreference = 'Stop'
$win = Split-Path -Parent $PSScriptRoot   # scripts/.. = desktop/windows
Set-Location $win

function Say($msg)  { Write-Host "[bootstrap] $msg" }
function Warn($msg) { Write-Host "[bootstrap] $msg" -ForegroundColor Yellow }

# 1. Dependencies. Worktrees start with an empty node_modules and native modules
#    (better-sqlite3, koffi) must be rebuilt per worktree, so a plain copy won't do.
Say 'Installing dependencies (pnpm install - rebuilds native modules)...'
& pnpm install
if ($LASTEXITCODE -ne 0) { throw 'pnpm install failed' }

# 2. .env - the app will not start without it, and worktrees do not carry
#    gitignored files. Copy it from the primary checkout when missing.
if (Test-Path '.env') {
  Say '.env present.'
} else {
  Warn '.env missing - copying from the primary checkout...'
  $commonDir = (& git rev-parse --path-format=absolute --git-common-dir 2>$null)
  if (($LASTEXITCODE -eq 0) -and $commonDir) {
    $primaryRoot = Split-Path -Parent $commonDir
    $primaryEnv = Join-Path $primaryRoot 'desktop/windows/.env'
    if (Test-Path $primaryEnv) {
      Copy-Item $primaryEnv '.env'   # byte-for-byte; no BOM rewrite
      Say "Copied .env from $primaryEnv"
    } else {
      Warn "Primary .env not found at $primaryEnv - create desktop/windows/.env before running."
    }
  } else {
    Warn 'Could not locate the primary checkout (git --git-common-dir failed).'
  }
}

# 3. UI-automation helper (native Windows UIA). postinstall builds the OCR helper
#    but NOT this one; without it, UI automation is silently disabled at runtime.
$helperScript = Join-Path $win 'scripts/build-automation-helper.ps1'
$hasDotnet = $null -ne (Get-Command dotnet -ErrorAction SilentlyContinue)
if (-not (Test-Path $helperScript)) {
  Say 'No automation-helper build script in this checkout - skipping.'
} elseif (-not $hasDotnet) {
  Warn 'dotnet SDK not found - skipping the UI-automation helper (UI automation will be disabled).'
} else {
  Say 'Building the UI-automation helper...'
  try {
    & powershell -ExecutionPolicy Bypass -File $helperScript
    if ($LASTEXITCODE -ne 0) { Warn 'automation-helper build returned nonzero - UI automation may be disabled.' }
    else { Say 'Automation helper built.' }
  } catch {
    Warn "automation-helper build failed: $($_.Exception.Message)"
  }
}

# 4. Status summary.
Write-Host ''
Say 'Instance:'
& node scripts/print-instance.mjs --human
Write-Host ''
Say 'Next steps:'
Write-Host '   pnpm dev          # run this worktree (its own port + userData profile)'
Write-Host '   pnpm seed:auth    # optional: boot signed-in by copying the session from the primary app'
Write-Host '                     # (both apps must be running; see docs/multi-worktree-dev.md)'
