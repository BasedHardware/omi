import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';
import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/models/sync_state.dart';
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
///   0x04 DONE            [0x04][status][next_seq:u64 BE]
///   0x05 READ_BEGIN      [0x05][transfer_start_seq:u64 BE][packet_count:u32 BE]
///
/// Data-safety invariant: CMD_RING_ADVANCE is sent ONLY after NOTIFY_DONE arrives
/// AND every chunk we received during the transfer has been handed to LocalWalSync.
/// On any failure (cancel, BLE drop, NOTIFY_DONE error status) the ring is left
/// untouched — the next sync session resumes from the same read_seq.
class RingStorageSyncImpl implements RingStorageSync {
  List<Wal> _wals = const [];
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

  int _totalBytesDownloaded = 0;
  DateTime? _downloadStartTime;
  double _currentSpeedKBps = 0.0;
  @override
  double get currentSpeedKBps => _currentSpeedKBps;

  RingStorageSyncImpl(this.listener);

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

      // timerStart = 0 here; the per-record timestamp from the first NOTIFY_DATA
      // record will become the authoritative start time (or now-duration fallback
      // if status.rtcValid == 0).
      _wals = [
        Wal(
          codec: codec,
          timerStart: 0,
          status: WalStatus.miss,
          storage: WalStorage.sdcard,
          seconds: estimatedSecs,
          storageOffset: 0,
          storageTotalBytes: status.unreadPackets * RingProtocol.recordSize,
          fileNum: -1, // sentinel: ring has no file index
          device: _device!.id,
          deviceModel: deviceModel,
          totalFrames: estimatedFrames,
          syncedFrameOffset: 0,
        ),
      ];
      Logger.debug(
          'RingStorageSync.refreshWalsFromDevice: 1 virtual WAL (${status.unreadPackets} pkts, ~${estimatedSecs}s)');
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
    await _clearRingOnDevice();
    _wals = _wals.where((w) => w.status != WalStatus.miss).toList();
    listener.onWalUpdated();
  }

  Future<void> _clearRingOnDevice() async {
    if (_device == null) return;
    try {
      final connection = await ServiceManager.instance().device.ensureConnection(_device!.id);
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
  Future<SyncLocalFilesResponse?> syncAll({
    IWalSyncProgressListener? progress,
    IWifiConnectionListener? connectionListener,
  }) async {
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
          break;
        }
        wal.status = WalStatus.synced;
        listener.onWalUpdated();
      }
    } catch (e) {
      Logger.debug('RingStorageSync.syncAll: error: $e');
      DebugLogManager.logError(e, null, 'RingStorageSync failed', {'device': _device?.id});
    } finally {
      _isSyncing = false;
    }

    progress?.onWalSyncedProgress(1.0, speedKBps: _currentSpeedKBps);
    return resp;
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({
    required Wal wal,
    IWalSyncProgressListener? progress,
    IWifiConnectionListener? connectionListener,
  }) async {
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
    }
    return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
  }

  /// Pull the unread ring contents from the device, parse opus frames, register
  /// chunks with LocalWalSync, then advance the ring iff NOTIFY_DONE arrived.
  /// Returns true if the transfer ran to completion (DONE received and acted on).
  Future<bool> _syncRing(Wal wal, {IWalSyncProgressListener? progress}) async {
    if (_device == null) return false;
    final connection = await ServiceManager.instance().device.ensureConnection(_device!.id);
    if (connection == null) throw Exception('Device not connected');

    _activeSyncDeviceId = _device!.id;
    _downloadStartTime = DateTime.now();
    _totalBytesDownloaded = 0;

    // Snapshot ring state so we know what range we're consuming.
    final ringInfo = await connection.getRingInfo();
    if (ringInfo == null) {
      Logger.debug('RingStorageSync._syncRing: getRingInfo returned null');
      return false;
    }
    if (ringInfo.unreadPackets <= 0) {
      Logger.debug('RingStorageSync._syncRing: nothing to read');
      return true;
    }
    if (ringInfo.droppedPackets > 0) {
      DebugLogManager.logWarning(
        'RingStorageSync: ring overwrote ${ringInfo.droppedPackets} packets before sync',
        {'ringInfo': ringInfo.toString()},
      );
    }
    final status = await connection.getRingStatus();
    final rtcValid = status?.isRtcValid ?? false;

    final completer = Completer<bool>();
    final reassembler = RingRecordReassembler();
    final List<List<int>> bytesData = []; // parsed opus frames awaiting flush
    int recordsConsumed = 0;
    int? firstRecordTs;
    int chunkTimerStart = 0; // updated as chunks flush
    final fps = wal.codec.getFramesPerSecond();
    final chunkFrames = sdcardChunkSizeSecs * fps;
    int? doneNextSeq;
    bool doneOk = false;
    bool flushError = false;
    Future<void>? inFlightFlush;
    Timer? firstDataTimer;
    bool firstDataReceived = false;

    DateTime lastProgressUpdate = DateTime.now();
    const progressInterval = Duration(milliseconds: 200);

    // Flush exactly [chunkFrames] frames at a time; on DONE, flush whatever is left.
    Future<void> flushChunks({required bool finalFlush}) async {
      while (bytesData.length >= chunkFrames || (finalFlush && bytesData.isNotEmpty)) {
        final take = bytesData.length >= chunkFrames ? chunkFrames : bytesData.length;
        final chunk = bytesData.sublist(0, take);
        bytesData.removeRange(0, take);
        try {
          final file = await _flushToDisk(wal, chunk, chunkTimerStart);
          await _registerWithLocalSync(wal, file, chunkTimerStart, chunk.length);
        } catch (e) {
          Logger.debug('RingStorageSync._syncRing: flush error: $e');
          flushError = true;
          rethrow;
        }
        chunkTimerStart += chunk.length ~/ (fps == 0 ? 1 : fps);
        if (finalFlush && bytesData.isEmpty) break;
      }
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
            Logger.debug(
                'RingStorageSync: NOTIFY_READ_BEGIN start=${begin.transferStartSeq} count=${begin.packetCount}');
            if (!firstDataReceived) {
              firstDataReceived = true;
              firstDataTimer?.cancel();
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
          final ts = RingProtocol.readRecordTimestamp(record);

          // Anchor timerStart on the first usable timestamp.
          if (firstRecordTs == null) {
            if (rtcValid && ts > 0) {
              firstRecordTs = ts;
              chunkTimerStart = ts;
            } else {
              // Fallback: now - estimated duration of the unread region.
              final estSecs = wal.totalFrames ~/ (fps == 0 ? 1 : fps);
              firstRecordTs = DateTime.now().millisecondsSinceEpoch ~/ 1000 - estSecs;
              chunkTimerStart = firstRecordTs!;
            }
          }

          final audio = record.sublist(RingProtocol.timestampBytes);
          bytesData.addAll(RingProtocol.parseAudioPayload(audio));
          recordsConsumed += 1;
        }

        // Throttled progress update.
        final now = DateTime.now();
        if (now.difference(lastProgressUpdate) >= progressInterval) {
          lastProgressUpdate = now;
          if (wal.storageTotalBytes > 0) {
            final consumedBytes = recordsConsumed * RingProtocol.recordSize;
            final pct = (consumedBytes / wal.storageTotalBytes).clamp(0.0, 1.0);
            progress?.onWalSyncedProgress(
              pct,
              speedKBps: _currentSpeedKBps,
              phase: SyncPhase.downloadingFromDevice,
              currentFile: 1,
              totalFiles: 1,
            );
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
    final readOk = await connection.readRingFromSeq(ringInfo.readSeq);
    if (!readOk) {
      firstDataTimer.cancel();
      await _notifyStream?.cancel();
      _notifyStream = null;
      throw Exception('Failed to send CMD_RING_READ');
    }

    Logger.debug(
        'RingStorageSync: reading from seq=${ringInfo.readSeq} (write=${ringInfo.writeSeq}, unread=${ringInfo.unreadPackets})');

    bool reachedDone = false;
    try {
      reachedDone = await completer.future.timeout(const Duration(minutes: 30));
    } on TimeoutException {
      Logger.debug('RingStorageSync: overall transfer timeout (30m)');
    } catch (e) {
      Logger.debug('RingStorageSync: transfer error: $e');
    } finally {
      firstDataTimer.cancel();
      if (_isCancelled) {
        await _requestFirmwareStopSync();
      }
      await _notifyStream?.cancel();
      _notifyStream = null;
    }

    // Wait for any flush still in flight from the streaming phase before
    // draining the tail — otherwise the final flush could race the in-flight
    // one on bytesData and chunkTimerStart.
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

    final advancedOk = reachedDone && doneOk && !flushError && !_isCancelled && doneNextSeq != null;
    if (advancedOk) {
      final ok = await connection.advanceRing(doneNextSeq!);
      Logger.debug('RingStorageSync: advance(seq=$doneNextSeq) -> $ok (records=$recordsConsumed)');
      DebugLogManager.logEvent('ring_sync_advanced', {
        'records': recordsConsumed,
        'next_seq': doneNextSeq,
        'advance_ok': ok,
      });
      return ok;
    } else {
      Logger.debug(
          'RingStorageSync: skipping advance (reachedDone=$reachedDone doneOk=$doneOk flushError=$flushError cancelled=$_isCancelled records=$recordsConsumed)');
      return false;
    }
  }

  /// Write opus frames to disk in WAL format: [frame_length_u32_le][frame_data]...
  /// Identical to StorageSyncImpl._flushToDisk for downstream compatibility.
  Future<File> _flushToDisk(Wal wal, List<List<int>> frames, int timerStart) async {
    final directory = await getApplicationDocumentsDirectory();
    final filePath = '${directory.path}/${wal.getFileNameByTimeStarts(timerStart)}';

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
    await file.writeAsBytes(data);
    Logger.debug('RingStorageSync: wrote ${data.length}B (${frames.length} frames) to $filePath');
    return file;
  }

  Future<void> _registerWithLocalSync(Wal wal, File file, int timerStart, int frameCount) async {
    if (_localSync == null) {
      Logger.debug('RingStorageSync: WARNING - LocalWalSync not available, chunk will not be uploaded');
      return;
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

    await _localSync!.addExternalWal(localWal);
    Logger.debug('RingStorageSync: registered chunk (ts=$timerStart, ${seconds}s, $frameCount frames)');
  }
}
