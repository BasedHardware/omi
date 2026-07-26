import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/wals/sdcard_wal_sync.dart';

void main() {
  test('a ring ACK cannot disable the legacy SD first-packet timeout', () {
    fakeAsync((async) {
      var timedOut = false;
      final deadline = LegacyStorageFirstPacketDeadline(
        timeout: const Duration(seconds: 5),
        onTimeout: () => timedOut = true,
      )..start();

      expect(deadline.observe([0x01, 0x09]), isFalse);
      async.elapse(const Duration(seconds: 5));

      expect(timedOut, isTrue);
    });
  });

  test('a supported legacy packet satisfies the deadline', () {
    fakeAsync((async) {
      var timedOut = false;
      final deadline = LegacyStorageFirstPacketDeadline(
        timeout: const Duration(seconds: 5),
        onTimeout: () => timedOut = true,
      )..start();

      expect(deadline.observe(List<int>.filled(83, 0)), isTrue);
      async.elapse(const Duration(seconds: 10));

      expect(timedOut, isFalse);
    });
  });
}
