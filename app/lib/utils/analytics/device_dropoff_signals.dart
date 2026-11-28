/// Daily signals that separate a pendant that failed or became unusable from
/// one that was put down. Pure: everything is derived from the native
/// diagnostics snapshot the daily rollup already reads, so there is no new
/// emission, native call or BLE traffic. Aggregates only; no identifiers.
///
/// A *gap* is a `disconnect` row whose next connection starts at least
/// [gapMs] later, or has not started by `observed_at`. Every day describes the
/// most recent gap that started before the day's end, so a fully disconnected
/// day still carries the cause of the gap the device is in.
abstract final class DeviceDropoffSignals {
  static const gapMs = 30 * 60 * 1000;
  static const noAudioSessionMinMs = 60 * 1000;

  /// Firmware powers off near empty without terminating the link, so the
  /// phone sees a supervision timeout. A low, recent, uncharged level is the
  /// only app-side evidence of a flat battery.
  static const flatBatteryLevel = 5;
  static const flatBatteryMaxAgeMs = 60 * 60 * 1000;

  /// RSSI is polled about every 10 s; a sample older than this says nothing
  /// about the moment of loss.
  static const rssiMaxAgeMs = 30 * 1000;
  static const outOfRangeRssi = -85;
  static const strongRssi = -75;

  /// Cumulative rise of a non-decreasing battery run that counts as charging.
  static const chargeRiseLevels = 5;

  /// A link that drops this soon after connecting is a short session. Support
  /// reports "keeps disconnecting seconds after connecting, even at 100%"; a
  /// put-down pendant does not reconnect at all.
  static const shortSessionMs = 30 * 1000;

  /// Two samples this close that differ by this much are an erratic reading,
  /// in either direction ("erratic battery reading", "stuck at 1% then off").
  static const erraticStepLevels = 20;
  static const erraticStepMaxMs = 10 * 60 * 1000;

  /// Level at or below which time is counted as stuck low; samples further
  /// apart than [lowSpanMaxMs] are not assumed to hold the level between them.
  static const lowBatteryLevel = 5;
  static const lowSpanMaxMs = 2 * 60 * 60 * 1000;

  static const _pairingReasons = {'pairing_lost', 'paired_to_another_phone', 'link_key_mismatch'};
  static const _phoneReasons = {'bluetooth_off', 'app_closed'};
  static const _trends = {'fading', 'sudden', 'gap', 'unknown'};

  /// True when the open `connected_at` stamp names an established link.
  ///
  /// iOS stamps it in `didConnect`. Android stamps it when a GATT attempt
  /// starts, before the link is established, so the stamp alone is not proof.
  /// A packet, or an RSSI read, at or after the stamp is a GATT operation that
  /// cannot happen before the link is up, so either proves establishment on
  /// both platforms. A pending attempt has neither, and a sample from the
  /// previous session predates the new stamp because the history is cleared
  /// when the link comes up.
  static bool linkEstablished(Map<String, dynamic> diagnostics) {
    final connectedAt = diagnostics['connected_at'] is int ? diagnostics['connected_at'] as int : 0;
    if (connectedAt <= 0) return false;
    final packetOnLink = (diagnostics['audio_packet_days'] as List? ?? [])
        .whereType<Map>()
        .any((point) => point['last_at'] is int && (point['last_at'] as int) >= connectedAt);
    if (packetOnLink) return true;
    return (diagnostics['rssi_samples'] as List? ?? [])
        .whereType<Map>()
        .any((sample) => sample['ts'] is int && (sample['ts'] as int) >= connectedAt);
  }

  static Map<String, dynamic> rollup(Map<String, dynamic> diagnostics, DateTime day) {
    final start = DateTime(day.year, day.month, day.day).millisecondsSinceEpoch;
    final end = DateTime(day.year, day.month, day.day + 1).millisecondsSinceEpoch;
    final observedAt = diagnostics['observed_at'] is int ? diagnostics['observed_at'] as int : end;
    final exposureEnd = observedAt.clamp(start, end);

    final rows = (diagnostics['disconnect_history_v2'] as List? ?? [])
        .whereType<Map>()
        .where((row) => row['timestamp'] is int)
        .toList()
      ..sort((a, b) => (a['timestamp'] as int).compareTo(b['timestamp'] as int));
    final disconnects = rows.where((row) => row['eventType'] == 'disconnect').toList();
    final failures = [
      for (final row in rows)
        if (row['eventType'] == 'fail_to_connect') row['timestamp'] as int
    ];
    final connectedAt = diagnostics['connected_at'] is int ? diagnostics['connected_at'] as int : 0;
    final linkProven = linkEstablished(diagnostics);
    final sessions = <({int start, int end, int? packets})>[
      for (final row in disconnects)
        if (row['connectionDurationMs'] is int && (row['connectionDurationMs'] as int) > 0)
          (
            start: (row['timestamp'] as int) - (row['connectionDurationMs'] as int),
            end: row['timestamp'] as int,
            packets: row['audioPacketsReceived'] is int ? row['audioPacketsReceived'] as int : null,
          ),
      if (linkProven && connectedAt < observedAt)
        (
          start: connectedAt,
          end: observedAt,
          packets: diagnostics['audio_packets_received'] is int ? diagnostics['audio_packets_received'] as int : null,
        ),
    ];
    final battery = (diagnostics['battery_history_v2'] as List? ?? [])
        .whereType<Map>()
        .where((point) => point['ts'] is int && point['level'] is num)
        .toList()
      ..sort((a, b) => (a['ts'] as int).compareTo(b['ts'] as int));

    int? reconnectAt(Map row) {
      final ts = row['timestamp'] as int;
      final measured = row['timeToReconnectMs'];
      if (measured is int && measured > 0) return ts + measured;
      // Audio resuming on this row's outage proves the link came back, even
      // when no later disconnect row records the next session.
      final resumed = row['lostAudioResolvedAt'];
      int? next = resumed is int && resumed > ts ? resumed : null;
      for (final session in sessions) {
        if (session.start >= ts && (next == null || session.start < next)) next = session.start;
      }
      return next;
    }

    Map? batteryBefore(int ts, {int back = 0}) {
      final before = battery.where((point) => (point['ts'] as int) <= ts).toList();
      return before.length > back ? before[before.length - 1 - back] : null;
    }

    final gaps = <({Map row, int? reconnect, String cause})>[];
    for (final row in disconnects) {
      final ts = row['timestamp'] as int;
      final reconnect = reconnectAt(row);
      if ((reconnect ?? observedAt) - ts < gapMs) continue;
      gaps.add((row: row, reconnect: reconnect, cause: cause(row, batteryBefore(ts), batteryBefore(ts, back: 1))));
    }

    final longGapsByCause = <String, int>{};
    for (final gap in gaps) {
      final ts = gap.row['timestamp'] as int;
      if (ts < start || ts >= end) continue;
      longGapsByCause[gap.cause] = (longGapsByCause[gap.cause] ?? 0) + 1;
    }

    final shortSessions = [
      for (final session in sessions)
        if (session.end - session.start < shortSessionMs && session.end < observedAt) session.end
    ];

    final result = <String, dynamic>{
      'short_sessions': shortSessions.where((at) => at >= start && at < end).length,
      'long_gaps': longGapsByCause.values.fold<int>(0, (sum, count) => sum + count),
      'long_gaps_by_cause': longGapsByCause,
      ..._audio(diagnostics, sessions, start, exposureEnd),
      ..._battery(battery, start, end),
    };

    final current = gaps.lastWhere((gap) => (gap.row['timestamp'] as int) < exposureEnd,
        orElse: () => (row: const {}, reconnect: null, cause: ''));
    if (current.cause.isEmpty) return result;
    final row = current.row;
    final ts = row['timestamp'] as int;
    final gapEnd = current.reconnect == null ? exposureEnd : current.reconnect!.clamp(ts, exposureEnd);
    final level = batteryBefore(ts);
    final rssi = row['lastRssi'];
    final rssiAge = row['lastRssiAgeMs'];
    final trend = row['rssiTrend'];
    result.addAll({
      'gap_cause': current.cause,
      'gap_age_hours': (exposureEnd - ts) ~/ 3600000,
      'gap_minutes': (gapEnd - ts) ~/ 60000,
      'gap_open_at_day_end': current.reconnect == null || current.reconnect! >= exposureEnd,
      'gap_battery_level': (level?['level'] as num?)?.toInt(),
      'gap_battery_age_min': level == null ? null : (ts - (level['ts'] as int)) ~/ 60000,
      'gap_battery_charging': level?['charging'] is bool ? level!['charging'] : null,
      'gap_last_rssi': rssi is int && rssi < 0 ? rssi : null,
      'gap_rssi_age_s': rssiAge is int && rssiAge >= 0 ? rssiAge ~/ 1000 : null,
      'gap_rssi_trend': trend is String && _trends.contains(trend) ? trend : 'unknown',
      'gap_fail_to_connect': failures.where((at) => at >= ts && at < gapEnd).length,
      'gap_short_sessions_24h': shortSessions.where((at) => at > ts - 24 * 3600 * 1000 && at <= ts).length,
      ..._scans(diagnostics, ts, gapEnd, observedAt),
    });
    // Reconnect intent is a snapshot of now, so it only describes a gap that
    // is still open when the snapshot was taken.
    if (current.reconnect == null) {
      for (final key in ['saved_reconnect_enabled', 'reconnect_suppressed']) {
        if (diagnostics[key] is bool) result['gap_$key'] = diagnostics[key];
      }
    }
    return result;
  }

  /// First match wins. `connection_timeout` alone cannot separate causes:
  /// firmware power-off and battery-critical shutdown drop the link without a
  /// terminate, exactly like walking out of range.
  /// [prior] is the sample before [battery]. Most firmware reports no
  /// charging bit, so an unknown bit counts as not charging unless the level
  /// was rising into the loss.
  static String cause(Map row, Map? battery, [Map? prior]) {
    final reason = row['reason']?.toString() ?? '';
    if (row['isManual'] == true || reason == 'manual') return 'manual';
    if (_pairingReasons.contains(reason)) return 'pairing_lost';
    if (_phoneReasons.contains(reason)) return 'phone_side';
    final ts = row['timestamp'] as int;
    final level = battery?['level'];
    final levelAt = battery?['ts'];
    if (level is num &&
        levelAt is int &&
        ts - levelAt <= flatBatteryMaxAgeMs &&
        level <= flatBatteryLevel &&
        battery?['charging'] != true &&
        !(prior?['level'] is num && (prior!['level'] as num) < level)) {
      return 'battery_flat';
    }
    if (row['rssiTrend'] == 'fading') return 'out_of_range';
    final rssi = row['lastRssi'];
    final age = row['lastRssiAgeMs'];
    if (rssi is int && rssi < 0 && age is int && age >= 0 && age <= rssiMaxAgeMs) {
      if (rssi <= outOfRangeRssi) return 'out_of_range';
      if (rssi >= strongRssi) return 'power_off';
    }
    return 'unknown';
  }

  /// Connected time split by whether the link delivered audio. Only devices
  /// that have delivered audio in retained history are judged, so a device
  /// type that never streams over this characteristic is not "no audio".
  static Map<String, dynamic> _audio(
    Map<String, dynamic> diagnostics,
    List<({int start, int end, int? packets})> sessions,
    int start,
    int end,
  ) {
    final streams = sessions.any((session) => (session.packets ?? 0) > 0) ||
        (diagnostics['audio_packet_days'] as List? ?? [])
            .whereType<Map>()
            .any((point) => point['received'] is int && (point['received'] as int) > 0);
    if (!streams) return const {};
    // A session counter restarts with the process; the day bucket's last
    // packet time does not. A packet inside the session means it had audio.
    final packetTimes = [
      for (final point in (diagnostics['audio_packet_days'] as List? ?? []).whereType<Map>())
        if (point['last_at'] is int) point['last_at'] as int
    ];
    var silentMs = 0;
    var silentSessions = 0;
    for (final session in sessions) {
      if (session.packets != 0 || session.end - session.start < noAudioSessionMinMs) continue;
      if (packetTimes.any((at) => at >= session.start && at <= session.end)) continue;
      final overlap = session.end.clamp(start, end) - session.start.clamp(start, end);
      if (overlap <= 0) continue;
      silentMs += overlap;
      silentSessions++;
    }
    return {'connected_no_audio_seconds': silentMs ~/ 1000, 'connected_no_audio_sessions': silentSessions};
  }

  /// Charging inferred from the level itself, for firmware that does not
  /// report a charging bit. A non-decreasing run that gains
  /// [chargeRiseLevels] counts once, on the day it crosses the threshold;
  /// a run may span a disconnection (charged off the link).
  static Map<String, dynamic> _battery(List<Map> battery, int start, int end) {
    int? low;
    int? high;
    var rises = 0;
    int? runBase;
    var counted = false;
    num? previous;
    int? previousTs;
    var erratic = 0;
    var lowMs = 0;
    for (final point in battery) {
      final ts = point['ts'] as int;
      final level = point['level'] as num;
      if (previous != null && previousTs != null && ts > previousTs) {
        if (ts >= start &&
            ts < end &&
            ts - previousTs <= erraticStepMaxMs &&
            (level - previous).abs() >= erraticStepLevels) {
          erratic++;
        }
        if (previous <= lowBatteryLevel && ts - previousTs <= lowSpanMaxMs) {
          lowMs += ts.clamp(start, end) - previousTs.clamp(start, end);
        }
      }
      if (previous == null || level < previous) {
        runBase = level.toInt();
        counted = false;
      } else if (!counted && level - runBase! >= chargeRiseLevels) {
        counted = true;
        if (ts >= start && ts < end) rises++;
      }
      previous = level;
      previousTs = ts;
      if (ts < start || ts >= end) continue;
      if (low == null || level < low) low = level.toInt();
      if (high == null || level > high) high = level.toInt();
    }
    return {
      'charge_inferred_events': rises,
      'battery_erratic_steps': erratic,
      'battery_low_seconds': lowMs ~/ 1000,
      if (low != null) 'battery_min_level': low,
      if (high != null) 'battery_max_level': high,
    };
  }

  /// iOS logs reconnect scans for 24 h (500 rows). Android reconnects with a
  /// passive OS scan and logs none, so it reports nothing rather than zero.
  /// Analytics drops null values, so coverage is explicit: `gap_scan_covered`
  /// false means the log no longer reaches back to the gap start and the
  /// counts are omitted (unknown), not zero.
  static Map<String, dynamic> _scans(Map<String, dynamic> diagnostics, int from, int to, int observedAt) {
    if (diagnostics['saved_reconnect_enabled'] is! bool) return const {};
    final log = (diagnostics['ble_log'] as List? ?? []).whereType<Map>().where((row) => row['ts'] is int).toList();
    final coveredFrom = log.length >= 500 ? log.first['ts'] as int : observedAt - 24 * 3600 * 1000;
    if (coveredFrom > from) return {'gap_scan_covered': false};
    var windows = 0;
    var sightings = 0;
    for (final row in log) {
      final ts = row['ts'] as int;
      if (ts < from || ts >= to) continue;
      if (row['event'] == 'reconnect_scan_started') windows++;
      if (row['event'] == 'reconnect_scan_result' && row['detail']?.toString().contains('saved_target=true') == true) {
        sightings++;
      }
    }
    return {'gap_scan_covered': true, 'gap_scan_windows': windows, 'gap_advert_sightings': sightings};
  }
}
