#!/usr/bin/env bash
# install.sh — One-click Omi backend deployment
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/.../install.sh | bash
#   OR
#   cd backend && bash scripts/install.sh
#
# Prerequisites: Docker + Docker Compose v2
#
# This script:
#   1. Checks for Docker and Docker Compose
#   2. Creates .env from template if missing
#   3. Prompts for required API keys
#   4. Starts all services with docker compose
#   5. Waits for health checks to pass
#   6. Prints status and API docs URL

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     Omi Backend — One-Click Deploy       ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""

# ── Check prerequisites ──
echo -e "${CYAN}Checking prerequisites...${NC}"

if ! command -v docker &>/dev/null; then
    echo -e "${RED}✗ Docker not found. Install: https://docs.docker.com/get-docker/${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} Docker $(docker --version | awk '{print $3}' | tr -d ',')"

if ! docker compose version &>/dev/null 2>&1; then
    echo -e "${RED}✗ Docker Compose v2 not found. Install: https://docs.docker.com/compose/install/${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} $(docker compose version | head -1)"

if ! docker info &>/dev/null 2>&1; then
    echo -e "${RED}✗ Docker daemon not running. Start Docker Desktop or run: sudo systemctl start docker${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} Docker daemon running"
echo ""

# ── Setup .env ──
cd "$BACKEND_DIR"

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "${YELLOW}Created .env from .env.example template${NC}"
    elif [ -f .env.template ]; then
        cp .env.template .env
        echo -e "${YELLOW}Created .env from .env.template${NC}"
    else
        echo -e "${RED}✗ No .env template found${NC}"
        exit 1
    fi

    echo ""
    echo -e "${CYAN}Required API keys (press Enter to skip optional ones):${NC}"
    echo ""

    # Prompt for required keys
    read -rp "  GCP Service Account JSON (single line): " sa_json
    if [ -n "$sa_json" ]; then
        sed -i.bak "s|^SERVICE_ACCOUNT_JSON=.*|SERVICE_ACCOUNT_JSON=$sa_json|" .env
    fi

    read -rp "  Firebase API Key: " fb_key
    if [ -n "$fb_key" ]; then
        sed -i.bak "s|^FIREBASE_API_KEY=.*|FIREBASE_API_KEY=$fb_key|" .env
    fi

    read -rp "  Firebase Project ID: " fb_project
    if [ -n "$fb_project" ]; then
        sed -i.bak "s|^FIREBASE_PROJECT_ID=.*|FIREBASE_PROJECT_ID=$fb_project|" .env
    fi

    read -rp "  OpenAI API Key (for LLM): " openai_key
    if [ -n "$openai_key" ]; then
        sed -i.bak "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=$openai_key|" .env
    fi

    read -rp "  Deepgram API Key (for STT): " dg_key
    if [ -n "$dg_key" ]; then
        sed -i.bak "s|^DEEPGRAM_API_KEY=.*|DEEPGRAM_API_KEY=$dg_key|" .env
    fi

    rm -f .env.bak
    echo ""
    echo -e "${GREEN}✓${NC} Environment configured"
else
    echo -e "${GREEN}✓${NC} Using existing .env file"
fi
echo ""

# ── Start services ──
echo -e "${CYAN}Starting services...${NC}"
docker compose up -d --build

echo ""
echo -e "${CYAN}Waiting for services to be healthy...${NC}"

# Wait up to 120 seconds for backend to be healthy
for i in $(seq 1 24); do
    if docker compose ps --format json 2>/dev/null | python3 -c "
import json, sys
services = [json.loads(line) for line in sys.stdin if line.strip()]
all_running = all(s.get('State') == 'running' for s in services)
sys.exit(0 if all_running and len(services) >= 3 else 1)
" 2>/dev/null; then
        break
    fi
    echo -n "."
    sleep 5
done
echo ""

# ── Status ──
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║           Service Status                 ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""
docker compose ps
echo ""

# Check if backend is responding
if curl -sf http://localhost:8080/ &>/dev/null; then
    echo -e "${GREEN}✓ Backend is running!${NC}"
    echo ""
    echo -e "  API Docs:  ${CYAN}http://localhost:8080/docs${NC}"
    echo -e "  Health:    ${CYAN}http://localhost:8080/${NC}"
    echo -e "  Redis:     ${CYAN}localhost:6379${NC}"
    echo -e "  Typesense: ${CYAN}localhost:8108${NC}"
else
    echo -e "${YELLOW}⚠ Backend is starting up — check logs with: docker compose logs -f backend${NC}"
fi

echo ""
echo -e "${CYAN}Commands:${NC}"
echo "  docker compose logs -f          # Follow all logs"
echo "  docker compose logs -f backend  # Follow backend logs"
echo "  docker compose down             # Stop all services"
echo "  docker compose restart backend  # Restart backend only"
echo ""
