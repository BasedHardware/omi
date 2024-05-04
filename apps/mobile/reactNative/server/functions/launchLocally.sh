#!/bin/bash

# Path to the current directory(script must be ran from the functions directory)
FUNCTIONS_DIR=$(pwd)
PORT=30000

# Kill any existing processes on ports 50000-50007
lsof -ti:30000-30007 | xargs kill

# This is a workaround for a known issue with Python 3.7+ on macOS
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

for dir in "$FUNCTIONS_DIR"/*; do
  if [ -d "$dir" ]; then
    # Extract the function name from the directory path
    FUNCTION_NAME=$(basename "$dir")
    
    # Check if the main.py file exists in this directory
    MAIN_PY="$dir/main.py"
    if [ -f "$MAIN_PY" ]; then
      echo "Starting function $FUNCTION_NAME on port $PORT"
      # Start the function locally in the background
      (cd "$dir" && functions-framework --target="$FUNCTION_NAME" --port="$PORT" --debug &)
      # Increment the port number for the next function
      PORT=$((PORT + 1))
    else
      echo "main.py not found in $dir"
    fi
  fi
done

# Wait for any function to exit
wait