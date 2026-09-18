import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
      appName: 'Omi Test',
      packageName: 'com.omi.test',
      version: '2.3.4',
      buildNumber: '567',
      buildSignature: '',
    );
    await SharedPreferencesUtil.init();
  });

  tearDown(AnalyticsManager.resetForTesting);

  test('Device Connected payload keeps hashed identity and drops the BtDevice dump', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();

    final device = _wearable();
    AnalyticsManager().deviceConnected(device);
    await AnalyticsManager.flushPending(force: true);

    final payload = adapter.payloadFor('Device Connected');
    expectNoWholesaleDeviceDump(device, payload);
    expectHashedIdentity(device, payload);
    expect(payload['type'], 'fieldy');
    expect(payload['device_vendor'], 'fieldlabs');
    expect(payload['hardware_family'], 'fieldy');
  });

  test('Device Paired payload keeps hashed identity and drops the BtDevice dump', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();

    final device = _wearable();
    SharedPreferencesUtil().btDevice = device;
    AnalyticsManager().devicePaired('2026-01-15T00:00:00.000Z');
    await AnalyticsManager.flushPending(force: true);

    final payload = adapter.payloadFor('Device Paired');
    expectNoWholesaleDeviceDump(device, payload);
    expectHashedIdentity(device, payload);
    expect(payload['type'], 'fieldy');
    expect(payload['device_vendor'], 'fieldlabs');
    expect(payload['hardware_family'], 'fieldy');
  });

  test('the dump guard fails when toJson keys ride along with named fields', () {
    final device = _wearable();
    final leaked = <String, Object>{
      for (final entry in device.toJson().entries)
        if (entry.value != null) entry.key: entry.value as Object,
      'type': device.type.name,
      'device_vendor': 'fieldlabs',
      'hardware_family': 'fieldy',
    };

    expect(() => expectNoWholesaleDeviceDump(device, leaked), throwsA(isA<TestFailure>()));
  });
}

BtDevice _wearable() => BtDevice(
      id: 'AA:AA:AA:AA:AA:01',
      name: 'User-renamed device',
      type: DeviceType.fieldy,
      rssi: -50,
      locator: DeviceLocator.bluetooth(deviceId: 'AA:AA:AA:AA:AA:01'),
      modelNumber: 'Fieldy One',
      firmwareRevision: '3.0.20',
      hardwareRevision: 'rev-a',
      manufacturerName: 'FieldLabs',
      serialNumber: 'OMI-SERIAL-001',
    );

/// Fails when a payload copies BtDevice persistence keys. `type` is the one
/// toJson key the dictionary already names explicitly; every other dump key is
/// the class, including fields added to toJson later.
void expectNoWholesaleDeviceDump(BtDevice device, Map<String, Object> properties) {
  const namedKeysThatShareToJsonSpelling = {'type'};
  final dumped = device.toJson().keys.toSet();
  final leaked = properties.keys.toSet().intersection(dumped).difference(namedKeysThatShareToJsonSpelling);
  expect(
    leaked,
    isEmpty,
    reason: 'analytics payload copied BtDevice.toJson keys $leaked',
  );
}

void expectHashedIdentity(BtDevice device, Map<String, Object> properties) {
  String hash(String value) => sha256.convert(utf8.encode(value)).toString().substring(0, 16);
  expect(properties['transport_device_id'], hash(device.id));
  expect(properties['transport_id_kind'], 'ble_identifier');
  expect(properties['transport_id_stability'], 'platform_dependent');
  expect(properties['hardware_id'], hash('OMI-SERIAL-001'));
  expect(properties['hardware_id_kind'], 'manufacturer_serial');
  expect(properties['hardware_id_stable'], isTrue);
}

class _FakeAnalyticsAdapter implements AnalyticsAdapter {
  final List<_RecordedEvent> events = [];
  bool _initialized = false;

  Map<String, Object> payloadFor(String eventName) {
    final match = events.where((event) => event.eventName == eventName);
    expect(match, hasLength(1), reason: 'expected one $eventName');
    return match.single.properties;
  }

  @override
  bool get isInitialized => _initialized;

  @override
  Future<void> init() async {
    _initialized = true;
  }

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}

  @override
  void alias({required String newUserId}) {}

  @override
  void track({required String eventName, Map<String, Object>? properties}) {
    events.add(_RecordedEvent(eventName, properties ?? const {}));
  }

  @override
  void setInteractionContext({String? screenName, required String target}) {}

  @override
  void registerSuperProperties(Map<String, Object> properties) {}

  @override
  void enable() {}

  @override
  void disable() {}

  @override
  void reset() {}
}

class _RecordedEvent {
  const _RecordedEvent(this.eventName, this.properties);

  final String eventName;
  final Map<String, Object> properties;
}
