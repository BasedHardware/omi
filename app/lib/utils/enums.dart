enum DeviceType {
  friend,
  openglass,
  necklace,
  frame,
  watch,
  phone,
}

enum DeviceConnectionState {
  connected,
  disconnected,
  connecting,
  disconnecting
}

enum RecordingState {
  pause,
  record,
  stop,
  initializing,
  error
}

enum RecordingSource {
  necklace,
  watch,
  phone,
}

enum BleAudioCodec {
  pcm16,
  pcm8,
  mulaw16,
  mulaw8,
  opus,
  unknown;

  @override
  String toString() {
    switch (this) {
      case BleAudioCodec.opus:
        return 'opus';
      case BleAudioCodec.pcm16:
        return 'pcm16';
      case BleAudioCodec.pcm8:
        return 'pcm8';
      default:
        return 'unknown';
    }
  }
}
