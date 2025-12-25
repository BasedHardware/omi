# OMI Project Initialization Script
# Ensures Chocolatey and other tools are available in PATH
# Run this script at the start of each PowerShell session: . .\init-project.ps1

Write-Host "Initializing OMI project environment..." -ForegroundColor Cyan

# Refresh PATH from Machine and User environment variables
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# Verify Chocolatey is available
if (Get-Command choco -ErrorAction SilentlyContinue) {
    $chocoVersion = choco --version
    Write-Host "✓ Chocolatey available (version $chocoVersion)" -ForegroundColor Green
} else {
    Write-Host "⚠ Chocolatey not found in PATH" -ForegroundColor Yellow
    Write-Host "  Chocolatey should be installed at: C:\ProgramData\chocolatey\bin" -ForegroundColor Yellow
}

# Verify other common tools
$tools = @("python", "git", "node")
foreach ($tool in $tools) {
    if (Get-Command $tool -ErrorAction SilentlyContinue) {
        Write-Host "✓ $tool available" -ForegroundColor Green
    } else {
        Write-Host "⚠ $tool not found" -ForegroundColor Yellow
    }
}

Write-Host "Environment initialized!" -ForegroundColor Cyan

