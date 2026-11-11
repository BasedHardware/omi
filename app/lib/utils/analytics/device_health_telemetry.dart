import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
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

  static final Map<String, Future<void>> _writes = {};
  static final Set<String> _packetSeen = {};
  static Future<void> _storageWrite = Future.value();
  static final Map<String, List<_PendingOutageWrite>> _pendingWrites = {};
  static final Set<String> _retryWrites = {};

  // Check before entering SharedPreferences: its loader can complete an internal
  // future with a binding error before the caller can attach an error handler.
  static bool get _hasBinding {
    try {
      ServicesBinding.instance;
      return true;
    } on FlutterError {
      return false;
    } on TypeError {
      // In release mode the uninitialized singleton fails its null assertion.
      return false;
    }
  }

  static Future<SharedPreferences?> _availablePreferences() async {
    if (!_hasBinding) return null;
    try {
      return await SharedPreferences.getInstance();
    } catch (_) {
      // An unavailable platform plugin is retryable on the next write too.
      return null;
    }
  }

  static String outageKey(String id) => 'device_health_outage_${id.toUpperCase()}';

  static const policyChannel = MethodChannel('com.omi/device_health_policy');
  static Future<void> _policyWrites = Future.value();
  static Future<void> get policySettled => _policyWrites;

  /// Called synchronously at identity/consent retirement. Queued writers capture
  /// the old epoch and cannot repopulate storage after this fence.
  static Future<void> syncPolicy({required bool enabled, required bool retire}) {
    _packetSeen.clear();
    if (retire) {
      _pendingWrites.clear();
      _retryWrites.clear();
    }
    final epoch = AnalyticsManager.identityEpoch;
    final pending = List<Future<void>>.from(_writes.values);
    _policyWrites = _policyWrites.catchError((Object _) {}).then((_) async {
      try {
        if (_hasBinding) {
          await policyChannel.invokeMethod<void>('setPolicy', {'enabled': enabled, 'epoch': epoch, 'retire': retire});
        }
      } on MissingPluginException {
        // No native BLE store on unsupported platforms.
      }
      await Future.wait(pending.map((write) => write.catchError((Object _) {})));
      final prefs = await _availablePreferences();
      if (prefs == null) return;
      if (retire) {
        for (final key in prefs
            .getKeys()
            .where((key) => key.startsWith('device_health_outage_') || key.startsWith('device_health_day_'))) {
          await prefs.remove(key);
        }
      }
    });
    return _policyWrites;
  }

  /// Each recovery is intersected with calendar days; daily emission cursors
  /// prevent re-emitting earlier open-day exposure after it becomes resolved.
  static Future<void> recordOutage(String id, {DateTime? at}) {
    if (!AnalyticsManager.deviceHealthRecordingEnabled) return Future.value();
    _packetSeen.remove(id.toUpperCase());
    return _writeOutage(id, (record, now) {
      if ((record['last_resolved_start'] as num? ?? -1) >= now) return;
      record['open_since'] ??= now;
    }, at);
  }

  static Future<void> recordRecovery(String id, {DateTime? at}) {
    if (!AnalyticsManager.deviceHealthRecordingEnabled) return Future.value();
    final key = id.toUpperCase();
    if (!_packetSeen.add(key)) return Future.value();
    return _resolveOutage(id, at: at);
  }

  static Future<void> _resolveOutage(
    String id, {
    DateTime? at,
    num? nativeStart,
    bool keepOutagesAfterRecovery = false,
  }) =>
      _writeOutage(id, (record, now) {
        final start = nativeStart ?? record['open_since'] as num?;
        if (start == null || (record['last_resolved_start'] as num? ?? -1) >= start) return;
        // A live audio-bearing link closes markers from before that link.
        // A newer gap on the same link stays open until its own recovery.
        if (keepOutagesAfterRecovery && start > now) return;
        if (record['open_since'] == start) record.remove('open_since');
        final began = DateTime.fromMillisecondsSinceEpoch(start.toInt());
        final days = Map<String, dynamic>.from(record['resolved_days'] as Map? ?? {});
        var day = DateTime(began.year, began.month, began.day);
        final recovery = DateTime.fromMillisecondsSinceEpoch(now);
        final oldest = DateTime(recovery.year, recovery.month, recovery.day - 7);
        if (day.isBefore(oldest)) day = oldest;
        while (day.millisecondsSinceEpoch < now) {
          final end = DateTime(day.year, day.month, day.day + 1);
          final lower = start.clamp(day.millisecondsSinceEpoch, end.millisecondsSinceEpoch);
          final upper = now.clamp(day.millisecondsSinceEpoch, end.millisecondsSinceEpoch);
          final dayKey = day.millisecondsSinceEpoch.toString();
          days[dayKey] = ((days[dayKey] as num? ?? 0) + (upper - lower).clamp(0, 86400000) / 1000).clamp(0, 86400);
          day = end;
        }
        record['resolved_days'] = days;
        record['last_resolved_start'] = start;
      }, at);

  static Future<void> _writeOutage(
    String id,
    void Function(Map<String, dynamic>, int) change,
    DateTime? at,
  ) {
    if (!AnalyticsManager.deviceHealthRecordingEnabled) return Future.value();
    final epoch = AnalyticsManager.identityEpoch;
    final policy = _policyWrites;
    final key = outageKey(id);
    final now = (at ?? DateTime.now()).millisecondsSinceEpoch;
    // Serialize all devices so the next available write also flushes other
    // devices buffered before startup. Preserve observation time, not flush time.
    final next = _storageWrite.catchError((Object _) {}).then((_) async {
      await policy;
      if (!AnalyticsManager.deviceHealthRecordingEnabled || epoch != AnalyticsManager.identityEpoch) return;
      (_pendingWrites[key] ??= []).add(_PendingOutageWrite(epoch, now, change));
      final prefs = await _availablePreferences();
      if (!AnalyticsManager.deviceHealthRecordingEnabled || epoch != AnalyticsManager.identityEpoch) return;
      if (prefs == null) return;
      for (final pendingKey in _pendingWrites.keys.toList()) {
        final pending = _pendingWrites[pendingKey];
        if (pending == null) continue;
        pending.removeWhere((write) => write.epoch != AnalyticsManager.identityEpoch);
        if (pending.isEmpty) {
          _pendingWrites.remove(pendingKey);
          _retryWrites.remove(pendingKey);
          continue;
        }
        try {
          var record = jsonDecode(prefs.getString(pendingKey) ?? '{}') as Map<String, dynamic>;
          if (record['identity_epoch'] != epoch) record = {};
          final before = jsonEncode(record);
          record['identity_epoch'] = epoch;
          for (final write in pending) {
            write.change(record, write.at);
            final days = Map<String, dynamic>.from(record['resolved_days'] as Map? ?? {});
            days.removeWhere((day, _) => int.parse(day) < write.at - 8 * 86400000);
            final retainedDays = days.keys.toList()..sort();
            for (final day in retainedDays.take((retainedDays.length - 8).clamp(0, retainedDays.length))) {
              days.remove(day);
            }
            record['resolved_days'] = days;
          }
          final encoded = jsonEncode(record);
          if (encoded != before || _retryWrites.contains(pendingKey)) {
            // SharedPreferences updates its cache even if the platform write
            // fails. Force a retry rather than mistaking that cache for disk.
            _retryWrites.add(pendingKey);
            if (!await prefs.setString(pendingKey, encoded)) continue;
          }
          // Retirement may have cleared the buffer while persistence was awaited.
          if (!AnalyticsManager.deviceHealthRecordingEnabled || epoch != AnalyticsManager.identityEpoch) return;
          _pendingWrites.remove(pendingKey);
          _retryWrites.remove(pendingKey);
        } catch (_) {
          // Keep the observations for retry; telemetry must never break BLE flows.
        }
      }
    }).catchError((Object _) {});
    _storageWrite = next;
    _writes[key] = next;
    return next;
  }

  static bool hasObservation(Map<String, dynamic> diagnostics, DateTime day) {
    final start = DateTime(day.year, day.month, day.day).millisecondsSinceEpoch;
    final end = DateTime(day.year, day.month, day.day + 1).millisecondsSinceEpoch;
    final open = diagnostics['outage_open_since'];
    if (open is int && open < end) return true;
    if ((diagnostics['outage_resolved_days'] as Map?)?.containsKey(start.toString()) == true) return true;
    for (final key in ['battery_history_v2', 'firmware_diagnostics', 'disconnect_history_v2', 'audio_packet_days']) {
      for (final point in (diagnostics[key] as List? ?? []).whereType<Map>()) {
        final ts = point['ts'] ?? point['timestamp'];
        if (ts is int && ts >= start && ts < end) return true;
      }
    }
    return false;
  }

  static String bucket(num value, List<int> limits) {
    for (final limit in limits) {
      if (value < limit) return '<$limit';
    }
    return '≥${limits.last}';
  }

  static Map<String, dynamic> rollup(Map<String, dynamic> diagnostics, DateTime day) {
    final start = DateTime(day.year, day.month, day.day).millisecondsSinceEpoch;
    final end = DateTime(day.year, day.month, day.day + 1).millisecondsSinceEpoch;
    // Writers emit integer millis; a fractional observed_at would shift both
    // the exposure and retention bounds.
    final observedAt = diagnostics['observed_at'] is int ? diagnostics['observed_at'] as int : end;
    final exposureEnd = observedAt.clamp(start, end);
    // Disconnect history is age-pruned to seven days. Catch-up can replay a
    // calendar day that starts before that horizon, so intervals which ended
    // earlier are gone and must not widen the disconnected-time budget.
    const historyRetentionMs = 7 * 24 * 3600 * 1000;
    final retentionHorizon = observedAt - historyRetentionMs;
    final events = (diagnostics['disconnect_history_v2'] as List? ?? []).whereType<Map>().toList();
    final battery = (diagnostics['battery_history_v2'] as List? ?? []).whereType<Map>().toList();
    final firmware = (diagnostics['firmware_diagnostics'] as List? ?? []).whereType<Map>().toList();
    final reasons = <String, int>{};
    final reconnectBuckets = <String, int>{};
    final rssiBuckets = <String, int>{};
    final resets = <String, int>{};
    var connectedMs = 0;
    var connectedBeforeHorizonMs = 0;
    double? lostAudioSeconds;
    final resolved = (diagnostics['outage_resolved_days'] as Map?)?[start.toString()] as num?;
    if (resolved != null) lostAudioSeconds = resolved.toDouble();
    final openSince = diagnostics['outage_open_since'] is int ? diagnostics['outage_open_since'] as int : null;
    var unresolved =
        openSince == null ? null : (exposureEnd - openSince.clamp(start, exposureEnd)).clamp(0, 86400000) / 1000;
    if (unresolved != null) lostAudioSeconds = (lostAudioSeconds ?? 0) + unresolved;
    final builds = <String>{};
    final firmwares = <String>{};
    for (final point in [
      ...battery,
      ...firmware,
      ...events,
      ...(diagnostics['audio_packet_days'] as List? ?? []).whereType<Map>()
    ]) {
      final ts = point['ts'] ?? point['timestamp'];
      if (ts is! num || ts < start || ts >= end) continue;
      if (point['app_build'] is String) builds.add(point['app_build'] as String);
      if (point['firmware'] is String) firmwares.add(point['firmware'] as String);
    }
    var received = 0;
    var expected = 0;
    for (final event in events) {
      if (event['eventType'] != 'disconnect') continue;
      // Integer millis only: writers emit ints, and a fractional value would
      // truncate into a shifted connected-window inside the lost-audio cap.
      final ts = event['timestamp'] is int ? event['timestamp'] as int : 0;
      final duration = event['connectionDurationMs'] is int ? event['connectionDurationMs'] as int : 0;
      connectedMs += (ts.clamp(start, end) - (ts - duration).clamp(start, end)).clamp(0, end - start);
      if (retentionHorizon > start) {
        final prefixEnd = retentionHorizon < end ? retentionHorizon : end;
        connectedBeforeHorizonMs +=
            (ts.clamp(start, prefixEnd) - (ts - duration).clamp(start, prefixEnd)).clamp(0, prefixEnd - start);
      }
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
      if (event['lostAudioResolvedAt'] == null && event['lostAudioSeconds'] is num) {
        lostAudioSeconds = (lostAudioSeconds ?? 0) + (event['lostAudioSeconds'] as num).toDouble();
      }
      // Legacy whole-session totals are usable only when wholly inside the day.
      if (!diagnostics.containsKey('audio_packet_days') && ts - duration >= start) {
        received += (event['audioPacketsReceived'] as num?)?.toInt() ?? 0;
        expected += (event['audioPacketsExpected'] as num?)?.toInt() ?? 0;
      }
    }
    final activeSince = diagnostics['connected_at'] is int ? diagnostics['connected_at'] as int : 0;
    if (activeSince > 0 && activeSince < exposureEnd) {
      connectedMs += exposureEnd - activeSince.clamp(start, exposureEnd);
      if (retentionHorizon > start) {
        final prefixEnd = retentionHorizon < end ? retentionHorizon : end;
        connectedBeforeHorizonMs +=
            (exposureEnd.clamp(start, prefixEnd) - activeSince.clamp(start, prefixEnd)).clamp(0, prefixEnd - start);
      }
      if (!diagnostics.containsKey('audio_packet_days') && activeSince >= start) {
        received += (diagnostics['audio_packets_received'] as num?)?.toInt() ?? 0;
        expected += (diagnostics['audio_packets_expected'] as num?)?.toInt() ?? 0;
      }
    }
    for (final point in (diagnostics['audio_packet_days'] as List? ?? []).whereType<Map>()) {
      final ts = point['ts'] as num?;
      if (ts == null || ts < start || ts >= end) continue;
      received += (point['received'] as num?)?.toInt() ?? 0;
      expected += (point['expected'] as num?)?.toInt() ?? 0;
    }
    // Lost audio is time without a link. A stale open marker must not bill the
    // connected part of the day. Disconnect history is pruned at seven days, so
    // a replayed day that starts before that horizon has an unknown prefix.
    // Exclude it from the disconnected budget whether or not a packet row
    // survived; packets are not a precondition for the correction.
    var disconnectedMs = (end - start) - connectedMs.clamp(0, end - start);
    var connectionHistoryIncomplete = false;
    if (start < retentionHorizon) {
      final prefixMs = retentionHorizon.clamp(start, end) - start;
      final unknownPrefix = (prefixMs - connectedBeforeHorizonMs.clamp(0, prefixMs)).clamp(0, prefixMs);
      disconnectedMs -= unknownPrefix;
      connectionHistoryIncomplete = true;
    }
    if (disconnectedMs < 0) disconnectedMs = 0;
    final disconnectedSeconds = disconnectedMs / 1000;
    if (unresolved != null && unresolved > disconnectedSeconds) {
      lostAudioSeconds = (lostAudioSeconds ?? 0) - (unresolved - disconnectedSeconds);
      unresolved = disconnectedSeconds;
    }
    if (lostAudioSeconds != null && lostAudioSeconds > disconnectedSeconds) {
      lostAudioSeconds = disconnectedSeconds;
    }
    var drainLevels = 0;
    var drainHours = 0.0;
    var chargeEvents = 0;
    var cliffCount = 0;
    var maxStepDrop = 0;
    var maxStepDropSeconds = 0.0;
    Map? previousBattery;
    int? lastOffChargerMvMin;
    int? lastOffChargerMvMax;
    for (final point in battery) {
      final ts = (point['ts'] as num?)?.toInt() ?? 0;
      if (ts < start || ts >= end) {
        previousBattery = point;
        continue;
      }
      if (point['charging'] == true && previousBattery?['charging'] != true) chargeEvents++;
      if (previousBattery != null) {
        final priorTs = (previousBattery['ts'] as num?)?.toInt() ?? 0;
        final elapsed = (ts - priorTs) / 3600000;
        final drop = ((previousBattery['level'] as num?) ?? 0) - ((point['level'] as num?) ?? 0);
        // Unknown flags still count as drain, but an explicitly charging
        // endpoint on either side excludes the interval. The previous day's
        // last sample still anchors the first interval of the day so a drain
        // window crossing midnight is counted by this day's rollup.
        final draining = point['charging'] != true && previousBattery['charging'] != true;
        if (elapsed > 0 && elapsed <= 2 && drop > 0 && draining) {
          drainLevels += drop.toInt();
          drainHours += elapsed;
        }
        if (priorTs >= start && priorTs < end && ts > priorTs && ts - priorTs <= 10 * 60 * 1000 && drop >= 30) {
          cliffCount++;
          if (drop > maxStepDrop) {
            maxStepDrop = drop.toInt();
            maxStepDropSeconds = (ts - priorTs) / 1000;
          }
        }
      }
      previousBattery = point;
    }
    final observedBoots = <int>{};
    int? chargePinEdgesMax;
    int? socFrozenSamples;
    for (final read in firmware) {
      final ts = (read['ts'] as num?)?.toInt() ?? 0;
      if (ts < start || ts >= end) continue;
      final edges = read['charge_pin_edges'];
      if (edges is num && (chargePinEdgesMax == null || edges > chargePinEdgesMax)) {
        chargePinEdgesMax = edges.toInt();
      }
      final offChargerMv = read['last_off_charger_mv'];
      if (offChargerMv is num) {
        final value = offChargerMv.toInt();
        if (lastOffChargerMvMin == null || value < lastOffChargerMvMin) lastOffChargerMvMin = value;
        if (lastOffChargerMvMax == null || value > lastOffChargerMvMax) lastOffChargerMvMax = value;
      }
      if (read['soc_frozen'] is bool) {
        socFrozenSamples = (socFrozenSamples ?? 0) + (read['soc_frozen'] == true ? 1 : 0);
      }
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
      'schema_version': 2,
      'day_app_build': builds.isEmpty ? null : (builds.toList()..sort()),
      'day_firmware': firmwares.isEmpty ? null : (firmwares.toList()..sort()),
      'lost_audio_seconds': lostAudioSeconds?.clamp(0, 86400),
      if (connectionHistoryIncomplete) 'connection_history_incomplete': true,
      'unresolved_outage_seconds': unresolved,
      'unresolved_outage_open': openSince != null && openSince < end,
      'audio_packet_loss_ratio': expected == 0 ? null : (expected - received).clamp(0, expected) / expected,
      'drain_percent_per_hour': drainHours == 0 ? 0 : drainLevels / drainHours,
      'charge_events': chargeEvents,
      'cliff_count': cliffCount,
      'max_step_drop': maxStepDrop,
      'max_step_drop_seconds': maxStepDropSeconds,
      if (chargePinEdgesMax != null) 'charge_pin_edges_max': chargePinEdgesMax,
      if (lastOffChargerMvMin != null) 'last_off_charger_mv_min': lastOffChargerMvMin,
      if (lastOffChargerMvMax != null) 'last_off_charger_mv_max': lastOffChargerMvMax,
      if (socFrozenSamples != null) 'soc_frozen_samples': socFrozenSamples,
      'device_resets_by_reason': resets,
    };
  }

  /// Latest packet time that proves audio on the link that began at [connectedAt].
  /// Day buckets are midnight, so a same-day count is proof only with `last_at`
  /// (or a bucket that itself starts at or after the link).
  static int? _audioEvidenceAt(Map<String, dynamic> diagnostics, int connectedAt) {
    if (connectedAt <= 0) return null;
    int? evidence;
    for (final point in (diagnostics['audio_packet_days'] as List? ?? []).whereType<Map>()) {
      // Integer millis only: a fractional value truncating past connectedAt
      // would fabricate (or shift) the proof boundary.
      final received = point['received'] is int ? point['received'] as int : 0;
      if (received <= 0) continue;
      final lastAt = point['last_at'];
      int? at;
      if (lastAt is int) {
        if (lastAt >= connectedAt) at = lastAt;
      } else {
        final ts = point['ts'];
        if (ts is int && ts >= connectedAt) at = ts;
      }
      if (at != null && (evidence == null || at > evidence)) evidence = at;
    }
    return evidence;
  }

  /// Native stamps for genuine recoveries: the singular pair, plus every proof
  /// still inside native retention. Exact `(start, at)` equality is the proof.
  static List<({int start, int at})> _audioRecoveryStamps(Map<String, dynamic> diagnostics) {
    final stamps = <({int start, int at})>[];
    void add(Object? start, Object? at) {
      // Writers emit integer millis; a fractional value would truncate to a
      // proof it never wrote, so only int counts here.
      if (start is! int || at is! int || start <= 0 || at <= 0) return;
      final pair = (start: start, at: at);
      if (stamps.any((stamp) => stamp.start == pair.start && stamp.at == pair.at)) return;
      stamps.add(pair);
    }

    add(diagnostics['audio_outage_resolved_start'], diagnostics['audio_outage_resolved_at']);
    for (final proof in (diagnostics['audio_outage_recovery_proofs'] as List? ?? []).whereType<Map>()) {
      add(proof['start'], proof['at']);
    }
    return stamps;
  }

  static bool _stampBacksRecovery(Map event, List<({int start, int at})> stamps) {
    final start = event['timestamp'];
    final resolved = event['lostAudioResolvedAt'];
    // Exact integer equality is the proof; a fractional timestamp never
    // matches a stamp and must not truncate into one.
    if (start is! int || resolved is! int) return false;
    return stamps.any((stamp) => stamp.start == start && stamp.at == resolved);
  }

  /// An `audio_recovered` row is billable when a nearby disconnect records it,
  /// or when a native recovery stamp names this exact interval. Android writes
  /// the row alone once the disconnect row is gone; the stamp is what separates
  /// that recovery from a session-start echo. Neither proof means drop it.
  static bool _isUnbackedAudioRecovery(Map event, List<Map> history, List<({int start, int at})> stamps) {
    if (event['eventType'] != 'audio_recovered') return false;
    final start = event['timestamp'];
    if (start is! int || event['lostAudioResolvedAt'] == null) return false;
    if (_stampBacksRecovery(event, stamps)) return false;
    for (final row in history) {
      if (row['eventType'] != 'disconnect') continue;
      final ts = row['timestamp'];
      if (ts is int && (ts - start).abs() <= 5000) return false;
    }
    return true;
  }

  static Future<void> maybeEmit(
    BtDevice device, {
    DateTime? now,
    Future<String> Function(String)? loadDiagnostics,
    void Function(String, Map<String, dynamic>)? emit,
    Map<String, dynamic>? emissionContext,
  }) async {
    if (!AnalyticsManager.deviceHealthRecordingEnabled || !_inFlightDevices.add(device.id)) return;
    try {
      now ??= DateTime.now();
      final identityEpoch = AnalyticsManager.identityEpoch;
      await policySettled;
      if (!AnalyticsManager.deviceHealthRecordingEnabled || identityEpoch != AnalyticsManager.identityEpoch) return;
      final yesterday = DateTime(now.year, now.month, now.day - 1);
      final key = 'device_health_day_${device.id}';
      final prefs = await SharedPreferences.getInstance();
      final last = DateTime.tryParse(prefs.getString(key) ?? '');
      if (last != null && !last.isBefore(yesterday)) return;
      final raw = await (loadDiagnostics ?? BleHostApi().getExtendedDeviceDiagnostics)(device.id);
      final diagnostics = jsonDecode(raw) as Map<String, dynamic>;
      if (!AnalyticsManager.deviceHealthRecordingEnabled || identityEpoch != AnalyticsManager.identityEpoch) return;
      final nativeEpoch = diagnostics['identity_epoch'];
      if (nativeEpoch != null && nativeEpoch != identityEpoch) return;
      if (nativeEpoch != null) {
        for (final key in [
          'battery_history_v2',
          'disconnect_history_v2',
          'firmware_diagnostics',
          'audio_packet_days'
        ]) {
          diagnostics[key] = (diagnostics[key] as List? ?? [])
              .whereType<Map>()
              .where((record) => record['identity_epoch'] == identityEpoch)
              .toList();
        }
      }
      // Import native starts/recoveries missed while Dart was suspended. Native
      // retains the first start, even across failed reconnects and process death.
      // An `audio_recovered` row is billable when a measured disconnect backs it
      // or a native stamp names that same interval. A row with neither is a
      // session-start echo and is not imported.
      // Persisted per-day totals outlive native history (Dart keeps 8 days,
      // native 7). Absence of a history row is not proof a day was synthetic,
      // and a summed day cannot be split after the fact. Leave those totals
      // alone; a false day imported before this build rides out the 8-day retention.
      final historyValue = diagnostics['disconnect_history_v2'];
      final historyPresent = historyValue is List;
      final history =
          (historyValue as List? ?? []).whereType<Map>().map((event) => Map<String, dynamic>.from(event)).toList();
      final stamps = _audioRecoveryStamps(diagnostics);
      final keptHistory = <Map<String, dynamic>>[];
      for (final event in history) {
        if (_isUnbackedAudioRecovery(event, history, stamps)) continue;
        keptHistory.add(event);
      }
      if (historyPresent) diagnostics['disconnect_history_v2'] = keptHistory;
      keptHistory.sort((a, b) => ((a['timestamp'] as num?) ?? 0).compareTo((b['timestamp'] as num?) ?? 0));
      for (final event in keptHistory) {
        // Writers emit integer millis. A fractional timestamp is malformed and
        // must not truncate into a billable resolution.
        final recovered = event['lostAudioResolvedAt'];
        final start = event['timestamp'];
        if (recovered is! int || start is! int) continue;
        await _resolveOutage(device.id, nativeStart: start, at: DateTime.fromMillisecondsSinceEpoch(recovered));
      }
      for (final stamp in stamps) {
        await _resolveOutage(device.id, nativeStart: stamp.start, at: DateTime.fromMillisecondsSinceEpoch(stamp.at));
      }
      // Writers emit integer millis; a fractional nativeStart would truncate
      // into a billable outage boundary it never wrote.
      final nativeStartRaw = diagnostics['audio_outage_started_at'];
      final nativeStart = nativeStartRaw is int ? nativeStartRaw : null;
      final connectedAt = diagnostics['connected_at'] is int ? diagnostics['connected_at'] as int : 0;
      // Cumulative session counters are not proof: Android stamps connected_at
      // when a retry starts and keeps the previous session's packet count until
      // GATT succeeds. Require a packet timestamp at or after the link, and
      // ignore that link when the open marker is newer than the last packet.
      final evidenceAt = _audioEvidenceAt(diagnostics, connectedAt);
      if (evidenceAt != null && (nativeStart == null || nativeStart <= evidenceAt)) {
        // This link has delivered audio. A native marker from before the link
        // is stale (iOS keeps it across restore); close it at the link start
        // instead of reopening a calendar-day outage. Do not import a marker
        // that is still inside the link — packets are already flowing.
        if (nativeStart != null && nativeStart > 0 && nativeStart <= connectedAt) {
          await _resolveOutage(device.id,
              nativeStart: nativeStart, at: DateTime.fromMillisecondsSinceEpoch(connectedAt));
        }
        await _resolveOutage(device.id,
            at: DateTime.fromMillisecondsSinceEpoch(connectedAt), keepOutagesAfterRecovery: true);
      } else if (nativeStart != null && nativeStart > 0) {
        await recordOutage(device.id, at: DateTime.fromMillisecondsSinceEpoch(nativeStart));
      }
      await (_writes[outageKey(device.id)] ?? Future.value());
      final stored = jsonDecode(prefs.getString(outageKey(device.id)) ?? '{}') as Map;
      final outage = stored['identity_epoch'] == identityEpoch ? stored : {};
      diagnostics['outage_open_since'] = outage['open_since'];
      diagnostics['outage_resolved_days'] = outage['resolved_days'];
      final package = emissionContext == null ? await PackageInfo.fromPlatform() : null;
      final phone = emissionContext != null
          ? null
          : Platform.isIOS
              ? (await DeviceInfoPlugin().iosInfo).utsname.machine
              : (await DeviceInfoPlugin().androidInfo).model;
      var day = last == null ? yesterday : DateTime(last.year, last.month, last.day + 1);
      final oldest = DateTime(yesterday.year, yesterday.month, yesterday.day - 6);
      if (day.isBefore(oldest)) day = oldest;
      while (!day.isAfter(yesterday) &&
          AnalyticsManager.deviceHealthRecordingEnabled &&
          identityEpoch == AnalyticsManager.identityEpoch) {
        if (!hasObservation(diagnostics, day)) {
          day = DateTime(day.year, day.month, day.day + 1);
          continue;
        }
        final daily = rollup(diagnostics, day);
        final dayFirmware = daily['day_firmware'] as List?;
        final dayBuild = daily['day_app_build'] as List?;
        final properties = {
          ...daily,
          'firmware': dayFirmware?.length == 1 ? dayFirmware!.single : null,
          'hardware_revision': device.hardwareRevision,
          'app_version': dayBuild?.length == 1 ? dayBuild!.single : null,
          'emission_app_build': emissionContext?['app_build'] ?? '${package?.version}+${package?.buildNumber}',
          'os_version': null,
          'phone_model': phone,
          'device_model': device.modelNumber,
        };
        if (emit != null) {
          emit(eventName, properties);
        } else {
          PlatformManager.instance.analytics.track(eventName, properties: properties);
        }
        await prefs.setString(key, properties['day'] as String);
        day = DateTime(day.year, day.month, day.day + 1);
      }
    } catch (_) {
      // Diagnostics never blocks the connection.
    } finally {
      _inFlightDevices.remove(device.id);
    }
  }
}

class _PendingOutageWrite {
  final int epoch;
  final int at;
  final void Function(Map<String, dynamic>, int) change;

  _PendingOutageWrite(this.epoch, this.at, this.change);
}
