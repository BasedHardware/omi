# Limitless Pendant Setup Verification Script
# Run this script to verify your environment is ready for Limitless pendant migration

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Limitless Pendant Setup Verification" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Flutter installation
Write-Host "Checking Flutter installation..." -ForegroundColor Yellow
try {
    $flutterVersion = flutter --version 2>&1 | Select-String "Flutter"
    if ($flutterVersion) {
        Write-Host "✓ Flutter is installed" -ForegroundColor Green
        Write-Host "  $flutterVersion" -ForegroundColor Gray
    } else {
        Write-Host "✗ Flutter not found" -ForegroundColor Red
        Write-Host "  Please install Flutter: https://docs.flutter.dev/get-started/install" -ForegroundColor Yellow
        exit 1
    }
} catch {
    Write-Host "✗ Flutter not found" -ForegroundColor Red
    Write-Host "  Please install Flutter: https://docs.flutter.dev/get-started/install" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Check if we're in the app directory
Write-Host "Checking directory structure..." -ForegroundColor Yellow
if (Test-Path "pubspec.yaml") {
    Write-Host "✓ In app directory" -ForegroundColor Green
} else {
    Write-Host "✗ Not in app directory" -ForegroundColor Red
    Write-Host "  Please run this script from the app/ directory" -ForegroundColor Yellow
    exit 1
}

# Check for Limitless connection file
if (Test-Path "lib/services/devices/limitless_connection.dart") {
    Write-Host "✓ Limitless connection implementation found" -ForegroundColor Green
} else {
    Write-Host "✗ Limitless connection file not found" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Check Flutter dependencies
Write-Host "Checking Flutter dependencies..." -ForegroundColor Yellow
if (Test-Path ".dart_tool/package_config.json") {
    Write-Host "✓ Dependencies appear to be installed" -ForegroundColor Green
    Write-Host "  Run 'flutter pub get' if you haven't already" -ForegroundColor Gray
} else {
    Write-Host "⚠ Dependencies not installed" -ForegroundColor Yellow
    Write-Host "  Run 'flutter pub get' to install dependencies" -ForegroundColor Yellow
}

Write-Host ""

# Check for environment file
Write-Host "Checking environment configuration..." -ForegroundColor Yellow
if (Test-Path ".dev.env") {
    Write-Host "✓ Development environment file found" -ForegroundColor Green
} else {
    Write-Host "⚠ .dev.env not found" -ForegroundColor Yellow
    Write-Host "  This will be created by setup.sh" -ForegroundColor Gray
}

Write-Host ""

# Summary
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Setup Verification Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Run: bash setup.sh android  (for Android)" -ForegroundColor White
Write-Host "   OR: bash setup.sh ios       (for iOS)" -ForegroundColor White
Write-Host "   OR: bash setup.sh macos    (for macOS)" -ForegroundColor White
Write-Host ""
Write-Host "2. Pair your Limitless pendant in the app" -ForegroundColor White
Write-Host ""
Write-Host "3. Start using real-time transcription!" -ForegroundColor White
Write-Host ""
Write-Host "For detailed instructions, see:" -ForegroundColor Gray
Write-Host "  - LIMITLESS_MIGRATION_GUIDE.md" -ForegroundColor Gray
Write-Host "  - LIMITLESS_SETUP.md" -ForegroundColor Gray
Write-Host ""

