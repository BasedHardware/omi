# OMI Backend Setup Verification Script
# Run this script to verify your backend environment is ready

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "OMI Backend Setup Verification" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$allGood = $true

# Check Python
Write-Host "Checking Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($pythonVersion -match "Python 3\.([8-9]|[1-9][0-9])") {
        Write-Host "✓ Python is installed: $pythonVersion" -ForegroundColor Green
    } else {
        Write-Host "✗ Python 3.8+ required. Found: $pythonVersion" -ForegroundColor Red
        $allGood = $false
    }
} catch {
    Write-Host "✗ Python not found. Install with: choco install python" -ForegroundColor Red
    $allGood = $false
}

Write-Host ""

# Check if in backend directory
Write-Host "Checking directory..." -ForegroundColor Yellow
if (Test-Path "main.py") {
    Write-Host "✓ In backend directory" -ForegroundColor Green
} else {
    Write-Host "✗ Not in backend directory" -ForegroundColor Red
    Write-Host "  Please run this script from the backend/ directory" -ForegroundColor Yellow
    $allGood = $false
}

Write-Host ""

# Check virtual environment
Write-Host "Checking virtual environment..." -ForegroundColor Yellow
if (Test-Path "venv") {
    Write-Host "✓ Virtual environment exists" -ForegroundColor Green
    if ($env:VIRTUAL_ENV) {
        Write-Host "✓ Virtual environment is activated" -ForegroundColor Green
    } else {
        Write-Host "⚠ Virtual environment exists but not activated" -ForegroundColor Yellow
        Write-Host "  Activate with: .\venv\Scripts\activate" -ForegroundColor Gray
    }
} else {
    Write-Host "⚠ Virtual environment not found" -ForegroundColor Yellow
    Write-Host "  Create with: python -m venv venv" -ForegroundColor Gray
}

Write-Host ""

# Check .env file
Write-Host "Checking .env file..." -ForegroundColor Yellow
if (Test-Path ".env") {
    Write-Host "✓ .env file exists" -ForegroundColor Green
    
    # Check for required keys
    $envContent = Get-Content ".env" -Raw
    $requiredKeys = @("OPENAI_API_KEY", "DEEPGRAM_API_KEY", "REDIS_DB_HOST", "PINECONE_API_KEY")
    $missingKeys = @()
    
    foreach ($key in $requiredKeys) {
        if ($envContent -notmatch "$key=") {
            $missingKeys += $key
        }
    }
    
    if ($missingKeys.Count -eq 0) {
        Write-Host "✓ All required keys found in .env" -ForegroundColor Green
    } else {
        Write-Host "✗ Missing keys in .env:" -ForegroundColor Red
        foreach ($key in $missingKeys) {
            Write-Host "  - $key" -ForegroundColor Red
        }
        $allGood = $false
    }
} else {
    Write-Host "✗ .env file not found" -ForegroundColor Red
    Write-Host "  Create from template: cp env.template .env" -ForegroundColor Yellow
    $allGood = $false
}

Write-Host ""

# Check dependencies
Write-Host "Checking Python dependencies..." -ForegroundColor Yellow
if (Test-Path "venv\Scripts\pip.exe") {
    Write-Host "✓ Virtual environment has pip" -ForegroundColor Green
    
    if (Test-Path "venv\Lib\site-packages\fastapi") {
        Write-Host "✓ Dependencies appear to be installed" -ForegroundColor Green
    } else {
        Write-Host "⚠ Dependencies may not be installed" -ForegroundColor Yellow
        Write-Host "  Install with: pip install -r requirements.txt" -ForegroundColor Gray
    }
} else {
    Write-Host "⚠ Cannot check dependencies (venv not set up)" -ForegroundColor Yellow
}

Write-Host ""

# Check gcloud
Write-Host "Checking Google Cloud SDK..." -ForegroundColor Yellow
try {
    $gcloudVersion = gcloud --version 2>&1 | Select-String "Google Cloud SDK"
    if ($gcloudVersion) {
        Write-Host "✓ Google Cloud SDK is installed" -ForegroundColor Green
        
        # Check authentication
        $authList = gcloud auth list 2>&1
        if ($authList -match "ACTIVE") {
            Write-Host "✓ Google Cloud is authenticated" -ForegroundColor Green
        } else {
            Write-Host "⚠ Google Cloud not authenticated" -ForegroundColor Yellow
            Write-Host "  Run: gcloud auth application-default login" -ForegroundColor Gray
        }
    }
} catch {
    Write-Host "⚠ Google Cloud SDK not found" -ForegroundColor Yellow
    Write-Host "  Install with: choco install gcloudsdk" -ForegroundColor Gray
}

Write-Host ""

# Check ngrok
Write-Host "Checking ngrok..." -ForegroundColor Yellow
try {
    $ngrokVersion = ngrok version 2>&1
    if ($ngrokVersion) {
        Write-Host "✓ ngrok is installed" -ForegroundColor Green
        
        # Check if configured
        $ngrokConfig = ngrok config check 2>&1
        if ($ngrokConfig -match "valid") {
            Write-Host "✓ ngrok is configured" -ForegroundColor Green
        } else {
            Write-Host "⚠ ngrok may not be configured" -ForegroundColor Yellow
            Write-Host "  Configure with: ngrok config add-authtoken YOUR_TOKEN" -ForegroundColor Gray
        }
    }
} catch {
    Write-Host "⚠ ngrok not found" -ForegroundColor Yellow
    Write-Host "  Install with: choco install ngrok" -ForegroundColor Gray
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($allGood) {
    Write-Host "✓ Setup looks good!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "1. Start ngrok: ngrok http --domain=YOUR_DOMAIN.ngrok-free.app 8000" -ForegroundColor White
    Write-Host "2. Activate venv: .\venv\Scripts\activate" -ForegroundColor White
    Write-Host "3. Start backend: uvicorn main:app --reload --env-file .env" -ForegroundColor White
} else {
    Write-Host "⚠ Some issues found - please fix them above" -ForegroundColor Yellow
}
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

