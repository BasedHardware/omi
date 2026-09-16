import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/geolocation.dart';

const chunkSizeInSeconds = 60;
const flushIntervalInSeconds = 90;
const sdcardChunkSizeSecs = 180;
const newFrameSyncDelaySeconds = 15;
const framesPerFlashPage = 8;
const secondsPerFlashPage = 1.4;

/// Aligns with backend `SYNC_CAPTURE_MAX_FUTURE_SKEW_SECONDS` (default 300).
const int walMaxFutureSkewSeconds = 300;

/// Shared positive clock skew for a set of WAL capture windows (#4771).
///
/// Mirrors backend [batch_clock_shift]: one shift for the batch so successive
/// offline shards keep their relative spacing instead of collapsing onto the
/// same [timerStart].
int batchWalClockShiftSeconds(
  Iterable<({int start, int durationSeconds})> windows, {
  int? nowSeconds,
}) {
  final now = nowSeconds ?? DateTime.now().millisecondsSinceEpoch ~/ 1000;
  int? newestEnd;
  for (final window in windows) {
    final duration = window.durationSeconds < 0 ? 0 : window.durationSeconds;
    final end = window.start + duration;
    if (newestEnd == null || end > newestEnd) {
      newestEnd = end;
    }
  }
  if (newestEnd == null) {
    return 0;
  }
  return newestEnd > now ? newestEnd - now : 0;
}

/// Shift a capture window so it never ends after [nowSeconds] (#4770/#4771).
({int start, int end}) normalizeWalCaptureWindow(
  int startTs,
  int endTs, {
  int? nowSeconds,
  int? clockShiftSeconds,
}) {
  final now = nowSeconds ?? DateTime.now().millisecondsSinceEpoch ~/ 1000;
  var start = startTs;
  var end = endTs;
  if (clockShiftSeconds == null) {
    if (end <= now) {
      return (start: start, end: end);
    }
    final shift = end - now;
    start -= shift;
    end -= shift;
  } else {
    final shift = clockShiftSeconds < 0 ? 0 : clockShiftSeconds;
    if (shift == 0 && end <= now) {
      return (start: start, end: end);
    }
    start -= shift;
    end -= shift;
  }
  if (end > now) {
    final extra = end - now;
    start -= extra;
    end -= extra;
  }
  return (start: start, end: end);
}

/// Clamp a device/phone-proposed WAL capture start so the recording window
/// never ends after [nowSeconds] (#4770).
int normalizeWalTimerStart(
  int proposed, {
  required int durationSeconds,
  int? nowSeconds,
  int maxFutureSkewSeconds = walMaxFutureSkewSeconds,
}) {
  final now = nowSeconds ?? DateTime.now().millisecondsSinceEpoch ~/ 1000;
  final duration = durationSeconds < 0 ? 0 : durationSeconds;
  if (proposed > now + maxFutureSkewSeconds) {
    return now - duration;
  }
  final end = proposed + duration;
  if (end <= now) {
    return proposed;
  }
  return normalizeWalCaptureWindow(proposed, end, nowSeconds: now).start;
}

/// Applies one shared batch clock shift to every WAL whose window ends after
/// [nowSeconds], preserving inter-shard spacing (#4771).
void normalizeWalTimerStartsInBatch(
  List<Wal> wals, {
  int? nowSeconds,
  int maxFutureSkewSeconds = walMaxFutureSkewSeconds,
}) {
  if (wals.isEmpty) {
    return;
  }
  final now = nowSeconds ?? DateTime.now().millisecondsSinceEpoch ~/ 1000;
  final needsShift = <Wal>[];
  for (final wal in wals) {
    final duration = wal.seconds < 0 ? 0 : wal.seconds;
    if (wal.timerStart > now + maxFutureSkewSeconds) {
      wal.timerStart = now - duration;
      continue;
    }
    if (wal.timerStart + duration > now) {
      needsShift.add(wal);
    }
  }
  if (needsShift.isEmpty) {
    _ensureUniqueWalTimerStarts(wals);
    return;
  }
  final shift = batchWalClockShiftSeconds(
    needsShift.map((w) => (start: w.timerStart, durationSeconds: w.seconds)),
    nowSeconds: now,
  );
  for (final wal in needsShift) {
    final duration = wal.seconds < 0 ? 0 : wal.seconds;
    final end = wal.timerStart + duration;
    final normalized = normalizeWalCaptureWindow(
      wal.timerStart,
      end,
      nowSeconds: now,
      clockShiftSeconds: shift,
    );
    wal.timerStart = normalized.start;
  }
  _ensureUniqueWalTimerStarts(wals);
}

void _ensureUniqueWalTimerStarts(List<Wal> wals) {
  final seenStartsByDevice = <String, Set<int>>{};
  final ordered = List<Wal>.from(wals)..sort((a, b) => a.timerStart.compareTo(b.timerStart));
  for (final wal in ordered) {
    final used = seenStartsByDevice.putIfAbsent(wal.device, () => <int>{});
    var start = wal.timerStart;
    while (used.contains(start)) {
      start += 1;
    }
    wal.timerStart = start;
    used.add(start);
  }
}

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
/// - [outsideRecoveryWindow] — the server permanently refused this recording
///                  because it is older than the automatic-recovery window
///                  (HTTP 422 `backfill_lookback_exceeded`). The local file is
///                  intact, but re-uploading it can never succeed, so it is
///                  terminal for sync rather than pending work.
enum WalStatus { inProgress, miss, uploaded, synced, corrupted, outsideRecoveryWindow }

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
/// - [outsideRecoveryWindow] — too old for the server to accept; retrying
///                  cannot help, so the row explains that instead of offering
///                  a Retry the user would spend forever
enum WalSyncDisplayState { syncing, uploaded, synced, waiting, retrying, failed, corrupted, outsideRecoveryWindow }

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
  List<List<int>> data;
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

  /// Canonical start-time location snapshot for delayed/offline finalization.
  Geolocation? geolocation;

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
    // Corruption and a server lookback rejection are terminal. Neither must be
    // visually downgraded to an active upload if a transient flag was left
    // behind by an interrupted attempt.
    if (status == WalStatus.corrupted) return WalSyncDisplayState.corrupted;
    if (status == WalStatus.outsideRecoveryWindow) return WalSyncDisplayState.outsideRecoveryWindow;
    if (isSyncing) return WalSyncDisplayState.syncing;
    switch (status) {
      case WalStatus.uploaded:
        return WalSyncDisplayState.uploaded;
      case WalStatus.synced:
        return WalSyncDisplayState.synced;
      case WalStatus.corrupted:
        return WalSyncDisplayState.corrupted;
      case WalStatus.outsideRecoveryWindow:
        return WalSyncDisplayState.outsideRecoveryWindow;
      case WalStatus.miss:
        if (retryCount >= walMaxAutoRetries) return WalSyncDisplayState.failed;
        if (retryCount > 0) return WalSyncDisplayState.retrying;
        return WalSyncDisplayState.waiting;
      case WalStatus.inProgress:
        return WalSyncDisplayState.waiting;
    }
  }

  /// Marks this recording as terminally unavailable and clears any transient
  /// upload presentation left by an interrupted attempt.
  void markCorrupted() {
    status = WalStatus.corrupted;
    isSyncing = false;
    syncStartedAt = null;
    syncEtaSeconds = null;
    syncSpeedKBps = null;
  }

  /// Marks this recording as permanently refused by the server for being older
  /// than the automatic-recovery window. The local file is deliberately kept —
  /// only the sync attempt is terminal.
  void markOutsideRecoveryWindow() {
    status = WalStatus.outsideRecoveryWindow;
    isSyncing = false;
    syncStartedAt = null;
    syncEtaSeconds = null;
    syncSpeedKBps = null;
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
    List<List<int>>? data,
    this.totalFrames = 0,
    this.syncedFrameOffset = 0,
    this.originalStorage,
    this.conversationId,
    this.geolocation,
    this.retryCount = 0,
    this.lastRetryAt = 0,
    this.jobId,
    this.uploadedAt = 0,
  }) : data = data ?? [] {
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
      geolocation: json['geolocation'] is Map<String, dynamic>
          ? Geolocation.fromJson(json['geolocation'] as Map<String, dynamic>)
          : null,
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
      'geolocation': geolocation?.toJson(),
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
