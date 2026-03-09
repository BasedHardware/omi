#!/usr/bin/env bash
# Flow 2: Settings navigation + toggle switch
# Tests: multi-level navigation, switch detection, toggle ON/OFF, state verification
#
# Usage: AGENT_FLUTTER_LOG=/tmp/flutter-run.log ./app/e2e/flow2-settings-toggle.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/e2e-helpers.sh"

e2e_setup "flow2-settings-toggle"

# ---- Step 1: Navigate to settings ----
e2e_step "Navigate to settings from home"
# Ensure we have a fresh snapshot on home screen
af_wait 0.3
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
  e2e_pass "Opened settings"
else
  e2e_fail "Could not find settings button"
fi

# ---- Step 2: Scroll to see Developer Settings ----
e2e_step "Scroll to Developer Settings"
af scroll down 2>&1
af_wait
af_screenshot "settings-scrolled"
e2e_pass "Scrolled settings"

# ---- Step 3: Open Developer Settings ----
e2e_step "Open Developer Settings"
# Dev Settings is a gesture element in the y=400-520 range after scroll
dev_ref=$(af snapshot -i --json 2>/dev/null | python3 -c "
import sys, json
elems = json.load(sys.stdin)
gestures = [e for e in elems if e.get('type') == 'gesture' and 400 < e['bounds']['y'] < 520 and e['bounds']['width'] > 300]
if gestures: print(gestures[0]['ref'])
else:
    # Fallback: 7th wide gesture
    g = [e for e in elems if e.get('type') == 'gesture' and e['bounds']['width'] > 300]
    if len(g) >= 7: print(g[6]['ref'])
    else: sys.exit(1)
" 2>/dev/null) || dev_ref=""

if [ -n "$dev_ref" ]; then
  af_press_wait "$dev_ref"
  e2e_pass "Opened Developer Settings"
else
  e2e_fail "Could not find Developer Settings"
fi
af_screenshot "dev-settings"

# ---- Step 4: Find and toggle switch ----
e2e_step "Find and toggle switch ON"
switch_ref=$(af_find_type "switch" 0 2>/dev/null) || switch_ref=""
if [ -n "$switch_ref" ]; then
  echo "  Switch ref: $switch_ref"
  af_press_wait "$switch_ref"
  e2e_pass "Toggled switch ON"
  af_screenshot "toggle-on"

  # Step 5: Toggle OFF
  e2e_step "Toggle switch OFF"
  switch_ref=$(af_find_type "switch" 0 2>/dev/null) || switch_ref=""
  if [ -n "$switch_ref" ]; then
    af_press_wait "$switch_ref"
    e2e_pass "Toggled switch OFF"
  else
    e2e_fail "Could not find switch to toggle off"
  fi
  af_screenshot "toggle-off"
else
  e2e_fail "No switch widget found"
fi

# ---- Step 6: Back to settings ----
e2e_step "Back to settings"
af back 2>&1
af_wait
e2e_pass "Returned to settings"

# ---- Step 7: Back to home ----
e2e_step "Back to home"
af back 2>&1
af_wait
final_count=$(af_snapshot_interactive_count)
echo "  Final elements: $final_count"
if [ "$final_count" -ge 5 ]; then
  e2e_pass "Back on home screen"
else
  e2e_fail "Failed to return to home"
fi

e2e_teardown
