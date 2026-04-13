#!/bin/bash
set -e

echo "==================================="
echo "Omi Backend One-Click Deployment"
echo "==================================="
echo ""
echo "Select deployment mode:"
echo "1) QUICK START - Minimal setup, no API keys needed"
echo "2) FULL SETUP - All features enabled"
echo ""
read -p "Enter choice [1 or 2]: " choice

if [ "$choice" = "1" ]; then
    echo ""
    echo "Starting QUICK START mode..."
    export QUICK_START=true
    docker-compose -f docker-compose.yaml up -d
elif [ "$choice" = "2" ]; then
    echo ""
    echo "Starting FULL SETUP mode..."
    echo "Please ensure you have configured your API keys in .env file"
    read -p "Press Enter to continue..."
    docker-compose -f docker-compose.yaml up -d
else
    echo "Invalid choice. Exiting."
    exit 1
fi

echo ""
echo "==================================="
echo "Waiting for services to be ready..."
echo "==================================="
sleep 10

echo ""
echo "Checking service health..."
docker-compose ps

echo ""
echo "==================================="
echo "Omi backend is now running!"
echo "==================================="
echo "Backend: http://localhost:8080"
echo "PostgreSQL: localhost:5432"
echo "Redis: localhost:6379"
echo "Typesense: localhost:8108"
echo ""
echo "To view logs: docker-compose logs -f"
echo "To stop: docker-compose down"
