import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/settings_drawer.dart';
import 'package:omi/pages/settings/settings_search_index.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/enums.dart';

/// The smaller Settings top level (2026-09-24): Account, Plan & Usage, Referral Program, the
/// five settings groups, Help & About, Feedback and Developer Settings. Nothing became unreachable:
/// every row that was on the sheet is now at most one tap below it, and every row that was on
/// Profile is still one tap below it (on Account or a group page instead of Profile).
///
/// This test pumps the real sheet, taps each top-level row that opens a page of rows, and records
/// which rows each page draws. Depth = taps from the open sheet to see the row.

class _Device extends ChangeNotifier implements DeviceProvider {
  @override
  bool get isConnected => true;

  @override
  bool get isConnecting => false;

  @override
  BtDevice? get pairedDevice => null;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Usage extends ChangeNotifier implements UsageProvider {
  @override
  UserSubscriptionResponse? get subscription => null;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Capture extends ChangeNotifier implements CaptureProvider {
  @override
  bool get hasNativeBackgroundStreamRoute => true;

  @override
  RecordingState get recordingState => RecordingState.stop;

  @override
  bool get isPhoneMicPaused => false;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Sync extends ChangeNotifier implements SyncProvider {
  @override
  bool get isSyncing => false;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// The top-level rows that open a page of rows, and that page's widget key.
const _pagesOfRows = {
  'settings_account': 'settings_page_account',
  'settings_group_device': 'settings_page_device',
  'settings_group_recording': 'settings_page_recording',
  'settings_group_notifications': 'settings_page_notifications',
  'settings_group_privacy': 'settings_page_privacy',
  'settings_group_help': 'settings_page_help',
};

String? _keyOf(Widget widget) => switch (widget.key) { ValueKey<String>(:final value) => value, _ => null };

List<OmiSettingsRow> _rowsOnScreen(WidgetTester tester) =>
    tester.widgetList<OmiSettingsRow>(find.byType(OmiSettingsRow)).toList();

void main() {
  final en = lookupAppLocalizations(const Locale('en'));

  setUp(() async {
    SharedPreferences.setMockInitialValues({'givenName': 'Ada', 'email': 'ada@example.com', 'uid': 'uid-1234567'});
    await SharedPreferencesUtil.init();
    PackageInfo.setMockInitialValues(
      appName: 'Omi',
      packageName: 'com.friend.ios',
      version: '1.0.0',
      buildNumber: '1',
      buildSignature: '',
    );
  });

  Future<void> pumpSheet(WidgetTester tester) async {
    tester.view.physicalSize = const Size(1200, 4000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<DeviceProvider>(create: (_) => _Device()),
          ChangeNotifierProvider<UsageProvider>(create: (_) => _Usage()),
          ChangeNotifierProvider<CaptureProvider>(create: (_) => _Capture()),
          ChangeNotifierProvider<SyncProvider>(create: (_) => _Sync()),
        ],
        child: const MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          locale: Locale('en'),
          home: Scaffold(body: SettingsDrawer()),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('the sheet is Account, Plan, Referral, the groups and Feedback, in order, and every row is keyed',
      (tester) async {
    await pumpSheet(tester);
    final rows = _rowsOnScreen(tester);
    expect(rows.map(_keyOf).toList(), [
      'settings_account',
      'settings_row_referral',
      'settings_group_device',
      'settings_group_recording',
      'settings_group_notifications',
      'settings_row_apps', // Rev 3: Apps left the tab bar for Settings
      'settings_group_integrations',
      'settings_group_privacy',
      'settings_row_importData', // Rev 3: importing from other recorders is on the sheet
      'settings_group_help',
      'settings_row_feedback', // where Intercom is supported (the host test is)
      'settings_group_developer',
    ]);
    // Account shows who is signed in (the email when the sign-in provider is unknown), with an
    // initial avatar.
    expect(rows.first.title, 'Ada');
    expect(rows.first.subtitle, 'ada@example.com');
    expect(find.byType(OmiInitialAvatar), findsOneWidget);
    // The plan card sits between Account and Referral; with no subscription loaded it is titled
    // Plan & Usage.
    final plan = find.byKey(const ValueKey('settings_row_planAndUsage'));
    expect(plan, findsOneWidget);
    expect(find.descendant(of: plan, matching: find.text(en.planAndUsage)), findsOneWidget);
    expect(
        tester.getTopLeft(plan).dy, greaterThan(tester.getTopLeft(find.byKey(const ValueKey('settings_account'))).dy));
    expect(tester.getTopLeft(plan).dy,
        lessThan(tester.getTopLeft(find.byKey(const ValueKey('settings_row_referral'))).dy));
    expect(rows.skip(1).map((r) => r.title).toList(), [
      en.referralProgram,
      en.devices,
      en.recordingAndTranscription,
      en.notificationsAndDisplay,
      en.apps,
      en.integrations,
      en.dataAndPrivacy,
      en.importFromOtherApps,
      en.helpAndAbout,
      en.feedbackBug,
      en.developerSettings,
    ]);
    // The search field and close button stay in the header.
    expect(find.byType(OmiCloseButton), findsOneWidget);
    expect(find.bySemanticsLabel(en.search), findsOneWidget);
  });

  testWidgets('every row that was on the sheet or on Profile is still reachable at the same depth or less',
      (tester) async {
    await pumpSheet(tester);

    // Depth 0: the sheet itself.
    final titleDepth = <String, int>{};
    final keyDepth = <String, int>{};
    void record(int depth) {
      for (final row in _rowsOnScreen(tester)) {
        titleDepth.putIfAbsent(row.title, () => depth);
        final key = _keyOf(row);
        if (key != null) keyDepth.putIfAbsent(key, () => depth);
      }
    }

    record(0);
    // The plan card is not a row; it opens Plan & Usage from the sheet.
    expect(find.byKey(const ValueKey('settings_row_planAndUsage')), findsOneWidget);

    // Depth 1: every page of rows one tap below the sheet.
    final pageTitles = <String, List<String>>{};
    for (final entry in _pagesOfRows.entries) {
      await tester.tap(find.byKey(ValueKey(entry.key)));
      await tester.pumpAndSettle();
      expect(find.byKey(ValueKey(entry.value)), findsOneWidget, reason: '${entry.key} opens ${entry.value}');
      pageTitles[entry.value] = _rowsOnScreen(tester).map((r) => r.title).toList();
      record(1);
      await tester.tap(find.byType(OmiBackButton));
      await tester.pumpAndSettle();
      expect(find.byKey(ValueKey(entry.value)), findsNothing);
    }

    // Every destination that had a row on the sheet before (depth 0), now at most one tap deeper.
    const wasOnSheet = {
      SettingsDestination.profile: 'settings_account',
      SettingsDestination.integrations: 'settings_group_integrations',
      SettingsDestination.developer: 'settings_group_developer',
      SettingsDestination.referral: 'settings_row_referral',
      SettingsDestination.feedback: 'settings_row_feedback', // where Intercom is supported (the host test is)
    };
    const movedOffSheet = [
      SettingsDestination.notifications,
      SettingsDestination.device, // only while connected; the stub is connected
      SettingsDestination.transcription,
      SettingsDestination.conversationDisplay,
      SettingsDestination.conversationTimeout,
      SettingsDestination.offlineSync,
      SettingsDestination.phoneCalls,
      SettingsDestination.homeScreen,
      SettingsDestination.dataPrivacy,
      SettingsDestination.exportData,
      SettingsDestination.permissions,
      SettingsDestination.helpCenter,
      SettingsDestination.whatsNew,
      SettingsDestination.signOut,
    ];
    for (final entry in wasOnSheet.entries) {
      expect(keyDepth[entry.value], 0, reason: '${entry.key.name} stays on the sheet');
    }
    // Rev 3 brought Import from other apps up to the sheet, and added Appearance (light, dark or
    // the phone's) one tap below it, on Notifications & Display.
    expect(keyDepth['settings_row_importData'], 0, reason: 'importData is on the sheet');
    expect(keyDepth['settings_row_appearance'], 1, reason: 'appearance is one tap below the sheet');
    for (final destination in movedOffSheet) {
      expect(keyDepth['settings_row_${destination.name}'], 1, reason: '${destination.name} is one tap below the sheet');
    }

    // Every destination that had a row on Profile (depth 1) is still at depth 1.
    const wasOnProfile = [
      SettingsDestination.language,
      SettingsDestination.customVocabulary,
      SettingsDestination.memories,
      SettingsDestination.voiceProfile,
      SettingsDestination.people,
      SettingsDestination.deleteAccount,
    ];
    for (final destination in wasOnProfile) {
      expect(keyDepth['settings_row_${destination.name}'], 1, reason: '${destination.name} stays one tap deep');
    }

    // Every Profile row title, by its visible English text, is still one tap below the sheet.
    final profileTitles = [
      en.name,
      en.email,
      en.language,
      en.customVocabulary,
      en.memories,
      en.speechProfile,
      en.identifyingOthers,
      en.voiceResponseMode,
      en.transcribeLaterTitle,
      en.userId,
      en.deleteAccountTitle,
    ];
    for (final title in profileTitles) {
      expect(titleDepth[title], 1, reason: '"$title" (was on Profile) is one tap below the sheet');
    }

    // The rest of the old destinations are pages that did not move: Creator Payouts is inside
    // Developer Settings, still one tap below its (unchanged) top-level row.
    final covered = {
      ...wasOnSheet.keys,
      ...movedOffSheet,
      ...wasOnProfile,
      SettingsDestination.planAndUsage,
      SettingsDestination.importData,
      SettingsDestination.appearance,
      SettingsDestination.creatorPayouts,
      // Rev 3: Apps moved here from the tab bar (a row on the sheet).
      SettingsDestination.apps,
      // New in this change: the group pages themselves.
      SettingsDestination.deviceGroup,
      SettingsDestination.recordingGroup,
      SettingsDestination.notificationsGroup,
      SettingsDestination.privacyGroup,
      SettingsDestination.helpGroup,
    };
    expect(covered, SettingsDestination.values.toSet(), reason: 'a destination is missing from this walk');

    // Background Mode is Android-only (dart:io, so not drawn on the test host); it moved with its
    // handler to the Recording & Transcription page, and search opens that page.
    final background = settingsSearchEntries.singleWhere((e) => e.key == 'backgroundModeTitle');
    expect(background.destination, SettingsDestination.recordingGroup);
    expect(background.rowFile, 'lib/pages/settings/settings_groups.dart');

    // Pages hold what the brief says, in order.
    expect(pageTitles['settings_page_account'], [
      en.name,
      en.email,
      en.userId,
      en.signOut,
      en.deleteAccountTitle,
    ]);
    // Devices lists what can listen (this phone on the test host; no wearable is paired), then the
    // device rows.
    expect(pageTitles['settings_page_device'],
        [en.memoryThisPhone, en.deviceSettings, en.offlineSync, en.phoneCalls, en.permissions]);
    expect(pageTitles['settings_page_recording'], [
      en.transcription,
      en.language,
      en.customVocabulary,
      en.speechProfile,
      en.identifyingOthers,
      en.voiceResponseMode,
      en.conversationTimeout,
      en.transcribeLaterTitle,
    ]);
    expect(pageTitles['settings_page_notifications'],
        [en.appearance, en.notifications, en.homeScreen, en.conversationDisplay]);
    expect(pageTitles['settings_page_privacy'], [
      en.dataProtection,
      en.memories,
      en.exportAllData,
    ]);
    expect(pageTitles['settings_page_help'], [en.helpCenter, en.whatsNew]);
  });

  testWidgets('search still finds a moved row and opens the page that holds it', (tester) async {
    await pumpSheet(tester);
    await tester.tap(find.bySemanticsLabel(en.search));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), en.voiceResponseMode);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(OmiSettingsRow, en.voiceResponseMode));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('settings_page_recording')), findsOneWidget);
  });
}
