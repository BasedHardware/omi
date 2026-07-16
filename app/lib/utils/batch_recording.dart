import 'package:omi/backend/schema/bt_device/bt_device.dart';

/// Marker stored in [Wal.device] for recordings produced by offline/batch mode.
/// Lets the conversations list show *only* batch recordings — never the device
/// SD-card/flash sync WALs or realtime offline buffers (which live on the Sync page).
const String batchRecordingDevice = 'omibatch';

/// Marker for recordings drained from the Limitless pendant's flash. Starts with
/// [batchRecordingDevice] so the recordings scanner matches it; contains
/// `limitless` so the backend tags the conversation `source=limitless`.
const String limitlessBatchRecordingDevice = 'omibatchlimitless';

/// Marker for phone-mic recordings captured via explicit Transcribe Later. Starts
/// with [batchRecordingDevice] so the recordings scanner matches it; the backend
/// maps the `omibatchphone` substring to `source=phone`. These stay strictly
/// manual — the user chose Transcribe Later, so they never auto-upload.
const String phoneBatchRecordingDevice = 'omibatchphone';

/// Marker for phone-mic recordings captured by the automatic offline fallback
/// (the user wanted a live conversation but had no connectivity). Starts with
/// [phoneBatchRecordingDevice] (hence also [batchRecordingDevice], so both the
/// scanner and the backend `source=phone` mapping still match), with an `auto`
/// suffix that flags it for silent auto-upload once connectivity returns.
const String phoneBatchAutoRecordingDevice = 'omibatchphoneauto';

/// True if [fileName] is an automatic offline-fallback phone-mic recording
/// (as opposed to an explicit Transcribe Later one). Only these are eligible for
/// silent auto-upload; every other recording stays manual.
bool isAutoPhoneBatchRecording(String fileName) => fileName.startsWith('audio_${phoneBatchAutoRecordingDevice}_');

/// Per-file auto-upload failure cap: after this many consecutive failures for a
/// file we stop retrying it until the app relaunches (the count lives in memory).
const int autoPhoneUploadMaxFailures = 3;

/// Whether the silent auto-upload of offline-fallback recordings may run right
/// now. Mirrors the gates in `SyncProvider._autoUploadPendingPhoneFiles`:
/// custom-STT users sync manually (with confirmation), the auto-sync opt-out is
/// respected, and a second upload never starts while one is already in flight.
bool canAutoUploadPhoneRecordings({
  required bool useCustomStt,
  required bool autoSyncOfflineRecordings,
  required bool isUploading,
}) => !useCustomStt && autoSyncOfflineRecordings && !isUploading;

/// The next offline-fallback recording to auto-upload from [fileNames], or null
/// when none is eligible. Only auto-marker files qualify (explicit Transcribe
/// Later recordings stay manual); [busyNames] (uploading or processing) are
/// skipped, and a file at/over its [failureCounts] cap is skipped until the next
/// app launch. Pure so the selection/backoff rules are unit testable without the
/// provider's heavy singletons.
String? selectNextAutoPhoneUpload(
  List<String> fileNames, {
  required Set<String> busyNames,
  required Map<String, int> failureCounts,
}) {
  for (final name in fileNames) {
    if (!isAutoPhoneBatchRecording(name)) continue;
    if (busyNames.contains(name)) continue;
    if ((failureCounts[name] ?? 0) >= autoPhoneUploadMaxFailures) continue;
    return name;
  }
  return null;
}

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
