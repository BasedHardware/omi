import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';

class _StubDeviceProvider extends ChangeNotifier implements DeviceProvider {
  _StubDeviceProvider({this.device});

  final BtDevice? device;

  @override
  bool get isConnected => true;

  @override
  BtDevice? get connectedDevice => device;

  @override
  BtDevice? get pairedDevice => null;

  @override
  int get batteryLevel => 0;

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

PendingWorkStore _stubPendingWork() => PendingWorkStore(
      loadPending: () async =>
          const ApiSuccess(PendingWorkSnapshot(enabled: false, items: [], attentionUnseenCount: 0)),
      loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
    );

Widget _app(DeviceProvider provider, {PendingWorkStore? pendingWork}) {
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
      child: DeviceSettings(pendingWork: pendingWork),
    ),
  );
}

void main() {
  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({
      'singleTapAction': 3,
      'doubleTapAction': 1,
      'tripleTapAction': 0,
    });
    await SharedPreferencesUtil.init();
  });

  testWidgets('renders all customizable button options with defaults on supported DevKit', (tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final provider = _StubDeviceProvider(
      device: BtDevice(id: 'omi-devkit-1', name: 'Omi DevKit 2', type: DeviceType.omi, rssi: -40),
    );
    final pendingWork = _stubPendingWork();
    addTearDown(provider.dispose);
    addTearDown(pendingWork.dispose);

    await tester.pumpWidget(_app(provider, pendingWork: pendingWork));
    await tester.pumpAndSettle();

    // Verify Single Press row
    expect(find.byKey(const Key('single_tap_setting')), findsOneWidget);
    expect(find.text('Single Press'), findsOneWidget);
    expect(find.text('Ask Question'), findsOneWidget);

    // Verify Double Tap row
    expect(find.byKey(const Key('double_tap_setting')), findsOneWidget);
    expect(find.text('Double Tap'), findsOneWidget);
    expect(find.text('Mute / Unmute'), findsOneWidget);

    // Verify Triple Press row (enabled on DevKit)
    expect(find.byKey(const Key('triple_tap_setting')), findsOneWidget);
    expect(find.text('Triple Press'), findsOneWidget);
    expect(find.text('End & Process Conversation'), findsOneWidget);

    // Verify Long Press fixed row
    expect(find.byKey(const Key('long_press_setting')), findsOneWidget);
    expect(find.text('Long Press'), findsOneWidget);
    expect(find.text('Turn On/Off'), findsOneWidget);
  });

  testWidgets('single press sheet updates preference when option selected', (tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final provider = _StubDeviceProvider(
      device: BtDevice(id: 'omi-devkit-1', name: 'Omi DevKit 2', type: DeviceType.omi, rssi: -40),
    );
    final pendingWork = _stubPendingWork();
    addTearDown(provider.dispose);
    addTearDown(pendingWork.dispose);

    await tester.pumpWidget(_app(provider, pendingWork: pendingWork));
    await tester.pumpAndSettle();

    // Tap Single Press setting to open sheet
    await tester.tap(find.byKey(const Key('single_tap_setting')));
    await tester.pumpAndSettle();

    expect(find.text('Single Press Action'), findsOneWidget);

    // Select Mute / Unmute (action = 1)
    await tester.tap(find.text('Mute / Unmute').last);
    await tester.pumpAndSettle();

    expect(SharedPreferencesUtil().singleTapAction, 1);
  });

  testWidgets('triple press sheet updates preference when option selected on supported DevKit', (tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final provider = _StubDeviceProvider(
      device: BtDevice(id: 'omi-devkit-1', name: 'Omi DevKit 2', type: DeviceType.omi, rssi: -40),
    );
    final pendingWork = _stubPendingWork();
    addTearDown(provider.dispose);
    addTearDown(pendingWork.dispose);

    await tester.pumpWidget(_app(provider, pendingWork: pendingWork));
    await tester.pumpAndSettle();

    // Tap Triple Press setting to open sheet
    await tester.tap(find.byKey(const Key('triple_tap_setting')));
    await tester.pumpAndSettle();

    expect(find.text('Triple Press Action'), findsOneWidget);

    // Select Star Ongoing (action = 2)
    await tester.tap(find.text('Star Ongoing Conversation'));
    await tester.pumpAndSettle();

    expect(SharedPreferencesUtil().tripleTapAction, 2);
  });

  testWidgets('triple press is disabled and explains DevKit requirement on consumer CV1', (tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final provider = _StubDeviceProvider(
      device: BtDevice(id: 'omi-cv1', name: 'Omi', modelNumber: 'Omi CV 1', type: DeviceType.omi, rssi: -40),
    );
    final pendingWork = _stubPendingWork();
    addTearDown(provider.dispose);
    addTearDown(pendingWork.dispose);

    await tester.pumpWidget(_app(provider, pendingWork: pendingWork));
    await tester.pumpAndSettle();

    // Single press and double press are fully functional
    expect(find.byKey(const Key('single_tap_setting')), findsOneWidget);
    expect(find.byKey(const Key('double_tap_setting')), findsOneWidget);

    // Triple press displays "DevKit Only"
    expect(find.byKey(const Key('triple_tap_setting')), findsOneWidget);
    expect(find.text('DevKit Only'), findsOneWidget);

    // Tapping displays informative snackbar
    await tester.tap(find.byKey(const Key('triple_tap_setting')));
    await tester.pumpAndSettle();

    expect(find.text('Triple press requires compatible DevKit firmware.'), findsOneWidget);
  });

  testWidgets('unknown capability conservatively disables triple press while preserving single/double', (tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final provider = _StubDeviceProvider(device: null);
    final pendingWork = _stubPendingWork();
    addTearDown(provider.dispose);
    addTearDown(pendingWork.dispose);

    await tester.pumpWidget(_app(provider, pendingWork: pendingWork));
    await tester.pumpAndSettle();

    // Single press and double press are preserved and functional
    expect(find.byKey(const Key('single_tap_setting')), findsOneWidget);
    expect(find.byKey(const Key('double_tap_setting')), findsOneWidget);

    // Triple press is conservatively disabled
    expect(find.byKey(const Key('triple_tap_setting')), findsOneWidget);
    expect(find.text('DevKit Only'), findsOneWidget);

    await tester.tap(find.byKey(const Key('triple_tap_setting')));
    await tester.pumpAndSettle();

    expect(find.text('Triple press requires compatible DevKit firmware.'), findsOneWidget);
  });

  testWidgets('button controls are hidden on non-button device (e.g. OpenGlass)', (tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final provider = _StubDeviceProvider(
      device: BtDevice(id: 'glass-1', name: 'OpenGlass', type: DeviceType.openglass, rssi: -40),
    );
    final pendingWork = _stubPendingWork();
    addTearDown(provider.dispose);
    addTearDown(pendingWork.dispose);

    await tester.pumpWidget(_app(provider, pendingWork: pendingWork));
    await tester.pumpAndSettle();

    // Button customization rows must not be rendered on OpenGlass
    expect(find.byKey(const Key('single_tap_setting')), findsNothing);
    expect(find.byKey(const Key('double_tap_setting')), findsNothing);
    expect(find.byKey(const Key('triple_tap_setting')), findsNothing);
  });

  testWidgets('long press displays fixed warning snackbar', (tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final provider = _StubDeviceProvider(
      device: BtDevice(id: 'omi-devkit-1', name: 'Omi DevKit 2', type: DeviceType.omi, rssi: -40),
    );
    final pendingWork = _stubPendingWork();
    addTearDown(provider.dispose);
    addTearDown(pendingWork.dispose);

    await tester.pumpWidget(_app(provider, pendingWork: pendingWork));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('long_press_setting')));
    await tester.pumpAndSettle();

    expect(find.text('Long press powers the device on/off and cannot be customized.'), findsOneWidget);
  });
}
