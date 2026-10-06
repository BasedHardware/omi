import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';

class _DeviceProvider extends ChangeNotifier implements DeviceProvider {
  bool? connected;

  @override
  void setIsConnected(bool value) => connected = value;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('a failed connection tells the Connect page why (#20790)', (tester) async {
    await tester.pumpWidget(MaterialApp(
      navigatorKey: globalNavigatorKey,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: const SizedBox.shrink(),
    ));
    final devices = _DeviceProvider();
    final provider = OnboardingProvider()..setDeviceProvider(devices);
    final omi = BtDevice(id: 'AA:BB:CC:DD:EE:01', name: 'Omi', type: DeviceType.omi, rssi: -50);
    provider.deviceList = [omi];

    // No device service is running in this test, so connecting throws inside handleTap's try,
    // the same path a BLE connection or device-setup failure takes.
    await provider.handleTap(device: omi, isFromOnboarding: false);

    expect(provider.error, 'Connection failed');
    expect(provider.isClicked, isFalse);
    expect(provider.connectingToDeviceId, isNull);
    expect(devices.connected, isFalse);
  });
}
