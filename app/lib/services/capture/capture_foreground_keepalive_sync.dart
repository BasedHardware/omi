/// Serializes capture FGS start/stop so a stop that arrives while start is
/// still in flight still tears the task down (and retries a failed Bluetooth
/// audio-session deactivate).
class CaptureForegroundKeepAliveSync {
  bool held = false;
  bool bluetoothAudioSessionHeld = false;

  bool _inFlight = false;
  bool _dirty = false;

  Future<void> apply({
    required bool Function() desiredHold,
    required bool Function() bluetoothSessionOwner,
    required Future<void> Function() start,
    required Future<void> Function() stop,
    required Future<bool> Function() deactivateBluetoothAudioSession,
  }) async {
    if (_inFlight) {
      _dirty = true;
      return;
    }
    _inFlight = true;
    try {
      while (true) {
        _dirty = false;
        final hold = desiredHold();
        final needsDeactivate = !hold && bluetoothAudioSessionHeld;
        if (hold == held && !needsDeactivate) {
          if (!_dirty) break;
          continue;
        }
        try {
          if (hold) {
            final bluetoothOwner = bluetoothSessionOwner();
            await start();
            held = true;
            if (bluetoothOwner) {
              bluetoothAudioSessionHeld = true;
            } else {
              // Phone-mic / system-audio own AVAudioSession; do not retry a
              // previous BLE deactivate underneath them.
              bluetoothAudioSessionHeld = false;
            }
          } else {
            if (held) {
              await stop();
              held = false;
            }
            if (bluetoothAudioSessionHeld) {
              final deactivated = await deactivateBluetoothAudioSession();
              if (deactivated) {
                bluetoothAudioSessionHeld = false;
              }
            }
          }
        } catch (_) {
          // Leave flags unchanged so the next apply retries the failed step.
        }
        if (!_dirty) break;
      }
    } finally {
      _inFlight = false;
    }
    if (_dirty) {
      await apply(
        desiredHold: desiredHold,
        bluetoothSessionOwner: bluetoothSessionOwner,
        start: start,
        stop: stop,
        deactivateBluetoothAudioSession: deactivateBluetoothAudioSession,
      );
    }
  }
}
