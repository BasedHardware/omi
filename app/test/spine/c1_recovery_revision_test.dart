import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/capture_session_owner.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import '../support/spine/contract.dart';

void main() {
  contractTest('C1 coalescing preserves explicit retry when auto-upload is disabled', () async {
    final gate = Completer<void>();
    var drains = 0;
    final coordinator = RecordingTransferCoordinator(
      reconcile: () => gate.future,
      discover: () async {},
      refreshPending: () async {},
      drain: () async {
        drains++;
        return const RecordingTransferDrainResult.skipped();
      },
      autoUploadEnabled: () => false,
    );
    final owner =
        CaptureSessionOwner(coordinator: coordinator, startForeground: () async {}, stopForeground: () async {});
    final startup = owner.requestRecovery(WakeTrigger.startup);
    await pumpEventQueue();
    final retry = owner.requestRecovery(WakeTrigger.userRetry);
    gate.complete();
    await Future.wait([startup, retry]);
    await coordinator.waitUntilIdle();
    expect(drains, 1);
    await owner.requestRecovery(WakeTrigger.startup);
    expect(drains, 1); // did not permanently turn automatic upload on
    await owner.close();
  });

  contractTest('C1 a new WAL revision during a drain queues one serial pass, not a lost wake', () async {
    final gate = Completer<void>();
    var drains = 0;
    var active = 0;
    var peak = 0;
    final coordinator = RecordingTransferCoordinator(
      reconcile: () async {},
      discover: () async {},
      refreshPending: () async {},
      drain: () async {
        drains++;
        active++;
        if (active > peak) peak = active;
        if (drains == 1) await gate.future;
        active--;
        return const RecordingTransferDrainResult.skipped();
      },
      autoUploadEnabled: () => true,
    );
    final owner =
        CaptureSessionOwner(coordinator: coordinator, startForeground: () async {}, stopForeground: () async {});
    final first = owner.requestRecovery(WakeTrigger.startup, inventoryRevision: 1);
    await pumpEventQueue();
    final duplicate = owner.requestRecovery(WakeTrigger.deviceConnected, inventoryRevision: 1);
    final changed = owner.requestRecovery(WakeTrigger.cooldownElapsed, inventoryRevision: 2);
    final changedAgain = owner.requestRecovery(WakeTrigger.cooldownElapsed, inventoryRevision: 2);
    expect(drains, 1);
    gate.complete();
    await Future.wait([first, duplicate, changed, changedAgain]);
    await coordinator.waitUntilIdle();
    expect(drains, 2);
    expect(peak, 1);
    await owner.close();
  });
}
