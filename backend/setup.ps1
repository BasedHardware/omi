#!/usr/bin/env pwsh

# Omi One-Click Setup Script for Windows (PowerShell)
# Designed for backend developers and customers with low technical expertise.

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "   🚀 Omi One-Click Setup (Docker)   " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# Check for Docker
if (-Not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Error: Docker is not installed. Please install Docker Desktop: https://docs.docker.com/get-docker/" -ForegroundColor Red
    exit 1
}

# Check for Docker Compose
if (-Not (Get-Command docker-compose -ErrorAction SilentlyContinue) -and -Not (Get-Command "docker compose" -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Error: Docker Compose is not installed. Please install Docker Desktop or ensure it's in your PATH." -ForegroundColor Red
    exit 1
}

# Create .env if it doesn't exist
if (-Not (Test-Path .env)) {
    Write-Host "📄 Creating .env from .env.example..." -ForegroundColor Yellow
    Copy-Item .env.example .env
    
    # Generate secure random secrets
    $ADMIN_KEY = [System.Convert]::ToHexString((Get-Random -Count 32 -Minimum 0 -Maximum 256 | ForEach-Object { [byte]$_ }))
    $ENCRYPTION_SECRET = [System.Convert]::ToHexString((Get-Random -Count 32 -Minimum 0 -Maximum 256 | ForEach-Object { [byte]$_ }))
    
    # Update .env with generated secrets
    (Get-Content .env) -replace "ADMIN_KEY=.*", "ADMIN_KEY=$ADMIN_KEY" | Set-Content .env
    (Get-Content .env) -replace "ENCRYPTION_SECRET=.*", "ENCRYPTION_SECRET=$ENCRYPTION_SECRET" | Set-Content .env
    
    Write-Host "✅ Generated secure random keys for ADMIN_KEY and ENCRYPTION_SECRET." -ForegroundColor Green
    Write-Host "⚠️  Action Required: Please edit the .env file and add your API keys." -ForegroundColor Yellow
    Write-Host "   At minimum, you need: DEEPGRAM_API_KEY and OPENAI_API_KEY." -ForegroundColor Yellow
    
    # Optional: try to open the editor (notepad for Windows)
    $response = Read-Host "Would you like to edit .env now? (y/n)"
    if ($response -eq "y" -or $response -eq "Y") {
        notepad .env
    }
}

# Build and Start
Write-Host "🛠️  Building and starting Omi services..." -ForegroundColor Blue
docker compose up -d --build

Write-Host "" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "✅ Omi is now starting up!" -ForegroundColor Green
Write-Host "" -ForegroundColor Cyan
Write-Host "Services available at:" -ForegroundColor Cyan
Write-Host "👉 Frontend: http://localhost:3000" -ForegroundColor Cyan
Write-Host "👉 Backend:  http://localhost:8080" -ForegroundColor Cyan
Write-Host "👉 Pusher:   http://localhost:8081" -ForegroundColor Cyan
Write-Host "" -ForegroundColor Cyan
Write-Host "To view logs, run: docker compose logs -f" -ForegroundColor DarkGray
Write-Host "To stop Omi, run:  docker compose down" -ForegroundColor DarkGray
Write-Host "==========================================" -ForegroundColor Cyan
