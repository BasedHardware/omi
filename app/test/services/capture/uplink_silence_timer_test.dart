import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/uplink_silence_timer.dart';

import '../../support/capture/virtual_capture_time.dart';

void main() {
  test('timeout settings preserve the server minimum and four-hour sentinel', () {
    expect(UplinkSilenceTimer.fromPreference(120), const Duration(minutes: 2));
    expect(UplinkSilenceTimer.fromPreference(300), const Duration(minutes: 5));
    expect(UplinkSilenceTimer.fromPreference(-1), const Duration(hours: 4));
    expect(UplinkSilenceTimer.fromPreference(0), const Duration(minutes: 2));
  });

  test('speech replaces the deadline and cancellation releases its timer', () {
    final clock = VirtualClock(DateTime.utc(2026));
    final scheduler = ManualScheduler(clock: clock);
    var pauses = 0;
    final timer = UplinkSilenceTimer(
        scheduling: scheduler, now: clock.now, timeout: () => const Duration(seconds: 120), onTimeout: () => pauses++);
    timer.speechOrStart();
    scheduler.elapse(const Duration(seconds: 119));
    timer.speechOrStart();
    scheduler.elapse(const Duration(seconds: 119));
    expect(pauses, 0);
    expect(timer.expired, false);
    scheduler.elapse(const Duration(seconds: 1));
    expect(pauses, 1);
    expect(timer.expired, true);
    timer.speechOrStart();
    timer.cancel();
    expect(scheduler.pendingTimers, isEmpty);
    expect(timer.expired, false);
  });
}
