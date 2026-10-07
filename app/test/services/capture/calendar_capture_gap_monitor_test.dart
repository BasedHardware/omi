import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/calendar_capture_gap_monitor.dart';

void main() {
  final now = DateTime.utc(2026, 10, 7, 10);
  final meeting = CalendarCaptureWindow(
    'event-1',
    now.subtract(const Duration(minutes: 5)),
    now.add(const Duration(hours: 1)),
  );
  test('active accepted meeting without capture emits once per reason, with no title or id', () async {
    final events = <Map<String, Object?>>[];
    final monitor =
        CalendarCaptureGapMonitor(load: (start, end) async => [meeting], ownerKey: () => 'uid', emit: events.add);
    for (var i = 0; i < 4; i++) {
      await monitor.check(
        now.add(Duration(seconds: i * 15)),
        gapReason: () => 'not_capturing',
        phase: () => 'idle',
      );
    }
    expect(events, hasLength(1));
    expect(events.single, containsPair('reason', 'not_capturing'));
    expect(events.single.keys, isNot(contains('event_id')));
    expect(events.single.keys, isNot(contains('title')));
    await monitor.check(now.add(const Duration(minutes: 2)), gapReason: () => 'socket_down', phase: () => 'phoneLive');
    expect(events, hasLength(2));
  });
  test('healthy capture emits nothing; short server overlap does not erase active monitoring', () async {
    var loads = 0;
    final events = <Map<String, Object?>>[];
    final monitor = CalendarCaptureGapMonitor(
      load: (start, end) async => loads++ == 0 ? [meeting] : [],
      ownerKey: () => 'uid',
      emit: events.add,
    );
    await monitor.check(now, gapReason: () => null, phase: () => 'phoneLive');
    expect(events, isEmpty);
    await monitor.check(now.add(const Duration(minutes: 3)), gapReason: () => 'no_frames', phase: () => 'phoneLive');
    expect(events, hasLength(1));
    await monitor.check(now.add(const Duration(hours: 2)), gapReason: () => 'not_capturing', phase: () => 'idle');
    expect(events, hasLength(1));
  });
  test('missing calendar evidence never implies loss', () async {
    final events = <Map<String, Object?>>[];
    final monitor =
        CalendarCaptureGapMonitor(load: (start, end) async => null, ownerKey: () => 'uid', emit: events.add);
    await monitor.check(now, gapReason: () => 'not_capturing', phase: () => 'idle');
    expect(events, isEmpty);
  });
  test('health is sampled after fetch and retired accounts cannot publish', () async {
    var owner = 'a';
    var healthy = false;
    final pending = Completer<List<CalendarCaptureWindow>?>();
    final events = <Map<String, Object?>>[];
    final monitor =
        CalendarCaptureGapMonitor(load: (start, end) => pending.future, ownerKey: () => owner, emit: events.add);
    final pass = monitor.check(now, gapReason: () => healthy ? null : 'not_capturing', phase: () => 'idle');
    healthy = true;
    pending.complete([meeting]);
    await pass;
    expect(events, isEmpty);
    owner = 'b';
    monitor.dispose();
    await monitor.check(now, gapReason: () => 'not_capturing', phase: () => 'idle');
    expect(events, isEmpty);
  });
  test('account switch during a calendar read drops the previous account result', () async {
    var owner = 'a';
    final pending = Completer<List<CalendarCaptureWindow>?>();
    final events = <Map<String, Object?>>[];
    final monitor =
        CalendarCaptureGapMonitor(load: (start, end) => pending.future, ownerKey: () => owner, emit: events.add);
    final pass = monitor.check(now, gapReason: () => 'not_capturing', phase: () => 'idle');
    owner = 'b';
    pending.complete([meeting]);
    await pass;
    expect(events, isEmpty);
  });
}
