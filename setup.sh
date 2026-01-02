#!/bin/bash

# Omi One-Click Setup Script
# Designed for backend developers and customers with low technical expertise.

set -e

echo "=========================================="
echo "   🚀 Omi One-Click Setup (Docker)   "
echo "=========================================="

# Check for Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Error: Docker is not installed. Please install Docker first: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check for Docker Compose
if ! docker compose version &> /dev/null; then
    echo "❌ Error: Docker Compose is not installed. Please install it or use a newer version of Docker Desktop."
    exit 1
fi

# Create .env if it doesn't exist
if [ ! -f .env ]; then
    echo "📄 Creating .env from .env.example..."
    cp .env.example .env
    
    # Generate secure random secrets
    ADMIN_KEY=$(openssl rand -hex 32)
    ENCRYPTION_SECRET=$(openssl rand -hex 32)
    
    # Update .env with generated secrets
    sed -i "s/ADMIN_KEY=.*/ADMIN_KEY=$ADMIN_KEY/" .env
    sed -i "s/ENCRYPTION_SECRET=.*/ENCRYPTION_SECRET=$ENCRYPTION_SECRET/" .env
    
    echo "✅ Generated secure random keys for ADMIN_KEY and ENCRYPTION_SECRET."
    echo "⚠️  Action Required: Please edit the .env file and add your API keys."
    echo "   At minimum, you need: DEEPGRAM_API_KEY and OPENAI_API_KEY."
    
    # Optional: try to open the editor
    if command -v nano &> /dev/null; then
        read -p "Would you like to edit .env now? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            nano .env
        fi
    fi
fi

# Build and Start
echo "🛠️  Building and starting Omi services..."
docker compose up -d --build

echo ""
echo "=========================================="
echo "✅ Omi is now starting up!"
echo ""
echo "Services available at:"
echo "👉 Frontend: http://localhost:3000"
echo "👉 Backend:  http://localhost:8080"
echo "👉 Pusher:   http://localhost:8081"
echo ""
echo "To view logs, run: docker compose logs -f"
echo "To stop Omi, run:  docker compose down"
echo "=========================================="
