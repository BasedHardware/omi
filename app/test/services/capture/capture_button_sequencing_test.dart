import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/capture/virtual_capture_time.dart';

class _ButtonPrefs implements SharedPreferencesUtil {
  @override
  bool get deviceMuted => false;
  @override
  int get singleTapAction => 2;
  @override
  int get doubleTapAction => 2;
  @override
  int get tripleTapAction => 2;
  @override
  dynamic noSuchMethod(Invocation i) => null;
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
}) {
  return CaptureProvider(
    scheduling: scheduler,
    now: now,
    connectivity: CaptureConnectivityBoundary(
      initiallyConnected: true,
      changes: const Stream.empty(),
      isConnected: () => true,
    ),
    preferences: _ButtonPrefs(),
    bleListeners: _NoopBle(),
  );
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    try {
      await ServiceManager.init();
    } catch (_) {}
  });

  test('double-tap (state 2) arms debounce timer, cancelled by triple-tap (state 6)', () async {
    final clock = VirtualClock(DateTime.utc(2026));
    final scheduler = ManualScheduler(clock: clock);
    final provider = _provider(scheduler: scheduler, now: clock.now);
    addTearDown(provider.dispose);

    expect(provider.hasPendingDoubleTapForTesting, isFalse);

    // Emit state 2 (double tap)
    provider.handleButtonEventForTesting('test-device', 2);
    expect(provider.hasPendingDoubleTapForTesting, isTrue);

    // Emit state 6 (triple tap) within multi-tap window
    provider.handleButtonEventForTesting('test-device', 6);
    expect(provider.hasPendingDoubleTapForTesting, isFalse);
  });

  test('boundary: state 6 arriving after 350ms but inside 600ms window still suppresses double-tap', () async {
    final clock = VirtualClock(DateTime.utc(2026));
    final scheduler = ManualScheduler(clock: clock);
    final provider = _provider(scheduler: scheduler, now: clock.now);
    addTearDown(provider.dispose);

    expect(provider.hasPendingDoubleTapForTesting, isFalse);

    // Emit state 2 (double tap)
    provider.handleButtonEventForTesting('test-device', 2);
    expect(provider.hasPendingDoubleTapForTesting, isTrue);

    // Advance 450ms: past the previous 350ms threshold, but within the 600ms firmware window
    scheduler.elapse(const Duration(milliseconds: 450));
    expect(provider.hasPendingDoubleTapForTesting, isTrue);

    // Emit state 6 (triple tap) at 450ms — suppresses the pending double-tap
    provider.handleButtonEventForTesting('test-device', 6);
    expect(provider.hasPendingDoubleTapForTesting, isFalse);

    // Advance beyond the remaining window duration; verify double-tap never executes
    scheduler.elapse(const Duration(milliseconds: 300));
    expect(provider.hasPendingDoubleTapForTesting, isFalse);
  });

  test('standalone double press executes action exactly once after 600ms boundary', () async {
    final clock = VirtualClock(DateTime.utc(2026));
    final scheduler = ManualScheduler(clock: clock);
    final provider = _provider(scheduler: scheduler, now: clock.now);
    addTearDown(provider.dispose);

    expect(provider.hasPendingDoubleTapForTesting, isFalse);
    expect(provider.isConversationMarkedForStarring, isFalse);

    // Emit state 2 (double tap)
    provider.handleButtonEventForTesting('test-device', 2);
    expect(provider.hasPendingDoubleTapForTesting, isTrue);

    // Boundary: at 599ms the timer is still armed and action has not fired
    scheduler.elapse(const Duration(milliseconds: 599));
    expect(provider.hasPendingDoubleTapForTesting, isTrue);
    expect(provider.isConversationMarkedForStarring, isFalse);

    // At 600ms the firmware DOUBLE_TAP_WINDOW boundary is reached and action executes
    scheduler.elapse(const Duration(milliseconds: 1));
    expect(provider.hasPendingDoubleTapForTesting, isFalse);
    expect(provider.isConversationMarkedForStarring, isTrue);

    // Later time advances produce no redundant executions
    scheduler.elapse(const Duration(milliseconds: 500));
    expect(provider.hasPendingDoubleTapForTesting, isFalse);
    expect(provider.isConversationMarkedForStarring, isTrue);
  });

  test('late event arriving after 600ms classification window executes independently', () async {
    final clock = VirtualClock(DateTime.utc(2026));
    final scheduler = ManualScheduler(clock: clock);
    final provider = _provider(scheduler: scheduler, now: clock.now);
    addTearDown(provider.dispose);

    // Emit state 2 and let it execute at 600ms
    provider.handleButtonEventForTesting('test-device', 2);
    scheduler.elapse(const Duration(milliseconds: 600));
    expect(provider.hasPendingDoubleTapForTesting, isFalse);
    expect(provider.isConversationMarkedForStarring, isTrue);

    // Reset starring to observe late event effect
    provider.unmarkConversationForStarring();
    expect(provider.isConversationMarkedForStarring, isFalse);

    // Late state 6 arriving at 750ms executes triple-tap independently
    scheduler.elapse(const Duration(milliseconds: 150));
    provider.handleButtonEventForTesting('test-device', 6);
    expect(provider.hasPendingDoubleTapForTesting, isFalse);
    expect(provider.isConversationMarkedForStarring, isTrue);
  });

  test('double-tap debounce timer is cancelled on single tap or dispose', () async {
    final clock = VirtualClock(DateTime.utc(2026));
    final scheduler = ManualScheduler(clock: clock);
    final provider = _provider(scheduler: scheduler, now: clock.now);

    // State 2 followed by state 1 cancels double-tap
    provider.handleButtonEventForTesting('test-device', 2);
    expect(provider.hasPendingDoubleTapForTesting, isTrue);
    provider.handleButtonEventForTesting('test-device', 1);
    expect(provider.hasPendingDoubleTapForTesting, isFalse);

    // State 2 followed by dispose cancels double-tap and prevents delayed execution
    provider.handleButtonEventForTesting('test-device', 2);
    expect(provider.hasPendingDoubleTapForTesting, isTrue);
    provider.dispose();
    expect(provider.hasPendingDoubleTapForTesting, isFalse);

    // Virtual time advance after dispose does not execute action
    scheduler.elapse(const Duration(milliseconds: 600));
    expect(provider.hasPendingDoubleTapForTesting, isFalse);
  });
}
