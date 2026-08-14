// BLE reconnect + battery-history policy.
//
// Dart is the testable SoT. iOS `OmiBleManager` / `OmiBleReconnectPolicy`
// must keep the same numbers and branches.

/// Immediate parked `central.connect` after the first unexpected drop, then
/// exponential backoff for background `connection_timeout` / `fail_to_connect`.
const bleReconnectTimeoutBackoffMs = <int>[200, 2000, 10000, 30000, 60000];
const bleReconnectBackoffCapMs = 60000;

/// iOS `.inactive` (lock / transition) is not foreground: timeout backoff
/// must apply. Keep in sync with `OmiBleManager.scheduleReconnect`.
bool isBleReconnectBackgrounded({required bool isActive}) => !isActive;

/// Whether a delayed `central.connect` should fire after a CoreBluetooth wake.
/// Keep in sync with `OmiBleManager.flushDueReconnects`.
bool isBleReconnectDelayElapsed({
  required DateTime scheduledAt,
  required int delayMs,
  required DateTime now,
}) {
  return !now.isBefore(scheduledAt.add(Duration(milliseconds: delayMs)));
}

/// Delay before the next `central.connect`.
///
/// [attempt] is 0 for the first reconnect after an unexpected disconnect
/// (chipset-cheap parked connect, no delay). Later attempts back off only
/// while the app is backgrounded and the failure is a timeout or failed
/// connect. Foreground reconnects stay immediate so the user is not waiting
/// on a 60s cap.
int bleReconnectDelayMs({
  required int attempt,
  required bool isBackground,
  required bool isTimeoutOrFailToConnect,
}) {
  if (attempt <= 0 || !isBackground || !isTimeoutOrFailToConnect) {
    return 0;
  }
  final idx = (attempt - 1).clamp(0, bleReconnectTimeoutBackoffMs.length - 1);
  final delay = bleReconnectTimeoutBackoffMs[idx];
  return delay > bleReconnectBackoffCapMs ? bleReconnectBackoffCapMs : delay;
}

const bleBatteryPersistMinDeltaPercent = 5;
const bleBatteryPersistMinInterval = Duration(minutes: 15);
const bleBatteryLowThresholdPercent = 20;

/// Matches Dart UI throttle in `device_provider.dart` `initiateBleBatteryListener`.
bool shouldPersistBleBatteryReading({
  required int? previousLevel,
  required DateTime? lastPersistedAt,
  required int newLevel,
  required DateTime now,
}) {
  if (previousLevel == null || lastPersistedAt == null) {
    return true;
  }
  final delta = (previousLevel - newLevel).abs();
  final elapsed = now.difference(lastPersistedAt);
  final crossedLow = (newLevel < bleBatteryLowThresholdPercent && previousLevel >= bleBatteryLowThresholdPercent) ||
      (newLevel >= bleBatteryLowThresholdPercent && previousLevel < bleBatteryLowThresholdPercent);
  return delta >= bleBatteryPersistMinDeltaPercent || elapsed >= bleBatteryPersistMinInterval || crossedLow;
}
