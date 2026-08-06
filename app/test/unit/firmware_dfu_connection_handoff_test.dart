import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/home/firmware_mixin.dart';

void main() {
  test('success and duplicate terminal callbacks release then resume exactly once', () async {
    final events = <String>[];
    final handoff = FirmwareDfuConnectionHandoff(
      releaseUpdater: () async => events.add('release updater'),
      resumeDeviceConnection: () async => events.add('resume device'),
    );

    await Future.wait([handoff.finish(), handoff.finish()]);
    await handoff.finish();

    expect(events, ['release updater', 'resume device']);
  });

  test('page disposal and a later terminal callback share the in-flight reclaim', () async {
    final releaseGate = Completer<void>();
    final events = <String>[];
    final handoff = FirmwareDfuConnectionHandoff(
      releaseUpdater: () async {
        events.add('release updater');
        await releaseGate.future;
      },
      resumeDeviceConnection: () async => events.add('resume device'),
    );

    final pageDisposal = handoff.finish();
    final terminalCallback = handoff.finish();
    await pumpEventQueue();
    expect(events, ['release updater']);

    releaseGate.complete();
    await Future.wait([pageDisposal, terminalCallback]);

    expect(events, ['release updater', 'resume device']);
  });

  test('release failure still resumes and is memoized for later callbacks', () async {
    final events = <String>[];
    final handoff = FirmwareDfuConnectionHandoff(
      releaseUpdater: () async {
        events.add('release updater');
        throw StateError('release failed');
      },
      resumeDeviceConnection: () async => events.add('resume device'),
    );

    await expectLater(handoff.finish(), throwsStateError);
    await expectLater(handoff.finish(), throwsStateError);

    expect(events, ['release updater', 'resume device']);
  });

  test('resume failure is returned identically without a second reconnect', () async {
    var reconnectAttempts = 0;
    final handoff = FirmwareDfuConnectionHandoff(
      releaseUpdater: () async {},
      resumeDeviceConnection: () async {
        reconnectAttempts++;
        throw StateError('reconnect failed');
      },
    );

    await expectLater(handoff.finish(), throwsStateError);
    await expectLater(handoff.finish(), throwsStateError);

    expect(reconnectAttempts, 1);
  });
}
