import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/wals/sync_transfer_keep_alive.dart';

void main() {
  group('SyncTransferKeepAlive', () {
    test('nested acquire starts once and stop waits for the last release', () async {
      var starts = 0;
      var stops = 0;
      final keepAlive = SyncTransferKeepAlive(
        isAndroid: () => true,
        start: () async {
          starts++;
        },
        stop: () async {
          stops++;
        },
      );

      await keepAlive.acquire();
      await keepAlive.acquire();
      expect(keepAlive.refCount, 2);
      expect(starts, 1);
      expect(stops, 0);

      await keepAlive.release();
      expect(keepAlive.isHeld, isTrue);
      expect(stops, 0);

      await keepAlive.release();
      expect(keepAlive.isHeld, isFalse);
      expect(stops, 1);
    });

    test('releaseAll stops immediately and extra releases are no-ops', () async {
      var stops = 0;
      final keepAlive = SyncTransferKeepAlive(
        isAndroid: () => true,
        start: () async {},
        stop: () async {
          stops++;
        },
      );

      await keepAlive.acquire();
      await keepAlive.acquire();
      await keepAlive.releaseAll();

      expect(keepAlive.refCount, 0);
      expect(stops, 1);

      await keepAlive.release();
      await keepAlive.releaseAll();
      expect(stops, 1);
    });

    test('non-Android hosts never start the native service', () async {
      var starts = 0;
      var stops = 0;
      final keepAlive = SyncTransferKeepAlive(
        isAndroid: () => false,
        start: () async {
          starts++;
        },
        stop: () async {
          stops++;
        },
      );

      await keepAlive.acquire();
      await keepAlive.release();

      expect(starts, 0);
      expect(stops, 0);
    });

    test('a failed start still pairs with stop so cancel can drop the ref', () async {
      var stops = 0;
      final keepAlive = SyncTransferKeepAlive(
        isAndroid: () => true,
        start: () async {
          throw StateError('startForeground rejected');
        },
        stop: () async {
          stops++;
        },
      );

      await keepAlive.acquire();
      expect(keepAlive.isHeld, isTrue);
      await keepAlive.releaseAll();
      expect(keepAlive.isHeld, isFalse);
      expect(stops, 1);
    });
  });
}
