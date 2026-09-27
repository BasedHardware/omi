import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/device.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/device_provider.dart';

/// A device provider with no BLE behind it: paired/connected devices are absent, so the page
/// never reaches ServiceManager.
class _StubDeviceProvider extends ChangeNotifier implements DeviceProvider {
  _StubDeviceProvider({required this.connected});

  final bool connected;
  int setIsConnectedCalls = 0;

  @override
  bool get isConnected => connected;

  @override
  BtDevice? get connectedDevice => null;

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
  void setIsConnected(bool value) => setIsConnectedCalls++;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Widget _app(DeviceProvider provider, Widget page) {
  return MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: ChangeNotifierProvider<DeviceProvider>.value(value: provider, child: page),
  );
}

Future<void> _scrollTo(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(finder, 200, scrollable: find.byType(Scrollable).first);
  await tester.pump();
}

void main() {
  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('Forget Device asks first, and Cancel keeps the device', (tester) async {
    final provider = _StubDeviceProvider(connected: true);
    addTearDown(provider.dispose);

    await tester.pumpWidget(_app(provider, const DeviceSettings()));
    await tester.pump();

    final forget = find.byKey(const Key('forget_device_button'));
    await _scrollTo(tester, forget);
    expect(find.descendant(of: forget, matching: find.text('Forget Device')), findsOneWidget);
    expect(find.text('Disconnect Device'), findsNothing);

    await tester.tap(forget);
    await tester.pumpAndSettle();

    expect(find.text('Forget Device?'), findsOneWidget);
    expect(find.textContaining("you'll have to pair it again"), findsOneWidget);
    expect(find.text("Don't ask again"), findsNothing);

    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();

    expect(find.text('Forget Device?'), findsNothing);
    expect(provider.setIsConnectedCalls, 0);
    expect(find.byType(DeviceSettings), findsOneWidget);
  });

  testWidgets('the home alias shows the same page, with "Disconnected" and "Offline Sync"', (tester) async {
    final provider = _StubDeviceProvider(connected: false);
    addTearDown(provider.dispose);

    await tester.pumpWidget(_app(provider, const ConnectedDevice()));
    await tester.pump();

    expect(find.byType(DeviceSettings), findsOneWidget);
    expect(find.text('Disconnected'), findsWidgets);
    expect(find.text('Offline'), findsNothing);

    await _scrollTo(tester, find.text('Offline Sync'));
    expect(find.text('Offline Sync'), findsOneWidget);
    expect(find.text('SD Card Sync'), findsNothing);
  });
}
