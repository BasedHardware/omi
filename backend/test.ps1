param(
    [string]$Python = "python",
    [switch]$List
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RootDir

$env:ENCRYPTION_SECRET = "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv"
$env:PYTHONUTF8 = "1"

if (-not (Test-Path "test.sh")) {
    Write-Error "test.sh not found"
}

$pytestCommands = Get-Content "test.sh" |
    Where-Object { $_ -match "^pytest\s+tests/unit/" } |
    ForEach-Object { $_.Trim() }

if ($pytestCommands.Count -eq 0) {
    Write-Error "No pytest commands found in test.sh"
}

if ($List) {
    $pytestCommands | ForEach-Object { Write-Output $_ }
    exit 0
}

foreach ($command in $pytestCommands) {
    $arguments = $command -split "\s+"
    Write-Host "> $Python -m $($arguments -join ' ')" -ForegroundColor Cyan
    & $Python -m @arguments
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

$redisCli = Get-Command redis-cli -ErrorAction SilentlyContinue
if ($redisCli) {
    & $redisCli.Source ping *> $null
    if ($LASTEXITCODE -eq 0) {
        foreach ($integrationTest in @(
            "tests/integration/test_fair_use_live.py",
            "tests/integration/test_fair_use_api.py"
        )) {
            Write-Host "> $Python -m pytest $integrationTest -v" -ForegroundColor Cyan
            & $Python -m pytest $integrationTest -v
            if ($LASTEXITCODE -ne 0) {
                exit $LASTEXITCODE
            }
        }
    } else {
        Write-Host "SKIP: fair-use integration tests (Redis not available)"
    }
} else {
    Write-Host "SKIP: fair-use integration tests (redis-cli not available)"
}
