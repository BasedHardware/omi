import 'dart:async';

typedef FullyChargedNotification = void Function(int batteryLevel);
typedef FullyChargedLevelMismatch = void Function({required int notifiedAtLevel, required int correctedLevel});

/// Decides when the "Omi is fully charged" notification may fire.
///
/// The phone only learns the pendant level when a BLE battery sample arrives.
/// A cached 100% from an earlier charge must not notify on the next plug-in:
/// the sample has to be timestamped strictly after the charge-start edge, and
/// the device has to have stayed on the charger for [minimumOnChargerDwell].
///
/// State is per device id. A link drop keeps that device's once-per-cycle
/// alert; it does not suppress a different pendant, and it does not survive
/// evidence of a new charge cycle (an observed unplug, or a reconnect whose
/// first fresh sample is below 100). The map keeps at most [maxTrackedDevices]
/// identities. Disconnect marks a device evictable; a newly seen identity past
/// the bound drops the oldest disconnected one.
///
/// Dwell is measured with a monotonic clock ([Stopwatch] unless a test injects
/// one). [Stopwatch] excludes deep suspend on Android. The edge-to-notify
/// window is one minute and the phone is in use while docking, so time spent
/// suspended in that window is acceptable. Sample freshness stays on wall
/// timestamps against the charge-edge wall time — the phone stamps both, and
/// a backward step of the wall clock must not promote a cached reading.
///
/// Sixty seconds is the dwell. Charger inrush makes the fuel gauge spike for
/// a short stretch after dock (David, 2026-10-11: the notification fired at
/// the plug-in instant while the device face showed 66%, 15 minutes to 80%).
/// A few seconds still races that spike. Several minutes would leave a
/// genuinely full pendant sitting on the charger after the notification
/// itself says to unplug. One minute lets the first post-dock sample settle
/// and still tells the user to unplug about a minute after a confirming 100%.
class FullyChargedAlertGate {
  FullyChargedAlertGate({
    DateTime Function()? now,
    Duration Function()? monotonicNow,
    Duration? minimumDwell,
    required this.onFullyCharged,
    this.onLevelMismatch,
  })  : _now = now ?? DateTime.now,
        _monotonicNowOverride = monotonicNow,
        minimumDwell = minimumDwell ?? minimumOnChargerDwell;

  static const Duration minimumOnChargerDwell = Duration(seconds: 60);

  /// A sample this far before the charge-edge wall time is a cached reading
  /// from before this dock (the original stale-100 bug), not clock skew.
  static const Duration preEdgeStaleTolerance = Duration(seconds: 2);

  /// Disconnected identities are dropped once a new device would exceed this.
  static const int maxTrackedDevices = 4;

  final Duration minimumDwell;
  final DateTime Function() _now;
  final Duration Function()? _monotonicNowOverride;
  final Stopwatch _dwellClock = Stopwatch()..start();
  final FullyChargedNotification onFullyCharged;
  final FullyChargedLevelMismatch? onLevelMismatch;

  final Map<String, _Cycle> _cycles = {};
  final List<String> _order = [];
  String? _focusId;
  String? _lastFiredDeviceId;
  bool _disposed = false;

  Duration _monotonicNow() => _monotonicNowOverride?.call() ?? _dwellClock.elapsed;

  DateTime? chargeStartedAtFor(String deviceId) => _cycles[deviceId]?.chargeStartedWall;

  bool hasAlertedFor(String deviceId) => _cycles[deviceId]?.alerted ?? false;

  bool hasChargeWindowFor(String deviceId) => _cycles[deviceId]?.chargeStartedWall != null;

  /// The device most recently charged or sampled. Single-device callers use this.
  DateTime? get chargeStartedAt => _focusId == null ? null : chargeStartedAtFor(_focusId!);

  bool get hasAlerted => _focusId != null && hasAlertedFor(_focusId!);

  bool get hasChargeWindow => _focusId != null && hasChargeWindowFor(_focusId!);

  String? get lastFiredDeviceId => _lastFiredDeviceId;

  void dispose() {
    _disposed = true;
    reset();
  }

  /// Drops every device cycle. Account switch must not keep another user's alert.
  void reset() {
    for (final cycle in _cycles.values) {
      cycle.cancelTimer();
    }
    _cycles.clear();
    _order.clear();
    _focusId = null;
    _lastFiredDeviceId = null;
  }

  /// Plug-in, or a reconnect while the device is still on the charger.
  /// Restarts the dwell anchor. Does not clear [hasAlertedFor] by itself: one
  /// notification per charge cycle, and a link drop is not an unplug. A later
  /// fresh sample below 100 after this restart is evidence the cycle ended
  /// while the link was down.
  void onChargeStarted(String deviceId) {
    if (_disposed || deviceId.isEmpty) return;
    final cycle = _retain(deviceId);
    final restartingAlertedCycle = cycle.alerted;
    cycle.cancelTimer();
    cycle.suspended = false;
    cycle.linked = true;
    cycle.chargeStartedWall = _now();
    cycle.chargeStartedMono = _monotonicNow();
    cycle.awaitingNewCycleEvidence = restartingAlertedCycle;
    _focusId = deviceId;
  }

  /// Charger removed. Clears the dwell and the once-per-cycle alert.
  void onUnplugged(String deviceId) {
    final cycle = _cycles[deviceId];
    if (cycle == null) return;
    cycle.cancelTimer();
    cycle.suspended = false;
    cycle.chargeStartedWall = null;
    cycle.chargeStartedMono = null;
    cycle.alerted = false;
    cycle.notifiedAtLevel = null;
    cycle.mismatchEmitted = false;
    cycle.presented = false;
    cycle.awaitingNewCycleEvidence = false;
  }

  /// BLE dropped. Cancels a pending dwell fire so the old window cannot
  /// notify while the link is down. The charge cycle survives until an
  /// unplug observation or a reconnect with a fresh sub-100 sample. The
  /// device stays in the map until a newer identity needs the slot.
  void onLinkLost(String deviceId) {
    final cycle = _cycles[deviceId];
    if (cycle == null) return;
    cycle.cancelTimer();
    cycle.suspended = true;
    cycle.linked = false;
  }

  /// A battery sample from [deviceId]. [level] is the reported percent.
  /// [at] overrides the sample's wall timestamp; production leaves it null
  /// so the phone clock at arrival is used.
  void onBatterySample(String deviceId, int level, {DateTime? at}) {
    if (_disposed || deviceId.isEmpty) return;
    final cycle = _retain(deviceId);
    final sampleAt = at ?? _now();
    cycle.lastLevel = level;
    cycle.lastSampleAt = sampleAt;
    cycle.lastSampleMono = _monotonicNow();
    _focusId = deviceId;
    // A packet that arrives after the link drop is not a reconnect sample.
    // The next [onChargeStarted] is what restarts the cycle.
    if (cycle.suspended) return;
    cycle.linked = true;
    _noteNewCycleEvidence(cycle, level, sampleAt);
    _maybeRecordMismatch(cycle, level, sampleAt);
    _evaluate(deviceId, cycle);
  }

  /// The notification passed the permission check and [createNotification] ran.
  /// Mismatch telemetry waits for this; an attempt that never presented must
  /// not look like a delivered alert that the fuel gauge then corrected.
  void markPresented(String deviceId) {
    if (_disposed) return;
    final cycle = _cycles[deviceId];
    if (cycle == null || !cycle.alerted) return;
    cycle.presented = true;
    final level = cycle.lastLevel;
    final at = cycle.lastSampleAt;
    if (level != null && at != null) _maybeRecordMismatch(cycle, level, at);
  }

  void _noteNewCycleEvidence(_Cycle cycle, int level, DateTime sampleAt) {
    if (!cycle.awaitingNewCycleEvidence || !_isFreshSample(cycle, sampleAt)) return;
    cycle.awaitingNewCycleEvidence = false;
    if (level >= 100) return;
    cycle.alerted = false;
    cycle.notifiedAtLevel = null;
    cycle.mismatchEmitted = false;
    cycle.presented = false;
  }

  void _maybeRecordMismatch(_Cycle cycle, int level, DateTime sampleAt) {
    final notifiedAtLevel = cycle.notifiedAtLevel;
    final started = cycle.chargeStartedWall;
    if (!cycle.presented || !cycle.alerted || notifiedAtLevel == null || started == null || cycle.mismatchEmitted) {
      return;
    }
    if (level >= 100 || !_isFreshSample(cycle, sampleAt)) return;
    cycle.mismatchEmitted = true;
    onLevelMismatch?.call(notifiedAtLevel: notifiedAtLevel, correctedLevel: level);
  }

  bool _isFreshSample(_Cycle cycle, DateTime sampleAt) {
    final edge = cycle.chargeStartedWall;
    final edgeMono = cycle.chargeStartedMono;
    final sampleMono = cycle.lastSampleMono;
    if (edge == null || edgeMono == null || sampleMono == null) return false;
    // Far before the edge: cached reading. Strictly-after still rejects a
    // sample inside the tolerance, including one stamped at the edge itself.
    if (edge.difference(sampleAt) > preEdgeStaleTolerance) return false;
    if (!sampleAt.isAfter(edge)) return false;
    // Observed before the edge on the monotonic clock. A wall-clock step
    // cannot launder that into a post-edge sample.
    if (sampleMono < edgeMono) return false;
    return true;
  }

  void _evaluate(String deviceId, _Cycle cycle) {
    if (_disposed || cycle.suspended || cycle.alerted) return;
    final started = cycle.chargeStartedWall;
    final edgeMono = cycle.chargeStartedMono;
    final sampleAt = cycle.lastSampleAt;
    final level = cycle.lastLevel;
    if (started == null || edgeMono == null || sampleAt == null || level == null) return;
    if (!_isFreshSample(cycle, sampleAt) || level < 100) {
      cycle.cancelTimer();
      return;
    }
    final elapsed = _monotonicNow() - edgeMono;
    if (elapsed >= minimumDwell) {
      _fire(deviceId, cycle, level);
      return;
    }
    final remaining = minimumDwell - elapsed;
    cycle.cancelTimer();
    cycle.timer = Timer(remaining, () {
      cycle.timer = null;
      _evaluate(deviceId, cycle);
    });
  }

  void _fire(String deviceId, _Cycle cycle, int level) {
    if (_disposed || cycle.suspended || cycle.alerted) return;
    cycle.cancelTimer();
    cycle.alerted = true;
    cycle.notifiedAtLevel = level;
    cycle.presented = false;
    cycle.awaitingNewCycleEvidence = false;
    _lastFiredDeviceId = deviceId;
    onFullyCharged(level);
  }

  _Cycle _retain(String deviceId) {
    final existing = _cycles[deviceId];
    if (existing != null) {
      _touch(deviceId);
      return existing;
    }
    while (_cycles.length >= maxTrackedDevices) {
      final victim = _evictionCandidate();
      if (victim == null) break;
      _drop(victim);
    }
    final cycle = _Cycle();
    _cycles[deviceId] = cycle;
    _order.add(deviceId);
    return cycle;
  }

  String? _evictionCandidate() {
    for (final id in _order) {
      final cycle = _cycles[id];
      if (cycle != null && !cycle.linked) return id;
    }
    return _order.isEmpty ? null : _order.first;
  }

  void _touch(String deviceId) {
    _order.remove(deviceId);
    _order.add(deviceId);
  }

  void _drop(String deviceId) {
    _order.remove(deviceId);
    _cycles.remove(deviceId)?.cancelTimer();
    if (_focusId == deviceId) _focusId = null;
    if (_lastFiredDeviceId == deviceId) _lastFiredDeviceId = null;
  }
}

class _Cycle {
  DateTime? chargeStartedWall;
  Duration? chargeStartedMono;
  DateTime? lastSampleAt;
  Duration? lastSampleMono;
  int? lastLevel;
  bool alerted = false;
  int? notifiedAtLevel;
  bool mismatchEmitted = false;
  bool presented = false;
  bool awaitingNewCycleEvidence = false;
  bool suspended = false;
  bool linked = false;
  Timer? timer;

  void cancelTimer() {
    timer?.cancel();
    timer = null;
  }
}
