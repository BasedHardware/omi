#!/bin/bash

# Path to the current directory, assuming this script is inside the functions directory
FUNCTIONS_DIR="./"

# Iterate over each subdirectory in the current directory
for dir in "$FUNCTIONS_DIR"/*; do
  if [ -d "$dir" ] && [ "$dir" != "$FUNCTIONS_DIR" ]; then
    # Change to the directory
    pushd "$dir" > /dev/null
    # Check if the deploy script exists in this directory
    DEPLOY_SCRIPT="./deployFunc.sh"
    if [ -f "$DEPLOY_SCRIPT" ]; then
      echo "Deploying function in $dir"
      # Make the script executable and run it
      chmod +x "$DEPLOY_SCRIPT"
      "./$DEPLOY_SCRIPT"
    else
      echo "Deploy script not found in $dir"
    fi
    # Change back to the functions directory
    popd > /dev/null
  fi
done