// Shared admission policy for device-supplied recording dates. Impossible
// device values may become explicit phone-clock estimates; those estimates
// never supply ring identity, ordering proofs or device-reclaim authority.
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/sync/offline_sync_amounts.dart' show walMinPlausibleTimerStartSeconds;

/// Build-time rollback, matching the other offline-sync OFF switches. No
/// persisted identities or custody decisions depend on this policy.
const deviceCaptureClockRepairOff = bool.fromEnvironment('OMI_DEVICE_CAPTURE_CLOCK_REPAIR_OFF');
const deviceCaptureFutureToleranceSeconds = 24 * 60 * 60;

/// The phone must at least be inside the pendant UTC wire domain. This cannot
/// detect a plausible-looking but incorrectly configured phone clock.
bool phoneCaptureClockPlausible(int nowSeconds) =>
    nowSeconds >= walMinPlausibleTimerStartSeconds && nowSeconds <= 0x7fffffff;

bool deviceCaptureTimePlausible(int seconds, int nowSeconds) =>
    seconds >= walMinPlausibleTimerStartSeconds && seconds <= nowSeconds + deviceCaptureFutureToleranceSeconds;

/// A positive device time retains legacy behavior when the phone cannot act as
/// a clock reference. In particular, do not turn a bad phone date into a new
/// estimated date. Callers may only estimate through [estimatedDeviceStart].
bool useDeviceCaptureTime(int seconds, int nowSeconds, {bool enabled = !deviceCaptureClockRepairOff}) =>
    seconds > 0 &&
    (!enabled || !phoneCaptureClockPlausible(nowSeconds) || deviceCaptureTimePlausible(seconds, nowSeconds));

int estimatedDeviceStart(int nowSeconds, int durationSeconds, {bool enabled = !deviceCaptureClockRepairOff}) {
  final start = nowSeconds - durationSeconds;
  if (enabled &&
      (!phoneCaptureClockPlausible(nowSeconds) ||
          durationSeconds < 0 ||
          !deviceCaptureTimePlausible(start, nowSeconds))) {
    throw StateError('No trustworthy phone clock for device capture estimate; retain device audio');
  }
  return start;
}

/// LittleFS has a complete decoded file before persistence, so its own frame
/// duration gives the start. One file is one run: never infer cross-file order
/// from an invalid LIST timestamp.
({int start, String? run}) deviceFileCaptureClock({
  required int deviceSeconds,
  required int durationSeconds,
  required int nowSeconds,
  String? existingRun,
  bool enabled = !deviceCaptureClockRepairOff,
}) {
  if (useDeviceCaptureTime(deviceSeconds, nowSeconds, enabled: enabled)) return (start: deviceSeconds, run: null);
  return (
    start: estimatedDeviceStart(nowSeconds, durationSeconds, enabled: enabled),
    run: existingRun ?? Wal.newClockRun(),
  );
}

/// The backend reads clke only directly before the trailing timestamp. A
/// collision nonce belongs before that token, never between it and the time.
String deviceClockCollisionPrefix(String prefix, int nonce) {
  if (!deviceCaptureClockRepairOff) {
    final clock = RegExp(r'_clke[0-9a-z]{1,32}$').firstMatch(prefix);
    if (clock != null) return '${prefix.substring(0, clock.start)}_u$nonce${prefix.substring(clock.start)}';
  }
  return '${prefix}_u$nonce';
}
