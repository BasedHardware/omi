#!/bin/bash

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Error: .env file not found."
    echo "Please create a .env file first by copying .env.template:"
    echo "cp .env.template .env"
    exit 1
fi

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed or not in PATH."
    exit 1
fi

# Install dependencies if not already installed
echo "Checking dependencies..."
pip3 install -q fastapi uvicorn python-dotenv jinja2 python-multipart

# Run the server
echo "Starting OMI ChatGPT Integration server..."
python3 server.py 