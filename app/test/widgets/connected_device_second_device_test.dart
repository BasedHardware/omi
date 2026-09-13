import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/device.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';

final _omi = BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40);
final _glass = BtDevice(id: 'glass-1', name: 'OmiGlass', type: DeviceType.openglass, rssi: -50);

class _StubDeviceProvider extends ChangeNotifier implements DeviceProvider {
  _StubDeviceProvider(
      {required this.primary, this.savedCompanion, this.connectedCompanion, this.companionBattery = -1});

  final BtDevice primary;
  final BtDevice? savedCompanion;
  final BtDevice? connectedCompanion;
  final int companionBattery;
  int forgetCompanionCalls = 0;

  @override
  bool get isConnected => true;

  @override
  BtDevice? get connectedDevice => primary;

  @override
  BtDevice? get pairedDevice => primary;

  @override
  BtDevice? get pairedCompanionDevice => savedCompanion;

  @override
  BtDevice? get companionDevice => connectedCompanion;

  @override
  int get companionBatteryLevel => companionBattery;

  @override
  int get batteryLevel => -1;

  @override
  bool get isCharging => false;

  @override
  bool get isDeviceStorageSupport => false;

  @override
  bool get havingNewFirmware => false;

  @override
  String get latestStableFirmwareVersion => '';

  @override
  Map<String, dynamic> get latestOmiGlassFirmwareDetails => const {};

  @override
  Future<void> getDeviceInfo() async {}

  @override
  Future<void> forgetCompanionDevice() async {
    forgetCompanionCalls++;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _StubCaptureProvider extends ChangeNotifier implements CaptureProvider {
  @override
  void addMetricsListener() {}

  @override
  void removeMetricsListener() {}

  @override
  bool get havingRecordingDevice => false;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _StubSyncProvider extends ChangeNotifier implements SyncProvider {
  @override
  int get missingWalsInSeconds => 0;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Widget _app(_StubDeviceProvider device) {
  return MaterialApp(
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    home: MultiProvider(
      providers: [
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
        ChangeNotifierProvider<CaptureProvider>(create: (_) => _StubCaptureProvider()),
        ChangeNotifierProvider<SyncProvider>(create: (_) => _StubSyncProvider()),
      ],
      child: const ConnectedDevice(),
    ),
  );
}

void main() {
  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('offers to pair a second device when an Omi is alone', (tester) async {
    final provider = _StubDeviceProvider(primary: _omi);
    addTearDown(provider.dispose);

    await tester.pumpWidget(_app(provider));
    await tester.pump();

    expect(find.byKey(const Key('pair_second_device_button')), findsOneWidget);
    expect(find.text('Pair a second device'), findsOneWidget);
    expect(find.byKey(const Key('forget_second_device_button')), findsNothing);
  });

  testWidgets('shows the connected OmiGlass companion with its battery and a forget action', (tester) async {
    final provider = _StubDeviceProvider(
      primary: _omi,
      savedCompanion: _glass,
      connectedCompanion: _glass,
      companionBattery: 64,
    );
    addTearDown(provider.dispose);

    await tester.pumpWidget(_app(provider));
    await tester.pump();

    expect(find.text('OmiGlass'), findsOneWidget);
    expect(find.text('Connected · 64%'), findsOneWidget);
    expect(find.byKey(const Key('pair_second_device_button')), findsNothing);

    await tester.tap(find.byKey(const Key('forget_second_device_button')));
    await tester.pump();

    expect(provider.forgetCompanionCalls, 1);
  });

  testWidgets('shows a saved companion as offline while it is not connected', (tester) async {
    final provider = _StubDeviceProvider(primary: _omi, savedCompanion: _glass);
    addTearDown(provider.dispose);

    await tester.pumpWidget(_app(provider));
    await tester.pump();

    expect(find.text('OmiGlass'), findsOneWidget);
    expect(find.text('Offline'), findsOneWidget);
  });

  testWidgets('does not offer a second device for hardware outside the Omi family', (tester) async {
    final provider = _StubDeviceProvider(
      primary: BtDevice(id: 'pendant-1', name: 'Limitless', type: DeviceType.limitless, rssi: -40),
    );
    addTearDown(provider.dispose);

    await tester.pumpWidget(_app(provider));
    await tester.pump();

    expect(find.byKey(const Key('pair_second_device_button')), findsNothing);
  });
}
