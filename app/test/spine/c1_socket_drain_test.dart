import 'dart:async';
import '../support/spine/contract.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/capture_session_owner.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';

CaptureSessionOwner owner() => CaptureSessionOwner(
    coordinator: RecordingTransferCoordinator(
        reconcile: () async {},
        discover: () async {},
        refreshPending: () async {},
        drain: () async => const RecordingTransferDrainResult.skipped(),
        autoUploadEnabled: () => true),
    startForeground: () async {},
    stopForeground: () async {});
void main() {
  contractTest('roll while replacing a published socket cannot return obsolete new socket', () async {
    final o = owner();
    o.replaceSession('a');
    final closingOld = Completer<void>();
    final closed = <String>[];
    await o.connect<String>(
        configuration: 'old',
        open: () async => 'old',
        close: (s) async {
          closed.add(s);
          await closingOld.future;
        });
    final next = o.connect<String>(
        configuration: 'new',
        open: () async => 'new',
        close: (s) async {
          closed.add(s);
        });
    await pumpEventQueue();
    expect(closed, ['old']);
    o.replaceSession('b');
    closingOld.complete();
    final result = await next;
    final beforeCleanup = List<String>.of(closed);
    await o.close();
    expect(result, isNull);
    expect(beforeCleanup, ['old', 'new']);
  });
  contractTest('close waits for late open to be reaped', () async {
    final o = owner();
    o.replaceSession('a');
    final gate = Completer<String>();
    final closed = <String>[];
    final pending = o.connect<String>(
        configuration: 'one',
        open: () => gate.future,
        close: (s) async {
          closed.add(s);
        });
    var done = false;
    final closing = o.close().then((_) => done = true);
    await pumpEventQueue();
    final premature = done;
    gate.complete('late');
    expect(await pending, isNull);
    await closing;
    expect(closed, ['late']);
    expect(premature, isFalse);
  });
}
