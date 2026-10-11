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
    Duration? minimumDwell,
    required this.onFullyCharged,
    this.onLevelMismatch,
  })  : _now = now ?? DateTime.now,
        minimumDwell = minimumDwell ?? minimumOnChargerDwell;

  static const Duration minimumOnChargerDwell = Duration(seconds: 60);

  final Duration minimumDwell;
  final DateTime Function() _now;
  final FullyChargedNotification onFullyCharged;
  final FullyChargedLevelMismatch? onLevelMismatch;

  DateTime? _chargeStartedAt;
  DateTime? _lastBatterySampleAt;
  int? _lastBatteryLevel;
  bool _alerted = false;
  int? _notifiedAtLevel;
  bool _mismatchEmitted = false;
  bool _suspended = false;
  bool _disposed = false;
  Timer? _dwellTimer;

  DateTime? get chargeStartedAt => _chargeStartedAt;
  bool get hasAlerted => _alerted;
  bool get hasChargeWindow => _chargeStartedAt != null;

  void dispose() {
    _disposed = true;
    _dwellTimer?.cancel();
    _dwellTimer = null;
  }

  /// Plug-in, or a reconnect while the device is still on the charger.
  /// Restarts the dwell anchor. Does not clear [hasAlerted]: one notification
  /// per charge cycle, and a link drop is not an unplug.
  void onChargeStarted() {
    _dwellTimer?.cancel();
    _dwellTimer = null;
    _suspended = false;
    _chargeStartedAt = _now();
  }

  /// Charger removed. Clears the dwell and the once-per-cycle alert.
  void onUnplugged() {
    _dwellTimer?.cancel();
    _dwellTimer = null;
    _suspended = false;
    _chargeStartedAt = null;
    _alerted = false;
    _notifiedAtLevel = null;
    _mismatchEmitted = false;
  }

  /// BLE dropped. Cancels a pending dwell fire so the old window cannot
  /// notify while the link is down. The charge cycle survives until an
  /// unplug observation; the next [onChargeStarted] restarts dwell.
  void onLinkLost() {
    _dwellTimer?.cancel();
    _dwellTimer = null;
    _suspended = true;
  }

  /// A battery sample from the device. [level] is the reported percent.
  void onBatterySample(int level) {
    if (_disposed) return;
    final sampleAt = _now();
    _lastBatteryLevel = level;
    _lastBatterySampleAt = sampleAt;
    _maybeRecordMismatch(level, sampleAt);
    _evaluate();
  }

  void _maybeRecordMismatch(int level, DateTime sampleAt) {
    final notifiedAtLevel = _notifiedAtLevel;
    final started = _chargeStartedAt;
    if (!_alerted || notifiedAtLevel == null || started == null || _mismatchEmitted) return;
    if (level >= 100 || !sampleAt.isAfter(started)) return;
    _mismatchEmitted = true;
    onLevelMismatch?.call(notifiedAtLevel: notifiedAtLevel, correctedLevel: level);
  }

  void _evaluate() {
    if (_disposed || _suspended || _alerted) return;
    final started = _chargeStartedAt;
    final sampleAt = _lastBatterySampleAt;
    final level = _lastBatteryLevel;
    if (started == null || sampleAt == null || level == null) return;
    if (!sampleAt.isAfter(started) || level < 100) {
      _dwellTimer?.cancel();
      _dwellTimer = null;
      return;
    }
    final elapsed = _now().difference(started);
    if (elapsed >= minimumDwell) {
      _fire(level);
      return;
    }
    final remaining = minimumDwell - elapsed;
    _dwellTimer?.cancel();
    _dwellTimer = Timer(remaining, () {
      _dwellTimer = null;
      _evaluate();
    });
  }

  void _fire(int level) {
    if (_disposed || _suspended || _alerted) return;
    _dwellTimer?.cancel();
    _dwellTimer = null;
    _alerted = true;
    _notifiedAtLevel = level;
    onFullyCharged(level);
  }
}
