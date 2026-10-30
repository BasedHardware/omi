import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_platform_interface.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/widgets/live_activity_settings.dart';
import 'package:omi/services/bridges/live_activity_bridge.dart';
import 'package:omi/ui/ui.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel(LiveActivityBridge.channelName);
  const toggle = ValueKey('capture_live_activity_toggle');

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  var authorized = true;

  Future<void> pumpSettings(WidgetTester tester, {bool failSetEnabled = false}) async {
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(channel, (call) async {
      switch (call.method) {
        case 'availability':
          return {'supported': true, 'authorized': authorized};
        case 'setEnabled':
          if (failSetEnabled) throw PlatformException(code: 'unavailable');
          return null;
      }
      return null;
    });
    addTearDown(() => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(channel, null));
    await tester.pumpWidget(
      const MaterialApp(
        localizationsDelegates: [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: LiveActivitySettings()),
      ),
    );
    await tester.pump();
  }

  bool switchValue(WidgetTester tester) =>
      tester.widget<OmiSwitch>(find.descendant(of: find.byKey(toggle), matching: find.byType(OmiSwitch))).value;

  testWidgets('the Lock Screen switch is hidden while iOS has Live Activities off for Omi', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    try {
      authorized = false;
      await pumpSettings(tester);
      expect(find.byKey(toggle), findsNothing);

      // Turned back on in iOS Settings, then back to Omi.
      authorized = true;
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump();
      await tester.pump();
      expect(find.byKey(toggle), findsOneWidget);
    } finally {
      debugDefaultTargetPlatformOverride = null;
    }
  });

  testWidgets('a rejected preference write keeps the old choice for the next card update', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    final nativeCalls = <String>[];
    try {
      SharedPreferences.resetStatic();
      SharedPreferencesStorePlatform.instance = _RejectingStore();
      await SharedPreferencesUtil.init();
      await pumpSettings(tester);
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(channel, (call) async {
        nativeCalls.add(call.method);
        return call.method == 'availability' ? {'supported': true, 'authorized': true} : null;
      });
      await tester.tap(find.byKey(toggle));
      await tester.pumpAndSettle();

      expect(switchValue(tester), isTrue);
      expect(SharedPreferencesUtil().showCaptureLiveActivity, isTrue);
      expect(nativeCalls, isNot(contains('setEnabled')));
    } finally {
      debugDefaultTargetPlatformOverride = null;
    }
  });

  testWidgets('a failed native update restores the switch and the saved preference', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    try {
      authorized = true;
      await pumpSettings(tester, failSetEnabled: true);
      expect(switchValue(tester), isTrue);

      await tester.tap(find.descendant(of: find.byKey(toggle), matching: find.byType(OmiSwitch)));
      await tester.pump();
      await tester.pump();

      expect(switchValue(tester), isTrue);
      expect(SharedPreferencesUtil().showCaptureLiveActivity, isTrue);
      // Let the error feedback finish before the test ends.
      await tester.pump(const Duration(seconds: 10));
    } finally {
      debugDefaultTargetPlatformOverride = null;
    }
  });
}

/// Storage that refuses every write, as a full disk does. SharedPreferences caches a value
/// before writing it, so a refused write is still read back unless the caller restores it.
class _RejectingStore extends SharedPreferencesStorePlatform {
  @override
  Future<Map<String, Object>> getAll() async => {};

  @override
  Future<bool> setValue(String valueType, String key, Object value) async => false;

  @override
  Future<bool> remove(String key) async => false;

  @override
  Future<bool> clear() async => false;
}
