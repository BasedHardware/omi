import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';

import '../../support/capture/virtual_capture_time.dart';

class _MutePrefs implements SharedPreferencesUtil {
  @override
  bool get deviceMuted => true;
  @override
  dynamic noSuchMethod(Invocation i) => throw StateError('Unexpected preferences read: ${i.memberName}');
}

class _NoopBle implements CaptureBleListeners {
  @override
  void addBatchRecordingFinalizedListener(void Function(String) callback) {}
  @override
  void removeBatchRecordingFinalizedListener(void Function(String) callback) {}
}

CaptureProvider _provider({
  required ManualScheduler scheduler,
  required DateTime Function() now,
  Stream<bool>? connectivityChanges,
  bool Function()? isConnected,
}) {
  return CaptureProvider(
    scheduling: scheduler,
    now: now,
    connectivity: CaptureConnectivityBoundary(
      initiallyConnected: true,
      changes: connectivityChanges ?? const Stream.empty(),
      isConnected: isConnected ?? () => true,
    ),
    preferences: _MutePrefs(),
    bleListeners: _NoopBle(),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('dispose cancels voice-command timeout that dispose used to leak', () async {
    final clock = VirtualClock(DateTime.utc(2026));
    final scheduler = ManualScheduler(clock: clock);
    final provider = _provider(scheduler: scheduler, now: clock.now);
    provider.debugArmVoiceCommandTimeout('synthetic-device');
    expect(scheduler.pendingTimers, isNotEmpty);
    provider.dispose();
    // dispose() kicks off lifetime.close() without awaiting it; joining the
    // same idempotent close future lets the drain run the timer-cancel
    // release before we assert the timer is gone.
    await provider.lifetime.close();
    expect(scheduler.pendingTimers, isEmpty);
    scheduler.elapse(const Duration(seconds: 15));
    expect(scheduler.pendingTimers, isEmpty);
  });

  test('dispose then a late voice-command timeout never fires', () {
    final clock = VirtualClock(DateTime.utc(2026));
    final scheduler = ManualScheduler(clock: clock);
    final provider = _provider(scheduler: scheduler, now: clock.now);
    provider.dispose();
    provider.debugArmVoiceCommandTimeout('synthetic-device');
    scheduler.elapse(const Duration(seconds: 15));
    expect(scheduler.pendingTimers, isEmpty);
  });

  test('dispose drops connectivity listener so a later event does not run', () {
    final clock = VirtualClock(DateTime.utc(2026));
    final scheduler = ManualScheduler(clock: clock);
    final changes = StreamController<bool>.broadcast(sync: true);
    final provider = _provider(
      scheduler: scheduler,
      now: clock.now,
      connectivityChanges: changes.stream,
    );
    expect(provider.isConnected, isTrue);
    provider.dispose();
    changes.add(false);
    expect(provider.isConnected, isTrue);
    changes.close();
  });
}
