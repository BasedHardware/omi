import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/settings/notifications_settings_page.dart';
import 'package:omi/services/bridges/live_activity_bridge.dart';
import 'package:omi/ui/ui.dart';

class _UnreachableApiEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:1/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  const channel = MethodChannel(LiveActivityBridge.channelName);
  const toggle = ValueKey('capture_live_activity_toggle');

  setUpAll(() => Env.init(_UnreachableApiEnv()));

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Future<List<Object?>> pumpPage(WidgetTester tester, {bool authorized = true, bool failSetEnabled = false}) async {
    final enabledCalls = <Object?>[];
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(channel, (call) async {
      switch (call.method) {
        case 'availability':
          return {'supported': true, 'authorized': authorized};
        case 'setEnabled':
          enabledCalls.add(call.arguments);
          if (failSetEnabled) throw PlatformException(code: 'unavailable');
      }
      return null;
    });
    addTearDown(() => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(channel, null));
    await tester.pumpWidget(const MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: NotificationsSettingsPage(),
    ));
    await tester.pump();
    return enabledCalls;
  }

  NativeRow? nativeRow(WidgetTester tester) => tester
      .widget<IosNativeSurface>(find.byType(IosNativeSurface))
      .sections
      .expand((section) => section.rows)
      .where((row) => row.id == 'capture_live_activity_toggle')
      .firstOrNull;

  bool flutterSwitch(WidgetTester tester) =>
      tester.widget<OmiSwitch>(find.descendant(of: find.byKey(toggle), matching: find.byType(OmiSwitch))).value;

  testWidgets('native Notifications projects the Lock Screen choice through the Flutter row owner', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    try {
      final enabledCalls = await pumpPage(tester);
      final row = nativeRow(tester)!;
      expect(row.kind, 'toggle');
      expect(row.value, isTrue);
      expect(row.enabled, isTrue);

      await row.action!(false);
      await tester.pump();

      expect(enabledCalls, [false]);
      expect(SharedPreferencesUtil().showCaptureLiveActivity, isFalse);
      expect(nativeRow(tester)!.value, isFalse);
      expect(flutterSwitch(tester), isFalse);
    } finally {
      debugDefaultTargetPlatformOverride = null;
    }
  });

  testWidgets('a failed native update restores the projected choice and the saved preference', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    try {
      await pumpPage(tester, failSetEnabled: true);
      await nativeRow(tester)!.action!(false);
      await tester.pump();

      expect(nativeRow(tester)!.value, isTrue);
      expect(nativeRow(tester)!.enabled, isTrue);
      expect(SharedPreferencesUtil().showCaptureLiveActivity, isTrue);
      // Let the error feedback finish before the test ends.
      await tester.pump(const Duration(seconds: 10));
    } finally {
      debugDefaultTargetPlatformOverride = null;
    }
  });

  testWidgets('the native row stays hidden while iOS has Live Activities off for Omi', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    try {
      await pumpPage(tester, authorized: false);
      expect(nativeRow(tester), isNull);
      expect(find.byKey(toggle), findsNothing);
    } finally {
      debugDefaultTargetPlatformOverride = null;
    }
  });
}
