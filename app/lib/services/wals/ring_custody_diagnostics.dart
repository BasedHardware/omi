// Bounded content-free ring observations for the existing diagnostics export.
// This recorder never grants custody, changes clocks, or retains audio bodies.
import 'dart:collection';

import 'device_capture_clock.dart';

/// Vocabulary, rather than arbitrary log text, keeps this buffer content-free.
enum RingDiagnosticEvent {
  connection,
  captureMuteReadback,
  liveGrant,
  readRequest,
  readBegin,
  readDone,
  readTimeout,
  readStopped,
  chunkDurable,
  advanceAttempt,
  advanceResult,
  markAccepted,
  markRejected,
}

enum RingDiagnosticReason {
  none,
  firstDataTimeout,
  idleTimeout,
  incomplete,
  connectionChanged,
  notEnabled,
  ringMismatch,
  evidenceBroken,
  duplicate,
  boundaryUnresolved,
  malformed,
  commandFailed,
  deadline,
}

enum RingCaptureRoute { ordinaryWal, mobileBatch }

class _Trace {
  _Trace(this.sinceMs);
  final int sinceMs;
  int? epoch;
  int? grantedAtMs;
  final events = Queue<Map<String, Object?>>();
  final firstRecords = <Map<String, Object?>>[];
  final invalidRecords = Queue<Map<String, Object?>>();
  final minutes = <int, Map<String, int>>{};
  Map<String, Object?>? previous;
  bool? previousPlausible;
  int? previousOrdinal;
  int readRecords = 0;
}

/// Small process-local flight recorder. Never used for custody or dedup.
/// Restart deliberately means "not observed", not a fabricated history.
class RingCustodyDiagnostics {
  RingCustodyDiagnostics({DateTime Function()? now}) : _now = now ?? DateTime.now;
  static final shared = RingCustodyDiagnostics();
  static const maxDevices = 4;
  static const maxEvents = 20;
  static const maxFirstRecords = 16;
  static const maxInvalidRecords = 64;
  final DateTime Function() _now;
  final _traces = <String, _Trace>{};

  _Trace _trace(String deviceId) {
    final existing = _traces.remove(deviceId);
    final trace = existing ?? _Trace(_now().millisecondsSinceEpoch);
    _traces[deviceId] = trace;
    while (_traces.length > maxDevices) {
      _traces.remove(_traces.keys.first);
    }
    return trace;
  }

  void event(String deviceId, RingDiagnosticEvent event,
      {int? epoch,
      int? ringId,
      int? start,
      int? end,
      int? records,
      int? status,
      bool? granted,
      bool? requestedMuted,
      bool? observedMuted,
      RingDiagnosticReason reason = RingDiagnosticReason.none}) {
    final t = _trace(deviceId);
    final at = _now().millisecondsSinceEpoch;
    if (event == RingDiagnosticEvent.connection) {
      t.epoch = epoch;
      t.grantedAtMs = null;
    }
    if (event == RingDiagnosticEvent.liveGrant && granted == true) t.grantedAtMs = at;
    t.events.add({
      'at_ms': at,
      'event': event.name,
      'reason': reason.name,
      if (epoch != null) 'connection_epoch': epoch,
      if (ringId != null) 'ring_id': ringId,
      if (start != null) 'start_seq': start,
      if (end != null) 'end_seq': end,
      if (records != null) 'records': records,
      if (status != null) 'status': status,
      if (granted != null) 'granted': granted,
      if (requestedMuted != null) 'requested_muted': requestedMuted,
      if (observedMuted != null) 'observed_muted': observedMuted,
    });
    while (t.events.length > maxEvents) {
      t.events.removeFirst();
    }
  }

  void beginRead(String deviceId,
      {required int epoch, required int? ringId, required int start, required int records}) {
    final t = _trace(deviceId);
    t.firstRecords.clear();
    t.previous = null;
    t.previousOrdinal = null;
    t.previousPlausible = null;
    t.readRecords = 0;
    event(deviceId, RingDiagnosticEvent.readRequest, epoch: epoch, ringId: ringId, start: start, records: records);
  }

  void record(String deviceId,
      {required int epoch,
      required int? ringId,
      required int ordinal,
      required List<int> record,
      required int timestamp,
      required int frames,
      required int phoneSeconds}) {
    if (record.length < 8 || record.take(8).any((b) => b < 0 || b > 255)) return;
    final t = _trace(deviceId);
    t.readRecords++;
    final plausible = deviceCaptureTimePlausible(timestamp, phoneSeconds) && phoneCaptureClockPlausible(phoneSeconds);
    if (t.previousOrdinal == ordinal - 1) t.previous?['next_plausible'] = plausible;
    final retain = t.firstRecords.length < maxFirstRecords || !plausible;
    Map<String, Object?>? sample;
    if (retain) {
      sample = {
        'at_ms': _now().millisecondsSinceEpoch,
        'connection_epoch': epoch,
        'ring_id': ringId,
        'ordinal': ordinal,
        // Only eight diagnostic prefix bytes, not intelligible speech content:
        // timestamp + frame-length/codec prefix. Never keep an audio frame/body.
        'prefix_8_hex': record.take(8).map((b) => b.toRadixString(16).padLeft(2, '0')).join(),
        'decoded_timestamp': timestamp,
        'frame_count': frames,
        'plausible': plausible,
        'phone_clock_plausible': phoneCaptureClockPlausible(phoneSeconds),
        'previous_plausible': t.previousOrdinal == ordinal - 1 ? t.previousPlausible : null,
        'next_plausible': null,
      };
      if (t.firstRecords.length < maxFirstRecords) t.firstRecords.add(sample);
      if (!plausible) {
        t.invalidRecords.add(sample);
        while (t.invalidRecords.length > maxInvalidRecords) {
          t.invalidRecords.removeFirst();
        }
      }
    }
    t.previous = sample;
    t.previousOrdinal = ordinal;
    t.previousPlausible = plausible;
    _prune(t);
  }

  void timeout(String deviceId, RingDiagnosticReason reason) {
    final t = _trace(deviceId);
    event(deviceId, RingDiagnosticEvent.readTimeout, records: t.readRecords, reason: reason);
  }

  /// Frame counts at acceptance and durable proof publication are distinct.
  void route(String deviceId, RingCaptureRoute route, {int frames = 1, bool proofPublished = false}) {
    final t = _trace(deviceId);
    final minute = _now().millisecondsSinceEpoch ~/ 60000;
    final counts = t.minutes.putIfAbsent(minute, () => {});
    final key = '${route.name}_${proofPublished ? 'proof_frames' : 'frames'}';
    counts[key] = (counts[key] ?? 0) + frames;
    _prune(t);
  }

  void _prune(_Trace t) {
    final now = _now().millisecondsSinceEpoch;
    t.invalidRecords.removeWhere((r) => now - (r['at_ms']! as int) > 86400000);
    t.minutes.removeWhere((minute, _) => minute < now ~/ 60000 - 59 || minute > now ~/ 60000);
  }

  Map<String, Object?> build(String deviceId,
      {required Map<String, Object?> device,
      Map<String, Object?>? ledger,
      Map<String, int>? walStates,
      int? implausibleWals}) {
    final t = _traces[deviceId];
    if (t != null) _prune(t);
    final counts = <String, int>{};
    for (final minute in t?.minutes.values ?? <Map<String, int>>[]) {
      for (final entry in minute.entries) {
        counts[entry.key] = (counts[entry.key] ?? 0) + entry.value;
      }
    }
    // Explicit allowlists prevent new caller fields from exporting content.
    const deviceKeys = {
      'phone_utc_seconds',
      'phone_clock_plausible',
      'connected',
      'firmware',
      'rtc_raw_seconds',
      'rtc_valid',
      'read_at_ms',
      'rtc_read_started_at_ms',
      'rtc_read_completed_at_ms',
      'connection_epoch',
      'ring_id',
      'read_seq',
      'write_seq',
      'dropped',
      'capacity',
      'used',
      'used_bytes',
      'live_persistence_granted',
      'read_error',
    };
    const ledgerKeys = {
      'connection_epoch',
      'connected',
      'live_enabled',
      'ring_id',
      'read_seq',
      'write_seq',
      'durable_frontier',
      'last_advanced_seq',
      'last_mark_seq',
      'last_advanced_mark_seq',
      'evidence_broken',
      'incarnation_invalid',
      'pending_marks',
      'last_observed_mark_seq',
      'last_observed_mark_index',
      'proof_range_count',
      'proof_record_span',
      'first_unproven_start',
      'first_unproven_length',
      'records_held_behind_gap',
      'batch_proof_ranges',
    };
    return {
      'schema_version': 1,
      'phone_utc_seconds': _now().millisecondsSinceEpoch ~/ 1000,
      'history_scope': 'current_app_process',
      'observed_since_ms': t?.sinceMs,
      'device': {
        for (final e in device.entries)
          if (deviceKeys.contains(e.key) &&
              (e.value == null ||
                  e.value is int ||
                  e.value is bool ||
                  (e.key == 'firmware' &&
                      e.value is String &&
                      RegExp(r'^[a-zA-Z0-9._+ -]{1,64}$').hasMatch(e.value! as String)) ||
                  (e.key == 'read_error' &&
                      const {
                        'absent_pendant',
                        'rtc_wrong_length',
                        'rtc_unavailable',
                        'ring_snapshot_unavailable',
                        'legacy_firmware',
                        'connection_changed'
                      }.contains(e.value))))
            e.key: e.value
      },
      'live_persistence_granted_at_ms': t?.epoch == device['connection_epoch'] ? t?.grantedAtMs : null,
      'events': [for (final e in t?.events ?? <Map<String, Object?>>[]) Map<String, Object?>.of(e)],
      'ledger': ledger == null
          ? null
          : {
              for (final e in ledger.entries)
                if (ledgerKeys.contains(e.key) && (e.value == null || e.value is int || e.value is bool)) e.key: e.value
            },
      'ledger_validation': 'previously_recorded_proofs_not_revalidated_by_export',
      'routes_last_hour': counts,
      'batch_route_observed': counts.containsKey('mobileBatch_frames'),
      'batch_route_note': 'missing_batch_counter_is_unknown_until_owned_route_hook_observes_a_packet',
      'route_window': 'current_process_up_to_60_minute_buckets',
      'wal_states': walStates == null
          ? null
          : {
              for (final e in walStates.entries)
                if (const {
                  'inProgress',
                  'miss',
                  'uploaded',
                  'synced',
                  'corrupted',
                  'outsideRecoveryWindow',
                  'unsupportedAudio',
                  'uploadRejected'
                }.contains(e.key))
                  e.key: e.value,
            },
      'implausible_capture_time_wals': implausibleWals,
      'latest_read_first_records': [
        for (final r in t?.firstRecords ?? <Map<String, Object?>>[]) Map<String, Object?>.of(r)
      ],
      'implausible_records_last_24h': [
        for (final r in t?.invalidRecords ?? <Map<String, Object?>>[]) Map<String, Object?>.of(r)
      ],
    };
  }
}
