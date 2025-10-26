# Developer Settings Webhook Persistence Fix

## Summary
Fixed critical bugs where webhook settings (toggles AND URLs) in Developer Settings would not persist after saving and navigating away from the page.

---

## The Bugs

### Bug 1: Toggle State Not Persisting
**Issue:** When users toggled on "Realtime Audio Bytes" (or any webhook toggle), the toggle would revert to OFF after navigating away and returning to the page.

**Root Causes:**
1. **Fire-and-Forget API Calls**: Toggle callbacks called `enableWebhook`/`disableWebhook` without `await`
2. **No Immediate Persistence**: Toggle state wasn't saved to SharedPreferences when toggled
3. **Race Condition in initialize()**: `getWebhooksStatus()` ran in parallel with URL fetching
4. **No Error Handling**: Failed API calls had no recovery mechanism

### Bug 2: Webhook URLs Not Persisting
**Issue:** When users entered webhook URLs (like "Endpoint URL" and "Every X Seconds"), clicked Save, then navigated away, the URL fields would be empty upon return.

**Root Cause:** During initialization (`initialize()`), the code fetched webhook URLs from the server and **unconditionally overwrote** both the UI text fields AND SharedPreferences with the server response - even when the server returned empty strings! This meant:
1. User enters URL and clicks "Save"
2. URL saved to server and SharedPreferences
3. User navigates away
4. User returns → `initialize()` runs
5. Loads URL from SharedPreferences (correct value)
6. Fetches from server (might be empty or old)
7. **Overwrites SharedPreferences with server value** (lines 140-171)
8. URL lost!

**Battery Optimization Impact:** None. Battery settings only affect BLE keep-alive intervals and frame coalescing, not UI state persistence.

---

## Fixes Applied

### 1. Made Toggle Callbacks Async (Lines 32-106)
```dart
// BEFORE
void onAudioBytesToggled(bool value) {
  audioBytesToggled = value;
  if (!value) {
    disableWebhook(type: 'audio_bytes');  // ❌ Fire-and-forget
  } else {
    enableWebhook(type: 'audio_bytes');    // ❌ Fire-and-forget
  }
  notifyListeners();
}

// AFTER
Future<void> onAudioBytesToggled(bool value) async {
  audioBytesToggled = value;
  SharedPreferencesUtil().audioBytesToggled = value;  // ✅ Persist immediately
  notifyListeners();

  try {
    if (!value) {
      await disableWebhook(type: 'audio_bytes');  // ✅ Await
    } else {
      await enableWebhook(type: 'audio_bytes');    // ✅ Await
    }
  } catch (e) {
    Logger.error('Failed to toggle audio bytes webhook: $e');
    audioBytesToggled = !value;  // ✅ Rollback on failure
    SharedPreferencesUtil().audioBytesToggled = !value;
    notifyListeners();
  }
}
```

**Applied to all toggle callbacks:**
- `onConversationEventsToggled()`
- `onTranscriptsToggled()`
- `onAudioBytesToggled()`
- `onDaySummaryToggled()`

### 2. Immediate SharedPreferences Persistence
Each toggle now immediately saves to SharedPreferences before making the API call, ensuring state persists even if navigation occurs during the API call.

### 3. Error Handling with Rollback
If the API call fails, the toggle state is automatically reverted to its previous value in both memory and SharedPreferences.

### 4. Fixed initialize() Race Condition (Lines 93-138)
```dart
// BEFORE
await Future.wait([
  getWebhooksStatus(),      // ❌ Could override local state
  getUserWebhookUrl(...),
  // ...
]);

// AFTER
await Future.wait([
  getUserWebhookUrl(...),   // ✅ Fetch URLs first
  // ...
]);

await getWebhooksStatus();  // ✅ Then sync status from server
```

Now `getWebhooksStatus()` runs **after** URL fetching completes, maintaining proper order of operations.

### 5. Improved getWebhooksStatus() (Lines 108-122)
```dart
// BEFORE
if (res == null) {
  conversationEventsToggled = false;  // ❌ Overwrites everything
  transcriptsToggled = false;
  audioBytesToggled = false;
  daySummaryToggled = false;
}

// AFTER
if (res == null) {
  return;  // ✅ Preserve existing state if server unreachable
}
```

### 6. **NEW: Preserve Local URLs During Initialization (Lines 140-172)**
```dart
// BEFORE
getUserWebhookUrl(type: 'audio_bytes').then((url) {
  List<dynamic> parts = url.split(',');
  if (parts.length == 2) {
    webhookAudioBytes.text = parts[0].toString();  // ❌ Always overwrites!
    webhookAudioBytesDelay.text = parts[1].toString();
  } else {
    webhookAudioBytes.text = url;  // ❌ Even if url is empty ''!
    webhookAudioBytesDelay.text = '5';
  }
  SharedPreferencesUtil().webhookAudioBytes = webhookAudioBytes.text;  // ❌ Overwrites local
  SharedPreferencesUtil().webhookAudioBytesDelay = webhookAudioBytesDelay.text;
}),

// AFTER
getUserWebhookUrl(type: 'audio_bytes').then((url) {
  if (url.isNotEmpty) {  // ✅ Only update if server has data!
    List<dynamic> parts = url.split(',');
    if (parts.length == 2) {
      webhookAudioBytes.text = parts[0].toString();
      webhookAudioBytesDelay.text = parts[1].toString();
    } else {
      webhookAudioBytes.text = url;
      webhookAudioBytesDelay.text = '5';
    }
    SharedPreferencesUtil().webhookAudioBytes = webhookAudioBytes.text;
    SharedPreferencesUtil().webhookAudioBytesDelay = webhookAudioBytesDelay.text;
  }  // ✅ If server returns empty, keep local values!
}),
```

**Applied to all webhook URLs:**
- `webhookAudioBytes` + `webhookAudioBytesDelay`
- `webhookOnTranscriptReceived`
- `webhookOnConversationCreated`
- `webhookDaySummary`

Now if the server returns empty strings, the local SharedPreferences values are preserved!

---

## Tests Added

**File:** `app/test/providers/developer_mode_provider_toggle_test.dart`

**15 comprehensive tests** verify both toggle and URL persistence behavior:

### Toggle Persistence Tests (11)
1. ✅ **Persist audioBytesToggled on toggle ON** - Immediate SharedPreferences write
2. ✅ **Persist audioBytesToggled on toggle OFF** - State cleared immediately
3. ✅ **Persist conversationEventsToggled** - Same pattern for all toggles
4. ✅ **Persist transcriptsToggled** - Verify all webhooks work
5. ✅ **Persist daySummaryToggled** - Complete coverage
6. ✅ **Load toggle states from SharedPreferences** - Initialization works
7. ✅ **Maintain toggle state after navigation** - Simulates page navigation
8. ✅ **API failure causes rollback** - Error handling works correctly
9. ✅ **Manual state persistence** - Direct SharedPreferences access works
10. ✅ **Multiple rapid toggles** - No race conditions
11. ✅ **Webhook URL + toggle both persist** - Integration test

### URL Persistence Tests (4 NEW)
12. ✅ **Webhook URL persists when set** - URLs survive provider recreation
13. ✅ **Webhook delay persists when set** - Delay value survives recreation
14. ✅ **All webhook URLs persist independently** - No cross-contamination
15. ✅ **Empty server response doesn't overwrite** - Local values preserved

**Test Runtime:** ~4 seconds
**All tests pass:** ✅ 15/15

---

## Running Tests

### Quick Test
```bash
cd app
flutter test test/providers/developer_mode_provider_toggle_test.dart
```

### Run All Developer Tests
```bash
cd app
flutter test test/backend/preferences_webhook_test.dart test/providers/developer_mode_provider_toggle_test.dart
```

---

## Files Modified

1. **`app/lib/providers/developer_mode_provider.dart`**
   - Made toggle callbacks async (lines 32-106)
   - Added immediate SharedPreferences persistence
   - Added error handling with rollback
   - Fixed initialize() race condition (lines 93-138)
   - Improved getWebhooksStatus() null handling (lines 108-122)

2. **`app/test/providers/developer_mode_provider_toggle_test.dart`** (created)
   - 11 comprehensive tests for toggle persistence
   - Tests cover normal operation, errors, navigation, and edge cases

---

## Verification

### Before Fixes:
1. Open Developer Settings
2. Toggle "Realtime Audio Bytes" ON
3. Enter webhook URL: `https://example.com/webhook`
4. Enter delay: `10`
5. Click "Save"
6. Navigate to home screen
7. Return to Developer Settings
8. ❌ **Toggle is OFF**
9. ❌ **URL field is EMPTY**
10. ❌ **Delay field is EMPTY**

### After Fixes:
1. Open Developer Settings
2. Toggle "Realtime Audio Bytes" ON
3. Enter webhook URL: `https://example.com/webhook`
4. Enter delay: `10`
5. Click "Save"
6. Navigate to home screen
7. Return to Developer Settings
8. ✅ **Toggle stays ON**
9. ✅ **URL field shows `https://example.com/webhook`**
10. ✅ **Delay field shows `10`**

---

## User Experience Improvements

### Immediate Feedback
- **Toggle state** persists **instantly** when changed (no Save needed)
- **URL fields** require clicking "Save" to persist
- Clear visual feedback via "Syncing..." banner during save

### Error Resilience
- If webhook enable/disable API fails, toggle automatically reverts
- If URL save API fails, error message shown and values not persisted
- User sees immediate visual feedback
- All errors logged for debugging

### Consistent State
- **Toggles:** Always match SharedPreferences, survive navigation and app restarts
- **URLs:** Preserved locally even if server returns empty values
- No more confusion between UI state and actual persisted state
- Offline-first approach - local values take precedence when server data is unavailable

---

## Technical Details

### State Flow (Before)
```
User toggles ON
  → Provider sets audioBytesToggled = true (in memory only)
  → Calls enableWebhook() (fire-and-forget, no await)
  → User clicks "Save"
  → URLs are saved to server
  → User navigates away
  → On return, initialize() fetches from server
  → Server returns audioBytesToggled = false (webhook never enabled)
  → Toggle reverts to OFF
```

### State Flow (After)
```
User toggles ON
  → Provider sets audioBytesToggled = true (in memory)
  → Provider saves to SharedPreferences immediately
  → Awaits enableWebhook() API call
    → Success: State stays true
    → Failure: Rolls back to false in both memory and SharedPreferences
  → User navigates away
  → On return, initialize() loads from SharedPreferences first
  → Then syncs with server (if available)
  → Toggle remains in correct state
```

---

## Related Issues

This fix resolves the same class of issues as:
- **WEBHOOK_URL_PERSISTENCE_FIX.md** - URL persistence (fixed 2025-10-19)
- Both bugs caused by missing `await` and fire-and-forget patterns

---

## Prevention Checklist

**For Future Development:**
- ✅ Always `await` async operations that modify state
- ✅ Persist critical UI state immediately, not just on "Save"
- ✅ Add error handling with rollback for all API calls
- ✅ Test navigation scenarios (page leave/return)
- ✅ Avoid race conditions in initialization
- ✅ Write tests for every state persistence scenario

---

**Fixed:** 2025-10-19
**Time Investment:** ~2 hours
**Impact:** Critical - affects all webhook toggle users
**Related:** WEBHOOK_URL_PERSISTENCE_FIX.md
