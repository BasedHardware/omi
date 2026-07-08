import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/batch_recording.dart';

/// Lifecycle of a local recording captured in batch/offline mode.
enum LocalRecordingState {
  /// On disk, not yet uploaded. The user can transcribe it.
  pending,

  /// Upload in flight (multipart POST to /v2/sync-local-files).
  uploading,

  /// Uploaded; the server is transcribing in the background (job reconciling).
  processing,

  /// The last upload attempt failed; the file is intact and can be retried.
  failed,
}

/// A recording captured in batch/offline mode and written natively to the phone
/// as a length-prefixed `.bin` file (see [BatchRecordingInfo]).
///
/// Unlike a WAL it is **not** backed by the offline-sync store — the file on
/// disk is the single source of truth and this object is derived on demand by
/// scanning the recordings directory (fieldy-style). Uploading one turns it
/// into a conversation. See [LocalRecordingsProvider].
class LocalRecording {
  /// The `.bin` file name. Doubles as the stable id and the relative path that
  /// `AudioPlayerUtils`/`Wal.getFilePath` resolve against the app documents dir.
  final String fileName;

  /// Absolute path on disk.
  final String filePath;

  /// Recording start time, unix seconds (parsed from the filename).
  final int timerStart;

  final BleAudioCodec codec;
  final int frameSize;
  final int sizeBytes;

  /// Estimated duration in seconds (the backend computes the exact value).
  final int seconds;

  /// Server job id once uploaded (HTTP 202); null while [LocalRecordingState.pending].
  final String? jobId;

  final LocalRecordingState state;

  const LocalRecording({
    required this.fileName,
    required this.filePath,
    required this.timerStart,
    required this.codec,
    required this.frameSize,
    required this.sizeBytes,
    required this.seconds,
    required this.state,
    this.jobId,
  });

  String get id => fileName;

  DateTime get startedAt => DateTime.fromMillisecondsSinceEpoch(timerStart * 1000);

  /// True while uploading or processing — playback/delete stay allowed, but a
  /// second upload must not start.
  bool get isBusy => state == LocalRecordingState.uploading || state == LocalRecordingState.processing;

  /// Build from a finalized batch `.bin` file on disk. Returns null if [fileName]
  /// isn't a parseable recording filename or the file is empty.
  static LocalRecording? fromFile({
    required String fileName,
    required String filePath,
    required int sizeBytes,
    int? seconds,
    String? jobId,
    required LocalRecordingState state,
  }) {
    final info = BatchRecordingInfo.fromFileName(fileName);
    if (info == null || sizeBytes <= 0) return null;
    return LocalRecording(
      fileName: fileName,
      filePath: filePath,
      timerStart: info.timerStart,
      codec: info.codec,
      frameSize: info.frameSize,
      sizeBytes: sizeBytes,
      seconds: seconds ?? info.estimateSeconds(sizeBytes),
      jobId: jobId,
      state: state,
    );
  }
}
