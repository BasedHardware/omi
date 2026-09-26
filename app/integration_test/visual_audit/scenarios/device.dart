// The device page with its Forget Device confirmation, and the firmware update page.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/devices/add_device_page.dart';
import 'package:omi/pages/devices/devices_page.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/device_provider.dart';

import '../fakes.dart';
import '../harness.dart';

final deviceScenarios = <AuditScenario>[
  AuditScenario(
    id: 'devices-tab',
    title: 'Devices tab: a paired Omi and this phone, Add a device',
    page: 'lib/pages/devices/devices_page.dart (DevicesPage)',
    state: 'An Omi pendant paired and connected at 72% battery; nothing recording',
    run: (a) async {
      final device = BtDevice(id: 'd1', name: 'Omi Device', type: DeviceType.omi, rssi: -40);
      await a.pump(const DevicesPage(), providers: [
        ChangeNotifierProvider<DeviceProvider>.value(
            value: AuditDeviceProvider(connected: true, battery: 72, device: device)),
      ]);
      await a.shot('Open the Devices tab');
    },
  ),
  AuditScenario(
    id: 'devices-add',
    title: 'What will you wear? (Add a device)',
    page: 'lib/pages/devices/add_device_page.dart (AddDevicePage)',
    state: 'No device paired',
    run: (a) async {
      await a.pump(const AddDevicePage());
      await a.scrollSeries('Open Add a device');
    },
  ),
  AuditScenario(
    id: 'device-connected',
    title: 'Device page, connected, and the Forget Device confirmation',
    page: 'lib/pages/settings/device_settings.dart (DeviceSettings)',
    state: 'An Omi pendant (CV1, firmware 3.0.21) reported connected at 42% with no BLE behind it',
    run: (a) async {
      final pendant = BtDevice(
        id: 'D1:A2:B3:C4:D5:E6',
        name: 'Omi',
        type: DeviceType.omi,
        rssi: -40,
        modelNumber: 'Omi CV 1',
        firmwareRevision: '3.0.21',
        hardwareRevision: 'CV1',
        manufacturerName: 'Based Hardware',
        serialNumber: 'OMI-4F2A-91C0',
      );
      await a.pump(
          DeviceSettings(
            levelsLoader: (_) async => (hasDimming: true, hasMicGain: true, dimRatio: 60, micGain: 3),
          ),
          providers: [
            ChangeNotifierProvider<DeviceProvider>.value(
                value: AuditDeviceProvider(connected: true, battery: 42, device: pendant)),
          ]);
      await a.shot('Open the connected device page', step: 'page');
      await a.tester.scrollUntilVisible(find.byKey(const Key('find_device_button')), 200,
          scrollable: find.byType(Scrollable).first);
      await a.settle();
      await a.shot('Scroll to Find my pendant, Diagnostics and About', step: 'more');
      final forget = find.byKey(const Key('forget_device_button'));
      await a.tester.scrollUntilVisible(forget, 200, scrollable: find.byType(Scrollable).first);
      await a.settle();
      await a.tap(forget);
      await a.shot('Tap Forget Device', step: 'forget-confirm');
    },
  ),
  AuditScenario(
    id: 'device-away',
    title: 'Device page while the pendant is away',
    page: 'lib/pages/settings/device_settings.dart (DeviceSettings)',
    state: 'A paired Omi pendant that is not connected',
    run: (a) async {
      final pendant = BtDevice(id: 'D1:A2:B3:C4:D5:E6', name: 'Omi', type: DeviceType.omi, rssi: -40);
      await a.pump(DeviceSettings(levelsLoader: (_) async => null), providers: [
        ChangeNotifierProvider<DeviceProvider>.value(value: AuditDeviceProvider(device: pendant)),
      ]);
      await a.shot('Open the device page with the pendant away');
    },
  ),
  AuditScenario(
    id: 'device-firmware-low-battery',
    title: 'Firmware update available but the battery is too low',
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
      await a.shot('Open firmware update with an update available at 8% battery');
    },
  ),
];
