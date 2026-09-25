import 'package:flutter/material.dart';

import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/core/app_shell.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/auth/clear_user_state.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Local preferences that belong to this phone and its paired device, not to the account, so they
/// survive Sign Out (chat-apps-settings #9). Everything else — tokens, the user id, profile,
/// caches, onboarding progress and account-scoped toggles — is cleared, as before.
///
/// Keep this list to device pairing, device behaviour and display preferences. Never add
/// credentials (auth tokens, OTA Wi-Fi password) or anything derived from the account.
const Set<String> kPreferencesKeptOnSignOut = {
  // Paired device
  'btDevice',
  'btDevices',
  'deviceName',
  'deviceIsV2',
  'deviceSupportsMultiFileSync',
  'deviceOnboardingCompleted',
  'lastKnownFirmwareVersion',
  'doubleTapAction',
  'omiButtonActionsEnabled',
  'companionAssociationPrompted',
  'autoSyncOfflineRecordings',
  // Display and phone behaviour
  'showGoalTrackerEnabled',
  'showDailyScoreEnabled',
  'showTasksEnabled',
  'showPhoneCallButton',
  'showShortConversations',
  'showDiscardedMemories',
  'voiceResponseMode',
  'devLogsToFileEnabled',
  // So announcements already seen on this phone do not come back
  'lastKnownAppVersion',
  'lastAnnouncementCheckTime',
};

/// Clears the preferences store except [kPreferencesKeptOnSignOut] (see there).
Future<void> clearPreferencesForSignOut() async {
  final prefs = await SharedPreferences.getInstance();
  final kept = <String, Object>{};
  for (final key in kPreferencesKeptOnSignOut) {
    final value = prefs.get(key);
    if (value != null) kept[key] = value;
  }
  await SharedPreferencesUtil().clear();
  for (final entry in kept.entries) {
    final value = entry.value;
    if (value is String) {
      await prefs.setString(entry.key, value);
    } else if (value is bool) {
      await prefs.setBool(entry.key, value);
    } else if (value is int) {
      await prefs.setInt(entry.key, value);
    } else if (value is double) {
      await prefs.setDouble(entry.key, value);
    } else if (value is List<String>) {
      await prefs.setStringList(entry.key, value);
    }
  }
}

/// Asks "Sign Out?" (destructive, confirmed every time) and, on confirm, signs out and returns to
/// the auth screen. The message says what happens: sign in again; the paired device and app
/// preferences stay on the phone.
Future<void> confirmAndSignOut(BuildContext context) async {
  final confirmed = await showOmiConfirm(
    context,
    title: context.l10n.signOutQuestion,
    message: context.l10n.signOutConfirmation,
    confirmLabel: context.l10n.signOut,
    destructive: true,
  );
  if (!confirmed) return;
  // The caller's context (often the Settings sheet) may be gone after this; route through the
  // root navigator so we always land back on the auth screen.
  final rootCtx = globalNavigatorKey.currentContext;
  if (rootCtx != null && rootCtx.mounted) clearAllUserState(rootCtx);
  await clearPreferencesForSignOut();
  await AuthService.instance.signOut();
  if (rootCtx != null && rootCtx.mounted) routeToPage(rootCtx, const AppShell(), replace: true);
}
