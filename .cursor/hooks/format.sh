#!/bin/bash
# Auto-format hook for Cursor
# Formats code after file edits based on file type

set -e

# Get the file path from stdin (Cursor passes file path)
FILE_PATH="${1:-}"

if [ -z "$FILE_PATH" ]; then
    echo "No file path provided"
    exit 0
fi

# Skip if file doesn't exist
if [ ! -f "$FILE_PATH" ]; then
    exit 0
fi

# Get file extension
EXT="${FILE_PATH##*.}"
BASENAME=$(basename "$FILE_PATH")

# Skip auto-generated files
if [[ "$BASENAME" == *.gen.dart ]] || [[ "$BASENAME" == *.g.dart ]]; then
    exit 0
fi

# Format based on file type
case "$EXT" in
    py)
        # Python files in backend/
        if [[ "$FILE_PATH" == backend/* ]]; then
            if command -v black &> /dev/null; then
                echo "Formatting Python: $FILE_PATH"
                black --line-length 120 --skip-string-normalization "$FILE_PATH" 2>/dev/null || true
            fi
        fi
        ;;
    dart)
        # Dart files in app/
        if [[ "$FILE_PATH" == app/* ]]; then
            if command -v dart &> /dev/null; then
                echo "Formatting Dart: $FILE_PATH"
                dart format --line-length 120 "$FILE_PATH" 2>/dev/null || true
            fi
        fi
        ;;
    c|cpp|cc|cxx|h|hpp)
        # C/C++ files in firmware directories
        if [[ "$FILE_PATH" == omi/* ]] || [[ "$FILE_PATH" == omiGlass/* ]]; then
            if command -v clang-format &> /dev/null; then
                echo "Formatting C/C++: $FILE_PATH"
                clang-format -i "$FILE_PATH" 2>/dev/null || true
            fi
        fi
        ;;
    ts|tsx|js|jsx)
        # TypeScript/JavaScript files in web/
        if [[ "$FILE_PATH" == web/* ]]; then
            # Check for prettier in web directory
            if [ -f "web/frontend/node_modules/.bin/prettier" ]; then
                echo "Formatting TypeScript/JavaScript: $FILE_PATH"
                cd web/frontend && npx prettier --write "../../$FILE_PATH" 2>/dev/null || true
            fi
        fi
        ;;
esac

exit 0
