#!/bin/bash

# OMI Glass UF2 Builder Script
# Simple wrapper for building UF2 files

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Print colored output
print_header() {
    echo -e "${PURPLE}🚀 OMI Glass UF2 Builder${NC}"
    echo -e "${PURPLE}════════════════════════${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -e, --env ENV        Build environment (default: seeed_xiao_esp32s3)"
    echo "  -c, --convert-only   Only convert existing binary to UF2"
    echo "  -b, --binary FILE    Specific binary file to convert"
    echo "  -o, --output FILE    Output UF2 filename"
    echo "  -h, --help          Show this help message"
    echo ""
    echo "Environments:"
    echo "  seeed_xiao_esp32s3      Standard ESP32-S3 build (default)"
    echo "  seeed_xiao_esp32s3_slow Slower upload for reliability"
    echo "  uf2_release             Optimized release build"
    echo ""
    echo "Examples:"
    echo "  $0                      # Build default environment and create UF2"
    echo "  $0 -e uf2_release       # Build optimized release version"
    echo "  $0 -c                   # Convert existing binary to UF2"
    echo "  $0 -b firmware.bin      # Convert specific binary file"
}

# Default values
ENV="seeed_xiao_esp32s3"
CONVERT_ONLY=false
BINARY=""
OUTPUT=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--env)
            ENV="$2"
            shift 2
            ;;
        -c|--convert-only)
            CONVERT_ONLY=true
            shift
            ;;
        -b|--binary)
            BINARY="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

print_header

# Check if we're in the firmware directory
if [ ! -f "platformio.ini" ]; then
    print_error "platformio.ini not found. Please run this script from the firmware directory."
    exit 1
fi

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 not found. Please install Python 3."
    exit 1
fi

# Build arguments for Python script
PYTHON_ARGS=""

if [ "$ENV" != "seeed_xiao_esp32s3" ]; then
    PYTHON_ARGS="$PYTHON_ARGS --env $ENV"
fi

if [ "$CONVERT_ONLY" = true ]; then
    PYTHON_ARGS="$PYTHON_ARGS --convert-only"
fi

if [ -n "$BINARY" ]; then
    PYTHON_ARGS="$PYTHON_ARGS --binary $BINARY"
fi

if [ -n "$OUTPUT" ]; then
    PYTHON_ARGS="$PYTHON_ARGS --output $OUTPUT"
fi

# Run the Python UF2 builder
print_info "Running UF2 builder with arguments: $PYTHON_ARGS"
echo ""

if python3 build_uf2.py $PYTHON_ARGS; then
    echo ""
    print_success "UF2 build completed successfully!"
    
    # Show additional instructions
    echo ""
    print_info "Next steps:"
    echo "1. Put your ESP32-S3 in bootloader mode"
    echo "2. Copy the .uf2 file to the ESP32S3 USB drive"
    echo "3. Device will automatically flash and reboot"
    echo ""
    print_info "Alternative flashing methods:"
    echo "• Using existing build script: ./build_and_test.sh upload"
    echo "• Using PlatformIO directly: pio run -t upload"
    echo "• Monitor device: pio device monitor --baud 115200"
    
else
    print_error "UF2 build failed!"
    exit 1
fi 