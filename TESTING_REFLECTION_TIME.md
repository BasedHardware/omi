# Daily Reflection Notification Time Setting - Testing Guide

## Overview
This feature adds user-facing settings to change the time of "reflection notifications" (daily reflection prompts) via in-app settings.

## What Changed

### Backend Changes
- **Database Layer** (`backend/database/notifications.py`):
  - Added `get_daily_reflection_hour_local()` - Retrieves user's preferred reflection hour
  - Added `set_daily_reflection_hour_local()` - Stores user's preferred reflection hour
  - Added `get_daily_reflection_enabled()` - Checks if reflection notifications are enabled
  - Added `set_daily_reflection_enabled()` - Enables/disables reflection notifications
  - Default hour: 21 (9 PM local time)

- **API Endpoints** (`backend/routers/users.py`):
  - `GET /v1/users/daily-reflection-settings` - Get current reflection notification settings
  - `PATCH /v1/users/daily-reflection-settings` - Update reflection notification settings
  - Settings include: `enabled` (boolean) and `hour` (0-23 in local time)

### App Changes
- **API Client** (`app/lib/backend/http/api/users.dart`):
  - Added `DailyReflectionSettings` model
  - Added `getDailyReflectionSettings()` - Fetch settings from backend
  - Added `setDailyReflectionSettings()` - Update settings on backend

- **Notification Scheduler** (`app/lib/services/notifications/daily_reflection_notification.dart`):
  - Updated `scheduleDailyNotification()` to accept configurable `hour` parameter
  - Added validation for hour (0-23)
  - Default remains 21 (9 PM) if not specified

- **Settings UI** (`app/lib/pages/settings/notifications_settings_page.dart`):
  - Added time picker UI for daily reflection (similar to daily summary)
  - Added hour state variable `_dailyReflectionHour`
  - Loads reflection settings from API on initialization
  - Time picker shows 12-hour format with AM/PM
  - Settings are disabled (grayed out) when reflection notifications are turned off
  - Updates backend immediately when time is changed

- **Other Updates**:
  - Updated home page, developer mode provider, and desktop settings to load hour from API
  - Added Mixpanel tracking for reflection time changes
  - Added localization key `dailyReflectionTime`

## How to Test

### Prerequisites
1. Have the Omi mobile app installed (iOS or Android)
2. Be logged in with a valid account
3. Have notification permissions granted

### Test Scenarios

#### Test 1: Default Behavior (Existing Users)
**Purpose**: Verify existing users maintain current behavior (9 PM notifications)

**Steps**:
1. Open the app
2. Navigate to Settings → Notifications
3. Verify Daily Reflection section shows:
   - Enable toggle: ON (default)
   - Time: 9:00 PM (default)

**Expected Result**: 
- Default time is 9:00 PM
- Notifications scheduled for 9 PM local time
- No breaking changes for existing users

---

#### Test 2: Change Reflection Time
**Purpose**: Verify users can change notification time

**Steps**:
1. Open the app
2. Navigate to Settings → Notifications
3. In the Daily Reflection section, tap on the time (shows current time, e.g., "9:00 PM")
4. A time picker modal should appear
5. Select a different time (e.g., 8:00 PM)
6. Tap "Done"

**Expected Result**:
- Time updates immediately in UI
- Settings saved to backend (check API: `GET /v1/users/daily-reflection-settings`)
- Notification rescheduled for new time
- Next notification arrives at new time

---

#### Test 3: Enable/Disable Reflection Notifications
**Purpose**: Verify toggle works and respects time setting

**Steps**:
1. Navigate to Settings → Notifications → Daily Reflection
2. Toggle OFF the "Enable" switch
3. Verify time selector becomes grayed out
4. Toggle ON the "Enable" switch
5. Verify time selector becomes active again

**Expected Result**:
- When disabled:
  - No notifications scheduled
  - Time picker is disabled (grayed out but still shows current time)
  - Backend updated (`enabled: false`)
- When re-enabled:
  - Notifications scheduled at previously set time
  - Time picker becomes active
  - Backend updated (`enabled: true`)

---

#### Test 4: Time Picker UI
**Purpose**: Verify time picker displays correctly

**Steps**:
1. Navigate to Settings → Notifications → Daily Reflection
2. Tap on the time to open picker
3. Scroll through hours (0-23 displayed as 12:00 AM - 11:00 PM)
4. Observe the picker UI

**Expected Result**:
- Modal appears with dark theme
- Shows "Cancel" and "Done" buttons
- Shows "Select time" header
- Displays all 24 hours in 12-hour format (12:00 AM, 1:00 AM, ..., 11:00 PM)
- Selected time is centered
- Can cancel without saving
- Can save with "Done"

---

#### Test 5: Validation
**Purpose**: Verify invalid values are rejected

**Steps**:
1. Try to set hour via API with invalid values:
   ```bash
   curl -X PATCH https://api.omi.me/v1/users/daily-reflection-settings \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"hour": 25}'
   ```

**Expected Result**:
- API returns 400 Bad Request
- Error message: "Hour must be between 0 and 23"
- Current setting unchanged

---

#### Test 6: Cross-Device Sync
**Purpose**: Verify settings sync across devices

**Steps**:
1. Login to same account on Device A and Device B
2. On Device A: Change reflection time to 10:00 PM
3. On Device B: Navigate to Settings → Notifications
4. Pull to refresh or restart app

**Expected Result**:
- Device B shows time as 10:00 PM
- Settings are synced via backend
- Notifications on both devices scheduled for 10 PM local time

---

#### Test 7: App Restart Persistence
**Purpose**: Verify settings survive app restart

**Steps**:
1. Set reflection time to 7:00 PM
2. Force close the app
3. Reopen the app
4. Navigate to Settings → Notifications → Daily Reflection

**Expected Result**:
- Time still shows 7:00 PM
- Settings loaded from backend on app start
- Notification still scheduled for 7 PM

---

#### Test 8: Notification Arrival Time
**Purpose**: Verify notifications arrive at correct time

**Steps**:
1. Set reflection time to a few minutes in the future (e.g., if it's 2:00 PM, set to 2:05 PM)
2. Wait for scheduled time
3. Observe notification arrival

**Expected Result**:
- Notification arrives at exactly the scheduled time
- Notification shows correct title and body
- Tapping notification opens chat with reflection prompt

---

#### Test 9: Background Operation
**Purpose**: Verify notifications work when app is closed/backgrounded

**Steps**:
1. Set reflection time to 1 minute from now
2. Close the app completely
3. Wait for scheduled time

**Expected Result**:
- Notification arrives even with app closed
- Notification shows correctly
- Tapping notification opens app to chat

---

#### Test 10: Multiple Time Changes
**Purpose**: Verify only latest time is used

**Steps**:
1. Set time to 8:00 PM
2. Immediately change to 9:00 PM
3. Change again to 10:00 PM
4. Check scheduled notifications

**Expected Result**:
- Only ONE notification scheduled (not 3)
- Scheduled for latest time (10:00 PM)
- Previous schedules cancelled

---

### API Testing

#### Get Reflection Settings
```bash
curl -X GET https://api.omi.me/v1/users/daily-reflection-settings \
  -H "Authorization: Bearer <your_token>"
```

Expected Response:
```json
{
  "enabled": true,
  "hour": 21
}
```

#### Update Reflection Settings - Enable/Disable
```bash
curl -X PATCH https://api.omi.me/v1/users/daily-reflection-settings \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

Expected Response:
```json
{
  "status": "ok"
}
```

#### Update Reflection Settings - Change Time
```bash
curl -X PATCH https://api.omi.me/v1/users/daily-reflection-settings \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{"hour": 20}'
```

Expected Response:
```json
{
  "status": "ok"
}
```

#### Update Both Settings
```bash
curl -X PATCH https://api.omi.me/v1/users/daily-reflection-settings \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "hour": 22}'
```

---

### Edge Cases

#### Edge Case 1: Timezone Changes
**Test**: User travels to different timezone
**Expected**: Notification still arrives at same local time (e.g., if set to 9 PM, arrives at 9 PM in new timezone)

#### Edge Case 2: Midnight Crossing
**Test**: Set time to 12:00 AM (midnight)
**Expected**: Notification arrives at midnight, picker shows "12:00 AM"

#### Edge Case 3: Noon
**Test**: Set time to 12:00 PM (noon)
**Expected**: Notification arrives at noon, picker shows "12:00 PM"

#### Edge Case 4: Network Failure During Save
**Test**: Disable network, change time, re-enable network
**Expected**: Setting saved locally, syncs when network returns

---

## Manual Verification Checklist

- [ ] Settings UI loads correctly with default values
- [ ] Time picker displays in 12-hour format
- [ ] Time picker can select any hour (12 AM - 11 PM)
- [ ] Cancel button closes picker without saving
- [ ] Done button saves and closes picker
- [ ] Settings persist after app restart
- [ ] Settings sync across devices
- [ ] Notifications arrive at scheduled time
- [ ] Notifications work when app is closed
- [ ] Enable/disable toggle works
- [ ] Time picker disabled when notifications disabled
- [ ] API endpoints return correct responses
- [ ] Invalid hours rejected by API (< 0 or > 23)
- [ ] Mixpanel tracking fires on changes
- [ ] No crashes or errors in logs

---

## Known Limitations

1. **Local Scheduling**: Notifications are scheduled locally on the device using the specified local time. If the device timezone changes, the notification will still arrive at the same "clock time" in the new timezone.

2. **iOS Background Limitations**: iOS may delay or throttle notifications if the app has been closed for extended periods. This is an iOS system behavior.

3. **Battery Optimization**: On Android, aggressive battery optimization settings may prevent notifications. Users may need to whitelist Omi.

---

## Rollback Plan

If issues are found, the feature can be safely disabled by:
1. Reverting the backend endpoints (notifications will fall back to local storage)
2. The default behavior (9 PM) remains functional
3. No data loss - settings stored in Firestore user documents

---

## Success Criteria

✅ Users can change reflection notification time via in-app settings
✅ Time picker UI is intuitive and matches existing settings patterns
✅ Settings persist across app restarts and devices
✅ Notifications arrive at the configured time
✅ Default behavior (9 PM) preserved for existing users
✅ No breaking changes to existing notification system
✅ Validation prevents invalid time values
✅ Backend API properly stores and retrieves settings
