// The device page with its Forget Device confirmation, the firmware update page, and Device
// Diagnostics.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/pages/home/device.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/pages/settings/device_diagnostics.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/providers/device_provider.dart';

import '../fakes.dart';
import '../harness.dart';

final deviceScenarios = <AuditScenario>[
  AuditScenario(
    id: 'device-connected',
    title: 'Device page, connected, and the Forget Device confirmation',
    page: 'lib/pages/home/device.dart (ConnectedDevice)',
    state: 'A device reported connected with no BLE behind it',
    run: (a) async {
      await a.pump(
        const ConnectedDevice(),
        providers: [ChangeNotifierProvider<DeviceProvider>.value(value: AuditDeviceProvider(connected: true))],
      );
      await a.shot('Open the connected device page', step: 'page');
      final forget = find.byKey(const Key('forget_device_button'));
      await a.tester.scrollUntilVisible(forget, 200, scrollable: find.byType(Scrollable).first);
      await a.settle();
      await a.tap(forget);
      await a.shot('Tap Forget Device', step: 'forget-confirm');
    },
  ),
  AuditScenario(
    id: 'device-firmware-low-battery',
    title: 'Firmware update available but the battery is too low',
    page: 'lib/pages/home/firmware_update.dart (FirmwareUpdate)',
    state: 'Omi device on firmware 2.0.10 at 8% battery, not charging; the fixture backend offers firmware 3.0.1',
    run: (a) async {
      PackageInfo.setMockInitialValues(
        appName: 'Omi',
        packageName: 'com.friend.ios',
        version: '1.0.0',
        buildNumber: '1',
        buildSignature: '',
      );
      // One canned 200 for the version check; failNext serves any status and body once.
      a.server.failNext(
        'GET',
        '/v2/firmware/latest',
        status: 200,
        body: jsonEncode({
          'version': '3.0.1',
          'min_version': '2.0.0',
          'changelog': ['Faster sync', 'Longer battery life'],
          'zip_url': 'http://127.0.0.1:9/firmware.zip',
          'draft': false,
        }),
      );
      final device = BtDevice(
        id: 'd1',
        name: 'Omi Device',
        type: DeviceType.omi,
        rssi: -50,
        modelNumber: 'Omi',
        firmwareRevision: '2.0.10',
      );
      await a.pump(
        FirmwareUpdate(device: device),
        providers: [
          ChangeNotifierProvider<DeviceProvider>.value(
            value: AuditDeviceProvider(connected: true, battery: 8, device: device),
          ),
        ],
      );
      await a.shot('Open firmware update with an update available at 8% battery');
    },
  ),
  AuditScenario(
    id: 'device-diagnostics-healthy',
    title: 'Device Diagnostics, a healthy week with frequent auto-recovered drops',
    page: 'lib/pages/settings/device_diagnostics.dart (DeviceDiagnostics)',
    state: 'Native BLE replies faked: connected 1h 11m at 100% battery and about -68 dBm; 357 drops in the '
        'last 7 days, each back in 1-3 s except one of about 40 s; 368 since pairing; no failed connections',
    run: (a) async {
      await _pumpDiagnostics(a, battery: 100, rssi: -68, failedLast24h: 0);
      expect(find.byKey(const Key('diagnostics_verdict_ok')), findsOneWidget);
      await a.shot('Open Device Diagnostics', step: 'top');
      await _scrollDiagnostics(a, 640);
      await a.shot('Scroll to the signal and battery charts', step: 'charts');
    },
  ),
  AuditScenario(
    id: 'device-diagnostics-trouble',
    title: 'Device Diagnostics with failed connections in the last 24 hours',
    page: 'lib/pages/settings/device_diagnostics.dart (DeviceDiagnostics)',
    state: 'Native BLE replies faked: 3 failed connections today, weak signal (about -89 dBm), 9% battery',
    run: (a) async {
      await _pumpDiagnostics(a, battery: 9, rssi: -89, failedLast24h: 3);
      expect(find.byKey(const Key('diagnostics_verdict_trouble')), findsOneWidget);
      await a.shot('Open Device Diagnostics', step: 'top');
      await _scrollDiagnostics(a, 640);
      await a.shot('Scroll to the signal and battery charts', step: 'charts');
    },
  ),
];

const _diagnosticsDeviceId = 'AA:BB:CC:DD:EE:FF';

/// Pumps [DeviceDiagnostics] over faked pigeon replies (the page builds its own `BleHostApi`), then
/// streams 60 one-second RSSI samples through [BleBridge] as native would.
Future<void> _pumpDiagnostics(AuditRun a, {required int battery, required int rssi, required int failedLast24h}) async {
  final now = DateTime.now().millisecondsSinceEpoch;
  const hour = 3600 * 1000;
  const week = 7 * 24 * hour;
  final history = <BleDisconnectEvent>[];
  const drops = 357;
  for (var i = 0; i < drops; i++) {
    final ts = now - week + ((i + 1) * week ~/ (drops + 1));
    history.add(_disconnect(ts, reconnectMs: i == 200 ? 40400 : 1000 + (i * 7919) % 2000, rssi: -66 - (i % 9)));
  }
  for (var i = 0; i < failedLast24h; i++) {
    history.add(_disconnect(now - (3 - i) * hour, failed: true, rssi: -91));
  }
  history.sort((x, y) => x.timestamp.compareTo(y.timestamp));
  final batteryHistory = [
    for (var t = now - week; t <= now; t += hour ~/ 2)
      BleBatteryPoint(
        timestamp: t,
        level: battery >= 50
            ? 100 - (((now - t) ~/ (hour ~/ 2)) % 48) ~/ 3
            : (battery + (now - t) ~/ (2 * hour)).clamp(0, 100),
      ),
  ];

  final replies = <String, Object?>{
    'getDeviceDiagnostics': BleDeviceDiagnostics(
      disconnectHistory: history,
      reconnectionCount: 368,
      connectedAt: now - (71 * 60 * 1000),
      failToConnectCount: failedLast24h,
      nativeBackgroundBytesConsumed: 0,
      nativeBackgroundPacketsConsumed: 0,
    ),
    'getExtendedDeviceDiagnostics': jsonEncode({'counters_since': now - 30 * 24 * hour}),
    'getBatteryHistory': batteryHistory,
    'startRssiStreaming': null,
    'stopRssiStreaming': null,
  };
  final messenger = a.tester.binding.defaultBinaryMessenger;
  for (final entry in replies.entries) {
    final channel = 'dev.flutter.pigeon.omi_pigeon.BleHostApi.${entry.key}';
    messenger.setMockMessageHandler(
      channel,
      (_) async => BleHostApi.pigeonChannelCodec.encodeMessage(<Object?>[entry.value]),
    );
    addTearDown(() => messenger.setMockMessageHandler(channel, null));
  }

  await a.pump(
    const DeviceDiagnostics(deviceId: _diagnosticsDeviceId),
    scaffold: false,
    providers: [
      ChangeNotifierProvider<DeviceProvider>.value(value: AuditDeviceProvider(connected: true, battery: battery)),
    ],
  );
  for (var i = 0; i < 60; i++) {
    BleBridge.instance.onRssiUpdate(_diagnosticsDeviceId, rssi + const [2, -1, 3, 0, -3, 1, -2, 2, 0, -1][i % 10]);
    await a.tester.pump(const Duration(seconds: 1));
  }
  BleBridge.instance.onRssiUpdate(_diagnosticsDeviceId, rssi);
  await a.settle();
}

Future<void> _scrollDiagnostics(AuditRun a, double offset) async {
  a.tester.state<ScrollableState>(find.byType(Scrollable).first).position.jumpTo(offset);
  await a.settle();
}

BleDisconnectEvent _disconnect(int ts, {int reconnectMs = 0, bool failed = false, required int rssi}) {
  return BleDisconnectEvent(
    timestamp: ts,
    reason: 'connection_timeout',
    reasonCode: 8,
    isManual: false,
    eventType: failed ? 'fail_to_connect' : 'disconnect',
    lastRssi: rssi,
    connectionDurationMs: failed ? 0 : 1650000,
    appState: 'background',
    timeToReconnectMs: reconnectMs,
    rssiTrend: 'stable',
  );
}
