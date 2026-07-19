import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/wals/sdcard_wal_sync.dart';

/// Regression tests for the 83-byte SD card packet parser.
///
/// Crash: FlutterError — RangeError (end): Invalid value: Not in inclusive
/// range 4..83: 217 in SDCardWalSyncImpl._readStorageBytesToFileLegacy.
/// A corrupted length byte (value[3]) larger than the packet payload made
/// `value.sublist(4, 4 + amount)` throw.
void main() {
  List<int> packet(int amount, {int length = 83}) {
    final p = List<int>.filled(length, 0xAB);
    p[3] = amount;
    return p;
  }

  group('SDCardWalSyncImpl.parseLegacyPacketFrame', () {
    test('returns the frame for a valid length byte', () {
      final frame = SDCardWalSyncImpl.parseLegacyPacketFrame(packet(79));
      expect(frame, isNotNull);
      expect(frame!.length, 79);
    });

    test('returns a partial frame when length byte is under the max', () {
      final frame = SDCardWalSyncImpl.parseLegacyPacketFrame(packet(40));
      expect(frame, isNotNull);
      expect(frame!.length, 40);
    });

    test('returns null instead of throwing for a corrupted length byte (crash case: 217)', () {
      expect(SDCardWalSyncImpl.parseLegacyPacketFrame(packet(217)), isNull);
    });

    test('returns null when the frame would exceed the packet by one byte', () {
      expect(SDCardWalSyncImpl.parseLegacyPacketFrame(packet(80)), isNull);
    });

    test('returns null for a zero length byte', () {
      expect(SDCardWalSyncImpl.parseLegacyPacketFrame(packet(0)), isNull);
    });
  });
}
