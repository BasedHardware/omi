/// Transient BLE disconnect grace before capture side-effects (#6678).
///
/// Native auto-reconnect schedules:
/// - Android `OmiBleForegroundService.RECONNECT_DELAY_MS` = 3000ms
/// - iOS `OmiBleManager` reconnect ≈ 200ms
///
/// Dart previously ran phone-fallback / session teardown after only 500ms, so
/// every Android RF blip during live capture stopped the device stream and
/// started `omibatchphoneauto` — producing dozens of short conversation shards
/// per day (Device Diagnostics disconnect churn).
///
/// Pure helpers so the contract is unit-testable without DeviceProvider.

/// Must exceed Android native reconnect delay (3000ms) with a small cushion.
const Duration kAndroidBleReconnectGrace = Duration(milliseconds: 3500);

/// Exceeds iOS auto-reconnect (~200ms) without feeling sticky on real drops.
const Duration kIosBleReconnectGrace = Duration(milliseconds: 1500);

/// Capture-side disconnect grace for the current platform.
Duration bleDisconnectCaptureGrace({required bool isAndroid}) =>
    isAndroid ? kAndroidBleReconnectGrace : kIosBleReconnectGrace;

/// Whether capture teardown / phone fallback should run after a disconnect.
///
/// Call with the elapsed time since the disconnect event was observed. Returns
/// false while native reconnect may still restore the link.
bool shouldApplyDisconnectCaptureSideEffects({required Duration disconnectedFor, required Duration grace}) {
  if (disconnectedFor.isNegative) return false;
  return disconnectedFor >= grace;
}
