import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/connectors/rayban_meta_connection.dart';

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';
import 'visual_audit/fakes.dart';

/// Ray-Ban Meta glasses whose camera is ready; nothing reaches the toolkit.
class _FakeRayBanConnection implements RayBanMetaDeviceConnection {
  @override
  Future<int> getFeatures() async => 0;
  @override
  Future<String> getCameraPermissionStatus() async => 'granted';
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// An Omi with LED dimming and mic gain that records every write instead of reaching BLE.
class _FakeOmiConnection implements DeviceConnection {
  final dimWrites = <int>[];

  @override
  Future<int> getFeatures() async => OmiFeatures.ledDimming | OmiFeatures.micGain;
  @override
  Future<int?> getLedDimRatio() async => 50;
  @override
  Future<int?> getMicGain() async => 4;
  @override
  Future<void> setLedDimRatio(int ratio) async => dimWrites.add(ratio);
  @override
  Future<void> setMicGain(int gain) async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Widget _settings(BtDevice device, DeviceConnection connection) => nativeHostApp(
      DeviceSettings(connectionForTest: (_) async => connection),
      providers: [
        ChangeNotifierProvider<DeviceProvider>.value(value: AuditDeviceProvider(connected: true, device: device)),
      ],
    );

void main() => runNativeHostSuite((checkNativeHost) {
      testWidgets('native Device Settings stays native for paired Ray-Ban Meta glasses', (tester) async {
        await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
        addTearDown(JourneyHermeticBoot.stop);
        final glasses = BtDevice(id: 'rayban-fixture', name: 'Ray-Ban Meta', type: DeviceType.raybanMeta, rssi: -40);
        await tester.pumpWidget(_settings(glasses, _FakeRayBanConnection()));
        await checkNativeHost(tester, 'native-device-settings-diagnostics-rayban-dark');
        expect(nativeProjectedRow(tester, 'device_name').title, 'Ray-Ban Meta');
      });

      testWidgets('a native LED level change reaches the device writer', (tester) async {
        await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
        addTearDown(JourneyHermeticBoot.stop);
        final connection = _FakeOmiConnection();
        final omi = BtDevice(id: 'omi-fixture', name: 'Omi', type: DeviceType.omi, rssi: -40);
        await tester.pumpWidget(_settings(omi, connection));
        await checkNativeHost(tester, 'native-device-settings-diagnostics-controls-dark');

        final led = nativeProjectedRow(tester, 'device_led');
        expect((led.kind, led.value), ('level', 50.0));
        // Deliver the command the way Swift does, through the surface channel and its dispatch checks.
        final id = nativeViewId(tester, find.byType(UiKitView))!;
        final channel = MethodChannel('com.omi.native_ui/surface/$id');
        await tester.binding.defaultBinaryMessenger.handlePlatformMessage(channel.name,
            channel.codec.encodeMethodCall(const MethodCall('action', {'id': 'device_led', 'value': 30.0})), (_) {});
        await tester.pump(const Duration(milliseconds: 400));
        expect(connection.dimWrites, [30]);
        expect(nativeProjectedRow(tester, 'device_led').subtitle, '30%');
      });
    });
