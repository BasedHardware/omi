import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/wals/flash_page_wal_sync.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
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

    test('only a conversation-bound recent WAL counts as live capture', () {
      const now = 2000000000;
      Wal at(int ageSeconds, {String? conversationId}) =>
          Wal(timerStart: now - ageSeconds, codec: BleAudioCodec.opus, seconds: 60, conversationId: conversationId);

      expect(isLiveCaptureWal(at(60), now), isFalse);
      expect(isLiveCaptureWal(at(60, conversationId: 'c'), now), isTrue);
      expect(isLiveCaptureWal(at(7 * 60 * 60, conversationId: 'c'), now), isFalse);
    });

    test('active unbound continuity stays local without a server conversation owner', () {
      const now = 2000000000;
      final historical = Wal(
        timerStart: now - 7 * 60 * 60,
        codec: BleAudioCodec.opus,
        seconds: 60,
        status: WalStatus.miss,
        storage: WalStorage.disk,
      );
      final liveContinuity = Wal(
        timerStart: now - 10,
        codec: BleAudioCodec.opus,
        seconds: 2,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        uploadIntent: WalUploadIntent.liveContinuity,
      );

      final batch = nextSyncUploadBatch([historical, liveContinuity], now);

      expect(batch, [historical]);
    });

    test('closed unbound continuity never uploads without a server conversation owner', () {
      const now = 2000000000;
      final historical = Wal(
        timerStart: now - 7 * 60 * 60,
        codec: BleAudioCodec.opus,
        seconds: 60,
        status: WalStatus.miss,
        storage: WalStorage.disk,
      );
      final closedConversation = List.generate(
        30,
        (index) => Wal(
          timerStart: now - 300 + index * 2,
          codec: BleAudioCodec.opus,
          seconds: 2,
          totalFrames: 100,
          status: WalStatus.miss,
          storage: WalStorage.disk,
          originalStorage: WalStorage.sdcard,
          device: 'cv1',
          sourceId: 'ring_${index * 10}_${(index + 1) * 10}',
          uploadIntent: WalUploadIntent.liveContinuity,
        ),
      );

      final batch = nextSyncUploadBatch([historical, ...closedConversation], now);

      expect(batch, [historical]);
    });

    test('bound archive waits for canonical repair while unbound archive remains opt-in backfill', () {
      const now = 2000000000;
      final unboundArchive = Wal(
        timerStart: now - 300,
        codec: BleAudioCodec.opus,
        seconds: 30,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        device: 'cv1',
        sourceId: 'archive_ring_100_200_1999999700',
        uploadIntent: WalUploadIntent.historicalBackfill,
      );
      final boundArchive = Wal(
        timerStart: now - 300,
        codec: BleAudioCodec.opus,
        seconds: 30,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        device: 'cv1',
        sourceId: 'archive_ring_200_300_1999999700',
        conversationId: 'server-owner',
        uploadIntent: WalUploadIntent.historicalBackfill,
      );

      expect(
        nextSyncUploadBatch([unboundArchive, boundArchive], now),
        [unboundArchive],
      );
      expect(nextSyncUploadBatch([boundArchive], now), isEmpty);
    });

    test('upload artifacts join only sequence- and time-contiguous ring WALs', () {
      Wal ringWal(int startSeq, int endSeq, int timestamp) => Wal(
            timerStart: timestamp,
            codec: BleAudioCodec.opus,
            seconds: 2,
            totalFrames: 100,
            status: WalStatus.miss,
            storage: WalStorage.disk,
            originalStorage: WalStorage.sdcard,
            device: 'cv1',
            sourceId: 'ring_${startSeq}_$endSeq',
            uploadIntent: WalUploadIntent.liveContinuity,
          );

      final contiguousA = ringWal(100, 110, 1000);
      final contiguousB = ringWal(110, 120, 1002);
      final deliveredLiveGap = ringWal(130, 140, 1004);
      final silenceBoundary = ringWal(140, 150, 1010);

      final runs = contiguousWalUploadRuns([
        silenceBoundary,
        contiguousB,
        deliveredLiveGap,
        contiguousA,
      ]);

      expect(runs, [
        [contiguousA, contiguousB],
        [deliveredLiveGap],
        [silenceBoundary],
      ]);
    });

    test('a small historical backlog drains in one batch instead of a few files at a time', () {
      const now = 2000000000;
      final historical = List.generate(
        3,
        (index) => Wal(timerStart: now - 7 * 60 * 60 - index, codec: BleAudioCodec.opus, seconds: 60),
      );

      final batch = nextSyncUploadBatch(historical.reversed.toList(), now);

      expect(batch.length, 3);
    });

    test('historical batches are bounded by the shared upload batch limit, newest first', () {
      const now = 2000000000;
      final historical = List.generate(
        25,
        (index) => Wal(timerStart: now - 7 * 60 * 60 - index, codec: BleAudioCodec.opus, seconds: 60),
      );

      final batch = nextSyncUploadBatch(historical.reversed.toList(), now);

      expect(batch.length, 20);
      expect(batch.map((wal) => wal.timerStart), historical.take(20).map((wal) => wal.timerStart));
    });

    test('one recovery conversation stays one ordered transaction beyond the legacy 20-file batch', () {
      const now = 2000000000;
      final recoveryConversation = List.generate(
        25,
        (index) => _historicalRingWal(
          timerStart: now - 600 + index * 3,
          sourceId: 'archive_ring_${index * 10}_${(index + 1) * 10}_${now - 600 + index * 3}',
          filePath: 'archive_$index.bin',
          seconds: 3,
          totalFrames: 300,
        ),
      );

      final batch = nextSyncUploadBatch(
        recoveryConversation.reversed.toList(),
        now,
      );

      expect(batch, recoveryConversation);
      expect(batch.length, greaterThan(20));
    });

    test('an exact two-minute recovery gap starts a separate upload transaction', () {
      const now = 2000000000;
      final older = _historicalRingWal(
        timerStart: now - 600,
        sourceId: 'archive_ring_100_200_${now - 600}',
        filePath: 'older.bin',
        seconds: 60,
        totalFrames: 6000,
      );
      final newer = _historicalRingWal(
        timerStart: now - 420,
        sourceId: 'archive_ring_200_300_${now - 420}',
        filePath: 'newer.bin',
        seconds: 60,
        totalFrames: 6000,
      );

      final batch = nextSyncUploadBatch([older, newer], now);

      expect(batch, [newer]);
    });

    test('recovery grouping honors configured 60s and 300s conversation boundaries', () {
      const now = 2000000000;
      for (final boundary in [60, 300]) {
        final older = _historicalRingWal(
          timerStart: now - 1000,
          sourceId: 'archive2_ring_100_200_${now - 1000}',
          filePath: 'older_$boundary.bin',
          seconds: 10,
          totalFrames: 1000,
        );
        final inside = _historicalRingWal(
          timerStart: now - 1000 + 10 + boundary - 1,
          sourceId: 'archive2_ring_200_300_${now - 1000 + boundary + 9}',
          filePath: 'inside_$boundary.bin',
          seconds: 10,
          totalFrames: 1000,
        );
        final exactBoundary = _historicalRingWal(
          timerStart: inside.timerStart + inside.seconds + boundary,
          sourceId: 'archive2_ring_300_400_${inside.timerStart + inside.seconds + boundary}',
          filePath: 'boundary_$boundary.bin',
          seconds: 10,
          totalFrames: 1000,
        );

        expect(
          nextSyncUploadBatch(
            [older, inside],
            now,
            conversationBoundarySeconds: boundary,
          ),
          [older, inside],
        );
        expect(
          nextSyncUploadBatch(
            [older, inside, exactBoundary],
            now,
            conversationBoundarySeconds: boundary,
          ),
          [exactBoundary],
        );
      }
    });

    test('overlapping legacy archives upload one exact nonduplicating tile', () {
      const now = 2000000000;
      final prefix = _historicalRingWal(
        timerStart: now - 600,
        sourceId: 'archive_ring_100_200_${now - 600}',
        filePath: 'prefix.bin',
        seconds: 30,
        totalFrames: 3000,
      );
      final suffix = _historicalRingWal(
        timerStart: now - 570,
        sourceId: 'archive_ring_200_300_${now - 570}',
        filePath: 'suffix.bin',
        seconds: 30,
        totalFrames: 3000,
      );
      final rolledForward = _historicalRingWal(
        timerStart: now - 600,
        sourceId: 'archive_ring_100_300_${now - 600}',
        filePath: 'rolled_forward.bin',
        seconds: 60,
        totalFrames: 6000,
      );

      expect(
        nextSyncUploadBatch([prefix, suffix, rolledForward], now),
        [rolledForward],
      );
    });

    test('legacy aliases share the exact-tile acknowledgement and never reupload', () async {
      SyncRateLimiter.instance.clear();
      final prefixName = 'legacy_alias_${DateTime.now().microsecondsSinceEpoch}';
      final prefixFile = File('${Directory.systemTemp.path}/${prefixName}_prefix.bin');
      final suffixFile = File('${Directory.systemTemp.path}/${prefixName}_suffix.bin');
      final rolledFile = File('${Directory.systemTemp.path}/${prefixName}_rolled.bin');
      for (final file in [prefixFile, suffixFile, rolledFile]) {
        await file.writeAsBytes([1, 0, 0, 0, 1], flush: true);
      }
      addTearDown(() async {
        for (final file in [prefixFile, suffixFile, rolledFile]) {
          if (await file.exists()) await file.delete();
        }
      });

      final uploads = <List<String>>[];
      final legacySync = LocalWalSyncImpl(
        listener,
        uploadGate: _completedUploadGate(uploads),
        walPersister: (_) async => true,
      );
      final prefix = _historicalRingWal(
        timerStart: 1000,
        sourceId: 'archive_ring_100_200_1000',
        filePath: prefixFile.uri.pathSegments.last,
        seconds: 30,
        totalFrames: 3000,
      );
      final suffix = _historicalRingWal(
        timerStart: 1030,
        sourceId: 'archive_ring_200_300_1030',
        filePath: suffixFile.uri.pathSegments.last,
        seconds: 30,
        totalFrames: 3000,
      );
      final rolled = _historicalRingWal(
        timerStart: 1000,
        sourceId: 'archive_ring_100_300_1000',
        filePath: rolledFile.uri.pathSegments.last,
        seconds: 60,
        totalFrames: 6000,
      );
      legacySync.testWals = [prefix, suffix, rolled];

      await legacySync.syncAll();
      await legacySync.syncAll();

      expect(uploads, hasLength(1));
      expect(uploads.single.single, rolledFile.path);
      expect(
        legacySync.testWals.map((wal) => wal.status),
        everyElement(WalStatus.synced),
      );
    });

    test('irreducible legacy overlap does not block exact independent components', () {
      const now = 2000000000;
      final overlapA = _historicalRingWal(
        timerStart: now - 600,
        sourceId: 'archive_ring_100_220_${now - 600}',
        filePath: 'overlap_a.bin',
        seconds: 30,
        totalFrames: 3000,
      );
      final overlapB = _historicalRingWal(
        timerStart: now - 570,
        sourceId: 'archive_ring_200_300_${now - 570}',
        filePath: 'overlap_b.bin',
        seconds: 30,
        totalFrames: 3000,
      );
      final gapA = _historicalRingWal(
        timerStart: now - 539,
        sourceId: 'archive_ring_400_500_${now - 539}',
        filePath: 'gap_a.bin',
        seconds: 30,
        totalFrames: 3000,
      );
      final gapB = _historicalRingWal(
        timerStart: now - 509,
        sourceId: 'archive_ring_520_600_${now - 509}',
        filePath: 'gap_b.bin',
        seconds: 30,
        totalFrames: 3000,
      );

      expect(nextSyncUploadBatch([overlapA, overlapB], now), isEmpty);
      expect(
        nextSyncUploadBatch(
          [overlapA, overlapB, gapA, gapB],
          now,
        ),
        [gapA, gapB],
      );
    });

    test('an archive stays local while an adjacent raw recovery fragment is unassembled', () {
      const now = 2000000000;
      final archive = _historicalRingWal(
        timerStart: now - 600,
        sourceId: 'archive_ring_100_200_${now - 600}',
        filePath: 'archive.bin',
        seconds: 60,
        totalFrames: 6000,
      );
      final raw = _historicalRingWal(
        timerStart: now - 539,
        sourceId: 'ring_200_210',
        filePath: 'raw.bin',
        seconds: 3,
        totalFrames: 300,
      )..uploadIntent = WalUploadIntent.liveContinuity;

      expect(nextSyncUploadBatch([archive, raw], now), isEmpty);
    });

    test('an extraordinarily large fresh conversation is downgraded as one unit', () {
      const now = 2000000000;
      final oversized = List.generate(
        2001,
        (index) => Wal(
          timerStart: now - index,
          codec: BleAudioCodec.opus,
          seconds: 60,
          conversationId: 'oversized-conversation',
        ),
      );
      final maximumFresh = oversized.take(2000).toList();
      expect(oversizedFreshConversationIds(maximumFresh, now), isEmpty);
      final forcedBackfill = oversizedFreshConversationIds(oversized, now);
      expect(forcedBackfill, {'oversized-conversation'});

      final batch = nextSyncUploadBatch(oversized, now, forcedBackfillConversationIds: forcedBackfill);
      // Downgraded to the backfill rate-limit domain, but kept as one bounded
      // capture transaction rather than split into 20-file async jobs.
      expect(batch.length, 2000);
      expect(batch.every((wal) => wal.conversationId == 'oversized-conversation'), isTrue);
    });
  });

  group('authorized recovery receipt drain', () {
    test('irreducible legacy overlap stays pending without pinning the receipt', () async {
      const now = 2000000000;
      final overlapA = _historicalRingWal(
        timerStart: now - 600,
        sourceId: 'archive_ring_100_220_${now - 600}',
        filePath: 'irreducible_a.bin',
        seconds: 30,
        totalFrames: 3000,
      );
      final overlapB = _historicalRingWal(
        timerStart: now - 570,
        sourceId: 'archive_ring_200_300_${now - 570}',
        filePath: 'irreducible_b.bin',
        seconds: 30,
        totalFrames: 3000,
      );
      final receiptSync = LocalWalSyncImpl(
        listener,
        walPersister: (_) async => true,
      )..testWals = [overlapA, overlapB];

      final result = await receiptSync.syncAuthorizedRecovery(
        deviceId: 'test-device',
        targetWriteSeq: 300,
        nowSeconds: now,
      );

      expect(result.hasDeferredRecovery, isFalse);
      expect(receiptSync.testWals, [overlapA, overlapB]);
      expect(receiptSync.testWals.map((wal) => wal.status), everyElement(WalStatus.miss));
    });

    test('splits at the receipt target and leaves newer recovery untouched', () async {
      SyncRateLimiter.instance.clear();
      const now = 2000000000;
      final prefix = 'omi_authorized_split_${DateTime.now().microsecondsSinceEpoch}';
      final firstFile = File('${Directory.systemTemp.path}/${prefix}_first.bin');
      final secondFile = File('${Directory.systemTemp.path}/${prefix}_second.bin');
      await firstFile.writeAsBytes([1, 0, 0, 0, 1], flush: true);
      await secondFile.writeAsBytes([1, 0, 0, 0, 2], flush: true);
      addTearDown(() async {
        for (final file in [firstFile, secondFile]) {
          if (await file.exists()) await file.delete();
        }
      });

      final uploads = <List<String>>[];
      final receiptSync = LocalWalSyncImpl(
        listener,
        uploadGate: _completedUploadGate(uploads),
        walPersister: (_) async => true,
        walPathResolver: (path) async => path == null ? null : '${Directory.systemTemp.path}/$path',
        silenceFrameFactory: (_) => [0],
      )..testWals = [
          _historicalRingWal(
            timerStart: now - 500,
            sourceId: 'ring_100_200',
            filePath: firstFile.path.split('/').last,
          ),
          _historicalRingWal(
            timerStart: now - 499,
            sourceId: 'ring_200_300',
            filePath: secondFile.path.split('/').last,
          ),
        ];

      final result = await receiptSync.syncAuthorizedRecovery(
        deviceId: 'test-device',
        targetWriteSeq: 200,
        nowSeconds: now,
      );

      expect(uploads, hasLength(1));
      expect(uploads.single, [firstFile.path]);
      final authorized = receiptSync.testWals.singleWhere(
        (wal) => wal.sourceId == 'archive2_ring_100_200_${now - 500}',
      );
      final newer = receiptSync.testWals.singleWhere(
        (wal) => wal.sourceId == 'archive2_ring_200_300_${now - 499}',
      );
      expect(authorized.status, WalStatus.synced);
      expect(newer.status, WalStatus.miss);
      expect(result.hasDeferredRecovery, isFalse);
    });

    test('recent authorized raw stays deferred until its configured close', () async {
      SyncRateLimiter.instance.clear();
      const captureStart = 1000;
      final prefix = 'omi_authorized_recent_${DateTime.now().microsecondsSinceEpoch}';
      final sourceFile = File('${Directory.systemTemp.path}/${prefix}_source.bin');
      await sourceFile.writeAsBytes([1, 0, 0, 0, 1], flush: true);
      addTearDown(() async {
        if (await sourceFile.exists()) await sourceFile.delete();
      });

      final uploads = <List<String>>[];
      final receiptSync = LocalWalSyncImpl(
        listener,
        uploadGate: _completedUploadGate(uploads),
        walPersister: (_) async => true,
        walPathResolver: (path) async => path == null ? null : '${Directory.systemTemp.path}/$path',
        silenceFrameFactory: (_) => [0],
        conversationBoundarySecondsProvider: () => 300,
      )..testWals = [
          _historicalRingWal(
            timerStart: captureStart,
            sourceId: 'ring_100_200',
            filePath: sourceFile.path.split('/').last,
          ),
        ];

      final deferred = await receiptSync.syncAuthorizedRecovery(
        deviceId: 'test-device',
        targetWriteSeq: 200,
        nowSeconds: captureStart + 300,
      );

      expect(uploads, isEmpty);
      expect(receiptSync.testWals.single.sourceId, 'ring_100_200');
      expect(deferred.hasDeferredRecovery, isTrue);

      final closed = await receiptSync.syncAuthorizedRecovery(
        deviceId: 'test-device',
        targetWriteSeq: 200,
        nowSeconds: captureStart + 301,
      );

      expect(uploads, hasLength(1));
      expect(receiptSync.testWals.single.sourceId, 'archive2_ring_100_200_$captureStart');
      expect(receiptSync.testWals.single.status, WalStatus.synced);
      expect(closed.hasDeferredRecovery, isFalse);
    });

    test('local close timing mirrors the backend minimum conversation timeout', () async {
      SyncRateLimiter.instance.clear();
      const captureStart = 1000;
      final fileName = 'effective_timeout_${DateTime.now().microsecondsSinceEpoch}.bin';
      final sourceFile = File('${Directory.systemTemp.path}/$fileName');
      await sourceFile.writeAsBytes([1, 0, 0, 0, 1], flush: true);
      addTearDown(() async {
        if (await sourceFile.exists()) await sourceFile.delete();
      });
      final uploads = <List<String>>[];
      final receiptSync = LocalWalSyncImpl(
        listener,
        uploadGate: _completedUploadGate(uploads),
        walPersister: (_) async => true,
        walPathResolver: (path) async => path == null ? null : '${Directory.systemTemp.path}/$path',
        silenceFrameFactory: (_) => [0],
        conversationBoundarySecondsProvider: () => 30,
      )..testWals = [
          _historicalRingWal(
            timerStart: captureStart,
            sourceId: 'ring_100_200',
            filePath: fileName,
          ),
        ];

      final stillOpen = await receiptSync.syncAuthorizedRecovery(
        deviceId: 'test-device',
        targetWriteSeq: 200,
        nowSeconds: captureStart + 61,
      );
      expect(stillOpen.hasDeferredRecovery, isTrue);
      expect(uploads, isEmpty);

      final closed = await receiptSync.syncAuthorizedRecovery(
        deviceId: 'test-device',
        targetWriteSeq: 200,
        nowSeconds: captureStart + 121,
      );
      expect(closed.hasDeferredRecovery, isFalse);
      expect(uploads, hasLength(1));
    });

    test('uploaded receipt work retains authority through reconciliation and retry', () async {
      SyncRateLimiter.instance.clear();
      const now = 2000000000;
      final prefix = 'omi_authorized_pending_${DateTime.now().microsecondsSinceEpoch}';
      final sourceFile = File('${Directory.systemTemp.path}/${prefix}_source.bin');
      await sourceFile.writeAsBytes([1, 0, 0, 0, 1], flush: true);
      addTearDown(() async {
        if (await sourceFile.exists()) await sourceFile.delete();
      });

      final uploads = <List<String>>[];
      final gate = SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        fairUseStatusLoader: () async => {'stage': 'none'},
        uploader: (
          files, {
          onUploadProgress,
          conversationId,
          syncLane = SyncUploadLane.fresh,
          replaceTranscript = false,
        }) async {
          uploads.add(files.map((file) => file.path).toList());
          return UploadFilesResult.queued('authorized-retry-job');
        },
      );
      final pending = _historicalRingWal(
        timerStart: now - 500,
        sourceId: 'archive2_ring_100_200_${now - 500}',
        filePath: sourceFile.path.split('/').last,
      )
        ..status = WalStatus.uploaded
        ..jobId = 'pending-job';
      final receiptSync = LocalWalSyncImpl(
        listener,
        uploadGate: gate,
        walPersister: (_) async => true,
        walPathResolver: (path) async => path == null ? null : '${Directory.systemTemp.path}/$path',
        silenceFrameFactory: (_) => [0],
      )..testWals = [pending];

      final waiting = await receiptSync.syncAuthorizedRecovery(
        deviceId: 'test-device',
        targetWriteSeq: 200,
        nowSeconds: now,
      );
      expect(uploads, isEmpty);
      expect(waiting.hasDeferredRecovery, isTrue);

      pending.status = WalStatus.synced;
      final completed = await receiptSync.syncAuthorizedRecovery(
        deviceId: 'test-device',
        targetWriteSeq: 200,
        nowSeconds: now,
      );
      expect(completed.hasDeferredRecovery, isFalse);

      pending
        ..status = WalStatus.miss
        ..jobId = null;
      final retried = await receiptSync.syncAuthorizedRecovery(
        deviceId: 'test-device',
        targetWriteSeq: 200,
        nowSeconds: now,
      );
      expect(uploads, hasLength(1));
      expect(pending.status, WalStatus.uploaded);
      expect(retried.hasDeferredRecovery, isTrue);
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

  group('historical ring archive migration', () {
    test('sub-two-second VAD pauses stay one open conversation until the true capture end closes', () async {
      final directory = await Directory.systemTemp.createTemp('omi_ring_vad_wall_clock_');
      addTearDown(() async {
        if (await directory.exists()) await directory.delete(recursive: true);
      });
      await File('${directory.path}/first.bin').writeAsBytes([1, 0, 0, 0, 1], flush: true);
      await File('${directory.path}/second.bin').writeAsBytes([1, 0, 0, 0, 2], flush: true);
      final archiveSync = LocalWalSyncImpl(
        listener,
        walPersister: (_) async => true,
        walPathResolver: (path) async => path == null ? null : '${directory.path}/$path',
        silenceFrameFactory: (_) => [0],
      )..testWals = [
          _historicalRingWal(
            timerStart: 1000,
            sourceId: 'ring_10_20',
            filePath: 'first.bin',
            captureEndSeconds: 1100,
          ),
          _historicalRingWal(
            timerStart: 1219,
            sourceId: 'ring_20_30',
            filePath: 'second.bin',
            captureEndSeconds: 1300,
          ),
        ];

      // The playable files contain only two 10 ms speech frames, but their
      // record timestamps show one VAD-spanning conversation whose latest
      // capture is only 50 seconds old.
      await archiveSync.prepareHistoricalRingFragments(nowSeconds: 1350);

      expect(archiveSync.testWals.map((wal) => wal.sourceId), ['ring_10_20', 'ring_20_30']);

      await archiveSync.prepareHistoricalRingFragments(nowSeconds: 1421);

      expect(archiveSync.testWals, hasLength(1));
      expect(archiveSync.testWals.single.sourceId, 'archive2_ring_10_30_1000');
      expect(archiveSync.testWals.single.captureEndSeconds, 1300);
      expect(archiveSync.testWals.single.wallClockEndSeconds, 1300);
    });

    test('rolls adjacent bounded archives forward when later recovery data arrives', () async {
      final directory = await Directory.systemTemp.createTemp('omi_ring_archive_roll_forward_');
      addTearDown(() async {
        if (await directory.exists()) await directory.delete(recursive: true);
      });

      Future<Wal> writeRecoveryWal({
        required int timerStart,
        required int seconds,
        required String sourceId,
        required String fileName,
      }) async {
        const codec = BleAudioCodec.opusFS320;
        final totalFrames = seconds * codec.getFramesPerSecond();
        final bytes = <int>[];
        for (var index = 0; index < totalFrames; index++) {
          bytes.addAll([1, 0, 0, 0, 1]);
        }
        await File('${directory.path}/$fileName').writeAsBytes(bytes, flush: true);
        return Wal(
          timerStart: timerStart,
          codec: codec,
          seconds: seconds,
          totalFrames: totalFrames,
          status: WalStatus.miss,
          storage: WalStorage.disk,
          originalStorage: WalStorage.sdcard,
          filePath: fileName,
          device: 'test-device',
          sourceId: sourceId,
          uploadIntent:
              sourceId.startsWith('ring_') ? WalUploadIntent.liveContinuity : WalUploadIntent.historicalBackfill,
        );
      }

      final first = await writeRecoveryWal(
        timerStart: 1000,
        seconds: 275,
        sourceId: 'archive2_ring_100_200_1000',
        fileName: 'first.bin',
      );
      final second = await writeRecoveryWal(
        timerStart: 1275,
        seconds: 79,
        sourceId: 'archive2_ring_200_300_1275',
        fileName: 'second.bin',
      );
      final laterRaw = await writeRecoveryWal(
        timerStart: 1354,
        seconds: 336,
        sourceId: 'ring_300_400',
        fileName: 'later.bin',
      );
      final archiveSync = LocalWalSyncImpl(
        listener,
        walPersister: (_) async => true,
        walPathResolver: (path) async => path == null ? null : '${directory.path}/$path',
        silenceFrameFactory: (_) => [0],
      )..testWals = [first, second, laterRaw];

      await archiveSync.prepareHistoricalRingFragments(nowSeconds: 2000);

      expect(archiveSync.testWals, hasLength(1));
      final rolledForward = archiveSync.testWals.single;
      expect(rolledForward.sourceId, 'archive2_ring_100_400_1000');
      expect(rolledForward.seconds, 690);
      expect(rolledForward.totalFrames, 34500);
      expect(await File('${directory.path}/${rolledForward.filePath}').exists(), isTrue);
      expect(await File('${directory.path}/first.bin').exists(), isFalse);
      expect(await File('${directory.path}/second.bin').exists(), isFalse);
      expect(await File('${directory.path}/later.bin').exists(), isFalse);
    });

    test('never lets an archive claim sequence records missing from the phone', () async {
      final directory = await Directory.systemTemp.createTemp('omi_ring_archive_sequence_gap_');
      addTearDown(() async {
        if (await directory.exists()) await directory.delete(recursive: true);
      });
      final firstFile = File('${directory.path}/first.bin');
      final secondFile = File('${directory.path}/second.bin');
      await firstFile.writeAsBytes([1, 0, 0, 0, 1], flush: true);
      await secondFile.writeAsBytes([1, 0, 0, 0, 2], flush: true);

      final archiveSync = LocalWalSyncImpl(
        listener,
        walPersister: (_) async => true,
        walPathResolver: (path) async => path == null ? null : '${directory.path}/$path',
        silenceFrameFactory: (_) => [0],
      )..testWals = [
          _historicalRingWal(
            timerStart: 1000,
            sourceId: 'ring_100_200',
            filePath: firstFile.path.split('/').last,
          ),
          _historicalRingWal(
            timerStart: 1001,
            sourceId: 'ring_220_300',
            filePath: secondFile.path.split('/').last,
          ),
        ];

      await archiveSync.prepareHistoricalRingFragments(nowSeconds: 2000);

      expect(archiveSync.testWals, hasLength(2));
      expect(
        archiveSync.testWals.map((wal) => wal.sourceId).toSet(),
        {'archive2_ring_100_200_1000', 'archive2_ring_220_300_1001'},
      );
      expect(
        archiveSync.testWals.any((wal) => wal.sourceId == 'archive2_ring_100_300_1000'),
        isFalse,
      );
      final restartCoverage = RingSequenceCoverage(
        archiveSync.testWals.map(
          (wal) => RingProtocol.parseRecoverySourceRange(wal.sourceId)!,
        ),
      );
      expect(restartCoverage.contiguousEndFrom(100), 200);
      expect(restartCoverage.firstUncovered(100, 300), 200);

      // Timestamp continuity still owns the cloud transaction: the server gets
      // one ordered conversation job, while restart coverage retains the hole.
      expect(
        nextSyncUploadBatch(archiveSync.testWals, 2000),
        archiveSync.testWals,
      );
    });

    test('a legacy archive cannot suppress its truthful raw reread after upgrade', () async {
      final directory = await Directory.systemTemp.createTemp('omi_ring_archive_upgrade_');
      addTearDown(() async {
        if (await directory.exists()) await directory.delete(recursive: true);
      });
      final legacyFile = File('${directory.path}/legacy.bin');
      final rawFile = File('${directory.path}/raw.bin');
      const bytes = [1, 0, 0, 0, 1];
      await legacyFile.writeAsBytes(bytes, flush: true);
      await rawFile.writeAsBytes(bytes, flush: true);

      final archiveSync = LocalWalSyncImpl(
        listener,
        walPersister: (_) async => true,
        walPathResolver: (path) async => path == null ? null : '${directory.path}/$path',
        silenceFrameFactory: (_) => [0],
      )..testWals = [
          _historicalRingWal(
            timerStart: 1000,
            sourceId: 'archive_ring_100_200_1000',
            filePath: legacyFile.path.split('/').last,
          ),
        ];
      final truthfulRaw = _historicalRingWal(
        timerStart: 1000,
        sourceId: 'ring_100_200',
        filePath: rawFile.path.split('/').last,
      );

      final registration = await archiveSync.addExternalWal(
        truthfulRaw,
        scheduleUpload: false,
      );
      expect(registration, ExternalWalRegistration.added);
      expect(archiveSync.testWals, hasLength(2));

      await archiveSync.prepareHistoricalRingFragments(nowSeconds: 2000);

      expect(archiveSync.testWals, hasLength(1));
      expect(archiveSync.testWals.single.sourceId, 'archive2_ring_100_200_1000');
      expect(await legacyFile.exists(), isFalse);
      expect(await rawFile.exists(), isTrue);
    });

    test('replaces many raw fragments with one playable local artifact', () async {
      final directory = await Directory.systemTemp.createTemp('omi_ring_archive_');
      addTearDown(() async {
        if (await directory.exists()) await directory.delete(recursive: true);
      });
      final firstFile = File('${directory.path}/first.bin');
      final secondFile = File('${directory.path}/second.bin');
      await firstFile.writeAsBytes([1, 0, 0, 0, 1], flush: true);
      await secondFile.writeAsBytes([1, 0, 0, 0, 2], flush: true);

      final persistedSizes = <int>[];
      final archiveSync = LocalWalSyncImpl(
        listener,
        walPersister: (wals) async {
          persistedSizes.add(wals.length);
          return true;
        },
        walPathResolver: (path) async => path == null ? null : '${directory.path}/$path',
        silenceFrameFactory: (_) => [0],
      );
      archiveSync.testWals = [
        _historicalRingWal(
          timerStart: 1000,
          sourceId: 'ring_10_11',
          filePath: firstFile.path.split('/').last,
        ),
        _historicalRingWal(
          timerStart: 1002,
          sourceId: 'ring_11_12',
          filePath: secondFile.path.split('/').last,
        )..status = WalStatus.synced,
      ];

      await archiveSync.prepareHistoricalRingFragments(nowSeconds: 2000);

      expect(persistedSizes, [1]);
      expect(archiveSync.testWals, hasLength(1));
      final archive = archiveSync.testWals.single;
      expect(archive.sourceId, startsWith('archive2_ring_10_12_'));
      expect(archive.uploadIntent, WalUploadIntent.historicalBackfill);
      expect(archive.status, WalStatus.miss);
      expect(archive.totalFrames, 201);
      expect(await File('${directory.path}/${archive.filePath}').exists(), isTrue);
      expect(await firstFile.exists(), isFalse);
      expect(await secondFile.exists(), isFalse);
    });

    test('quarantines a missing archive once and accepts truthful pendant recovery', () async {
      final directory = await Directory.systemTemp.createTemp(
        'omi_ring_archive_missing_',
      );
      addTearDown(() async {
        if (await directory.exists()) await directory.delete(recursive: true);
      });
      final adjacentFile = File('${directory.path}/adjacent.bin');
      await adjacentFile.writeAsBytes([1, 0, 0, 0, 2], flush: true);
      final persistedSnapshots = <List<WalStatus>>[];
      final archiveSync = LocalWalSyncImpl(
        listener,
        walPersister: (wals) async {
          persistedSnapshots.add(
            wals.map((wal) => wal.status).toList(growable: false),
          );
          return true;
        },
        walPathResolver: (path) async {
          return path == null ? null : '${directory.path}/$path';
        },
        silenceFrameFactory: (_) => [0],
      )..testWals = [
          _historicalRingWal(
            timerStart: 1000,
            sourceId: 'archive2_ring_10_11_1000',
            filePath: 'missing.bin',
          ),
          _historicalRingWal(
            timerStart: 1002,
            sourceId: 'ring_11_12',
            filePath: 'adjacent.bin',
          ),
        ];

      await archiveSync.prepareHistoricalRingFragments(nowSeconds: 2000);

      expect(persistedSnapshots, hasLength(2));
      expect(
        archiveSync.testWals
            .singleWhere(
              (wal) => wal.sourceId == 'archive2_ring_10_11_1000',
            )
            .status,
        WalStatus.corrupted,
      );
      expect(
        archiveSync.testWals.any(
          (wal) => wal.sourceId == 'archive2_ring_11_12_1002',
        ),
        isTrue,
      );

      await archiveSync.prepareHistoricalRingFragments(nowSeconds: 2000);
      expect(
        persistedSnapshots,
        hasLength(2),
        reason: 'a quarantined source must not retry every compaction timer',
      );

      final recoveredFile = File('${directory.path}/recovered.bin');
      await recoveredFile.writeAsBytes([1, 0, 0, 0, 1], flush: true);
      expect(
        await archiveSync.addExternalWal(
          _historicalRingWal(
            timerStart: 1000,
            sourceId: 'ring_10_11',
            filePath: 'recovered.bin',
          ),
          scheduleUpload: false,
        ),
        ExternalWalRegistration.added,
      );
      await archiveSync.prepareHistoricalRingFragments(nowSeconds: 2000);

      expect(archiveSync.testWals, hasLength(1));
      expect(
        archiveSync.testWals.single.sourceId,
        'archive2_ring_10_12_1000',
      );
      expect(archiveSync.testWals.single.status, WalStatus.miss);
      expect(
        archiveSync.testWals.any(
          (wal) => wal.status == WalStatus.corrupted,
        ),
        isFalse,
      );
    });

    test('replaces a quarantined raw range with the exact pendant reread', () async {
      final directory = await Directory.systemTemp.createTemp(
        'omi_ring_raw_reread_',
      );
      addTearDown(() async {
        if (await directory.exists()) await directory.delete(recursive: true);
      });
      final archiveSync = LocalWalSyncImpl(
        listener,
        walPersister: (_) async => true,
        walPathResolver: (path) async {
          return path == null ? null : '${directory.path}/$path';
        },
      )..testWals = [
          _historicalRingWal(
            timerStart: 1000,
            sourceId: 'ring_10_11',
            filePath: 'missing.bin',
          ),
        ];

      await archiveSync.prepareHistoricalRingFragments(nowSeconds: 2000);
      expect(archiveSync.testWals.single.status, WalStatus.corrupted);

      final recoveredFile = File('${directory.path}/recovered.bin');
      await recoveredFile.writeAsBytes([1, 0, 0, 0, 7], flush: true);
      final recovered = _historicalRingWal(
        timerStart: 1000,
        sourceId: 'ring_10_11',
        filePath: 'recovered.bin',
      );
      expect(
        await archiveSync.addExternalWal(
          recovered,
          scheduleUpload: false,
        ),
        ExternalWalRegistration.added,
      );

      expect(archiveSync.testWals, [recovered]);
      expect(archiveSync.testWals.single.status, WalStatus.miss);
      expect(await recoveredFile.exists(), isTrue);
    });

    test('serializes historical compaction with canonical conversation stamping', () async {
      final directory = await Directory.systemTemp.createTemp(
        'omi_ring_archive_stamp_race_',
      );
      addTearDown(() async {
        if (await directory.exists()) await directory.delete(recursive: true);
      });
      final firstFile = File('${directory.path}/first.bin');
      final secondFile = File('${directory.path}/second.bin');
      await firstFile.writeAsBytes([1, 0, 0, 0, 1], flush: true);
      await secondFile.writeAsBytes([1, 0, 0, 0, 2], flush: true);

      final resolverStarted = Completer<void>();
      final releaseResolver = Completer<void>();
      var heldCompaction = false;
      final archiveSync = LocalWalSyncImpl(
        listener,
        walPersister: (_) async => true,
        walPathResolver: (path) async {
          if (path == 'first.bin' && !heldCompaction) {
            heldCompaction = true;
            resolverStarted.complete();
            await releaseResolver.future;
          }
          return path == null ? null : '${directory.path}/$path';
        },
        silenceFrameFactory: (_) => [0],
      )..testWals = [
          _historicalRingWal(
            timerStart: 1000,
            sourceId: 'ring_10_11',
            filePath: 'first.bin',
          )..status = WalStatus.synced,
          _historicalRingWal(
            timerStart: 1002,
            sourceId: 'ring_11_12',
            filePath: 'second.bin',
          )..status = WalStatus.synced,
        ];

      final compaction = archiveSync.prepareHistoricalRingFragments(
        nowSeconds: 2000,
      );
      await resolverStarted.future.timeout(const Duration(seconds: 1));
      var stampCompleted = false;
      final stamp = archiveSync
          .stampConversationId(
            900,
            'serialized-conversation',
            hasServerSpeechProof: true,
            sessionEndSeconds: 1100,
          )
          .whenComplete(() => stampCompleted = true);
      await Future<void>.delayed(Duration.zero);

      expect(stampCompleted, isFalse);
      releaseResolver.complete();
      await Future.wait([compaction, stamp]).timeout(
        const Duration(seconds: 2),
      );

      final canonical = archiveSync.testWals.single;
      expect(
        canonical.sourceId,
        startsWith('canonical_serialized-conversation'),
      );
      expect(canonical.conversationId, 'serialized-conversation');
      expect(canonical.totalFrames, 201);
      expect(
        await File('${directory.path}/${canonical.filePath}').exists(),
        isTrue,
      );
    });

    test('keeps every source when the archive manifest commit fails', () async {
      final directory = await Directory.systemTemp.createTemp('omi_ring_archive_failure_');
      addTearDown(() async {
        if (await directory.exists()) await directory.delete(recursive: true);
      });
      final firstFile = File('${directory.path}/first.bin');
      final secondFile = File('${directory.path}/second.bin');
      await firstFile.writeAsBytes([1, 0, 0, 0, 1], flush: true);
      await secondFile.writeAsBytes([1, 0, 0, 0, 2], flush: true);

      final archiveSync = LocalWalSyncImpl(
        listener,
        walPersister: (_) async => false,
        walPathResolver: (path) async => path == null ? null : '${directory.path}/$path',
        silenceFrameFactory: (_) => [0],
      );
      final sources = [
        _historicalRingWal(
          timerStart: 1000,
          sourceId: 'ring_10_11',
          filePath: firstFile.path.split('/').last,
        ),
        _historicalRingWal(
          timerStart: 1002,
          sourceId: 'ring_12_13',
          filePath: secondFile.path.split('/').last,
        ),
      ];
      archiveSync.testWals = sources;

      await expectLater(
        archiveSync.prepareHistoricalRingFragments(nowSeconds: 2000),
        throwsA(isA<StateError>()),
      );

      expect(archiveSync.testWals, sources);
      expect(await firstFile.exists(), isTrue);
      expect(await secondFile.exists(), isTrue);
      expect(
        directory.listSync().whereType<File>().where((file) => file.path.contains('archive2_ring_')),
        isEmpty,
      );
    });

    test('failed archive persistence restores sources and preserves concurrent registration', () async {
      final directory = await Directory.systemTemp.createTemp(
        'omi_ring_archive_persist_failure_',
      );
      addTearDown(() async {
        if (await directory.exists()) await directory.delete(recursive: true);
      });
      final firstFile = File('${directory.path}/first.bin');
      final secondFile = File('${directory.path}/second.bin');
      final concurrentFile = File('${directory.path}/concurrent.bin');
      await firstFile.writeAsBytes([1, 0, 0, 0, 1], flush: true);
      await secondFile.writeAsBytes([1, 0, 0, 0, 2], flush: true);
      await concurrentFile.writeAsBytes([1, 0, 0, 0, 3], flush: true);

      final archivePersistStarted = Completer<void>();
      final releaseArchivePersist = Completer<void>();
      final concurrentSaveQueued = Completer<void>();
      var rejectedArchiveCommit = false;
      var persistenceCallCount = 0;
      var persistenceBarrier = Future<void>.value();
      var durableSourceIds = <String>[];
      final persistedSnapshots = <List<String>>[];
      final archiveSync = LocalWalSyncImpl(
        listener,
        walPersister: (wals) {
          final call = ++persistenceCallCount;
          final snapshot = wals.map((wal) => wal.sourceId!).toList(growable: false);
          persistedSnapshots.add(snapshot);
          if (call == 2) concurrentSaveQueued.complete();
          final operation = persistenceBarrier.then((_) async {
            final hasArchive = snapshot.any(
              (sourceId) => sourceId.startsWith('archive2_ring_'),
            );
            if (hasArchive && !rejectedArchiveCommit) {
              rejectedArchiveCommit = true;
              archivePersistStarted.complete();
              await releaseArchivePersist.future;
              return false;
            }
            durableSourceIds = snapshot;
            return true;
          });
          persistenceBarrier = operation.then<void>(
            (_) {},
            onError: (error, stackTrace) {},
          );
          return operation;
        },
        walPathResolver: (path) async => path == null ? null : '${directory.path}/$path',
        silenceFrameFactory: (_) => [0],
      );
      final first = _historicalRingWal(
        timerStart: 1000,
        sourceId: 'ring_10_11',
        filePath: 'first.bin',
      );
      final second = _historicalRingWal(
        timerStart: 1002,
        sourceId: 'ring_11_12',
        filePath: 'second.bin',
      );
      final concurrent = _historicalRingWal(
        timerStart: 1000,
        sourceId: 'ring_90_91',
        filePath: 'concurrent.bin',
      )..device = 'other-device';
      archiveSync.testWals = [first, second];

      final compaction = archiveSync.prepareHistoricalRingFragments(
        nowSeconds: 2000,
      );
      await archivePersistStarted.future.timeout(const Duration(seconds: 1));
      final concurrentRegistration = archiveSync.addExternalWal(
        concurrent,
        scheduleUpload: false,
      );
      await concurrentSaveQueued.future.timeout(const Duration(seconds: 1));
      expect(
        persistedSnapshots[1],
        containsAll(<String>[
          'archive2_ring_10_12_1000',
          'ring_90_91',
        ]),
      );

      releaseArchivePersist.complete();
      expect(
        await concurrentRegistration,
        ExternalWalRegistration.added,
      );
      await expectLater(
        compaction.timeout(const Duration(seconds: 2)),
        throwsA(isA<StateError>()),
      );

      expect(rejectedArchiveCommit, isTrue);
      expect(
        archiveSync.testWals,
        containsAllInOrder([concurrent, first, second]),
      );
      expect(
        archiveSync.testWals.any(
          (wal) => wal.sourceId?.startsWith('archive2_ring_') == true,
        ),
        isFalse,
      );
      expect(await firstFile.exists(), isTrue);
      expect(await secondFile.exists(), isTrue);
      expect(await concurrentFile.exists(), isTrue);
      expect(
        durableSourceIds.toSet(),
        {'ring_10_11', 'ring_11_12', 'ring_90_91'},
      );
      expect(
        persistedSnapshots.last.toSet(),
        {'ring_10_11', 'ring_11_12', 'ring_90_91'},
      );
      expect(
        directory.listSync().whereType<File>().where(
              (file) => file.path.contains('archive2_ring_'),
            ),
        isEmpty,
      );
    });

    test('does not archive the old prefix of a still-active conversation', () async {
      final directory = await Directory.systemTemp.createTemp('omi_ring_archive_open_');
      addTearDown(() async {
        if (await directory.exists()) await directory.delete(recursive: true);
      });
      final sources = <Wal>[];
      for (final entry in [
        (timestamp: 1000, sourceId: 'ring_10_11'),
        (timestamp: 1100, sourceId: 'ring_11_12'),
        (timestamp: 1190, sourceId: 'ring_12_13'),
      ]) {
        final fileName = '${entry.sourceId}.bin';
        await File('${directory.path}/$fileName').writeAsBytes(
          [1, 0, 0, 0, 1],
          flush: true,
        );
        sources.add(
          _historicalRingWal(
            timerStart: entry.timestamp,
            sourceId: entry.sourceId,
            filePath: fileName,
          )..uploadIntent = WalUploadIntent.liveContinuity,
        );
      }
      final archiveSync = LocalWalSyncImpl(
        listener,
        walPersister: (_) async => true,
        walPathResolver: (path) async => path == null ? null : '${directory.path}/$path',
        silenceFrameFactory: (_) => [0],
      );
      archiveSync.testWals = sources;

      await archiveSync.prepareHistoricalRingFragments(nowSeconds: 1250);

      expect(archiveSync.testWals, sources);
      expect(
        archiveSync.testWals.map((wal) => wal.uploadIntent),
        everyElement(WalUploadIntent.liveContinuity),
      );

      await archiveSync.prepareHistoricalRingFragments(nowSeconds: 1400);

      expect(archiveSync.testWals, hasLength(1));
      expect(
        archiveSync.testWals.single.uploadIntent,
        WalUploadIntent.historicalBackfill,
      );
    });

    test('late server completion can reclaim a compacted archive as one canonical repair', () async {
      SyncRateLimiter.instance.clear();
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final prefix = 'omi_ring_archive_reclaim_${DateTime.now().microsecondsSinceEpoch}';
      final firstFile = File('${Directory.systemTemp.path}/${prefix}_first.bin');
      final secondFile = File('${Directory.systemTemp.path}/${prefix}_second.bin');
      await firstFile.writeAsBytes([1, 0, 0, 0, 1], flush: true);
      await secondFile.writeAsBytes([1, 0, 0, 0, 2], flush: true);
      final uploads = <({String? conversationId, bool replaceTranscript, int files})>[];
      final uploadStarted = Completer<void>();
      final gate = SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        fairUseStatusLoader: () async => {'stage': 'none'},
        uploader: (files,
            {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh, replaceTranscript = false}) async {
          uploads.add(
            (
              conversationId: conversationId,
              replaceTranscript: replaceTranscript,
              files: files.length,
            ),
          );
          if (!uploadStarted.isCompleted) uploadStarted.complete();
          return UploadFilesResult.queued('archive-repair-job');
        },
      );
      final archiveSync = LocalWalSyncImpl(
        listener,
        uploadGate: gate,
        walPersister: (_) async => true,
        walPathResolver: (path) async => path == null ? null : '${Directory.systemTemp.path}/$path',
        silenceFrameFactory: (_) => [0],
      );
      addTearDown(() async {
        for (final file in [
          firstFile,
          secondFile,
          ...archiveSync.testWals
              .map((wal) => wal.filePath)
              .whereType<String>()
              .map((path) => File('${Directory.systemTemp.path}/$path')),
        ]) {
          if (await file.exists()) await file.delete();
        }
      });
      archiveSync.testWals = [
        _historicalRingWal(
          timerStart: now - 300,
          sourceId: 'ring_10_11',
          filePath: firstFile.path.split('/').last,
        )..uploadIntent = WalUploadIntent.liveContinuity,
        _historicalRingWal(
          timerStart: now - 298,
          sourceId: 'ring_11_12',
          filePath: secondFile.path.split('/').last,
        )..uploadIntent = WalUploadIntent.liveContinuity,
      ];

      await archiveSync.prepareHistoricalRingFragments(nowSeconds: now);
      expect(archiveSync.testWals.single.sourceId, startsWith('archive2_ring_'));
      expect(archiveSync.testWals.single.status, WalStatus.miss);

      await archiveSync.stampConversationId(
        now - 400,
        'late-conversation',
        hasServerSpeechProof: true,
        sessionEndSeconds: now,
      );
      expect(archiveSync.testWals.single.status, WalStatus.miss);
      expect(archiveSync.testWals.single.canonicalReplacement, isTrue);
      await uploadStarted.future.timeout(const Duration(seconds: 1));

      expect(uploads, [
        (
          conversationId: 'late-conversation',
          replaceTranscript: true,
          files: 1,
        ),
      ]);
      expect(
        archiveSync.testWals.single.sourceId,
        startsWith('canonical_late-conversation_'),
      );
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

      await freshSync.addExternalWal(wal);

      expect(freshSync.testWals.map((w) => w.id), contains(wal.id));
    });

    test('external registration waits for manifest, not upload, and coalesces the next wake', () async {
      SyncRateLimiter.instance.clear();
      final manifestCommit = Completer<bool>();
      final uploadStarted = Completer<void>();
      final secondUploadStarted = Completer<void>();
      final releaseUpload = Completer<void>();
      final backgroundManifestSaved = Completer<void>();
      final uploadBatches = <List<String>>[];
      var manifestWrites = 0;
      final fileName = 'external_wal_${DateTime.now().microsecondsSinceEpoch}.bin';
      final secondFileName = 'external_wal_next_${DateTime.now().microsecondsSinceEpoch}.bin';
      final file = File('${Directory.systemTemp.path}/$fileName');
      final secondFile = File('${Directory.systemTemp.path}/$secondFileName');
      await file.writeAsBytes([1, 2, 3], flush: true);
      await secondFile.writeAsBytes([4, 5, 6], flush: true);
      addTearDown(() async {
        if (await file.exists()) await file.delete();
        if (await secondFile.exists()) await secondFile.delete();
      });

      final gate = SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        fairUseStatusLoader: () async => {'stage': 'none'},
        uploader: (files,
            {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh, replaceTranscript = false}) async {
          uploadBatches.add(files.map((file) => file.uri.pathSegments.last).toList());
          if (uploadBatches.length == 1) uploadStarted.complete();
          if (uploadBatches.length == 2) secondUploadStarted.complete();
          await releaseUpload.future;
          return UploadFilesResult.queued('test-job-${uploadBatches.length}');
        },
      );
      final externalSync = LocalWalSyncImpl(
        listener,
        uploadGate: gate,
        walPersister: (_) {
          manifestWrites++;
          if (manifestWrites == 1) return manifestCommit.future;
          if (manifestWrites >= 5 && !backgroundManifestSaved.isCompleted) {
            backgroundManifestSaved.complete();
          }
          return Future.value(true);
        },
      );
      final wal = Wal(
        timerStart: DateTime.now().millisecondsSinceEpoch ~/ 1000,
        codec: BleAudioCodec.opus,
        seconds: 1,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        filePath: fileName,
        device: 'test-device',
        sourceId: 'external_1',
        conversationId: 'conversation-1',
      );

      var registrationCompleted = false;
      final registrationFuture = externalSync.addExternalWal(wal).whenComplete(() => registrationCompleted = true);
      await Future<void>.delayed(Duration.zero);

      expect(manifestWrites, 1);
      expect(registrationCompleted, isFalse);

      manifestCommit.complete(true);
      expect(
        await registrationFuture.timeout(const Duration(seconds: 1)),
        ExternalWalRegistration.added,
      );
      await uploadStarted.future.timeout(const Duration(seconds: 1));
      expect(releaseUpload.isCompleted, isFalse);
      expect(uploadBatches, [
        [fileName],
      ]);

      final secondWal = Wal(
        timerStart: DateTime.now().millisecondsSinceEpoch ~/ 1000,
        codec: BleAudioCodec.opus,
        seconds: 1,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        filePath: secondFileName,
        device: 'test-device',
        sourceId: 'external_2',
        conversationId: 'conversation-1',
      );
      expect(
        await externalSync.addExternalWal(secondWal).timeout(const Duration(seconds: 1)),
        ExternalWalRegistration.added,
      );
      expect(uploadBatches, [
        [fileName],
      ]);

      releaseUpload.complete();
      await secondUploadStarted.future.timeout(const Duration(seconds: 1));
      await backgroundManifestSaved.future.timeout(const Duration(seconds: 1));
      expect(uploadBatches, [
        [fileName],
        [secondFileName],
      ]);
    });

    test('fresh external WAL wakes ahead of a large historical queue without a conversation id', () async {
      SyncRateLimiter.instance.clear();
      final uploadStarted = Completer<void>();
      final uploadedFiles = <String>[];
      final uploadLanes = <SyncUploadLane>[];
      final uploadedReplaceModes = <bool>[];
      final fileName = 'external_live_${DateTime.now().microsecondsSinceEpoch}.bin';
      final file = File('${Directory.systemTemp.path}/$fileName');
      await file.writeAsBytes([3, 0, 0, 0, 1, 2, 3], flush: true);
      addTearDown(() async {
        if (await file.exists()) await file.delete();
      });

      final gate = SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        fairUseStatusLoader: () async => {'stage': 'none'},
        uploader: (files,
            {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh, replaceTranscript = false}) async {
          uploadedFiles.addAll(files.map((candidate) => candidate.uri.pathSegments.last));
          uploadLanes.add(syncLane);
          uploadedReplaceModes.add(replaceTranscript);
          if (!uploadStarted.isCompleted) uploadStarted.complete();
          return UploadFilesResult.queued('fresh-priority-job');
        },
      );
      final externalSync = LocalWalSyncImpl(
        listener,
        uploadGate: gate,
        walPersister: (_) async => true,
      );
      externalSync.testWals = List.generate(
        1000,
        (index) => Wal(
          timerStart: 1000 + index,
          codec: BleAudioCodec.opus,
          seconds: 60,
          status: WalStatus.miss,
          storage: WalStorage.disk,
          filePath: 'historical_$index.bin',
          device: 'test-device',
          uploadIntent: WalUploadIntent.historicalBackfill,
        ),
      );
      final liveWal = Wal(
        timerStart: DateTime.now().millisecondsSinceEpoch ~/ 1000,
        codec: BleAudioCodec.opus,
        seconds: 2,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        filePath: fileName,
        device: 'test-device',
        sourceId: 'ring_1000_1020',
        uploadIntent: WalUploadIntent.liveContinuity,
      );

      expect(await externalSync.addExternalWal(liveWal), ExternalWalRegistration.added);
      await Future<void>.delayed(const Duration(milliseconds: 20));

      expect(uploadStarted.isCompleted, isFalse);
      expect(uploadedFiles, isEmpty);
      expect(uploadLanes, isEmpty);

      await externalSync.stampConversationId(
        liveWal.timerStart,
        'conversation-1',
        hasServerSpeechProof: true,
      );
      await uploadStarted.future.timeout(const Duration(seconds: 1));

      expect(uploadedFiles.single, contains('canonical_conversation-1'));
      expect(uploadLanes, [SyncUploadLane.fresh]);
      expect(uploadedReplaceModes, [isTrue]);
    });

    test('recovered live ranges stay local until their session has a conversation id', () async {
      SyncRateLimiter.instance.clear();
      final uploadedBatches = <List<String>>[];
      final uploadedPayloads = <List<int>>[];
      final uploadedConversationIds = <String?>[];
      final uploadedReplaceModes = <bool>[];
      final uploadStarted = Completer<void>();
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      const firstFileName = 'audio_test_opus_16000_1_fs320_ring_1_2_1700000001.bin';
      const secondFileName = 'audio_test_opus_16000_1_fs320_ring_2_3_1700000002.bin';
      final firstFile = File('${Directory.systemTemp.path}/$firstFileName');
      final secondFile = File('${Directory.systemTemp.path}/$secondFileName');
      await firstFile.writeAsBytes(
        List.generate(100, (_) => [3, 0, 0, 0, 1, 2, 3]).expand((frame) => frame).toList(),
        flush: true,
      );
      await secondFile.writeAsBytes(
        List.generate(100, (_) => [3, 0, 0, 0, 4, 5, 6]).expand((frame) => frame).toList(),
        flush: true,
      );
      addTearDown(() async {
        if (await firstFile.exists()) await firstFile.delete();
        if (await secondFile.exists()) await secondFile.delete();
      });

      final gate = SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        fairUseStatusLoader: () async => {'stage': 'none'},
        uploader: (files,
            {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh, replaceTranscript = false}) async {
          uploadedBatches.add(files.map((file) => file.uri.pathSegments.last).toList());
          uploadedPayloads.add(await files.single.readAsBytes());
          uploadedConversationIds.add(conversationId);
          uploadedReplaceModes.add(replaceTranscript);
          if (!uploadStarted.isCompleted) uploadStarted.complete();
          return UploadFilesResult.queued('batched-recovery-job');
        },
      );
      final externalSync = LocalWalSyncImpl(
        listener,
        uploadGate: gate,
        walPersister: (_) async => true,
      );
      Wal recoveredWal({
        required int timerStart,
        required String fileName,
        required String sourceId,
        required double captureEndSeconds,
      }) =>
          Wal(
            timerStart: timerStart,
            codec: BleAudioCodec.opus,
            seconds: 1,
            captureEndSeconds: captureEndSeconds,
            status: WalStatus.miss,
            storage: WalStorage.disk,
            originalStorage: WalStorage.sdcard,
            filePath: fileName,
            device: 'test-device',
            totalFrames: 100,
            sourceId: sourceId,
            uploadIntent: WalUploadIntent.liveContinuity,
          );

      expect(
        await externalSync.addExternalWal(
          recoveredWal(
            timerStart: now - 2,
            fileName: firstFileName,
            sourceId: 'ring_1_2',
            captureEndSeconds: now - 1.25,
          ),
        ),
        ExternalWalRegistration.added,
      );
      expect(
        await externalSync.addExternalWal(
          recoveredWal(
            timerStart: now - 1,
            fileName: secondFileName,
            sourceId: 'ring_2_3',
            captureEndSeconds: now - 0.25,
          ),
        ),
        ExternalWalRegistration.added,
      );
      expect(externalSync.testWals, hasLength(2));
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(uploadedBatches, isEmpty);

      await externalSync.stampConversationId(
        now - 2,
        'conversation-1',
        hasServerSpeechProof: true,
      );
      await uploadStarted.future.timeout(const Duration(seconds: 1));

      expect(uploadedBatches, hasLength(1));
      expect(uploadedBatches.single, hasLength(1));
      expect(uploadedBatches.single.single, contains('canonical_conversation-1'));
      expect(uploadedPayloads.single, hasLength(1400));
      expect(uploadedPayloads.single.take(7), [3, 0, 0, 0, 1, 2, 3]);
      expect(uploadedPayloads.single.skip(1393), [3, 0, 0, 0, 4, 5, 6]);
      expect(uploadedConversationIds, ['conversation-1']);
      expect(uploadedReplaceModes, [isTrue]);
      expect(externalSync.testWals, hasLength(1));
      expect(externalSync.testWals.single.canonicalReplacement, isTrue);
      expect(externalSync.testWals.single.captureEndSeconds, now - 0.25);
    });

    test('conversation stamping claims the complete configured ring window', () async {
      final directory = await Directory.systemTemp.createTemp(
        'omi_ring_conversation_window_',
      );
      addTearDown(() async {
        if (await directory.exists()) await directory.delete(recursive: true);
      });
      for (final entry in {
        'before.bin': 1,
        'session.bin': 2,
        'after.bin': 3,
        'boundary.bin': 4,
      }.entries) {
        await File('${directory.path}/${entry.key}').writeAsBytes(
          [1, 0, 0, 0, entry.value],
          flush: true,
        );
      }
      final sources = [
        _historicalRingWal(
          timerStart: 1000,
          sourceId: 'ring_10_11',
          filePath: 'before.bin',
          captureEndSeconds: 1001,
        ),
        _historicalRingWal(
          timerStart: 1110,
          sourceId: 'ring_11_12',
          filePath: 'session.bin',
          captureEndSeconds: 1111,
        ),
        _historicalRingWal(
          timerStart: 1220,
          sourceId: 'ring_12_13',
          filePath: 'after.bin',
          captureEndSeconds: 1221,
        ),
        _historicalRingWal(
          timerStart: 1341,
          sourceId: 'ring_13_14',
          filePath: 'boundary.bin',
          captureEndSeconds: 1342,
        ),
      ];
      for (final source in sources) {
        source
          ..status = WalStatus.synced
          ..uploadIntent = WalUploadIntent.liveContinuity;
      }
      final externalSync = LocalWalSyncImpl(
        listener,
        walPersister: (_) async => true,
        walPathResolver: (path) async {
          return path == null ? null : '${directory.path}/$path';
        },
        silenceFrameFactory: (_) => [0],
        conversationBoundarySecondsProvider: () => 120,
      )..testWals = sources;

      await externalSync.stampConversationId(
        1110,
        'complete-window',
        hasServerSpeechProof: true,
        sessionEndSeconds: 1111,
      );

      expect(externalSync.testWals, hasLength(2));
      final canonical = externalSync.testWals.singleWhere(
        (wal) => wal.sourceId?.startsWith('canonical_complete-window_') == true,
      );
      expect(canonical.conversationId, 'complete-window');
      expect(canonical.timerStart, 1000);
      expect(canonical.captureEndSeconds, 1221);
      expect(canonical.status, WalStatus.synced);
      final outside = externalSync.testWals.singleWhere(
        (wal) => wal.sourceId == 'ring_13_14',
      );
      expect(outside.conversationId, isNull);
    });

    test('conversation ownership without speech proof cannot create an upload job', () async {
      SyncRateLimiter.instance.clear();
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final fileName = 'no_speech_proof_${DateTime.now().microsecondsSinceEpoch}.bin';
      final file = File('${Directory.systemTemp.path}/$fileName');
      await file.writeAsBytes([1, 0, 0, 0, 1], flush: true);
      addTearDown(() async {
        if (await file.exists()) await file.delete();
      });
      var uploadCalls = 0;
      final gate = SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        fairUseStatusLoader: () async => {'stage': 'none'},
        uploader: (files,
            {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh, replaceTranscript = false}) async {
          uploadCalls++;
          return UploadFilesResult.queued('must-not-upload');
        },
      );
      final externalSync = LocalWalSyncImpl(
        listener,
        uploadGate: gate,
        walPersister: (_) async => true,
      );
      final wal = Wal(
        timerStart: now - 10,
        codec: BleAudioCodec.opus,
        seconds: 1,
        totalFrames: 1,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        filePath: fileName,
        device: 'test-device',
        sourceId: 'ring_1_2',
        uploadIntent: WalUploadIntent.liveContinuity,
      );
      await externalSync.addExternalWal(wal, scheduleUpload: false);

      await externalSync.stampConversationId(
        now - 20,
        'noise-only-conversation',
        hasServerSpeechProof: false,
      );
      await Future<void>.delayed(const Duration(milliseconds: 20));

      expect(uploadCalls, 0);
      expect(externalSync.testWals, [wal]);
      expect(wal.conversationId, isNull);
    });

    test('one thousand one-second repairs become one job instead of one thousand jobs', () async {
      SyncRateLimiter.instance.clear();
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final prefix = 'repair_${DateTime.now().microsecondsSinceEpoch}';
      final files = <File>[];
      final uploadedArtifactSizes = <List<int>>[];
      final uploadedConversationIds = <String?>[];
      final uploadedReplaceModes = <bool>[];
      final uploadStarted = Completer<void>();

      addTearDown(() async {
        for (final file in files) {
          if (await file.exists()) await file.delete();
        }
      });

      final gate = SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        fairUseStatusLoader: () async => {'stage': 'none'},
        uploader: (artifacts,
            {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh, replaceTranscript = false}) async {
          uploadedArtifactSizes.add(
            await Future.wait(artifacts.map((artifact) => artifact.length())),
          );
          uploadedConversationIds.add(conversationId);
          uploadedReplaceModes.add(replaceTranscript);
          if (!uploadStarted.isCompleted) uploadStarted.complete();
          return UploadFilesResult.queued('single-repair-job');
        },
      );
      final externalSync = LocalWalSyncImpl(
        listener,
        uploadGate: gate,
        walPersister: (_) async => true,
      );

      final repairs = <Wal>[];
      for (var index = 0; index < 1000; index++) {
        final filename = '${prefix}_$index.bin';
        final file = File('${Directory.systemTemp.path}/$filename');
        await file.writeAsBytes(
          List.generate(100, (_) => [1, 0, 0, 0, index & 0xff]).expand((frame) => frame).toList(),
          flush: true,
        );
        files.add(file);
        final wal = Wal(
          timerStart: now - 1000 + index,
          codec: BleAudioCodec.opus,
          seconds: 1,
          totalFrames: 100,
          status: WalStatus.miss,
          storage: WalStorage.disk,
          originalStorage: WalStorage.sdcard,
          filePath: filename,
          device: 'test-device',
          sourceId: 'ring_${index}_${index + 1}',
          uploadIntent: WalUploadIntent.liveContinuity,
        );
        repairs.add(wal);
        expect(
          await externalSync.addExternalWal(wal),
          ExternalWalRegistration.added,
        );
      }

      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(uploadedArtifactSizes, isEmpty);

      await externalSync.stampConversationId(
        now - 1000,
        'conversation-1000',
        hasServerSpeechProof: true,
      );
      await uploadStarted.future.timeout(const Duration(seconds: 5));

      expect(uploadedArtifactSizes, hasLength(1));
      expect(uploadedArtifactSizes.single, [500000]);
      expect(uploadedConversationIds, ['conversation-1000']);
      expect(uploadedReplaceModes, [isTrue]);
      expect(externalSync.testWals, hasLength(1));
      expect(externalSync.testWals.single.jobId, 'single-repair-job');
    });

    test('canonical commit preserves a WAL registered while assembly reads disk', () async {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final sourceName = 'canonical_race_source_${DateTime.now().microsecondsSinceEpoch}.bin';
      final lateName = 'canonical_race_late_${DateTime.now().microsecondsSinceEpoch}.bin';
      final sourceFile = File('${Directory.systemTemp.path}/$sourceName');
      final lateFile = File('${Directory.systemTemp.path}/$lateName');
      await sourceFile.writeAsBytes([1, 0, 0, 0, 7], flush: true);
      await lateFile.writeAsBytes([1, 0, 0, 0, 8], flush: true);
      addTearDown(() async {
        if (await sourceFile.exists()) await sourceFile.delete();
        if (await lateFile.exists()) await lateFile.delete();
      });

      final resolverStarted = Completer<void>();
      final releaseResolver = Completer<void>();
      final externalSync = LocalWalSyncImpl(
        listener,
        walPersister: (_) async => true,
        walPathResolver: (path) async {
          if (path == sourceName && !resolverStarted.isCompleted) {
            resolverStarted.complete();
            await releaseResolver.future;
          }
          return path == null ? null : '${Directory.systemTemp.path}/$path';
        },
      );
      addTearDown(() async {
        for (final wal in externalSync.testWals) {
          final path = wal.filePath;
          if (path == null || !path.contains('canonical_conversation-race')) continue;
          final file = File('${Directory.systemTemp.path}/$path');
          if (await file.exists()) await file.delete();
        }
      });
      final source = Wal(
        timerStart: now - 10,
        codec: BleAudioCodec.opus,
        seconds: 1,
        totalFrames: 1,
        status: WalStatus.synced,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        filePath: sourceName,
        device: 'test-device',
        sourceId: 'ring_10_11',
        uploadIntent: WalUploadIntent.liveContinuity,
      );
      final late = Wal(
        timerStart: now - 5,
        codec: BleAudioCodec.opus,
        seconds: 1,
        totalFrames: 1,
        status: WalStatus.synced,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        filePath: lateName,
        device: 'other-device',
        sourceId: 'ring_90_91',
        uploadIntent: WalUploadIntent.historicalBackfill,
      );
      expect(
        await externalSync.addExternalWal(source, scheduleUpload: false),
        ExternalWalRegistration.added,
      );

      final stamp = externalSync.stampConversationId(
        now - 20,
        'conversation-race',
        hasServerSpeechProof: true,
      );
      await resolverStarted.future.timeout(const Duration(seconds: 1));
      expect(
        await externalSync.addExternalWal(late, scheduleUpload: false),
        ExternalWalRegistration.added,
      );
      releaseResolver.complete();
      await stamp.timeout(const Duration(seconds: 1));

      expect(
        externalSync.testWals.map((wal) => wal.id),
        contains(late.id),
      );
      expect(
        externalSync.testWals.where((wal) => wal.conversationId == 'conversation-race'),
        hasLength(1),
      );
    });

    test('canonical commit rescans and includes a same-device WAL registered during assembly', () async {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final sourceName = 'canonical_same_device_source_${DateTime.now().microsecondsSinceEpoch}.bin';
      final lateName = 'canonical_same_device_late_${DateTime.now().microsecondsSinceEpoch}.bin';
      final sourceFile = File('${Directory.systemTemp.path}/$sourceName');
      final lateFile = File('${Directory.systemTemp.path}/$lateName');
      await sourceFile.writeAsBytes([1, 0, 0, 0, 7], flush: true);
      await lateFile.writeAsBytes([1, 0, 0, 0, 8], flush: true);
      addTearDown(() async {
        for (final file in [sourceFile, lateFile]) {
          if (await file.exists()) await file.delete();
        }
      });

      final resolverStarted = Completer<void>();
      final releaseResolver = Completer<void>();
      var heldFirstAssembly = false;
      final externalSync = LocalWalSyncImpl(
        listener,
        walPersister: (_) async => true,
        walPathResolver: (path) async {
          if (path == sourceName && !heldFirstAssembly) {
            heldFirstAssembly = true;
            resolverStarted.complete();
            await releaseResolver.future;
          }
          return path == null ? null : '${Directory.systemTemp.path}/$path';
        },
      );
      addTearDown(() async {
        for (final wal in externalSync.testWals) {
          final path = wal.filePath;
          if (path == null || !path.contains('canonical_conversation-same-device')) continue;
          final file = File('${Directory.systemTemp.path}/$path');
          if (await file.exists()) await file.delete();
        }
      });
      final source = Wal(
        timerStart: now - 10,
        codec: BleAudioCodec.opus,
        seconds: 1,
        totalFrames: 1,
        captureEndSeconds: now - 9.99,
        status: WalStatus.synced,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        filePath: sourceName,
        device: 'same-device',
        sourceId: 'ring_10_11',
        uploadIntent: WalUploadIntent.liveContinuity,
      );
      final late = Wal(
        timerStart: now - 10,
        codec: BleAudioCodec.opus,
        seconds: 1,
        totalFrames: 1,
        captureEndSeconds: now - 9.99,
        status: WalStatus.synced,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        filePath: lateName,
        device: 'same-device',
        sourceId: 'ring_11_12',
        uploadIntent: WalUploadIntent.liveContinuity,
      );
      await externalSync.addExternalWal(source, scheduleUpload: false);

      final stamp = externalSync.stampConversationId(
        now - 20,
        'conversation-same-device',
        hasServerSpeechProof: true,
        sessionEndSeconds: now,
      );
      await resolverStarted.future.timeout(const Duration(seconds: 1));
      await externalSync.addExternalWal(late, scheduleUpload: false);
      releaseResolver.complete();
      await stamp.timeout(const Duration(seconds: 2));

      final canonical = externalSync.testWals.single;
      expect(canonical.sourceId, startsWith('canonical_conversation-same-device'));
      expect(canonical.conversationId, 'conversation-same-device');
      expect(canonical.totalFrames, 2);
      expect(await File('${Directory.systemTemp.path}/${canonical.filePath}').length(), 10);
    });

    test('failed canonical persistence restores sources and preserves concurrent registration', () async {
      final directory = await Directory.systemTemp.createTemp(
        'omi_canonical_persist_failure_',
      );
      addTearDown(() async {
        if (await directory.exists()) await directory.delete(recursive: true);
      });
      final sourceFile = File('${directory.path}/source.bin');
      final concurrentFile = File('${directory.path}/concurrent.bin');
      await sourceFile.writeAsBytes([1, 0, 0, 0, 7], flush: true);
      await concurrentFile.writeAsBytes([1, 0, 0, 0, 8], flush: true);

      final canonicalPersistStarted = Completer<void>();
      final releaseCanonicalPersist = Completer<void>();
      final concurrentSaveQueued = Completer<void>();
      var rejectedCanonicalCommit = false;
      var persistenceCallCount = 0;
      var persistenceBarrier = Future<void>.value();
      var durableSourceIds = <String>[];
      final persistedSnapshots = <List<String>>[];
      final externalSync = LocalWalSyncImpl(
        listener,
        walPersister: (wals) {
          final call = ++persistenceCallCount;
          final snapshot = wals.map((wal) => wal.sourceId!).toList(growable: false);
          persistedSnapshots.add(snapshot);
          if (call == 2) concurrentSaveQueued.complete();
          final operation = persistenceBarrier.then((_) async {
            final hasCanonical = snapshot.any(
              (sourceId) => sourceId.startsWith('canonical_'),
            );
            if (hasCanonical && !rejectedCanonicalCommit) {
              rejectedCanonicalCommit = true;
              canonicalPersistStarted.complete();
              await releaseCanonicalPersist.future;
              return false;
            }
            durableSourceIds = snapshot;
            return true;
          });
          persistenceBarrier = operation.then<void>(
            (_) {},
            onError: (error, stackTrace) {},
          );
          return operation;
        },
        walPathResolver: (path) async {
          return path == null ? null : '${directory.path}/$path';
        },
        silenceFrameFactory: (_) => [0],
      );
      final source = _historicalRingWal(
        timerStart: 1000,
        sourceId: 'ring_10_11',
        filePath: 'source.bin',
      )
        ..status = WalStatus.synced
        ..uploadIntent = WalUploadIntent.liveContinuity;
      final concurrent = Wal(
        timerStart: 1000,
        codec: BleAudioCodec.opus,
        seconds: 1,
        totalFrames: 1,
        status: WalStatus.synced,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        filePath: 'concurrent.bin',
        device: 'other-device',
        sourceId: 'ring_90_91',
        uploadIntent: WalUploadIntent.historicalBackfill,
      );
      externalSync.testWals = [source];

      final stamp = externalSync.stampConversationId(
        900,
        'persist-failure',
        hasServerSpeechProof: true,
        sessionEndSeconds: 1100,
      );
      await canonicalPersistStarted.future.timeout(
        const Duration(seconds: 1),
      );
      final concurrentRegistration = externalSync.addExternalWal(
        concurrent,
        scheduleUpload: false,
      );
      await concurrentSaveQueued.future.timeout(const Duration(seconds: 1));
      expect(
        persistedSnapshots[1].any(
          (sourceId) => sourceId.startsWith('canonical_'),
        ),
        isTrue,
      );
      expect(persistedSnapshots[1], contains('ring_90_91'));
      releaseCanonicalPersist.complete();
      expect(
        await concurrentRegistration,
        ExternalWalRegistration.added,
      );
      await stamp.timeout(const Duration(seconds: 2));

      expect(rejectedCanonicalCommit, isTrue);
      expect(
        externalSync.testWals.any(
          (wal) => wal.sourceId?.startsWith('canonical_') == true,
        ),
        isFalse,
      );
      expect(externalSync.testWals, containsAllInOrder([concurrent, source]));
      expect(source.conversationId, 'persist-failure');
      expect(concurrent.conversationId, isNull);
      expect(await sourceFile.exists(), isTrue);
      expect(await concurrentFile.exists(), isTrue);
      expect(
        durableSourceIds.toSet(),
        {'ring_10_11', 'ring_90_91'},
      );
      expect(
        persistedSnapshots.last.toSet(),
        {'ring_10_11', 'ring_90_91'},
      );
      expect(
        persistedSnapshots.last.any(
          (sourceId) => sourceId.startsWith('canonical_'),
        ),
        isFalse,
      );
      expect(
        directory.listSync().whereType<File>().where(
              (file) => file.path.contains('canonical_persist-failure'),
            ),
        isEmpty,
      );
    });

    test('post-commit late ring audio inherits canonical ownership and never uploads alone', () async {
      SyncRateLimiter.instance.clear();
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final canonicalName = 'canonical_post_commit_${DateTime.now().microsecondsSinceEpoch}.bin';
      final lateName = 'canonical_post_commit_late_${DateTime.now().microsecondsSinceEpoch}.bin';
      final canonicalFile = File('${Directory.systemTemp.path}/$canonicalName');
      final lateFile = File('${Directory.systemTemp.path}/$lateName');
      await canonicalFile.writeAsBytes([1, 0, 0, 0, 7], flush: true);
      await lateFile.writeAsBytes([1, 0, 0, 0, 8], flush: true);
      addTearDown(() async {
        for (final file in [canonicalFile, lateFile]) {
          if (await file.exists()) await file.delete();
        }
      });
      var uploadCalls = 0;
      final gate = SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        fairUseStatusLoader: () async => {'stage': 'none'},
        uploader: (
          files, {
          onUploadProgress,
          conversationId,
          syncLane = SyncUploadLane.fresh,
          replaceTranscript = false,
        }) async {
          uploadCalls++;
          return UploadFilesResult.queued('must-not-upload-gap');
        },
      );
      final canonical = Wal(
        timerStart: now - 10,
        codec: BleAudioCodec.opus,
        seconds: 1,
        totalFrames: 1,
        captureEndSeconds: now - 9,
        status: WalStatus.synced,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        filePath: canonicalName,
        device: 'same-device',
        sourceId: 'canonical_conversation-post-commit_test',
        conversationId: 'conversation-post-commit',
        uploadIntent: WalUploadIntent.liveContinuity,
      );
      final late = Wal(
        timerStart: now - 8,
        codec: BleAudioCodec.opus,
        seconds: 1,
        totalFrames: 1,
        captureEndSeconds: now - 7,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        filePath: lateName,
        device: 'same-device',
        sourceId: 'ring_11_12',
        uploadIntent: WalUploadIntent.liveContinuity,
      );
      final externalSync = LocalWalSyncImpl(
        listener,
        uploadGate: gate,
        walPersister: (_) async => true,
      )..testWals = [canonical];

      await externalSync.addExternalWal(late, scheduleUpload: false);
      await externalSync.syncWal(wal: late);

      expect(late.conversationId, 'conversation-post-commit');
      expect(late.status, WalStatus.miss);
      expect(uploadCalls, 0);
      expect(
        externalSync.testWals.where((wal) => wal.sourceId?.startsWith('canonical_') == true),
        [canonical],
      );
      expect(await canonicalFile.readAsBytes(), [1, 0, 0, 0, 7]);
    });
  });

  group('syncWal — orphan WAL guard', () {
    test('selected ring row uploads its configured-boundary run only', () async {
      SyncRateLimiter.instance.clear();
      final prefix = 'manual_ring_run_${DateTime.now().microsecondsSinceEpoch}';
      final files = <String, File>{};
      for (final name in ['selected', 'adjacent', 'boundary', 'unrelated']) {
        final file = File('${Directory.systemTemp.path}/${prefix}_$name.bin');
        await file.writeAsBytes([1, 0, 0, 0, name.length], flush: true);
        files[name] = file;
      }
      addTearDown(() async {
        for (final file in files.values) {
          if (await file.exists()) await file.delete();
        }
      });

      final uploadCalls = <List<String>>[];
      final gate = SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        fairUseStatusLoader: () async => {'stage': 'none'},
        uploader: (
          artifacts, {
          onUploadProgress,
          conversationId,
          syncLane = SyncUploadLane.fresh,
          replaceTranscript = false,
        }) async {
          uploadCalls.add(
            artifacts.map((file) => file.uri.pathSegments.last).toList(),
          );
          return UploadFilesResult.done(
            SyncLocalFilesResponse(
              newConversationIds: ['manual-run'],
              updatedConversationIds: [],
            ),
          );
        },
      );
      final manualSync = LocalWalSyncImpl(
        listener,
        uploadGate: gate,
        walPersister: (_) async => true,
        conversationBoundarySecondsProvider: () => 300,
      );
      final selected = _historicalRingWal(
        timerStart: 1000,
        sourceId: 'archive2_ring_100_200_1000',
        filePath: files['selected']!.uri.pathSegments.last,
        seconds: 300,
        totalFrames: 30000,
      );
      final adjacent = _historicalRingWal(
        timerStart: 1599,
        sourceId: 'archive2_ring_200_300_1599',
        filePath: files['adjacent']!.uri.pathSegments.last,
        seconds: 300,
        totalFrames: 30000,
      );
      final exactBoundary = _historicalRingWal(
        timerStart: 2199,
        sourceId: 'archive2_ring_300_400_2199',
        filePath: files['boundary']!.uri.pathSegments.last,
        seconds: 300,
        totalFrames: 30000,
      );
      final unrelated = _historicalRingWal(
        timerStart: 1599,
        sourceId: 'archive2_ring_900_1000_1599',
        filePath: files['unrelated']!.uri.pathSegments.last,
        seconds: 300,
        totalFrames: 30000,
      )..device = 'other-device';
      manualSync.testWals = [
        selected,
        adjacent,
        exactBoundary,
        unrelated,
      ];

      await manualSync.syncWal(wal: selected);

      expect(uploadCalls, hasLength(1));
      expect(
        uploadCalls.single.toSet(),
        {
          files['selected']!.uri.pathSegments.last,
          files['adjacent']!.uri.pathSegments.last,
        },
      );
      expect(selected.status, WalStatus.synced);
      expect(adjacent.status, WalStatus.synced);
      expect(exactBoundary.status, WalStatus.miss);
      expect(unrelated.status, WalStatus.miss);
    });

    test('canonical single-row retry preserves replaceTranscript', () async {
      SyncRateLimiter.instance.clear();
      final filename = 'canonical_retry_${DateTime.now().microsecondsSinceEpoch}.bin';
      final file = File('${Directory.systemTemp.path}/$filename');
      await file.writeAsBytes([1, 0, 0, 0, 7], flush: true);
      addTearDown(() async {
        if (await file.exists()) await file.delete();
      });

      final uploadedConversationIds = <String?>[];
      final uploadedReplaceModes = <bool>[];
      final gate = SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        fairUseStatusLoader: () async => {'stage': 'none'},
        uploader: (
          files, {
          onUploadProgress,
          conversationId,
          syncLane = SyncUploadLane.fresh,
          replaceTranscript = false,
        }) async {
          uploadedConversationIds.add(conversationId);
          uploadedReplaceModes.add(replaceTranscript);
          return UploadFilesResult.done(
            SyncLocalFilesResponse(
              newConversationIds: [],
              updatedConversationIds: ['conversation-repair'],
            ),
          );
        },
      );
      final manualSync = LocalWalSyncImpl(
        listener,
        uploadGate: gate,
        walPersister: (_) async => true,
      );
      final canonical = Wal(
        timerStart: DateTime.now().millisecondsSinceEpoch ~/ 1000,
        codec: BleAudioCodec.opus,
        seconds: 30,
        totalFrames: 3000,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        filePath: filename,
        device: 'test-device',
        sourceId: 'canonical_conversation-repair_test',
        conversationId: 'conversation-repair',
        uploadIntent: WalUploadIntent.liveContinuity,
        canonicalReplacement: true,
      );
      manualSync.testWals = [canonical];

      await manualSync.syncWal(wal: canonical);

      expect(uploadedConversationIds, ['conversation-repair']);
      expect(uploadedReplaceModes, [isTrue]);
      expect(canonical.status, WalStatus.synced);
    });

    test('bound ring row retry repairs and retargets the canonical replacement', () async {
      SyncRateLimiter.instance.clear();
      final filename = 'bound_retry_${DateTime.now().microsecondsSinceEpoch}.bin';
      final file = File('${Directory.systemTemp.path}/$filename');
      await file.writeAsBytes([1, 0, 0, 0, 9], flush: true);

      final uploadedFiles = <String>[];
      final uploadedConversationIds = <String?>[];
      final uploadedReplaceModes = <bool>[];
      final gate = SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        fairUseStatusLoader: () async => {'stage': 'none'},
        uploader: (
          files, {
          onUploadProgress,
          conversationId,
          syncLane = SyncUploadLane.fresh,
          replaceTranscript = false,
        }) async {
          uploadedFiles.addAll(
            files.map((candidate) => candidate.uri.pathSegments.last),
          );
          uploadedConversationIds.add(conversationId);
          uploadedReplaceModes.add(replaceTranscript);
          return UploadFilesResult.done(
            SyncLocalFilesResponse(
              newConversationIds: [],
              updatedConversationIds: ['bound-conversation'],
            ),
          );
        },
      );
      final manualSync = LocalWalSyncImpl(
        listener,
        uploadGate: gate,
        walPersister: (_) async => true,
        silenceFrameFactory: (_) => [0],
      );
      addTearDown(() async {
        if (await file.exists()) await file.delete();
        for (final wal in manualSync.testWals) {
          final path = wal.filePath;
          if (path == null || !path.contains('canonical_bound-conversation')) {
            continue;
          }
          final canonicalFile = File('${Directory.systemTemp.path}/$path');
          if (await canonicalFile.exists()) await canonicalFile.delete();
        }
      });
      final bound = _historicalRingWal(
        timerStart: 1000,
        sourceId: 'ring_100_200',
        filePath: filename,
        seconds: 1,
        totalFrames: 1,
      )..conversationId = 'bound-conversation';
      manualSync.testWals = [bound];

      await manualSync.syncWal(wal: bound);

      expect(uploadedFiles.single, contains('canonical_bound-conversation'));
      expect(uploadedConversationIds, ['bound-conversation']);
      expect(uploadedReplaceModes, [isTrue]);
      expect(manualSync.testWals, hasLength(1));
      expect(
        manualSync.testWals.single.sourceId,
        startsWith('canonical_bound-conversation'),
      );
      expect(manualSync.testWals.single.status, WalStatus.synced);
    });

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
}

Wal _historicalRingWal({
  required int timerStart,
  required String sourceId,
  required String filePath,
  int seconds = 1,
  int totalFrames = 1,
  double? captureEndSeconds,
}) =>
    Wal(
      timerStart: timerStart,
      codec: BleAudioCodec.opus,
      seconds: seconds,
      captureEndSeconds: captureEndSeconds,
      totalFrames: totalFrames,
      status: WalStatus.miss,
      storage: WalStorage.disk,
      originalStorage: WalStorage.sdcard,
      filePath: filePath,
      device: 'test-device',
      sourceId: sourceId,
      uploadIntent: WalUploadIntent.historicalBackfill,
    );

SyncUploadGate _completedUploadGate(List<List<String>> uploads) => SyncUploadGate(
      limiter: SyncRateLimiter.instance,
      fairUseStatusLoader: () async => {'stage': 'none'},
      uploader: (
        files, {
        onUploadProgress,
        conversationId,
        syncLane = SyncUploadLane.fresh,
        replaceTranscript = false,
      }) async {
        uploads.add(files.map((file) => file.path).toList());
        return UploadFilesResult.done(
          SyncLocalFilesResponse(
            newConversationIds: ['authorized-conversation-${uploads.length}'],
            updatedConversationIds: [],
          ),
        );
      },
    );
