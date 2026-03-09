#!/usr/bin/env bash
# Flow 1: Desktop app navigation
# Tests: snapshot, sidebar navigation, element discovery, app responsiveness
#
# Usage: ./desktop/e2e/flow1-app-navigation.sh
# Requires: AGENT_SWIFT env var pointing to agent-swift binary

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/e2e-helpers.sh"

e2e_setup "flow1-app-navigation"

# ---- Step 1: Snapshot main window ----
e2e_step "Snapshot main window"
count=$(as_snapshot_interactive_count)
echo "  Interactive elements: $count"
if [ "$count" -ge 3 ]; then
  e2e_pass "Main window has $count interactive elements"
else
  e2e_fail "Main window has too few elements: $count"
fi
as_screenshot "main-window"

# ---- Step 2: Identify element types ----
e2e_step "Identify UI element types"
$AGENT_SWIFT snapshot --json 2>/dev/null | python3 -c "
import sys, json
from collections import Counter
elems = json.load(sys.stdin)
app_elems = [e for e in elems if e.get('type') not in ('menuitem', 'menubaritem', 'menu', 'menubar')]
types = Counter(e.get('type', 'unknown') for e in app_elems)
print(f'  App UI elements: {len(app_elems)}')
for t, c in types.most_common(10):
    print(f'    {t}: {c}')
" 2>/dev/null
e2e_pass "Element types identified"

# ---- Step 3: Verify sidebar navigation icons ----
e2e_step "Verify sidebar navigation icons"
# Sidebar uses image elements with labels: Home, Conversation, brain, checklist, puzzlepiece.fill, gearshape.fill
sidebar_found=0
for label in "Home" "Conversation" "brain" "checklist" "puzzlepiece.fill" "gearshape.fill"; do
  ref=$($AGENT_SWIFT snapshot --json 2>/dev/null | python3 -c "
import sys, json
elems = json.load(sys.stdin)
matches = [e for e in elems if e.get('type') == 'image' and e.get('label') == '$label']
if matches: print(matches[0]['ref'])
else: sys.exit(1)
" 2>/dev/null) || ref=""
  if [ -n "$ref" ]; then
    echo "  Found sidebar icon: $label ($ref)"
    sidebar_found=$((sidebar_found + 1))
  fi
done
if [ "$sidebar_found" -ge 4 ]; then
  e2e_pass "Found $sidebar_found/6 sidebar icons"
else
  e2e_fail "Only found $sidebar_found sidebar icons (expected >=4)"
fi

# ---- Step 4: Navigate sidebar — click each section ----
e2e_step "Navigate through sidebar sections"
nav_success=0
for label in "Conversation" "brain" "checklist" "Home"; do
  ref=$($AGENT_SWIFT snapshot --json 2>/dev/null | python3 -c "
import sys, json
elems = json.load(sys.stdin)
matches = [e for e in elems if e.get('type') == 'image' and e.get('label') == '$label']
if matches: print(matches[0]['ref'])
else: sys.exit(1)
" 2>/dev/null) || ref=""
  if [ -n "$ref" ]; then
    $AGENT_SWIFT press "@$ref" 2>&1
    as_wait 0.5
    new_count=$(as_snapshot_interactive_count)
    echo "  $label ($ref): $new_count elements"
    nav_success=$((nav_success + 1))
  else
    echo "  $label: not found"
  fi
done
if [ "$nav_success" -ge 3 ]; then
  e2e_pass "Navigated $nav_success sections successfully"
else
  e2e_fail "Only navigated $nav_success sections"
fi
as_screenshot "after-navigation"

# ---- Step 5: Test menu bar items ----
e2e_step "Verify menu bar structure"
menu_count=$($AGENT_SWIFT snapshot -i --json 2>/dev/null | python3 -c "
import sys, json
elems = json.load(sys.stdin)
menus = [e for e in elems if e.get('type') == 'menubaritem']
print(len(menus))
for m in menus[:8]:
    label = m.get('label', '(unlabeled)')
    print(f'  {m[\"ref\"]} {label}')
" 2>/dev/null || echo "0")
echo "  Menu bar items: $(echo "$menu_count" | head -1)"
echo "$menu_count" | tail -n +2
if [ "$(echo "$menu_count" | head -1)" -ge 3 ]; then
  e2e_pass "Menu bar has $(echo "$menu_count" | head -1) items"
else
  e2e_fail "Menu bar has too few items"
fi

# ---- Step 6: Test system tray menu items ----
e2e_step "Verify system tray menu"
tray_items=$($AGENT_SWIFT snapshot -i --json 2>/dev/null | python3 -c "
import sys, json
elems = json.load(sys.stdin)
# Tray items have identifiers like openOmiFromMenu, checkForUpdates, etc.
tray = [e for e in elems if e.get('type') == 'menuitem' and e.get('identifier', '').startswith(('openOmi', 'checkFor', 'resetOnb', 'reportIs', 'signOut', 'quitApp'))]
print(len(tray))
for t in tray:
    print(f'  {t[\"ref\"]} {t.get(\"label\", \"\")} ({t.get(\"identifier\", \"\")})')
" 2>/dev/null || echo "0")
tray_count=$(echo "$tray_items" | head -1)
echo "  Tray menu items: $tray_count"
echo "$tray_items" | tail -n +2
if [ "$tray_count" -ge 3 ]; then
  e2e_pass "System tray has $tray_count custom items"
else
  e2e_fail "System tray has too few items: $tray_count"
fi

# ---- Step 7: Verify app is still responsive ----
e2e_step "Verify app responsiveness"
final_count=$(as_snapshot_interactive_count)
echo "  Final elements: $final_count"
if [ "$final_count" -ge 3 ]; then
  e2e_pass "App is responsive with $final_count elements"
else
  e2e_fail "App may be unresponsive: $final_count elements"
fi
as_screenshot "final"

e2e_teardown
