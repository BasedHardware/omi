import 'dart:async';
import 'dart:collection';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';
import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

/// Ring-buffer storage sync for firmware 3.0.20+ (omi PR #7216).
///
/// Wire layout (per record, packet_size = 444 bytes):
///   [timestamp:4 BE][audio_payload:440]
/// The 440-byte payload uses the same packed [size:1][frame:size]... framing
/// as the multi-file protocol, so the audio parser is reused unchanged.
///
/// Notifications on the control characteristic carry an opcode byte:
///   0x01 ACK             [0x01][status]
///   0x02 INFO            [0x02][read:u64 BE][write:u64 BE][cap:u32 BE][dropped:u64 BE][pkt_size:u16 BE]
///   0x03 DATA            [0x03][raw_bytes...]   <-- not aligned to record boundaries
///   0x04 DONE            [0x04][status][next_seq:u64 BE](optional [crc32:u32 BE])
///   0x05 READ_BEGIN      [0x05][transfer_start_seq:u64 BE][packet_count:u32 BE]
///
/// Data-safety invariant: each bounded source-sequence range is registered in
/// the atomically persisted local WAL manifest only after READ_BEGIN, byte
/// count, DONE, and optional CRC all agree. CMD_RING_ADVANCE is sent after that
/// durable registration. On any failure the current range stays on the device;
/// previously advanced ranges never need to be downloaded again.
typedef RingConnectionResolver = Future<DeviceConnection?> Function(String deviceId);
typedef RingDocumentsDirectoryProvider = Future<Directory> Function();

class RingStorageSyncImpl implements RingStorageSync {
  static const RingInfoRetryPolicy _ringInfoRetryPolicy = RingInfoRetryPolicy();

  static const int defaultPacketsPerRead = 1800;
  static const Duration defaultInactivityTimeout = Duration(seconds: 15);

  List<Wal> _wals = [];
  BtDevice? _device;

  StreamSubscription? _notifyStream;
  String? _activeSyncDeviceId;
  bool _firmwareStopRequested = false;

  IWalSyncListener listener;
  LocalWalSync? _localSync;
  final RingConnectionResolver? _connectionResolverOverride;
  final RingDocumentsDirectoryProvider _documentsDirectoryProvider;
  final int _packetsPerRead;
  final Duration _inactivityTimeout;
  final int Function() _nowSeconds;

  bool _isCancelled = false;
  bool _isSyncing = false;
  @override
  bool get isSyncing => _isSyncing;

  int _totalBytesDownloaded = 0;
  DateTime? _downloadStartTime;
  double _currentSpeedKBps = 0.0;
  @override
  double get currentSpeedKBps => _currentSpeedKBps;

  RingStorageSyncImpl(
    this.listener, {
    RingConnectionResolver? connectionResolver,
    RingDocumentsDirectoryProvider? documentsDirectoryProvider,
    int packetsPerRead = defaultPacketsPerRead,
    Duration inactivityTimeout = defaultInactivityTimeout,
    int Function()? nowSeconds,
  })  : _connectionResolverOverride = connectionResolver,
        _documentsDirectoryProvider = documentsDirectoryProvider ?? getApplicationDocumentsDirectory,
        _packetsPerRead = packetsPerRead,
        _inactivityTimeout = inactivityTimeout,
        _nowSeconds = nowSeconds ?? _systemNowSeconds {
    if (packetsPerRead <= 0) throw ArgumentError.value(packetsPerRead, 'packetsPerRead', 'must be positive');
  }

  static int _systemNowSeconds() => DateTime.now().millisecondsSinceEpoch ~/ 1000;

  Future<DeviceConnection?> _ensureConnection(String deviceId) {
    final resolver = _connectionResolverOverride;
    if (resolver != null) return resolver(deviceId);
    return ServiceManager.instance().device.ensureConnection(deviceId);
  }

  @override
  void setLocalSync(LocalWalSync localSync) {
    _localSync = localSync;
  }

  @override
  void setDevice(BtDevice? device) {
    _device = device;
    if (device == null) {
      _wals = [];
      listener.onWalUpdated();
    }
  }

  @override
  void cancelSync() {
    if (!_isSyncing) return;
    _isCancelled = true;
    Logger.debug('RingStorageSync: Cancel requested');

    final sub = _notifyStream;
    if (sub != null) {
      unawaited(sub.cancel());
    }
    unawaited(_requestFirmwareStopSync());
  }

  Future<void> _requestFirmwareStopSync() async {
    if (_firmwareStopRequested) return;
    _firmwareStopRequested = true;

    final deviceId = _activeSyncDeviceId ?? _device?.id;
    if (deviceId == null || deviceId.isEmpty) return;

    try {
      final connection = await _ensureConnection(deviceId);
      if (connection == null) return;
      // CMD_STOP_SYNC (0x03) — does not persist progress; data stays in the ring.
      await connection.stopStorageSync();
      Logger.debug('RingStorageSync: STOP command sent');
    } catch (e) {
      Logger.debug('RingStorageSync: Failed to send STOP: $e');
    }
  }

  void _resetSyncState() {
    _isCancelled = false;
    _isSyncing = false;
    _activeSyncDeviceId = null;
    _firmwareStopRequested = false;
    _totalBytesDownloaded = 0;
    _downloadStartTime = null;
    _currentSpeedKBps = 0.0;
  }

  void _updateSpeed(int newBytes) {
    _totalBytesDownloaded += newBytes;
    if (_downloadStartTime != null) {
      final elapsedSeconds = DateTime.now().difference(_downloadStartTime!).inMilliseconds / 1000.0;
      if (elapsedSeconds > 0.5) {
        _currentSpeedKBps = (_totalBytesDownloaded / 1024.0) / elapsedSeconds;
      }
    }
  }

  /// Returns true if the device has unread packets in the ring.
  /// Returns false for devices on older firmware (status read returns null).
  @override
  Future<bool> hasFilesToSync() async {
    if (_device == null) return false;
    try {
      final connection = await _ensureConnection(_device!.id);
      if (connection == null) return false;
      final status = await connection.getRingStatus();
      final result = status != null && status.unreadPackets > 0;
      Logger.debug('RingStorageSync.hasFilesToSync: status=$status result=$result');
      return result;
    } catch (e) {
      Logger.debug('RingStorageSync.hasFilesToSync: error: $e');
      return false;
    }
  }

  /// Returns the cached virtual WAL representing the unread ring range.
  /// Safe to call during sync — never touches BLE.
  @override
  Future<List<Wal>> getMissingWals() async {
    return _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.sdcard).toList();
  }

  /// Discover unread ring data via BLE. Must be called BEFORE syncAll().
  /// Constructs ONE virtual Wal covering the entire unread range (the ring is
  /// a single logical stream, not a list of files).
  @override
  Future<void> refreshWalsFromDevice() async {
    if (_device == null) return;
    if (_isSyncing) {
      Logger.debug('RingStorageSync.refreshWalsFromDevice: skipping — sync in progress');
      return;
    }

    try {
      final connection = await _ensureConnection(_device!.id);
      if (connection == null) return;

      final status = await connection.getRingStatus();
      Logger.debug('RingStorageSync.refreshWalsFromDevice: status=$status');
      if (status == null || status.unreadPackets <= 0) {
        _wals = [];
        return;
      }

      // Stop any in-flight transfer before discovery (mirrors PR #5905 pattern).
      await connection.stopStorageSync();
      await Future.delayed(const Duration(milliseconds: 500));

      final codec = await connection.getAudioCodec();
      final pd = await _device!.getDeviceInfo(connection);
      final deviceModel = pd.modelNumber.isNotEmpty ? pd.modelNumber : 'Omi';

      final fps = codec.getFramesPerSecond();
      final frameLen = codec.getFramesLengthInBytes();
      // Estimate seconds: each 440B audio payload holds ~ floor(440 / (frameLen + 1)) frames
      // (size byte + frame). framesPerRecord rounded down for a conservative duration.
      final framesPerRecord = frameLen > 0 ? RingProtocol.audioPayloadBytes ~/ (frameLen + 1) : 0;
      final estimatedFrames = framesPerRecord * status.unreadPackets;
      final estimatedSecs = fps > 0 ? estimatedFrames ~/ fps : 0;

      // Skip very small rings (<10s of audio) — same threshold as the file-based path.
      if (estimatedSecs < 10) {
        Logger.debug('RingStorageSync.refreshWalsFromDevice: ring too small ($estimatedSecs s), skipping');
        _wals = [];
        return;
      }

      final displayTimerStart = DateTime.now().millisecondsSinceEpoch ~/ 1000 - estimatedSecs;
      _wals = [
        Wal(
          codec: codec,
          timerStart: displayTimerStart,
          status: WalStatus.miss,
          storage: WalStorage.sdcard,
          seconds: estimatedSecs,
          storageOffset: 0,
          storageTotalBytes: status.unreadPackets * RingProtocol.recordSize,
          fileNum: -1,
          device: _device!.id,
          deviceModel: deviceModel,
          totalFrames: estimatedFrames,
          syncedFrameOffset: 0,
        ),
      ];
      Logger.debug(
        'RingStorageSync.refreshWalsFromDevice: 1 virtual WAL (${status.unreadPackets} pkts, ~${estimatedSecs}s)',
      );
    } catch (e) {
      Logger.debug('RingStorageSync.refreshWalsFromDevice: error: $e');
    }
  }

  /// Delete a wal. WalSyncs.deleteWal cascades to every sub-sync regardless
  /// of which one owns the wal, so we MUST verify membership before touching
  /// the device — clearing the ring on an unrelated phone/sdcard delete would
  /// wipe data the user didn't intend to delete.
  ///
  /// The ring is a single logical stream; deleting our virtual wal maps to
  /// clearing the entire ring on the device.
  @override
  Future deleteWal(Wal wal) async {
    if (!_wals.any((w) => w.id == wal.id)) return;
    if (_isSyncing) {
      Logger.debug('RingStorageSync.deleteWal: skipping — sync in progress');
      return;
    }
    await _clearRingOnDevice();
    _wals = _wals.where((w) => w.id != wal.id).toList();
    listener.onWalUpdated();
  }

  @override
  Future<void> deleteAllSyncedWals() async {
    _wals = _wals.where((w) => w.status != WalStatus.synced).toList();
    listener.onWalUpdated();
  }

  /// Cascades from WalSyncs.deleteAllPendingWals across every sub-sync.
  /// Only clear the ring when WE actually own pending wals — otherwise this
  /// runs as a no-op for users with phone/sdcard pending wals only.
  @override
  Future<void> deleteAllPendingWals() async {
    if (!_wals.any((w) => w.status == WalStatus.miss)) return;
    if (_isSyncing) {
      Logger.debug('RingStorageSync.deleteAllPendingWals: skipping — sync in progress');
      return;
    }
    await _clearRingOnDevice();
    _wals = _wals.where((w) => w.status != WalStatus.miss).toList();
    listener.onWalUpdated();
  }

  Future<void> _clearRingOnDevice() async {
    if (_device == null) return;
    try {
      final connection = await _ensureConnection(_device!.id);
      if (connection == null) return;
      final ok = await connection.clearRing();
      Logger.debug('RingStorageSync._clearRingOnDevice: ok=$ok');
    } catch (e) {
      Logger.debug('RingStorageSync._clearRingOnDevice: error: $e');
    }
  }

  @override
  void start() {}

  @override
  Future stop() async {
    cancelSync();
    await _notifyStream?.cancel();
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    if (_device == null) {
      Logger.debug('RingStorageSync.syncAll: _device is null');
      return null;
    }

    final wals = _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.sdcard).toList();
    if (wals.isEmpty) return null;

    _resetSyncState();
    _isSyncing = true;
    DebugLogManager.logInfo('RingStorageSync: Starting sync');

    final resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    try {
      for (final wal in wals) {
        if (_isCancelled) break;
        final complete = await _syncRing(wal, progress: progress);
        if (!complete) {
          // Leave wal.status as miss so the next sync session retries it.
          // This preserves the "resume from same read_seq" guarantee — pairing
          // with the no-advance-on-failure invariant in _syncRing.
          Logger.debug('RingStorageSync: Ring transfer incomplete; ring untouched, will resume next sync');
          listener.onWalUpdated();
          if (!_isCancelled) {
            throw const RingStorageException('Device storage transfer did not complete');
          }
          break;
        }
        wal.status = WalStatus.synced;
        listener.onWalUpdated();
      }
    } catch (e) {
      Logger.debug('RingStorageSync.syncAll: error: $e');
      DebugLogManager.logError(e, null, 'RingStorageSync failed', {'device': _device?.id});
      rethrow;
    } finally {
      _isSyncing = false;
    }

    if (!_isCancelled) {
      progress?.onWalSyncedProgress(1.0, speedKBps: _currentSpeedKBps);
    }
    return resp;
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) async {
    _resetSyncState();
    _isSyncing = true;
    try {
      progress?.onWalSyncedProgress(0.0);
      final complete = await _syncRing(wal, progress: progress);
      if (complete) {
        wal.status = WalStatus.synced;
        progress?.onWalSyncedProgress(1.0, speedKBps: _currentSpeedKBps);
      } else if (!_isCancelled) {
        throw const RingStorageException('Device storage transfer did not complete');
      }
      listener.onWalUpdated();
    } catch (e) {
      Logger.debug('RingStorageSync.syncWal: error: $e');
      rethrow;
    } finally {
      _isSyncing = false;
    }
    return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
  }

  /// Drain the ring in bounded, independently durable transactions.
  ///
  /// A full CV1 can take well over an hour to transfer. Keeping one cumulative
  /// ADVANCE behind the entire backlog means any disconnect replays everything.
  /// Each range is small enough to retry cheaply, and advances only after that
  /// exact range is durably represented by local WALs.
  Future<bool> _syncRing(Wal wal, {IWalSyncProgressListener? progress}) async {
    if (_device == null) return false;
    final connection = await _ensureConnection(_device!.id);
    if (connection == null) throw Exception('Device not connected');

    _activeSyncDeviceId = _device!.id;
    _downloadStartTime = DateTime.now();
    _totalBytesDownloaded = 0;

    final ringInfo = await _ringInfoRetryPolicy.run(connection.getRingInfo);
    if (ringInfo.unreadPackets <= 0) {
      Logger.debug('RingStorageSync._syncRing: nothing to read');
      return true;
    }
    if (ringInfo.droppedPackets > 0) {
      DebugLogManager.logWarning('RingStorageSync: ring overwrote ${ringInfo.droppedPackets} packets before sync', {
        'ringInfo': ringInfo.toString(),
      });
    }
    final targetWriteSeq = ringInfo.writeSeq;
    final totalRecords = targetWriteSeq - ringInfo.readSeq;
    final fps = wal.codec.getFramesPerSecond();
    final fallbackAnchor = await _resolveFallbackAnchor(wal, ringInfo.readSeq, fps);
    var nextReadSeq = ringInfo.readSeq;
    var completedRecords = 0;
    var completedFrames = 0;

    while (!_isCancelled && nextReadSeq < targetWriteSeq) {
      final remaining = targetWriteSeq - nextReadSeq;
      final packetCount = remaining > _packetsPerRead ? _packetsPerRead : remaining;
      final advancedTo = await _syncRange(
        connection,
        wal,
        startSeq: nextReadSeq,
        packetCount: packetCount,
        fallbackAnchor: fallbackAnchor,
        fallbackFramesBefore: completedFrames,
        completedRecords: completedRecords,
        totalRecords: totalRecords,
        progress: progress,
      );
      if (advancedTo == null) return false;
      nextReadSeq = advancedTo.nextSeq;
      completedRecords += packetCount;
      completedFrames += advancedTo.frameCount;
    }

    return !_isCancelled && nextReadSeq == targetWriteSeq;
  }

  Future<int> _resolveFallbackAnchor(Wal virtualWal, int initialReadSeq, int fps) async {
    final localSync = _localSync;
    if (localSync == null) return virtualWal.timerStart;

    final sourcePattern = RegExp(r'^ring_(\d+)_(\d+)$');
    Wal? predecessor;
    for (final wal in await localSync.getAllWals()) {
      if (wal.device != virtualWal.device || wal.sourceId == null) continue;
      final match = sourcePattern.firstMatch(wal.sourceId!);
      if (match == null) continue;
      final startSeq = int.parse(match.group(1)!);
      final endSeq = int.parse(match.group(2)!);
      if (startSeq == initialReadSeq) return wal.timerStart;
      if (endSeq == initialReadSeq &&
          (predecessor == null || wal.timerStart + wal.seconds > predecessor.timerStart + predecessor.seconds)) {
        predecessor = wal;
      }
    }
    if (predecessor != null) {
      return predecessor.timerStart + predecessor.totalFrames ~/ (fps == 0 ? 1 : fps);
    }
    return virtualWal.timerStart;
  }

  Future<_RingRangeResult?> _syncRange(
    DeviceConnection connection,
    Wal wal, {
    required int startSeq,
    required int packetCount,
    required int fallbackAnchor,
    required int fallbackFramesBefore,
    required int completedRecords,
    required int totalRecords,
    IWalSyncProgressListener? progress,
  }) async {
    final completer = Completer<bool>();
    final reassembler = RingRecordReassembler();
    final pendingRecords = ListQueue<_RecoveredRingRecord>();
    int recordsConsumed = 0;
    int segment = 0;
    int? previousRecordTimestamp;
    int fallbackFrames = 0;
    final fps = wal.codec.getFramesPerSecond();
    final chunkFrames = sdcardChunkSizeSecs * fps;
    int? doneNextSeq;
    int? transferStartSeq;
    int? announcedPacketCount;
    bool doneOk = false;
    bool protocolError = false;
    bool crcVerified = true;
    bool flushError = false;
    Timer? inactivityTimer;
    final transferCrc = RingTransferCrc32();

    DateTime lastProgressUpdate = DateTime.now();
    const progressInterval = Duration(milliseconds: 200);

    Future<void> flushValidatedRange() async {
      while (pendingRecords.isNotEmpty) {
        final firstSegment = pendingRecords.first.segment;
        final chunkRecords = <_RecoveredRingRecord>[];
        var frameCount = 0;
        while (pendingRecords.isNotEmpty && pendingRecords.first.segment == firstSegment) {
          if (frameCount >= chunkFrames) break;
          final record = pendingRecords.removeFirst();
          chunkRecords.add(record);
          frameCount += record.frames.length;
        }
        if (chunkRecords.isEmpty) break;

        final frames = chunkRecords.expand((record) => record.frames).toList(growable: false);
        final timerStart = chunkRecords.first.timestamp;
        final sourceStartSeq = chunkRecords.first.sequence;
        final sourceEndSeq = chunkRecords.last.sequence + 1;
        final sourceId = 'ring_${sourceStartSeq}_$sourceEndSeq';
        try {
          final file = await _flushToDisk(wal, frames, timerStart, sourceId);
          await _registerWithLocalSync(wal, file, timerStart, frames.length, sourceId);
        } catch (e) {
          Logger.debug('RingStorageSync._syncRing: flush error: $e');
          flushError = true;
          rethrow;
        }
      }
    }

    void armInactivityTimer() {
      inactivityTimer?.cancel();
      inactivityTimer = Timer(_inactivityTimeout, () {
        if (!completer.isCompleted) {
          Logger.debug('RingStorageSync: range inactive for ${_inactivityTimeout.inSeconds}s');
          completer.complete(false);
        }
      });
    }

    await _notifyStream?.cancel();

    _notifyStream = await connection.getBleStorageBytesListener(
      onStorageBytesReceived: (List<int> value) {
        if (completer.isCompleted) return;
        if (_isCancelled) {
          if (!completer.isCompleted) completer.complete(false);
          return;
        }
        if (value.isEmpty) return;
        armInactivityTimer();

        final opcode = value[0];
        if (opcode == RingProtocol.notifyAck) {
          // ACK from a CMD we didn't initiate here (e.g. CLEAR/STOP). Ignore.
          return;
        }
        if (opcode == RingProtocol.notifyInfo) {
          // Late INFO response; we already have ringInfo. Ignore.
          return;
        }
        if (opcode == RingProtocol.notifyReadBegin) {
          final begin = RingProtocol.parseReadBeginNotification(value);
          if (begin == null || begin.transferStartSeq != startSeq || begin.packetCount != packetCount) {
            protocolError = true;
            Logger.debug('RingStorageSync: invalid READ_BEGIN for requested range start=$startSeq count=$packetCount');
            if (!completer.isCompleted) completer.complete(false);
          } else if (transferStartSeq != null &&
              (transferStartSeq != begin.transferStartSeq || announcedPacketCount != begin.packetCount)) {
            protocolError = true;
            if (!completer.isCompleted) completer.complete(false);
          } else {
            transferStartSeq = begin.transferStartSeq;
            announcedPacketCount = begin.packetCount;
            Logger.debug(
              'RingStorageSync: NOTIFY_READ_BEGIN start=${begin.transferStartSeq} count=${begin.packetCount}',
            );
          }
          return;
        }
        if (opcode == RingProtocol.notifyDone) {
          final done = RingProtocol.parseDoneNotification(value);
          if (done == null) {
            Logger.debug('RingStorageSync: NOTIFY_DONE truncated (${value.length} bytes)');
            if (!completer.isCompleted) completer.complete(false);
            return;
          }
          doneNextSeq = done.nextSeq;
          doneOk = done.isOk;
          if (done.transferCrc32 != null) {
            crcVerified = done.transferCrc32 == transferCrc.value;
            if (!crcVerified) {
              Logger.debug(
                'RingStorageSync: transfer CRC mismatch expected=${done.transferCrc32} actual=${transferCrc.value}',
              );
            }
          }
          Logger.debug('RingStorageSync: NOTIFY_DONE status=${done.status} next_seq=$doneNextSeq');
          if (!completer.isCompleted) completer.complete(true);
          return;
        }
        if (opcode != RingProtocol.notifyData) {
          Logger.debug('RingStorageSync: unknown notification opcode 0x${opcode.toRadixString(16)}');
          return;
        }

        // NOTIFY_DATA: append payload (skip the leading opcode byte) to the
        // reassembler. The firmware does NOT align chunks to record boundaries.
        final payload = value.sublist(1);
        if (transferStartSeq == null) {
          protocolError = true;
          Logger.debug('RingStorageSync: DATA arrived before READ_BEGIN');
          if (!completer.isCompleted) completer.complete(false);
          return;
        }
        transferCrc.add(payload);
        reassembler.append(payload);
        _updateSpeed(payload.length);

        for (final record in reassembler.drainRecords()) {
          final ts = RingProtocol.readRecordTimestamp(record);
          final frames = RingProtocol.parseAudioPayload(record.sublist(RingProtocol.timestampBytes));
          if (frames.isEmpty) {
            protocolError = true;
            Logger.debug('RingStorageSync: record ${transferStartSeq! + recordsConsumed} has no decodable frames');
          }
          final now = _nowSeconds();
          final effectiveTimestamp = RingProtocol.isPlausibleRecordTimestamp(ts, nowSeconds: now)
              ? ts
              : fallbackAnchor + (fallbackFramesBefore + fallbackFrames) ~/ (fps == 0 ? 1 : fps);

          if (previousRecordTimestamp != null &&
              (effectiveTimestamp < previousRecordTimestamp! || effectiveTimestamp > previousRecordTimestamp! + 2)) {
            segment += 1;
          }
          previousRecordTimestamp = effectiveTimestamp;

          if (frames.isNotEmpty) {
            pendingRecords.add(
              _RecoveredRingRecord(
                sequence: transferStartSeq! + recordsConsumed,
                timestamp: effectiveTimestamp,
                segment: segment,
                frames: frames,
              ),
            );
          }
          fallbackFrames += frames.length;
          recordsConsumed += 1;
        }

        // Throttled progress update.
        final now = DateTime.now();
        if (now.difference(lastProgressUpdate) >= progressInterval) {
          lastProgressUpdate = now;
          if (totalRecords > 0) {
            final pct = ((completedRecords + recordsConsumed) / totalRecords).clamp(0.0, 1.0);
            progress?.onWalSyncedProgress(
              pct,
              speedKBps: _currentSpeedKBps,
              phase: SyncPhase.downloadingFromDevice,
              currentFile: 1,
              totalFiles: 1,
            );
          }
        }
      },
    );

    if (_notifyStream == null) {
      throw Exception('Failed to set up storage listener');
    }
    _notifyStream!.onDone(() {
      if (!completer.isCompleted) {
        Logger.debug('RingStorageSync: BLE stream closed mid-transfer');
        completer.complete(false);
      }
    });

    armInactivityTimer();

    final readOk = await connection.readRingFromSeq(startSeq, packetCount: packetCount);
    if (!readOk) {
      inactivityTimer?.cancel();
      await _notifyStream?.cancel();
      _notifyStream = null;
      throw Exception('Failed to send CMD_RING_READ');
    }

    Logger.debug(
      'RingStorageSync: reading bounded range start=$startSeq count=$packetCount',
    );

    bool reachedDone = false;
    try {
      reachedDone = await completer.future;
    } catch (e) {
      Logger.debug('RingStorageSync: transfer error: $e');
    } finally {
      inactivityTimer?.cancel();
      if (_isCancelled) {
        await _requestFirmwareStopSync();
      }
      await _notifyStream?.cancel();
      _notifyStream = null;
    }

    final receivedCompleteRange = RingProtocol.receivedCompleteRange(
      transferStartSeq: transferStartSeq,
      announcedPacketCount: announcedPacketCount,
      doneNextSeq: doneNextSeq,
      receivedPacketCount: recordsConsumed,
      pendingBytes: reassembler.pendingBytes,
    );
    final transportComplete =
        reachedDone && doneOk && !protocolError && crcVerified && !_isCancelled && receivedCompleteRange;

    // No bytes are registered before the complete range and optional CRC have
    // been validated. A corrupt retry therefore cannot poison an immutable
    // source identity that would block the next clean retry.
    if (transportComplete) {
      try {
        await flushValidatedRange();
      } catch (e) {
        Logger.debug('RingStorageSync: final flush error: $e');
      }
    }

    final advancedOk = RingProtocol.canAdvance(
      reachedDone: reachedDone,
      doneOk: doneOk,
      flushError: flushError,
      isCancelled: _isCancelled,
      receivedCompleteRange: receivedCompleteRange,
      protocolError: protocolError,
      crcVerified: crcVerified,
    );
    if (advancedOk) {
      final ok = await connection.advanceRing(doneNextSeq!);
      Logger.debug('RingStorageSync: advance(seq=$doneNextSeq) -> $ok (records=$recordsConsumed)');
      DebugLogManager.logEvent('ring_sync_advanced', {
        'records': recordsConsumed,
        'next_seq': doneNextSeq,
        'advance_ok': ok,
      });
      return ok ? _RingRangeResult(nextSeq: doneNextSeq!, frameCount: fallbackFrames) : null;
    } else {
      Logger.debug(
        'RingStorageSync: skipping advance (reachedDone=$reachedDone doneOk=$doneOk flushError=$flushError '
        'cancelled=$_isCancelled completeRange=$receivedCompleteRange protocolError=$protocolError '
        'crcVerified=$crcVerified records=$recordsConsumed pendingBytes=${reassembler.pendingBytes})',
      );
      return null;
    }
  }

  /// Write opus frames to disk in WAL format: [frame_length_u32_le][frame_data]...
  /// Identical to StorageSyncImpl._flushToDisk for downstream compatibility.
  Future<File> _flushToDisk(
    Wal wal,
    List<List<int>> frames,
    int timerStart,
    String sourceId,
  ) async {
    final directory = await _documentsDirectoryProvider();
    final filePath = '${directory.path}/${wal.getFileNameByTimeStarts(timerStart, sourceId: sourceId)}';

    var dataLength = 0;
    for (final frame in frames) {
      dataLength += Uint32List.bytesPerElement + frame.length;
    }

    final data = Uint8List(dataLength);
    final writer = ByteData.sublistView(data);
    var offset = 0;
    for (final frame in frames) {
      writer.setUint32(offset, frame.length, Endian.little);
      offset += Uint32List.bytesPerElement;
      data.setRange(offset, offset + frame.length, frame);
      offset += frame.length;
    }

    final file = File(filePath);
    if (await file.exists()) {
      final existing = await file.readAsBytes();
      if (!listEquals(existing, data)) {
        throw StateError('Immutable ring WAL collision for $sourceId');
      }
      return file;
    }

    final temporaryFile = File('$filePath.tmp');
    try {
      if (await temporaryFile.exists()) await temporaryFile.delete();
      await temporaryFile.writeAsBytes(data, flush: true);
      await temporaryFile.rename(filePath);
    } catch (_) {
      if (await temporaryFile.exists()) {
        try {
          await temporaryFile.delete();
        } catch (_) {}
      }
      rethrow;
    }
    Logger.debug('RingStorageSync: wrote ${data.length}B (${frames.length} frames) to $filePath');
    return file;
  }

  Future<void> _registerWithLocalSync(
    Wal wal,
    File file,
    int timerStart,
    int frameCount,
    String sourceId,
  ) async {
    if (_localSync == null) {
      throw StateError('LocalWalSync is unavailable; refusing to acknowledge device records');
    }
    final fps = wal.codec.getFramesPerSecond();
    final seconds = fps > 0 ? frameCount ~/ fps : 0;

    final localWal = Wal(
      codec: wal.codec,
      channel: wal.channel,
      sampleRate: wal.sampleRate,
      timerStart: timerStart,
      filePath: file.path.split('/').last,
      storage: WalStorage.disk,
      status: WalStatus.miss,
      device: wal.device,
      deviceModel: wal.deviceModel,
      seconds: seconds,
      totalFrames: frameCount,
      syncedFrameOffset: 0,
      originalStorage: WalStorage.sdcard,
      sourceId: sourceId,
    );

    final registration = await _localSync!.addExternalWal(localWal);
    Logger.debug(
      'RingStorageSync: registered chunk (source=$sourceId, ts=$timerStart, ${seconds}s, '
      '$frameCount frames, result=${registration.name})',
    );
  }
}

class _RecoveredRingRecord {
  final int sequence;
  final int timestamp;
  final int segment;
  final List<List<int>> frames;

  const _RecoveredRingRecord({
    required this.sequence,
    required this.timestamp,
    required this.segment,
    required this.frames,
  });
}

class _RingRangeResult {
  final int nextSeq;
  final int frameCount;

  const _RingRangeResult({required this.nextSeq, required this.frameCount});
}
