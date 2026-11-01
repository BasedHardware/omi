import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/wals/sdcard_wal_sync.dart';

/// An SD card read arms a 5s first-byte timer, then a 15s stall timer on every
/// packet. The 5s arm used to assign over the stall timer without cancelling it,
/// so a packet that arrived before that arm left a timer that still fired and
/// aborted a transfer that was still receiving data.
void main() {
  test('replaceTimer cancels the timer it replaces', () {
    fakeAsync((async) {
      var fired = 0;
      final first = SDCardWalSyncImpl.replaceTimer(null, const Duration(seconds: 5), () => fired++);
      SDCardWalSyncImpl.replaceTimer(first, const Duration(seconds: 15), () => fired++);

      async.elapse(const Duration(seconds: 6));
      expect(fired, 0);

      async.elapse(const Duration(seconds: 10));
      expect(fired, 1);
    });
  });
}
