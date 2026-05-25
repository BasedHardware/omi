import 'dart:async';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/services/wals/flash_page_wal_sync.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/ring_storage_sync.dart';
import 'package:omi/services/wals/sdcard_wal_sync.dart';
import 'package:omi/services/wals/storage_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';

class WalSyncs implements IWalSync {
  late LocalWalSyncImpl _phoneSync;
  LocalWalSyncImpl get phone => _phoneSync;

  late SDCardWalSyncImpl _sdcardSync;
  SDCardWalSyncImpl get sdcard => _sdcardSync;

  late FlashPageWalSyncImpl _flashPageSync;
  FlashPageWalSyncImpl get flashPage => _flashPageSync;

  late StorageSyncImpl _storageSync;
  StorageSyncImpl get storage => _storageSync;

  late RingStorageSyncImpl _ringSync;
  RingStorageSyncImpl get ring => _ringSync;

  final IWalSyncListener listener;

  bool _isCancelled = false;
  BtDevice? _device;

  /// Called from DeviceProvider when a device connects/disconnects so the
  /// firmware-version gate in syncAll() can route to the right Phase-0 sync.
  void setDevice(BtDevice? device) {
    _device = device;
  }

  /// Firmware >= 3.0.20 speaks the ring-buffer protocol; older multi-file
  /// firmware (3.0.17–3.0.19) keeps using StorageSync.
  static bool isRingBufferFirmware(String? version) {
    if (version == null || version.isEmpty || version == 'Unknown') return false;
    final parts = version.split('.').map((p) => int.tryParse(p) ?? 0).toList();
    if (parts.length < 3) return false;
    if (parts[0] > 3) return true;
    if (parts[0] < 3) return false;
    if (parts[1] > 0) return true;
    if (parts[1] < 0) return false;
    return parts[2] >= 20;
  }

  WalSyncs(this.listener) {
    _phoneSync = LocalWalSyncImpl(listener);
    _sdcardSync = SDCardWalSyncImpl(listener);
    _flashPageSync = FlashPageWalSyncImpl(listener);
    _storageSync = StorageSyncImpl(listener);
    _ringSync = RingStorageSyncImpl(listener);

    _sdcardSync.setLocalSync(_phoneSync);
    _flashPageSync.setLocalSync(_phoneSync);
    _storageSync.setLocalSync(_phoneSync);
    _ringSync.setLocalSync(_phoneSync);
  }

  @override
  Future deleteWal(Wal wal) async {
    await _phoneSync.deleteWal(wal);
    await _sdcardSync.deleteWal(wal);
    await _flashPageSync.deleteWal(wal);
    await _storageSync.deleteWal(wal);
    await _ringSync.deleteWal(wal);
  }

  @override
  Future<List<Wal>> getMissingWals() async {
    List<Wal> wals = [];
    wals.addAll(await _ringSync.getMissingWals());
    wals.addAll(await _storageSync.getMissingWals());
    wals.addAll(await _sdcardSync.getMissingWals());
    wals.addAll(await _phoneSync.getMissingWals());
    wals.addAll(await _flashPageSync.getMissingWals());
    return wals;
  }

  Future<List<Wal>> getAllWals() async {
    List<Wal> wals = [];
    wals.addAll(await _ringSync.getMissingWals());
    wals.addAll(await _storageSync.getMissingWals());
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
    await _storageSync.deleteAllSyncedWals();
    await _ringSync.deleteAllSyncedWals();
  }

  Future<void> deleteAllPendingWals() async {
    await _phoneSync.deleteAllPendingWals();
    await _sdcardSync.deleteAllPendingWals();
    await _flashPageSync.deleteAllPendingWals();
    await _storageSync.deleteAllPendingWals();
    await _ringSync.deleteAllPendingWals();
  }

  @override
  void start() {
    _phoneSync.start();
    _sdcardSync.start();
    _flashPageSync.start();
    _storageSync.start();
    _ringSync.start();
  }

  @override
  Future stop() async {
    await _phoneSync.stop();
    await _sdcardSync.stop();
    await _flashPageSync.stop();
    await _storageSync.stop();
    await _ringSync.stop();
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    _isCancelled = false;
    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    final allMissing = await getMissingWals();
    DebugLogManager.logEvent('sync_started', {
      'totalMissingWals': allMissing.length,
      'sdcard': allMissing.where((w) => w.storage == WalStorage.sdcard).length,
      'flashPage': allMissing.where((w) => w.storage == WalStorage.flashPage).length,
      'phone': allMissing.where((w) => w.storage == WalStorage.disk || w.storage == WalStorage.mem).length,
    });

    // Phase 0: New offline storage sync, gated by firmware version.
    //   fw >= 3.0.20  -> ring-buffer protocol (RingStorageSync)
    //   fw 3.0.17–.19 -> multi-file LittleFS protocol (StorageSync)
    //   fw < 3.0.17   -> falls through to Phase 1a legacy SD-card path
    final fwVersion = _device?.firmwareRevision;
    final useRing = isRingBufferFirmware(fwVersion);
    if (useRing) {
      await _ringSync.refreshWalsFromDevice();
      final ringMissing = await _ringSync.getMissingWals();
      if (ringMissing.isNotEmpty) {
        Logger.debug("WalSyncs: Phase 0 - Ring-buffer sync (fw=$fwVersion)");
        DebugLogManager.logInfo('Sync Phase 0: Ring-buffer sync', {'fw': fwVersion ?? ''});
        progress?.onWalSyncedProgress(0.0, phase: SyncPhase.downloadingFromDevice);
        await _ringSync.syncAll(progress: progress);
      }
    } else {
      await _storageSync.refreshWalsFromDevice();
      final storageMissing = await _storageSync.getMissingWals();
      if (storageMissing.isNotEmpty) {
        Logger.debug("WalSyncs: Phase 0 - Downloading ${storageMissing.length} multi-file storage files to phone");
        DebugLogManager.logInfo('Sync Phase 0: Multi-file storage sync', {'fw': fwVersion ?? ''});
        progress?.onWalSyncedProgress(0.0, phase: SyncPhase.downloadingFromDevice);
        await _storageSync.syncAll(progress: progress);
      }
    }

    if (_isCancelled) {
      Logger.debug("WalSyncs: Cancelled after storage sync phase");
      return resp;
    }

    // Phase 1a: Download SD card data to phone (legacy firmware)
    Logger.debug("WalSyncs: Phase 1a - Downloading SD card data to phone");
    DebugLogManager.logInfo('Sync Phase 1a: Downloading SD card data to phone');
    progress?.onWalSyncedProgress(0.0, phase: SyncPhase.downloadingFromDevice);
    final missingSDCardWals = (await _sdcardSync.getMissingWals()).where((w) => w.status == WalStatus.miss).toList();

    if (missingSDCardWals.isNotEmpty) {
      DebugLogManager.logInfo('SD card sync over BLE', {'walCount': missingSDCardWals.length});
      await _sdcardSync.syncAll(progress: progress);
    }

    if (_isCancelled) {
      Logger.debug("WalSyncs: Cancelled after SD card phase");
      DebugLogManager.logWarning('Sync cancelled after SD card phase');
      return resp;
    }

    // Phase 1b: Download flash page data to phone
    Logger.debug("WalSyncs: Phase 1b - Downloading flash page data to phone");
    DebugLogManager.logInfo('Sync Phase 1b: Downloading flash page data to phone');
    await _flashPageSync.syncAll(progress: progress);

    if (_isCancelled) {
      Logger.debug("WalSyncs: Cancelled after flash page phase");
      DebugLogManager.logWarning('Sync cancelled after flash page phase');
      return resp;
    }

    // Phase 2: Upload all phone files to cloud (includes SD card and flash page downloads)
    Logger.debug("WalSyncs: Phase 2 - Uploading phone files to cloud");
    DebugLogManager.logInfo('Sync Phase 2: Uploading phone files to cloud');
    progress?.onWalSyncedProgress(0.0, phase: SyncPhase.uploadingToCloud);
    var partialRes = await _phoneSync.syncAll(progress: progress);
    if (partialRes != null) {
      resp.newConversationIds.addAll(
        partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)),
      );
      resp.updatedConversationIds.addAll(
        partialRes.updatedConversationIds.where(
          (id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id),
        ),
      );
    }

    DebugLogManager.logEvent('sync_completed', {
      'newConversations': resp.newConversationIds.length,
      'updatedConversations': resp.updatedConversationIds.length,
    });

    return resp;
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) async {
    if (wal.storage == WalStorage.sdcard) {
      progress?.onWalSyncedProgress(0.0, phase: SyncPhase.downloadingFromDevice);
      if (wal.fileNum == -1) {
        return _ringSync.syncWal(wal: wal, progress: progress);
      }
      return _sdcardSync.syncWal(wal: wal, progress: progress);
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
    _ringSync.cancelSync();
    _storageSync.cancelSync();
    _sdcardSync.cancelSync();
    _flashPageSync.cancelSync();
    _phoneSync.cancelSync();
  }

  bool get isStorageSyncing => _storageSync.isSyncing || _ringSync.isSyncing;

  double get storageSpeedKBps => _ringSync.isSyncing ? _ringSync.currentSpeedKBps : _storageSync.currentSpeedKBps;

  bool get isSdCardSyncing => _sdcardSync.isSyncing;

  double get sdCardSpeedKBps => _sdcardSync.currentSpeedKBps;

  bool get isFlashPageSyncing => _flashPageSync.isSyncing;

  /// Get conversation IDs accumulated so far from completed upload batches.
  /// Returns null if no sync is in progress or no batches have completed.
  SyncLocalFilesResponse? get accumulatedResponse => _phoneSync.accumulatedResponse;
}
