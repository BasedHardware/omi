#!/bin/bash

# Directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "🧠 OMI Memory Quality Tuner"
echo "============================="

# Load environment variables if .env exists
if [ -f .env ]; then
    echo "Loading environment variables from .env file..."
    export $(grep -v '^#' .env | xargs)
else
    echo "Warning: .env file not found. Using default environment variables."
    # Set default environment variables
    export OPENAI_API_KEY=${OPENAI_API_KEY:-""}
    export LANGFUSE_API_KEY=${LANGFUSE_API_KEY:-"dummy_key"}
    export LANGFUSE_SECRET_KEY=${LANGFUSE_SECRET_KEY:-"dummy_secret"}
    export LANGFUSE_HOST=${LANGFUSE_HOST:-"https://cloud.langfuse.com"}
    export DSPY_VERBOSE=${DSPY_VERBOSE:-"0"}
fi

# Check if OpenAI API key is set and prompt if in interactive mode
if [ -z "$OPENAI_API_KEY" ] && [ -t 0 ]; then  # Only prompt if in interactive terminal
    echo "Notice: OPENAI_API_KEY is not set. You can:"
    echo "  1. Set it manually in a .env file"
    echo "  2. Run in DUMMY_MODE=true to test without API keys"
    echo "  3. Enter your key now"
    read -p "Enter your OpenAI API key (or press Enter to use DUMMY_MODE): " key
    if [ -z "$key" ]; then
        echo "No API key provided. Enabling DUMMY_MODE..."
        export DUMMY_MODE="true"
    else
        export OPENAI_API_KEY="$key"
    fi
fi

# Check for dependencies
DEPENDENCIES_OK=true

check_python_package() {
    python -c "import $1" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "⚠️ $1 package not found."
        DEPENDENCIES_OK=false
    fi
}

# Check if required packages are installed
check_python_package streamlit
check_python_package dspy
check_python_package openai
check_python_package numpy
check_python_package pandas
check_python_package dotenv

# Install dependencies if missing
if [ "$DEPENDENCIES_OK" = false ]; then
    echo "Installing missing dependencies..."
    pip install -r requirements.txt
    
    # Double-check installation
    echo "Verifying installations..."
    DEPENDENCIES_OK=true
    check_python_package streamlit
    check_python_package dspy
    check_python_package openai
    
    if [ "$DEPENDENCIES_OK" = false ]; then
        echo "⚠️ Some dependencies could not be installed. Attempting with --force-reinstall..."
        pip install -r requirements.txt --force-reinstall
    fi
fi

# Run the Streamlit app
echo "Starting OMI Memory Quality Tuner..."
python -m streamlit run app.py 