param()

$ErrorActionPreference = "Continue"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $RootDir

$PassCount = 0
$WarnCount = 0
$FailCount = 0
$ExpectedPythonVersion = if (Test-Path ".python-version") { (Get-Content ".python-version" -Raw).Trim() } else { "" }
$Script:PythonLauncher = $null
$Script:PythonLauncherName = $null
$Script:PythonLauncherArgs = @()

function Add-Pass {
    param([string]$Message)
    Write-Host "  OK    $Message" -ForegroundColor Green
    $script:PassCount += 1
}

function Add-Warn {
    param([string]$Message)
    Write-Host "  WARN  $Message" -ForegroundColor Yellow
    $script:WarnCount += 1
}

function Add-Fail {
    param([string]$Message)
    Write-Host "  FAIL  $Message" -ForegroundColor Red
    $script:FailCount += 1
}

function Invoke-SelectedPython {
    param([string[]]$Arguments)
    $allArgs = @()
    $allArgs += $Script:PythonLauncherArgs
    $allArgs += $Arguments
    & $Script:PythonLauncher @allArgs
}

function Invoke-PythonCandidate {
    param(
        [pscustomobject]$Candidate,
        [string[]]$Arguments
    )
    $allArgs = @()
    $allArgs += $Candidate.Args
    $allArgs += $Arguments
    & $Candidate.Command @allArgs
}

function Test-PythonCandidate {
    param(
        [pscustomobject]$Candidate,
        [string[]]$Arguments
    )
    try {
        Invoke-PythonCandidate $Candidate $Arguments *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

try {

Write-Host "Tools:"

$pythonCandidates = @()
if ($env:PYTHON) {
    $pythonEnvCommand = Get-Command $env:PYTHON -ErrorAction SilentlyContinue
    if ($pythonEnvCommand) {
        $pythonCandidates += [pscustomobject]@{ Name = $env:PYTHON; Command = $pythonEnvCommand.Source; Args = @() }
    }
}
foreach ($commandName in @("python3", "python")) {
    $command = Get-Command $commandName -ErrorAction SilentlyContinue
    if ($command) {
        $pythonCandidates += [pscustomobject]@{ Name = $commandName; Command = $command.Source; Args = @() }
    }
}
$pyCommand = Get-Command py -ErrorAction SilentlyContinue
if ($pyCommand) {
    $pythonCandidates += [pscustomobject]@{ Name = "py -3"; Command = $pyCommand.Source; Args = @("-3") }
}

$firstRunnablePython = $null
foreach ($candidate in $pythonCandidates) {
    if (-not (Test-PythonCandidate $candidate @("-c", "import sys"))) {
        continue
    }
    if (-not $firstRunnablePython) {
        $firstRunnablePython = $candidate
    }
    if (Test-PythonCandidate $candidate @("-m", "pytest", "--version")) {
        $Script:PythonLauncher = $candidate.Command
        $Script:PythonLauncherName = $candidate.Name
        $Script:PythonLauncherArgs = $candidate.Args
        break
    }
}

if (-not $Script:PythonLauncher -and $firstRunnablePython) {
    $Script:PythonLauncher = $firstRunnablePython.Command
    $Script:PythonLauncherName = $firstRunnablePython.Name
    $Script:PythonLauncherArgs = $firstRunnablePython.Args
}

if ($Script:PythonLauncher) {
    if (-not $Script:PythonLauncherName) {
        $Script:PythonLauncherName = $Script:PythonLauncher
    }
    $pythonVersionOutput = Invoke-SelectedPython @("--version") 2>&1
    $pythonVersion = (($pythonVersionOutput -join " ").Trim() -replace "^Python\s+", "")
    Add-Pass "$Script:PythonLauncherName $pythonVersion"
    if ($ExpectedPythonVersion) {
        if ($pythonVersion -eq $ExpectedPythonVersion) {
            Add-Pass "Python version matches .python-version ($ExpectedPythonVersion)"
        } else {
            Add-Fail "Python version mismatch: expected $ExpectedPythonVersion from .python-version, got $pythonVersion from $Script:PythonLauncherName"
            Write-Host "  -> Run: bash ./scripts/sync-python-deps.sh, then `$env:PYTHON = '.\.venv\Scripts\python.exe'; powershell -NoProfile -ExecutionPolicy Bypass -File .\test-preflight.ps1" -ForegroundColor Yellow
        }
    }
} else {
    Add-Fail "python not found"
}

if ($Script:PythonLauncher) {
    $pytestOutput = Invoke-SelectedPython @("-m", "pytest", "--version") 2>$null
    if ($LASTEXITCODE -eq 0) {
        Add-Pass $pytestOutput
    } else {
        Add-Fail "pytest not installed (python -m pip install pytest)"
    }
} else {
    Add-Fail "pytest not checked because python is missing"
}

if (Get-Command black -ErrorAction SilentlyContinue) {
    Add-Pass "black (formatter)"
} else {
    Add-Warn "black not installed - pre-commit hook will fail (pip install black)"
}

Write-Host ""
Write-Host "Python packages:"

$missingPackages = @()
foreach ($pkg in @("pydantic", "fastapi", "firebase_admin", "google.cloud.firestore", "redis", "deepgram", "openpipe", "pytest_asyncio", "fake_firestore", "fakeredis")) {
    if (-not $Script:PythonLauncher) {
        $missingPackages += $pkg
        Add-Warn "$pkg not checked because python is missing"
        continue
    }

    Invoke-SelectedPython @("-c", "import $pkg") *> $null
    if ($LASTEXITCODE -eq 0) {
        Add-Pass $pkg
    } else {
        $missingPackages += $pkg
        Add-Warn "$pkg not importable"
    }
}

if ($missingPackages.Count -gt 0) {
    $pythonPip = if ($Script:PythonLauncherName) { $Script:PythonLauncherName } else { "python" }
    Write-Host "  -> Run: $pythonPip -m pip install -r requirements.txt" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Env vars (unit tests):"

if ($env:ENCRYPTION_SECRET) {
    Add-Pass "ENCRYPTION_SECRET (set in env)"
} else {
    Add-Pass "ENCRYPTION_SECRET (set by test.sh - no action needed)"
}

Write-Host ""
Write-Host "Env vars (integration - optional):"

function Test-OptionalEnv {
    param(
        [string]$Name,
        [string]$Description
    )
    if ([Environment]::GetEnvironmentVariable($Name)) {
        Add-Pass "$Name ($Description)"
    } else {
        Add-Warn "$Name not set ($Description)"
    }
}

Test-OptionalEnv "OPENAI_API_KEY" "LLM calls - some integration tests skip without it"
Test-OptionalEnv "DEEPGRAM_API_KEY" "STT streaming and pre-recorded transcription"
Test-OptionalEnv "ADMIN_KEY" "admin endpoint tests"
Test-OptionalEnv "REDIS_DB_HOST" "Redis connection (default: localhost)"
Test-OptionalEnv "REDIS_DB_PASSWORD" "Redis auth"
Test-OptionalEnv "GOOGLE_APPLICATION_CREDENTIALS" "Firebase/Firestore integration tests"

Write-Host ""
Write-Host "Services:"

$redisCli = Get-Command redis-cli -ErrorAction SilentlyContinue
if ($redisCli) {
    $redisHost = if ($env:REDIS_DB_HOST) { $env:REDIS_DB_HOST } else { "localhost" }
    $redisPort = if ($env:REDIS_DB_PORT) { $env:REDIS_DB_PORT } else { "6379" }
    $redisArgs = @("-h", $redisHost, "-p", $redisPort)
    if ($env:REDIS_DB_PASSWORD) {
        $redisArgs += @("-a", $env:REDIS_DB_PASSWORD)
    }
    $redisArgs += "ping"

    & $redisCli.Source @redisArgs *> $null
    if ($LASTEXITCODE -eq 0) {
        Add-Pass "Redis ($redisHost`:$redisPort) - connected"
    } else {
        Add-Warn "Redis ($redisHost`:$redisPort) - not reachable (integration tests may fail)"
    }
} else {
    Add-Warn "redis-cli not installed - cannot check Redis connectivity"
}

Write-Host ""
Write-Host "Test files:"

$unitTests = @(Get-ChildItem -Path "tests/unit" -Filter "test_*.py" -Recurse -ErrorAction SilentlyContinue)
if ($unitTests.Count -gt 0) {
    Add-Pass "$($unitTests.Count) unit test files found"
} else {
    Add-Fail "No unit test files found in tests/unit/"
}

$selectedTestsPath = Join-Path ([System.IO.Path]::GetTempPath()) "backend-unit-tests-preflight.txt"
if ($Script:PythonLauncher) {
    Invoke-SelectedPython @("scripts/select_backend_unit_tests.py", "--all") > $selectedTestsPath
    if ($LASTEXITCODE -eq 0) {
        $selectedTestCount = @(Get-Content $selectedTestsPath -ErrorAction SilentlyContinue).Count
        Add-Pass "$selectedTestCount backend unit test files selected"
    } else {
        Add-Fail "backend unit test selection failed"
    }
} else {
    Add-Fail "backend unit test selection skipped because python is missing"
}

if ($Script:PythonLauncher) {
    Invoke-SelectedPython @("scripts/export_openapi.py", "--help") *> $null
    if ($LASTEXITCODE -eq 0) {
        Add-Pass "OpenAPI export script is runnable"
    } else {
        Add-Fail "OpenAPI export script failed to start"
    }
} else {
    Add-Fail "OpenAPI export script check skipped because python is missing"
}

Write-Host ""
Write-Host "Summary:"
$total = $PassCount + $WarnCount + $FailCount
Write-Host "  $PassCount passed  $WarnCount warnings  $FailCount failed  ($total checks)"

if ($FailCount -gt 0) {
    Write-Host "  Fix failures above before running test.sh" -ForegroundColor Red
    exit 1
}

if ($WarnCount -gt 0) {
    Write-Host "  Warnings are optional - unit tests should still pass" -ForegroundColor Yellow
    exit 0
}

Write-Host "  All clear - ready to run test.sh" -ForegroundColor Green
exit 0

} finally {
    Pop-Location
}
