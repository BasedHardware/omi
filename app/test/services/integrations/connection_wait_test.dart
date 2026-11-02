import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/integrations/connection_wait.dart';

void main() {
  testWidgets('slow reads never overlap; a foreground return replaces an older verdict', (tester) async {
    final first = Completer<ConnectionProbe>();
    var calls = 0;
    final wait = ConnectionWait(
        probe: () {
          calls++;
          return calls == 1 ? first.future : Future.value(ConnectionProbe.connected);
        },
        isCurrent: () => true);
    ConnectionWaitOutcome? result;
    unawaited(wait.start().then((v) => result = v));
    await tester.pump(const Duration(seconds: 10));
    expect(calls, 1);
    wait.refresh();
    first.complete(ConnectionProbe.failed);
    await tester.pump();
    expect(calls, 2);
    expect(result, ConnectionWaitOutcome.connected);
  });

  testWidgets('pending authorization is rechecked and becomes connected without another tap', (tester) async {
    var connected = false;
    var calls = 0;
    final wait = ConnectionWait(
        probe: () async {
          calls++;
          return connected ? ConnectionProbe.connected : ConnectionProbe.pending;
        },
        isCurrent: () => true);
    ConnectionWaitOutcome? result;
    unawaited(wait.start().then((v) => result = v));
    await tester.pump();
    connected = true;
    await tester.pump(const Duration(seconds: 3));
    expect(calls, 2);
    expect(result, ConnectionWaitOutcome.connected);
  });

  testWidgets('a hung probe ends the wait and its late connected result is ignored', (tester) async {
    final pending = Completer<ConnectionProbe>();
    final wait =
        ConnectionWait(probe: () => pending.future, isCurrent: () => true, probeTimeout: const Duration(seconds: 1));
    ConnectionWaitOutcome? result;
    unawaited(wait.start().then((v) => result = v));
    await tester.pump(const Duration(seconds: 2));
    expect(result, ConnectionWaitOutcome.failed);
    pending.complete(ConnectionProbe.connected);
    await tester.pump();
    expect(result, ConnectionWaitOutcome.failed);
  });

  testWidgets('overall deadline cancels polling and never reports connection', (tester) async {
    final wait = ConnectionWait(
        probe: () async => ConnectionProbe.pending, isCurrent: () => true, waitTimeout: const Duration(seconds: 1));
    ConnectionWaitOutcome? result;
    unawaited(wait.start().then((v) => result = v));
    await tester.pump();
    await tester.pump(const Duration(seconds: 2));
    expect(result, ConnectionWaitOutcome.timedOut);
    expect(wait.isActive, isFalse);
  });

  testWidgets('leaving the page/account cancels the owned wait and its timers', (tester) async {
    var current = true;
    final pending = Completer<ConnectionProbe>();
    final wait = ConnectionWait(probe: () => pending.future, isCurrent: () => current);
    ConnectionWaitOutcome? result;
    unawaited(wait.start().then((v) => result = v));
    current = false;
    pending.complete(ConnectionProbe.connected);
    await tester.pump();
    expect(result, ConnectionWaitOutcome.cancelled);
    wait.refresh();
    expect(wait.isActive, isFalse);
  });
  testWidgets('cancellation releases a hung dependency without retaining a deadline timer', (tester) async {
    final pending = Completer<ConnectionProbe>();
    final wait = ConnectionWait(probe: () => pending.future, isCurrent: () => true);
    final result = wait.start();
    wait.cancel();
    await tester.pump();
    expect(await result, ConnectionWaitOutcome.cancelled);
    pending.complete(ConnectionProbe.connected);
    await tester.pump();
    expect(wait.isActive, isFalse);
  });
}
