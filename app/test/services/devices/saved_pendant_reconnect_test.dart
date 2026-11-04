import 'dart:async';
import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/devices/saved_pendant_reconnect.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('an already connected saved target arms native intent without another connect', () {
    fakeAsync((async) {
      var connects = 0;
      final configured = <bool>[];
      final retry = SavedPendantReconnect(
        target: () => 'saved',
        blocked: (_) => false,
        connected: (_) => true,
        connect: (_, __) async {
          connects++;
        },
        configure: (_, enabled) async => configured.add(enabled),
        retire: (_) async {},
        observeTarget: (_) => () {},
        killed: () => false,
        record: (_, __, ___, ____) {},
      );
      retry.start();
      retry.ensure('launch');
      async.flushMicrotasks();
      expect(configured, [true]);
      expect(connects, 0);
      retry.stop();
    });
  });

  for (final refresh in ['throws', 'hangs', 'false']) {
    test('cached default ON connects immediately when refresh $refresh', () {
      fakeAsync((async) {
        var calls = 0;
        final retry = SavedPendantReconnect(
          target: () => 'saved',
          blocked: (_) => false,
          connected: (_) => false,
          connect: (_, __) async {
            calls++;
            throw TimeoutException('out of range');
          },
          configure: (_, __) async {},
          retire: (_) async {},
          observeTarget: (_) => () {},
          killed: () => false,
          refreshKilled: () => refresh == 'throws'
              ? Future.error(StateError('offline'))
              : refresh == 'hangs'
                  ? Completer<bool>().future
                  : Future.value(false),
          record: (_, __, ___, ____) {},
        );
        retry.start();
        retry.ensure('launch');
        async.flushMicrotasks();
        expect(calls, 1, reason: 'no fake time elapsed while PostHog is unavailable');
        async.elapse(const Duration(minutes: 20));
        expect(calls, greaterThan(3));
        expect(calls, lessThan(13));
        retry.stop();
        final stopped = calls;
        async.elapse(const Duration(hours: 1));
        expect(calls, stopped);
      });
    });
  }

  test('a late kill disarms native and stops retry timers without delaying launch', () {
    fakeAsync((async) {
      var calls = 0;
      final configured = <bool>[];
      final flag = Completer<bool>();
      final retry = SavedPendantReconnect(
        target: () => 'saved',
        blocked: (_) => false,
        connected: (_) => false,
        connect: (_, __) async {
          calls++;
          throw TimeoutException('offline');
        },
        configure: (_, enabled) async => configured.add(enabled),
        retire: (_) async {},
        observeTarget: (_) => () {},
        killed: () => false,
        refreshKilled: () => flag.future,
        record: (_, __, ___, ____) {},
      );
      retry.start();
      retry.ensure('launch');
      async.flushMicrotasks();
      expect(calls, 1);
      async.elapse(const Duration(seconds: 3)); // A slow refresh still applies after launch has connected.
      flag.complete(true);
      async.flushMicrotasks();
      expect(configured, [true, false]);
      expect(retry.killed, isTrue);
      async.elapse(const Duration(minutes: 20));
      expect(calls, 1);
      retry.stop();
    });
  });

  test('attempt telemetry stays bounded for a long outage and preserves terminal success', () {
    fakeAsync((async) {
      var up = false;
      final events = <String>[];
      final retry = SavedPendantReconnect(
        target: () => 'saved',
        blocked: (_) => false,
        connected: (_) => up,
        connect: (_, __) async => throw TimeoutException('offline'),
        configure: (_, __) async {},
        retire: (_) async {},
        observeTarget: (_) => () {},
        killed: () => false,
        record: (_, __, result, ___) => events.add(result),
      );
      retry.start();
      retry.ensure('launch');
      async.elapse(const Duration(hours: 12));
      up = true;
      retry.stateChanged('saved', true);
      expect(events, ['attempted', 'failed:timeout', 'connected']);
      retry.stateChanged('saved', false);
      retry.stateChanged('saved', true);
      expect(events.where((result) => result == 'connected'), hasLength(1));
      retry.stop();
    });
  });
}
