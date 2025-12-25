# OMI Project PowerShell Profile
# This profile automatically loads when PowerShell starts in this directory
# To use: Add this line to your PowerShell profile:
#   if (Test-Path "$PSScriptRoot\.powershell_profile.ps1") { . "$PSScriptRoot\.powershell_profile.ps1" }

# Refresh PATH from Machine and User environment variables
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# Verify Chocolatey is available
if (Get-Command choco -ErrorAction SilentlyContinue) {
    Write-Host "[OMI] Chocolatey available" -ForegroundColor Green
} else {
    Write-Host "[OMI] Warning: Chocolatey not found in PATH" -ForegroundColor Yellow
}

