import 'dart:typed_data';

/// Pure helpers for the DevKit 2 wearable speaker path.
///
/// Firmware (`omi/firmware/devkit/src/speaker.c`) expects mono PCM16LE at 8 kHz.
/// Each speak cycle fills a 10 KB stereo I2S block (mono samples are duplicated),
/// so a single cycle accepts at most [maxMonoBytesPerCycle] bytes of mono PCM.
/// The BLE write protocol also fails to complete when the byte length is an
/// exact multiple of [packetSize], so frames are padded with one silent sample
/// when needed.
class DeviceSpeakerPcm {
  DeviceSpeakerPcm._();

  static const int sampleRateHz = 8000;
  static const int packetSize = 400;

  /// Firmware `MAX_BLOCK_SIZE` (10000) / 2 — mono bytes before stereo expand.
  static const int maxMonoBytesPerCycle = 5000;

  /// Downsample signed 16-bit little-endian PCM by taking every Nth sample.
  ///
  /// [fromRateHz] must be an integer multiple of [toRateHz]. Used to turn
  /// ElevenLabs `pcm_16000` into the device's 8 kHz input (factor 2).
  static Uint8List downsamplePcm16Le({
    required Uint8List pcm,
    required int fromRateHz,
    required int toRateHz,
  }) {
    if (pcm.isEmpty) return Uint8List(0);
    if (fromRateHz <= 0 || toRateHz <= 0) {
      throw ArgumentError('sample rates must be positive');
    }
    if (fromRateHz % toRateHz != 0) {
      throw ArgumentError('fromRateHz ($fromRateHz) must be a multiple of toRateHz ($toRateHz)');
    }
    final factor = fromRateHz ~/ toRateHz;
    if (factor == 1) return Uint8List.fromList(pcm);

    final sampleCount = pcm.length ~/ 2;
    final outCount = sampleCount ~/ factor;
    final out = ByteData(outCount * 2);
    final src = ByteData.sublistView(pcm);
    for (var i = 0; i < outCount; i++) {
      out.setInt16(i * 2, src.getInt16(i * factor * 2, Endian.little), Endian.little);
    }
    return out.buffer.asUint8List();
  }

  /// Split mono 8 kHz PCM into firmware-sized frames, each safe to stream once.
  static List<Uint8List> frameForDevice(Uint8List pcm8kMono) {
    if (pcm8kMono.isEmpty) return const [];
    final frames = <Uint8List>[];
    var offset = 0;
    while (offset < pcm8kMono.length) {
      final end = (offset + maxMonoBytesPerCycle).clamp(0, pcm8kMono.length);
      frames.add(ensurePlayableLength(pcm8kMono.sublist(offset, end)));
      offset = end;
    }
    return frames;
  }

  /// Ensure [pcm] length is not a multiple of [packetSize] (firmware final-chunk bug).
  static Uint8List ensurePlayableLength(Uint8List pcm) {
    if (pcm.isEmpty) return pcm;
    if (pcm.length % packetSize != 0) return pcm;
    // Append one silent 16-bit sample so the final write is a short remainder.
    final padded = Uint8List(pcm.length + 2);
    padded.setAll(0, pcm);
    return padded;
  }

  /// Little-endian uint32 length header expected as the first BLE write.
  static Uint8List lengthHeader(int byteLength) {
    final data = ByteData(4)..setUint32(0, byteLength, Endian.little);
    return data.buffer.asUint8List();
  }
}
