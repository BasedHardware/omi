# PRD v2: Localization of Hardcoded Strings in Omi Flutter App

**Status:** IN PROGRESS
**Created:** 2026-01-20
**Last Updated:** 2026-01-21
**Version:** 2.0

## Overview

This document outlines the requirements for localizing hardcoded user-facing strings found in the Omi Flutter app. A comprehensive audit identified **~200+ hardcoded strings** across **~45 files** that need to be migrated to Flutter's l10n system.

This is an updated version of the original PRD, incorporating newly discovered files and the PRIORITY 0 task for translating pre-existing untranslated keys.

## Background

The app uses Flutter's ARB-based localization system (`context.l10n.keyName`). While much of the app is localized, an audit revealed significant gaps in newer features, providers, and some overlooked areas.

## Scope

### In Scope
- User-facing text (labels, titles, messages, buttons)
- Error messages and validation messages
- Success/status messages
- Notification titles and bodies
- Dialog content and titles
- Text field placeholders (hintText)
- Onboarding step titles
- SnackBar messages
- AppSnackbar messages in providers

### Out of Scope
- Technical strings (API keys, log tags, debug messages)
- Generated files (`.g.dart`, `.gen.dart`)
- l10n/ folder contents
- Emoji-only strings
- Single characters/punctuation
- URLs and emails displayed as data (not labels)
- Commented-out code

## Files Requiring Localization

### PRIORITY 0: Pre-existing Untranslated Keys (~89 keys × 33 languages)
**Status: IN PROGRESS**

~89 keys in non-English ARB files contain English text instead of proper translations. This affects all non-English users.

**Progress:**
| Language | Status |
|----------|--------|
| Spanish (es) | COMPLETED - 89 keys translated |
| French (fr) | COMPLETED - 89 keys translated |
| German (de) | COMPLETED - 110 keys translated |
| Other languages (30) | PENDING |

---

### PRIORITY 1: High Impact - Completed Files (From Original PRD)

| File | Strings | Status |
|------|---------|--------|
| `pages/conversation_detail/widgets/create_template_bottom_sheet.dart` | ~20 | COMPLETED |
| `pages/apps/providers/add_app_provider.dart` | ~20 | COMPLETED |
| `pages/persona/persona_provider.dart` | ~15 | COMPLETED |
| `pages/payments/payment_method_provider.dart` | 3 | COMPLETED |
| `pages/payments/paypal_setup_page.dart` | 2 | COMPLETED |
| `pages/payments/models/payment_method_config.dart` | 5 | COMPLETED |

---

### PRIORITY 2: Medium Impact - Completed Files

| File | Strings | Status |
|------|---------|--------|
| `pages/settings/widgets/plans_sheet.dart` | 7 | COMPLETED |
| `pages/settings/ai_app_generator_provider.dart` | 9 | COMPLETED |
| `pages/settings/ai_app_generator_page.dart` | 1 | COMPLETED |
| `pages/settings/transcription_settings_page.dart` | 2 | COMPLETED |
| `pages/settings/import_history_page.dart` | 2 | COMPLETED |
| `pages/apps/app_detail/app_detail.dart` | 1 | COMPLETED |
| `pages/persona/twitter/social_profile.dart` | 7 | COMPLETED |
| `pages/apps/widgets/payment_details_widget.dart` | 5 | COMPLETED |

---

### PRIORITY 3: Notifications & Services - Completed

| File | Strings | Status |
|------|---------|--------|
| `services/notifications/merge_notification_handler.dart` | 2 | COMPLETED |
| `services/notifications/daily_reflection_notification.dart` | 2 | COMPLETED |
| `services/notifications/action_item_notification_handler.dart` | 1 | COMPLETED |
| `services/devices/device_connection.dart` | 2 | COMPLETED |
| `services/devices/models.dart` | 1 | N/A (debug log) |

---

### PRIORITY 4: Desktop - Completed

| File | Strings | Status |
|------|---------|--------|
| `desktop/pages/onboarding/desktop_onboarding_wrapper.dart` | 10 | COMPLETED |
| `desktop/pages/settings/desktop_settings_modal.dart` | 2 | N/A (URLs/emails) |
| `desktop/pages/conversations/widgets/desktop_name_speaker_dialog.dart` | 10 | COMPLETED |

---

### PRIORITY 5: Lower Impact - Completed

| File | Strings | Status |
|------|---------|--------|
| `pages/conversation_detail/page.dart` | 1 | COMPLETED |
| `pages/conversations/widgets/goal_tracker_widget.dart` | 1 | COMPLETED |
| `main.dart` | 1 | N/A (const before init) |

---

### NEW - PRIORITY 6: Newly Discovered Files (~80 strings)

#### 6.1 Core App Shell & Providers (~50 strings)

| File | Est. Strings | Description |
|------|--------------|-------------|
| `core/app_shell.dart` | ~25 | COMPLETED - Integration connection success/error messages |
| `providers/auth_provider.dart` | ~8 | COMPLETED - Authentication error messages (Google, Apple, Firebase) |
| `providers/onboarding_provider.dart` | ~10 | COMPLETED - Permission error messages (Bluetooth, Microphone, Screen Capture, Accessibility, Notification) |
| `providers/message_provider.dart` | ~12 | COMPLETED - Camera/photo/file picker error messages |
| `providers/capture_provider.dart` | ~5 | COMPLETED - Recording error messages |
| `providers/developer_mode_provider.dart` | ~5 | COMPLETED - Webhook validation errors |
| `providers/voice_recorder_provider.dart` | 1 | COMPLETED - Transcription error |

#### 6.2 UI Components (~25 strings)

| File | Est. Strings | Description |
|------|--------------|-------------|
| `pages/settings/widgets/plans_sheet.dart` | 3 | COMPLETED - Cancel Subscription, Omi Training localized |
| `pages/conversations/sync_widgets/location_permission_dialog.dart` | 4 | COMPLETED - Location permission dialog text |
| `pages/conversations/widgets/merge_action_bar.dart` | 1 | COMPLETED - Reused existing `ok` key |
| `pages/conversations/widgets/conversation_list_item.dart` | ~12 | COMPLETED - Delete dialogs, New indicator, photos count, upgrade overlay, merging status |

#### 6.3 PDF Export Strings (~10 strings)

| File | Est. Strings | Description |
|------|--------------|-------------|
| `pages/conversation_detail/share.dart` | ~10 | COMPLETED - PDF export labels (Transcript Export, Conversation Export, Title, Overview, Action Items, Summary) |

#### 6.4 Date/Time Utility Strings (~16 strings)

| File | Est. Strings | Description |
|------|--------------|-------------|
| `utils/other/time_utils.dart` | ~16 | COMPLETED - Time duration strings (secs, mins, hours, days) for human-readable and compact formats |
| `pages/conversations/widgets/date_list_item.dart` | 1 | COMPLETED - Pass locale to dateTimeFormat() for proper date formatting |

#### 6.5 DateFormat Locale Fixes

| File | Lines Fixed | Description |
|------|-------------|-------------|
| `desktop/pages/settings/desktop_settings_modal.dart` | 2 | COMPLETED - DateFormat('EEEE, MMMM d'), DateFormat('h:mm a') |
| `pages/settings/calendar_settings_page.dart` | 2 | COMPLETED - DateFormat('EEEE, MMMM d'), DateFormat('h:mm a') |
| `pages/settings/usage_page.dart` | 4 | COMPLETED - DateFormat.Hm(), DateFormat('d'), DateFormat('MMM'), DateFormat.y() |
| `pages/conversations/widgets/score_widget.dart` | 1 | COMPLETED - DateFormat('E') |
| `pages/apps/widgets/api_keys_widget.dart` | 1 | COMPLETED - DateFormat('MMM d, yyyy HH:mm') |
| `desktop/pages/conversations/desktop_conversations_page.dart` | 3 | COMPLETED - DateFormat('MMM d'), DateFormat('MMM d, yyyy'), DateFormat('EEE, MMM d') |
| `pages/conversations/widgets/conversation_list_item.dart` | 2 | COMPLETED - dateTimeFormat('h:mm a') x2 |

---

## Requirements

### Functional Requirements

1. **FR-1**: All hardcoded user-facing strings must be replaced with `context.l10n.keyName` pattern
2. **FR-2**: New localization keys must be added to all 34 supported language ARB files
3. **FR-3**: **CRITICAL - Translation Requirement**: All new l10n keys MUST be properly translated to each target language. Do NOT copy English text to non-English ARB files.
4. **FR-4**: Translations must be culturally appropriate for each language
5. **FR-5**: After ARB file updates, run `flutter gen-l10n` to regenerate localization files
6. **FR-6**: Parameterized strings must use proper ICU message format with placeholders

### Non-Functional Requirements

1. **NFR-1**: Use `jq` CLI to add keys to ARB files (never read full ARB files)
2. **NFR-2**: Key names should be descriptive and follow camelCase convention
3. **NFR-3**: Maintain consistency with existing localization patterns
4. **NFR-4**: Run `app/test.sh` after changes to verify no regressions

## Estimated Scope Summary

| Priority | Files | Strings | Status |
|----------|-------|---------|--------|
| P0 - Pre-existing keys | All ARBs | ~162 | PENDING |
| P1-P5 - Original PRD | 27 | ~125 | 93% COMPLETE |
| P6 - New discoveries | ~10 | ~80 | PENDING |
| **Total** | **~40** | **~367** | - |

## Success Criteria

- [ ] All ~367 hardcoded strings replaced with l10n keys
- [ ] All 34 language ARB files updated with proper translations
- [ ] Pre-existing ~162 untranslated keys properly translated
- [ ] `flutter gen-l10n` runs without errors
- [ ] App builds successfully
- [ ] Tests pass (`app/test.sh`)
- [ ] No regression in existing localized strings

## Dependencies

- `add-a-new-localization-key-l10n-arb` skill for adding keys to ARB files
- Access to all language ARB files in `app/lib/l10n/`
- `jq` CLI tool for ARB file manipulation

## Technical Notes

### Provider Strings
Providers often don't have BuildContext. Use pattern:
```dart
MyApp.navigatorKey.currentContext?.l10n.keyName ?? 'Fallback'
```

### Parameterized Strings
Strings with variables need ICU message format:
```json
"errorWithMessage": "Error: {message}",
"@errorWithMessage": {
  "placeholders": {
    "message": {"type": "String"}
  }
}
```

### PDF Export Strings
PDF export uses `pw.Text` (from `pdf` package). These may require a different approach or remain as-is if not user-facing in the traditional sense.
