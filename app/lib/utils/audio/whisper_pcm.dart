import 'dart:typed_data';
import 'package:omi/services/sockets/local_stt_failure.dart';
import 'package:omi/utils/audio/wav_bytes.dart';

/// Canonical PCM input from app transcoders: validates before entering native
/// code, downmixes and resamples to Whisper's mandatory 16 kHz / 16-bit mono.
class WhisperPcm {
  final Uint8List wav;
  final double duration;
  WhisperPcm(this.wav, this.duration);

  static WhisperPcm normalize(Uint8List bytes) {
    if (bytes.length < 44) throw const LocalSttFailure('invalid_audio');
    final data = ByteData.sublistView(bytes);
    bool tag(int offset, String value) => String.fromCharCodes(bytes.sublist(offset, offset + 4)) == value;
    final channels = data.getUint16(22, Endian.little);
    final rate = data.getUint32(24, Endian.little);
    final size = data.getUint32(40, Endian.little);
    if (!tag(0, 'RIFF') ||
        !tag(8, 'WAVE') ||
        !tag(12, 'fmt ') ||
        !tag(36, 'data') ||
        data.getUint32(16, Endian.little) != 16 ||
        data.getUint16(20, Endian.little) != 1 ||
        channels < 1 ||
        channels > 2 ||
        rate < 8000 ||
        rate > 48000 ||
        data.getUint16(34, Endian.little) != 16 ||
        size > bytes.length - 44 ||
        size % (channels * 2) != 0) {
      throw const LocalSttFailure('invalid_audio');
    }
    final frames = size ~/ (channels * 2);
    final duration = frames / rate;
    final count = (frames * 16000 / rate).round();
    final pcm = ByteData(count * 2);
    double sample(int frame) {
      if (frames == 0) return 0;
      frame = frame.clamp(0, frames - 1);
      var sum = 0;
      for (var ch = 0; ch < channels; ch++) {
        sum += data.getInt16(44 + (frame * channels + ch) * 2, Endian.little);
      }
      return sum / channels;
    }

    for (var i = 0; i < count; i++) {
      final position = i * rate / 16000;
      final base = position.floor();
      final fraction = position - base;
      final value = sample(base) * (1 - fraction) + sample(base + 1) * fraction;
      pcm.setInt16(i * 2, value.round().clamp(-32768, 32767), Endian.little);
    }
    return WhisperPcm(
        WavBytes.fromPcm(pcm.buffer.asUint8List(), sampleRate: 16000, numChannels: 1).asBytes(), duration);
  }
}
