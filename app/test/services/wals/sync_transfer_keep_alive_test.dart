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

      final releaseFirst = await keepAlive.acquireScoped();
      final releaseSecond = await keepAlive.acquireScoped();
      expect(keepAlive.refCount, 2);
      expect(starts, 1);
      expect(stops, 0);

      await releaseFirst();
      await releaseFirst();
      expect(keepAlive.isHeld, isTrue);
      expect(stops, 0);

      await releaseSecond();
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

      final releaseFirst = await keepAlive.acquireScoped();
      final releaseSecond = await keepAlive.acquireScoped();
      await keepAlive.releaseAll();

      expect(keepAlive.refCount, 0);
      expect(stops, 1);

      await releaseFirst();
      await releaseSecond();
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

      final release = await keepAlive.acquireScoped();
      await release();

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

      final releaseFirst = await keepAlive.acquireScoped();
      final releaseSecond = await keepAlive.acquireScoped();
      await releaseFirst();
      expect(starts, 1);
      expect(stops, 0);

      await releaseSecond();
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

      await keepAlive.acquireScoped();
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

        final releaseExpiredFirst = await keepAlive.acquireScoped();
        final releaseExpiredSecond = await keepAlive.acquireScoped();
        expect(starts, 1);
        expect(keepAlive.refCount, 2);

        await nativeHandler!(MethodCall('expired', {'reason': reason}));
        expect(keepAlive.refCount, 0);

        final releaseCurrent = await keepAlive.acquireScoped();
        expect(starts, 2, reason: 'the old native task no longer backs a Dart ref');
        await releaseExpiredFirst();
        await releaseExpiredSecond();
        expect(keepAlive.refCount, 1);
        await releaseCurrent();
        expect(stops, 1);
      });
    }
  });
}
