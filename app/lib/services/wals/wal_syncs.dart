import 'dart:async';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/services/connectivity_service.dart';
import 'package:omi/services/wals/flash_page_wal_sync.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sdcard_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/logger.dart';

class WalSyncs implements IWalSync {
  late LocalWalSyncImpl _phoneSync;
  LocalWalSyncImpl get phone => _phoneSync;

  late SDCardWalSyncImpl _sdcardSync;
  SDCardWalSyncImpl get sdcard => _sdcardSync;

  late FlashPageWalSyncImpl _flashPageSync;
  FlashPageWalSyncImpl get flashPage => _flashPageSync;

  final IWalSyncListener listener;

  bool _isCancelled = false;

  WalSyncs(this.listener) {
    _phoneSync = LocalWalSyncImpl(listener);
    _sdcardSync = SDCardWalSyncImpl(listener);
    _flashPageSync = FlashPageWalSyncImpl(listener);

    _sdcardSync.setLocalSync(_phoneSync);
    _flashPageSync.setLocalSync(_phoneSync);

    _sdcardSync.loadWifiCredentials();
  }

  @override
  Future deleteWal(Wal wal) async {
    await _phoneSync.deleteWal(wal);
    await _sdcardSync.deleteWal(wal);
    await _flashPageSync.deleteWal(wal);
  }

  @override
  Future<List<Wal>> getMissingWals() async {
    List<Wal> wals = [];
    wals.addAll(await _sdcardSync.getMissingWals());
    wals.addAll(await _phoneSync.getMissingWals());
    wals.addAll(await _flashPageSync.getMissingWals());
    return wals;
  }

  Future<List<Wal>> getAllWals() async {
    List<Wal> wals = [];
    wals.addAll(await _sdcardSync.getMissingWals());
    wals.addAll(await _phoneSync.getAllWals());
    wals.addAll(await _flashPageSync.getMissingWals());
    return wals;
  }

  Future<WalStats> getWalStats() async {
    final allWals = await getAllWals();
    int phoneFiles = 0;
    int sdcardFiles = 0;
    int fromSdcardFiles = 0;
    int limitlessFiles = 0;
    int fromFlashPageFiles = 0;
    int phoneSize = 0;
    int sdcardSize = 0;
    int syncedFiles = 0;
    int missedFiles = 0;

    for (final wal in allWals) {
      if (wal.storage == WalStorage.sdcard) {
        sdcardFiles++;
        sdcardSize += _estimateWalSize(wal);
      } else if (wal.storage == WalStorage.flashPage) {
        limitlessFiles++;
      } else {
        if (wal.originalStorage == WalStorage.sdcard) {
          fromSdcardFiles++;
        } else if (wal.originalStorage == WalStorage.flashPage) {
          fromFlashPageFiles++;
        } else {
          phoneFiles++;
        }
        phoneSize += _estimateWalSize(wal);
      }

      if (wal.status == WalStatus.synced) {
        syncedFiles++;
      } else if (wal.status == WalStatus.miss) {
        missedFiles++;
      }
    }

    return WalStats(
      totalFiles: allWals.length,
      phoneFiles: phoneFiles,
      sdcardFiles: sdcardFiles,
      fromSdcardFiles: fromSdcardFiles,
      limitlessFiles: limitlessFiles,
      fromFlashPageFiles: fromFlashPageFiles,
      phoneSize: phoneSize,
      sdcardSize: sdcardSize,
      syncedFiles: syncedFiles,
      missedFiles: missedFiles,
    );
  }

  int _estimateWalSize(Wal wal) {
    int bytesPerSecond;
    switch (wal.codec) {
      case BleAudioCodec.opusFS320:
        bytesPerSecond = 16000;
      case BleAudioCodec.opus:
        bytesPerSecond = 8000;
        break;
      case BleAudioCodec.pcm16:
        bytesPerSecond = wal.sampleRate * 2 * wal.channel;
        break;
      case BleAudioCodec.pcm8:
        bytesPerSecond = wal.sampleRate * 1 * wal.channel;
        break;
      default:
        bytesPerSecond = 8000;
    }
    return bytesPerSecond * wal.seconds;
  }

  Future<void> deleteAllSyncedWals() async {
    await _phoneSync.deleteAllSyncedWals();
    await _sdcardSync.deleteAllSyncedWals();
    await _flashPageSync.deleteAllSyncedWals();
  }

  @override
  void start() {
    _phoneSync.start();
    _sdcardSync.start();
    _flashPageSync.start();
  }

  @override
  Future stop() async {
    await _phoneSync.stop();
    await _sdcardSync.stop();
    await _flashPageSync.stop();
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({
    IWalSyncProgressListener? progress,
    IWifiConnectionListener? connectionListener,
  }) async {
    _isCancelled = false;
    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    // Phase 1a: Download SD card data to phone
    Logger.debug("WalSyncs: Phase 1a - Downloading SD card data to phone");
    progress?.onWalSyncedProgress(0.0, phase: SyncPhase.downloadingFromDevice);
    final missingSDCardWals = (await _sdcardSync.getMissingWals()).where((w) => w.status == WalStatus.miss).toList();

    bool usedWifi = false;
    if (missingSDCardWals.isNotEmpty) {
      final preferredMethod = SharedPreferencesUtil().preferredSyncMethod;
      final wifiSupported = await _sdcardSync.isWifiSyncSupported();

      if (preferredMethod == 'wifi' && wifiSupported) {
        usedWifi = true;
        await _sdcardSync.syncWithWifi(progress: progress, connectionListener: connectionListener);
      } else {
        await _sdcardSync.syncAll(progress: progress);
      }
    }

    if (_isCancelled) {
      Logger.debug("WalSyncs: Cancelled after SD card phase");
      return resp;
    }

    // Phase 1b: Download flash page data to phone
    Logger.debug("WalSyncs: Phase 1b - Downloading flash page data to phone");
    await _flashPageSync.syncAll(progress: progress);

    if (_isCancelled) {
      Logger.debug("WalSyncs: Cancelled after flash page phase");
      return resp;
    }

    if (usedWifi) {
      Logger.debug("WalSyncs: Waiting for internet after WiFi transfer...");
      progress?.onWalSyncedProgress(0.0, phase: SyncPhase.waitingForInternet);
      await _waitForInternet();
    }

    if (_isCancelled) {
      Logger.debug("WalSyncs: Cancelled after waiting for internet");
      return resp;
    }

    // Phase 2: Upload all phone files to cloud (includes SD card and flash page downloads)
    Logger.debug("WalSyncs: Phase 2 - Uploading phone files to cloud");
    progress?.onWalSyncedProgress(0.0, phase: SyncPhase.uploadingToCloud);
    var partialRes = await _phoneSync.syncAll(progress: progress);
    if (partialRes != null) {
      resp.newConversationIds
          .addAll(partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)));
      resp.updatedConversationIds.addAll(partialRes.updatedConversationIds
          .where((id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id)));
    }

    return resp;
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({
    required Wal wal,
    IWalSyncProgressListener? progress,
    IWifiConnectionListener? connectionListener,
  }) async {
    if (wal.storage == WalStorage.sdcard) {
      progress?.onWalSyncedProgress(0.0, phase: SyncPhase.downloadingFromDevice);
      final preferredMethod = SharedPreferencesUtil().preferredSyncMethod;
      final wifiSupported = await _sdcardSync.isWifiSyncSupported();

      if (preferredMethod == 'wifi' && wifiSupported) {
        return await _sdcardSync.syncWithWifi(progress: progress, connectionListener: connectionListener);
      } else {
        return _sdcardSync.syncWal(wal: wal, progress: progress);
      }
    } else if (wal.storage == WalStorage.flashPage) {
      progress?.onWalSyncedProgress(0.0, phase: SyncPhase.downloadingFromDevice);
      return _flashPageSync.syncWal(wal: wal, progress: progress);
    } else {
      progress?.onWalSyncedProgress(0.0, phase: SyncPhase.uploadingToCloud);
      return _phoneSync.syncWal(wal: wal, progress: progress);
    }
  }

  @override
  void cancelSync() {
    _isCancelled = true;
    _sdcardSync.cancelSync();
    _flashPageSync.cancelSync();
    _phoneSync.cancelSync();
  }

  bool get isSdCardSyncing => _sdcardSync.isSyncing;

  double get sdCardSpeedKBps => _sdcardSync.currentSpeedKBps;

  bool get isFlashPageSyncing => _flashPageSync.isSyncing;

  /// Get conversation IDs accumulated so far from completed upload batches.
  /// Returns null if no sync is in progress or no batches have completed.
  SyncLocalFilesResponse? get accumulatedResponse => _phoneSync.accumulatedResponse;

  /// Wait for internet connectivity to be restored (e.g. after WiFi transfer).
  /// Polls every 2 seconds, gives up after 30 seconds.
  Future<void> _waitForInternet() async {
    final connectivity = ConnectivityService();
    for (int i = 0; i < 15; i++) {
      if (connectivity.isConnected) {
        Logger.debug("WalSyncs: Internet available after ${i * 2}s");
        return;
      }
      await Future.delayed(const Duration(seconds: 2));
    }
    Logger.debug("WalSyncs: Internet not available after 30s, proceeding anyway");
  }
}
