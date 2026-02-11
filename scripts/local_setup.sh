#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "============================================"
echo "  Omi Local Development Setup"
echo "============================================"
echo

# Check prerequisites
if ! command -v docker &> /dev/null; then
    echo "ERROR: docker is not installed. Please install Docker Desktop."
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo "ERROR: docker compose is not available. Please install Docker Compose V2."
    exit 1
fi

# Create .env.local from template if it doesn't exist
if [ ! -f backend/.env.local ]; then
    if [ -f backend/.env.docker ]; then
        cp backend/.env.docker backend/.env.local
        echo "Created backend/.env.local from template."
    else
        echo "ERROR: backend/.env.docker not found."
        exit 1
    fi
fi

# Check for OpenAI API key
OPENAI_KEY=$(grep '^OPENAI_API_KEY=' backend/.env.local | cut -d'=' -f2)
if [ -z "$OPENAI_KEY" ]; then
    echo "WARNING: OPENAI_API_KEY is not set in backend/.env.local"
    echo "  LLM features will not work without it."
    echo "  Edit backend/.env.local and add your OpenAI API key."
    echo
fi

# Build and start services
echo "[1/4] Building and starting services..."
docker compose up -d --build

# Wait for health checks
echo "[2/4] Waiting for services to be healthy..."
echo -n "  Waiting..."
TIMEOUT=120
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    HEALTHY=$(docker compose ps --format json 2>/dev/null | python3 -c "
import sys, json
healthy = 0
total = 0
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    svc = json.loads(line)
    total += 1
    status = svc.get('Health', svc.get('State', ''))
    if 'healthy' in status.lower() or svc.get('State') == 'running':
        healthy += 1
print(f'{healthy}/{total}')
" 2>/dev/null || echo "0/0")
    if [[ "$HEALTHY" == "5/5" ]] || [[ "$HEALTHY" == "4/4" ]]; then
        echo " done!"
        break
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    echo -n "."
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    echo
    echo "WARNING: Timed out waiting for all services. Checking status..."
    docker compose ps
    echo
    echo "Some services may still be starting. Check 'docker compose logs <service>' for details."
fi

# Initialize Typesense collections
echo "[3/4] Initializing Typesense collections..."
python3 scripts/init_typesense.py

# Seed test data
echo "[4/4] Creating test user..."
python3 scripts/seed_local.py

echo
echo "============================================"
echo "  Services Running"
echo "============================================"
echo "  Backend API:        http://localhost:8080"
echo "  Firebase Emulator:  http://localhost:4000"
echo "  Firestore:          localhost:8081"
echo "  Firebase Auth:      localhost:9099"
echo "  Firebase Storage:   localhost:9199"
echo "  Redis:              localhost:6379"
echo "  Typesense:          http://localhost:8108"
echo "  Qdrant:             http://localhost:6333"
echo "  Qdrant Dashboard:   http://localhost:6334/dashboard"
echo "============================================"
echo
echo "To stop: docker compose down"
echo "To view logs: docker compose logs -f omi-backend"
