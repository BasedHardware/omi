import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';

import '../support/typed_conversation_screen.dart' show inertPendingWorkStore;

class _ConnectedCv1Provider extends ChangeNotifier implements DeviceProvider {
  _ConnectedCv1Provider(this.device);

  final BtDevice device;

  @override
  bool get isConnected => true;

  @override
  bool get isSyncStalled => false;

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
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  setUp(() async {
    final previousStore = PendingWorkStore.instance;
    final store = inertPendingWorkStore();
    PendingWorkStore.instance = store;
    addTearDown(() {
      PendingWorkStore.instance = previousStore;
      store.dispose();
    });
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({'deviceOnboardingCompleted': false});
    await SharedPreferencesUtil.init();
  });

  testWidgets('DeviceSettings does not render the device tutorial row for a connected Omi CV1 (#19236)', (
    tester,
  ) async {
    final cv1 = BtDevice(
      id: 'cv1-id',
      name: 'Omi',
      type: DeviceType.omi,
      rssi: -45,
      modelNumber: 'Omi CV 1',
      firmwareRevision: '2.1.0',
    );
    final provider = _ConnectedCv1Provider(cv1);
    addTearDown(provider.dispose);

    await tester.pumpWidget(
      MaterialApp(
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
      ),
    );
    await tester.pump();

    expect(find.text('How to Use Your Omi'), findsNothing);
    expect(find.text('Offline Sync'), findsOneWidget);
  });

  test('Home and DeviceSettings do not wire InteractiveDeviceOnboardingWrapper (#19236)', () {
    final homeSource = File('lib/pages/home/page.dart').readAsStringSync();
    final deviceSettingsSource = File('lib/pages/settings/device_settings.dart').readAsStringSync();

    expect(homeSource, isNot(contains('InteractiveDeviceOnboardingWrapper')));
    expect(homeSource, isNot(contains('_checkDeviceOnboarding')));
    expect(deviceSettingsSource, isNot(contains('InteractiveDeviceOnboardingWrapper')));
    expect(deviceSettingsSource, isNot(contains('l10n.deviceTutorial')));
  });
}
