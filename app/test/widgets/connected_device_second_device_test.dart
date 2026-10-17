// Platform-interface packages are transitive test seams, not app dependencies.
// ignore: depend_on_referenced_packages
import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
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
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/services.dart';

class _TestConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

final _omi = BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40);
final _glass = BtDevice(id: 'glass-1', name: 'OmiGlass', type: DeviceType.openglass, rssi: -50);

class _StubDeviceProvider extends DeviceProvider {
  _StubDeviceProvider({
    required BtDevice primary,
    BtDevice? savedCompanion,
    BtDevice? connectedCompanion,
    int companionBattery = -1,
  }) {
    isConnected = true;
    connectedDevice = primary;
    pairedDevice = primary;
    _savedCompanion = savedCompanion;
    companionDevice = connectedCompanion;
    companionBatteryLevel = companionBattery;
  }

  BtDevice? _savedCompanion;
  int forgetCompanionCalls = 0;

  @override
  BtDevice? get pairedCompanionDevice => _savedCompanion;

  @override
  Future<void> forgetCompanionDevice() async {
    forgetCompanionCalls++;
  }

  @override
  Future getDeviceInfo() async {}
}

class _StubCaptureProvider extends CaptureProvider {
  _StubCaptureProvider() : super(localSegmentStore: LocalSegmentStore.disabled());
}

class _StubSyncProvider extends SyncProvider {
  _StubSyncProvider() : super(startBackgroundSync: false);
}

Widget _app(_StubDeviceProvider device) {
  return MaterialApp(
    locale: const Locale('en'),
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
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    ConnectivityPlatform.instance = _TestConnectivityPlatform();
    try {
      await ServiceManager.init();
    } catch (_) {
      // Already initialised by another test in this isolate.
    }
  });

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
    await tester.scrollUntilVisible(find.byKey(const Key('second_device_section')), 300);

    expect(find.text('Second device'), findsOneWidget);
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
    await tester.scrollUntilVisible(find.byKey(const Key('second_device_section')), 300);

    expect(find.text('Second device'), findsOneWidget);
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
    await tester.scrollUntilVisible(find.byKey(const Key('second_device_section')), 300);

    expect(find.text('Second device'), findsOneWidget);
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

    expect(find.text('Second device'), findsNothing);
    expect(find.byKey(const Key('pair_second_device_button')), findsNothing);
  });
}
