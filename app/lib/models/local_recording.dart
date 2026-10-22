import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/services/wals/wal.dart';

/// Lifecycle of a local recording captured in batch/offline mode.
enum LocalRecordingState {
  /// On disk, not yet uploaded. The user can transcribe it.
  pending,

  /// Upload in flight (multipart POST to custody upload).
  uploading,

  /// Uploaded; the server is transcribing in the background (job reconciling).
  processing,

  /// The last upload attempt failed; the file is intact and can be retried.
  failed,
}

/// A Home view of a user-held custody WAL.
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

  /// Canonical start-location snapshot copied beside the native batch file.
  final Geolocation? geolocation;

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
    this.geolocation,
    this.jobId,
  });

  factory LocalRecording.fromWal(Wal wal, {required String filePath, required int sizeBytes}) => LocalRecording(
        fileName: wal.filePath!,
        filePath: filePath,
        timerStart: wal.timerStart,
        codec: wal.codec,
        frameSize: wal.frameSize,
        sizeBytes: sizeBytes,
        seconds: wal.seconds,
        geolocation: wal.geolocation,
        jobId: wal.jobId,
        state: wal.isSyncing
            ? LocalRecordingState.uploading
            : wal.status == WalStatus.uploaded
                ? LocalRecordingState.processing
                : wal.retryCount > 0 || wal.status != WalStatus.miss
                    ? LocalRecordingState.failed
                    : LocalRecordingState.pending,
      );

  String get id => fileName;

  DateTime get startedAt => DateTime.fromMillisecondsSinceEpoch(timerStart * 1000);

  /// True while uploading or processing — playback/delete stay allowed, but a
  /// second upload must not start.
  bool get isBusy => state == LocalRecordingState.uploading || state == LocalRecordingState.processing;
}
