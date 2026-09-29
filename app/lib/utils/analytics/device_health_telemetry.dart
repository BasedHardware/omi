import 'dart:convert';
import 'dart:io';

import 'package:device_info_plus/device_info_plus.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Aggregates only. The local device id is used for deduplication and never emitted.
class DeviceHealthTelemetry {
  static const eventName = 'Mobile Device Health Daily';
  static final Set<String> _inFlightDevices = {};

  static String bucket(num value, List<int> limits) {
    for (final limit in limits) {
      if (value < limit) return '<$limit';
    }
    return '≥${limits.last}';
  }

  static Map<String, dynamic> rollup(Map<String, dynamic> diagnostics, DateTime day) {
    final start = DateTime(day.year, day.month, day.day).millisecondsSinceEpoch;
    final end = start + const Duration(days: 1).inMilliseconds;
    final events = (diagnostics['disconnect_history_v2'] as List? ?? []).whereType<Map>().toList();
    final battery = (diagnostics['battery_history_v2'] as List? ?? []).whereType<Map>().toList();
    final firmware = (diagnostics['firmware_diagnostics'] as List? ?? []).whereType<Map>().toList();
    final reasons = <String, int>{};
    final reconnectBuckets = <String, int>{};
    final rssiBuckets = <String, int>{};
    final resets = <String, int>{};
    var connectedMs = 0;
    var lostAudioSeconds = 0.0;
    var received = 0;
    var expected = 0;
    for (final event in events) {
      if (event['eventType'] != 'disconnect') continue;
      final ts = (event['timestamp'] as num?)?.toInt() ?? 0;
      final duration = (event['connectionDurationMs'] as num?)?.toInt() ?? 0;
      connectedMs += (ts.clamp(start, end) - (ts - duration).clamp(start, end)).clamp(0, end - start);
      if (ts < start || ts >= end) continue;
      final reason = event['reason']?.toString() ?? 'unknown';
      reasons[reason] = (reasons[reason] ?? 0) + 1;
      final reconnect = (event['timeToReconnectMs'] as num?)?.toInt() ?? 0;
      if (reconnect > 0) {
        final key = bucket(reconnect / 1000, [5, 30, 120, 600]);
        reconnectBuckets[key] = (reconnectBuckets[key] ?? 0) + 1;
      }
      final rssi = (event['lastRssi'] as num?)?.toInt() ?? 0;
      if (rssi < 0) {
        final key = bucket(rssi, [-90, -75, -60]);
        rssiBuckets[key] = (rssiBuckets[key] ?? 0) + 1;
      }
      lostAudioSeconds += (event['lostAudioSeconds'] as num?)?.toDouble() ?? 0;
      received += (event['audioPacketsReceived'] as num?)?.toInt() ?? 0;
      expected += (event['audioPacketsExpected'] as num?)?.toInt() ?? 0;
    }
    final activeSince = (diagnostics['connected_at'] as num?)?.toInt() ?? 0;
    if (activeSince > 0 && activeSince < end) {
      connectedMs += end - activeSince.clamp(start, end);
      received += (diagnostics['audio_packets_received'] as num?)?.toInt() ?? 0;
      expected += (diagnostics['audio_packets_expected'] as num?)?.toInt() ?? 0;
    }
    var drainLevels = 0;
    var drainHours = 0.0;
    var chargeEvents = 0;
    Map? previousBattery;
    for (final point in battery) {
      final ts = (point['ts'] as num?)?.toInt() ?? 0;
      if (ts < start || ts >= end) {
        previousBattery = point;
        continue;
      }
      if (point['charging'] == true && previousBattery?['charging'] != true) chargeEvents++;
      if (previousBattery != null && point['charging'] == false && previousBattery['charging'] == false) {
        final priorTs = (previousBattery['ts'] as num?)?.toInt() ?? 0;
        final elapsed = (ts - priorTs) / 3600000;
        final drop = ((previousBattery['level'] as num?) ?? 0) - ((point['level'] as num?) ?? 0);
        if (elapsed > 0 && elapsed <= 2 && drop > 0) {
          drainLevels += drop.toInt();
          drainHours += elapsed;
        }
      }
      previousBattery = point;
    }
    final observedBoots = <int>{};
    for (final read in firmware) {
      final ts = (read['ts'] as num?)?.toInt() ?? 0;
      if (ts < start || ts >= end) continue;
      final bootAt = ts - (((read['uptime_s'] as num?)?.toInt() ?? 0) * 1000);
      final bootBucket = bootAt ~/ 60000;
      if (!observedBoots.add(bootBucket)) continue;
      for (final name in (read['reset_cause_names'] as List? ?? [])) {
        final key = name.toString();
        resets[key] = (resets[key] ?? 0) + 1;
      }
    }
    return {
      'day':
          '${day.year.toString().padLeft(4, '0')}-${day.month.toString().padLeft(2, '0')}-${day.day.toString().padLeft(2, '0')}',
      'connected_time_fraction': (connectedMs / (end - start)).clamp(0, 1),
      'disconnects_by_reason': reasons,
      'reconnect_latency_buckets': reconnectBuckets,
      'rssi_at_disconnect_buckets': rssiBuckets,
      'lost_audio_seconds': lostAudioSeconds,
      'audio_packet_loss_ratio': expected == 0 ? 0 : (expected - received).clamp(0, expected) / expected,
      'drain_percent_per_hour': drainHours == 0 ? 0 : drainLevels / drainHours,
      'charge_events': chargeEvents,
      'device_resets_by_reason': resets,
    };
  }

  static Future<void> maybeEmit(BtDevice device) async {
    if (!AnalyticsManager.trackingEnabled || !_inFlightDevices.add(device.id)) return;
    try {
      final now = DateTime.now();
      final yesterday = DateTime(now.year, now.month, now.day).subtract(const Duration(days: 1));
      final key = 'device_health_day_${device.id}';
      final prefs = await SharedPreferences.getInstance();
      final last = DateTime.tryParse(prefs.getString(key) ?? '');
      if (last != null && !last.isBefore(yesterday)) return;
      final raw = await BleHostApi().getExtendedDeviceDiagnostics(device.id);
      final diagnostics = jsonDecode(raw) as Map<String, dynamic>;
      final package = await PackageInfo.fromPlatform();
      final phone = Platform.isIOS
          ? (await DeviceInfoPlugin().iosInfo).utsname.machine
          : (await DeviceInfoPlugin().androidInfo).model;
      var day = last == null ? yesterday : last.add(const Duration(days: 1));
      final oldest = yesterday.subtract(const Duration(days: 6));
      if (day.isBefore(oldest)) day = oldest;
      while (!day.isAfter(yesterday) && AnalyticsManager.trackingEnabled) {
        final properties = {
          ...rollup(diagnostics, day),
          'firmware': device.firmwareRevision,
          'hardware_revision': device.hardwareRevision,
          'app_version': '${package.version}+${package.buildNumber}',
          'os_version': Platform.operatingSystemVersion,
          'phone_model': phone,
          'device_model': device.modelNumber,
        };
        PlatformManager.instance.analytics.track(eventName, properties: properties);
        await prefs.setString(key, properties['day'] as String);
        day = day.add(const Duration(days: 1));
      }
    } catch (_) {
      // Diagnostics never blocks the connection.
    } finally {
      _inFlightDevices.remove(device.id);
    }
  }
}
