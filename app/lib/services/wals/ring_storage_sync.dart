import 'dart:async';
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
import 'package:omi/services/wals/pendant_ring_custody.dart';
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
///   0x04 DONE            [0x04][status][next_seq:u64 BE]
///   0x05 READ_BEGIN      [0x05][transfer_start_seq:u64 BE][packet_count:u32 BE]
///
/// Data-safety invariant: the device-side read frontier is released ONLY for
/// records proven durable on the phone — file bytes fsynced AND the WAL index
/// save completed. With CAP_APP_ACK_RECLAIM an incarnation-scoped ADVANCE_ID
/// may run incrementally per durable chunk; otherwise a single anonymous
/// ADVANCE is sent after a DONE that consumed the expected records. Legacy
/// firmware may reclaim during BLE delivery; interruption can lose its RAM
/// tail. Custody firmware preserves ONLY unadvanced records; already durable
/// chunk advances remain. On any failure (cancel, BLE drop, READ_BEGIN/DONE
/// mismatch, refused admission) no further advance is sent — the next sync
/// resumes from the same read_seq.
class RingStorageSyncImpl implements RingStorageSync {
  List<Wal> _wals = [];
  BtDevice? _device;

  StreamSubscription? _notifyStream;
  String? _activeSyncDeviceId;
  bool _firmwareStopRequested = false;

  IWalSyncListener listener;
  LocalWalSync? _localSync;

  bool _isCancelled = false;
  bool _isSyncing = false;
  @override
  bool get isSyncing => _isSyncing;

  final Map<String, int> _droppedBaseline = {};

  int _totalBytesDownloaded = 0;
  DateTime? _downloadStartTime;
  double _currentSpeedKBps = 0.0;
  @override
  double get currentSpeedKBps => _currentSpeedKBps;

  RingStorageSyncImpl(this.listener);

  @visibleForTesting
  set testWals(List<Wal> wals) => _wals = wals;

  DeviceConnection? _testConnection;

  @visibleForTesting
  set testConnection(DeviceConnection? connection) => _testConnection = connection;

  PendantRingCustody _custody = PendantRingCustody.shared;

  @visibleForTesting
  set testCustody(PendantRingCustody custody) => _custody = custody;

  @override
  void setLocalSync(LocalWalSync localSync) {
    _localSync = localSync;
  }

  @override
  void setDevice(BtDevice? device) {
    _device = device;
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
      final connection = await ServiceManager.instance().device.ensureConnection(deviceId);
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
      final connection = await ServiceManager.instance().device.ensureConnection(_device!.id);
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
      final connection = await ServiceManager.instance().device.ensureConnection(_device!.id);
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
  /// clearing the entire ring on the device. The wal is removed only after
  /// the device confirms the clear — an unconfirmed clear keeps the wal so
  /// the audio cannot resurrect as a "new" recording on the next sync.
  @override
  Future deleteWal(Wal wal) async {
    if (!_wals.any((w) => w.id == wal.id)) return;
    if (_isSyncing) {
      Logger.debug('RingStorageSync.deleteWal: skipping — sync in progress');
      return;
    }
    final cleared = await _clearRingOnDevice();
    if (!cleared) {
      Logger.debug('RingStorageSync.deleteWal: ring clear not confirmed, keeping WAL');
      return;
    }
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
    final cleared = await _clearRingOnDevice();
    if (!cleared) {
      Logger.debug('RingStorageSync.deleteAllPendingWals: ring clear not confirmed, keeping WALs');
      return;
    }
    _wals = _wals.where((w) => w.status != WalStatus.miss).toList();
    listener.onWalUpdated();
  }

  /// Clear the ring on the device. Returns true only when the device
  /// confirmed the clear; absent device, missing connection, BLE errors, and
  /// a rejected command all return false (fail-closed).
  Future<bool> _clearRingOnDevice() async {
    if (_device == null) return false;
    try {
      final connection = _testConnection ?? await ServiceManager.instance().device.ensureConnection(_device!.id);
      if (connection == null) return false;
      final ok = await connection.clearRing();
      Logger.debug('RingStorageSync._clearRingOnDevice: ok=$ok');
      return ok;
    } catch (e) {
      Logger.debug('RingStorageSync._clearRingOnDevice: error: $e');
      return false;
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
          Logger.debug(
            'RingStorageSync: Ring transfer incomplete; unadvanced records preserved, will resume next sync',
          );
          listener.onWalUpdated();
          break;
        }
        wal.status = WalStatus.synced;
        wal.deviceDownloadFraction = null;
        listener.onWalUpdated();
      }
    } catch (e) {
      Logger.debug('RingStorageSync.syncAll: error: $e');
      DebugLogManager.logError(e, null, 'RingStorageSync failed', {'device': _device?.id});
    } finally {
      _isSyncing = false;
      for (final w in _wals) {
        w.deviceDownloadFraction = null;
      }
    }

    progress?.onWalSyncedProgress(1.0, speedKBps: _currentSpeedKBps);
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
      }
      progress?.onWalSyncedProgress(1.0, speedKBps: _currentSpeedKBps);
      listener.onWalUpdated();
    } catch (e) {
      Logger.debug('RingStorageSync.syncWal: error: $e');
    } finally {
      _isSyncing = false;
      for (final w in _wals) {
        w.deviceDownloadFraction = null;
      }
    }
    return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
  }

  /// Pull the unread ring contents from the device, parse opus frames, register
  /// chunks with LocalWalSync, then advance the ring iff NOTIFY_DONE arrived.
  /// Returns true if the transfer ran to completion (DONE received and acted on).
  Future<bool> _syncRing(Wal wal, {IWalSyncProgressListener? progress}) async {
    if (_device == null) return false;
    final admittedGeneration = _localSync?.sessionGeneration ?? -1;
    final connection = _testConnection ?? await ServiceManager.instance().device.ensureConnection(_device!.id);
    if (connection == null) throw Exception('Device not connected');

    _activeSyncDeviceId = _device!.id;
    _downloadStartTime = DateTime.now();
    _totalBytesDownloaded = 0;

    final epoch = connection.ringCustodyEpoch;
    bool stillEpoch() => connection.ringCustodyEpoch == epoch && !_isCancelled;

    await connection.ringCustodyReady;
    if (!stillEpoch()) return false;

    // Snapshot ring state so we know what range we're consuming.
    final ringInfo = await connection.getRingInfo();
    if (!stillEpoch()) return false;
    if (ringInfo == null) {
      Logger.debug('RingStorageSync._syncRing: getRingInfo returned null');
      return false;
    }
    if (ringInfo.unreadPackets <= 0) {
      Logger.debug('RingStorageSync._syncRing: nothing to read');
      return true;
    }
    if (ringInfo.droppedPackets > 0) {
      DebugLogManager.logWarning('RingStorageSync: ring overwrote ${ringInfo.droppedPackets} packets before sync', {
        'ringInfo': ringInfo.toString(),
      });
    }
    final status = await connection.getRingStatus();
    if (!stillEpoch()) return false;
    final rtcValid = status?.isRtcValid ?? false;

    final custodyDeviceId = _device!.id;
    final effectiveCaps = connection.ringEffectiveCaps;
    final ringId = (effectiveCaps & RingProtocol.capRingId) != 0 ? ringInfo.ringId : null;
    final readStart = ringInfo.readSeq;
    if (ringId != null && !_custody.hasConnection(custodyDeviceId, epoch)) {
      if (!stillEpoch()) return false;
      await _custody.beginConnection(
        custodyDeviceId,
        epoch,
        ringInfo,
        sessionToken: Object(),
        effectiveCaps: effectiveCaps,
        replayAdvance: (seq) async =>
            (await connection.advanceRingCustody(seq, expectedEpoch: epoch, expectedRingId: ringId))?.status,
      );
      if (!stillEpoch()) return false;
    }
    final droppedKey = '$custodyDeviceId:${ringInfo.ringId}';
    final lastDropped = _droppedBaseline[droppedKey];
    final droppedDelta = lastDropped == null ? null : (ringInfo.droppedPackets - lastDropped).clamp(0, 1 << 62);
    _droppedBaseline[droppedKey] = ringInfo.droppedPackets;

    final completer = Completer<bool>();
    final reassembler = RingRecordReassembler();
    final List<List<int>> bytesData = []; // parsed opus frames awaiting flush
    final recordSeqs = <int>[];
    final recordFrameCounts = <int>[];
    final recordTimestamps = <int>[];
    int provenSeq = readStart;
    int skippedDuplicates = 0;
    int recordsConsumed = 0;
    int? firstRecordTs;
    int elapsedTotal = 0;
    int bufferBaseElapsed = 0;
    final fps = wal.codec.getFramesPerSecond();
    final chunkFrames = sdcardChunkSizeSecs * fps;
    int? doneNextSeq;
    bool doneOk = false;
    int? beginStartSeq;
    int? beginPacketCount;
    bool flushError = false;
    Future<void>? inFlightFlush;
    Timer? firstDataTimer;
    bool firstDataReceived = false;
    DateTime lastProgressUpdate = DateTime.now();
    const progressInterval = Duration(milliseconds: 200);

    List<(int, int)> contiguousRanges(List<int> seqs) {
      final ranges = <(int, int)>[];
      var start = seqs.first, prev = seqs.first;
      for (var i = 1; i < seqs.length; i++) {
        if (seqs[i] != prev + 1) {
          ranges.add((start, prev + 1));
          start = seqs[i];
        }
        prev = seqs[i];
      }
      ranges.add((start, prev + 1));
      return ranges;
    }

    // Flush exactly [chunkFrames] frames at a time; on DONE, flush whatever is left.
    Future<void> flushChunks({required bool finalFlush}) async {
      while (recordFrameCounts.isNotEmpty) {
        var framesToTake = 0;
        var recordsToTake = 0;
        for (var i = 0; i < recordFrameCounts.length; i++) {
          if (framesToTake >= chunkFrames && recordsToTake > 0) break;
          framesToTake += recordFrameCounts[i];
          recordsToTake++;
        }
        if (!finalFlush && framesToTake < chunkFrames) break;
        if (finalFlush && recordsToTake == 0 && bytesData.isEmpty) break;

        final chunkSeqs = recordSeqs.sublist(0, recordsToTake);
        final chunk = bytesData.sublist(0, framesToTake);
        final chunkTimerStart = (recordTimestamps.isNotEmpty && recordTimestamps.first > 0 && rtcValid)
            ? recordTimestamps.first
            : (firstRecordTs ?? DateTime.now().millisecondsSinceEpoch ~/ 1000) +
                bufferBaseElapsed ~/ (fps > 0 ? fps : 1);
        final flushStartedAt = DateTime.now().millisecondsSinceEpoch;
        try {
          if (chunk.isEmpty) {
            for (final s in chunkSeqs) {
              if (s == provenSeq) provenSeq = s + 1;
            }
            if (ringId != null && connection.ringCustodyEpoch == epoch) {
              for (final range in contiguousRanges(chunkSeqs)) {
                await _custody.recordDurableRingRange(custodyDeviceId, epoch, ringId, range.$1, range.$2, const []);
              }
            }
            recordSeqs.removeRange(0, recordsToTake);
            recordFrameCounts.removeRange(0, recordsToTake);
            recordTimestamps.removeRange(0, recordsToTake);
            bufferBaseElapsed = elapsedTotal - bytesData.length;
            if (finalFlush && recordFrameCounts.isEmpty) break;
            continue;
          }
          var bytes = 0;
          for (final f in chunk) {
            bytes += 4 + f.length;
          }
          final localSync = _localSync;
          if (localSync == null) {
            throw StateError('LocalWalSync unavailable; refusing release');
          }
          var admittedBytes = 0;
          try {
            final admitted = await localSync.ensureStorageAdmission(
              bytes: bytes,
              admittedGeneration: admittedGeneration,
            );
            if (!admitted) {
              throw StateError('storage admission refused (cap/disk reserve)');
            }
            admittedBytes = bytes;
            final file = await _flushToDisk(wal, chunk, chunkTimerStart);
            final localWal = await _registerWithLocalSync(wal, file, chunkTimerStart, chunk.length, admittedGeneration);
            admittedBytes = 0;
            if (!await localSync.hasDurableWal(localWal, admittedGeneration: admittedGeneration)) {
              throw StateError('WAL not durable after registration');
            }
            final fileBytes = await file.length();
            for (final s in chunkSeqs) {
              if (s == provenSeq) provenSeq = s + 1;
            }
            if (ringId != null && connection.ringCustodyEpoch == epoch) {
              for (final range in contiguousRanges(chunkSeqs)) {
                await _custody.recordDurableRingRange(custodyDeviceId, epoch, ringId, range.$1, range.$2, [
                  CustodyWalRef(fileName: file.path.split('/').last, bytes: fileBytes, frames: chunk.length),
                ]);
              }
            }
            DebugLogManager.logEvent('pendant_custody', {
              'action': 'chunk_durable',
              'device': custodyDeviceId,
              'ring_id': ringId,
              'start_seq': chunkSeqs.first,
              'end_seq': chunkSeqs.last + 1,
              'durable_flush_latency_ms': DateTime.now().millisecondsSinceEpoch - flushStartedAt,
            });
            recordSeqs.removeRange(0, recordsToTake);
            recordFrameCounts.removeRange(0, recordsToTake);
            recordTimestamps.removeRange(0, recordsToTake);
            bytesData.removeRange(0, framesToTake);
            bufferBaseElapsed = elapsedTotal - bytesData.length;
            final managerFrontier = ringId != null ? _custody.durableFrontierFor(custodyDeviceId, epoch) : null;
            if (managerFrontier != null && managerFrontier > provenSeq) provenSeq = managerFrontier;
            if (ringId != null && (effectiveCaps & RingProtocol.capAppAckReclaim) != 0) {
              final target = await _custody.validatedAdvanceTarget(custodyDeviceId, epoch, ringId);
              if (target != null) {
                await _custodyAdvance(connection, custodyDeviceId, epoch, target, ringId);
              }
            }
          } catch (e) {
            if (admittedBytes > 0) localSync.releaseStorageAdmission(admittedBytes);
            rethrow;
          }
        } catch (e) {
          Logger.debug('RingStorageSync._syncRing: flush error: $e');
          flushError = true;
          rethrow;
        }
        if (finalFlush && recordFrameCounts.isEmpty) break;
      }
    }

    await _notifyStream?.cancel();

    Future<void> notifyQueue = Future.value();
    bool beginAborted = false;

    Future<void> handleNotification(List<int> value) async {
      if (completer.isCompleted) return;
      if (_isCancelled) {
        if (!completer.isCompleted) completer.complete(false);
        return;
      }
      if (value.isEmpty) return;

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
        if (begin != null) {
          Logger.debug('RingStorageSync: NOTIFY_READ_BEGIN start=${begin.transferStartSeq} count=${begin.packetCount}');
          beginStartSeq = begin.transferStartSeq;
          beginPacketCount = begin.packetCount;
          if (!firstDataReceived) {
            firstDataReceived = true;
            firstDataTimer?.cancel();
          }
          if (beginStartSeq != readStart) {
            Logger.debug('RingStorageSync: READ_BEGIN start $beginStartSeq != requested $readStart — aborting');
            beginAborted = true;
            if (!completer.isCompleted) completer.complete(false);
          }
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
        Logger.debug('RingStorageSync: NOTIFY_DONE status=${done.status} next_seq=$doneNextSeq');
        if (!completer.isCompleted) completer.complete(true);
        return;
      }
      if (opcode == RingProtocol.notifyLiveMark) {
        return;
      }
      if (opcode != RingProtocol.notifyData) {
        Logger.debug('RingStorageSync: unknown notification opcode 0x${opcode.toRadixString(16)}');
        return;
      }

      // NOTIFY_DATA: append payload (skip the leading opcode byte) to the
      // reassembler. The firmware does NOT align chunks to record boundaries.
      final payload = value.sublist(1);
      if (!firstDataReceived) {
        firstDataReceived = true;
        firstDataTimer?.cancel();
      }
      reassembler.append(payload);
      _updateSpeed(payload.length);

      for (final record in reassembler.drainRecords()) {
        final seq = readStart + recordsConsumed;
        recordsConsumed += 1;
        final ts = RingProtocol.readRecordTimestamp(record);
        final audio = record.sublist(RingProtocol.timestampBytes);
        final frames = RingProtocol.parseAudioPayload(audio);
        elapsedTotal += frames.length;

        // Anchor timerStart on the first usable timestamp.
        if (firstRecordTs == null) {
          if (rtcValid && ts > 0) {
            firstRecordTs = ts;
          } else {
            // Fallback: now - estimated duration of the unread region.
            final estSecs = wal.totalFrames ~/ (fps == 0 ? 1 : fps);
            firstRecordTs = DateTime.now().millisecondsSinceEpoch ~/ 1000 - estSecs;
          }
        }

        if (await _custody.isDurableLiveRecord(custodyDeviceId, ringId, seq)) {
          skippedDuplicates++;
          if (seq == provenSeq) provenSeq = seq + 1;
          continue;
        }

        recordSeqs.add(seq);
        recordTimestamps.add(ts);
        recordFrameCounts.add(frames.length);
        bytesData.addAll(frames);
      }

      // Throttled progress update.
      final now = DateTime.now();
      if (now.difference(lastProgressUpdate) >= progressInterval) {
        lastProgressUpdate = now;
        if (wal.storageTotalBytes > 0) {
          final consumedBytes = recordsConsumed * RingProtocol.recordSize;
          final pct = (consumedBytes / wal.storageTotalBytes).clamp(0.0, 1.0);
          wal.deviceDownloadFraction = pct;
          progress?.onWalSyncedProgress(pct, speedKBps: _currentSpeedKBps, phase: SyncPhase.downloadingFromDevice);
        }
      }

      // Flush full chunks as we go (data safety: even if BLE drops mid-stream,
      // already-flushed chunks land in LocalWalSync and reach the cloud).
      //
      // Single in-flight flush at a time. flushChunks loops while bytesData
      // has >= chunkFrames, so additional NOTIFY_DATA arriving during a flush
      // are absorbed by the in-flight task's next iteration. Without this
      // guard, two concurrent flush closures would both read chunkTimerStart
      // before either updated it, producing overlapping timestamps in
      // LocalWalSync. We hold the Future so the post-DONE final flush can
      // await any flush still in flight before draining the tail.
      if (inFlightFlush == null && bytesData.length >= chunkFrames) {
        inFlightFlush = () async {
          try {
            await flushChunks(finalFlush: false);
          } catch (_) {
            if (!completer.isCompleted) completer.complete(false);
          } finally {
            inFlightFlush = null;
          }
        }();
      }
    }

    if (!stillEpoch()) return false;
    _notifyStream = await connection.getBleStorageBytesListener(
      onStorageBytesReceived: (List<int> value) {
        final snapshot = List<int>.of(value);
        notifyQueue = notifyQueue.then((_) => handleNotification(snapshot)).catchError((e) {
          Logger.debug('RingStorageSync: notification handler error: $e');
          if (!completer.isCompleted) completer.complete(false);
        });
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

    firstDataTimer = Timer(const Duration(seconds: 5), () {
      if (!firstDataReceived && !completer.isCompleted) {
        Logger.debug('RingStorageSync: no data within 5s');
        completer.completeError(TimeoutException('No data from device'));
      }
    });

    // Kick off the read. No packet_count = stream everything from read_seq.
    if (!stillEpoch()) {
      firstDataTimer.cancel();
      await _notifyStream?.cancel();
      _notifyStream = null;
      return false;
    }
    final readOk = await connection.readRingFromSeq(ringInfo.readSeq);
    if (!readOk) {
      firstDataTimer.cancel();
      await _notifyStream?.cancel();
      _notifyStream = null;
      throw Exception('Failed to send CMD_RING_READ');
    }

    Logger.debug(
      'RingStorageSync: reading from seq=${ringInfo.readSeq} (write=${ringInfo.writeSeq}, unread=${ringInfo.unreadPackets})',
    );

    bool reachedDone = false;
    bool stopSent = false;
    try {
      reachedDone = await completer.future.timeout(const Duration(minutes: 30));
    } on TimeoutException {
      Logger.debug('RingStorageSync: overall transfer timeout (30m)');
    } catch (e) {
      Logger.debug('RingStorageSync: transfer error: $e');
    } finally {
      firstDataTimer.cancel();
      if (_isCancelled || !(reachedDone && doneOk)) {
        await _stopRingTransfer(connection, epoch);
        stopSent = true;
      }
      await _notifyStream?.cancel();
      _notifyStream = null;
    }

    try {
      await notifyQueue;
    } catch (_) {}

    // Wait for any flush still in flight from the streaming phase before
    // draining the tail — otherwise the final flush could race the in-flight
    // one on bytesData and recordTimestamps.
    final pendingFlush = inFlightFlush;
    if (pendingFlush != null) {
      try {
        await pendingFlush;
      } catch (e) {
        Logger.debug('RingStorageSync: in-flight flush error during settle: $e');
      }
    }

    // Flush whatever frames are buffered, even on partial failure — those frames
    // are safe to upload to cloud regardless. ADVANCE is gated separately.
    try {
      await flushChunks(finalFlush: true);
    } catch (e) {
      Logger.debug('RingStorageSync: final flush error: $e');
    }

    final beginConsistent = !beginAborted &&
        (beginStartSeq == null ||
            (beginStartSeq == readStart && (beginPacketCount == null || beginPacketCount == recordsConsumed)));
    final doneConsistent = doneNextSeq != null &&
        doneNextSeq == readStart + recordsConsumed &&
        reassembler.pendingBytes == 0 &&
        beginConsistent;
    final fullyProven = doneNextSeq != null && provenSeq >= doneNextSeq!;
    final advancedOk = reachedDone && doneOk && !flushError && !_isCancelled && doneConsistent && fullyProven;
    if (advancedOk) {
      final ok = await _custodyAdvance(connection, custodyDeviceId, epoch, doneNextSeq!, ringId);
      Logger.debug('RingStorageSync: advance(seq=$doneNextSeq) -> $ok (records=$recordsConsumed)');
      DebugLogManager.logEvent('pendant_custody', {
        'action': 'sync_advance',
        'caps': effectiveCaps,
        'contract_version': ringInfo.contractVersion,
        'ring_id': ringId,
        'advance_lag_records': ringInfo.writeSeq - doneNextSeq!,
        'dropped_delta': droppedDelta,
        'records': recordsConsumed,
        'deduped': skippedDuplicates,
        'advance_ok': ok,
        'residual_legacy_risk': ringId == null,
      });
      return ok;
    } else {
      Logger.debug(
        'RingStorageSync: skipping advance (reachedDone=$reachedDone doneOk=$doneOk flushError=$flushError cancelled=$_isCancelled records=$recordsConsumed doneConsistent=$doneConsistent fullyProven=$fullyProven)',
      );
      if (!stopSent) await _stopRingTransfer(connection, epoch);
      return false;
    }
  }

  Future<void> _stopRingTransfer(DeviceConnection connection, int epoch) async {
    try {
      if (connection.ringCustodyEpoch != epoch) return;
      await connection.stopStorageSync();
      Logger.debug('RingStorageSync: STOP sent on the source connection');
    } catch (e) {
      Logger.debug('RingStorageSync: STOP failed: $e');
    }
  }

  Future<bool> _custodyAdvance(DeviceConnection connection, String deviceId, int epoch, int seq, int? ringId) async {
    if (connection.ringCustodyEpoch != epoch) return false;
    if (_custody.isIncarnationInvalid(deviceId, epoch)) return false;
    final ack = await connection.advanceRingCustody(seq, expectedEpoch: epoch, expectedRingId: ringId);
    if (ack == null) return false;
    if (ack.isOk) {
      await _custody.markAdvanced(deviceId, epoch, seq);
      return true;
    }
    if (ack.isSeqOutOfRange) {
      final info = await connection.getRingInfo();
      if (connection.ringCustodyEpoch != epoch || info == null) return false;
      _custody.noteInfo(deviceId, epoch, info);
      if ((ringId == null || info.ringId == ringId) && seq <= info.readSeq) {
        await _custody.markAdvanced(deviceId, epoch, seq);
        return true;
      }
      return false;
    }
    if (ack.isRingIdMismatch) {
      _custody.noteMismatch(deviceId, epoch);
      DebugLogManager.logWarning('pendant_custody ring_id mismatch; refusing release', {
        'action': 'advance_mismatch',
        'device': deviceId,
        'ring_id': ringIdOf(connection),
      });
    }
    return false;
  }

  static int? ringIdOf(DeviceConnection connection) => connection.lastRingInfo?.ringId;

  int _storageFileSeq = 0;

  /// Write opus frames to disk in WAL format: [frame_length_u32_le][frame_data]...
  /// Identical to StorageSyncImpl._flushToDisk for downstream compatibility.
  Future<File> _flushToDisk(Wal wal, List<List<int>> frames, int timerStart) async {
    final directory = await getApplicationDocumentsDirectory();
    var fileName = wal.getFileNameByTimeStarts(timerStart);
    if (await File('${directory.path}/$fileName').exists()) {
      final dot = fileName.lastIndexOf('.');
      final stem = dot > 0 ? fileName.substring(0, dot) : fileName;
      final ext = dot > 0 ? fileName.substring(dot) : '';
      do {
        fileName = '${stem}_u${_storageFileSeq++}$ext';
      } while (await File('${directory.path}/$fileName').exists());
    }
    final filePath = '${directory.path}/$fileName';

    final List<int> data = [];
    for (final frame in frames) {
      final byteFrame = ByteData(frame.length);
      for (int j = 0; j < frame.length; j++) {
        byteFrame.setUint8(j, frame[j]);
      }
      data.addAll(Uint32List.fromList([frame.length]).buffer.asUint8List());
      data.addAll(byteFrame.buffer.asUint8List());
    }

    final file = File(filePath);
    await file.writeAsBytes(data, flush: true);
    Logger.debug('RingStorageSync: wrote ${data.length}B (${frames.length} frames) to $filePath');
    return file;
  }

  Future<Wal> _registerWithLocalSync(Wal wal, File file, int timerStart, int frameCount, int admittedGeneration) async {
    final localSync = _localSync;
    if (localSync == null) {
      throw StateError('LocalWalSync unavailable; chunk cannot be proven durable');
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
    );

    await localSync.addExternalWal(localWal, admittedGeneration: admittedGeneration);
    Logger.debug('RingStorageSync: registered chunk (ts=$timerStart, ${seconds}s, $frameCount frames)');
    return localWal;
  }
}
