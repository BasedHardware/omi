
enum BleAudioCodec {
  pcm16('pcm16', 16000, 16),
  pcm8('pcm8', 8000, 16),
  mulaw16('mulaw16', 16000, 16),
  mulaw8('mulaw8', 8000, 16),
  opus('opus', 16000, 16),
  unknown('unknown', 0, 0);

  final String value;
  final int sampleRate;
  final int bitDepth;
  const BleAudioCodec(this.value, this.sampleRate, this.bitDepth);

  static BleAudioCodec fromString(String value) {
    return BleAudioCodec.values.firstWhere(
      (codec) => codec.value == value,
      orElse: () => BleAudioCodec.unknown,
    );
  }

  String toName() => value;
}
