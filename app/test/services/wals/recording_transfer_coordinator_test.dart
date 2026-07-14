import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';

void main() {
  group('RecordingTransferCoordinator', () {
    test('connectivity restoration drains without a Bluetooth event (#7373)', () async {
      final harness = _TransferHarness();
      addTearDown(harness.dispose);

      harness.connectivity.add(false);
      harness.connectivity.add(true);
      await _settle();

      expect(harness.drainPasses, 1);
    });

    test('connectivity restoration drains after a successful startup pass', () async {
      final harness = _TransferHarness();
      addTearDown(harness.dispose);

      await harness.coordinator.wake(WakeTrigger.startup);
      harness.backlog.add('wal-after-startup');
      harness.connectivity.add(false);
      harness.connectivity.add(true);
      await _settle();

      expect(harness.drainPasses, 2);
    });

    test('five concurrent wakes schedule exactly one additional serial pass', () async {
      final harness = _TransferHarness();
      addTearDown(harness.dispose);
      final reconcileGate = Completer<void>();
      harness.reconcileGate = reconcileGate;

      final firstWake = harness.coordinator.wake(WakeTrigger.startup);
      await _settle();
      expect(harness.reconcilePasses, 1);

      final concurrentWakes = List.generate(
        5,
        (_) => harness.coordinator.wake(WakeTrigger.connectivityRestored),
      );
      reconcileGate.complete();
      await Future.wait([firstWake, ...concurrentWakes]);

      expect(harness.reconcilePasses, 2);
      expect(harness.drainPasses, 1);
      expect(harness.maximumConcurrentDrains, 1);
    });

    test('a retryable drain failure never presents synced and schedules cooldown', () async {
      final harness = _TransferHarness()..drainFails = true;
      addTearDown(harness.dispose);

      await harness.coordinator.wake(WakeTrigger.startup);

      expect(harness.walState, 'miss');
      expect(harness.walState, isNot('synced'));
      expect(harness.scheduledCooldowns, hasLength(1));
      expect(harness.scheduledCooldowns.single.delay, const Duration(seconds: 5));
      expect(harness.coordinator.nextCooldownAt, DateTime.utc(2026, 1, 1, 0, 0, 5));
    });

    test('backgrounding cancels a scheduled foreground cooldown wake', () async {
      final harness = _TransferHarness()..drainFails = true;
      addTearDown(harness.dispose);

      await harness.coordinator.wake(WakeTrigger.startup);
      final scheduled = harness.scheduledCooldowns.single;
      harness.coordinator.setForeground(false);
      scheduled.callback();
      await _settle();

      expect(harness.drainPasses, 1);
      expect(harness.coordinator.nextCooldownAt, isNull);
    });

    test('background recovery wakes wait for the foreground before draining', () async {
      final harness = _TransferHarness();
      addTearDown(harness.dispose);

      harness.coordinator.setForeground(false);
      harness.connectivity.add(false);
      harness.connectivity.add(true);
      await _settle();

      expect(harness.reconcilePasses, 0);
      expect(harness.drainPasses, 0);

      harness.coordinator.setForeground(true);
      await harness.coordinator.wake(WakeTrigger.foregrounded);

      expect(harness.reconcilePasses, 1);
      expect(harness.drainPasses, 1);
    });

    test('startup resumes a pending backlog once without loss or duplication', () async {
      final sharedBacklog = <String>['pending-wal'];
      final drainedWalIds = <String>[];
      final firstProcess = _TransferHarness(backlog: sharedBacklog, drainedWalIds: drainedWalIds);
      addTearDown(firstProcess.dispose);

      await firstProcess.coordinator.wake(WakeTrigger.startup);
      expect(drainedWalIds, ['pending-wal']);
      expect(sharedBacklog, isEmpty);

      final restartedProcess = _TransferHarness(backlog: sharedBacklog, drainedWalIds: drainedWalIds);
      addTearDown(restartedProcess.dispose);
      await restartedProcess.coordinator.wake(WakeTrigger.startup);

      expect(drainedWalIds, ['pending-wal']);
      expect(restartedProcess.drainPasses, 0);
    });

    test('auto-sync opt-out still reconciles and reports pending, while retry uploads', () async {
      final harness = _TransferHarness(autoUploadEnabled: false);
      addTearDown(harness.dispose);

      await harness.coordinator.wake(WakeTrigger.startup);
      expect(harness.reconcilePasses, 1);
      expect(harness.discoveryPasses, 1);
      expect(harness.pendingRefreshes, 1);
      expect(harness.drainPasses, 0);

      await harness.coordinator.wake(WakeTrigger.userRetry);
      expect(harness.drainPasses, 1);
    });

    test('uploaded WALs resolve before the drain can offer bytes again', () async {
      final harness = _TransferHarness()..uploadedWalAwaitingReconcile = true;
      addTearDown(harness.dispose);

      await harness.coordinator.wake(WakeTrigger.connectivityRestored);

      expect(harness.reconciledUploadedWal, isTrue);
      expect(harness.reofferedUploadedWal, isFalse);
    });

    test('partial drain failure still reconciles uploaded WALs before retry', () async {
      final harness = _TransferHarness()
        ..drainFails = true
        ..drainNeedsReconciliation = true;
      addTearDown(harness.dispose);

      await harness.coordinator.wake(WakeTrigger.startup);

      // Initial reconcile + post-drain reconcile for uploaded WALs.
      expect(harness.reconcilePasses, 2);
      expect(harness.scheduledCooldowns, hasLength(1));
    });

    test('contended drain schedules retry instead of clearing as success', () async {
      final harness = _TransferHarness()..drainContended = true;
      addTearDown(harness.dispose);

      await harness.coordinator.wake(WakeTrigger.startup);

      expect(harness.drainPasses, 1);
      expect(harness.scheduledCooldowns, hasLength(1));
      expect(harness.coordinator.nextCooldownAt, DateTime.utc(2026, 1, 1, 0, 0, 5));
    });
  });
}

Future<void> _settle() => Future<void>.delayed(Duration.zero);

class _ScheduledCooldown {
  const _ScheduledCooldown(this.delay, this.callback);

  final Duration delay;
  final void Function() callback;
}

class _TransferHarness {
  _TransferHarness({
    bool autoUploadEnabled = true,
    List<String>? backlog,
    List<String>? drainedWalIds,
  })  : _autoUploadEnabled = autoUploadEnabled,
        backlog = backlog ?? <String>['wal-1'],
        drainedWalIds = drainedWalIds ?? <String>[] {
    coordinator = RecordingTransferCoordinator(
      reconcile: _reconcile,
      discover: _discover,
      refreshPending: _refreshPending,
      drain: _drain,
      autoUploadEnabled: () => _autoUploadEnabled,
      connectivityChanges: connectivity.stream,
      initiallyConnected: true,
      clock: () => DateTime.utc(2026, 1, 1),
      scheduleCooldown: (delay, callback) => scheduledCooldowns.add(_ScheduledCooldown(delay, callback)),
    );
  }

  final bool _autoUploadEnabled;
  final StreamController<bool> connectivity = StreamController<bool>.broadcast(sync: true);
  final List<String> backlog;
  final List<String> drainedWalIds;
  final List<_ScheduledCooldown> scheduledCooldowns = [];
  late final RecordingTransferCoordinator coordinator;

  Completer<void>? reconcileGate;
  bool drainFails = false;
  bool drainNeedsReconciliation = false;
  bool drainContended = false;
  bool uploadedWalAwaitingReconcile = false;
  bool reconciledUploadedWal = false;
  bool reofferedUploadedWal = false;
  String walState = 'miss';
  int reconcilePasses = 0;
  int discoveryPasses = 0;
  int pendingRefreshes = 0;
  int drainPasses = 0;
  int _concurrentDrains = 0;
  int maximumConcurrentDrains = 0;

  Future<void> _reconcile() async {
    reconcilePasses++;
    if (uploadedWalAwaitingReconcile) {
      uploadedWalAwaitingReconcile = false;
      reconciledUploadedWal = true;
    }
    final gate = reconcileGate;
    if (gate != null) await gate.future;
  }

  Future<void> _discover() async {
    discoveryPasses++;
  }

  Future<void> _refreshPending() async {
    pendingRefreshes++;
  }

  Future<RecordingTransferDrainResult> _drain() async {
    if (backlog.isEmpty) return const RecordingTransferDrainResult.skipped();
    drainPasses++;
    _concurrentDrains++;
    maximumConcurrentDrains = maximumConcurrentDrains < _concurrentDrains ? _concurrentDrains : maximumConcurrentDrains;
    try {
      if (drainContended) {
        return const RecordingTransferDrainResult.contended();
      }
      if (uploadedWalAwaitingReconcile) reofferedUploadedWal = true;
      if (drainFails) {
        // This mirrors LocalWalSyncImpl's normal-return failure: the WAL stays
        // retryable and is not surfaced as synced.
        walState = 'miss';
        return RecordingTransferDrainResult(
          attempted: true,
          failed: true,
          needsReconciliation: drainNeedsReconciliation,
        );
      }
      drainedWalIds.addAll(backlog);
      backlog.clear();
      walState = 'uploaded';
      return const RecordingTransferDrainResult(attempted: true, failed: false, needsReconciliation: false);
    } finally {
      _concurrentDrains--;
    }
  }

  Future<void> dispose() async {
    coordinator.dispose();
    await connectivity.close();
  }
}
