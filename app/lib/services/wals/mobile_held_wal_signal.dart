// Count sealed mobile WALs still in phone custody. No file identifiers or
// audio leave the device, and reporting never blocks the upload drain.
import 'dart:async';
import 'dart:math';

import 'package:omi/services/experiments/mobile_batch_upload_hold_gate.dart';
import 'package:omi/services/wals/sync_upload_batch.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/analytics/analytics_manager.dart' show AnalyticsManager;
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';

typedef _Snapshot = ({int count, int oldestAgeSeconds, MobileHeldWalBacklogHoldState state});

class MobileHeldWalSignal {
  MobileHeldWalSignal({
    Future<bool?> Function(bool refresh)? cohort,
    void Function(MobileHeldWalBacklog)? emit,
    String? Function(Wal)? holdLabel,
  })  : _cohort = cohort ?? _readCohort,
        _emit = emit ?? const TypedEvents().emit,
        _holdLabel = holdLabel;

  static const _hour = Duration(hours: 1);
  static const _refreshInterval = Duration(minutes: 1);

  final Future<bool?> Function(bool refresh) _cohort;
  final void Function(MobileHeldWalBacklog) _emit;
  final String? Function(Wal)? _holdLabel;
  final _pending = <MobileHeldWalBacklogTrigger, _Snapshot>{};
  DateTime? _nextHourly;
  DateTime? _lastFlagRefresh;
  bool _started = false;
  bool _sending = false;
  int _accountEpoch = 0;

  static Future<bool?> _readCohort(bool refresh) => AnalyticsManager().resolvedBooleanFeatureFlag(
        MobileBatchUploadHoldGate.enabledFlag,
        refresh: refresh,
        refreshTimeout: const Duration(seconds: 6),
      );

  void startup(Iterable<Wal> wals, DateTime now) {
    if (_started) return;
    _started = true;
    _nextHourly = now.add(_hour);
    _sample(MobileHeldWalBacklogTrigger.startup, wals, now);
  }

  void foreground(Iterable<Wal> wals, DateTime now) => _sample(MobileHeldWalBacklogTrigger.foreground, wals, now);

  void hourly(Iterable<Wal> wals, DateTime now) {
    final next = _nextHourly ??= now.add(_hour);
    if (!now.isBefore(next)) {
      _nextHourly = now.add(_hour);
      _sample(MobileHeldWalBacklogTrigger.hourly, wals, now);
    } else {
      // Cold startup may predate identity or the flag snapshot. Keep the
      // aggregate captured before the upload drain and retry after readiness.
      unawaited(_send(now));
    }
  }

  void clearUserData() {
    _accountEpoch++;
    _pending.clear();
    _lastFlagRefresh = null;
  }

  void _sample(MobileHeldWalBacklogTrigger trigger, Iterable<Wal> wals, DateTime now) {
    final nowMs = now.millisecondsSinceEpoch;
    var count = 0;
    int? oldestSealMs;
    String? oldestState;
    for (final wal in wals) {
      if (wal.storage != WalStorage.disk ||
          (wal.status != WalStatus.miss && wal.status != WalStatus.uploadRejected) ||
          wal.holdForUser ||
          wal.totalFrames <= 0 ||
          !isMobileStandardBatchWal(wal)) {
        continue;
      }
      final sealMs = wal.mobileBatchHold?.sealedAtMs ?? (wal.timerStart + wal.seconds) * 1000;
      if (sealMs <= 0) continue;
      count++;
      if (oldestSealMs == null || sealMs < oldestSealMs) {
        oldestSealMs = sealMs;
        // A cold restart has no active hold. The prior seal state is
        // still available for the separately labelled recovery upload.
        oldestState = wal.recoveredMobileBatchHold ? null : _holdLabel?.call(wal) ?? wal.mobileBatchHold?.state;
      }
    }
    _pending[trigger] = (
      count: min(count, 65535),
      oldestAgeSeconds: ((nowMs - (oldestSealMs ?? nowMs)) ~/ 1000).clamp(0, 86400),
      state: MobileHeldWalBacklogHoldState.values.firstWhere(
        (state) => state.wireName == oldestState,
        orElse: () => MobileHeldWalBacklogHoldState.unknown,
      ),
    );
    unawaited(_send(now));
  }

  Future<void> _send(DateTime now) async {
    if (_sending || _pending.isEmpty) return;
    _sending = true;
    final epoch = _accountEpoch;
    try {
      var enabled = await _cohort(false);
      if (epoch != _accountEpoch) return;
      final last = _lastFlagRefresh;
      if (enabled == null && (last == null || now.difference(last) >= _refreshInterval)) {
        _lastFlagRefresh = now;
        enabled = await _cohort(true);
      }
      if (enabled == null || epoch != _accountEpoch) return;
      final snapshots = Map.of(_pending);
      _pending.clear();
      for (final entry in snapshots.entries) {
        _emit(MobileHeldWalBacklog(
          trigger: entry.key,
          heldWalCount: entry.value.count,
          oldestHeldAgeS: entry.value.oldestAgeSeconds,
          holdFlagOn: enabled,
          holdState: entry.value.state,
          cohort: enabled ? MobileHeldWalBacklogCohort.on : MobileHeldWalBacklogCohort.off,
        ));
      }
    } catch (_) {
      // Analytics failures cannot change capture, upload, or custody.
    } finally {
      _sending = false;
    }
  }
}
