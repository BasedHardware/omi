import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/wals/wal.dart';

// Re-export for convenience
export 'package:omi/backend/http/api/conversations.dart' show syncLocalFilesV2, SyncJobPollCallback;

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

/// Listener for WiFi connection progress
abstract class IWifiConnectionListener {
  void onEnablingDeviceWifi();
  void onConnectingToDevice();
  void onConnected();
  void onConnectionFailed(String error);
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
  Future<SyncLocalFilesResponse?> syncAll({
    IWalSyncProgressListener? progress,
    IWifiConnectionListener? connectionListener,
  });
  Future<SyncLocalFilesResponse?> syncWal({
    required Wal wal,
    IWalSyncProgressListener? progress,
    IWifiConnectionListener? connectionListener,
  });
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
}

abstract class SDCardWalSync implements IWalSync {
  void setLocalSync(LocalWalSync localSync);
  void setDevice(BtDevice? device);
  Future<void> deleteAllSyncedWals();
  Future<void> deleteAllPendingWals();
  bool get isSyncing;
  double get currentSpeedKBps;

  Future<bool> isWifiSyncSupported();
  Future<bool> setWifiCredentials(String ssid, String password);
  Future<void> clearWifiCredentials();
  Future<void> loadWifiCredentials();
  Map<String, String?>? getWifiCredentials();
  Future<SyncLocalFilesResponse?> syncWithWifi({
    IWalSyncProgressListener? progress,
    IWifiConnectionListener? connectionListener,
  });
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

abstract class FlashPageWalSync implements IWalSync {
  void setDevice(BtDevice? device);
  void setLocalSync(LocalWalSync localSync);
  Future<void> deleteAllSyncedWals();
  Future<void> deleteAllPendingWals();
  bool get isSyncing;
}
