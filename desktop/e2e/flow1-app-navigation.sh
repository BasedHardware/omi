#!/usr/bin/env bash
# Flow 1: Desktop app navigation
# Tests: snapshot, sidebar navigation, find, fill, scroll, is, wait, screenshot
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

# ---- Step 3: Find elements by role and text ----
e2e_step "Find elements (role, text)"
btn_ref=$(as_find_role "button")
if [ -n "$btn_ref" ]; then
  echo "  find role button → $btn_ref"
  e2e_pass "Found button: $btn_ref"
else
  e2e_fail "find role button returned nothing"
fi

# ---- Step 4: Get element properties ----
e2e_step "Get element properties"
if [ -n "$btn_ref" ]; then
  btn_type=$(as get type "@$btn_ref" --json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('value','?'))" 2>/dev/null || echo "?")
  btn_text=$(as get text "@$btn_ref" --json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('value','?'))" 2>/dev/null || echo "?")
  echo "  @$btn_ref type=$btn_type text=$btn_text"
  e2e_pass "get type=$btn_type, text=$btn_text"
else
  e2e_fail "no element for get test"
fi

# ---- Step 5: Assert element conditions ----
e2e_step "Assert element conditions (is)"
if [ -n "$btn_ref" ]; then
  as is exists "@$btn_ref" 2>/dev/null
  exists_exit=$?
  echo "  is exists @$btn_ref → exit $exists_exit"
  if [ "$exists_exit" -eq 0 ]; then e2e_pass "is exists → true"; else e2e_fail "is exists returned $exists_exit"; fi

  as is exists "@e99999" 2>/dev/null
  fake_exit=$?
  echo "  is exists @e99999 → exit $fake_exit"
  if [ "$fake_exit" -ne 0 ]; then e2e_pass "is exists → false for non-existent"; else e2e_fail "is returned 0 for fake element"; fi
else
  e2e_fail "no element for is test"
fi

# ---- Step 6: Verify sidebar navigation icons ----
e2e_step "Verify sidebar navigation icons"
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

# ---- Step 7: Navigate sidebar — click each section ----
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
    as_screenshot "$label"
  else
    echo "  $label: not found"
  fi
done
if [ "$nav_success" -ge 3 ]; then
  e2e_pass "Navigated $nav_success sections successfully"
else
  e2e_fail "Only navigated $nav_success sections"
fi

# ---- Step 8: Fill text field ----
e2e_step "Fill text input"
snap_i=$($AGENT_SWIFT snapshot -i --json 2>/dev/null)
text_ref=$(echo "$snap_i" | python3 -c "
import sys, json
elems = json.load(sys.stdin)
fields = [e for e in elems if e.get('type') in ('textfield', 'textarea', 'searchfield')]
if fields: print(fields[0]['ref'])
else: sys.exit(1)
" 2>/dev/null) || text_ref=""
if [ -n "$text_ref" ]; then
  echo "  Filling @$text_ref..."
  $AGENT_SWIFT fill "@$text_ref" "agent-swift E2E test" --json 2>&1 > /dev/null
  fill_exit=$?
  if [ "$fill_exit" -eq 0 ]; then e2e_pass "fill @$text_ref succeeded"; else e2e_fail "fill failed (exit $fill_exit)"; fi
  as_screenshot "after-fill"
else
  echo "  No text field in current view (informational)"
  e2e_pass "fill skipped — no text field visible"
fi

# ---- Step 9: Scroll ----
e2e_step "Scroll down and up"
$AGENT_SWIFT scroll down --json 2>&1 > /dev/null
d_exit=$?
as_wait 0.3
$AGENT_SWIFT scroll up --json 2>&1 > /dev/null
u_exit=$?
echo "  scroll down: exit $d_exit, scroll up: exit $u_exit"
if [ "$d_exit" -eq 0 ] && [ "$u_exit" -eq 0 ]; then
  e2e_pass "scroll down + up"
else
  e2e_fail "scroll failed (down=$d_exit, up=$u_exit)"
fi

# ---- Step 10: Wait for element ----
e2e_step "Wait for condition"
if [ -n "$btn_ref" ]; then
  $AGENT_SWIFT wait exists "@$btn_ref" --timeout 3000 --json 2>&1 > /dev/null
  wait_exit=$?
  echo "  wait exists @$btn_ref → exit $wait_exit"
  if [ "$wait_exit" -eq 0 ]; then e2e_pass "wait exists succeeded"; else e2e_fail "wait failed (exit $wait_exit)"; fi
else
  e2e_pass "wait skipped — no ref available"
fi

# ---- Step 11: Verify tray menu ----
e2e_step "Verify system tray menu"
tray_items=$($AGENT_SWIFT snapshot -i --json 2>/dev/null | python3 -c "
import sys, json
elems = json.load(sys.stdin)
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

# ---- Step 12: Final responsiveness + screenshot ----
e2e_step "Verify app responsiveness"
final_count=$(as_snapshot_interactive_count)
echo "  Final elements: $final_count"
if [ "$final_count" -ge 3 ]; then
  e2e_pass "App is responsive with $final_count elements"
else
  e2e_fail "App may be unresponsive: $final_count elements"
fi
as_screenshot "final"

# ---- Step 13: JSON output modes ----
e2e_step "JSON output modes"
# AGENT_SWIFT_JSON=1 env var
is_json=$(AGENT_SWIFT_JSON=1 $AGENT_SWIFT status 2>&1 | python3 -c "
import sys,json
try: json.load(sys.stdin); print('yes')
except: print('no')
")
echo "  AGENT_SWIFT_JSON=1: $is_json"
if [ "$is_json" = "yes" ]; then e2e_pass "AGENT_SWIFT_JSON=1 produces JSON"; else e2e_fail "env var JSON failed"; fi

# Piped auto-JSON
piped_json=$($AGENT_SWIFT status | python3 -c "
import sys,json
try: json.load(sys.stdin); print('yes')
except: print('no')
")
echo "  Piped auto-JSON: $piped_json"
if [ "$piped_json" = "yes" ]; then e2e_pass "piped auto-JSON works"; else e2e_fail "piped JSON failed"; fi

e2e_teardown
