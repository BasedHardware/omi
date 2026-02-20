#!/bin/bash
set -e

# Backend configuration
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TUNNEL_PID=""
BACKEND_PID=""
TUNNEL_URL="https://omi-dev.m13v.com"

# Cleanup function to stop backend and tunnel on exit
cleanup() {
    echo ""
    if [ -n "$TUNNEL_PID" ] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
        echo "Stopping tunnel (PID: $TUNNEL_PID)..."
        kill "$TUNNEL_PID" 2>/dev/null || true
    fi
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "Stopping backend (PID: $BACKEND_PID)..."
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# Kill existing instances
echo "Killing existing backend/tunnel instances..."
pkill -f "cloudflared.*omi-computer-dev" 2>/dev/null || true
lsof -ti:8080 | xargs kill -9 2>/dev/null || true
sleep 1

# Create .env if it doesn't exist (copy from Python backend or example)
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    if [ -f "$SCRIPT_DIR/../backend/.env" ]; then
        echo "Copying .env from Python backend..."
        cp "$SCRIPT_DIR/../backend/.env" "$SCRIPT_DIR/.env"
    elif [ -f "$SCRIPT_DIR/.env.example" ]; then
        echo "Copying .env.example to .env..."
        cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    else
        echo "Warning: No .env file found. Create one with required variables."
    fi
fi

# Symlink google-credentials.json if not present
if [ ! -f "$SCRIPT_DIR/google-credentials.json" ] && [ -f "$SCRIPT_DIR/../backend/google-credentials.json" ]; then
    echo "Symlinking google-credentials.json from Python backend..."
    ln -sf "$SCRIPT_DIR/../backend/google-credentials.json" "$SCRIPT_DIR/google-credentials.json"
fi

# Build the Rust backend
echo "Building Rust backend..."
cd "$SCRIPT_DIR"
cargo build --release

# Start Cloudflare tunnel
echo "Starting Cloudflare tunnel..."
cloudflared tunnel run omi-computer-dev &
TUNNEL_PID=$!
sleep 2

# Start Rust backend
echo "Starting Rust backend..."
./target/release/omi-desktop-backend &
BACKEND_PID=$!

# Wait for backend to be ready
echo "Waiting for backend to start..."
for i in {1..30}; do
    if curl -s http://localhost:8080/health > /dev/null 2>&1; then
        echo "Backend is ready!"
        break
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "Backend failed to start. Check logs above for errors."
        exit 1
    fi
    sleep 0.5
done

echo ""
echo "=== Services Running ==="
echo "Backend:  http://localhost:8080 (PID: $BACKEND_PID)"
echo "Tunnel:   $TUNNEL_URL (PID: $TUNNEL_PID)"
echo "========================"
echo ""
echo "Endpoints:"
echo "  GET  /health                         - Health check"
echo "  GET  /v3/memories                    - Get user memories (requires auth)"
echo "  GET  /v1/conversations               - Get user conversations (requires auth)"
echo "  POST /v1/conversations/from-segments - Process new conversation (requires auth)"
echo ""
echo "Press Ctrl+C to stop all services..."

# Wait for backend process (keeps script running and shows logs)
wait "$BACKEND_PID"
