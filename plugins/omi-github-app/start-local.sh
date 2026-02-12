#!/bin/bash

# GitHub Issues OMI App - Local Development Starter
# This script helps you start the app locally with ngrok

echo "🐙 GitHub Issues OMI App - Local Setup"
echo "========================================"
echo ""

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "Please create .env file with your API keys first."
    exit 1
fi

# Check if API keys are configured
if grep -q "PASTE_YOUR" .env; then
    echo "⚠️  WARNING: .env file contains placeholder values!"
    echo ""
    echo "Please update .env with your actual API keys:"
    echo "  1. GitHub Client ID and Secret"
    echo "  2. OpenAI API Key"
    echo "  3. ngrok URL (after starting ngrok)"
    echo ""
    read -p "Have you updated the .env file? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Please update .env first, then run this script again."
        exit 1
    fi
fi

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
echo "✅ Activating virtual environment..."
source venv/bin/activate

# Check if ngrok is running
echo ""
echo "📡 Checking ngrok status..."
if ! curl -s http://localhost:4040/api/tunnels > /dev/null 2>&1; then
    echo ""
    echo "⚠️  ngrok doesn't seem to be running!"
    echo ""
    echo "Please open a NEW terminal window and run:"
    echo "  ngrok http 8000"
    echo ""
    echo "Then copy the ngrok URL (https://xxxxx.ngrok.app)"
    echo "and update your .env file with:"
    echo "  OAUTH_REDIRECT_URL=https://xxxxx.ngrok.app/auth/callback"
    echo ""
    read -p "Press Enter when ngrok is running and .env is updated..."
fi

# Get ngrok URL
if curl -s http://localhost:4040/api/tunnels > /dev/null 2>&1; then
    NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | python3 -c "import sys, json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])" 2>/dev/null)
    if [ ! -z "$NGROK_URL" ]; then
        echo ""
        echo "✅ ngrok is running!"
        echo "📡 Your ngrok URL: $NGROK_URL"
        echo ""
        echo "📋 Use these URLs in your OMI app settings:"
        echo "   Webhook URL: $NGROK_URL/webhook"
        echo "   App Home URL: $NGROK_URL/"
        echo "   Auth URL: $NGROK_URL/auth"
        echo "   Setup Check URL: $NGROK_URL/setup-completed"
        echo ""
        echo "⚠️  Make sure your GitHub OAuth callback is set to:"
        echo "   $NGROK_URL/auth/callback"
        echo ""
    fi
fi

# Start the app
echo "🚀 Starting the app on http://0.0.0.0:8000"
echo "📱 Test interface: http://localhost:8000/test"
if [ ! -z "$NGROK_URL" ]; then
    echo "🌐 Public URL: $NGROK_URL/test"
fi
echo ""
echo "Press Ctrl+C to stop the server"
echo "========================================"
echo ""

# Run the app
python main.py

