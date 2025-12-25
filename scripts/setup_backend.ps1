# OMI Backend Setup Script
# Automates backend setup steps

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "OMI Backend Setup Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if in backend directory
if (-not (Test-Path "main.py")) {
    Write-Host "✗ Error: Not in backend directory" -ForegroundColor Red
    Write-Host "  Please run this script from the backend/ directory" -ForegroundColor Yellow
    exit 1
}

# Step 1: Create virtual environment
Write-Host "Step 1: Creating virtual environment..." -ForegroundColor Yellow
if (Test-Path "venv") {
    Write-Host "⚠ Virtual environment already exists" -ForegroundColor Yellow
    $response = Read-Host "Recreate? (y/N)"
    if ($response -eq "y" -or $response -eq "Y") {
        Remove-Item -Recurse -Force venv
        python -m venv venv
        Write-Host "✓ Virtual environment created" -ForegroundColor Green
    }
} else {
    python -m venv venv
    Write-Host "✓ Virtual environment created" -ForegroundColor Green
}

Write-Host ""

# Step 2: Activate and upgrade pip
Write-Host "Step 2: Activating virtual environment and upgrading pip..." -ForegroundColor Yellow
& .\venv\Scripts\activate
python -m pip install --upgrade pip
Write-Host "✓ Pip upgraded" -ForegroundColor Green

Write-Host ""

# Step 3: Install dependencies
Write-Host "Step 3: Installing Python dependencies..." -ForegroundColor Yellow
Write-Host "  This may take 10-15 minutes..." -ForegroundColor Gray
pip install -r requirements.txt
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Dependencies installed" -ForegroundColor Green
} else {
    Write-Host "✗ Failed to install dependencies" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 4: Create .env file if it doesn't exist
Write-Host "Step 4: Checking .env file..." -ForegroundColor Yellow
if (Test-Path ".env") {
    Write-Host "✓ .env file already exists" -ForegroundColor Green
    Write-Host "  Make sure all required keys are filled in!" -ForegroundColor Yellow
} else {
    if (Test-Path "env.template") {
        Copy-Item "env.template" ".env"
        Write-Host "✓ Created .env from template" -ForegroundColor Green
        Write-Host "  ⚠ IMPORTANT: Edit .env and fill in your API keys!" -ForegroundColor Yellow
    } else {
        Write-Host "⚠ env.template not found" -ForegroundColor Yellow
        Write-Host "  Please create .env manually with your API keys" -ForegroundColor Yellow
        Write-Host "  See SELF_HOSTING_GUIDE.md for required keys" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Edit .env file and add your API keys" -ForegroundColor White
Write-Host "2. Configure Google Cloud: gcloud auth application-default login" -ForegroundColor White
Write-Host "3. Start ngrok: ngrok http --domain=YOUR_DOMAIN.ngrok-free.app 8000" -ForegroundColor White
Write-Host "4. Start backend: uvicorn main:app --reload --env-file .env" -ForegroundColor White
Write-Host ""
Write-Host "For detailed instructions, see: SELF_HOSTING_GUIDE.md" -ForegroundColor Gray
Write-Host ""

