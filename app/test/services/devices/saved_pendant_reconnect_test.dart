import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/devices/saved_pendant_reconnect.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  for (final flag in ['false', 'throws', 'hangs', 'true']) {
    test('kill switch $flag: only true disables retries and launch still connects', () {
      fakeAsync((async) {
        var calls = 0;
        final configured = <bool>[];
        final events = <String>[];
        final retry = SavedPendantReconnect(
          target: () => 'saved',
          blocked: (_) => false,
          connected: (_) => false,
          connect: (_) async {
            calls++;
            throw TimeoutException('out of range');
          },
          configure: (_, enabled) async => configured.add(enabled),
          killed: () {
            if (flag == 'throws') return Future.error(StateError('unreachable'));
            if (flag == 'hangs') return Completer<bool>().future;
            return Future.value(flag == 'true');
          },
          record: (_, __, result, ___) => events.add(result),
        );
        retry.start();
        retry.ensure('launch');
        async.elapse(const Duration(seconds: 4));
        expect(calls, 1);
        expect(configured.first, flag != 'true');
        async.elapse(const Duration(minutes: 20));
        if (flag == 'true') {
          expect(calls, 1);
          expect(events, contains('skipped:kill_switch'));
        } else {
          expect(calls, greaterThan(3));
          expect(calls, lessThan(13), reason: 'backoff caps at five minutes, never spins');
          expect(events, contains('failed:timeout'));
        }
        retry.stop();
        final stoppedAt = calls;
        async.elapse(const Duration(hours: 1));
        expect(calls, stoppedAt);
      });
    });
  }

  test('a native-only reconnect does not reuse the completed Dart attempt outcome', () {
    fakeAsync((async) {
      var connected = false;
      final outcomes = <String>[];
      final retry = SavedPendantReconnect(
        target: () => 'saved',
        blocked: (_) => false,
        connected: (_) => connected,
        connect: (_) async {},
        configure: (_, __) async {},
        killed: () async => false,
        record: (_, __, result, ___) => outcomes.add(result),
      );
      retry.start();
      retry.ensure('launch');
      async.flushMicrotasks();
      connected = true;
      retry.stateChanged('saved', true);
      connected = false;
      retry.stateChanged('saved', false);
      connected = true;
      retry.stateChanged('saved', true);
      expect(outcomes.where((result) => result == 'connected'), hasLength(1));
      retry.stop();
    });
  });

  test('dedupes overlapping triggers and rechecks manual intent after flag read', () {
    fakeAsync((async) {
      var manual = false;
      var calls = 0;
      var flagReads = 0;
      final flag = Completer<bool>();
      final retry = SavedPendantReconnect(
        target: () => 'saved',
        blocked: (_) => manual,
        connected: (_) => false,
        connect: (_) async {
          calls++;
        },
        configure: (_, __) async {},
        killed: () {
          flagReads++;
          return flag.future;
        },
        record: (_, __, ___, ____) {},
      );
      retry.start();
      retry.ensure('launch');
      retry.ensure('resume');
      retry.ensure('adapter_on');
      expect(flagReads, 1);
      manual = true;
      flag.complete(false);
      async.elapse(const Duration(minutes: 10));
      expect(calls, 0);
      retry.stop();
    });
  });
}
