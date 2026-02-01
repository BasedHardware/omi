#!/bin/bash
# Quick test script to validate community app structure
# Run this before submitting your PR

set -e

echo "🔍 Testing Community Apps Structure..."
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

# Test 1: Check registry.json is valid JSON
echo "Test 1: Validating registry.json..."
if python3 -c "import json; json.load(open('community-apps/registry.json'))" 2>/dev/null; then
    echo -e "${GREEN}✅ PASS${NC}: registry.json is valid JSON"
else
    echo -e "${RED}❌ FAIL${NC}: registry.json is not valid JSON"
    ERRORS=$((ERRORS + 1))
fi

# Test 2: Check app-schema.json is valid JSON
echo "Test 2: Validating app-schema.json..."
if python3 -c "import json; json.load(open('community-apps/app-schema.json'))" 2>/dev/null; then
    echo -e "${GREEN}✅ PASS${NC}: app-schema.json is valid JSON"
else
    echo -e "${RED}❌ FAIL${NC}: app-schema.json is not valid JSON"
    ERRORS=$((ERRORS + 1))
fi

# Test 3: Check each app directory
echo "Test 3: Validating app directories..."
for app_dir in community-apps/*/*/; do
    # Skip TEMPLATE and non-directories
    if [[ "$app_dir" == *"TEMPLATE"* ]] || [[ ! -d "$app_dir" ]]; then
        continue
    fi

    app_name=$(basename "$app_dir")
    author=$(basename $(dirname "$app_dir"))

    echo ""
    echo "  Checking $author/$app_name..."

    # Check required files
    REQUIRED_FILES=("app.json" "main.py" "README.md" "requirements.txt")
    for file in "${REQUIRED_FILES[@]}"; do
        if [[ ! -f "$app_dir$file" ]]; then
            echo -e "    ${RED}❌ FAIL${NC}: Missing $file"
            ERRORS=$((ERRORS + 1))
        fi
    done

    # Check for logo (any image format)
    if ! ls "$app_dir"logo.* 1> /dev/null 2>&1; then
        echo -e "    ${YELLOW}⚠️  WARNING${NC}: Missing logo image"
        WARNINGS=$((WARNINGS + 1))
    fi

    # Validate app.json
    if [[ -f "$app_dir/app.json" ]]; then
        if python3 -c "import json; json.load(open('$app_dir/app.json'))" 2>/dev/null; then
            # Check if ID matches directory structure
            APP_ID=$(python3 -c "import json; print(json.load(open('$app_dir/app.json'))['id'])" 2>/dev/null || echo "")
            EXPECTED_ID="$author/$app_name"

            if [[ "$APP_ID" == "$EXPECTED_ID" ]]; then
                echo -e "    ${GREEN}✅ PASS${NC}: app.json valid, ID matches"
            else
                echo -e "    ${RED}❌ FAIL${NC}: ID mismatch. Expected '$EXPECTED_ID', got '$APP_ID'"
                ERRORS=$((ERRORS + 1))
            fi
        else
            echo -e "    ${RED}❌ FAIL${NC}: app.json is not valid JSON"
            ERRORS=$((ERRORS + 1))
        fi
    fi

    # Check if app is in registry
    if grep -q "\"$author/$app_name\"" community-apps/registry.json; then
        echo -e "    ${GREEN}✅ PASS${NC}: App found in registry"
    else
        echo -e "    ${RED}❌ FAIL${NC}: App not found in registry.json"
        ERRORS=$((ERRORS + 1))
    fi
done

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ $ERRORS -eq 0 ]]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
    if [[ $WARNINGS -gt 0 ]]; then
        echo -e "${YELLOW}⚠️  $WARNINGS warning(s) found${NC}"
    fi
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 0
else
    echo -e "${RED}❌ Tests failed with $ERRORS error(s) and $WARNINGS warning(s)${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 1
fi
