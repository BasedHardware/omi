import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/capture/connect.dart';
import 'package:omi/pages/onboarding/find_device/page.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';
import 'visual_audit/fakes.dart';

/// An injected device list over inert BLE: scanning, cancelling and connecting only record calls.
class _InjectedDiscovery extends OnboardingProvider {
  _InjectedDiscovery(List<BtDevice> devices) {
    deviceList = devices;
    foundDevicesMap = {for (final device in devices) device.id: device};
  }

  final taps = <String>[];
  int scans = 0, cancels = 0;

  @override
  Future<void> handleTap({required BtDevice device, required bool isFromOnboarding, VoidCallback? goNext}) async =>
      taps.add(device.id);

  @override
  Future<void> scanDevices({required VoidCallback onShowDialog, VoidCallback? onShowLocationDialog}) async => scans++;

  @override
  void cancelActiveScan() => cancels++;
}

/// Exercises the native Connect page in the real UIKit host.
/// Run on Simulator with OMI_APP_PROFILE=local_dev and OMI_IOS_SWIFTUI=true.
void main() => runNativeHostSuite((checkNativeHost) {
      setUp(() async {
        // A signed-in synthetic owner, so the native surface's session is active.
        await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
        addTearDown(JourneyHermeticBoot.stop);
      });

      Future<_InjectedDiscovery> openConnect(WidgetTester tester) async {
        final discovery = _InjectedDiscovery([
          BtDevice(name: 'Omi', id: 'host-device-1', type: DeviceType.omi, rssi: -40),
          BtDevice(name: 'Plaud Note', id: 'host-device-2', type: DeviceType.plaud, rssi: -60),
        ])
          ..setDeviceProvider(AuditDeviceProvider());
        await tester.pumpWidget(nativeHostApp(
          Builder(
              builder: (context) => Scaffold(
                  body: Center(
                      child: TextButton(
                          onPressed: () => Navigator.of(context)
                              .push(MaterialPageRoute<void>(builder: (_) => const ConnectDevicePage())),
                          child: const Text('open connect'))))),
          providers: [
            ChangeNotifierProvider<OnboardingProvider>.value(value: discovery),
            ChangeNotifierProvider<DeviceProvider>(create: (_) => AuditDeviceProvider()),
          ],
        ));
        await tester.tap(find.text('open connect'));
        await tester.pumpAndSettle();
        return discovery;
      }

      testWidgets('native Connect lists injected devices, taps through handleTap and owns one scan', (tester) async {
        final discovery = await openConnect(tester);
        await checkNativeHost(tester, 'native-device-discovery-pairing-connect-dark');

        expect(find.byType(FindDevicesPage, skipOffstage: false), findsNothing);
        expect(discovery.scans, 1, reason: 'Only the native lifecycle scans');
        expect(nativeProjectedRow(tester, 'connect_device:0').title, 'Omi');
        expect(nativeProjectedRow(tester, 'connect_device:1').title, 'Plaud Note');

        await nativeProjectedRow(tester, 'connect_device:0').action!(null);
        expect(discovery.taps, ['host-device-1']);
      });

      testWidgets('DEVICE_CONNECTED pops the native Connect page', (tester) async {
        final discovery = await openConnect(tester);
        await checkNativeHost(tester, 'native-device-discovery-pairing-connect-before-pop-dark');

        discovery.notifyInfo('DEVICE_CONNECTED');
        await tester.pumpAndSettle();
        expect(find.byType(ConnectDevicePage), findsNothing);
        expect(discovery.cancels, 1, reason: 'Leaving cancels the scan the native owner started');
      });
    });
