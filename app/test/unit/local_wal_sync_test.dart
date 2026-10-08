import 'dart:io';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/wals/flash_page_wal_sync.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_batch.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

/// Minimal listener for testing — records calls without side effects.
class _MockListener implements IWalSyncListener {
  int walUpdatedCount = 0;
  final List<Wal> syncedWals = [];

  @override
  void onWalUpdated() {
    walUpdatedCount++;
  }

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {
    syncedWals.add(wal);
  }
}

void main() {
  late LocalWalSyncImpl sync;
  late _MockListener listener;

  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return Directory.systemTemp.path;
        return null;
      },
    );

    listener = _MockListener();
    sync = LocalWalSyncImpl(listener);
  });

  group('onFrameCaptured', () {
    test('adds frame with synced=false', () {
      final frame = WalFrame(payload: [0xAA, 0xBB], syncKey: FrameSyncKey([1]));

      sync.onFrameCaptured(frame);

      expect(sync.testFrames.length, 1);
      expect(sync.testFrames[0].payload, [0xAA, 0xBB]);
      expect(sync.testFrameSynced.length, 1);
      expect(sync.testFrameSynced[0], false);
    });

    test('capture root and ordinal survive WAL serialization', () async {
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      sync.onFrameCaptured(
        WalFrame(payload: [1], syncKey: FrameSyncKey([1])),
        captureRoot: 'root-a',
      );
      sync.onFrameCaptured(
        WalFrame(payload: [2], syncKey: FrameSyncKey([2])),
        captureRoot: 'root-a',
      );
      await sync.finalizeCurrentSession();

      final stored = Wal.fromJson(sync.testWals.single.toJson());
      expect(stored.captureRoot, 'root-a');
      expect(stored.sourceFrameStart, 0);
      expect(stored.sourceClockEpoch, 0);
      expect(Wal(timerStart: 0, codec: BleAudioCodec.opus, seconds: 0).toJson().containsKey('capture_root'), false);
      expect(stored.totalFrames, 2);
      sync.onFrameCaptured(
        WalFrame(payload: [3], syncKey: FrameSyncKey([3])),
        captureRoot: 'root-b',
      );
      expect(sync.testFrames.single.sourceFramePosition, 0);
      expect(sync.testFrames.single.sourceClockEpoch, 0);
    });

    test('socket and WAL receive the same allocated unit after reload', () async {
      const root = '12345678-1234-4234-8234-123456789abc';
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      final first = sync.onFrameCaptured(
        WalFrame(payload: [1], syncKey: FrameSyncKey([1])),
        captureRoot: root,
      );
      final second = sync.onFrameCaptured(
        WalFrame(payload: [2], syncKey: FrameSyncKey([2])),
        captureRoot: root,
      );
      expect((first.sourceFramePosition, second.sourceFramePosition), (0, 1));
      await sync.finalizeCurrentSession();
      final persisted = Wal.fromJson(sync.testWals.single.toJson());
      expect(persisted.sourceFrameStart, first.sourceFramePosition);

      final restored = LocalWalSyncImpl(listener)..testWals = [persisted];
      final next = restored.onFrameCaptured(
        WalFrame(payload: [3], syncKey: FrameSyncKey([3])),
        captureRoot: root,
      );
      expect(next.sourceFramePosition, 2);
      expect(next.sourceClockEpoch, persisted.sourceClockEpoch);
      await restored.onAudioCodecChanged(BleAudioCodec.pcm16);
      final changed = restored.onFrameCaptured(
        WalFrame(payload: [4], syncKey: FrameSyncKey([4])),
        captureRoot: root,
      );
      expect(changed.sourceClockEpoch, greaterThan(next.sourceClockEpoch!));
      expect(changed.sourceFramePosition, 0);
    });

    test('upload header is versioned and bounded only in dark-write builds', () {
      const root = '12345678-1234-4234-8234-123456789abc';
      final wal = Wal(
        timerStart: 1710000000,
        codec: BleAudioCodec.pcm16,
        seconds: 1,
        totalFrames: 100,
        sampleRate: 16000,
        captureRoot: root,
        sourceFrameStart: 42,
        sourceClockEpoch: 3,
      );
      final file = File('${Directory.systemTemp.path}/audio_phonemic_pcm16_16000_1_fs160_1710000000.bin');
      final header = captureEvidenceUploadHeader([wal], [file]);
      if (const bool.fromEnvironment('CAPTURE_EVIDENCE_V1_DARK_WRITE')) {
        final parsed = jsonDecode(header!) as Map<String, dynamic>;
        expect(parsed['version'], 1);
        expect((parsed['files'] as List).single['source_frame_start'], 42);
      } else {
        expect(header, isNull);
      }
    });

    test('preserves insertion order for multiple frames', () {
      for (int i = 0; i < 5; i++) {
        sync.onFrameCaptured(WalFrame(payload: [i], syncKey: FrameSyncKey([i])));
      }

      expect(sync.testFrames.length, 5);
      expect(sync.testFrameSynced.length, 5);
      for (int i = 0; i < 5; i++) {
        expect(sync.testFrames[i].payload, [i]);
        expect(sync.testFrameSynced[i], false);
      }
    });
  });

  group('markFrameSynced', () {
    test('marks matching frame as synced', () {
      final key = FrameSyncKey([0x10, 0x20, 0x30]);
      sync.onFrameCaptured(WalFrame(payload: [1], syncKey: key));

      sync.markFrameSynced(key);

      expect(sync.testFrameSynced[0], true);
    });

    test('marks only the last matching frame when duplicate keys exist', () {
      final key = FrameSyncKey([0x10]);

      // Add 3 frames with the same key
      sync.onFrameCaptured(WalFrame(payload: [1], syncKey: key));
      sync.onFrameCaptured(WalFrame(payload: [2], syncKey: key));
      sync.onFrameCaptured(WalFrame(payload: [3], syncKey: key));

      sync.markFrameSynced(key);

      // Only the last (index 2) should be marked
      expect(sync.testFrameSynced[0], false);
      expect(sync.testFrameSynced[1], false);
      expect(sync.testFrameSynced[2], true);
    });

    test('calling twice with same key marks two frames (reverse scan)', () {
      final key = FrameSyncKey([0x10]);

      sync.onFrameCaptured(WalFrame(payload: [1], syncKey: key));
      sync.onFrameCaptured(WalFrame(payload: [2], syncKey: key));
      sync.onFrameCaptured(WalFrame(payload: [3], syncKey: key));

      sync.markFrameSynced(key); // marks index 2
      sync.markFrameSynced(
        key,
      ); // marks index 1 (2 is already true, but reverse scan finds 2 first and breaks — so second call marks 2 again? No — it checks syncKey equality, not synced status)

      // Actually: markFrameSynced scans backward and breaks on FIRST syncKey match,
      // regardless of synced status. So second call marks index 2 again (already true).
      // Index 1 remains false.
      expect(sync.testFrameSynced[0], false);
      expect(sync.testFrameSynced[1], false);
      expect(sync.testFrameSynced[2], true);
    });

    test('no-op when key does not match any frame', () {
      final key1 = FrameSyncKey([0x10]);
      final key2 = FrameSyncKey([0x99]);

      sync.onFrameCaptured(WalFrame(payload: [1], syncKey: key1));

      // Mark with non-matching key — should not crash or change anything
      sync.markFrameSynced(key2);

      expect(sync.testFrameSynced[0], false);
    });

    test('no-op when frames list is empty', () {
      // Should not crash
      sync.markFrameSynced(FrameSyncKey([0x10]));
      expect(sync.testFrames, isEmpty);
    });

    test('correctly matches BLE-style 3-byte keys', () {
      final bleKey = FrameSyncKey.fromBleHeader([0x05, 0x00, 0x02, 0xFF, 0xFF]);

      sync.onFrameCaptured(WalFrame(payload: [1], syncKey: FrameSyncKey([0x05, 0x00, 0x01])));
      sync.onFrameCaptured(WalFrame(payload: [2], syncKey: bleKey));
      sync.onFrameCaptured(WalFrame(payload: [3], syncKey: FrameSyncKey([0x05, 0x00, 0x03])));

      sync.markFrameSynced(FrameSyncKey([0x05, 0x00, 0x02]));

      expect(sync.testFrameSynced[0], false);
      expect(sync.testFrameSynced[1], true);
      expect(sync.testFrameSynced[2], false);
    });

    test('correctly matches phone-mic-style 1-byte index keys', () {
      for (int i = 0; i < 5; i++) {
        sync.onFrameCaptured(WalFrame(payload: List.filled(320, i), syncKey: FrameSyncKey.fromIndex(i)));
      }

      sync.markFrameSynced(FrameSyncKey.fromIndex(3));

      for (int i = 0; i < 5; i++) {
        expect(sync.testFrameSynced[i], i == 3);
      }
    });
  });

  group('WAL binary serialization format', () {
    test('length-prefixed format with headerless payloads', () {
      // Simulate what _flush does: write [4-byte length][payload bytes]
      // Verify the format is correct when payloads have no firmware header
      final payloads = [
        [0xAA, 0xBB, 0xCC], // 3 bytes — pure audio, no header
        [0xDD, 0xEE], // 2 bytes
      ];

      // Reproduce the _flush serialization logic
      List<int> data = [];
      for (int i = 0; i < payloads.length; i++) {
        var frame = payloads[i];
        final byteFrame = ByteData(frame.length);
        for (int j = 0; j < frame.length; j++) {
          byteFrame.setUint8(j, frame[j]);
        }
        data.addAll(Uint32List.fromList([frame.length]).buffer.asUint8List());
        data.addAll(byteFrame.buffer.asUint8List());
      }

      // First frame: 4-byte length (3) + 3 payload bytes = 7 bytes
      expect(data.length, 4 + 3 + 4 + 2); // 13 bytes total

      // Verify first frame length prefix
      final len1 = ByteData.sublistView(Uint8List.fromList(data.sublist(0, 4))).getUint32(0, Endian.little);
      expect(len1, 3);
      expect(data.sublist(4, 7), [0xAA, 0xBB, 0xCC]);

      // Verify second frame length prefix
      final len2 = ByteData.sublistView(Uint8List.fromList(data.sublist(7, 11))).getUint32(0, Endian.little);
      expect(len2, 2);
      expect(data.sublist(11, 13), [0xDD, 0xEE]);
    });

    test('BLE payload stored without firmware header matches old sublist(3) behavior', () {
      // Old behavior: raw BLE packet stored in wal.data, then sublist(3) during flush
      final blePacket = [0x05, 0x00, 0x02, ...List.filled(80, 0xAA)];
      final oldFlushPayload = blePacket.sublist(3);

      // New behavior: BleDeviceSource strips header, payload stored directly
      // _flush writes wal.data[i] (already headerless) — no sublist(3)
      final newStorePayload = blePacket.sublist(3); // what BleDeviceSource.processBytes returns

      // Serialization of both should be identical
      List<int> serialize(List<int> payload) {
        List<int> data = [];
        final byteFrame = ByteData(payload.length);
        for (int j = 0; j < payload.length; j++) {
          byteFrame.setUint8(j, payload[j]);
        }
        data.addAll(Uint32List.fromList([payload.length]).buffer.asUint8List());
        data.addAll(byteFrame.buffer.asUint8List());
        return data;
      }

      expect(serialize(newStorePayload), equals(serialize(oldFlushPayload)));
      expect(newStorePayload.length, 80);
    });

    test('phone mic frames stored at correct size in WAL format', () {
      // Phone mic produces 320-byte PCM frames — stored directly
      final micPayload = List.filled(320, 0x42);

      List<int> data = [];
      final byteFrame = ByteData(micPayload.length);
      for (int j = 0; j < micPayload.length; j++) {
        byteFrame.setUint8(j, micPayload[j]);
      }
      data.addAll(Uint32List.fromList([micPayload.length]).buffer.asUint8List());
      data.addAll(byteFrame.buffer.asUint8List());

      // 4-byte length + 320 payload bytes
      expect(data.length, 324);

      final storedLen = ByteData.sublistView(Uint8List.fromList(data.sublist(0, 4))).getUint32(0, Endian.little);
      expect(storedLen, 320);
      expect(data.sublist(4), micPayload);
    });
  });

  group('upload batching', () {
    test('newest first, one conversation per batch', () {
      const now = 2000000000;
      final oldNewest = Wal(timerStart: now - 7 * 60 * 60, codec: BleAudioCodec.opus, seconds: 60);
      final liveOlder = Wal(
        timerStart: now - 120,
        codec: BleAudioCodec.opus,
        seconds: 60,
        conversationId: 'server-conversation',
      );
      final oldOldest = Wal(timerStart: now - 8 * 24 * 60 * 60, codec: BleAudioCodec.opus, seconds: 60);
      final liveNewest = Wal(
        timerStart: now - 30,
        codec: BleAudioCodec.opus,
        seconds: 60,
        conversationId: 'server-conversation',
      );

      final batch = nextSyncUploadBatch([oldNewest, liveOlder, oldOldest, liveNewest], now);

      expect(batch.map((wal) => wal.timerStart), [liveNewest.timerStart, liveOlder.timerStart]);
    });

    test('does not mix safety WALs from different recording sessions', () {
      const now = 2000000000;
      final newest = Wal(
        timerStart: now - 30,
        codec: BleAudioCodec.opus,
        seconds: 60,
        recordingSessionId: 'recording-b',
      );
      final olderSame = Wal(
        timerStart: now - 90,
        codec: BleAudioCodec.opus,
        seconds: 60,
        recordingSessionId: 'recording-b',
      );
      final otherRecording = Wal(
        timerStart: now - 20,
        codec: BleAudioCodec.opus,
        seconds: 60,
        recordingSessionId: 'recording-a',
      );

      final batch = nextSyncUploadBatch([otherRecording, newest, olderSame], now);

      expect(batch.map((wal) => wal.recordingSessionId), ['recording-a']);
    });

    test('recent ID-less WAL counts as live capture but cannot claim an existing manifest', () {
      const now = 2000000000;
      Wal at(int ageSeconds, {String? conversationId}) =>
          Wal(timerStart: now - ageSeconds, codec: BleAudioCodec.opus, seconds: 60, conversationId: conversationId);

      final idLess = at(60);
      expect(isLiveCaptureWal(idLess, now), isTrue);
      expect(canClaimLiveCapture([idLess], [idLess], now), isFalse);
      expect(isLiveCaptureWal(at(60, conversationId: 'c'), now), isTrue);
      expect(isLiveCaptureWal(at(7 * 60 * 60, conversationId: 'c'), now), isFalse);
    });

    test('a backlog smaller than the limit drains in one batch', () {
      const now = 2000000000;
      final historical = List.generate(
        3,
        (index) => Wal(timerStart: now - 7 * 60 * 60 - index, codec: BleAudioCodec.opus, seconds: 60),
      );

      final batch = nextSyncUploadBatch(historical.reversed.toList(), now);

      expect(batch.length, 3);
    });

    test('a batch never exceeds the limit that keeps a job inside the backend stale guard', () {
      const now = 2000000000;
      final historical = List.generate(
        25,
        (index) => Wal(timerStart: now - 7 * 60 * 60 - index, codec: BleAudioCodec.opus, seconds: 60),
      );

      final batch = nextSyncUploadBatch(historical.reversed.toList(), now);

      expect(batch.length, 5);
      expect(batch.map((wal) => wal.timerStart), historical.take(5).map((wal) => wal.timerStart));
    });

    test('historical WALs with different recording locations are never uploaded as one conversation batch', () {
      const now = 2000000000;
      final firstCapture = Geolocation(
        latitude: 40.7128,
        longitude: -74.0060,
        time: DateTime.utc(2033, 5, 18, 3, 30),
        captureSource: 'current_position',
      );
      final secondCapture = Geolocation(
        latitude: 34.0522,
        longitude: -118.2437,
        time: DateTime.utc(2033, 5, 18, 4, 30),
        captureSource: 'current_position',
      );
      final wals = [
        Wal(timerStart: now - 7 * 60 * 60, codec: BleAudioCodec.opus, seconds: 60, geolocation: firstCapture),
        Wal(timerStart: now - 7 * 60 * 60 - 60, codec: BleAudioCodec.opus, seconds: 60, geolocation: firstCapture),
        Wal(timerStart: now - 8 * 60 * 60, codec: BleAudioCodec.opus, seconds: 60, geolocation: secondCapture),
      ];

      final batch = nextSyncUploadBatch(wals, now);

      expect(batch, hasLength(2));
      expect(batch.every((wal) => identical(wal.geolocation, firstCapture)), isTrue);
    });

    test('a conversation too large for one batch does not claim a manifest', () {
      const now = 2000000000;
      final oversized = List.generate(
        6,
        (index) => Wal(
          timerStart: now - index,
          codec: BleAudioCodec.opus,
          seconds: 60,
          conversationId: 'oversized-conversation',
        ),
      );

      final batch = nextSyncUploadBatch(oversized, now);

      expect(batch.length, 5);
      expect(canClaimLiveCapture(batch, oversized, now), isFalse);
      expect(canClaimLiveCapture(batch, oversized.take(5).toList(), now), isTrue);
    });
  });

  group('bounded retained capture WALs', () {
    Wal retained(int timerStart) => Wal(
          timerStart: timerStart,
          codec: BleAudioCodec.opus,
          seconds: 60,
          storage: WalStorage.disk,
          status: WalStatus.miss,
        );

    test('the count cap warns at the boundary but never deletes pending WALs', () async {
      sync.testWals = List.generate(maxRetainedCaptureWalCount, retained);

      final excess = await sync.enforceRetentionPolicyForTesting();

      expect(excess, 0);
      expect(sync.testWals, hasLength(maxRetainedCaptureWalCount));
      expect(sync.retentionRisk?.reason, 'count_cap');
      expect(sync.retentionRisk?.retainedCount, maxRetainedCaptureWalCount);
    });

    test('dead-backend accumulation never deletes and never refuses new audio for count', () async {
      final sync = LocalWalSyncImpl(listener, freeDiskBytes: () async => 64 << 30);
      sync.testWals = List.generate(maxRetainedCaptureWalCount + 3, retained);

      final excess = await sync.enforceRetentionPolicyForTesting();

      expect(excess, 3);
      // No eviction: every pending WAL stays on disk/index.
      expect(sync.testWals, hasLength(maxRetainedCaptureWalCount + 3));
      expect(sync.retentionRisk?.retainedCount, maxRetainedCaptureWalCount + 3);
      // Over the count threshold is a warning only: with disk to spare, new audio is still admitted.
      expect(await sync.ensureStorageAdmission(bytes: 1024, admittedGeneration: sync.sessionGeneration), isTrue);
      expect(sync.retentionRisk?.reason, 'count_cap');
    });

    test('admission refuses when free space would breach the 512MiB reserve', () async {
      const reserve = minFreeDiskReserveBytes;
      final low = LocalWalSyncImpl(listener, freeDiskBytes: () async => reserve + 512);
      expect(await low.ensureStorageAdmission(bytes: 1024, admittedGeneration: low.sessionGeneration), isFalse);
      expect(low.retentionRisk?.reason, 'disk_reserve');
      final ok = LocalWalSyncImpl(listener, freeDiskBytes: () async => reserve + 4096);
      expect(await ok.ensureStorageAdmission(bytes: 1024, admittedGeneration: ok.sessionGeneration), isTrue);
    });

    test('admission fails closed when free space cannot be proven', () async {
      final unknown = LocalWalSyncImpl(listener, freeDiskBytes: () async => null);
      expect(await unknown.ensureStorageAdmission(bytes: 16, admittedGeneration: unknown.sessionGeneration), isFalse);
      expect(unknown.retentionRisk?.reason, 'disk_space_unknown');
    });
  });

  group('synced-copy auto-remove (expired synced retention)', () {
    Wal syncedCopy({
      required int syncedAt,
      WalStatus status = WalStatus.synced,
      WalStorage storage = WalStorage.disk,
    }) =>
        Wal(
          timerStart: syncedAt - 1000,
          codec: BleAudioCodec.opus,
          seconds: 60,
          storage: storage,
          status: status,
          syncedAt: syncedAt,
        );

    test('removes synced disk copies past the retention window and keeps the rest', () async {
      SharedPreferencesUtil().autoRemoveSyncedCopies = true;
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final old = syncedCopy(syncedAt: now - 31 * Duration.secondsPerDay);
      final fresh = syncedCopy(syncedAt: now - 3600);
      sync.testWals = [old, fresh];

      final removed = await sync.enforceSyncedCopyRetentionForTesting();

      expect(removed, 1);
      expect(sync.testWals.map((wal) => wal.id), contains(fresh.id));
      expect(sync.testWals.map((wal) => wal.id), isNot(contains(old.id)));
    });

    test('never removes synced copies with an unknown sync time (syncedAt == 0)', () async {
      SharedPreferencesUtil().autoRemoveSyncedCopies = true;
      final legacy = Wal(
        timerStart: DateTime.now().millisecondsSinceEpoch ~/ 1000 - 400 * Duration.secondsPerDay,
        codec: BleAudioCodec.opus,
        seconds: 60,
        storage: WalStorage.disk,
        status: WalStatus.synced,
        syncedAt: 0,
      );
      sync.testWals = [legacy];

      final removed = await sync.enforceSyncedCopyRetentionForTesting();

      expect(removed, 0);
      expect(sync.testWals, hasLength(1));
    });

    test('removes nothing when the preference is off', () async {
      SharedPreferencesUtil().autoRemoveSyncedCopies = false;
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final old = syncedCopy(syncedAt: now - 400 * Duration.secondsPerDay);
      sync.testWals = [old];

      final removed = await sync.enforceSyncedCopyRetentionForTesting();

      expect(removed, 0);
      expect(sync.testWals, hasLength(1));
    });

    test('only ever touches synced disk WALs', () async {
      SharedPreferencesUtil().autoRemoveSyncedCopies = true;
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final oldSyncedMem = syncedCopy(syncedAt: now - 400 * Duration.secondsPerDay, storage: WalStorage.mem);
      final oldPending = syncedCopy(syncedAt: now - 400 * Duration.secondsPerDay, status: WalStatus.miss);
      sync.testWals = [oldSyncedMem, oldPending];

      final removed = await sync.enforceSyncedCopyRetentionForTesting();

      expect(removed, 0);
      expect(sync.testWals, hasLength(2));
    });

    test('never touches synced sdcard or pendant flash copies however old', () async {
      SharedPreferencesUtil().autoRemoveSyncedCopies = true;
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final oldSd = syncedCopy(syncedAt: now - 400 * Duration.secondsPerDay, storage: WalStorage.sdcard);
      final oldFlash = syncedCopy(syncedAt: now - 400 * Duration.secondsPerDay, storage: WalStorage.flashPage);
      sync.testWals = [oldSd, oldFlash];

      final removed = await sync.enforceSyncedCopyRetentionForTesting();

      expect(removed, 0);
      expect(sync.testWals, hasLength(2));
    });

    test('honors a non-default retention window', () async {
      SharedPreferencesUtil().autoRemoveSyncedCopies = true;
      SharedPreferencesUtil().autoRemoveSyncedCopiesDays = 7;
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final eightDaysOld = syncedCopy(syncedAt: now - 8 * Duration.secondsPerDay);
      final fiveDaysOld = syncedCopy(syncedAt: now - 5 * Duration.secondsPerDay);
      sync.testWals = [eightDaysOld, fiveDaysOld];

      final removed = await sync.enforceSyncedCopyRetentionForTesting();

      expect(removed, 1);
      expect(sync.testWals, [fiveDaysOld]);
    });

    test('streamed WALs born synced (all frames acked) carry syncedAt == 0', () async {
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      final key = FrameSyncKey([0x77]);
      sync.onFrameCaptured(WalFrame(payload: [1], syncKey: key));
      sync.markFrameSynced(key);
      await sync.finalizeCurrentSession();

      final wal = sync.testWals.single;
      expect(wal.status, WalStatus.synced);
      // Socket-send bookkeeping is transport, not server confirmation, so the
      // retention clock must NOT start: only server-confirmed transitions
      // (upload fast-path / reconciler) stamp syncedAt. The transcript
      // acknowledgement flow owns this copy's lifecycle instead.
      expect(wal.syncedAt, 0);
    });
  });

  group('audio_player_utils temp file serialization (no double-strip)', () {
    test('headerless payloads are serialized without extra sublist(3)', () {
      // Simulate a Wal with headerless payloads (as now stored by _chunk)
      final headerlessPayloads = [
        [0xAA, 0xBB, 0xCC, 0xDD], // 4 bytes of pure audio
        [0x11, 0x22, 0x33], // 3 bytes of pure audio
      ];

      // This is the FIXED audio_player_utils._createTempFileFromMemoryData logic:
      // var frame = wal.data[i]; (no sublist(3))
      List<int> fixedData = [];
      for (int i = 0; i < headerlessPayloads.length; i++) {
        var frame = headerlessPayloads[i]; // FIXED: direct access
        final byteFrame = ByteData(frame.length);
        for (int j = 0; j < frame.length; j++) {
          byteFrame.setUint8(j, frame[j]);
        }
        fixedData.addAll(Uint32List.fromList([frame.length]).buffer.asUint8List());
        fixedData.addAll(byteFrame.buffer.asUint8List());
      }

      // Verify first frame is fully preserved
      final len1 = ByteData.sublistView(Uint8List.fromList(fixedData.sublist(0, 4))).getUint32(0, Endian.little);
      expect(len1, 4); // Full 4-byte payload
      expect(fixedData.sublist(4, 8), [0xAA, 0xBB, 0xCC, 0xDD]);

      // Verify second frame is fully preserved
      final len2 = ByteData.sublistView(Uint8List.fromList(fixedData.sublist(8, 12))).getUint32(0, Endian.little);
      expect(len2, 3); // Full 3-byte payload
      expect(fixedData.sublist(12, 15), [0x11, 0x22, 0x33]);
    });

    test('old buggy sublist(3) would corrupt headerless payloads', () {
      // Demonstrate the bug that was fixed: applying sublist(3) to
      // already-headerless payloads truncates audio data
      final headerlessPayload = [0xAA, 0xBB, 0xCC, 0xDD]; // 4 bytes

      // OLD buggy code: wal.data[i].sublist(3) on headerless payload
      final buggyResult = headerlessPayload.sublist(3);
      expect(buggyResult, [0xDD]); // Lost 3 bytes of audio!

      // FIXED code: wal.data[i] directly
      final fixedResult = headerlessPayload;
      expect(fixedResult, [0xAA, 0xBB, 0xCC, 0xDD]); // All audio preserved
      expect(fixedResult.length, buggyResult.length + 3); // 3 bytes recovered
    });
  });

  group('session lifecycle (production)', () {
    test('setDeviceInfo updates metadata without error', () {
      sync.setDeviceInfo('phone-mic', 'Phone Microphone');
      // Just verify no crash — metadata used during WAL creation
    });

    test('frames and synced arrays stay in sync after mixed operations', () {
      // Add 3 frames
      sync.onFrameCaptured(WalFrame(payload: [1], syncKey: FrameSyncKey([0])));
      sync.onFrameCaptured(WalFrame(payload: [2], syncKey: FrameSyncKey([1])));
      sync.onFrameCaptured(WalFrame(payload: [3], syncKey: FrameSyncKey([2])));

      // Mark middle frame synced
      sync.markFrameSynced(FrameSyncKey([1]));

      // Verify parallel arrays stay consistent
      expect(sync.testFrames.length, 3);
      expect(sync.testFrameSynced.length, 3);
      expect(sync.testFrameSynced[0], false);
      expect(sync.testFrameSynced[1], true);
      expect(sync.testFrameSynced[2], false);
    });

    test('phone mic frames with wrapping index keys', () {
      // Simulate phone mic producing 256+ frames (index wraps at 255)
      for (int i = 0; i < 260; i++) {
        sync.onFrameCaptured(WalFrame(payload: List.filled(320, i & 0xFF), syncKey: FrameSyncKey.fromIndex(i)));
      }

      expect(sync.testFrames.length, 260);

      // Mark frame index 3 (appears at position 3 and 259 due to wrapping)
      // Reverse scan finds position 259 first
      sync.markFrameSynced(FrameSyncKey.fromIndex(3));
      expect(sync.testFrameSynced[3], false); // Not this one
      expect(sync.testFrameSynced[259], true); // This one (last match)
    });

    test('each finalized WAL owns an independent location snapshot', () async {
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      final location = Geolocation(
        latitude: 40.7128,
        longitude: -74.006,
        time: DateTime.utc(2026, 8, 1, 12),
        captureSource: 'current_position',
      );
      sync.setSessionGeolocation(location);
      location.latitude = 41.0;

      sync.onFrameCaptured(WalFrame(payload: [1], syncKey: FrameSyncKey([1])));
      await sync.finalizeCurrentSession();

      sync.onFrameCaptured(WalFrame(payload: [2], syncKey: FrameSyncKey([2])));
      await sync.finalizeCurrentSession();

      expect(sync.testWals, hasLength(2));
      expect(sync.testWals[0].geolocation?.latitude, 40.7128);
      expect(sync.testWals[1].geolocation?.latitude, 40.7128);

      sync.testWals[0].geolocation!.latitude = 42.0;
      expect(sync.testWals[1].geolocation?.latitude, 40.7128);
    });

    test('a finalized safety WAL carries the active recording session id', () async {
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      sync.setActiveRecordingSessionId('  recording-live  ');
      sync.onFrameCaptured(WalFrame(payload: [1], syncKey: FrameSyncKey([1])));

      await sync.finalizeCurrentSession();

      expect(sync.testWals, hasLength(1));
      expect(sync.testWals.single.recordingSessionId, 'recording-live');
      final encoded = sync.testWals.single.toJson();
      expect(encoded['recording_session_id'], 'recording-live');
      final restored = Wal.fromJson({...encoded, 'codec': 'opus'});
      expect(restored.recordingSessionId, 'recording-live');
    });

    test('stampConversationId follows the recording id when timerStart is before the session', () async {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      sync.testWals = [
        Wal(
          timerStart: now - 200,
          codec: BleAudioCodec.opus,
          seconds: 60,
          status: WalStatus.miss,
          storage: WalStorage.disk,
          recordingSessionId: 'recording-live',
        ),
        Wal(
          timerStart: now - 180,
          codec: BleAudioCodec.opus,
          seconds: 60,
          status: WalStatus.miss,
          storage: WalStorage.disk,
          recordingSessionId: 'recording-other',
        ),
      ];

      sync.prepareConversationStamp('recording-live');
      await sync.stampConversationId(now - 100, 'conv-live');

      expect(sync.testWals[0].conversationId, 'conv-live');
      expect(sync.testWals[1].conversationId, isNull);
    });

    test('cleared session location is not inherited by external WALs', () async {
      sync.setSessionGeolocation(
        Geolocation(latitude: 40.7128, longitude: -74.006, time: DateTime.utc(2026, 8, 1, 12)),
      );
      sync.setSessionGeolocation(null);

      final wal = Wal(timerStart: DateTime.now().millisecondsSinceEpoch ~/ 1000, codec: BleAudioCodec.opus, seconds: 1);
      await sync.addExternalWal(wal, admittedGeneration: sync.sessionGeneration);

      expect(wal.geolocation, isNull);
    });
  });

  group('_chunk payload extraction', () {
    test('WalFrame.payload is used for Wal.data (not raw bytes)', () {
      // Simulate what _chunk does: extract payloads from WalFrames
      final frames = [
        WalFrame(payload: [0xAA, 0xBB], syncKey: FrameSyncKey([1])),
        WalFrame(payload: [0xCC, 0xDD], syncKey: FrameSyncKey([2])),
        WalFrame(payload: [0xEE, 0xFF], syncKey: FrameSyncKey([3])),
      ];

      // This is the exact expression from _chunk:
      final chunk = frames.map((f) => f.payload).toList();

      expect(chunk.length, 3);
      expect(chunk[0], [0xAA, 0xBB]);
      expect(chunk[1], [0xCC, 0xDD]);
      expect(chunk[2], [0xEE, 0xFF]);

      // Sync keys are NOT included in the chunk data
      for (final payload in chunk) {
        expect(payload.length, 2);
      }
    });

    test('BLE frames have header stripped before chunk storage', () {
      // Raw BLE packet: 3-byte header + audio
      final blePacket = [0x05, 0x00, 0x02, 0xAA, 0xBB, 0xCC];

      // BleDeviceSource strips header
      final payload = blePacket.sublist(3); // [0xAA, 0xBB, 0xCC]
      final frame = WalFrame(payload: payload, syncKey: FrameSyncKey.fromBleHeader(blePacket));

      // _chunk stores payload only
      final chunk = [frame].map((f) => f.payload).toList();
      expect(chunk[0], [0xAA, 0xBB, 0xCC]);

      // No firmware header in stored data
      expect(chunk[0].length, 3);
      expect(chunk[0][0], 0xAA); // First byte is audio, not header
    });
  });

  group('WAL lists are growable (regression: Cannot add to an unmodifiable list)', () {
    // Crash: LocalWalSyncImpl._chunk called wal.data.addAll(chunk) on a WAL
    // loaded from disk. Wal.fromJson never passed `data`, so the constructor
    // default `const []` left an unmodifiable list that threw on addAll.
    test('Wal.fromJson produces a growable data list that _chunk can append to', () {
      final wal = Wal.fromJson({
        'timer_start': 1700000000,
        'codec': 'opus',
        'seconds': 60,
        'status': 'miss',
        'storage': 'disk',
      });

      // The exact operation from _chunk that crashed in production:
      wal.data.addAll([
        [0xAA, 0xBB],
        [0xCC, 0xDD],
      ]);

      expect(wal.data.length, 2);
    });

    test('Wal constructed without data has a growable data list', () {
      final wal = Wal(timerStart: 1700000000, codec: BleAudioCodec.opus, seconds: 60);

      wal.data.add([0x01]);

      expect(wal.data, [
        [0x01],
      ]);
    });

    test('addExternalWal before _initializeWals completes does not throw on _wals', () async {
      // Same failure class: `_wals = const []` was unmodifiable until
      // _initializeWals replaced it, so an early addExternalWal crashed.
      final freshListener = _MockListener();
      final freshSync = LocalWalSyncImpl(freshListener);
      // Old timerStart → backfill lane, so no fresh-upload network call runs.
      final wal = Wal(timerStart: 1000, codec: BleAudioCodec.opus, seconds: 60);

      await freshSync.addExternalWal(wal, admittedGeneration: freshSync.sessionGeneration);

      expect(freshSync.testWals.map((w) => w.id), contains(wal.id));
    });
  });

  group('silent upload death recovery', () {
    test('connectivity recovery re-arms only retry-exhausted transient disk WALs', () async {
      var persisted = <Wal>[];
      final local = LocalWalSyncImpl(
        listener,
        persistWals: (wals) async => persisted = List<Wal>.from(wals),
        loadWals: () async => <Wal>[],
      );
      final exhausted = Wal(
        timerStart: 100,
        codec: BleAudioCodec.opus,
        seconds: 60,
        storage: WalStorage.disk,
        status: WalStatus.miss,
        retryCount: walMaxAutoRetries,
        lastRetryAt: 99,
      );
      final stillBudgeted = Wal(
        timerStart: 200,
        codec: BleAudioCodec.opus,
        seconds: 60,
        storage: WalStorage.disk,
        status: WalStatus.miss,
        retryCount: 2,
      );
      final permanent = Wal(
        timerStart: 300,
        codec: BleAudioCodec.opus,
        seconds: 60,
        storage: WalStorage.disk,
        status: WalStatus.unsupportedAudio,
        retryCount: walMaxAutoRetries,
      );
      local.testWals = [exhausted, stillBudgeted, permanent];

      expect(await local.resetExhaustedAutoRetries(), 1);

      expect(exhausted.retryCount, 0);
      expect(exhausted.lastRetryAt, 0);
      expect(stillBudgeted.retryCount, 2);
      expect(permanent.retryCount, walMaxAutoRetries);
      expect(persisted.map((wal) => wal.id), containsAll([exhausted.id, stillBudgeted.id, permanent.id]));
    });
  });

  group('transcript coverage confirmation — fail closed', () {
    late Directory directory;

    setUp(() async {
      directory = await Directory.systemTemp.createTemp('wal_coverage_');
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        (MethodCall call) async {
          if (call.method == 'getApplicationDocumentsDirectory') return directory.path;
          return null;
        },
      );
    });

    tearDown(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        null,
      );
      if (directory.existsSync()) directory.deleteSync(recursive: true);
    });

    Wal stamped(
      int timerStart, {
      int seconds = 60,
      int totalFrames = 0,
      String? conversationId = 'c1',
      String? filePath,
      WalStatus status = WalStatus.miss,
      int syncedAt = 0,
      bool isSyncing = false,
    }) {
      final wal = Wal(
        timerStart: timerStart,
        codec: BleAudioCodec.opus,
        seconds: seconds,
        totalFrames: totalFrames,
        storage: WalStorage.disk,
        status: status,
        syncedAt: syncedAt,
        conversationId: conversationId,
        filePath: filePath,
      );
      wal.isSyncing = isSyncing;
      return wal;
    }

    LocalWalSyncImpl build({
      List<Map<String, Object?>>? telemetry,
      List<Wal>? persistedSink,
      Future<void> Function(List<Wal>)? persist,
      SyncUploadGate? uploadGate,
      DateTime? now,
    }) =>
        LocalWalSyncImpl(
          listener,
          now: now == null ? null : () => now,
          persistWals: persist ??
              (wals) async {
                if (persistedSink != null) {
                  persistedSink
                    ..clear()
                    ..addAll(wals);
                }
              },
          loadWals: () async => <Wal>[],
          uploadGate: uploadGate,
          coverageTelemetry: telemetry?.add,
        );

    SyncUploadGate succeedingGate({List<List<String>>? attempted, UploadFilesResult Function()? outcome}) =>
        SyncUploadGate(
          limiter: SyncRateLimiter.instance,
          uploader: (
            files, {
            onUploadProgress,
            conversationId,
            captureEvidence,
            recordingSessionId,
            audioStartSeconds,
            audioEndSeconds,
            claimLiveCapture = false,
            geolocation,
          }) async {
            attempted?.add(files.map((f) => f.path.split(Platform.pathSeparator).last).toList());
            return outcome?.call() ??
                UploadFilesResult.done(
                  SyncLocalFilesResponse(newConversationIds: ['c1'], updatedConversationIds: []),
                );
          },
          fairUseStatusLoader: () async => null,
        );

    test('stamped WALs stay when there is no coverage evidence', () async {
      final persisted = <Wal>[];
      final local = build(persistedSink: persisted);
      final confirmed = stamped(450, seconds: 30, conversationId: 'confirmed-conversation');
      final unrelated = stamped(460, seconds: 30, conversationId: 'other-conversation');
      final unstamped = stamped(470, seconds: 30, conversationId: null);
      local.testWals = [confirmed, unrelated, unstamped];

      final outcome = await local.confirmSessionTranscription(400, 'confirmed-conversation');

      expect(outcome.released, 0);
      expect(outcome.kept, 1);
      expect(confirmed.keptForTranscriptRecovery, isTrue);
      expect(unrelated.keptForTranscriptRecovery, isFalse);
      expect(local.testWals, containsAll([confirmed, unrelated, unstamped]));
      expect(persisted.map((wal) => wal.id), containsAll([confirmed.id, unrelated.id, unstamped.id]));
      expect(persisted.firstWhere((wal) => wal.id == confirmed.id).keptForTranscriptRecovery, isTrue);
    });

    test('confirmation retains only the WALs trusted absolute spans fully cover', () async {
      final now = DateTime.fromMillisecondsSinceEpoch(1000 * 1000);
      final persisted = <Wal>[];
      final local = build(now: now, persistedSink: persisted);
      // Session window starts at 500; the conversation starts at 520.
      final backdated = stamped(470);
      final spoken = stamped(530);
      final lost = stamped(590);
      final ending = stamped(650);
      local.testWals = [backdated, spoken, lost, ending];

      final outcome = await local.confirmSessionTranscription(
        500,
        'c1',
        transcriptSpans: [(527, 652)],
        conversationStartSeconds: 520,
      );

      expect(outcome.released, 0);
      expect(outcome.kept, 2);
      expect(local.testWals, hasLength(4), reason: 'coverage suppresses the repair upload — it never deletes the copy');
      for (final wal in [spoken, lost]) {
        expect(wal.status, WalStatus.synced);
        expect(wal.syncedAt, 1000);
        expect(wal.keptForTranscriptRecovery, isFalse);
      }
      for (final wal in [backdated, ending]) {
        expect(wal.status, WalStatus.miss);
        expect(wal.keptForTranscriptRecovery, isTrue);
      }
      expect(
        persisted.firstWhere((wal) => wal.id == spoken.id).status,
        WalStatus.synced,
        reason: 'the durable index records the synced-retention transition',
      );
    });

    test('a covered WAL joins synced retention: status, fresh syncedAt, file kept', () async {
      const name = 'covered_retained.bin';
      File('${directory.path}/$name').writeAsBytesSync([1, 2, 3]);
      final now = DateTime.fromMillisecondsSinceEpoch(1000 * 1000);
      final persisted = <Wal>[];
      final telemetry = <Map<String, Object?>>[];
      final local = build(now: now, persistedSink: persisted, telemetry: telemetry);
      final covered = stamped(470, seconds: 60, totalFrames: 6000, filePath: name);
      local.testWals = [covered];

      final outcome = await local.confirmSessionTranscription(
        500,
        'c1',
        transcriptSpans: [(469, 531)],
        conversationStartSeconds: 520,
      );

      expect(outcome.released, 0);
      expect(outcome.kept, 0);
      expect(covered.status, WalStatus.synced);
      expect(covered.syncedAt, 1000, reason: 'newly synced copies start the retention clock now');
      expect(local.testWals, contains(covered));
      expect(persisted.single.status, WalStatus.synced);
      expect(File('${directory.path}/$name').existsSync(), isTrue);
      expect(telemetry.single['retained_covered_count'], 1);
      expect(telemetry.single['retained_covered_seconds'], 60.0);
      expect(telemetry.single['kept_count'], 0);
      expect(telemetry.single.containsKey('fail_closed_reason'), isFalse);
    });

    test('a covered transport-only synced copy starts its retention clock', () async {
      final now = DateTime.fromMillisecondsSinceEpoch(1000 * 1000);
      final local = build(now: now);
      final transportSynced = stamped(470, status: WalStatus.synced);
      local.testWals = [transportSynced];

      await local.confirmSessionTranscription(500, 'c1', transcriptSpans: [(469, 531)]);

      expect(transportSynced.status, WalStatus.synced);
      expect(transportSynced.syncedAt, 1000);
      expect(transportSynced.keptForTranscriptRecovery, isFalse);
    });

    test('an uncovered transport-only synced copy reclassifies to miss so recovery uploads it', () async {
      final now = DateTime.fromMillisecondsSinceEpoch(1000 * 1000);
      const name = 'transport_synced_gap.bin';
      File('${directory.path}/$name').writeAsBytesSync([1, 2, 3]);
      final attempted = <List<String>>[];
      final local = build(
        now: now,
        uploadGate: succeedingGate(attempted: attempted),
      );
      final transportSynced = stamped(470, status: WalStatus.synced, filePath: name);
      local.testWals = [transportSynced];

      await local.confirmSessionTranscription(500, 'c1', transcriptSpans: [(501, 531)]);

      expect(
        transportSynced.status,
        WalStatus.miss,
        reason: 'a synced status from socket sends alone would status-skip the repair upload',
      );
      expect(transportSynced.syncedAt, 0);
      expect(transportSynced.keptForTranscriptRecovery, isTrue);

      await local.syncAll();
      expect(attempted, [
        [name],
      ]);
      expect(transportSynced.status, WalStatus.synced);
      expect(transportSynced.syncedAt, 1000);
      expect(transportSynced.keptForTranscriptRecovery, isFalse);
    });

    test('durable synced, in-flight, accepted, terminal and pendant copies are never regressed', () async {
      final telemetry = <Map<String, Object?>>[];
      final local = build(telemetry: telemetry);
      final cases = <(Wal, WalStatus, int)>[
        (stamped(470, status: WalStatus.synced, syncedAt: 12345), WalStatus.synced, 12345),
        (stamped(470, isSyncing: true), WalStatus.miss, 0),
        (stamped(470, status: WalStatus.uploaded), WalStatus.uploaded, 0),
        (stamped(470, status: WalStatus.corrupted), WalStatus.corrupted, 0),
        (stamped(470, status: WalStatus.miss)..storage = WalStorage.sdcard, WalStatus.miss, 0),
        (stamped(470, status: WalStatus.miss)..storage = WalStorage.flashPage, WalStatus.miss, 0),
      ];
      local.testWals = [for (final (wal, _, _) in cases) wal];

      final outcome = await local.confirmSessionTranscription(500, 'c1', transcriptSpans: [(469, 531)]);

      expect(outcome.kept, 0, reason: 'ineligible copies are untouched, not counted as repair work');
      for (final (wal, status, syncedAt) in cases) {
        expect(wal.status, status);
        expect(wal.syncedAt, syncedAt);
        expect(wal.keptForTranscriptRecovery, isFalse);
      }
      expect(telemetry.single['retained_covered_count'], 0);
      expect(telemetry.single['kept_count'], 0);
    });

    test('an uncovered pending copy keeps its retry budget', () async {
      final local = build();
      final pending = stamped(470)
        ..retryCount = 2
        ..lastRetryAt = 400;
      local.testWals = [pending];

      await local.confirmSessionTranscription(500, 'c1', transcriptSpans: [(501, 531)]);

      expect(pending.retryCount, 2);
      expect(pending.lastRetryAt, 400);
      expect(pending.status, WalStatus.miss);
      expect(pending.keptForTranscriptRecovery, isTrue);
    });

    test('a covered miss refreshes a stale syncedAt instead of aging from it', () async {
      final now = DateTime.fromMillisecondsSinceEpoch(1000 * 1000);
      final local = build(now: now);
      // A requeued copy can carry a syncedAt from a previous clock — coverage stamps it fresh.
      final wal = stamped(470, syncedAt: 777);
      local.testWals = [wal];

      await local.confirmSessionTranscription(500, 'c1', transcriptSpans: [(469, 531)]);

      expect(wal.status, WalStatus.synced);
      expect(wal.syncedAt, 1000);
    });

    test('an explicit fail-closed reason keeps covered-looking copies too', () async {
      final telemetry = <Map<String, Object?>>[];
      final local = build(telemetry: telemetry);
      final wal = stamped(470);
      local.testWals = [wal];

      final outcome = await local.confirmSessionTranscription(
        500,
        'c1',
        transcriptSpans: [(469, 531)],
        failClosedReason: 'needs_repair',
      );

      expect(outcome.kept, 1, reason: 'spans supplied alongside a failure reason are not coverage evidence');
      expect(wal.status, WalStatus.miss);
      expect(wal.keptForTranscriptRecovery, isTrue);
      expect(telemetry.single['fail_closed_reason'], 'needs_repair');
    });

    test('an empty transcript span list keeps, never releases', () async {
      final local = build();
      final wal = stamped(450, seconds: 30);
      local.testWals = [wal];

      final outcome = await local.confirmSessionTranscription(400, 'c1', transcriptSpans: const []);

      expect(outcome.released, 0);
      expect(outcome.kept, 1);
      expect(local.testWals, contains(wal));
    });

    test('a failed save reverts covered copies to repair in memory and keeps the file', () async {
      const name = 'covered_save_fail.bin';
      File('${directory.path}/$name').writeAsBytesSync([1, 2, 3]);
      final telemetry = <Map<String, Object?>>[];
      final attempted = <List<String>>[];
      var saveCalls = 0;
      final local = build(
        telemetry: telemetry,
        persist: (wals) async {
          if (saveCalls++ == 0) throw StateError('synthetic save failure');
        },
        uploadGate: succeedingGate(attempted: attempted),
      );
      final covered = stamped(470, filePath: name);
      local.testWals = [covered];

      await expectLater(
        local.confirmSessionTranscription(500, 'c1', transcriptSpans: [(469, 531)]),
        throwsA(isA<StateError>()),
      );

      // The durable index never recorded the coverage, so recovery must not be suppressed:
      // memory reverts to the same repair state an uncovered copy gets.
      expect(telemetry, isEmpty);
      expect(covered.status, WalStatus.miss);
      expect(covered.syncedAt, 0);
      expect(covered.keptForTranscriptRecovery, isTrue);
      expect(local.testWals, contains(covered));
      expect(File('${directory.path}/$name').existsSync(), isTrue);

      await local.syncAll();
      expect(
          attempted,
          [
            [name],
          ],
          reason: 'the failed-closed copy uploads on the next pass');
      expect(covered.status, WalStatus.synced);
      expect(covered.keptForTranscriptRecovery, isFalse);
    });

    test('retained-covered synced copies cannot evict a pending gap WAL', () async {
      const name = 'oldest_gap.bin';
      File('${directory.path}/$name').writeAsBytesSync([1]);
      final local = build();
      final oldestPending = stamped(1, filePath: name);
      final retainedCovered = [for (var i = 0; i < maxRetainedCaptureWalCount + 4; i++) stamped(100 + i)];
      local.testWals = [oldestPending, ...retainedCovered];

      // The saved transcript covers the 724 newer copies; the oldest gap stays pending.
      final outcome = await local.confirmSessionTranscription(
        1,
        'c1',
        transcriptSpans: [(50, 1000)],
        conversationStartSeconds: 1,
      );
      expect(outcome.kept, 1);
      expect(retainedCovered.every((wal) => wal.status == WalStatus.synced && wal.syncedAt > 0), isTrue);

      final evicted = await local.enforceRetentionPolicyForTesting();

      expect(evicted, 0, reason: 'synced copies are excluded from the unacknowledged cap');
      expect(local.testWals, hasLength(maxRetainedCaptureWalCount + 5));
      expect(File('${directory.path}/$name').existsSync(), isTrue, reason: 'the oldest pending gap copy survives');
    });

    test('a positive subsecond tail is kept even though seconds truncates to 0', () async {
      final telemetry = <Map<String, Object?>>[];
      final local = build(telemetry: telemetry);
      final tail = stamped(450, seconds: 0, totalFrames: 50);
      local.testWals = [tail];

      final outcome = await local.confirmSessionTranscription(400, 'c1', transcriptSpans: [(400, 500)]);

      expect(outcome.released, 0);
      expect(outcome.kept, 1);
      expect(tail.keptForTranscriptRecovery, isTrue);
      expect(local.testWals, contains(tail));
      expect(telemetry.single['phase'], 'confirmation');
      expect(telemetry.single['kept_seconds'], 0.5);
      expect(telemetry.single['retained_covered_count'], 0);
    });

    test('fail-closed telemetry reports the explicit reason or no_spans by default', () async {
      final telemetry = <Map<String, Object?>>[];
      final local = build(telemetry: telemetry);
      local.testWals = [stamped(100), stamped(200)];

      await local.confirmSessionTranscription(100, 'c1');
      expect(telemetry.last['fail_closed_reason'], 'no_spans');
      expect(telemetry.last['kept_count'], 2);

      await local.confirmSessionTranscription(100, 'c1', transcriptSpans: const []);
      expect(telemetry.last['fail_closed_reason'], 'no_spans');

      await local.confirmSessionTranscription(100, 'c1', failClosedReason: 'needs_repair');
      expect(telemetry.last['fail_closed_reason'], 'needs_repair');
    });

    test('a non-file entity at the recorded path keeps the inventory record', () async {
      const name = 'audio_covered.bin';
      Directory('${directory.path}/$name').createSync();
      final persisted = <Wal>[];
      final local = build(persistedSink: persisted);
      final wal = stamped(100, filePath: name, status: WalStatus.synced, syncedAt: 1);
      local.testWals = [wal];

      await local.deleteAllSyncedWals();

      expect(
        local.testWals,
        contains(wal),
        reason: 'a directory where the file should be is not proof the copy is gone',
      );
      expect(persisted, contains(wal));
    });

    test('a path-resolution failure keeps the inventory record', () async {
      const name = 'audio_covered.bin';
      File('${directory.path}/$name').writeAsBytesSync([1, 2, 3]);
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        (MethodCall call) async =>
            throw PlatformException(code: 'unavailable', message: 'documents directory unavailable'),
      );
      final persisted = <Wal>[];
      final local = build(persistedSink: persisted);
      final wal = stamped(100, filePath: name, status: WalStatus.synced, syncedAt: 1);
      local.testWals = [wal];

      await local.deleteAllSyncedWals();

      expect(local.testWals, contains(wal));
      expect(persisted, contains(wal));
      expect(File('${directory.path}/$name').existsSync(), isTrue);
    });

    test('a file shared with another WAL stays on disk', () async {
      const name = 'shared_audio.bin';
      File('${directory.path}/$name').writeAsBytesSync([1, 2, 3]);
      var saves = 0;
      final local = build(persist: (wals) async => saves++);
      final covered = stamped(100, filePath: name, status: WalStatus.synced, syncedAt: 1);
      final sibling = stamped(200, conversationId: 'other', filePath: name, status: WalStatus.miss);
      local.testWals = [covered, sibling];

      await local.deleteWal(covered);

      expect(
        File('${directory.path}/$name').existsSync(),
        isTrue,
        reason: 'the sibling WAL still references the physical file',
      );
      expect(local.testWals, isNot(contains(covered)));
      expect(local.testWals, contains(sibling));
      expect(saves, 1);
    });

    test('public deleteWal resolves the tracked object and fails closed on equal ids', () async {
      const name = 'dup_audio.bin';
      File('${directory.path}/$name').writeAsBytesSync([1, 2, 3]);
      final local = build();
      final a = stamped(100, filePath: name);
      final b = stamped(100, filePath: name);
      local.testWals = [a, b];
      final detached = stamped(100, filePath: name);

      await local.deleteWal(detached);

      expect(
        local.testWals,
        containsAll([a, b]),
        reason: 'two tracked records share the id: deleting either is unproven',
      );
      expect(File('${directory.path}/$name').existsSync(), isTrue);
    });

    test('public deleteWal removes the single tracked record a detached object names', () async {
      const name = 'solo_audio.bin';
      File('${directory.path}/$name').writeAsBytesSync([1, 2, 3]);
      var saves = 0;
      final local = build(persist: (wals) async => saves++);
      final tracked = stamped(100, filePath: name);
      local.testWals = [tracked];
      final detached = stamped(100, filePath: name);

      await local.deleteWal(detached);

      expect(local.testWals, isEmpty);
      expect(saves, 1, reason: 'a successful removal is persisted');
      expect(File('${directory.path}/$name').existsSync(), isFalse);
    });

    test('public deleteWal never resolves to a retired record', () async {
      const name = 'retired_audio.bin';
      File('${directory.path}/$name').writeAsBytesSync([1, 2, 3]);
      var saves = 0;
      final local = build(persist: (wals) async => saves++);
      final retired = stamped(100, filePath: name);
      local.testRetiredWals.add(retired);
      final detached = stamped(100, filePath: name);

      await local.deleteWal(detached);

      expect(local.testRetiredWals, contains(retired));
      expect(saves, 0);
      expect(File('${directory.path}/$name').existsSync(), isTrue);
    });

    test('public deleteWal never resolves to a foreign record', () async {
      const name = 'foreign_audio.bin';
      File('${directory.path}/$name').writeAsBytesSync([1, 2, 3]);
      var saves = 0;
      final local = build(persist: (wals) async => saves++);
      final foreign = stamped(100, filePath: name)..ownerUid = 'other-account';
      local.testForeignWals.add(foreign);
      final detached = stamped(100, filePath: name);

      await local.deleteWal(detached);

      expect(local.testForeignWals, contains(foreign));
      expect(saves, 0);
      expect(File('${directory.path}/$name').existsSync(), isTrue);
    });

    test('public deleteWal ignores a detached id whose codec or storage differs', () async {
      const name = 'mismatch_audio.bin';
      File('${directory.path}/$name').writeAsBytesSync([1, 2, 3]);
      var saves = 0;
      final local = build(persist: (wals) async => saves++);
      final tracked = stamped(100, filePath: name);
      local.testWals = [tracked];
      final wrongCodec = stamped(100, filePath: name);
      wrongCodec.codec = BleAudioCodec.pcm8;
      final wrongStorage = stamped(100, filePath: name);
      wrongStorage.storage = WalStorage.sdcard;

      await local.deleteWal(wrongCodec);
      await local.deleteWal(wrongStorage);

      expect(local.testWals, contains(tracked));
      expect(saves, 0);
      expect(File('${directory.path}/$name').existsSync(), isTrue);
    });

    test('a detached old-account object cannot name a successor with the same id', () async {
      const oldName = 'old_owner.bin';
      const newName = 'new_owner.bin';
      File('${directory.path}/$oldName').writeAsBytesSync([1]);
      File('${directory.path}/$newName').writeAsBytesSync([2]);
      var saves = 0;
      final local = build(persist: (wals) async => saves++);
      final successor = stamped(100, filePath: newName)
        ..ownerUid = 'new-account'
        ..recordingSessionId = 'session-new';
      local.testWals = [successor];
      final oldRecord = stamped(100, filePath: oldName)
        ..ownerUid = 'old-account'
        ..recordingSessionId = 'session-old';
      local.testRetiredWals.add(oldRecord);
      final detached = stamped(100, filePath: oldName)
        ..ownerUid = 'old-account'
        ..recordingSessionId = 'session-old';

      await local.deleteWal(oldRecord);
      await local.deleteWal(detached);

      expect(local.testWals, contains(successor));
      expect(local.testRetiredWals, contains(oldRecord));
      expect(saves, 0);
      expect(File('${directory.path}/$oldName').existsSync(), isTrue);
      expect(File('${directory.path}/$newName').existsSync(), isTrue);
    });

    test('an inventory swap during path resolution removes nothing', () async {
      const name = 'swap_audio.bin';
      File('${directory.path}/$name').writeAsBytesSync([1, 2, 3]);
      late LocalWalSyncImpl local;
      local = build();
      final wal = stamped(100, filePath: name, status: WalStatus.synced, syncedAt: 1);
      local.testWals = [wal];
      final successor = Wal.fromJson(wal.toJson());

      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        (MethodCall call) async {
          if (call.method == 'getApplicationDocumentsDirectory') {
            local.testWals = [successor];
            return directory.path;
          }
          return null;
        },
      );

      await local.deleteAllSyncedWals();

      expect(
        local.testWals,
        contains(successor),
        reason: 'the captured record is no longer tracked — nothing may be removed in its name',
      );
      expect(File('${directory.path}/$name').existsSync(), isTrue);
    });

    test('equal-id siblings: the sweep removes only the expired exact object', () async {
      const nameA = 'dup_a.bin';
      const nameB = 'dup_b.bin';
      File('${directory.path}/$nameA').writeAsBytesSync([1]);
      File('${directory.path}/$nameB').writeAsBytesSync([2]);
      SharedPreferencesUtil().autoRemoveSyncedCopies = true;
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final local = build();
      final expired = stamped(
        100,
        filePath: nameA,
        status: WalStatus.synced,
        syncedAt: now - 31 * Duration.secondsPerDay,
      );
      final fresh = stamped(100, filePath: nameB, status: WalStatus.synced, syncedAt: now);
      expect(expired.id, fresh.id);
      local.testWals = [expired, fresh];

      final removed = await local.enforceSyncedCopyRetentionForTesting();

      expect(removed, 1);
      expect(local.testWals, [fresh]);
      expect(File('${directory.path}/$nameA').existsSync(), isFalse);
      expect(File('${directory.path}/$nameB').existsSync(), isTrue);
    });

    test('a generation roll during path resolution cannot remove the WAL', () async {
      const name = 'fenced_audio.bin';
      File('${directory.path}/$name').writeAsBytesSync([1, 2, 3]);
      SharedPreferencesUtil().autoRemoveSyncedCopies = true;
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      late LocalWalSyncImpl local;
      var persisted = <Wal>[];
      local = build(persist: (wals) async => persisted = List<Wal>.from(wals));
      final wal = stamped(100, filePath: name, status: WalStatus.synced, syncedAt: now - 31 * Duration.secondsPerDay);
      local.testWals = [wal];

      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        (MethodCall call) async {
          if (call.method == 'getApplicationDocumentsDirectory') {
            local.clearUserData();
            return directory.path;
          }
          return null;
        },
      );

      await local.enforceSyncedCopyRetentionForTesting();

      await local.persistRetryMetadata(wal);
      expect(File('${directory.path}/$name').existsSync(), isTrue);
      expect(persisted.map((w) => w.id), contains(wal.id));
    });

    test('a stale generation suppresses telemetry and successor publication', () async {
      final telemetry = <Map<String, Object?>>[];
      late LocalWalSyncImpl local;
      local = build(telemetry: telemetry, persist: (wals) async => local.clearUserData());
      local.testWals = [stamped(100)];

      await local.confirmSessionTranscription(100, 'c1');

      expect(telemetry, isEmpty);
    });

    test('covered WALs already uploading are never regressed', () async {
      final local = build();
      final syncing = stamped(100, isSyncing: true);
      final uploaded = stamped(200, status: WalStatus.uploaded);
      local.testWals = [syncing, uploaded];

      final outcome = await local.confirmSessionTranscription(100, 'c1', transcriptSpans: [(100, 300)]);

      expect(outcome.released, 0);
      expect(outcome.kept, 0);
      expect(local.testWals, containsAll([syncing, uploaded]));
      expect(syncing.status, WalStatus.miss, reason: 'confirmation must not overwrite sync state');
      expect(syncing.keptForTranscriptRecovery, isFalse);
      expect(uploaded.status, WalStatus.uploaded);
      expect(uploaded.keptForTranscriptRecovery, isFalse);
    });

    test('an accepted upload clears the marker and counts the redundant seconds', () async {
      final telemetry = <Map<String, Object?>>[];
      const name = 'recovery_audio.bin';
      File('${directory.path}/$name').writeAsBytesSync([1, 2, 3]);
      final local = build(telemetry: telemetry, uploadGate: succeedingGate());
      final tail = stamped(100, seconds: 0, totalFrames: 50, filePath: name);
      tail.conversationId = 'c1';
      local.testWals = [tail];

      await local.confirmSessionTranscription(100, 'c1');
      expect(tail.keptForTranscriptRecovery, isTrue);

      await local.syncAll();

      expect(tail.keptForTranscriptRecovery, isFalse);
      final uploads = telemetry.where((event) => event['phase'] == 'upload').toList();
      expect(uploads, hasLength(1));
      expect(uploads.single['kept_count'], 1);
      expect(uploads.single['kept_seconds'], 0.5);
      expect(uploads.single['kept_uploaded_count'], 1);
      expect(uploads.single['kept_uploaded_seconds'], 0.5);
      expect(uploads.single['retained_covered_count'], 0);
    });

    test('a queued 202 acceptance also clears the marker and counts the seconds', () async {
      final telemetry = <Map<String, Object?>>[];
      const name = 'recovery_queued.bin';
      File('${directory.path}/$name').writeAsBytesSync([1, 2, 3]);
      final local = build(
        telemetry: telemetry,
        uploadGate: succeedingGate(outcome: () => UploadFilesResult.queued('job-1')),
      );
      final wal = stamped(100, filePath: name);
      local.testWals = [wal];

      await local.confirmSessionTranscription(100, 'c1');
      await local.syncAll();

      expect(wal.status, WalStatus.uploaded);
      expect(wal.keptForTranscriptRecovery, isFalse);
      final uploads = telemetry.where((event) => event['phase'] == 'upload').toList();
      expect(uploads, hasLength(1));
      expect(uploads.single['kept_count'], 1);
      expect(uploads.single['kept_uploaded_seconds'], 60.0);
    });

    test('an accepted upload under a stale generation keeps the marker and stays silent', () async {
      final telemetry = <Map<String, Object?>>[];
      const name = 'recovery_stale.bin';
      File('${directory.path}/$name').writeAsBytesSync([1, 2, 3]);
      late LocalWalSyncImpl local;
      local = build(
        telemetry: telemetry,
        uploadGate: succeedingGate(
          outcome: () {
            local.clearUserData();
            return UploadFilesResult.done(
              SyncLocalFilesResponse(newConversationIds: ['c1'], updatedConversationIds: []),
            );
          },
        ),
      );
      final wal = stamped(100, filePath: name);
      wal.ownerUid = 'owner';
      local.testWals = [wal];

      await local.confirmSessionTranscription(100, 'c1');
      expect(wal.keptForTranscriptRecovery, isTrue);

      await local.syncAll();

      expect(wal.keptForTranscriptRecovery, isTrue);
      expect(telemetry.where((event) => event['phase'] == 'upload'), isEmpty);
    });

    test('a failed index save aborts confirmation before any success observation', () async {
      final telemetry = <Map<String, Object?>>[];
      const name = 'persist_fail.bin';
      File('${directory.path}/$name').writeAsBytesSync([1, 2, 3]);
      final local = build(telemetry: telemetry, persist: (wals) async => throw StateError('synthetic save failure'));
      final wal = stamped(100, filePath: name);
      local.testWals = [wal];

      await expectLater(local.confirmSessionTranscription(100, 'c1'), throwsA(isA<StateError>()));

      expect(telemetry, isEmpty);
      expect(wal.keptForTranscriptRecovery, isTrue);
      expect(local.testWals, contains(wal));
      expect(File('${directory.path}/$name').existsSync(), isTrue);
    });

    test('a refused upload keeps the marker and emits no positive uploaded seconds', () async {
      final telemetry = <Map<String, Object?>>[];
      const name = 'recovery_refused.bin';
      File('${directory.path}/$name').writeAsBytesSync([1, 2, 3]);
      final local = build(
        telemetry: telemetry,
        uploadGate: succeedingGate(outcome: () => throw StateError('synthetic refused upload')),
      );
      final tail = stamped(100, filePath: name);
      local.testWals = [tail];

      await local.confirmSessionTranscription(100, 'c1');
      await local.syncAll();

      expect(tail.keptForTranscriptRecovery, isTrue);
      expect(tail.status, WalStatus.miss);
      final uploadEvents = telemetry.where((event) => event['phase'] == 'upload').toList();
      expect(uploadEvents, isEmpty);
      expect(telemetry.every((event) => (event['kept_uploaded_seconds'] as double) == 0), isTrue);
    });

    test('the single-WAL upload path clears the marker on acceptance too', () async {
      final telemetry = <Map<String, Object?>>[];
      const name = 'recovery_single.bin';
      File('${directory.path}/$name').writeAsBytesSync([1, 2, 3]);
      final local = build(telemetry: telemetry, uploadGate: succeedingGate());
      final wal = stamped(100, filePath: name);
      local.testWals = [wal];

      await local.confirmSessionTranscription(100, 'c1');
      await local.syncWal(wal: wal);

      expect(wal.keptForTranscriptRecovery, isFalse);
      final uploads = telemetry.where((event) => event['phase'] == 'upload').toList();
      expect(uploads, hasLength(1));
      expect(uploads.single['kept_count'], 1);
      expect(uploads.single['kept_uploaded_seconds'], 60.0);
    });

    test('the recovery marker round-trips through the durable index', () async {
      final persisted = <Wal>[];
      final local = build(persistedSink: persisted);
      final wal = stamped(100);
      local.testWals = [wal];

      await local.confirmSessionTranscription(100, 'c1');

      final json = persisted.single.toJson();
      expect(json['kept_for_transcript_recovery'], isTrue);
      final restored = Wal.fromJson(json);
      expect(restored.keptForTranscriptRecovery, isTrue);

      const name = 'reloaded_audio.bin';
      File('${directory.path}/$name').writeAsBytesSync([1]);
      restored.filePath = name;
      restored.status = WalStatus.miss;
      final telemetry = <Map<String, Object?>>[];
      final reloaded = build(telemetry: telemetry, uploadGate: succeedingGate());
      reloaded.testWals = [restored];

      await reloaded.syncWal(wal: restored);

      expect(restored.keptForTranscriptRecovery, isFalse);
      expect(telemetry.single['phase'], 'upload');
      expect(telemetry.single['kept_uploaded_seconds'], 60.0);
    });

    test('an unmarked WAL serializes without the recovery key', () {
      final json = stamped(100).toJson();
      expect(json.containsKey('kept_for_transcript_recovery'), isFalse);
      expect(Wal.fromJson({...json, 'codec': 'opus'}).keptForTranscriptRecovery, isFalse);
    });
  });

  group('walCoveredByTranscript', () {
    Wal wal(int timerStart, int seconds, {int totalFrames = 0}) => Wal(
          timerStart: timerStart,
          codec: BleAudioCodec.opus,
          seconds: seconds,
          totalFrames: totalFrames,
          storage: WalStorage.disk,
        );

    test('a span inside the WAL does not cover it', () {
      expect(walCoveredByTranscript(wal(100, 60), [(120, 129)], 100), isFalse);
    });

    test('unordered, overlapping and adjacent spans that fully cover do', () {
      expect(walCoveredByTranscript(wal(100, 60), [(150, 165), (118, 152), (100, 120)], 100), isTrue);
      expect(walCoveredByTranscript(wal(100, 60), [(100, 130), (130, 160)], 100), isTrue);
      expect(
        walCoveredByTranscript(wal(100, 60), [(140, 170), (90, 140)], 100),
        isTrue,
        reason: 'clipped union still reaches both edges',
      );
    });

    test('thirty seconds of pause at each outer edge is tolerated, thirty-one is not', () {
      expect(walTranscriptPauseToleranceSeconds, 30);
      expect(walCoveredByTranscript(wal(100, 60), [(130, 160)], 100), isTrue);
      expect(walCoveredByTranscript(wal(100, 60), [(131, 160)], 100), isFalse);
      expect(walCoveredByTranscript(wal(100, 60), [(100, 130)], 100), isTrue);
      expect(walCoveredByTranscript(wal(100, 60), [(100, 129)], 100), isFalse);
    });

    test('a thirty-second interior pause is tolerated, thirty-one is not', () {
      expect(
        walCoveredByTranscript(wal(100, 100), [(100, 120), (150, 200)], 100),
        isTrue,
        reason: 'a 30 s silence between utterances is a pause, not a hole',
      );
      expect(
        walCoveredByTranscript(wal(100, 100), [(100, 120), (151, 200)], 100),
        isFalse,
        reason: 'a 31 s interior hole is longer than the pause tolerance',
      );
      expect(
        walCoveredByTranscript(wal(100, 60), [(100, 158), (159, 160)], 100),
        isTrue,
        reason: 'a one-second hole near the edge is an interior pause, not uncovered audio',
      );
      expect(
        walCoveredByTranscript(wal(100, 60), [(100, 158)], 100),
        isTrue,
        reason: 'a two-second uncovered tail is outer-edge tolerance, not a hole',
      );
      expect(
        walCoveredByTranscript(wal(100, 60), [(101, 102), (103, 160)], 100),
        isTrue,
        reason: 'a one-second head and a one-second interior pause both fall inside the tolerance',
      );
    });

    test('no actual overlap fails even on a short WAL', () {
      expect(walCoveredByTranscript(wal(200, 10), [(100, 150)], 100), isFalse);
      expect(
        walCoveredByTranscript(wal(200, 1), [(198, 199)], 100),
        isFalse,
        reason: 'a one-second WAL with zero overlap cannot be tolerated into coverage',
      );
      expect(
        walCoveredByTranscript(wal(200, 1), [(201, 205)], 100),
        isFalse,
        reason: 'a span beginning at the WAL end is no evidence either',
      );
    });

    test('a short utterance covers when both edges fall inside the tolerance', () {
      expect(
        walCoveredByTranscript(wal(100, 60), [(130, 131)], 100),
        isTrue,
        reason: 'a 30 s head and a 29 s tail around one utterance are both tolerable',
      );
      expect(
        walCoveredByTranscript(wal(100, 60), [(120, 128)], 100),
        isFalse,
        reason: 'the same utterance ending 32 s early leaves an intolerable tail',
      );
    });

    test('a head or tail longer than the tolerance fails', () {
      expect(walCoveredByTranscript(wal(100, 60), [(131, 160)], 100), isFalse);
      expect(walCoveredByTranscript(wal(100, 60), [(100, 129)], 100), isFalse);
    });

    test('two minutes of conversation with natural pauses and long silences are covered', () {
      expect(
        walCoveredByTranscript(
            wal(100, 120),
            [
              (102, 110),
              (112, 116),
              (121, 133),
              (135, 141),
              (149, 154),
              (172, 184),
              (187, 189),
              (214, 220),
            ],
            100),
        isTrue,
      );
    });

    test('invalid or empty spans cover nothing', () {
      expect(walCoveredByTranscript(wal(100, 60), [(130, 120)], 100), isFalse);
      expect(walCoveredByTranscript(wal(100, 60), const [], 100), isFalse);
    });

    test('pre-conversation audio is not auto-covered', () {
      expect(walCoveredByTranscript(wal(100, 60), [(400, 410)], 190), isFalse);
    });

    test('a subsecond or unknown duration is not empty proof', () {
      expect(walCoveredByTranscript(wal(100, 0), [(100, 160)], 100), isFalse);
      expect(walCoveredByTranscript(wal(100, -5), [(100, 160)], 100), isFalse);
    });

    test('codec frames must agree with the recorded seconds', () {
      expect(walCoveredByTranscript(wal(100, 60, totalFrames: 6000), [(100, 160)], 100), isTrue);
      expect(walCoveredByTranscript(wal(100, 60, totalFrames: 6050), [(100, 160)], 100), isFalse);
      expect(walCoveredByTranscript(wal(100, 59, totalFrames: 6000), [(100, 160)], 100), isFalse);
    });
  });

  group('transcriptStartOnDevice', () {
    test('is when the live segments arrived, less their end', () {
      // Segments ending 20 s and 40 s into the conversation arrived at phone seconds 1022 and 1042.
      expect(transcriptStartOnDevice([('a', 19.5), ('b', 40)], {'a': 1022, 'b': 1042}), 1002);
    });

    test('takes the median, so one stray arrival does not move it', () {
      final ends = [('a', 10.0), ('b', 20.0), ('c', 30.0)];
      expect(transcriptStartOnDevice(ends, {'a': 1012, 'b': 1022, 'c': 1900}), 1002);
    });

    test('ignores segments that never arrived live, and is null when none did', () {
      expect(transcriptStartOnDevice([('a', 10), ('b', 20)], {'b': 1023}), 1003);
      expect(transcriptStartOnDevice([('a', 10)], {'other': 1023}), isNull);
      expect(transcriptStartOnDevice(const [], const {}), isNull);
    });

    test('skips non-finite ends and non-positive arrivals instead of trusting them', () {
      expect(transcriptStartOnDevice([('a', double.nan), ('b', 20), ('c', 30)], {'a': 2000, 'b': 1022, 'c': 0}), 1002);
      expect(transcriptStartOnDevice([('a', 10)], {'a': 0}), isNull);
      expect(transcriptStartOnDevice([('a', double.infinity)], {'a': 1022}), isNull);
    });
  });

  group('syncWal — orphan WAL guard', () {
    // A WAL the user taps "sync" on may already be gone from `_wals` (a
    // concurrent delete/reload). Previously `.first` on the empty match list
    // threw an uncaught StateError; the guard now bails out to null instead.
    test('LocalWalSyncImpl.syncWal returns null when the WAL is not tracked', () async {
      final orphan = Wal(timerStart: 123, codec: BleAudioCodec.opus, seconds: 10);

      final result = await sync.syncWal(wal: orphan);

      expect(result, isNull);
    });

    test('FlashPageWalSyncImpl.syncWal returns null when the WAL is not tracked', () async {
      final flashSync = FlashPageWalSyncImpl(listener);
      final orphan = Wal(timerStart: 456, codec: BleAudioCodec.opus, seconds: 10);

      final result = await flashSync.syncWal(wal: orphan);

      expect(result, isNull);
    });
  });

  test('a chunk colliding with an indexed disk WAL never mutates its file or data', () async {
    const timerStart = 1700000000;
    var persisted = <Wal>[];
    final oldWal = Wal(
      timerStart: timerStart,
      codec: BleAudioCodec.opus,
      seconds: 10,
      totalFrames: 1000,
      status: WalStatus.miss,
      storage: WalStorage.disk,
      device: 'dev',
      filePath: 'old_disk.bin',
    );
    final local = LocalWalSyncImpl(
      _MockListener(),
      // _chunk computes timerStart = now/1000 - 15 - chunkSecs; pin now so the
      // fresh 10s chunk lands exactly on the existing disk WAL's timerStart.
      now: () => DateTime.fromMillisecondsSinceEpoch((timerStart + 25) * 1000),
      persistWals: (wals) async => persisted = List<Wal>.from(wals),
      loadWals: () async => [oldWal],
    );
    local.setDeviceInfo('dev', 'Omi');
    local.start();
    await local.walReady;

    for (var i = 0; i < 2500; i++) {
      local.onFrameCaptured(WalFrame(payload: [0xAA, i & 0xFF], syncKey: FrameSyncKey([i & 0xFF, (i >> 8) & 0xFF, 0])));
    }
    await local.stop();

    expect(oldWal.filePath, 'old_disk.bin', reason: 'the indexed disk WAL keeps its file identity');
    expect(oldWal.data, isEmpty, reason: 'no fresh frames may be appended into a durable disk WAL');
    expect(oldWal.totalFrames, 1000);
    final fresh = persisted.where((w) => w != oldWal && w.timerStart == timerStart).toList();
    expect(fresh, isNotEmpty, reason: 'the colliding chunk becomes a distinct WAL, not an in-place append');
    expect(fresh.every((w) => w.filePath != 'old_disk.bin'), isTrue);
  });

  group('capture evidence batch partition', () {
    const darkWrite = bool.fromEnvironment('CAPTURE_EVIDENCE_V1_DARK_WRITE');
    const root = '12345678-1234-4234-8234-123456789abc';
    const now = 2000000000;

    Wal claimWal(
      int timerStart, {
      String? filePath,
      String? conversationId = 'c1',
      String? recordingSessionId = 's1',
      String? captureRoot = root,
      int? sourceFrameStart = 0,
      int? sourceClockEpoch = 7,
      int totalFrames = 6000,
      int sampleRate = 16000,
      int channel = 1,
      BleAudioCodec codec = BleAudioCodec.opus,
    }) =>
        Wal(
          timerStart: timerStart,
          codec: codec,
          seconds: 60,
          totalFrames: totalFrames,
          sampleRate: sampleRate,
          channel: channel,
          storage: WalStorage.disk,
          status: WalStatus.miss,
          conversationId: conversationId,
          recordingSessionId: recordingSessionId,
          filePath: filePath,
          captureRoot: captureRoot,
          sourceFrameStart: sourceFrameStart,
          sourceClockEpoch: sourceClockEpoch,
        );

    Wal legacyWal(
      int timerStart, {
      String? filePath,
      String? conversationId = 'c1',
      String? recordingSessionId = 's1',
    }) =>
        Wal(
          timerStart: timerStart,
          codec: BleAudioCodec.opus,
          seconds: 60,
          totalFrames: 6000,
          storage: WalStorage.disk,
          status: WalStatus.miss,
          conversationId: conversationId,
          recordingSessionId: recordingSessionId,
          filePath: filePath,
        );

    test('a claimable-newest mixed group uploads only the claimable files', () {
      final claimableNew = claimWal(100, filePath: 'claim_new.bin');
      final legacyMid = legacyWal(90, filePath: 'legacy_mid.bin');
      final claimableOld = claimWal(80, filePath: 'claim_old.bin');
      final legacyOld = legacyWal(70, filePath: 'legacy_old.bin');

      final batch = nextSyncUploadBatch([claimableNew, legacyMid, claimableOld, legacyOld], now);

      if (darkWrite) {
        expect(batch, [claimableNew, claimableOld]);
        expect(
          captureEvidenceUploadHeader(batch, [File('claim_new.bin'), File('claim_old.bin')]),
          isNotNull,
        );
      } else {
        expect(batch, [claimableNew, legacyMid, claimableOld, legacyOld]);
        expect(
          captureEvidenceUploadHeader(batch, [for (final _ in batch) File('x.bin')]),
          isNull,
        );
      }
    });

    test('a legacy-newest group drains legacy first, then claimable siblings', () {
      final legacyNew = legacyWal(100, filePath: 'legacy_new.bin');
      final claimableMid = claimWal(90, filePath: 'claim_mid.bin');
      final claimableOld = claimWal(80, filePath: 'claim_old.bin');
      final pending = [legacyNew, claimableMid, claimableOld];

      final first = nextSyncUploadBatch(pending, now);
      if (darkWrite) {
        expect(first, [legacyNew]);
        expect(captureEvidenceUploadHeader(first, [File('legacy_new.bin')]), isNull);

        final remainder = pending.where((wal) => !first.contains(wal)).toList();
        final second = nextSyncUploadBatch(remainder, now);
        expect(second, [claimableMid, claimableOld]);
        expect(
          captureEvidenceUploadHeader(second, [File('claim_mid.bin'), File('claim_old.bin')]),
          isNotNull,
        );
      } else {
        expect(first, pending);
      }
    });

    test('equal timestamps keep their original input order', () {
      final first = legacyWal(100, filePath: 'tie_a.bin');
      final second = legacyWal(100, filePath: 'tie_b.bin');
      final third = legacyWal(50, filePath: 'tie_c.bin');

      expect(nextSyncUploadBatch([first, second, third], now), [first, second, third]);
      expect(nextSyncUploadBatch([second, first, third], now), [second, first, third]);
    });

    test('a group tied past the batch limit matches the pre-partition recipe', () {
      final wals = [for (var i = 0; i < 8; i++) legacyWal(100, filePath: 'tie_$i.bin')];

      final batch = nextSyncUploadBatch(wals, now);
      final original = List<Wal>.from(wals)..sort((a, b) => b.timerStart.compareTo(a.timerStart));

      expect(batch.length, 5);
      expect(batch.map((wal) => wal.filePath), original.take(5).map((wal) => wal.filePath));
    });

    test('header rejects invalid fields, mismatched lengths, and empty input', () {
      if (!darkWrite) return;
      final file = File('ok.bin');
      expect(captureEvidenceUploadHeader([], []), isNull);
      expect(captureEvidenceUploadHeader([claimWal(100, filePath: 'ok.bin')], []), isNull);
      expect(
        captureEvidenceUploadHeader([claimWal(100, filePath: 'ok.bin')], [file, File('extra.bin')]),
        isNull,
      );
      final invalid = <Wal>[
        claimWal(100, filePath: 'ok.bin', sampleRate: 0),
        claimWal(100, filePath: 'ok.bin', sampleRate: -16000),
        claimWal(100, filePath: 'ok.bin', captureRoot: null),
        claimWal(100, filePath: 'ok.bin', sourceFrameStart: null),
        claimWal(100, filePath: 'ok.bin', sourceClockEpoch: null),
      ];
      for (final wal in invalid) {
        expect(captureEvidenceUploadHeader([wal], [file]), isNull);
      }
    });

    test('the five-file batch limit still holds for claimable groups', () {
      final wals = [for (var i = 0; i < 7; i++) claimWal(100 - i, filePath: 'claim_$i.bin')];

      final batch = nextSyncUploadBatch(wals, now);

      expect(batch.length, 5);
      expect(batch.map((wal) => wal.timerStart), [100, 99, 98, 97, 96]);
    });

    test('a legacy member between claimables does not suppress them', () {
      final claimableNew = claimWal(100, filePath: 'c_new.bin');
      final legacy = legacyWal(90, filePath: 'l_mid.bin');
      final claimableOld = claimWal(80, filePath: 'c_old.bin');

      final batch = nextSyncUploadBatch([claimableNew, legacy, claimableOld], now);

      if (darkWrite) {
        expect(batch, [claimableNew, claimableOld]);
      } else {
        expect(batch, [claimableNew, legacy, claimableOld]);
      }
    });

    test('a duplicated file basename stops the claimable batch before it', () {
      final first = claimWal(100, filePath: 'dup.bin');
      final second = claimWal(90, filePath: 'dup.bin');
      final third = claimWal(80, filePath: 'other.bin');

      final batch = nextSyncUploadBatch([first, second, third], now);

      if (darkWrite) {
        expect(batch, [first]);
      } else {
        expect(batch, [first, second, third]);
      }
    });

    test('single-file invalid claims keep the whole file in the legacy class', () {
      final cases = <Wal>[
        claimWal(100, filePath: 'bad_root.bin', captureRoot: 'not-a-uuid'),
        claimWal(100, filePath: 'neg_start.bin', sourceFrameStart: -1),
        claimWal(100, filePath: 'neg_epoch.bin', sourceClockEpoch: -5),
        claimWal(100, filePath: 'no_frames.bin', totalFrames: 0),
        claimWal(100, filePath: 'stereo.bin', channel: 2),
        claimWal(100, filePath: 'pcm8.bin', codec: BleAudioCodec.pcm8),
        claimWal(100, filePath: 'bad name.bin'),
      ];

      for (final invalid in cases) {
        final claimable = claimWal(90, filePath: 'sibling.bin');
        final batch = nextSyncUploadBatch([invalid, claimable], now);
        if (darkWrite) {
          expect(batch, [invalid], reason: 'invalid claim stays a single-file legacy batch');
          expect(
            captureEvidenceUploadHeader(batch, [File(invalid.filePath!)]),
            isNull,
          );
        } else {
          expect(batch, [invalid, claimable]);
        }
      }
    });

    test('a name over 255 bytes or without a file name is legacy', () {
      final tooLong = claimWal(100, filePath: 'a' * 256);
      final claimable = claimWal(90, filePath: 'ok.bin');

      final batch = nextSyncUploadBatch([tooLong, claimable], now);

      if (darkWrite) {
        expect(batch, [tooLong]);
      } else {
        expect(batch, [tooLong, claimable]);
      }
    });

    test('worst-case claims stay inside the 4096-byte header budget', () {
      const maxInt = 0x7FFFFFFFFFFFFFFF;
      final wals = [
        for (var i = 0; i < 5; i++)
          claimWal(
            100 - i,
            filePath: '${'a' * (251 - i)}${'b' * i}.bin',
            sourceFrameStart: maxInt - i,
            sourceClockEpoch: maxInt,
            totalFrames: maxInt,
            sampleRate: maxInt,
          ),
      ];

      if (darkWrite) {
        final batch = nextSyncUploadBatch(wals, now);
        expect(batch.length, 5);
        final header = captureEvidenceUploadHeader(batch, [for (final wal in batch) File(wal.filePath!)]);
        expect(header, isNotNull);
        expect(utf8.encode(header!).length, lessThanOrEqualTo(4096));
      }
    });

    test('an opus_fs320 WAL claims with the normalized opus codec token', () {
      if (!darkWrite) return;
      final wal = claimWal(100, filePath: 'audio_fs320.bin', codec: BleAudioCodec.opusFS320, totalFrames: 3000);

      final batch = nextSyncUploadBatch([wal], now);

      expect(batch, [wal], reason: 'supported Opus variants are claimable');
      final parsed = jsonDecode(captureEvidenceUploadHeader(batch, [File('audio_fs320.bin')])!) as Map<String, dynamic>;
      expect((parsed['files'] as List).single['codec'], 'opus');
      expect((parsed['files'] as List).single['frame_count'], 3000);
    });

    test('an oversized claim list still falls back to an unclaimed upload', () {
      if (!darkWrite) return;
      final wals = [for (var i = 0; i < 20; i++) claimWal(200 - i, filePath: '${'a' * 243}_cap_$i.bin')];
      expect(
        captureEvidenceUploadHeader(wals, [for (final wal in wals) File(wal.filePath!)]),
        isNull,
      );
    });
  });

  group('syncAll capture evidence partition', () {
    const darkWrite = bool.fromEnvironment('CAPTURE_EVIDENCE_V1_DARK_WRITE');
    const root = '12345678-1234-4234-8234-123456789abc';
    late Directory directory;
    late List<(List<String> names, String? evidence)> uploads;

    setUp(() async {
      directory = await Directory.systemTemp.createTemp('wal_s1_partition_');
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        (MethodCall call) async {
          if (call.method == 'getApplicationDocumentsDirectory') return directory.path;
          return null;
        },
      );
      uploads = [];
      SyncRateLimiter.instance.clear();
    });

    tearDown(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        null,
      );
      SyncRateLimiter.instance.clear();
      if (directory.existsSync()) directory.deleteSync(recursive: true);
    });

    Wal diskWal(
      int timerStart,
      String name, {
      bool claimable = false,
      String? conversationId = 'c1',
      String? recordingSessionId = 's1',
    }) {
      File('${directory.path}/$name').writeAsBytesSync([1, 2, 3]);
      return Wal(
        timerStart: timerStart,
        codec: BleAudioCodec.opus,
        seconds: 60,
        totalFrames: 6000,
        sampleRate: 16000,
        storage: WalStorage.disk,
        status: WalStatus.miss,
        conversationId: conversationId,
        recordingSessionId: recordingSessionId,
        filePath: name,
        captureRoot: claimable ? root : null,
        sourceFrameStart: claimable ? 0 : null,
        sourceClockEpoch: claimable ? 7 : null,
      );
    }

    LocalWalSyncImpl buildSync() => LocalWalSyncImpl(
          listener,
          now: () => DateTime.fromMillisecondsSinceEpoch(2000000000 * 1000),
          persistWals: (wals) async {},
          loadWals: () async => <Wal>[],
          uploadGate: SyncUploadGate(
            limiter: SyncRateLimiter.instance,
            uploader: (files,
                {onUploadProgress,
                conversationId,
                captureEvidence,
                recordingSessionId,
                audioStartSeconds,
                audioEndSeconds,
                claimLiveCapture = false,
                geolocation}) async {
              uploads.add((
                files.map((file) => file.uri.pathSegments.last).toList(),
                captureEvidence,
              ));
              return UploadFilesResult.queued('job-${uploads.length}');
            },
            fairUseStatusLoader: () async => null,
          ),
        );

    test('a claimable-newest mixed drain sends claims, then the legacy batch goes unclaimed', () async {
      final local = buildSync();
      local.testWals = [
        diskWal(100, 'claim_a.bin', claimable: true),
        diskWal(90, 'legacy_b.bin'),
        diskWal(80, 'claim_c.bin', claimable: true),
      ];

      await local.syncAll();

      if (darkWrite) {
        expect(uploads.length, 2);
        expect(uploads[0].$1, ['claim_a.bin', 'claim_c.bin']);
        final parsed = jsonDecode(uploads[0].$2!) as Map<String, dynamic>;
        expect(
          (parsed['files'] as List).map((claim) => claim['name']),
          uploads[0].$1,
          reason: 'each claim names the exact uploaded file basename',
        );
        expect(uploads[1].$1, ['legacy_b.bin']);
        expect(uploads[1].$2, isNull);
      } else {
        expect(uploads.length, 1);
        expect(uploads.single.$1, ['claim_a.bin', 'legacy_b.bin', 'claim_c.bin']);
        expect(uploads.single.$2, isNull);
      }
    });

    test('a legacy-newest mixed drain goes unclaimed first, then claimable siblings drain', () async {
      final local = buildSync();
      local.testWals = [
        diskWal(100, 'legacy_a.bin'),
        diskWal(90, 'claim_b.bin', claimable: true),
        diskWal(80, 'claim_c.bin', claimable: true),
      ];

      await local.syncAll();

      if (darkWrite) {
        expect(uploads.length, 2);
        expect(uploads[0].$1, ['legacy_a.bin']);
        expect(uploads[0].$2, isNull);
        expect(uploads[1].$1, ['claim_b.bin', 'claim_c.bin']);
        final parsed = jsonDecode(uploads[1].$2!) as Map<String, dynamic>;
        expect((parsed['files'] as List).map((claim) => claim['name']), uploads[1].$1);
      } else {
        expect(uploads.length, 1);
        expect(uploads.single.$1, ['legacy_a.bin', 'claim_b.bin', 'claim_c.bin']);
        expect(uploads.single.$2, isNull);
      }
    });

    test('split WALs sharing one id still each upload in separate batches', () async {
      final local = buildSync();
      local.testWals = [
        diskWal(100, 'split_a.bin', claimable: true, recordingSessionId: 's1'),
        diskWal(100, 'split_b.bin', claimable: true, recordingSessionId: 's2'),
      ];

      await local.syncAll();

      if (darkWrite) {
        expect(uploads.length, 2, reason: 'attempted membership uses durable keys, not the colliding wal.id');
        expect(
          uploads.map((upload) => upload.$1.single),
          unorderedEquals(['split_a.bin', 'split_b.bin']),
        );
        for (final upload in uploads) {
          final parsed = jsonDecode(upload.$2!) as Map<String, dynamic>;
          expect((parsed['files'] as List).single['name'], upload.$1.single);
        }
      } else {
        expect(uploads.length, 1, reason: 'wal.id attempted membership suppresses the same-id sibling');
      }
    });

    test('root-marked but unclaimable WALs keep legacy wal.id attempted membership', () async {
      final first = diskWal(100, 'partial_a.bin', recordingSessionId: 's1');
      first.captureRoot = root;
      final second = diskWal(100, 'partial_b.bin', recordingSessionId: 's2');
      second.captureRoot = root;
      final local = buildSync();
      local.testWals = [first, second];

      await local.syncAll();

      expect(
        uploads.length,
        1,
        reason: 'a root without the full evidence triple is not claimable, so wal.id suppression is unchanged',
      );
    });
  });

  group('capture evidence run construction', () {
    const darkWrite = bool.fromEnvironment('CAPTURE_EVIDENCE_V1_DARK_WRITE');
    const rootA = '12345678-1234-4234-8234-123456789abc';
    const rootB = 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa';

    void feed(int count, {String? root, FrameSyncKey Function(int index)? keyOf}) {
      for (var i = 0; i < count; i++) {
        sync.onFrameCaptured(
          WalFrame(payload: [i & 0xFF], syncKey: keyOf?.call(i) ?? FrameSyncKey.fromIndex(i)),
          captureRoot: root,
        );
      }
    }

    test('a periodic chunk splits at a root rotation without losing rooted runs', () async {
      const timerStart = 1700000000;
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      final local = LocalWalSyncImpl(
        _MockListener(),
        now: () => DateTime.fromMillisecondsSinceEpoch(timerStart * 1000),
        persistWals: (wals) async {},
        loadWals: () async => <Wal>[],
      );
      addTearDown(local.stop);
      for (var i = 0; i < 1600; i++) {
        local.onFrameCaptured(
          WalFrame(payload: [i & 0xFF], syncKey: FrameSyncKey.fromIndex(i)),
          captureRoot: i < 60 ? rootA : rootB,
        );
      }

      await local.onAudioCodecChanged(BleAudioCodec.pcm16);

      if (darkWrite) {
        expect(local.testWals, hasLength(2));
        final first = local.testWals[0];
        final second = local.testWals[1];
        expect((first.captureRoot, first.sourceFrameStart, first.totalFrames), (rootA, 0, 60));
        expect((second.captureRoot, second.sourceFrameStart, second.totalFrames), (rootB, 0, 40));
        expect(first.timerStart, second.timerStart, reason: 'both runs land inside the same second');
        expect(
          {first.filePath, second.filePath},
          hasLength(2),
          reason: 'same-second runs persist under distinct durable filenames',
        );
        expect(first.filePath, isNotNull);
      } else {
        expect(local.testWals, hasLength(1));
        expect(local.testWals.single.captureRoot, isNull);
        expect(local.testWals.single.totalFrames, 100);
      }
    });

    test('the session tail stores each contiguous run as its own WAL', () async {
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      feed(10, root: rootA);
      feed(10);
      feed(10, root: rootB);

      await sync.finalizeCurrentSession();

      if (darkWrite) {
        expect(sync.testWals, hasLength(3));
        expect(
          sync.testWals.map((wal) => (wal.captureRoot, wal.sourceFrameStart, wal.totalFrames)).toList(),
          [(rootA, 0, 10), (null, null, 10), (rootB, 0, 10)],
        );
        for (final wal in sync.testWals) {
          final path = await Wal.getFilePath(wal.filePath!);
          expect(
            await File(path!).length(),
            50,
            reason: 'each run keeps only its own payload bytes (4-byte length + 1-byte payload per frame)',
          );
        }
      } else {
        expect(sync.testWals, hasLength(1));
        expect(sync.testWals.single.captureRoot, isNull);
        expect(sync.testWals.single.totalFrames, 30);
      }
    });

    test('the pendant tail drain stores each contiguous run as its own WAL', () async {
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      sync.setDeviceInfo('dev', 'Omi');
      FrameSyncKey bleKey(int i) => FrameSyncKey([i & 0xFF, (i >> 8) & 0xFF, 0]);
      feed(10, root: rootA, keyOf: bleKey);
      feed(10, keyOf: bleKey);
      feed(10, root: rootB, keyOf: bleKey);

      await sync.stop();

      if (darkWrite) {
        expect(sync.testWals, hasLength(3));
        expect(
          sync.testWals.map((wal) => (wal.captureRoot, wal.sourceFrameStart, wal.totalFrames)).toList(),
          [(rootA, 0, 10), (null, null, 10), (rootB, 0, 10)],
        );
        expect(sync.testWals.every((wal) => wal.device == 'dev'), isTrue);
      } else {
        expect(sync.testWals, hasLength(1));
        expect(sync.testWals.single.captureRoot, isNull);
        expect(sync.testWals.single.totalFrames, 30);
      }
    });

    test('an ordinal gap inside one root splits the run', () async {
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      WalFrame positioned(int position) => WalFrame(
            payload: [position & 0xFF],
            syncKey: FrameSyncKey.fromIndex(position),
            captureRoot: rootA,
            sourceFramePosition: position,
            sourceClockEpoch: 0,
          );
      sync.testFrames.addAll([positioned(0), positioned(1), positioned(5), positioned(6)]);
      sync.testFrameSynced.addAll([false, false, false, false]);

      await sync.finalizeCurrentSession();

      if (darkWrite) {
        expect(sync.testWals, hasLength(2));
        expect(
          sync.testWals.map((wal) => (wal.captureRoot, wal.sourceFrameStart, wal.totalFrames)).toList(),
          [(rootA, 0, 2), (rootA, 5, 2)],
        );
      } else {
        expect(sync.testWals, hasLength(1));
        expect(sync.testWals.single.captureRoot, isNull);
        expect(sync.testWals.single.totalFrames, 4);
      }
    });

    test('a same-second chunk with a different root becomes a distinct WAL', () async {
      const timerStart = 1700000000;
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      final oldWal = Wal(
        timerStart: timerStart,
        codec: BleAudioCodec.opus,
        seconds: 1,
        totalFrames: 60,
        storage: WalStorage.mem,
        status: WalStatus.miss,
        device: 'omi',
        data: List.generate(60, (_) => [1]),
        captureRoot: rootA,
        sourceFrameStart: 0,
        sourceClockEpoch: 0,
      );
      final uploads = <(List<String>, String?)>[];
      final local = LocalWalSyncImpl(
        _MockListener(),
        now: () => DateTime.fromMillisecondsSinceEpoch((timerStart + 16) * 1000),
        persistWals: (wals) async {},
        loadWals: () async => [oldWal],
        uploadGate: SyncUploadGate(
          limiter: SyncRateLimiter.instance,
          uploader: (files,
              {onUploadProgress,
              conversationId,
              captureEvidence,
              recordingSessionId,
              audioStartSeconds,
              audioEndSeconds,
              claimLiveCapture = false,
              geolocation}) async {
            uploads.add((files.map((file) => file.uri.pathSegments.last).toList(), captureEvidence));
            return UploadFilesResult.queued('job-${uploads.length}');
          },
          fairUseStatusLoader: () async => null,
        ),
      );
      local.start();
      await local.walReady;

      for (var i = 0; i < 1600; i++) {
        local.onFrameCaptured(
          WalFrame(payload: [i & 0xFF], syncKey: FrameSyncKey.fromIndex(i)),
          captureRoot: rootB,
        );
      }
      await local.stop();

      if (darkWrite) {
        expect(local.testWals, hasLength(2), reason: 'the non-contiguous run must not extend the rooted WAL');
        expect((oldWal.captureRoot, oldWal.sourceFrameStart, oldWal.totalFrames), (rootA, 0, 60),
            reason: 'the prior claim is never cleared');
        final fresh = local.testWals.firstWhere((wal) => wal != oldWal);
        expect((fresh.captureRoot, fresh.sourceFrameStart, fresh.totalFrames), (rootB, 0, 100));
        expect({oldWal.filePath, fresh.filePath}, hasLength(2));

        await local.syncAll();
        expect(uploads, hasLength(1));
        expect(uploads.single.$1, hasLength(2), reason: 'both same-second runs reach the uploader');
        final parsed = jsonDecode(uploads.single.$2!) as Map<String, dynamic>;
        expect((parsed['files'] as List).map((f) => f['capture_root']).toSet(), {rootA, rootB});
      } else {
        expect(local.testWals, hasLength(1), reason: 'the colliding chunk extends the in-memory WAL in place');
        expect(oldWal.captureRoot, isNull, reason: 'the unstable root clears the whole WAL claim');
        expect(oldWal.totalFrames, 100);
      }
    });

    test('a same-second entirely legacy chunk extends the in-memory WAL exactly as before', () async {
      const timerStart = 1700000000;
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      final oldWal = Wal(
        timerStart: timerStart,
        codec: BleAudioCodec.opus,
        seconds: 1,
        totalFrames: 60,
        storage: WalStorage.mem,
        status: WalStatus.miss,
        device: 'omi',
        data: List.generate(60, (_) => [1]),
      );
      final local = LocalWalSyncImpl(
        _MockListener(),
        now: () => DateTime.fromMillisecondsSinceEpoch((timerStart + 16) * 1000),
        persistWals: (wals) async {},
        loadWals: () async => [oldWal],
        uploadGate: SyncUploadGate(
          limiter: SyncRateLimiter.instance,
          uploader: (files,
              {onUploadProgress,
              conversationId,
              captureEvidence,
              recordingSessionId,
              audioStartSeconds,
              audioEndSeconds,
              claimLiveCapture = false,
              geolocation}) async {
            return UploadFilesResult.queued('job-1');
          },
          fairUseStatusLoader: () async => null,
        ),
      );
      local.start();
      await local.walReady;

      for (var i = 0; i < 1600; i++) {
        local.onFrameCaptured(WalFrame(payload: [i & 0xFF], syncKey: FrameSyncKey.fromIndex(i)));
      }
      await local.stop();

      expect(local.testWals, hasLength(1), reason: 'a legacy selection keeps the original in-place extension');
      expect(oldWal.captureRoot, isNull);
      expect(oldWal.sourceFrameStart, isNull);
      expect(oldWal.sourceClockEpoch, isNull);
      expect(oldWal.totalFrames, 100, reason: 'non-evident extension keeps the original reset semantics');
      final path = await Wal.getFilePath(oldWal.filePath);
      final bytes = await File(path!).readAsBytes();
      final payloads = <List<int>>[];
      var offset = 0;
      while (offset + 4 <= bytes.length) {
        final length = ByteData.sublistView(Uint8List.fromList(bytes), offset).getUint32(0, Endian.little);
        payloads.add(bytes.sublist(offset + 4, offset + 4 + length));
        offset += 4 + length;
      }
      expect(payloads, hasLength(160), reason: 'payload bytes append exactly like the legacy path');
      expect(payloads.sublist(0, 60).every((frame) => frame.single == 1), isTrue);
      if (darkWrite) {
        expect(captureEvidenceUploadHeader([oldWal], [File(path)]), isNull);
      }
    });

    test('a rooted chunk with an unsupported codec keeps the original single-WAL path', () async {
      const timerStart = 1700000000;
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      final local = LocalWalSyncImpl(
        _MockListener(),
        now: () => DateTime.fromMillisecondsSinceEpoch((timerStart + 16) * 1000),
        persistWals: (wals) async {},
        loadWals: () async => <Wal>[],
        uploadGate: SyncUploadGate(
          limiter: SyncRateLimiter.instance,
          uploader: (files,
              {onUploadProgress,
              conversationId,
              captureEvidence,
              recordingSessionId,
              audioStartSeconds,
              audioEndSeconds,
              claimLiveCapture = false,
              geolocation}) async {
            return UploadFilesResult.queued('job-1');
          },
          fairUseStatusLoader: () async => null,
        ),
      );
      local.start();
      await local.walReady;
      await local.onAudioCodecChanged(BleAudioCodec.pcm8);

      for (var i = 0; i < 1600; i++) {
        local.onFrameCaptured(
          WalFrame(payload: [i & 0xFF], syncKey: FrameSyncKey.fromIndex(i)),
          captureRoot: rootA,
        );
      }
      await local.stop();

      expect(local.testWals, hasLength(1), reason: 'an unsupported codec never enters the run partitioner');
      expect(local.testWals.single.totalFrames, 100);
      if (darkWrite) {
        final wal = local.testWals.single;
        final path = await Wal.getFilePath(wal.filePath);
        expect(captureEvidenceUploadHeader([wal], [File(path!)]), isNull);
      }
    });

    LocalWalSyncImpl pinnedSync(Wal prior) => LocalWalSyncImpl(
          _MockListener(),
          now: () => DateTime.fromMillisecondsSinceEpoch((1700000000 + 16) * 1000),
          persistWals: (wals) async {},
          loadWals: () async => [prior],
          uploadGate: SyncUploadGate(
            limiter: SyncRateLimiter.instance,
            uploader: (files,
                {onUploadProgress,
                conversationId,
                captureEvidence,
                recordingSessionId,
                audioStartSeconds,
                audioEndSeconds,
                claimLiveCapture = false,
                geolocation}) async {
              return UploadFilesResult.queued('job-1');
            },
            fairUseStatusLoader: () async => null,
          ),
        );

    Wal rootedMemWal(int syncedOffset, {WalStatus status = WalStatus.miss}) => Wal(
          timerStart: 1700000000,
          codec: BleAudioCodec.opus,
          seconds: 1,
          totalFrames: 60,
          storage: WalStorage.mem,
          status: status,
          device: 'omi',
          data: List.generate(60, (_) => [1]),
          syncedFrameOffset: syncedOffset,
          captureRoot: rootA,
          sourceFrameStart: 0,
          sourceClockEpoch: 0,
        );

    Future<LocalWalSyncImpl> extendOnce(Wal prior, {required int syncedCount}) async {
      final local = pinnedSync(prior);
      local.start();
      await local.walReady;
      for (var i = 0; i < 1600; i++) {
        final frame = local.onFrameCaptured(
          WalFrame(payload: [i & 0xFF], syncKey: FrameSyncKey.fromIndex(i)),
          captureRoot: rootA,
        );
        if (i < syncedCount) local.markFrameSynced(frame.syncKey);
      }
      await local.stop();
      return local;
    }

    test('a contiguous extension never marks unconfirmed prior frames synced', () async {
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      final prior = rootedMemWal(30);
      final local = await extendOnce(prior, syncedCount: 1600);

      if (darkWrite) {
        expect(local.testWals, hasLength(1));
        expect((prior.captureRoot, prior.sourceFrameStart, prior.totalFrames), (rootA, 0, 160));
        expect(prior.syncedFrameOffset, 30, reason: 'the unconfirmed prefix never advances');
        expect(prior.status, WalStatus.miss);
      } else {
        expect((prior.captureRoot, prior.totalFrames), (rootA, 160));
      }
    });

    test('a confirmed prior prefix plus a confirmed run marks the whole WAL synced', () async {
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      final prior = rootedMemWal(60, status: WalStatus.synced);
      final local = await extendOnce(prior, syncedCount: 1600);

      if (darkWrite) {
        expect(local.testWals, hasLength(1));
        expect((prior.captureRoot, prior.sourceFrameStart, prior.totalFrames), (rootA, 0, 160));
        expect(prior.syncedFrameOffset, 160);
        expect(prior.status, WalStatus.synced);
      } else {
        expect((prior.captureRoot, prior.totalFrames), (rootA, 160));
      }
    });

    test('a confirmed prior prefix plus a partially confirmed run advances exactly', () async {
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      final prior = rootedMemWal(60, status: WalStatus.synced);
      final local = await extendOnce(prior, syncedCount: 50);

      if (darkWrite) {
        expect(local.testWals, hasLength(1));
        expect((prior.captureRoot, prior.sourceFrameStart, prior.totalFrames), (rootA, 0, 160));
        expect(prior.syncedFrameOffset, 110, reason: 'only the confirmed incoming prefix advances the offset');
        expect(prior.status, WalStatus.miss);
      } else {
        expect((prior.captureRoot, prior.totalFrames), (rootA, 160));
      }
    });

    test('a mismatching same-second sibling neither clears claims nor steals the extension', () async {
      const timerStart = 1700000000;
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      final walA = Wal(
        timerStart: timerStart,
        codec: BleAudioCodec.opus,
        seconds: 1,
        totalFrames: 60,
        storage: WalStorage.mem,
        status: WalStatus.miss,
        device: 'omi',
        data: List.generate(60, (_) => [1]),
        captureRoot: rootA,
        sourceFrameStart: 0,
        sourceClockEpoch: 0,
      );
      final walB = Wal(
        timerStart: timerStart,
        codec: BleAudioCodec.opus,
        seconds: 1,
        totalFrames: 60,
        storage: WalStorage.mem,
        status: WalStatus.miss,
        device: 'omi',
        data: List.generate(60, (_) => [2]),
        captureRoot: rootB,
        sourceFrameStart: 200,
        sourceClockEpoch: 0,
      );
      final local = LocalWalSyncImpl(
        _MockListener(),
        now: () => DateTime.fromMillisecondsSinceEpoch((timerStart + 16) * 1000),
        persistWals: (wals) async {},
        loadWals: () async => [walA, walB],
        uploadGate: SyncUploadGate(
          limiter: SyncRateLimiter.instance,
          uploader: (files,
              {onUploadProgress,
              conversationId,
              captureEvidence,
              recordingSessionId,
              audioStartSeconds,
              audioEndSeconds,
              claimLiveCapture = false,
              geolocation}) async {
            return UploadFilesResult.queued('job-1');
          },
          fairUseStatusLoader: () async => null,
        ),
      );
      local.start();
      await local.walReady;

      for (var i = 0; i < 1600; i++) {
        local.onFrameCaptured(
          WalFrame(payload: [i & 0xFF], syncKey: FrameSyncKey.fromIndex(i)),
          captureRoot: rootB,
        );
      }
      await local.stop();

      if (darkWrite) {
        expect(local.testWals, hasLength(2),
            reason: 'the contiguous sibling extends; the mismatching one is untouched');
        expect((walA.captureRoot, walA.sourceFrameStart, walA.totalFrames), (rootA, 0, 60));
        expect((walB.captureRoot, walB.sourceFrameStart, walB.totalFrames), (rootB, 200, 160));
      } else {
        expect(local.testWals, hasLength(2));
        expect(walA.captureRoot, isNull);
        expect(walA.totalFrames, 100);
      }
    });

    test('a subsecond rooted split keeps fractional names and fractional upload bounds', () async {
      const timerStart = 1735689600;
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      final bounds = <(List<String>, double?, double?)>[];
      final local = LocalWalSyncImpl(
        _MockListener(),
        now: () => DateTime.fromMillisecondsSinceEpoch((timerStart + 1) * 1000),
        persistWals: (wals) async {},
        loadWals: () async => <Wal>[],
        uploadGate: SyncUploadGate(
          limiter: SyncRateLimiter.instance,
          uploader: (files,
              {onUploadProgress,
              conversationId,
              captureEvidence,
              recordingSessionId,
              audioStartSeconds,
              audioEndSeconds,
              claimLiveCapture = false,
              geolocation}) async {
            bounds.add((files.map((file) => file.uri.pathSegments.last).toList(), audioStartSeconds, audioEndSeconds));
            return UploadFilesResult.queued('job-${bounds.length}');
          },
          fairUseStatusLoader: () async => null,
        ),
      );
      local.start();
      await local.walReady;

      WalFrame positioned(int position, String root) => WalFrame(
            payload: [position & 0xFF],
            syncKey: FrameSyncKey.fromIndex(position),
            captureRoot: root,
            sourceFramePosition: position,
            sourceClockEpoch: 0,
          );
      local.testFrames.addAll([for (var i = 0; i < 100; i++) positioned(i, i < 60 ? rootA : rootB)]);
      local.testFrameSynced.addAll(List.filled(100, false));

      await local.finalizeCurrentSession();

      if (!darkWrite) {
        expect(local.testWals, hasLength(1));
        expect(local.testWals.single.captureRoot, isNull);
        return;
      }

      expect(local.testWals, hasLength(2));
      final first = local.testWals[0];
      final second = local.testWals[1];
      expect(first.timerStart, timerStart);
      expect(second.timerStart, timerStart);
      expect(first.filePath, endsWith('_$timerStart.bin'));
      expect(second.filePath, endsWith('_$timerStart.6.bin'),
          reason: 'the second run keeps its 0.6s offset in the persisted name');

      final reloaded = Wal.fromJson(second.toJson());
      expect(reloaded.filePath, second.filePath, reason: 'the fractional name survives serialization');

      await local.syncAll();
      expect(bounds, hasLength(1));
      expect(bounds.single.$1, unorderedEquals([first.filePath, second.filePath]));
      expect(bounds.single.$2, timerStart.toDouble());
      expect(bounds.single.$3, (timerStart + 1).toDouble(),
          reason: 'run durations sum through the fractional start, not integer seconds');

      final solo = LocalWalSyncImpl(
        _MockListener(),
        now: () => DateTime.fromMillisecondsSinceEpoch((timerStart + 1) * 1000),
        persistWals: (wals) async {},
        loadWals: () async => <Wal>[],
        uploadGate: SyncUploadGate(
          limiter: SyncRateLimiter.instance,
          uploader: (files,
              {onUploadProgress,
              conversationId,
              captureEvidence,
              recordingSessionId,
              audioStartSeconds,
              audioEndSeconds,
              claimLiveCapture = false,
              geolocation}) async {
            bounds.add((files.map((file) => file.uri.pathSegments.last).toList(), audioStartSeconds, audioEndSeconds));
            return UploadFilesResult.queued('job-${bounds.length}');
          },
          fairUseStatusLoader: () async => null,
        ),
      );
      solo.start();
      await solo.walReady;
      solo.testWals = [reloaded];
      await solo.syncWal(wal: solo.testWals.single);

      expect(bounds.last.$2, timerStart + 0.6, reason: 'syncWal derives the fractional start from the filename');
      expect(bounds.last.$3, (timerStart + 1).toDouble());
    });

    test('a claimable filename collision inserts the discriminator before the timestamp token', () async {
      const timerStart = 1735689600;
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      final uploaded = <(List<String>, String?)>[];
      final local = LocalWalSyncImpl(
        _MockListener(),
        now: () => DateTime.fromMillisecondsSinceEpoch((timerStart + 1) * 1000),
        persistWals: (wals) async {},
        loadWals: () async => <Wal>[],
        uploadGate: SyncUploadGate(
          limiter: SyncRateLimiter.instance,
          uploader: (files,
              {onUploadProgress,
              conversationId,
              captureEvidence,
              recordingSessionId,
              audioStartSeconds,
              audioEndSeconds,
              claimLiveCapture = false,
              geolocation}) async {
            uploaded.add((files.map((file) => file.uri.pathSegments.last).toList(), captureEvidence));
            return UploadFilesResult.queued('job-1');
          },
          fairUseStatusLoader: () async => null,
        ),
      );
      local.start();
      await local.walReady;

      for (var round = 0; round < 2; round++) {
        local.testFrames.addAll([
          for (var i = 0; i < 100; i++)
            WalFrame(
              payload: [i & 0xFF],
              syncKey: FrameSyncKey.fromIndex(i),
              captureRoot: rootA,
              sourceFramePosition: i,
              sourceClockEpoch: round,
            ),
        ]);
        local.testFrameSynced.addAll(List.filled(100, false));
        await local.finalizeCurrentSession();
      }

      if (!darkWrite) {
        return;
      }
      expect(local.testWals, hasLength(2));
      final wal = local.testWals.last;
      expect(
        wal.filePath,
        matches(RegExp(r'_u\d+_\d+\.bin$')),
        reason: 'the _u<seq> discriminator stays ahead of the terminal timestamp token',
      );
      await local.syncAll();
      final names = uploaded.expand((upload) => upload.$1).toList();
      expect(names, contains(wal.filePath));
      final parsed = jsonDecode(uploaded.single.$2!) as Map<String, dynamic>;
      expect(
        (parsed['files'] as List).map((f) => f['name']).toSet(),
        containsAll(names),
        reason: 'claim names match the collision-safe filenames actually uploaded',
      );
    });

    void expectSubsecondSplit(List<Wal> wals, {int secondSourceStart = 70}) {
      const t = 1735689600;
      expect(wals, hasLength(2));
      final first = wals[0];
      final second = wals[1];
      expect((first.captureRoot, first.sourceFrameStart, first.totalFrames), (rootA, 0, 70));
      expect((second.captureRoot, second.sourceFrameStart, second.totalFrames), (rootB, secondSourceStart, 10));
      expect(first.timerStart, t, reason: 'floor(t + 0.4)');
      expect(second.timerStart, t + 1, reason: 'floor(t + 1.1)');
      expect(first.filePath, endsWith('_$t.4.bin'));
      expect(second.filePath, endsWith('_${t + 1}.1.bin'));
      expect(Wal.fromJson(second.toJson()).filePath, second.filePath,
          reason: 'the fractional name survives serialization');
    }

    void expectSubsecondBounds(List<Wal> wals, List<(List<String>, double?, double?)> bounds) {
      const t = 1735689600;
      final first = wals[0];
      final second = wals[1];
      expect(bounds.single.$1, unorderedEquals([first.filePath, second.filePath]));
      expect(bounds.single.$2, closeTo(t + 0.4, 1e-6));
      expect(bounds.single.$3, closeTo(t + 1.2, 1e-6));
    }

    LocalWalSyncImpl boundsSync(List<(List<String>, double?, double?)> bounds, DateTime Function() now) =>
        LocalWalSyncImpl(
          _MockListener(),
          now: now,
          persistWals: (wals) async {},
          loadWals: () async => <Wal>[],
          uploadGate: SyncUploadGate(
            limiter: SyncRateLimiter.instance,
            uploader: (files,
                {onUploadProgress,
                conversationId,
                captureEvidence,
                recordingSessionId,
                audioStartSeconds,
                audioEndSeconds,
                claimLiveCapture = false,
                geolocation}) async {
              bounds
                  .add((files.map((file) => file.uri.pathSegments.last).toList(), audioStartSeconds, audioEndSeconds));
              return UploadFilesResult.queued('job-${bounds.length}');
            },
            fairUseStatusLoader: () async => null,
          ),
        );

    List<WalFrame> splitFrames({FrameSyncKey Function(int index)? keyOf}) => [
          for (var i = 0; i < 80; i++)
            WalFrame(
              payload: [i & 0xFF],
              syncKey: keyOf?.call(i) ?? FrameSyncKey.fromIndex(i),
              captureRoot: i < 70 ? rootA : rootB,
              sourceFramePosition: i,
              sourceClockEpoch: 0,
            ),
        ];

    test('a precise session end keeps subsecond run starts in names and bounds', () async {
      const t = 1735689600;
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      final bounds = <(List<String>, double?, double?)>[];
      final local = boundsSync(bounds, () => DateTime.fromMillisecondsSinceEpoch(t * 1000 + 1200));
      addTearDown(local.stop);
      local.start();
      await local.walReady;

      local.testFrames.addAll(splitFrames());
      local.testFrameSynced.addAll(List.filled(80, false));
      await local.finalizeCurrentSession();

      if (!darkWrite) {
        expect(local.testWals, hasLength(1));
        expect(local.testWals.single.captureRoot, isNull);
        return;
      }
      expectSubsecondSplit(local.testWals);
      await local.syncAll();
      expectSubsecondBounds(local.testWals, bounds);
    });

    test('a precise chunk end keeps subsecond run starts through the delayed boundary', () async {
      const t = 1735689600;
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      final bounds = <(List<String>, double?, double?)>[];
      final local = boundsSync(bounds, () => DateTime.fromMillisecondsSinceEpoch(t * 1000 + 16200));

      for (var i = 0; i < 1580; i++) {
        local.onFrameCaptured(
          WalFrame(payload: [i & 0xFF], syncKey: FrameSyncKey.fromIndex(i)),
          captureRoot: i < 70 ? rootA : rootB,
        );
      }
      await local.stop();

      if (!darkWrite) {
        return;
      }
      await local.syncAll();
      final chunked = local.testWals.where((wal) => wal.captureRoot != null).toList();
      expect(chunked, hasLength(2), reason: 'the delayed chunk boundary preserves both rooted runs');
      expectSubsecondSplit(chunked, secondSourceStart: 0);
      expectSubsecondBounds(chunked, bounds);
    });

    test('a precise pendant drain keeps subsecond run starts in names and bounds', () async {
      const t = 1735689600;
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      final bounds = <(List<String>, double?, double?)>[];
      final local = boundsSync(bounds, () => DateTime.fromMillisecondsSinceEpoch(t * 1000 + 1200));
      local.start();
      await local.walReady;
      local.setDeviceInfo('pendant1', 'Omi');

      local.testFrames.addAll(splitFrames(keyOf: (i) => FrameSyncKey([i & 0xFF, (i >> 8) & 0xFF, 0])));
      local.testFrameSynced.addAll(List.filled(80, false));
      await local.stop();

      if (!darkWrite) {
        return;
      }
      await local.syncAll();
      expectSubsecondSplit(local.testWals);
      expectSubsecondBounds(local.testWals, bounds);
    });
  });
}
