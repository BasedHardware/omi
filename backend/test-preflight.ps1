param()

$ErrorActionPreference = "Continue"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $RootDir

$PassCount = 0
$WarnCount = 0
$FailCount = 0
$Script:PythonLauncher = $null

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
    if ($Script:PythonLauncher -eq "py") {
        & py -3 @Arguments
    } else {
        & $Script:PythonLauncher @Arguments
    }
}

try {

Write-Host "Tools:"

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand) {
    $Script:PythonLauncher = $pythonCommand.Source
    $pythonVersion = (& $Script:PythonLauncher --version 2>&1)
    Add-Pass "python $pythonVersion"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $Script:PythonLauncher = "py"
    $pythonVersion = (& py -3 --version 2>&1)
    Add-Pass "python $pythonVersion"
} else {
    Add-Fail "python not found"
}

if ($Script:PythonLauncher) {
    $pytestOutput = Invoke-SelectedPython @("-m", "pytest", "--version") 2>$null
    if ($LASTEXITCODE -eq 0) {
        Add-Pass $pytestOutput
    } else {
        Add-Fail "pytest not installed (pip install pytest)"
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
foreach ($pkg in @("pydantic", "fastapi", "firebase_admin", "google.cloud.firestore", "redis", "deepgram_sdk", "openpipe")) {
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
    Write-Host "  -> Run: pip install -r requirements.txt" -ForegroundColor Yellow
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

$missingTests = @()
if (Test-Path "test.sh") {
    foreach ($line in Get-Content "test.sh") {
        if ($line -match '^pytest\s+(tests/\S+)') {
            $testFile = $Matches[1]
            if (-not (Test-Path $testFile)) {
                $missingTests += $testFile
            }
        }
    }

    if ($missingTests.Count -gt 0) {
        Add-Fail "test.sh references missing files: $($missingTests -join ', ')"
    } else {
        Add-Pass "All test.sh references resolve to existing files"
    }
} else {
    Add-Fail "test.sh not found"
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
