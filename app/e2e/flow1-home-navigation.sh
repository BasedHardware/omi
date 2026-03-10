#!/usr/bin/env bash
# Flow 1: Home screen navigation
# Tests: snapshot, press @ref, screen transitions, scroll, back
#
# Usage: AGENT_FLUTTER_LOG=/tmp/flutter-run.log ./app/e2e/flow1-home-navigation.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/e2e-helpers.sh"

e2e_setup "flow1-home-navigation"

# ---- Step 1: Snapshot home screen ----
e2e_step "Snapshot home screen"
count=$(af_snapshot_interactive_count)
echo "  Interactive elements: $count"
if [ "$count" -ge 5 ]; then
  e2e_pass "Home screen has $count interactive elements"
else
  e2e_fail "Home screen has too few elements: $count"
fi
af_screenshot "home"

# ---- Step 2: Find and press settings gear (last IconButton, top-right) ----
e2e_step "Press settings gear"
# Settings gear is the rightmost button in the top bar
settings_ref=$(af snapshot -i --json 2>/dev/null | python3 -c "
import sys, json
elems = json.load(sys.stdin)
buttons = [e for e in elems if e.get('type') == 'button']
buttons.sort(key=lambda e: e['bounds']['x'], reverse=True)
if buttons: print(buttons[0]['ref'])
else: sys.exit(1)
" 2>/dev/null) || settings_ref=""

if [ -n "$settings_ref" ]; then
  af_press_wait "$settings_ref"
  settings_count=$(af_snapshot_interactive_count)
  echo "  Settings elements: $settings_count"
  if [ "$settings_count" -ge 5 ]; then
    e2e_pass "Settings page loaded with $settings_count elements"
  else
    e2e_fail "Settings page has too few elements: $settings_count"
  fi
else
  e2e_fail "Could not find settings button"
fi
af_screenshot "settings"

# ---- Step 3: Scroll down in settings ----
e2e_step "Scroll down in settings"
af scroll down 2>&1
af_wait
af_screenshot "settings-scrolled"
e2e_pass "Scrolled in settings"

# ---- Step 4: Go back to home ----
e2e_step "Dismiss settings"
af back 2>&1
af_wait
final_count=$(af_snapshot_interactive_count)
echo "  Final elements: $final_count"
if [ "$final_count" -ge 5 ]; then
  e2e_pass "Back on home screen"
else
  e2e_fail "Failed to return to home screen"
fi
af_screenshot "final"

e2e_teardown
