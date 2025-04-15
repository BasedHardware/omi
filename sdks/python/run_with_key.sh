#!/bin/bash

# Activate virtual environment
source venv/bin/activate

# Prompt for Deepgram API key 
echo "Enter your Deepgram API key: "
read -s API_KEY

# Run the application with the API key
DEEPGRAM_API_KEY=$API_KEY python3 main.py 