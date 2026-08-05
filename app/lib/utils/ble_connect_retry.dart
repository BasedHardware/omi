/// BLE connect retry helpers for post-timeout auto-reconnect (#6721 / #6610).
///
/// Pure predicates/delays so the "connecting → timeout → disconnected → retry"
/// contract can be unit-tested without CoreBluetooth or NativeBleTransport.
library;

/// Matches [NativeBleTransport.connect] device-ready wait.
const Duration kBleDeviceReadyTimeout = Duration(seconds: 60);

/// Backoff after a failed Dart-side connect / device-ready timeout.
/// Caps at 60s so background stalls keep retrying without hammering radio.
const List<int> kBleConnectRetryBackoffSeconds = [2, 5, 10, 30, 60];

/// Native/CoreBluetooth can sit in `.connecting` without firing disconnect.
/// Kick the attempt slightly after the Dart timeout window.
const Duration kBleConnectingWatchdogAfter = Duration(seconds: 65);

Duration nextBleConnectRetryDelay(int attempt) {
  if (attempt < 0) attempt = 0;
  final idx = attempt >= kBleConnectRetryBackoffSeconds.length ? kBleConnectRetryBackoffSeconds.length - 1 : attempt;
  return Duration(seconds: kBleConnectRetryBackoffSeconds[idx]);
}

/// Whether DeviceService should schedule another soft reconnect after a failure.
bool shouldScheduleBleConnectRetry({
  required bool serviceReady,
  required bool hasPairedDevice,
  required bool userDisconnected,
  required bool alreadyConnected,
  required bool retryAlreadyScheduled,
}) {
  if (!serviceReady) return false;
  if (!hasPairedDevice) return false;
  if (userDisconnected) return false;
  if (alreadyConnected) return false;
  if (retryAlreadyScheduled) return false;
  return true;
}

/// Soft retry reuses an existing transport for the same device so native
/// auto-reconnect / BleBridge registration is not torn down.
bool shouldSoftRetryExistingConnection({
  required String? existingDeviceId,
  required String targetDeviceId,
  required bool force,
}) {
  if (!force) return false;
  if (existingDeviceId == null || existingDeviceId.isEmpty) return false;
  return existingDeviceId == targetDeviceId;
}

/// Whether an iOS connecting watchdog should cancel + re-issue connect.
bool shouldKickStuckConnectingAttempt({
  required bool isConnecting,
  required bool manuallyDisconnected,
  required Duration elapsed,
  Duration threshold = kBleConnectingWatchdogAfter,
}) {
  if (!isConnecting) return false;
  if (manuallyDisconnected) return false;
  return elapsed >= threshold;
}

/// Whether a force-connect to [targetDeviceId] should invalidate a pending
/// soft-retry timer tracked for [pendingRetryDeviceId].
///
/// Without this, a retry scheduled for a device the user has since moved away
/// from can still fire later, target the old device id with `force: true`,
/// and tear down + replace a connection the user explicitly established to a
/// *different* device in the meantime — see #6610 review discussion.
bool shouldInvalidatePendingRetryForDifferentTarget({
  required String? pendingRetryDeviceId,
  required String targetDeviceId,
  required bool force,
}) {
  if (!force) return false;
  if (pendingRetryDeviceId == null) return false;
  return pendingRetryDeviceId != targetDeviceId;
}

/// Whether bringing the app to the foreground should kick a BLE reconnect (#6721).
///
/// Native iOS already calls `reconnectStalePeripherals` on foreground; Dart still
/// needs an `initiateConnection` when the 60s device-ready timeout left the
/// transport disconnected with no pending soft-retry.
bool shouldAttemptBleReconnectOnResume({
  required bool hasPairedDevice,
  required bool isConnected,
  required bool isConnecting,
  required bool userDisconnected,
}) {
  if (!hasPairedDevice) return false;
  if (userDisconnected) return false;
  if (isConnected) return false;
  if (isConnecting) return false;
  return true;
}
