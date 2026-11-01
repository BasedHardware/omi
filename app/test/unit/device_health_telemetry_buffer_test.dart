import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/device_health_telemetry.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_platform_interface.dart';

void main() {
  test('binding-free outage and recovery flush on the next available device write', () async {
    // Intentionally start without a binding or a preferences mock.
    final began = DateTime(2026, 10, 9, 23);
    await DeviceHealthTelemetry.recordOutage('buffered', at: began);
    await DeviceHealthTelemetry.recordRecovery('buffered', at: began.add(const Duration(hours: 2)));
    await DeviceHealthTelemetry.recordOutage('still-open', at: began);
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await DeviceHealthTelemetry.recordOutage('flush-trigger', at: began);
    final prefs = await SharedPreferences.getInstance();
    final resolved = jsonDecode(prefs.getString(DeviceHealthTelemetry.outageKey('buffered'))!) as Map;
    expect(resolved['open_since'], isNull);
    expect((resolved['resolved_days'] as Map).values, [3600, 3600]);
    final open = jsonDecode(prefs.getString(DeviceHealthTelemetry.outageKey('still-open'))!) as Map;
    expect(open['open_since'], began.millisecondsSinceEpoch);
  });

  test('unavailable preferences retain recovery and retry without escaping errors', () async {
    SharedPreferences.setMockInitialValues({});
    SharedPreferencesStorePlatform.instance = _UnavailableStore();
    final began = DateTime(2026, 10, 10);
    await DeviceHealthTelemetry.recordOutage('no-plugin', at: began);
    await DeviceHealthTelemetry.recordRecovery('no-plugin', at: began.add(const Duration(minutes: 1)));
    SharedPreferences.setMockInitialValues({});
    await DeviceHealthTelemetry.recordOutage('trigger');
    final prefs = await SharedPreferences.getInstance();
    final record = jsonDecode(prefs.getString(DeviceHealthTelemetry.outageKey('no-plugin'))!) as Map;
    expect(record['open_since'], isNull);
    expect((record['resolved_days'] as Map).values.single, 60);
  });

  test('failed cached persistence retries to disk without duplicating recovery', () async {
    SharedPreferences.setMockInitialValues({});
    final store = _RetryStore();
    SharedPreferencesStorePlatform.instance = store;
    final began = DateTime(2026, 10, 10);
    await DeviceHealthTelemetry.recordOutage('retry', at: began);
    store.reject = true;
    await DeviceHealthTelemetry.recordRecovery('retry', at: began.add(const Duration(minutes: 1)));
    store.reject = false;
    await DeviceHealthTelemetry.recordOutage('retry-trigger');
    final record = jsonDecode(store.disk['flutter.${DeviceHealthTelemetry.outageKey('retry')}']! as String) as Map;
    expect(record['open_since'], isNull);
    expect((record['resolved_days'] as Map).values.single, 60);
  });

  test('buffered writes are dropped after identity epoch changes', () async {
    SharedPreferences.setMockInitialValues({});
    SharedPreferencesStorePlatform.instance = _UnavailableStore();
    await DeviceHealthTelemetry.recordOutage('retired');
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    await DeviceHealthTelemetry.recordOutage('current');
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString(DeviceHealthTelemetry.outageKey('retired')), isNull);
    expect(prefs.getString(DeviceHealthTelemetry.outageKey('current')), isNotNull);
  });

  test('policy retirement drops buffered observations before a later flush', () async {
    SharedPreferences.setMockInitialValues({});
    SharedPreferencesStorePlatform.instance = _UnavailableStore();
    await DeviceHealthTelemetry.recordOutage('policy-retired');
    await DeviceHealthTelemetry.syncPolicy(enabled: false, retire: true);
    SharedPreferences.setMockInitialValues({});
    await DeviceHealthTelemetry.recordOutage('after-retirement');
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString(DeviceHealthTelemetry.outageKey('policy-retired')), isNull);
  });
}

class _UnavailableStore extends SharedPreferencesStorePlatform {
  @override
  Future<Map<String, Object>> getAll() async => throw MissingPluginException('preferences unavailable');

  @override
  Future<bool> setValue(String valueType, String key, Object value) async => false;

  @override
  Future<bool> remove(String key) async => false;

  @override
  Future<bool> clear() async => false;
}

class _RetryStore extends _UnavailableStore {
  final disk = <String, Object>{};
  bool reject = false;

  @override
  Future<Map<String, Object>> getAll() async => disk;

  @override
  Future<bool> setValue(String valueType, String key, Object value) async {
    if (reject) return false;
    disk[key] = value;
    return true;
  }
}
