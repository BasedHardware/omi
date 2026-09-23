#!/bin/bash

# Ensure script fails if any command fails
set -euo pipefail

# Define colors for better output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed or not in PATH${NC}"
    exit 1
fi

# Parse command line arguments
CLEAN_BUILD=0
for arg in "$@"; do
    case $arg in
        --clean)
            CLEAN_BUILD=1
            shift
            ;;
        *)
            # Unknown option
            ;;
    esac
done

# Make script executable
chmod +x $(dirname "$0")/build-firmware-in-docker.sh

# Detect platform - for M1/M2/M3 Macs
PLATFORM_FLAG=""
if [[ $(uname -m) == "arm64" ]]; then
    echo -e "${YELLOW}Detected ARM64 platform (M1/M2/M3 Mac)${NC}"
fi

# Get the absolute path to the repository root
REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)

# Clean build if requested
if [ $CLEAN_BUILD -eq 1 ]; then
    echo -e "${YELLOW}Cleaning previous build...${NC}"
    rm -rf "$REPO_ROOT/firmware/v2.7.0"
    rm -rf "$REPO_ROOT/firmware/build/docker_build"
    # Also clean the build directory inside app if it exists from previous runs
    rm -rf "$REPO_ROOT/firmware/app/build"
fi

echo -e "${YELLOW}Starting Docker container for firmware build...${NC}"
echo -e "${YELLOW}This might take a while the first time.${NC}"

# Run the Docker container with the repository mounted correctly
# Rely on the environment variables set within the ghcr.io/zephyrproject-rtos/ci image
docker run --rm -it $PLATFORM_FLAG \
    -v "$REPO_ROOT:/omi" \
    -e CMAKE_PREFIX_PATH=/opt/toolchains \
    -e PATH="/root/.local/bin:$PATH" \
    ghcr.io/zephyrproject-rtos/ci \
    bash -c "pip install --user adafruit-nrfutil && \
             /omi/firmware/scripts/build-firmware-in-docker.sh"

# Check if the build was successful
if [ -d "$REPO_ROOT/firmware/build/docker_build" ] && [ "$(ls -A "$REPO_ROOT/firmware/build/docker_build")" ]; then
    echo -e "${GREEN}Build artifacts are available at:${NC}"
    echo -e "${GREEN}$(realpath "$REPO_ROOT/firmware/build/docker_build")${NC}"

    # List the generated files
    echo -e "${YELLOW}Generated files:${NC}"
    ls -la "$REPO_ROOT/firmware/build/docker_build"
else
    echo -e "${RED}Build may have failed. Check the logs above for errors.${NC}"
    exit 1
fi
