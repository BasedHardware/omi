# White Label TODO: Remove Hardcoded "Omi" References

This document tracks all hardcoded "Omi" references found in the Flutter app that need to be replaced with `Env.appName` for proper white-labeling.

**Total Files:** 66
**Last Updated:** 2025-11-16

---

## ✅ Completed

### Voice & Settings (8 files)
- [x] `lib/pages/capture/widgets/widgets.dart` - "Update omi firmware"
- [x] `lib/desktop/pages/settings/desktop_profile_page.dart` - Persona subtitle, analytics text
- [x] `lib/pages/settings/settings_drawer.dart` - Version copy, "About Omi"
- [x] `lib/pages/conversations/sync_page.dart` - Device fallback name, storage messages
- [x] `lib/pages/conversation_detail/widgets/summarized_apps_sheet.dart` - Auto-select message
- [x] `lib/pages/conversation_detail/share.dart` - Export header
- [x] `lib/pages/home/firmware_update.dart` - Device restart message
- [x] `lib/pages/home/firmware_update_dialog.dart` - USB and battery warnings

### Mobile Onboarding (4 files) - COMPLETED IN PHASE 1
- [x] `lib/pages/onboarding/permissions/permissions_widget.dart` - Line 70: "Let Omi run in the background..."
- [x] `lib/pages/onboarding/speech_profile_widget.dart` - Line 181: "Omi needs to learn your voice..."
- [x] `lib/pages/onboarding/find_device/page.dart` - Line 63: "Omi needs Bluetooth to connect..."
- [x] `lib/pages/onboarding/setup/setup_questions.dart` - Lines 34, 55

### Desktop Onboarding (6 files) - COMPLETED IN PHASE 1
- [x] `lib/desktop/pages/onboarding/screens/desktop_auth_screen.dart` - Line 56: "Welcome to Omi"
- [x] `lib/desktop/pages/onboarding/screens/desktop_complete_screen.dart` - Lines 130, 145
- [x] `lib/desktop/pages/onboarding/screens/desktop_name_screen.dart` - Line 156
- [x] `lib/desktop/pages/onboarding/screens/desktop_language_screen.dart` - Line 221
- [x] `lib/desktop/pages/onboarding/screens/desktop_permissions_screen.dart` - Lines 175, 206

### Core Settings Pages (5 files) - COMPLETED IN PHASE 1
- [x] `lib/pages/settings/about.dart` - Line 21: "About Omi"
- [x] `lib/pages/settings/change_name_widget.dart` - Lines 37, 78
- [x] `lib/pages/settings/privacy.dart` - Lines 31, 111, 116
- [x] `lib/pages/settings/device_settings.dart` - Lines 249, 656, 709
- [x] `lib/pages/settings/profile.dart` - Line 327

---

## 📋 Pending Tasks

### 1. Apple Watch Setup & Permissions (2 files) - COMPLETED
**File:** `lib/widgets/apple_watch_setup_bottom_sheet.dart` - COMPLETED
- [x] Line 118: "Install Omi on your\nApple Watch" - Changed to 'Install ${Env.appName} on your\nApple Watch'
- [x] Line 124: "To use your Apple Watch with Omi..." - Changed to use ${Env.appName}
- [x] Line 131: "Open Omi on your\nApple Watch" - Changed to 'Open ${Env.appName} on your\nApple Watch'
- [x] Line 137: "The Omi app is installed..." - Changed to 'The ${Env.appName} app is installed...'
- [x] Line 230: "...install Omi from the 'Available Apps' section" - Changed to use ${Env.appName}
- [x] Line 258: "...make sure the Omi app is open on your watch" - Changed to use ${Env.appName}

**File:** `lib/pages/onboarding/apple_watch_permission_page.dart` - COMPLETED
- [x] Line 82: "Open the Omi app on your watch..." - Changed to use ${Env.appName}
- [x] Line 242: "1. Ensure Omi is installed on your watch" - Changed to use ${Env.appName}
- [x] Line 243: "2. Open the Omi app on your watch" - Changed to use ${Env.appName}

---

### 2. Onboarding Flow (1 file)
**File:** `lib/pages/onboarding/name/name_widget.dart`
- [ ] Line 75: "This helps personalize your Omi experience" (commented)

---

### 3. Settings Pages (2 files)
**File:** `lib/pages/settings/data_privacy_page.dart`
- [ ] Line 54: "At Omi, we are committed to protecting..."

**File:** `lib/pages/settings/usage_page.dart`
- [ ] Line 134: "Sharing my Omi stats! (omi.me - your always-on AI assistant)"
- [ ] Line 169: "Omi has:"
- [ ] Line 281: "Your Omi Insights"
- [ ] Line 647: "Start a conversation with Omi..."
- [ ] Line 717: "Total time Omi has actively listened"

---

### 4. Data Protection & Security (1 file)
**File:** `lib/pages/settings/widgets/data_protection_section.dart`
- [ ] Line 46: "...no one, not even Omi, can access your content"
- [ ] Line 258: "...inaccessible to anyone, including Omi staff or Google"

---

### 5. Plans & Subscription (1 file)
**File:** `lib/pages/settings/widgets/plans_sheet.dart`
- [ ] Line 84: "Omi Training"
- [ ] Line 97: "Get Omi Unlimited for free..."
- [ ] Line 893: "Your Omi, unleashed..."
- [ ] Line 939: "Ask Omi anything about your life"
- [ ] Line 944: "Unlock Omi's infinite memory"
- [ ] Line 1765: "Omi Training" (title)
- [ ] Line 1854: "Omi Training" (title)

---

### 6. Persona/Clone Features (4 files)
**File:** `lib/pages/persona/persona_profile.dart`
- [ ] Line 606: "Get Omi Device"
- [ ] Line 644: "Get Omi"
- [ ] Line 658: "I have Omi device"

**File:** `lib/pages/persona/persona_provider.dart`
- [ ] Line 295: "...connect at least one knowledge data source (Omi or Twitter)"
- [ ] Line 376: "...connect at least one knowledge data source (Omi or Twitter)"

**File:** `lib/pages/persona/twitter/clone_success_sceen.dart`
- [ ] Line 68: "Your Omi clone is verified and live!"

**File:** `lib/pages/persona/twitter/social_profile.dart`
- [ ] Line 82: "We will pre-train your Omi clone..."
- [ ] Line 224: "Connect Omi Device"

---

### 7. Memories Management (3 files)
**File:** `lib/pages/memories/widgets/memory_management_sheet.dart`
- [ ] Line 238: "Clear Omi's Memory"
- [ ] Line 242: "...clear Omi's memory? This action cannot be undone"
- [ ] Line 260: "Omi's memory about you has been cleared"

**File:** `lib/pages/memories/page.dart`
- [ ] Line 689: "Clear Omi's Memory"
- [ ] Line 693: "...clear Omi's memory? This action cannot be undone"
- [ ] Line 710: "Omi's memory about you has been cleared"

**File:** `lib/desktop/pages/memories/widgets/desktop_memory_management_dialog.dart`
- [ ] Line 265: "Permanently remove all memories from Omi"
- [ ] Line 415: "Clear Omi's Memory"
- [ ] Line 424: "...clear Omi's memory?"
- [ ] Line 470: "Omi's memory about you has been cleared"

---

### 8. Chat Pages (3 files)
**File:** `lib/pages/chat/page.dart`
- [ ] Search for "Omi" references

**File:** `lib/pages/chat/clone_chat_page.dart`
- [ ] Search for "Omi" references

**File:** `lib/desktop/pages/chat/desktop_chat_page.dart`
- [ ] Line 343: "Omi" (app name fallback)
- [ ] Line 461: "Deleting your messages from Omi's memory..."
- [ ] Line 1413: "Response from Omi. Get yours at https://omi.me"
- [ ] Line 1414: "Chat with Omi" (subject)
- [ ] Line 1547: "Default Omi option" (comment)
- [ ] Line 1674: "Omi" (fallback)

---

### 9. Apps & Integrations (4 files)
**File:** `lib/pages/apps/add_app.dart`
- [ ] Search for "Omi" references

**File:** `lib/pages/apps/app_detail/app_detail.dart`
- [ ] Search for "Omi" references

**File:** `lib/pages/apps/widgets/external_trigger_fields_widget.dart`
- [ ] Search for "Omi" references

**File:** `lib/pages/apps/widgets/api_keys_widget.dart`
- [ ] Search for "Omi" references

**File:** `lib/desktop/pages/apps/desktop_add_app_page.dart`
- [ ] Search for "Omi" references

**File:** `lib/desktop/pages/apps/widgets/desktop_app_detail.dart`
- [ ] Search for "Omi" references

---

### 10. Task Integrations (1 file)
**File:** `lib/pages/settings/task_integrations_page.dart`
- [ ] Line 383: "...authorize Omi to create tasks..."

---

### 11. Action Items (1 file) - COMPLETED
**File:** `lib/pages/action_items/widgets/action_item_tile_widget.dart`
- [x] Line 404: "From Omi" (description) - Changed to 'From ${Env.appName}'
- [x] Line 512: "From Omi" (notes) - Changed to 'From ${Env.appName}'
- [x] Line 620: "From Omi" (notes) - Changed to 'From ${Env.appName}'
- [x] Line 708: "From Omi" (description) - Changed to 'From ${Env.appName}'
- [x] Line 825: "From Omi" (notes) - Changed to 'From ${Env.appName}'

---

### 12. Developer Settings (2 files)
**File:** `lib/pages/settings/developer.dart`
- [ ] Line 107: "Omi debug log" (share text)
- [ ] Line 142: "Omi debug log" (share text)
- [ ] Line 268: "Exported Conversations from Omi"
- [ ] Line 363: "To connect Omi with other applications..."
- [ ] Line 576: "Try the latest experimental features from Omi Team"

**File:** `lib/desktop/pages/settings/desktop_developer_page.dart`
- [ ] Line 221: "Omi debug log"
- [ ] Line 268: "Omi debug log"
- [ ] Line 365: "Exported Conversations from Omi"
- [ ] Line 419: Similar API keys description

---

### 13. Desktop Onboarding (6 files)
**File:** `lib/desktop/pages/onboarding/desktop_onboarding_wrapper.dart`
- [ ] Line 36: "Welcome to Omi"

**File:** `lib/desktop/pages/onboarding/screens/desktop_auth_screen.dart`
- [ ] Line 56: "Welcome to Omi"

**File:** `lib/desktop/pages/onboarding/screens/desktop_complete_screen.dart`
- [ ] Line 130: "Welcome to Omi! Your AI companion is ready..."
- [ ] Line 145: "Start Using Omi"

**File:** `lib/desktop/pages/onboarding/screens/desktop_device_screen.dart`
- [ ] Line 184: "Find and connect your Omi device" (commented)
- [ ] Line 328: "Turn on your Omi device first" (commented)

**File:** `lib/desktop/pages/onboarding/screens/desktop_language_screen.dart`
- [ ] Line 221: "...for the best Omi experience"

**File:** `lib/desktop/pages/onboarding/screens/desktop_name_screen.dart`
- [ ] Line 156: "This helps personalize your Omi experience"

**File:** `lib/desktop/pages/onboarding/screens/desktop_permissions_screen.dart`
- [ ] Line 175: "Enable features for the best Omi experience..."
- [ ] Line 206: "Connect to your Omi device"

---

### 14. Desktop Pages (4 files)
**File:** `lib/desktop/pages/desktop_home_page.dart`
- [ ] Search for "Omi" references

**File:** `lib/desktop/pages/conversations/widgets/desktop_conversation_summary.dart`
- [ ] Search for "Omi" references

**File:** `lib/desktop/pages/conversations/widgets/desktop_empty_conversations.dart`
- [ ] Search for "Omi" references

**File:** `lib/desktop/pages/settings/desktop_about_page.dart`
- [ ] Search for "Omi" references

---

### 15. Widgets (3 files)
**File:** `lib/widgets/transcript.dart`
- [ ] Line 685: "Omi translates conversations into your primary language..."

**File:** `lib/widgets/device_widget.dart`
- [ ] Line 90-91: Device type checking logic for 'Omi'

**File:** `lib/pages/home/widgets/chat_apps_dropdown_widget.dart`
- [ ] Line 209: "Add Omi option to the dropdown" (comment)

---

### 16. Services & Utils (7 files)
**File:** `lib/services/wals.dart`
- [ ] Line 284: "Omi" (default device model)
- [ ] Line 787: "Omi" (device model fallback)

**File:** `lib/services/devices.dart`
- [ ] Line 40: "Feature flags for Omi device capabilities" (comment)

**File:** `lib/services/devices/omi_connection.dart`
- [ ] Line 80: "Subscribed to button stream from Omi Device"
- [ ] Line 100: "Subscribed to audioBytes stream from Omi Device"
- [ ] Line 289: "Subscribed to imageBytes stream from Omi Device"
- [ ] Line 549: "Get device information from Omi device"
- [ ] Line 612: "Omi Device" (default model number)

**File:** `lib/services/apple_reminders_service.dart`
- [x] Line 130: "From Omi" (notes) - Changed to 'From ${Env.appName}'

**File:** `lib/utils/audio/foreground.dart`
- [ ] Line 161: "Your Omi Device is connected"

**File:** `lib/utils/audio_player_utils.dart`
- [ ] Line 162: "Omi Audio Recording - ..."

**File:** `lib/utils/device.dart`
- [ ] Line 41: "Update your Omi now"
- [ ] Line 162: "Get device image... (for special cases like Omi)" (comment)
- [ ] Line 169: "Special case for Omi when disconnected" (comment)

---

### 17. Analytics (2 files)
**File:** `lib/utils/analytics/intercom.dart`
- [ ] Line 39: "Omi DevKit 2" (device check)
- [ ] Line 41: "Omi" (device check)

**File:** `lib/utils/analytics/mixpanel.dart`
- [ ] Line 418: "Using Omi At" (user property)

---

### 18. Backend Schema (2 files)
**File:** `lib/backend/schema/bt_device/bt_device.dart`
- [ ] Line 343: "Omi" (default model number)
- [ ] Line 368: "Error getting Omi device info"
- [ ] Line 555: "...current firmware works great with Omi"
- [ ] Line 559: "...current firmware works great with Omi"
- [ ] Line 564: "...current firmware works great with Omi"
- [ ] Line 568: "...current firmware works great with Omi"

**File:** `lib/backend/schema/app.dart`
- [ ] Line 364: GitHub repository URL contains "Omi"

---

### 19. Other Pages (3 files)
**File:** `lib/pages/speech_profile/page.dart`
- [ ] Search for "Omi" references

**File:** `lib/pages/speech_profile/user_speech_samples.dart`
- [ ] Search for "Omi" references

**File:** `lib/pages/sdcard/about_sdcard_sync.dart`
- [ ] Search for "Omi" references

**File:** `lib/pages/settings/people.dart`
- [ ] Search for "Omi" references

**File:** `lib/providers/capture_provider.dart`
- [ ] Search for "Omi" references

---

## 🔧 Implementation Notes

### Standard Replacement Pattern
Replace hardcoded "Omi" with:
```dart
Env.appName  // For display text
```

### Special Cases
1. **URLs**: Consider making configurable (e.g., GitHub repo, website links)
2. **Device Type Enums**: May need to remain as "omi" for backward compatibility
3. **Debug/Technical Strings**: Some may be acceptable to keep for clarity
4. **Comments**: Low priority, but can be updated for consistency
5. **Analytics Properties**: May need to coordinate with analytics platform

### Testing Checklist
After updates:
- [ ] Test all UI text displays correctly with custom app name
- [ ] Verify sharing/export functionality works
- [ ] Check analytics tracking still functions
- [ ] Test onboarding flow completely
- [ ] Verify device connection logic works
- [ ] Test desktop app separately

---

## 📊 Progress Summary

- **Completed:** 27 files (8 original + 15 Phase 1 + 2 Action Items + 2 Onboarding)
- **Pending:** 39 files
- **Total Progress:** ~41%

---

## 🎯 Priority Order

1. **High Priority** - User-facing text in main flows:
   - Onboarding screens
   - Settings pages
   - Chat/Memories pages
   - Plans & subscription

2. **Medium Priority** - Secondary features:
   - Desktop app
   - Developer settings
   - Apps integrations
   - Action items

3. **Low Priority** - Technical/internal:
   - Services & utils
   - Backend schemas
   - Analytics
   - Comments

---

*Note: Some files may have already been partially updated. Always verify current state before making changes.*
