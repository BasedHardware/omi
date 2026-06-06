param(
    [string]$Python
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RootDir

$script:PassCount = 0
$script:WarnCount = 0
$script:FailCount = 0
$script:PythonCommand = @()

function Write-Ok {
    param([string]$Message)
    Write-Host "  [OK] $Message" -ForegroundColor Green
    $script:PassCount += 1
}

function Write-Warn {
    param([string]$Message)
    Write-Host "  [WARN] $Message" -ForegroundColor Yellow
    $script:WarnCount += 1
}

function Write-Bad {
    param([string]$Message)
    Write-Host "  [FAIL] $Message" -ForegroundColor Red
    $script:FailCount += 1
}

function Set-PythonCommand {
    if ($Python) {
        $script:PythonCommand = @($Python)
        return
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        $script:PythonCommand = @("python")
        return
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        $script:PythonCommand = @("py", "-3")
        return
    }
}

function Invoke-Python {
    param([string[]]$Arguments)

    $exe = $script:PythonCommand[0]
    $prefix = @()
    if ($script:PythonCommand.Count -gt 1) {
        $prefix = $script:PythonCommand[1..($script:PythonCommand.Count - 1)]
    }

    $oldErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $exe @prefix @Arguments
    } finally {
        $ErrorActionPreference = $oldErrorActionPreference
    }
}

function Test-PythonImport {
    param([string]$ModuleName)

    Invoke-Python @("-c", "import $ModuleName") *> $null
    return $LASTEXITCODE -eq 0
}

function Get-EnvValue {
    param([string]$Name)
    return [Environment]::GetEnvironmentVariable($Name)
}

function Check-Env {
    param(
        [string]$Name,
        [string]$Description
    )

    if (Get-EnvValue $Name) {
        Write-Ok "$Name ($Description)"
    } else {
        Write-Warn "$Name not set ($Description)"
    }
}

Write-Host "Tools:"
Set-PythonCommand

if ($script:PythonCommand.Count -eq 0) {
    Write-Bad "python not found (install Python 3.11 or pass -Python <path>)"
} else {
    $pythonVersion = (Invoke-Python @("--version") 2>&1) -join " "
    if ($LASTEXITCODE -eq 0) {
        if ($pythonVersion -match "Python 3\.11\.") {
            Write-Ok $pythonVersion
        } else {
            Write-Warn "$pythonVersion detected; backend expects Python 3.11"
        }
    } else {
        Write-Bad "python command failed"
    }
}

if ($script:PythonCommand.Count -gt 0) {
    $pytestVersion = (Invoke-Python @("-m", "pytest", "--version") 2>&1) -join " "
    if ($LASTEXITCODE -eq 0) {
        Write-Ok $pytestVersion
    } else {
        Write-Bad "pytest not installed (pip install pytest)"
    }
}

if (Get-Command black -ErrorAction SilentlyContinue) {
    Write-Ok "black (formatter)"
} elseif ($script:PythonCommand.Count -gt 0) {
    Invoke-Python @("-m", "black", "--version") *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "python -m black (formatter)"
    } else {
        Write-Warn "black not installed; pre-commit formatting will fail (pip install black)"
    }
} else {
    Write-Warn "black not checked because python was not found"
}

Write-Host ""
Write-Host "Python packages:"

$missingPackages = @()
if ($script:PythonCommand.Count -gt 0) {
    foreach ($pkg in @("pydantic", "fastapi", "firebase_admin", "google.cloud.firestore", "redis", "deepgram_sdk", "openpipe")) {
        if (Test-PythonImport $pkg) {
            Write-Ok $pkg
        } else {
            $missingPackages += $pkg
            Write-Warn "$pkg not importable"
        }
    }
}

if ($missingPackages.Count -gt 0) {
    Write-Host "  -> Run: pip install -r requirements.txt" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Env vars (unit tests):"

if (Get-EnvValue "ENCRYPTION_SECRET") {
    Write-Ok "ENCRYPTION_SECRET (set in env)"
} else {
    Write-Ok "ENCRYPTION_SECRET (set by test.sh; no action needed)"
}

Write-Host ""
Write-Host "Env vars (integration - optional):"

Check-Env "OPENAI_API_KEY" "LLM calls; some integration tests skip without it"
Check-Env "DEEPGRAM_API_KEY" "STT streaming and pre-recorded transcription"
Check-Env "ADMIN_KEY" "admin endpoint tests"
Check-Env "REDIS_DB_HOST" "Redis connection (default: localhost)"
Check-Env "REDIS_DB_PASSWORD" "Redis auth"
Check-Env "GOOGLE_APPLICATION_CREDENTIALS" "Firebase/Firestore integration tests"

Write-Host ""
Write-Host "Services:"

$redisCli = Get-Command redis-cli -ErrorAction SilentlyContinue
if ($redisCli) {
    $redisHost = Get-EnvValue "REDIS_DB_HOST"
    if (-not $redisHost) {
        $redisHost = "localhost"
    }
    $redisPort = Get-EnvValue "REDIS_DB_PORT"
    if (-not $redisPort) {
        $redisPort = "6379"
    }

    $redisArgs = @("-h", $redisHost, "-p", $redisPort)
    $redisPassword = Get-EnvValue "REDIS_DB_PASSWORD"
    $redisArgs += "ping"

    $previousRedisCliAuth = [Environment]::GetEnvironmentVariable("REDISCLI_AUTH")
    if ($redisPassword) {
        $env:REDISCLI_AUTH = $redisPassword
    }

    try {
        & $redisCli.Source @redisArgs *> $null
    } finally {
        if ($null -eq $previousRedisCliAuth) {
            Remove-Item Env:REDISCLI_AUTH -ErrorAction SilentlyContinue
        } else {
            $env:REDISCLI_AUTH = $previousRedisCliAuth
        }
    }

    if ($LASTEXITCODE -eq 0) {
        Write-Ok "Redis ($redisHost`:$redisPort) connected"
    } else {
        Write-Warn "Redis ($redisHost`:$redisPort) not reachable (integration tests may fail)"
    }
} else {
    Write-Warn "redis-cli not installed; cannot check Redis connectivity"
}

Write-Host ""
Write-Host "Test files:"

$unitTests = Get-ChildItem -Path "tests/unit" -Filter "test_*.py" -File -ErrorAction SilentlyContinue
if ($unitTests.Count -gt 0) {
    Write-Ok "$($unitTests.Count) unit test files found"
} else {
    Write-Bad "No unit test files found in tests/unit/"
}

$missingTests = @()
if (Test-Path "test.sh") {
    $testRefs = Get-Content "test.sh" |
        ForEach-Object {
            $line = $_.Trim()
            if ($line -match "^pytest\s+") {
                $line -split "\s+" | Where-Object { $_ -like "tests/*" }
            }
        }

    foreach ($testRef in $testRefs) {
        if (-not (Test-Path $testRef)) {
            $missingTests += $testRef
        }
    }

    if ($missingTests.Count -gt 0) {
        Write-Bad "test.sh references missing files: $($missingTests -join ', ')"
    } else {
        Write-Ok "All test.sh references resolve to existing files"
    }
} else {
    Write-Bad "test.sh not found"
}

Write-Host ""
Write-Host "----------------------------------------"
$total = $script:PassCount + $script:WarnCount + $script:FailCount
Write-Host "  $script:PassCount passed  $script:WarnCount warnings  $script:FailCount failed  ($total checks)"

if ($script:FailCount -gt 0) {
    Write-Host "  Fix failures above before running test.sh" -ForegroundColor Red
    exit 1
}

if ($script:WarnCount -gt 0) {
    Write-Host "  Warnings are optional; unit tests should still pass" -ForegroundColor Yellow
    exit 0
}

Write-Host "  All clear; ready to run test.sh" -ForegroundColor Green
exit 0
