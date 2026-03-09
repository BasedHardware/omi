#!/usr/bin/env bash
# Flow 3: Bottom tab navigation
# Tests: bottom nav bar, tab switching, scroll, element counts per tab
#
# Usage: AGENT_FLUTTER_LOG=/tmp/flutter-run.log ./app/e2e/flow3-tab-navigation.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/e2e-helpers.sh"

e2e_setup "flow3-tab-navigation"

# Helper: get sorted bottom nav tab refs (InkWell elements near bottom, y > 780)
get_nav_tabs() {
  af snapshot -i --json 2>/dev/null | python3 -c "
import sys, json
elems = json.load(sys.stdin)
tabs = sorted(
    [e for e in elems if e.get('flutterType') == 'InkWell' and e['bounds']['y'] > 780],
    key=lambda e: e['bounds']['x']
)
for t in tabs: print(t['ref'])
"
}

# ---- Step 1: Verify home tab ----
e2e_step "Verify home tab"
count=$(af_snapshot_interactive_count)
echo "  Interactive elements: $count"
mapfile -t TABS < <(get_nav_tabs)
echo "  Nav tabs: ${#TABS[@]} (refs: ${TABS[*]:-none})"
if [ "$count" -ge 5 ] && [ "${#TABS[@]}" -ge 2 ]; then
  e2e_pass "Home tab loaded, ${#TABS[@]} nav tabs found"
else
  e2e_fail "Home tab unhealthy: $count elements, ${#TABS[@]} tabs"
fi
af_screenshot "tab-home"

# ---- Step 2: Switch to 2nd tab ----
e2e_step "Switch to tab 2"
if [ "${#TABS[@]}" -ge 2 ]; then
  af_press_wait "${TABS[1]}"
  tab2_count=$(af_snapshot_interactive_count)
  echo "  Tab 2 elements: $tab2_count"
  e2e_pass "Switched to tab 2"
else
  e2e_fail "Not enough tabs"
fi
af_screenshot "tab-2"

# ---- Step 3: Switch to 3rd tab ----
e2e_step "Switch to tab 3"
mapfile -t TABS < <(get_nav_tabs)
if [ "${#TABS[@]}" -ge 3 ]; then
  af_press_wait "${TABS[2]}"
  tab3_count=$(af_snapshot_interactive_count)
  echo "  Tab 3 elements: $tab3_count"
  e2e_pass "Switched to tab 3"
else
  e2e_fail "Not enough tabs"
fi
af_screenshot "tab-3"

# ---- Step 4: Scroll ----
e2e_step "Scroll in current tab"
af scroll down 2>&1
af_wait
e2e_pass "Scrolled"

# ---- Step 5: Switch to 4th tab ----
e2e_step "Switch to tab 4"
mapfile -t TABS < <(get_nav_tabs)
if [ "${#TABS[@]}" -ge 4 ]; then
  af_press_wait "${TABS[3]}"
  tab4_count=$(af_snapshot_interactive_count)
  echo "  Tab 4 elements: $tab4_count"
  e2e_pass "Switched to tab 4"
else
  e2e_fail "Not enough tabs"
fi
af_screenshot "tab-4"

# ---- Step 6: Return to home tab ----
e2e_step "Return to home tab"
mapfile -t TABS < <(get_nav_tabs)
if [ "${#TABS[@]}" -ge 1 ]; then
  af_press_wait "${TABS[0]}"
  home_count=$(af_snapshot_interactive_count)
  echo "  Home elements: $home_count"
  if [ "$home_count" -ge 5 ]; then
    e2e_pass "Returned to home"
  else
    e2e_fail "Home tab unhealthy after return: $home_count elements"
  fi
else
  e2e_fail "Could not find home tab"
fi
af_screenshot "final"

e2e_teardown
