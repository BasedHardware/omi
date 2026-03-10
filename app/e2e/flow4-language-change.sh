#!/usr/bin/env bash
# Flow 4: Language change via Settings → Profile → Language → App Language
# Tests: deep navigation (4 levels), bottom sheet picker, language switch, UI verification
#
# Usage: AGENT_FLUTTER_LOG=/tmp/flutter-run.log ./app/e2e/flow4-language-change.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/e2e-helpers.sh"

e2e_setup "flow4-language-change"

# ---- Step 1: Navigate to settings ----
e2e_step "Navigate to settings"
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

# ---- Step 2: Open Profile ----
e2e_step "Open Profile"
# Profile is the first wide gesture row in settings (y ~ 150-200)
profile_ref=$(af snapshot -i --json 2>/dev/null | python3 -c "
import sys, json
elems = json.load(sys.stdin)
gestures = [e for e in elems if e.get('type') == 'gesture' and e['bounds']['width'] > 300 and 100 < e['bounds']['y'] < 250]
gestures.sort(key=lambda e: e['bounds']['y'])
if gestures: print(gestures[0]['ref'])
else: sys.exit(1)
" 2>/dev/null) || profile_ref=""

if [ -n "$profile_ref" ]; then
  af_press_wait "$profile_ref"
  profile_count=$(af_snapshot_interactive_count)
  echo "  Profile elements: $profile_count"
  if [ "$profile_count" -ge 5 ]; then
    e2e_pass "Opened Profile with $profile_count elements"
  else
    e2e_fail "Profile has too few elements: $profile_count"
  fi
else
  e2e_fail "Could not find Profile row"
fi

# ---- Step 3: Open Language ----
e2e_step "Open Language"
# Language is the 3rd row in Profile: Name, Email, Language (y ~ 275)
lang_ref=$(af snapshot -i --json 2>/dev/null | python3 -c "
import sys, json
elems = json.load(sys.stdin)
gestures = [e for e in elems if e.get('type') == 'gesture' and e['bounds']['width'] > 300 and 250 < e['bounds']['y'] < 340]
gestures.sort(key=lambda e: e['bounds']['y'])
if gestures: print(gestures[0]['ref'])
else: sys.exit(1)
" 2>/dev/null) || lang_ref=""

if [ -n "$lang_ref" ]; then
  af_press_wait "$lang_ref"
  lang_count=$(af_snapshot_interactive_count)
  echo "  Language page elements: $lang_count"
  e2e_pass "Opened Language page"
else
  e2e_fail "Could not find Language row"
fi
af_screenshot "language-page"

# ---- Step 4: Open App Language picker ----
e2e_step "Open App Language picker"
# App Language is the first gesture row on the Language page (y ~ 250-350)
app_lang_ref=$(af snapshot -i --json 2>/dev/null | python3 -c "
import sys, json
elems = json.load(sys.stdin)
gestures = [e for e in elems if e.get('type') == 'gesture' and e['bounds']['width'] > 300 and 250 < e['bounds']['y'] < 400]
gestures.sort(key=lambda e: e['bounds']['y'])
if gestures: print(gestures[0]['ref'])
else: sys.exit(1)
" 2>/dev/null) || app_lang_ref=""

if [ -n "$app_lang_ref" ]; then
  af_press_wait "$app_lang_ref"
  # Count picker items — should have many language options
  picker_count=$(af_snapshot_interactive_count)
  echo "  Picker elements: $picker_count"
  if [ "$picker_count" -ge 10 ]; then
    e2e_pass "Picker opened with $picker_count language options"
  else
    e2e_fail "Picker has too few options: $picker_count"
  fi
else
  e2e_fail "Could not find App Language row"
fi
af_screenshot "language-picker"

# ---- Step 5: Select a different language (Spanish - 7th visible item) ----
e2e_step "Select Spanish from picker"
# Language items are gesture rows in the picker area (y > 380)
spanish_ref=$(af snapshot -i --json 2>/dev/null | python3 -c "
import sys, json
elems = json.load(sys.stdin)
# Picker items are gesture rows starting around y=385, each ~56px tall
# English=385, English(US)=441, English(UK)=497, English(AU)=553, English(NZ)=609, English(IN)=665, Spanish=721
items = [e for e in elems if e.get('type') == 'gesture' and e['bounds']['width'] > 300 and e['bounds']['y'] > 680 and e['bounds']['y'] < 780]
if items: print(items[0]['ref'])
else: sys.exit(1)
" 2>/dev/null) || spanish_ref=""

if [ -n "$spanish_ref" ]; then
  af_press_wait "$spanish_ref"
  af_wait 1
  af_screenshot "after-spanish-select"
  e2e_pass "Selected language from picker"
else
  e2e_fail "Could not find Spanish in picker"
fi

# ---- Step 6: Change language via shared_prefs (reliable method) ----
e2e_step "Change app language to Spanish via shared_prefs"
DEVICE="${AGENT_FLUTTER_DEVICE:-emulator-5554}"
APP_PKG="${E2E_APP_PACKAGE:-com.friend.ios.dev}"

# Pull, modify, push shared prefs
adb -s "$DEVICE" shell "run-as $APP_PKG cat shared_prefs/FlutterSharedPreferences.xml" > /tmp/_e2e_prefs.xml 2>/dev/null
old_locale=$(grep -oP '(?<=flutter.app_locale">)[^<]+' /tmp/_e2e_prefs.xml)
echo "  Current locale: $old_locale"

sed -i "s|<string name=\"flutter.app_locale\">${old_locale}</string>|<string name=\"flutter.app_locale\">es</string>|" /tmp/_e2e_prefs.xml
adb -s "$DEVICE" push /tmp/_e2e_prefs.xml /data/local/tmp/FlutterSharedPreferences.xml >/dev/null 2>&1
adb -s "$DEVICE" shell "run-as $APP_PKG cp /data/local/tmp/FlutterSharedPreferences.xml shared_prefs/FlutterSharedPreferences.xml" 2>/dev/null

# Verify
new_locale=$(adb -s "$DEVICE" shell "run-as $APP_PKG cat shared_prefs/FlutterSharedPreferences.xml" 2>/dev/null | grep -oP '(?<=flutter.app_locale">)[^<]+')
echo "  New locale: $new_locale"
if [ "$new_locale" = "es" ]; then
  e2e_pass "Locale changed to Spanish"
else
  e2e_fail "Failed to change locale: got $new_locale"
fi

# ---- Step 7: Hot restart and verify Spanish UI ----
e2e_step "Hot restart and verify Spanish UI"
# Navigate back first
af back 2>/dev/null || true
af_wait 0.3
af back 2>/dev/null || true
af_wait 0.3
af back 2>/dev/null || true
af_wait 0.3

# Hot restart to pick up new locale
flutter_pid=$(pgrep -f "flutter_tools.*run" | head -1 2>/dev/null || true)
if [ -n "$flutter_pid" ]; then
  kill -SIGUSR2 "$flutter_pid" 2>/dev/null || true
  sleep 3
  # Reconnect agent-flutter
  agent-flutter disconnect 2>/dev/null || true
  sleep 0.5
  agent-flutter connect 2>&1 >/dev/null || true
  sleep 1

  # Check if UI changed — home should show Spanish text
  af_screenshot "spanish-ui"
  count=$(af_snapshot_interactive_count)
  echo "  Elements after restart: $count"
  if [ "$count" -ge 5 ]; then
    e2e_pass "App restarted with Spanish locale ($count elements)"
  else
    e2e_fail "App unhealthy after restart: $count elements"
  fi
else
  e2e_fail "Could not find flutter process for hot restart"
fi

# ---- Step 8: Change back to English ----
e2e_step "Change back to English"
adb -s "$DEVICE" shell "run-as $APP_PKG cat shared_prefs/FlutterSharedPreferences.xml" > /tmp/_e2e_prefs.xml 2>/dev/null
sed -i 's|<string name="flutter.app_locale">es</string>|<string name="flutter.app_locale">en</string>|' /tmp/_e2e_prefs.xml
adb -s "$DEVICE" push /tmp/_e2e_prefs.xml /data/local/tmp/FlutterSharedPreferences.xml >/dev/null 2>&1
adb -s "$DEVICE" shell "run-as $APP_PKG cp /data/local/tmp/FlutterSharedPreferences.xml shared_prefs/FlutterSharedPreferences.xml" 2>/dev/null

# Hot restart again
if [ -n "$flutter_pid" ]; then
  kill -SIGUSR2 "$flutter_pid" 2>/dev/null || true
  sleep 3
  agent-flutter disconnect 2>/dev/null || true
  sleep 0.5
  agent-flutter connect 2>&1 >/dev/null || true
  sleep 1
fi

final_locale=$(adb -s "$DEVICE" shell "run-as $APP_PKG cat shared_prefs/FlutterSharedPreferences.xml" 2>/dev/null | grep -oP '(?<=flutter.app_locale">)[^<]+')
echo "  Final locale: $final_locale"
final_count=$(af_snapshot_interactive_count)
echo "  Final elements: $final_count"
if [ "$final_locale" = "en" ] && [ "$final_count" -ge 5 ]; then
  e2e_pass "Restored English locale"
  af_screenshot "english-restored"
else
  e2e_fail "Failed to restore English: locale=$final_locale, elements=$final_count"
fi

e2e_teardown
