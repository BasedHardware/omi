import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';

const chunkSizeInSeconds = 60;
const flushIntervalInSeconds = 90;
const sdcardChunkSizeSecs = 60;
const newFrameSyncDelaySeconds = 15;
const framesPerFlashPage = 8;
const secondsPerFlashPage = 1.4;

/// Sync lifecycle of a recording.
///
/// - [inProgress] — still being written (audio is live).
/// - [miss]       — finalized locally, not yet uploaded (or reverted to retry).
/// - [uploaded]   — audio safely received by the server (HTTP 202); the server
///                  job is processing. NOT yet confirmed and NOT deletable —
///                  the local file is retained until [synced]. A reconciler
///                  resolves the job_id to [synced] / [miss] / [corrupted].
/// - [synced]     — server job confirmed success; conversation created. Safe to clean up.
/// - [corrupted]  — the underlying local file is missing/unreadable.
enum WalStatus { inProgress, miss, uploaded, synced, corrupted }

enum WalStorage { mem, disk, sdcard, flashPage }

enum SyncMethod { ble }

/// User-facing sync state for a single recording, derived from [Wal.status],
/// [Wal.isSyncing] and [Wal.retryCount]. This is what the sync UI renders so a
/// recording is never shown as an indistinct row — every state is explicit.
///
/// - [syncing]    — actively uploading right now
/// - [uploaded]   — uploaded; processing on Omi's servers (will finish in the background)
/// - [synced]     — safely backed up to the cloud
/// - [waiting]    — recorded, never attempted yet (will sync automatically)
/// - [retrying]   — a sync attempt failed; will be retried automatically
/// - [failed]     — auto-retries exhausted; needs a manual retry
/// - [corrupted]  — the underlying file is missing/unreadable
enum WalSyncDisplayState { syncing, uploaded, synced, waiting, retrying, failed, corrupted }

/// Max automatic sync attempts before a recording is considered [WalSyncDisplayState.failed].
/// Mirrors the `maxRetries` used by the auto-sync loop in capture_provider.
const int walMaxAutoRetries = 3;

class WalStats {
  final int totalFiles;
  final int phoneFiles;
  final int sdcardFiles;
  final int fromSdcardFiles;
  final int limitlessFiles;
  final int fromFlashPageFiles;
  final int phoneSize;
  final int sdcardSize;
  final int syncedFiles;
  final int missedFiles;

  WalStats({
    required this.totalFiles,
    required this.phoneFiles,
    required this.sdcardFiles,
    required this.fromSdcardFiles,
    required this.limitlessFiles,
    required this.fromFlashPageFiles,
    required this.phoneSize,
    required this.sdcardSize,
    required this.syncedFiles,
    required this.missedFiles,
  });

  int get sdcardRelatedFiles => sdcardFiles + fromSdcardFiles;
  int get flashPageRelatedFiles => limitlessFiles + fromFlashPageFiles;

  String get totalSizeFormatted => _formatBytes(phoneSize + sdcardSize);
  String get phoneSizeFormatted => _formatBytes(phoneSize);
  String get sdcardSizeFormatted => _formatBytes(sdcardSize);

  String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1024 * 1024 * 1024) return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }
}

class Wal {
  int timerStart;
  BleAudioCodec codec;
  int channel;
  int sampleRate;
  int seconds;
  String device;
  String? deviceModel;

  WalStatus status;
  WalStorage storage;

  String? filePath;
  List<List<int>> data = [];
  int storageOffset = 0;
  int storageTotalBytes = 0;
  int fileNum = 1;

  bool isSyncing = false;
  DateTime? syncStartedAt;
  int? syncEtaSeconds;
  double? syncSpeedKBps;
  SyncMethod syncMethod = SyncMethod.ble;

  int frameSize = 160;

  int totalFrames = 0;
  int syncedFrameOffset = 0;

  WalStorage? originalStorage;

  /// The conversation this WAL belongs to. Stamped when ConversationProcessingStartedEvent
  /// arrives so WALs survive app kill and can be recovered on startup.
  String? conversationId;

  /// Number of sync retry attempts for this WAL.
  int retryCount;

  /// Unix timestamp (seconds) of the last sync retry attempt.
  int lastRetryAt;

  /// Server job id assigned when this recording's audio was uploaded (HTTP 202).
  /// The reconciler polls this to resolve [WalStatus.uploaded] → synced / miss /
  /// corrupted. Null until uploaded. Multiple WALs in one upload batch share it.
  String? jobId;

  /// Unix timestamp (seconds) when the audio was uploaded (202 received).
  int uploadedAt;

  String get id => '${device}_$timerStart';

  /// Single source of truth for how this recording's sync state is shown to the
  /// user. The sync page renders an explicit label + icon for every value so a
  /// not-yet-synced recording is never visually identical to a failed one.
  WalSyncDisplayState get syncDisplayState {
    if (isSyncing) return WalSyncDisplayState.syncing;
    switch (status) {
      case WalStatus.uploaded:
        return WalSyncDisplayState.uploaded;
      case WalStatus.synced:
        return WalSyncDisplayState.synced;
      case WalStatus.corrupted:
        return WalSyncDisplayState.corrupted;
      case WalStatus.miss:
        if (retryCount >= walMaxAutoRetries) return WalSyncDisplayState.failed;
        if (retryCount > 0) return WalSyncDisplayState.retrying;
        return WalSyncDisplayState.waiting;
      case WalStatus.inProgress:
        return WalSyncDisplayState.waiting;
    }
  }

  Wal({
    required this.timerStart,
    required this.codec,
    required this.seconds,
    this.sampleRate = 16000,
    this.channel = 1,
    this.status = WalStatus.inProgress,
    this.storage = WalStorage.mem,
    this.filePath,
    this.device = "phone",
    this.deviceModel,
    this.storageOffset = 0,
    this.storageTotalBytes = 0,
    this.fileNum = 1,
    this.data = const [],
    this.totalFrames = 0,
    this.syncedFrameOffset = 0,
    this.originalStorage,
    this.conversationId,
    this.retryCount = 0,
    this.lastRetryAt = 0,
    this.jobId,
    this.uploadedAt = 0,
  }) {
    frameSize = codec.getFrameSize();
  }

  factory Wal.fromJson(Map<String, dynamic> json) {
    return Wal(
      timerStart: json['timer_start'],
      codec: mapNameToCodec(json['codec']),
      channel: json['channel'] ?? 1,
      sampleRate: json['sample_rate'] ?? 16000,
      status: WalStatus.values.asNameMap()[json['status']] ?? WalStatus.inProgress,
      storage: WalStorage.values.asNameMap()[json['storage']] ?? WalStorage.mem,
      filePath: json['file_path'],
      seconds: json['seconds'] ?? chunkSizeInSeconds,
      device: json['device'] ?? "phone",
      deviceModel: json['device_model'],
      storageOffset: json['storage_offset'] ?? 0,
      storageTotalBytes: json['storage_total_bytes'] ?? 0,
      fileNum: json['file_num'] ?? 1,
      totalFrames: json['total_frames'] ?? 0,
      syncedFrameOffset: json['synced_frame_offset'] ?? 0,
      originalStorage:
          json['original_storage'] != null ? WalStorage.values.asNameMap()[json['original_storage']] : null,
      conversationId: json['conversation_id'],
      retryCount: json['retry_count'] ?? 0,
      lastRetryAt: json['last_retry_at'] ?? 0,
      jobId: json['job_id'],
      uploadedAt: json['uploaded_at'] ?? 0,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'timer_start': timerStart,
      'codec': codec.toString(),
      'channel': channel,
      'sample_rate': sampleRate,
      'status': status.name,
      'storage': storage.name,
      'file_path': filePath,
      'seconds': seconds,
      'device': device,
      'device_model': deviceModel,
      'storage_offset': storageOffset,
      'storage_total_bytes': storageTotalBytes,
      'file_num': fileNum,
      'total_frames': totalFrames,
      'synced_frame_offset': syncedFrameOffset,
      'original_storage': originalStorage?.name,
      'conversation_id': conversationId,
      'retry_count': retryCount,
      'last_retry_at': lastRetryAt,
      'job_id': jobId,
      'uploaded_at': uploadedAt,
    };
  }

  static List<Wal> fromJsonList(List<dynamic> jsonList) => jsonList.map((e) => Wal.fromJson(e)).toList();

  getFileName() {
    return "audio_${device.replaceAll(RegExp(r'[^a-zA-Z0-9]'), "").toLowerCase()}_${codec}_${sampleRate}_${channel}_fs${frameSize}_${timerStart}.bin";
  }

  getFileNameByTimeStarts(int timestarts) {
    return "audio_${device.replaceAll(RegExp(r'[^a-zA-Z0-9]'), "").toLowerCase()}_${codec}_${sampleRate}_${channel}_fs${frameSize}_${timestarts}.bin";
  }

  static Future<String?> getFilePath(String? pathOrName) async {
    if (pathOrName == null || pathOrName.isEmpty) {
      return null;
    }

    final directory = await getApplicationDocumentsDirectory();
    if (pathOrName.contains('/')) {
      final filename = pathOrName.split('/').last;
      return '${directory.path}/$filename';
    }
    return '${directory.path}/$pathOrName';
  }
}
