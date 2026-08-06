/// Owns the decision to consume audio from a connected device.
///
/// Storage-authoritative firmware keeps recording on the pendant while the
/// phone cannot transcribe. Draining that ring without a ready transcription
/// service only moves thousands of immutable transfer ranges onto the phone;
/// it cannot produce a live preview and needlessly spends BLE bandwidth and
/// battery. Intentional Transcribe Later mode is the exception because local
/// capture is the requested destination.
abstract final class DeviceAudioStreamingPolicy {
  static bool shouldConsumeDeviceAudio({
    required bool usesStorageAuthoritativeAudio,
    required bool transcribeLaterEnabled,
    required bool transcriptionServiceReady,
  }) {
    if (!usesStorageAuthoritativeAudio) return true;
    return transcribeLaterEnabled || transcriptionServiceReady;
  }
}
