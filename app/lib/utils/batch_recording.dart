import 'package:omi/backend/schema/bt_device/bt_device.dart';

/// Marker stored in [Wal.device] for recordings produced by offline/batch mode.
/// Lets the conversations list show *only* batch recordings — never the device
/// SD-card/flash sync WALs or realtime offline buffers (which live on the Sync page).
const String batchRecordingDevice = 'omibatch';

/// Marker for recordings drained from the Limitless pendant's flash. Starts with
/// [batchRecordingDevice] so the recordings scanner matches it; contains
/// `limitless` so the backend tags the conversation `source=limitless`.
const String limitlessBatchRecordingDevice = 'omibatchlimitless';

/// Metadata parsed from a batch recording filename written by the native layer:
///
///   audio_{device}_{codec}_{sampleRate}_{channel}_fs{frameSize}_{timestamp}.bin
///
/// Mirrors how the backend `/v2/sync-local-files` pipeline interprets the name:
/// codec is detected from the `_pcm16_`/`_pcm8_` markers (otherwise opus), the
/// frame size from `_fs<n>`, and the timestamp from the trailing segment
/// (milliseconds are normalized to seconds). Kept pure so it can be unit tested.
class BatchRecordingInfo {
  /// Recording start time, unix seconds.
  final int timerStart;
  final BleAudioCodec codec;
  final int frameSize;
  final int sampleRate;

  const BatchRecordingInfo({
    required this.timerStart,
    required this.codec,
    required this.frameSize,
    this.sampleRate = 16000,
  });

  /// Returns null if [name] is not a parseable, finalized batch `.bin` filename
  /// (e.g. a `.bin.part` in-progress file, or an unrelated file).
  static BatchRecordingInfo? fromFileName(String name) {
    if (!name.startsWith('audio_') || !name.endsWith('.bin')) return null;

    final base = name.substring(0, name.length - 4); // strip ".bin"
    final ts = int.tryParse(base.split('_').last);
    if (ts == null) return null;
    final timerStart = ts > 100000000000 ? ts ~/ 1000 : ts; // ms -> s

    final fsMatch = RegExp(r'_fs(\d+)').firstMatch(name);
    final frameSize = fsMatch != null ? int.parse(fsMatch.group(1)!) : 160;

    final srMatch = RegExp(r'_(\d+)_\d+_fs\d+_\d+\.bin$').firstMatch(name);
    final sampleRate = srMatch != null ? int.parse(srMatch.group(1)!) : 16000;

    final BleAudioCodec codec;
    if (name.contains('_pcm16_')) {
      codec = BleAudioCodec.pcm16;
    } else if (name.contains('_pcm8_')) {
      codec = BleAudioCodec.pcm8;
    } else {
      codec = frameSize == 320 ? BleAudioCodec.opusFS320 : BleAudioCodec.opus;
    }

    return BatchRecordingInfo(timerStart: timerStart, codec: codec, frameSize: frameSize, sampleRate: sampleRate);
  }

  /// Exact duration in seconds from the decoded frame count. Each length-prefixed
  /// frame decodes to [frameSize] samples (the backend uses the same), so the audio
  /// duration is `frames * frameSize / sampleRate` — independent of opus VBR bitrate.
  /// Preferred over [estimateSeconds], which only sees the byte size.
  int secondsFromFrameCount(int frames) {
    if (sampleRate <= 0 || frameSize <= 0) return 1;
    return (frames * frameSize / sampleRate).round().clamp(1, 24 * 3600);
  }

  /// Rough duration in seconds from file size — for display/stats only. The
  /// backend recomputes the exact duration from the decoded audio. Accounts for
  /// ~16 kbps opus plus the 4-byte per-frame length prefix, or raw PCM rates.
  int estimateSeconds(int sizeBytes) {
    final bytesPerSec = codec == BleAudioCodec.pcm16
        ? 32200
        : codec == BleAudioCodec.pcm8
        ? 16100
        : 2400;
    return (sizeBytes / bytesPerSec).round().clamp(1, 24 * 3600);
  }
}
