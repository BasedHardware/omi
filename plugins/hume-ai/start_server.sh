#!/bin/bash

# Script to start FastAPI server with ngrok tunnel

echo "🚀 Starting Omi Audio Streaming Service with Hume AI..."
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo "Please copy .env.example to .env and add your HUME_API_KEY"
    echo "Run: cp .env.example .env"
    exit 1
fi

# Check if HUME_API_KEY is set
source .env
if [ -z "$HUME_API_KEY" ] || [ "$HUME_API_KEY" = "your_hume_api_key_here" ]; then
    echo "❌ Error: HUME_API_KEY not configured in .env file!"
    echo "Please edit .env and add your Hume AI API key"
    exit 1
fi

echo "✓ Environment variables loaded"
echo ""

# Start FastAPI server in background
echo "📡 Starting FastAPI server on port 8080..."
python main.py > server.log 2>&1 &
SERVER_PID=$!
echo "✓ Server started (PID: $SERVER_PID)"

# Wait for server to be ready
echo "⏳ Waiting for server to start..."
sleep 3

# Check if server is running
if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "❌ Server failed to start. Check server.log for errors:"
    cat server.log
    exit 1
fi

echo "✓ Server is running"
echo ""

# Start ngrok tunnel
echo "🌐 Starting ngrok tunnel..."
ngrok http 8080 > ngrok.log 2>&1 &
NGROK_PID=$!
echo "✓ Ngrok started (PID: $NGROK_PID)"

# Wait for ngrok to be ready
sleep 3

# Get ngrok URL
echo "⏳ Getting ngrok URL..."
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | grep -o '"public_url":"https://[^"]*' | grep -o 'https://[^"]*' | head -1)

if [ -z "$NGROK_URL" ]; then
    echo "❌ Failed to get ngrok URL"
    echo "You can manually check at: http://localhost:4040"
else
    echo ""
    echo "============================================"
    echo "✅ Server is running!"
    echo "============================================"
    echo ""
    echo "📍 Local URL:  http://localhost:8080"
    echo "🌐 Public URL: $NGROK_URL"
    echo ""
    echo "📋 CONFIGURE YOUR OMI DEVICE:"
    echo "1. Open the Omi App"
    echo "2. Go to Settings → Developer Mode"
    echo "3. Set 'Realtime audio bytes' to:"
    echo "   $NGROK_URL/audio"
    echo "4. Set 'Every x seconds' to your desired interval (e.g., 10)"
    echo ""
    echo "============================================"
    echo ""
    echo "📊 Monitoring:"
    echo "   - Server logs: tail -f server.log"
    echo "   - Ngrok dashboard: http://localhost:4040"
    echo ""
    echo "🛑 To stop: Press Ctrl+C or run: pkill -P $$ "
    echo ""
fi

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down..."
    kill $SERVER_PID 2>/dev/null
    kill $NGROK_PID 2>/dev/null
    echo "✓ Stopped"
}

trap cleanup EXIT INT TERM

# Keep script running
wait
