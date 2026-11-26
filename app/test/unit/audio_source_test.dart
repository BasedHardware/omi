import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/audio_sources/ble_device_source.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';

void main() {
  group('FrameSyncKey', () {
    test('equality by content', () {
      final a = FrameSyncKey([1, 2, 3]);
      final b = FrameSyncKey([1, 2, 3]);
      final c = FrameSyncKey([1, 2, 4]);

      expect(a, equals(b));
      expect(a, isNot(equals(c)));
      expect(a.hashCode, equals(b.hashCode));
    });

    test('BLE factory uses first 3 bytes', () {
      final key = FrameSyncKey.fromBleHeader([0x10, 0x20, 0x30, 0xFF, 0xFF]);
      expect(key.bytes, [0x10, 0x20, 0x30]);
    });

    test('index factory wraps to single byte', () {
      final key = FrameSyncKey.fromIndex(256);
      expect(key.bytes, [0]);

      final key2 = FrameSyncKey.fromIndex(255);
      expect(key2.bytes, [255]);
    });
  });

  group('BleDeviceSource', () {
    late BleDeviceSource source;

    setUp(() {
      source = BleDeviceSource(
        codec: BleAudioCodec.opus,
        deviceId: 'test-device',
        deviceModel: 'Omi',
      );
    });

    test('strips 3-byte firmware header from payload', () {
      final raw = [0x10, 0x20, 0x30, 0xAA, 0xBB, 0xCC, 0xDD];
      final frames = source.processBytes(raw);

      expect(frames.length, 1);
      expect(frames[0].payload, [0xAA, 0xBB, 0xCC, 0xDD]);
    });

    test('produces sync key from firmware header', () {
      final raw = [0x10, 0x20, 0x30, 0xAA, 0xBB];
      final frames = source.processBytes(raw);

      expect(frames[0].syncKey, equals(FrameSyncKey([0x10, 0x20, 0x30])));
    });

    test('returns empty list for packets <= 3 bytes', () {
      expect(source.processBytes([1, 2, 3]).length, 0);
      expect(source.processBytes([1, 2]).length, 0);
      expect(source.processBytes([]).length, 0);
    });

    test('getSocketPayload strips header', () {
      final raw = [0x10, 0x20, 0x30, 0xAA, 0xBB];
      expect(source.getSocketPayload(raw), [0xAA, 0xBB]);
    });

    test('getSocketPayload returns empty for header-only packets', () {
      expect(source.getSocketPayload([1, 2, 3]), isEmpty);
      expect(source.getSocketPayload([1, 2]), isEmpty);
      expect(source.getSocketPayload([]), isEmpty);
    });

    test('flush returns empty (no buffering)', () {
      expect(source.flush(), isEmpty);
    });

    test('exposes correct codec and device info', () {
      expect(source.codec, BleAudioCodec.opus);
      expect(source.deviceId, 'test-device');
      expect(source.deviceModel, 'Omi');
    });

    test('WAL compatibility: processBytes payload matches old sublist(3) behavior', () {
      // Simulate a typical BLE Opus packet (3-byte header + audio)
      final blePacket = [0x05, 0x00, 0x02, ...List.filled(80, 0xAA)];
      final frames = source.processBytes(blePacket);

      // Old behavior: wal.data[i].sublist(3) during flush
      final oldBehavior = blePacket.sublist(3);
      // New behavior: WalFrame.payload (already headerless)
      final newBehavior = frames[0].payload;

      expect(newBehavior, equals(oldBehavior));
      expect(newBehavior.length, 80);
    });
  });

  group('WalFrame', () {
    test('stores payload and sync key', () {
      final payload = [1, 2, 3, 4, 5];
      final key = FrameSyncKey([0x10, 0x20, 0x30]);
      final frame = WalFrame(payload: payload, syncKey: key);

      expect(frame.payload, payload);
      expect(frame.syncKey, key);
    });
  });
}
