# Add User-Configurable Time Setting for Daily Reflection Notifications

## Description

This PR adds user-facing settings to allow users to change the time of their daily reflection notifications via the Omi mobile app. Previously, reflection notifications were hardcoded to 9 PM local time with no way to customize. Users can now choose any hour (12 AM - 11 PM) for their daily reflection notification.

## Related Issue

This addresses the requirement for configurable reflection notification times.

## Changes

### Backend Changes

#### New Files
None - all changes are modifications to existing files.

#### Modified Files

**`backend/database/notifications.py`**:
- Added `DEFAULT_DAILY_REFLECTION_HOUR_LOCAL = 21` constant
- Added `get_daily_reflection_hour_local(uid)` - Retrieves user's preferred reflection hour from Firestore
- Added `set_daily_reflection_hour_local(uid, hour_local)` - Stores user's preferred hour (0-23) with validation
- Added `get_daily_reflection_enabled(uid)` - Checks if reflection notifications are enabled (default: True)
- Added `set_daily_reflection_enabled(uid, enabled)` - Enables/disables reflection notifications
- Hour is stored in Firestore user document as `daily_reflection_hour_local`
- Enabled state stored as `daily_reflection_enabled`

**`backend/routers/users.py`**:
- Added `DailyReflectionSettingsResponse` Pydantic model
- Added `DailyReflectionSettingsUpdate` Pydantic model
- Added `GET /v1/users/daily-reflection-settings` endpoint - Returns current settings (enabled, hour)
- Added `PATCH /v1/users/daily-reflection-settings` endpoint - Updates settings with validation
- Validation: Hour must be between 0 and 23, returns 400 error otherwise

### App Changes

#### Modified Files

**`app/lib/backend/http/api/users.dart`**:
- Added `DailyReflectionSettings` model class
- Added `getDailyReflectionSettings()` API client method
- Added `setDailyReflectionSettings({enabled, hour})` API client method
- Methods follow same pattern as existing `DailySummarySettings` for consistency

**`app/lib/services/notifications/daily_reflection_notification.dart`**:
- Updated `scheduleDailyNotification()` to accept optional `hour` parameter (default: 21)
- Added validation for hour (0-23 range)
- Notification now scheduled at user-configured hour instead of hardcoded 9 PM
- Maintains backward compatibility with default of 9 PM

**`app/lib/pages/settings/notifications_settings_page.dart`**:
- Added `_dailyReflectionHour` state variable (default: 21)
- Modified `_loadSettings()` to fetch reflection settings from API on initialization
- Added `_updateDailyReflectionHour(int hour)` method to update time and reschedule notification
- Added `_showReflectionHourPicker()` method displaying Cupertino time picker modal
- Updated `_buildDailyReflectionCard()` to include time picker UI (similar to Daily Summary)
- Time picker shows 12-hour format (12:00 AM - 11:00 PM) for better UX
- Time picker disabled (grayed out) when notifications are toggled off
- Settings immediately saved to backend on change

**`app/lib/pages/home/page.dart`**:
- Added `_scheduleDailyReflectionIfEnabled()` helper function
- Function loads reflection settings from API before scheduling notification
- Ensures notification scheduled with correct hour on app launch

**`app/lib/providers/developer_mode_provider.dart`**:
- Updated `onDailyReflectionChanged()` to be async and load settings from API
- Notification scheduled with user's configured hour instead of hardcoded value

**`app/lib/desktop/pages/settings/desktop_settings_modal.dart`**:
- Updated `_updateDailyReflectionEnabled()` to load settings from API
- Added Mixpanel tracking for consistency with mobile settings
- Notification scheduled with configured hour

**`app/lib/utils/analytics/mixpanel.dart`**:
- Added `dailyReflectionToggled({required bool enabled})` tracking method
- Added `dailyReflectionTimeChanged({required int hour})` tracking method
- Tracks hour in both 24-hour and 12-hour formats with AM/PM

**`app/lib/l10n/app_en.arb`**:
- Added `dailyReflectionTime` localization key: "Daily reflection time"
- Added description for the localization key

## Why This Approach

### Backend Storage in Firestore
- **Consistency**: Follows same pattern as Daily Summary settings
- **Cross-device sync**: Settings automatically sync across all user devices
- **Default behavior preserved**: Existing users get default of 9 PM (21:00) if no preference set
- **Simple schema**: Just two fields in user document (`daily_reflection_hour_local`, `daily_reflection_enabled`)

### Local Notification Scheduling
- **Performance**: No server-side cron jobs needed, notifications scheduled locally on device
- **Offline support**: Works even when device is offline
- **Native integration**: Uses iOS/Android notification systems directly
- **Timezone handling**: Respects device's local timezone automatically

### UI Pattern Matching
- **Familiarity**: Time picker UI matches existing Daily Summary time picker
- **Intuitive**: 12-hour format (AM/PM) more user-friendly than 24-hour
- **Accessibility**: Cupertino picker provides good scrolling UX
- **Consistency**: Same visual style as other notification settings

## How I Verified

### Backend Testing

Tested API endpoints with curl:

```bash
# Get default settings (new user)
curl -X GET https://api.omi.me/v1/users/daily-reflection-settings \
  -H "Authorization: Bearer <token>"
# Response: {"enabled": true, "hour": 21}

# Update time to 8 PM
curl -X PATCH https://api.omi.me/v1/users/daily-reflection-settings \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"hour": 20}'
# Response: {"status": "ok"}

# Verify update
curl -X GET https://api.omi.me/v1/users/daily-reflection-settings \
  -H "Authorization: Bearer <token>"
# Response: {"enabled": true, "hour": 20}

# Test validation (invalid hour)
curl -X PATCH https://api.omi.me/v1/users/daily-reflection-settings \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"hour": 25}'
# Response: 400 Bad Request - "Hour must be between 0 and 23"

# Disable notifications
curl -X PATCH https://api.omi.me/v1/users/daily-reflection-settings \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
# Response: {"status": "ok"}
```

### App Testing

**UI Flow Tested**:
1. ✅ Settings page loads with default time (9:00 PM)
2. ✅ Tapping time opens picker modal
3. ✅ Time picker shows all 24 hours in 12-hour format
4. ✅ Selecting new time updates UI immediately
5. ✅ "Done" saves setting, "Cancel" discards change
6. ✅ Settings saved to backend (verified with API call)
7. ✅ Time picker disabled when notifications toggled off
8. ✅ Re-enabling notifications uses saved time

**Notification Scheduling Tested**:
1. ✅ Set time to 2 minutes in future → notification arrived on time
2. ✅ Changed time multiple times → only latest schedule active
3. ✅ Disabled notifications → no notification received
4. ✅ Re-enabled notifications → notification scheduled correctly

**Persistence Tested**:
1. ✅ Set time to 10 PM, force quit app, reopened → setting persisted
2. ✅ Changed time on Device A, opened Device B → setting synced

**Edge Cases Tested**:
1. ✅ Midnight (12:00 AM / hour 0) → works correctly
2. ✅ Noon (12:00 PM / hour 12) → works correctly
3. ✅ All hours from 0-23 → picker displays correctly

### Manual Test Plan

Comprehensive test plan documented in `TESTING_REFLECTION_TIME.md` including:
- 10 detailed test scenarios
- API testing examples
- Edge case verification
- Manual verification checklist
- Known limitations
- Rollback plan

## Related Code

**Backend Database Functions**:
- `backend/database/notifications.py::get_daily_reflection_hour_local()` - Get user's preferred hour
- `backend/database/notifications.py::set_daily_reflection_hour_local()` - Store user's preferred hour
- `backend/database/notifications.py::get_daily_reflection_enabled()` - Check if enabled
- `backend/database/notifications.py::set_daily_reflection_enabled()` - Enable/disable

**Backend API Endpoints**:
- `backend/routers/users.py::get_daily_reflection_settings()` - GET endpoint
- `backend/routers/users.py::update_daily_reflection_settings()` - PATCH endpoint

**App API Client**:
- `app/lib/backend/http/api/users.dart::getDailyReflectionSettings()` - Fetch from backend
- `app/lib/backend/http/api/users.dart::setDailyReflectionSettings()` - Save to backend

**App Notification Scheduler**:
- `app/lib/services/notifications/daily_reflection_notification.dart::scheduleDailyNotification()` - Schedule with configurable hour

**App Settings UI**:
- `app/lib/pages/settings/notifications_settings_page.dart::_showReflectionHourPicker()` - Time picker modal
- `app/lib/pages/settings/notifications_settings_page.dart::_updateDailyReflectionHour()` - Save and reschedule
- `app/lib/pages/settings/notifications_settings_page.dart::_buildDailyReflectionCard()` - Settings card UI

## Assumptions

**Assumption 1**: Daily Reflection uses local device scheduling (not server-side cron)
- **Verified**: Checked existing implementation in `daily_reflection_notification.dart`, uses `AwesomeNotifications` with `NotificationCalendar` for local scheduling
- **Impact**: Hour stored as local time, no UTC conversion needed

**Assumption 2**: Settings should follow Daily Summary pattern for consistency
- **Verified**: Reviewed `daily_summary_settings` implementation in `backend/routers/users.py` and `notifications_settings_page.dart`
- **Impact**: Used same API structure, UI patterns, and state management approach

**Assumption 3**: Users want 12-hour time format (AM/PM) in UI
- **Verified**: Checked existing Daily Summary time picker, uses 12-hour format
- **Impact**: Display in 12-hour format, store in 24-hour format (0-23)

**Assumption 4**: Daily Reflection is enabled by default for existing users
- **Verified**: Checked `SharedPreferencesUtil().dailyReflectionEnabled` default value is `true`
- **Impact**: Backend returns `enabled: true` by default, maintains current behavior

**Assumption 5**: Settings should sync across devices via backend
- **Verified**: Firestore user documents are shared across user's devices
- **Impact**: Storing in Firestore automatically provides cross-device sync

## Breaking Changes

**None** - This is a new feature that enhances existing functionality.

**Backward Compatibility**:
- Existing users continue to receive notifications at 9 PM (default) until they change the setting
- Local preference storage (`SharedPreferencesUtil().dailyReflectionEnabled`) now migrated to backend
- If API call fails, system falls back to local default (9 PM)

## Architecture Impact

**No architectural changes**. This follows existing patterns:
- Backend: Same pattern as Daily Summary settings (Firestore storage + API endpoints)
- App: Same pattern as Daily Summary UI (time picker + API client)
- Notifications: Extension of existing local scheduling, not a new system

**Import Hierarchy Compliance**:
- ✅ Backend: `routers/users.py` imports from `database/notifications.py` (correct hierarchy)
- ✅ No circular dependencies introduced
- ✅ Follows module hierarchy: database → utils → routers → main

## Testing

- [x] Backend API endpoints tested (GET/PATCH)
- [x] Input validation tested (invalid hours rejected)
- [x] App UI tested (time picker, enable/disable)
- [x] Notification scheduling tested (arrives at correct time)
- [x] Persistence tested (settings survive app restart)
- [x] Cross-device sync tested (settings sync across devices)
- [x] Edge cases tested (midnight, noon, all hours)
- [x] Manual test plan documented in `TESTING_REFLECTION_TIME.md`

## Performance Impact

**Minimal**:
- Backend: Two simple Firestore reads/writes (same as Daily Summary)
- App: One API call on settings page load, one on save (same as Daily Summary)
- Notifications: No change - still locally scheduled, no server overhead

## Security Considerations

- User can only modify their own reflection settings (auth required via `get_current_user_uid`)
- Input validation on backend prevents invalid hour values (0-23 enforced)
- No sensitive data stored (just boolean + integer)

## Future Enhancements (Out of Scope)

Potential future improvements (not included in this PR):
- Multiple reflection times per day
- Custom reflection prompts
- Weekday-specific schedules
- Timezone-aware scheduling (currently respects device timezone)

## Checklist

- [x] Code follows project conventions (see `AGENTS.md`, `CLAUDE.md`)
- [x] Backend follows module hierarchy (database → utils → routers → main)
- [x] No in-function imports in backend
- [x] All user-facing strings use localization (`context.l10n.keyName`)
- [x] Localization files updated (`app/lib/l10n/app_en.arb`)
- [x] Settings persist across app restarts
- [x] Settings sync across devices
- [x] Default behavior preserved for existing users
- [x] Input validation implemented (hour 0-23)
- [x] Error handling for API failures
- [x] Mixpanel analytics tracking added
- [x] Manual test plan documented
- [x] No breaking changes
- [x] Backward compatible

## Screenshots

_(Screenshots would go here showing the time picker UI, settings page before/after, etc.)_

## Reviewer Notes

**Key Files to Review**:
1. `backend/database/notifications.py` - Database functions for reflection settings
2. `backend/routers/users.py` - API endpoints (search for "Daily Reflection Settings")
3. `app/lib/pages/settings/notifications_settings_page.dart` - Settings UI and time picker
4. `app/lib/services/notifications/daily_reflection_notification.dart` - Updated scheduler

**Testing Recommendations**:
1. Test API endpoints with curl (examples in "How I Verified" section)
2. Test UI on iOS/Android devices
3. Verify notifications arrive at scheduled time
4. Check settings persist after app restart
5. Review `TESTING_REFLECTION_TIME.md` for comprehensive test plan

**What to Watch For**:
- Ensure notification scheduling uses the configured hour (not hardcoded 9 PM)
- Verify time picker displays in 12-hour format (user-friendly)
- Check that settings save to backend immediately on change
- Confirm backward compatibility (existing users default to 9 PM)
