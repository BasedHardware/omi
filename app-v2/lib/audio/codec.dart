/// Audio codecs the app understands.
///
/// Phase 1 only exercises [pcm16] (phone-mic capture); the remaining values
/// are kept here so the BLE bridge added in a later phase can drop straight in
/// without renaming.
enum BleAudioCodec {
  pcm16,
  pcm8,
  opus,
  opusFS320,
  unknown,
}

int sampleRateForCodec(BleAudioCodec codec) {
  // All codecs we care about run at 16 kHz to match desktop-v2's Tauri capture
  // plugin. Keep this constant — never widen without updating the desktop side.
  return 16000;
}

int bitDepthForCodec(BleAudioCodec codec) {
  switch (codec) {
    case BleAudioCodec.pcm8:
      return 8;
    default:
      return 16;
  }
}
