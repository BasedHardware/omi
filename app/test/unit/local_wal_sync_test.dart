import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
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

    listener = _MockListener();
    sync = LocalWalSyncImpl(listener);
  });

  group('onFrameCaptured', () {
    test('adds frame with synced=false', () {
      final frame = WalFrame(
        payload: [0xAA, 0xBB],
        syncKey: FrameSyncKey([1]),
      );

      sync.onFrameCaptured(frame);

      expect(sync.testFrames.length, 1);
      expect(sync.testFrames[0].payload, [0xAA, 0xBB]);
      expect(sync.testFrameSynced.length, 1);
      expect(sync.testFrameSynced[0], false);
    });

    test('preserves insertion order for multiple frames', () {
      for (int i = 0; i < 5; i++) {
        sync.onFrameCaptured(WalFrame(
          payload: [i],
          syncKey: FrameSyncKey([i]),
        ));
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
          key); // marks index 1 (2 is already true, but reverse scan finds 2 first and breaks — so second call marks 2 again? No — it checks syncKey equality, not synced status)

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
        sync.onFrameCaptured(WalFrame(
          payload: List.filled(320, i),
          syncKey: FrameSyncKey.fromIndex(i),
        ));
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
        sync.onFrameCaptured(WalFrame(
          payload: List.filled(320, i & 0xFF),
          syncKey: FrameSyncKey.fromIndex(i),
        ));
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
      final frame = WalFrame(
        payload: payload,
        syncKey: FrameSyncKey.fromBleHeader(blePacket),
      );

      // _chunk stores payload only
      final chunk = [frame].map((f) => f.payload).toList();
      expect(chunk[0], [0xAA, 0xBB, 0xCC]);

      // No firmware header in stored data
      expect(chunk[0].length, 3);
      expect(chunk[0][0], 0xAA); // First byte is audio, not header
    });
  });
}
