import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/wals/wal.dart';

// Re-export for convenience
export 'package:omi/backend/http/api/conversations.dart'
    show
        uploadLocalFilesV2,
        UploadFilesResult,
        fetchSyncJobStatus,
        SyncJobFetch,
        SyncJobFetchOutcome,
        SyncRateLimitedException,
        SyncRateLimitKind,
        SyncRecoveryWindowExceededException;

abstract class IWalSyncProgressListener {
  void onWalSyncedProgress(
    double percentage, {
    double? speedKBps,
    SyncPhase? phase,
    int? currentFile,
    int? totalFiles,
    int? uploadedBytes,
    int? totalBytesToUpload,
  });
}

abstract class IWalServiceListener extends IWalSyncListener {
  void onStatusChanged(WalServiceStatus status);
}

abstract class IWalSyncListener {
  void onWalUpdated();
  void onWalSynced(Wal wal, {ServerConversation? conversation});
}

abstract class IWalSync {
  Future<List<Wal>> getMissingWals();
  Future deleteWal(Wal wal);
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress});
  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress});
  void cancelSync();

  void start();
  Future stop();
}

abstract class IWalService {
  void start();
  Future stop();

  void subscribe(IWalServiceListener subscription, Object context);
  void unsubscribe(Object context);

  /// Returns the WalSyncs instance for managing sync operations.
  /// Returns dynamic to avoid circular imports - cast to WalSyncs at call site.
  dynamic getSyncs();
}

enum WalServiceStatus { init, ready, stop }

// Forward declarations for sync types
abstract class LocalWalSync implements IWalSync {
  Future<void> addExternalWal(Wal wal);
  Future<List<Wal>> getAllWals();
  Future<void> deleteAllSyncedWals();
  Future<void> deleteAllPendingWals();
  Future<void> deleteAllCorruptedWals();

  /// Ingest a pre-processed audio frame from an AudioSource.
  /// The frame contains headerless payload and a source-specific sync key.
  void onFrameCaptured(WalFrame frame);

  /// Mark a frame as synced (sent to server via WebSocket).
  /// Matches frames by sync key (source-agnostic).
  void markFrameSynced(FrameSyncKey key);

  /// Notify WAL that the audio codec has changed (resets frame state).
  Future onAudioCodecChanged(BleAudioCodec codec);

  /// Set device metadata for WAL file naming.
  void setDeviceInfo(String? deviceId, String? deviceModel);

  /// Set the snapshot inherited by WALs created for the active session.
  void setSessionGeolocation(Geolocation? geolocation);
}

abstract class SDCardWalSync implements IWalSync {
  void setLocalSync(LocalWalSync localSync);
  void setDevice(BtDevice? device);
  Future<void> deleteAllSyncedWals();
  Future<void> deleteAllPendingWals();
  bool get isSyncing;
  double get currentSpeedKBps;
}

abstract class StorageSync implements IWalSync {
  void setLocalSync(LocalWalSync localSync);
  void setDevice(BtDevice? device);
  Future<void> deleteAllSyncedWals();
  Future<void> deleteAllPendingWals();
  bool get isSyncing;
  double get currentSpeedKBps;
  Future<bool> hasFilesToSync();
}

/// Ring-buffer storage sync (firmware 3.0.20+).
/// Mirrors StorageSync, with the ring as a single logical stream rather than a list of files.
abstract class RingStorageSync implements IWalSync {
  void setLocalSync(LocalWalSync localSync);
  void setDevice(BtDevice? device);
  Future<void> deleteAllSyncedWals();
  Future<void> deleteAllPendingWals();
  bool get isSyncing;
  double get currentSpeedKBps;
  Future<bool> hasFilesToSync();
  Future<void> refreshWalsFromDevice();
}

/// Why the most recent flash-page drain pass stopped before reaching the
/// newest page enumerated from the device. A stall with the newest-page
/// pointer still advancing means the pendant is recording (an open recording
/// session starves the drain). A stall with zero free capture pages means the
/// pendant is full: it halts recording but stays armed in recording mode, and
/// serves no flash pages until the user presses the button to stop recording.
enum FlashSyncStallReason { none, recordingSuspected, deviceFull, unknown }

abstract class FlashPageWalSync implements IWalSync {
  void setDevice(BtDevice? device);
  void setLocalSync(LocalWalSync localSync);
  Future<void> deleteAllSyncedWals();
  Future<void> deleteAllPendingWals();
  bool get isSyncing;
  Future<void> refreshWalsFromDevice();
  FlashSyncStallReason get lastStallReason;
}
