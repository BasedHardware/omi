import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/analytics/app_foreground_time.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

// App Foreground Ended: how long the app was in front, and how much of that with capture active.
// "In front" is the lifecycle state `resumed` only; a launch in the background is not in front.

void main() {
  late List<RegisteredEvent> events;
  late AppForegroundTime time;
  var clock = DateTime.utc(2026, 11, 26, 9);
  var capturing = false;

  void wait(int seconds) => clock = clock.add(Duration(seconds: seconds));
  void capture(bool active) {
    capturing = active;
    time.onCaptureChanged();
  }

  Map<String, Object> only() => events.single.properties;

  setUp(() {
    events = [];
    clock = DateTime.utc(2026, 11, 26, 9);
    capturing = false;
    time = AppForegroundTime(capturing: () => capturing, now: () => clock, emit: events.add);
  });

  test('a stretch in front is reported once, when the app goes to the background', () {
    time.start(AppLifecycleState.resumed);
    wait(90);
    time.onLifecycle(AppLifecycleState.inactive);
    expect(events, isEmpty); // Not yet: inactive is not the background.
    time.onLifecycle(AppLifecycleState.hidden);
    time.onLifecycle(AppLifecycleState.paused); // The same departure reports once.
    expect(events.single.wireName, 'App Foreground Ended');
    expect(only(), {'foreground_seconds': 90, 'capturing_seconds': 0});
  });

  test('a launch in the background is not in front, however long it lasts', () {
    time.start(null);
    wait(3600);
    expect(time.inFront, isFalse);
    time.onLifecycle(AppLifecycleState.paused);
    expect(events, isEmpty);
    // The user opens the app an hour later: only that counts.
    time.onLifecycle(AppLifecycleState.resumed);
    wait(20);
    time.onLifecycle(AppLifecycleState.paused);
    expect(only(), {'foreground_seconds': 20, 'capturing_seconds': 0});
  });

  test('time under the notification shade or a system dialog is not counted and does not end the stretch', () {
    time.start(AppLifecycleState.resumed);
    wait(30);
    time.onLifecycle(AppLifecycleState.inactive);
    wait(45); // Reading a notification.
    time.onLifecycle(AppLifecycleState.resumed);
    wait(15);
    time.onLifecycle(AppLifecycleState.paused);
    expect(only(), {'foreground_seconds': 45, 'capturing_seconds': 0});
  });

  test('capture active for part of the stretch is counted for that part only', () {
    time.start(AppLifecycleState.resumed);
    wait(10);
    capture(true); // The pendant connects.
    wait(40);
    capture(false); // Paused.
    wait(5);
    capture(true);
    wait(20);
    time.onLifecycle(AppLifecycleState.paused);
    expect(only(), {'foreground_seconds': 75, 'capturing_seconds': 60});
  });

  test('capture that is already active when the app comes to the front counts from that moment', () {
    capturing = true;
    time.start(null);
    wait(600); // Capturing in the background: not in front.
    time.onCaptureChanged();
    time.onLifecycle(AppLifecycleState.resumed);
    wait(30);
    time.onLifecycle(AppLifecycleState.inactive);
    wait(100);
    time.onLifecycle(AppLifecycleState.paused);
    expect(only(), {'foreground_seconds': 30, 'capturing_seconds': 30});
  });

  test('each visit is its own row, and nothing carries over', () {
    time.start(AppLifecycleState.resumed);
    wait(12);
    time.onLifecycle(AppLifecycleState.paused);
    wait(5000);
    time.onLifecycle(AppLifecycleState.resumed);
    wait(7);
    time.onLifecycle(AppLifecycleState.paused);
    expect([for (final event in events) event.properties['foreground_seconds']], [12, 7]);
  });

  test('a glance shorter than a second, and a repeated resumed, report nothing extra', () {
    time.start(AppLifecycleState.resumed);
    time.onLifecycle(AppLifecycleState.resumed);
    clock = clock.add(const Duration(milliseconds: 400));
    time.onLifecycle(AppLifecycleState.paused);
    expect(events, isEmpty);
  });

  test('a clock that jumps cannot produce a negative or an absurd time', () {
    time.start(AppLifecycleState.resumed);
    capture(true);
    clock = clock.subtract(const Duration(hours: 1)); // Set backwards while in front.
    time.onLifecycle(AppLifecycleState.paused);
    expect(events, isEmpty);
    time.onLifecycle(AppLifecycleState.resumed);
    clock = clock.add(const Duration(days: 3)); // Set far forwards.
    time.onLifecycle(AppLifecycleState.paused);
    expect(only(), {'foreground_seconds': 12 * 3600, 'capturing_seconds': 12 * 3600});
  });

  test('the app closing from the front still reports the stretch', () {
    time.start(AppLifecycleState.resumed);
    wait(33);
    time.onLifecycle(AppLifecycleState.detached);
    expect(only(), {'foreground_seconds': 33, 'capturing_seconds': 0});
  });
}
