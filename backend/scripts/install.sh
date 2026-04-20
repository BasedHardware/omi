#!/bin/bash
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo "=================================="
echo " Omi Backend One-Click Deployment"
echo "=================================="

# Detect docker compose (v2 plugin first, fall back to v1 standalone)
if docker compose version &>/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
elif docker-compose version &>/dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose"
else
    error "Docker Compose not found. Install Docker Desktop: https://docs.docker.com/get-docker/"
fi
info "Docker Compose: $DOCKER_COMPOSE"

# Check Docker is running
docker info &>/dev/null 2>&1 || error "Docker daemon not running. Please start Docker."

# Navigate to backend directory (script lives in backend/scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
cd "$BACKEND_DIR"
info "Working directory: $BACKEND_DIR"

# Create .env.docker if missing
if [ ! -f ".env.docker" ]; then
    error ".env.docker not found in $BACKEND_DIR. See scripts/README.md for setup instructions."
fi

# Generate ADMIN_KEY if not set
if grep -q "^ADMIN_KEY=$" .env.docker 2>/dev/null; then
    if command -v openssl &>/dev/null; then
        GENERATED_KEY=$(openssl rand -hex 32)
        sed -i.bak "s/^ADMIN_KEY=$/ADMIN_KEY=$GENERATED_KEY/" .env.docker && rm -f .env.docker.bak
        info "Generated secure ADMIN_KEY"
    fi
fi

# Validate critical env vars
set -a; source .env.docker; set +a

missing=()
[ -z "${OPENAI_API_KEY:-}" ]       && missing+=("OPENAI_API_KEY")
[ -z "${DEEPGRAM_API_KEY:-}" ]     && missing+=("DEEPGRAM_API_KEY")
[ -z "${PINECONE_API_KEY:-}" ]     && missing+=("PINECONE_API_KEY")
[ -z "${SERVICE_ACCOUNT_JSON:-}" ] && missing+=("SERVICE_ACCOUNT_JSON")

if [ ${#missing[@]} -gt 0 ]; then
    warn "The following required keys are not set in .env.docker:"
    for key in "${missing[@]}"; do warn "  - $key"; done
    echo ""
    read -p "Continue anyway? Some features will not work. [y/N]: " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || exit 1
fi

# Build and start services
info "Building and starting services (this may take a few minutes on first run)..."
$DOCKER_COMPOSE -f docker-compose.yaml up -d --build

# Wait for backend health
info "Waiting for backend to be ready..."
max_attempts=40
attempt=0
until curl -sf http://localhost:8080/v1/health &>/dev/null; do
    attempt=$((attempt + 1))
    if [ $attempt -ge $max_attempts ]; then
        warn "Health check timed out after $((max_attempts * 3))s. Showing logs:"
        $DOCKER_COMPOSE -f docker-compose.yaml logs backend --tail=30
        exit 1
    fi
    printf "."
    sleep 3
done
echo ""

info "========================================="
info " Omi backend is running!"
info "========================================="
info " API:       http://localhost:8080"
info " Health:    http://localhost:8080/v1/health"
info " Typesense: http://localhost:8108"
info " Redis:     localhost:6379"
info ""
info " Logs:  $DOCKER_COMPOSE -f docker-compose.yaml logs -f"
info " Stop:  $DOCKER_COMPOSE -f docker-compose.yaml down"
info "========================================="
