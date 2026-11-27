// Hermetic loader parser and stale-session regression coverage.
// No radio, device, or backend is used to qualify these wire/session contracts.
import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/bootloader_fingerprint.dart';

List<int> packet({int status = 1}) =>
    [1, status, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, ...List.filled(32, status == 1 ? 0xab : 0)];

void main() {
  test('measured digest is full lowercase32-byte SHA256; not a qualification verdict', () {
    expect(BootloaderFingerprint.parse(packet())?.sha256, 'ab' * 32);
  });
  for (final status in [0, 2, 3, 4]) {
    test('non-OK status $status remains unknown and rejects nonzero digest', () {
      expect(BootloaderFingerprint.parse(packet(status: status))?.sha256, isNull);
      expect(BootloaderFingerprint.parse(packet(status: status))?.status, status);
      final invalid = packet(status: status)..[12] = 1;
      expect(BootloaderFingerprint.parse(invalid), isNull);
    });
  }
  test('reject truncated, oversized, non-byte, unknown schema/status/algo/reserved/range', () {
    for (var length = 0; length < 44; length++) {
      expect(BootloaderFingerprint.parse(packet().sublist(0, length)), isNull);
    }
    expect(BootloaderFingerprint.parse([...packet(), 0]), isNull);
    for (final index in [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]) {
      final invalid = packet();
      invalid[index] ^= 0x80;
      expect(BootloaderFingerprint.parse(invalid), isNull, reason: 'index $index');
    }
    expect(BootloaderFingerprint.parse(packet()..[1] = 5), isNull);
    expect(BootloaderFingerprint.parse(packet()..[12] = -1), isNull);
    expect(BootloaderFingerprint.parse(packet()..[12] = 256), isNull);
  });
  test('same-device reconnect while read pending discards old evidence', () async {
    var epoch = 1;
    final pending = Completer<List<int>?>();
    final session =
        FirmwareDeviceSession(deviceId: 'A', isCurrent: () => epoch == 1, readFingerprint: () => pending.future);
    final reading = session.readBootloaderSha256();
    epoch++;
    pending.complete(packet());
    expect(await reading, isNull);
    expect(session.isCurrent, isFalse);
  });
  test('device switch/disconnect before read does not read retired peer', () async {
    var reads = 0;
    final session = FirmwareDeviceSession(
        deviceId: 'A',
        isCurrent: () => false,
        readFingerprint: () async {
          reads++;
          return packet();
        });
    expect(await session.readBootloaderSha256(), isNull);
    expect(reads, 0);
  });
  test('each check reads fresh; absence on .21 never borrows a prior digest', () async {
    var reads = 0;
    final session = FirmwareDeviceSession(
        deviceId: 'A',
        isCurrent: () => true,
        readFingerprint: () async {
          reads++;
          return reads == 1 ? packet() : null;
        });
    expect(await session.readBootloaderSha256(), 'ab' * 32);
    expect(await session.readBootloaderSha256(), isNull);
    expect(reads, 2);
  });
  test('read error is unknown', () async {
    final session = FirmwareDeviceSession(
        deviceId: 'A', isCurrent: () => true, readFingerprint: () async => throw StateError('missing characteristic'));
    expect(await session.readBootloaderSha256(), isNull);
  });
  test('device binding remains testable after the backend await', () async {
    var current = true;
    final session =
        FirmwareDeviceSession(deviceId: 'A', isCurrent: () => current, readFingerprint: () async => packet());
    expect(await session.readBootloaderSha256(), 'ab' * 32);
    current = false;
    expect(session.isCurrent, isFalse);
  });
}
