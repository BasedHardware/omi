# PRD: Localization of Hardcoded Strings in Omi Flutter App

**Status:** NOT STARTED
**Created:** 2026-01-20
**Last Updated:** 2026-01-20

## Overview

This document outlines the requirements for localizing hardcoded user-facing strings found in the Omi Flutter app. A comprehensive audit identified **120+ hardcoded strings** across **27 files** that need to be migrated to Flutter's l10n system.

## Background

The app uses Flutter's ARB-based localization system (`context.l10n.keyName`). While much of the app is localized, an audit revealed significant gaps in newer features and some overlooked areas.

## Scope

### In Scope
- User-facing text (labels, titles, messages, buttons)
- Error messages and validation messages
- Success/status messages
- Notification titles and bodies
- Dialog content and titles
- Text field placeholders (hintText)
- Onboarding step titles

### Out of Scope
- Technical strings (API keys, log tags, debug messages)
- Generated files (`.g.dart`, `.gen.dart`)
- l10n/ folder contents
- Emoji-only strings
- Single characters/punctuation
- URLs and emails displayed as data (not labels)

## Files Requiring Localization

### Priority 1: High Impact - User-Facing Features (11 files, ~65 strings)

| File | Strings | Description |
|------|---------|-------------|
| `pages/conversation_detail/widgets/create_template_bottom_sheet.dart` | ~20 | Template creation UI - labels, placeholders, validation, status messages |
| `pages/apps/providers/add_app_provider.dart` | ~20 | App creation - validation errors, success/error messages |
| `pages/persona/persona_provider.dart` | ~15 | Persona feature - error messages, validation |
| `pages/payments/payment_method_provider.dart` | 3 | Payment errors |
| `pages/payments/paypal_setup_page.dart` | 2 | PayPal form placeholders |
| `pages/payments/models/payment_method_config.dart` | 4 | Payment method labels |

### Priority 2: Medium Impact - Settings & Configuration (8 files, ~30 strings)

| File | Strings | Description |
|------|---------|-------------|
| `pages/settings/widgets/plans_sheet.dart` | 3 | Subscription management dialogs |
| `pages/settings/ai_app_generator_provider.dart` | 6 | AI app generator messages |
| `pages/settings/ai_app_generator_page.dart` | 1 | Price placeholder |
| `pages/settings/transcription_settings_page.dart` | 2 | JSON placeholder, title |
| `pages/settings/import_history_page.dart` | 2 | Error messages |
| `pages/apps/widgets/payment_details_widget.dart` | 8 | Payment UI labels/validation |
| `pages/apps/app_detail/app_detail.dart` | 1 | Error display - **DONE** |
| `pages/persona/twitter/social_profile.dart` | 3 | Twitter handle validation |

### Priority 3: Notifications & Services (5 files, ~10 strings)

| File | Strings | Description |
|------|---------|-------------|
| `services/notifications/merge_notification_handler.dart` | 2 | Merge notification - **DONE** |
| `services/notifications/daily_reflection_notification.dart` | 2 | Daily reflection notification - **DONE** |
| `services/notifications/action_item_notification_handler.dart` | 1 | Reminder notification - **DONE** |
| `services/devices/device_connection.dart` | 2 | Device disconnect notification - **DONE** |
| `services/devices/models.dart` | 1 | Device error message - **N/A (debug log)** |

### Priority 4: Desktop App (3 files, ~15 strings)

| File | Strings | Description |
|------|---------|-------------|
| `desktop/pages/onboarding/desktop_onboarding_wrapper.dart` | 10 | Onboarding step titles and descriptions - **DONE** |
| `desktop/pages/settings/desktop_settings_modal.dart` | 2 | About section |
| `desktop/pages/conversations/widgets/desktop_name_speaker_dialog.dart` | 3 | Speaker dialog buttons - **DONE** |

### Priority 5: Lower Impact (3 files, ~5 strings)

| File | Strings | Description |
|------|---------|-------------|
| `pages/conversation_detail/page.dart` | 1 | Search placeholder - **DONE** |
| `pages/conversations/widgets/goal_tracker_widget.dart` | 1 | Default goal title |
| `main.dart` | 1 | Desktop window title |

## Requirements

### Functional Requirements

1. **FR-1**: All hardcoded user-facing strings must be replaced with `context.l10n.keyName` pattern
2. **FR-2**: New localization keys must be added to all 34 supported language ARB files
3. **FR-3**: **CRITICAL - Translation Requirement**: All new l10n keys MUST be properly translated to each target language. Do NOT copy English text to non-English ARB files. Each language file must contain the actual translation in that language.
4. **FR-4**: Translations must be culturally appropriate for each language
5. **FR-5**: After ARB file updates, run `flutter gen-l10n` to regenerate localization files
6. **FR-6**: Parameterized strings (with variables like `$e`, `${count}`) must use proper l10n placeholders

### Non-Functional Requirements

1. **NFR-1**: Use `jq` CLI to add keys to ARB files (never read full ARB files)
2. **NFR-2**: Key names should be descriptive and follow camelCase convention
3. **NFR-3**: Maintain consistency with existing localization patterns
4. **NFR-4**: Run `app/test.sh` after changes to verify no regressions

## Localization Key Naming Convention

- Use camelCase
- Prefix with feature context for clarity
- Examples:
  - `createTemplateTitle` - Template creation sheet title
  - `paymentMethodStripe` - Payment method name
  - `personaTwitterHandleRequired` - Persona validation error
  - `notificationMergeSuccessTitle` - Notification title

## Estimated Scope

| Priority | Files | Strings | Effort |
|----------|-------|---------|--------|
| P1 - High Impact | 6 | ~65 | High |
| P2 - Settings | 8 | ~30 | Medium |
| P3 - Notifications | 5 | ~10 | Low |
| P4 - Desktop | 3 | ~15 | Medium |
| P5 - Lower | 3 | ~5 | Low |
| **Total** | **27** | **~125** | - |

## Success Criteria

- [ ] All 125+ hardcoded strings replaced with l10n keys
- [ ] All 34 language ARB files updated with new keys
- [ ] `flutter gen-l10n` runs without errors
- [ ] App builds successfully
- [ ] Tests pass (`app/test.sh`)
- [ ] No regression in existing localized strings

## Dependencies

- `add-a-new-localization-key-l10n-arb` skill for adding keys to ARB files
- Access to all language ARB files in `app/lib/l10n/`
- `jq` CLI tool for ARB file manipulation

## Technical Notes

### Notification Strings
Some notification strings run in background isolates without BuildContext. These may need alternative localization approaches or may remain in English as system-level strings.

### Parameterized Strings
Strings with variables like `'Error: ${e.toString()}'` need proper ICU message format:
```json
"errorWithMessage": "Error: {message}",
"@errorWithMessage": {
  "placeholders": {
    "message": {"type": "String"}
  }
}
```

### Desktop App
Desktop-specific files in `desktop/` directory need the same localization treatment as mobile.
