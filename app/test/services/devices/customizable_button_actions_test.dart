import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/pages/settings/sign_out.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/ui/ui.dart';
import '../../support/typed_conversation_screen.dart' show inertPendingWorkStore;

class _StubOmiDeviceProvider extends ChangeNotifier implements DeviceProvider {
  _StubOmiDeviceProvider({required this.device});

  final BtDevice device;

  @override
  bool get isConnected => true;

  @override
  BtDevice? get connectedDevice => device;

  @override
  BtDevice? get pairedDevice => device;

  @override
  int get batteryLevel => 85;

  @override
  bool get isCharging => false;

  @override
  bool get havingNewFirmware => false;

  @override
  String get latestStableFirmwareVersion => '';

  @override
  Future<void> getDeviceInfo() async {}

  @override
  Future<bool> findDevice() async => true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Widget _buildTestApp(DeviceProvider provider) {
  return MaterialApp(
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    builder: (context, child) => MediaQuery(
      data: MediaQuery.of(context).copyWith(disableAnimations: true),
      child: child!,
    ),
    home: ChangeNotifierProvider<DeviceProvider>.value(
      value: provider,
      child: const DeviceSettings(),
    ),
  );
}

int _decodeBleButtonState(List<int> snapshot) {
  return snapshot[0] | (snapshot[1] << 8) | (snapshot[2] << 16) | (snapshot[3] << 24);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('Customizable button action preferences (#2825)', () {
    test('defaults match issue #2825 specification (Single=Ask, Double=Mute, Triple=End)', () {
      final prefs = SharedPreferencesUtil();
      expect(prefs.singlePressAction, 3);
      expect(prefs.singleTapAction, 3);
      expect(prefs.doublePressAction, 1);
      expect(prefs.doubleTapAction, 1);
      expect(prefs.doubleTapPausesMuting, isTrue);
      expect(prefs.triplePressAction, 0);
      expect(prefs.tripleTapAction, 0);
    });

    test('persists custom actions across all gestures and keeps double-tap aliases in sync', () {
      final prefs = SharedPreferencesUtil();

      prefs.singlePressAction = 2;
      prefs.doublePressAction = 0;
      prefs.triplePressAction = 4;

      expect(prefs.singlePressAction, 2);
      expect(prefs.singleTapAction, 2);
      expect(prefs.doublePressAction, 0);
      expect(prefs.doubleTapAction, 0);
      expect(prefs.doubleTapPausesMuting, isFalse);
      expect(prefs.triplePressAction, 4);
      expect(prefs.tripleTapAction, 4);

      prefs.doubleTapAction = 3;
      expect(prefs.doublePressAction, 3);
      expect(prefs.doubleTapAction, 3);
    });

    test('honors legacy doubleTapAction when doublePressAction is absent', () async {
      SharedPreferences.setMockInitialValues({'doubleTapAction': 2});
      await SharedPreferencesUtil.init();

      final prefs = SharedPreferencesUtil();
      expect(prefs.doublePressAction, 2);
      expect(prefs.doubleTapAction, 2);
    });

    test('sanitizes out-of-range action values to gesture defaults', () async {
      SharedPreferences.setMockInitialValues({
        'singlePressAction': 99,
        'doublePressAction': -5,
        'triplePressAction': 42,
      });
      await SharedPreferencesUtil.init();

      final prefs = SharedPreferencesUtil();
      expect(prefs.singlePressAction, 3);
      expect(prefs.doublePressAction, 1);
      expect(prefs.triplePressAction, 0);

      prefs.singlePressAction = -1;
      prefs.doublePressAction = 8;
      prefs.triplePressAction = 99;
      expect(prefs.singlePressAction, 3);
      expect(prefs.doublePressAction, 1);
      expect(prefs.triplePressAction, 0);
    });

    test('preserves customized button actions across sign out', () async {
      final prefs = SharedPreferencesUtil();
      prefs.singlePressAction = 1;
      prefs.doublePressAction = 2;
      prefs.triplePressAction = 3;

      await clearPreferencesForSignOut();
      await SharedPreferencesUtil.init();

      expect(SharedPreferencesUtil().singlePressAction, 1);
      expect(SharedPreferencesUtil().doublePressAction, 2);
      expect(SharedPreferencesUtil().doubleTapAction, 2);
      expect(SharedPreferencesUtil().triplePressAction, 3);
    });

    test('decodes firmware BLE button states including TRIPLE_TAP (6)', () {
      expect(_decodeBleButtonState([1, 0, 0, 0, 0, 0, 0, 0]), 1);
      expect(_decodeBleButtonState([2, 0, 0, 0, 0, 0, 0, 0]), 2);
      expect(_decodeBleButtonState([3, 0, 0, 0, 0, 0, 0, 0]), 3);
      expect(_decodeBleButtonState([5, 0, 0, 0, 0, 0, 0, 0]), 5);
      expect(_decodeBleButtonState([6, 0, 0, 0, 0, 0, 0, 0]), 6);
    });
  });

  group('DeviceSettings button customization UI (#2825)', () {
    late PendingWorkStore previousStore;
    late PendingWorkStore testStore;

    setUp(() {
      previousStore = PendingWorkStore.instance;
      testStore = inertPendingWorkStore();
      PendingWorkStore.instance = testStore;
    });

    tearDown(() {
      PendingWorkStore.instance = previousStore;
      testStore.dispose();
    });

    testWidgets('renders Single Press, Double Tap, Triple Press, and fixed Long Press for Omi', (tester) async {
      tester.view.physicalSize = const Size(800, 1400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      final provider = _StubOmiDeviceProvider(
        device: BtDevice(id: '', name: 'Omi', type: DeviceType.omi, rssi: -45),
      );
      addTearDown(provider.dispose);

      await tester.pumpWidget(_buildTestApp(provider));
      await tester.pump();

      expect(find.byKey(const Key('single_tap_setting')), findsOneWidget);
      expect(find.byKey(const Key('double_tap_setting')), findsOneWidget);
      expect(find.byKey(const Key('triple_tap_setting')), findsOneWidget);
      expect(find.byKey(const Key('long_press_setting')), findsOneWidget);

      expect(find.text('Single Press'), findsOneWidget);
      expect(find.text('Ask Omi a Question'), findsOneWidget);
      expect(find.text('Double Tap'), findsOneWidget);
      expect(find.text('Mute / Unmute'), findsOneWidget);
      expect(find.text('Triple Press'), findsOneWidget);
      expect(find.text('End Conversation'), findsOneWidget);
      expect(find.text('Long Press'), findsOneWidget);
      expect(find.text('Turn On / Turn Off'), findsOneWidget);

      final longPressRow = tester.widget<OmiSettingsRow>(find.byKey(const Key('long_press_setting')));
      expect(longPressRow.showChevron, isFalse);
      expect(longPressRow.onTap, isNull);

      // Customize Single Press to Star Ongoing Conversation (2)
      await tester.tap(find.byKey(const Key('single_tap_setting')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Star Ongoing Conversation'));
      await tester.pumpAndSettle();
      expect(SharedPreferencesUtil().singlePressAction, 2);

      // Customize Triple Press to Off (4)
      await tester.tap(find.byKey(const Key('triple_tap_setting')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Off'));
      await tester.pumpAndSettle();
      expect(SharedPreferencesUtil().triplePressAction, 4);
    });
  });
}
