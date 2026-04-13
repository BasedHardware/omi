#!/bin/bash
set -e

# ================================================================
# Omi Backend — One-Click Deployment Script
# ================================================================

RED='[0;31m'; GREEN='[0;32m'; YELLOW='[1;33m'; NC='[0m'
info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Detect docker compose (v2 plugin preferred, fall back to v1 standalone)
if docker compose version &>/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
elif docker-compose version &>/dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose"
else
    error "Docker Compose not found. Install Docker Desktop or the compose plugin."
fi

info "Using: $DOCKER_COMPOSE"

# Check Docker is running
docker info &>/dev/null 2>&1 || error "Docker daemon is not running. Please start Docker."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
cd "$BACKEND_DIR"

# ---- Create .env.docker from template if not present ---------
if [ ! -f ".env.docker" ]; then
    warn ".env.docker not found. Creating from template..."
    cp "$(dirname "$SCRIPT_DIR")/../backend/.env.docker" .env.docker 2>/dev/null || \
    cp .env.docker .env.docker 2>/dev/null || true

    # Generate secure random keys
    if command -v openssl &>/dev/null; then
        ADMIN_KEY=$(openssl rand -hex 32)
        sed -i.bak "s/^ADMIN_KEY=$/ADMIN_KEY=$ADMIN_KEY/" .env.docker && rm -f .env.docker.bak
        info "Generated secure ADMIN_KEY"
    fi

    echo ""
    warn "============================================================"
    warn " ACTION REQUIRED: Fill in your API keys in .env.docker"
    warn " Required keys: FIREBASE (SERVICE_ACCOUNT_JSON), OPENAI_API_KEY,"
    warn "                DEEPGRAM_API_KEY, PINECONE_API_KEY"
    warn "============================================================"
    echo ""
    read -p "Press Enter once you have filled in .env.docker to continue, or Ctrl+C to exit: "
fi

# ---- Validate critical env vars ------------------------------
source .env.docker 2>/dev/null || true

missing=()
[ -z "$OPENAI_API_KEY" ]      && missing+=("OPENAI_API_KEY")
[ -z "$DEEPGRAM_API_KEY" ]    && missing+=("DEEPGRAM_API_KEY")
[ -z "$PINECONE_API_KEY" ]    && missing+=("PINECONE_API_KEY")
[ -z "$SERVICE_ACCOUNT_JSON" ] && [ -z "$FIREBASE_PROJECT_ID" ] && missing+=("SERVICE_ACCOUNT_JSON or FIREBASE_PROJECT_ID")

if [ ${#missing[@]} -gt 0 ]; then
    warn "The following keys are not set (some features will be disabled):"
    for key in "${missing[@]}"; do
        warn "  - $key"
    done
    echo ""
    read -p "Continue anyway? [y/N]: " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || exit 1
fi

# ---- Build and start -----------------------------------------
info "Building and starting services..."
$DOCKER_COMPOSE -f docker-compose.yaml up -d --build

# ---- Wait for backend health check ---------------------------
info "Waiting for backend to be ready..."
max_attempts=30
attempt=0
until curl -sf http://localhost:8080/v1/health &>/dev/null; do
    attempt=$((attempt + 1))
    if [ $attempt -ge $max_attempts ]; then
        warn "Backend health check timed out. Check logs:"
        $DOCKER_COMPOSE -f docker-compose.yaml logs backend --tail=50
        exit 1
    fi
    echo -n "."
    sleep 3
done
echo ""

# ---- Done ---------------------------------------------------
info "================================================"
info " Omi backend is running!"
info "================================================"
info " API:       http://localhost:8080"
info " Health:    http://localhost:8080/v1/health"
info " Redis:     localhost:6379"
info " Typesense: localhost:8108"
info ""
info " Logs:  $DOCKER_COMPOSE -f docker-compose.yaml logs -f"
info " Stop:  $DOCKER_COMPOSE -f docker-compose.yaml down"
info "================================================"
