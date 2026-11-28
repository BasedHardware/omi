import 'package:flutter/foundation.dart';

// Owns which Omi battery percentage the UI may show. It never changes the raw reading the
// pendant sent; it only withholds numbers the shipping firmware is known to get wrong.

/// Why a pendant battery percentage is being withheld from the UI.
enum BatteryHideReason {
  /// The pendant is charging and reports a low number. Firmware 3.0.24 repeats the
  /// last off-charger reading for the whole charge, so a low number here is stale.
  chargingLow,

  /// A first pairing reports a near-empty, non-charging reading. Users pair a
  /// freshly charged pendant, so a near-empty number then is most likely stuck.
  firstPairing,

  /// The app watched a long charge end and the pendant still reports near-empty.
  longCharge,

  /// A near-empty reading has not moved for a long time. A real near-empty Omi
  /// keeps stepping down and powers itself off; a stuck filter stays flat.
  flat,
}

/// Where readings judged stuck are remembered across reconnects and app restarts.
abstract class BatteryStuckStore {
  /// Device id -> (percent, when it was judged stuck).
  Map<String, (int, DateTime)> load();
  void save(Map<String, (int, DateTime)> readings);
}

class InMemoryBatteryStuckStore implements BatteryStuckStore {
  Map<String, (int, DateTime)> _readings = {};
  @override
  Map<String, (int, DateTime)> load() => Map.of(_readings);
  @override
  void save(Map<String, (int, DateTime)> readings) => _readings = Map.of(readings);
}

/// Decides whether an Omi battery reading is believable enough to show.
///
/// Firmware 3.0.19 and 3.0.21 can keep notifying ~1% after a full charge until the
/// pendant restarts (its filter refuses increases while the charge pin reads idle).
/// 3.0.24 repeats its pre-charge reading while charging. In both cases the number is
/// wrong and alarming, so the app shows the device without a percentage instead.
///
/// Raw readings are untouched: firmware-update gating, diagnostics and telemetry keep
/// using the value the pendant sent. A falling reading always shows, because a real
/// near-empty battery drops and a stuck one does not.
class BatteryDisplayPolicy {
  BatteryDisplayPolicy({DateTime Function()? clock, BatteryStuckStore? store})
      : _clock = clock ?? DateTime.now,
        _store = store ?? InMemoryBatteryStuckStore();

  /// Below this, a charging reading is not shown.
  static const lowWhileCharging = 20;

  /// At or below this (and above 0), a non-charging reading can be stale.
  static const nearEmpty = 5;

  /// A charge this long cannot end near empty.
  static const longCharge = Duration(minutes: 20);

  /// How long after a long charge a near-empty reading stays suspect.
  static const longChargeMemory = Duration(hours: 2);

  /// How long a near-empty reading may stay flat before it is treated as stuck.
  static const flatHold = Duration(minutes: 10);

  /// How long a stuck reading is remembered for the same device.
  static const stuckMemory = Duration(days: 7);

  final DateTime Function() _clock;
  final BatteryStuckStore _store;

  /// False when the remote kill switch is set; every reading then shows as reported.
  bool enabled = true;

  // Per-device charge history. A long charge that ended is kept across reconnects;
  // a charge still in progress is dropped when the link is re-established.
  final Map<String, DateTime> _chargeStartedAt = {};
  final Map<String, DateTime> _longChargeEndedAt = {};
  final Set<String> _firstPairing = {};

  String? _deviceId;
  int _lastLevel = -1;
  int? _flatLevel;
  DateTime? _flatSince;

  /// A falling near-empty reading proved itself real for this connection.
  bool _confirmedDrain = false;

  /// This device's remembered stuck reading, loaded once per connection.
  (int, DateTime)? _remembered;

  /// Starts a new connection to [deviceId]. A charge in progress is not carried over: the
  /// app did not observe the gap, so it cannot count toward a long charge.
  void beginConnection(String deviceId) {
    _chargeStartedAt.remove(deviceId);
    _deviceId = deviceId;
    _lastLevel = -1;
    _flatLevel = null;
    _flatSince = null;
    _confirmedDrain = false;
    _remembered = _store.load()[deviceId];
  }

  /// Marks [deviceId] as being paired for the first time.
  void markFirstPairing(String deviceId) => _firstPairing.add(deviceId);

  /// Records a charging-status reading from the pendant.
  void onCharging(String deviceId, bool charging) {
    final now = _clock();
    if (charging) {
      _chargeStartedAt.putIfAbsent(deviceId, () => now);
      // A drain seen before this charge says nothing about the reading after it.
      if (deviceId == _deviceId) _confirmedDrain = false;
      return;
    }
    final started = _chargeStartedAt.remove(deviceId);
    if (started != null && now.difference(started) >= longCharge) {
      _longChargeEndedAt[deviceId] = now;
    }
  }

  /// Records a battery sample from the current connection.
  void onSample(int level, {required bool charging}) {
    if (level < 0 || level > 100) return;
    final now = _clock();
    final id = _deviceId;
    if (level == 0) {
      // A real 0% ends any remembered stuck value (a stuck filter never reads 0).
      if (id != null) _forgetStuck(id);
    } else if (level > nearEmpty) {
      // A believable reading: the pendant is past any stuck state.
      _confirmedDrain = false;
      if (id != null) {
        _firstPairing.remove(id);
        _longChargeEndedAt.remove(id);
        _forgetStuck(id);
      }
    } else if (!charging && _lastLevel >= 0 && _lastLevel <= nearEmpty && level < _lastLevel) {
      _confirmedDrain = true;
      if (id != null) _forgetStuck(id);
    }
    if (_flatLevel != level) {
      _flatLevel = level;
      _flatSince = now;
    }
    _lastLevel = level;
  }

  /// The reason [level] should be withheld, or null to show it.
  BatteryHideReason? hideReason(int level, {required bool charging}) {
    if (!enabled || level < 0 || level > 100) return null;
    if (charging) return level < lowWhileCharging ? BatteryHideReason.chargingLow : null;
    // 0% is never stuck: the old firmware filter only clamps a nonzero value.
    if (level == 0 || level > nearEmpty || _confirmedDrain) return null;
    final id = _deviceId;
    if (id != null && _firstPairing.contains(id)) return BatteryHideReason.firstPairing;
    final ended = id == null ? null : _longChargeEndedAt[id];
    if (ended != null && _clock().difference(ended) <= longChargeMemory) return BatteryHideReason.longCharge;
    final since = _flatSince;
    if (_flatLevel == level && since != null && _clock().difference(since) >= flatHold) {
      return BatteryHideReason.flat;
    }
    // The same pendant was stuck at exactly this reading before a reconnect or app restart.
    final remembered = _remembered;
    if (remembered != null && remembered.$1 == level && _clock().difference(remembered.$2) <= stuckMemory) {
      return BatteryHideReason.flat;
    }
    return null;
  }

  /// Remembers [level] for the current device when it is proven stuck (flat, or near empty
  /// after a long charge), so the next connection hides it at once instead of after another
  /// [flatHold]. A first-pairing suspicion is never remembered: that pendant may really be empty.
  void rememberIfStuck(int level, {required bool charging}) {
    final id = _deviceId;
    final reason = hideReason(level, charging: charging);
    if (id == null || (reason != BatteryHideReason.flat && reason != BatteryHideReason.longCharge)) return;
    if (_remembered?.$1 == level) return;
    final now = _clock();
    _remembered = (level, now);
    final readings = _store.load()
      ..removeWhere((_, value) => now.difference(value.$2) > stuckMemory)
      ..[id] = (level, now);
    _store.save(readings);
  }

  void _forgetStuck(String id) {
    if (_remembered == null) return;
    _remembered = null;
    final readings = _store.load();
    if (readings.remove(id) != null) _store.save(readings);
  }

  /// How long until a near-empty reading that is shown now would turn flat, or null.
  Duration? untilFlat(int level, {required bool charging}) {
    if (!enabled || charging || level <= 0 || level > nearEmpty || _confirmedDrain) return null;
    if (hideReason(level, charging: charging) != null) return null;
    final since = _flatSince;
    if (_flatLevel != level || since == null) return null;
    final remaining = flatHold - _clock().difference(since);
    return remaining.isNegative ? Duration.zero : remaining;
  }

  @visibleForTesting
  bool get confirmedDrainForTesting => _confirmedDrain;
}
