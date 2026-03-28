#!/bin/bash
set -e

echo "🚀 omi One-Click Deployment"
echo "=============================="

# Check dependencies
command -v docker >/dev/null 2>&1 || { echo "❌ Docker not installed. Install: https://docs.docker.com/get-docker/"; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { echo "❌ Docker Compose not installed. Install: https://docs.docker.com/compose/install/"; exit 1; }

# Create .env file if not exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file..."
    cat > .env << 'EOF'
# omi Configuration
# Get your API keys from respective services

# Firebase (Required)
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nYOUR_KEY\n-----END PRIVATE KEY-----\n"
FIREBASE_CLIENT_EMAIL=firebase-adminsdk@your-project.iam.gserviceaccount.com

# Pinecone (Required)
PINECONE_API_KEY=your-pinecone-api-key
PINECONE_INDEX_NAME=omi

# OpenAI (Required)
OPENAI_API_KEY=your-openai-api-key

# Redis (Auto-configured by Docker)
REDIS_URL=redis://redis:6379

# PostgreSQL (Auto-configured by Docker)
DATABASE_URL=postgresql://omi:omi@postgres:5432/omi
EOF
    echo "✅ .env created. Please edit with your API keys."
    exit 0
fi

# Start services
echo "🔧 Starting services..."
docker-compose up -d --build

# Wait for services
echo "⏳ Waiting for services..."
sleep 10

# Check health
echo "🏥 Checking service health..."
curl -f http://localhost:8080/health || echo "⚠️ Backend not responding"

echo ""
echo "✅ Deployment complete!"
echo "=============================="
echo "📱 Backend API: http://localhost:8080"
echo "📊 Redis: localhost:6379"
echo "🗄️ PostgreSQL: localhost:5432"
echo ""
echo "📝 Next steps:"
echo "1. Edit .env with your API keys"
echo "2. Restart: docker-compose restart backend"
echo "3. Check logs: docker-compose logs -f backend"
