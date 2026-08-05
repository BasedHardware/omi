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
library;

/// Must exceed Android native reconnect delay (3000ms) with a small cushion.
const Duration kAndroidBleReconnectGrace = Duration(milliseconds: 3500);

/// Exceeds iOS auto-reconnect (~200ms) without feeling sticky on real drops.
const Duration kIosBleReconnectGrace = Duration(milliseconds: 1500);

/// Capture-side disconnect grace for the current platform.
Duration bleDisconnectCaptureGrace({required bool isAndroid}) =>
    isAndroid ? kAndroidBleReconnectGrace : kIosBleReconnectGrace;

/// Whether capture teardown / phone fallback should run after the grace timer.
///
/// The [Debouncer] delay is the primary wait (past native reconnect). Reconnect
/// cancels that timer; [stillDisconnected] guards the residual race where the
/// callback was already scheduled when cancel ran.
bool shouldApplyDisconnectCaptureSideEffects({required bool stillDisconnected}) => stillDisconnected;
