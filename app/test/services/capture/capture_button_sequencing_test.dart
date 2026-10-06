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
  bool get omiButtonActionsDisabled => false;
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

  test('double-tap debounce timer is cancelled on single tap or dispose', () async {
    final clock = VirtualClock(DateTime.utc(2026));
    final scheduler = ManualScheduler(clock: clock);
    final provider = _provider(scheduler: scheduler, now: clock.now);

    // State 2 followed by state 1 cancels double-tap
    provider.handleButtonEventForTesting('test-device', 2);
    expect(provider.hasPendingDoubleTapForTesting, isTrue);
    provider.handleButtonEventForTesting('test-device', 1);
    expect(provider.hasPendingDoubleTapForTesting, isFalse);

    // State 2 followed by dispose cancels double-tap
    provider.handleButtonEventForTesting('test-device', 2);
    expect(provider.hasPendingDoubleTapForTesting, isTrue);
    provider.dispose();
    expect(provider.hasPendingDoubleTapForTesting, isFalse);
  });
}
