import 'package:flutter/foundation.dart';

/// The service repeats every 5 minutes for the WAL sync wake. Location only
/// keeps the backend's 30-minute geolocation cache warm, so a fix and its
/// upload run at most this often.
const Duration backgroundLocationRefreshInterval = Duration(minutes: 15);

@visibleForTesting
bool backgroundLocationRefreshDue(DateTime? lastAttempt, DateTime now) =>
    lastAttempt == null ||
    now.isBefore(lastAttempt) ||
    !now.isBefore(lastAttempt.add(backgroundLocationRefreshInterval));

/// The sync wake always runs. Location runs only when due, and the attempt
/// stamp is recorded before the refresh so a failed fix is not retried on
/// the next 5-minute repeat.
@visibleForTesting
Future<void> runBackgroundRepeat({
  required DateTime? lastAttempt,
  required DateTime now,
  required void Function() sendSyncWake,
  required void Function(DateTime attemptAt) recordAttempt,
  required Future<void> Function() refreshLocation,
}) async {
  sendSyncWake();
  if (!backgroundLocationRefreshDue(lastAttempt, now)) return;
  recordAttempt(now);
  await refreshLocation();
}

/// Owns the attempt stamp. The field is library-private, so the foreground
/// handler cannot assign null and force a refresh on every repeat.
@visibleForTesting
class BackgroundLocationCadence {
  DateTime? _attemptAt;

  DateTime? get attemptAt => _attemptAt;

  /// Stamps [DateTime.now]. No caller-supplied time, so the handler cannot
  /// backdate the stamp and force every repeat to look due.
  Future<void> onStart({required Future<void> Function() refreshLocation}) async {
    _attemptAt = DateTime.now();
    await refreshLocation();
  }

  Future<void> onRepeat({
    required DateTime now,
    required void Function() sendSyncWake,
    required Future<void> Function() refreshLocation,
  }) {
    return runBackgroundRepeat(
      lastAttempt: _attemptAt,
      now: now,
      sendSyncWake: sendSyncWake,
      recordAttempt: (stamp) => _attemptAt = stamp,
      refreshLocation: refreshLocation,
    );
  }
}
