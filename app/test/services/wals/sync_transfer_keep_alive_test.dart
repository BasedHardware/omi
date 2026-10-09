import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/services.dart';
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

    test('non-mobile hosts never start the native service', () async {
      var starts = 0;
      var stops = 0;
      final keepAlive = SyncTransferKeepAlive(
        isAndroid: () => false,
        isIOS: () => false,
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

    test('iOS starts and stops one bounded background-task lease', () async {
      var starts = 0;
      var stops = 0;
      final keepAlive = SyncTransferKeepAlive(
        isAndroid: () => false,
        isIOS: () => true,
        start: () async {
          starts++;
        },
        stop: () async {
          stops++;
        },
      );

      await keepAlive.acquire();
      await keepAlive.acquire();
      await keepAlive.release();
      expect(starts, 1);
      expect(stops, 0);

      await keepAlive.release();
      expect(stops, 1);
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

    for (final reason in ['expired', 'invalid']) {
      test('iOS $reason notification resets refs and reacquire starts a fresh task', () async {
        var starts = 0;
        var stops = 0;
        Future<dynamic> Function(MethodCall)? nativeHandler;
        final keepAlive = SyncTransferKeepAlive(
          isAndroid: () => false,
          isIOS: () => true,
          start: () async => starts++,
          stop: () async => stops++,
          installNativeHandler: (handler) => nativeHandler = handler,
        );

        await keepAlive.acquire();
        await keepAlive.acquire();
        expect(starts, 1);
        expect(keepAlive.refCount, 2);

        await nativeHandler!(MethodCall('expired', {'reason': reason}));
        expect(keepAlive.refCount, 0);

        await keepAlive.acquire();
        expect(starts, 2, reason: 'the old native task no longer backs a Dart ref');
        await keepAlive.release();
        expect(stops, 1);
      });
    }
  });
}
