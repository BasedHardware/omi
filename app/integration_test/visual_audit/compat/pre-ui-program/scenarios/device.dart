// The device page and the firmware update page before the UI program. Disconnect Device had no
// confirmation yet, so there is no forget-confirm step.
import 'dart:convert';

import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/home/device.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/providers/device_provider.dart';

import '../fakes.dart';
import '../../../harness.dart';

final deviceScenarios = <AuditScenario>[
  AuditScenario(
    id: 'device-connected',
    title: 'Device page, connected',
    page: 'lib/pages/home/device.dart (ConnectedDevice)',
    state: 'A device reported connected with no BLE behind it',
    run: (a) async {
      await a.pump(const ConnectedDevice(), providers: [
        ChangeNotifierProvider<DeviceProvider>.value(value: AuditDeviceProvider(connected: true)),
      ]);
      // No forget-confirm step: Disconnect Device forgets the device at once at this revision.
      await a.shot('Open the connected device page', step: 'page');
    },
  ),
  AuditScenario(
    id: 'device-firmware-low-battery',
    title: 'Firmware update available at low battery (no battery gate yet)',
    page: 'lib/pages/home/firmware_update.dart (FirmwareUpdate)',
    state: 'Omi device on firmware 2.0.10 at 8% battery, not charging; the fixture backend offers firmware 3.0.1',
    run: (a) async {
      PackageInfo.setMockInitialValues(
          appName: 'Omi', packageName: 'com.friend.ios', version: '1.0.0', buildNumber: '1', buildSignature: '');
      // One canned 200 for the version check; failNext serves any status and body once.
      a.server.failNext('GET', '/v2/firmware/latest',
          status: 200,
          body: jsonEncode({
            'version': '3.0.1',
            'min_version': '2.0.0',
            'changelog': ['Faster sync', 'Longer battery life'],
            'zip_url': 'http://127.0.0.1:9/firmware.zip',
            'draft': false,
          }));
      final device = BtDevice(
          id: 'd1',
          name: 'Omi Device',
          type: DeviceType.omi,
          rssi: -50,
          modelNumber: 'Omi',
          firmwareRevision: '2.0.10');
      await a.pump(FirmwareUpdate(device: device), providers: [
        ChangeNotifierProvider<DeviceProvider>.value(
            value: AuditDeviceProvider(connected: true, battery: 8, device: device)),
      ]);
      await a.shot('Open firmware update at 8% battery: this revision offers Install Update regardless');
    },
  ),
];
