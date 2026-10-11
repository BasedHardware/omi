import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/capture/calendar_capture_gap_monitor.dart';
import 'package:omi/services/integrations/google_calendar_service.dart';

import '../../support/capture/capture_replay_world.dart';

void main() {
  final now = DateTime.utc(2026, 10, 7, 10);
  final meeting = CalendarCaptureWindow('event-1', now, now.add(const Duration(hours: 2)));
  late ValueNotifier<CalendarMeetingSnapshot> known;
  setUp(() => known = ValueNotifier(CalendarMeetingSnapshot(owner: 'uid', windows: [meeting])));
  tearDown(() => known.dispose());

  Future<void> check(CalendarCaptureGapMonitor monitor, DateTime at, {bool owns = false}) => monitor.check(at,
      captureOwns: () => owns,
      gapReason: () => owns ? null : 'not_capturing',
      phase: () => owns ? 'phoneLive' : 'idle');
  CalendarCaptureGapMonitor monitor(
          {required Future<List<CalendarCaptureWindow>?> Function(DateTime, DateTime) load,
          void Function(Map<String, Object?>)? emit,
          String Function()? owner}) =>
      CalendarCaptureGapMonitor(localMeetings: known, load: load, ownerKey: owner ?? () => 'uid', emit: emit ?? (_) {});

  test('no upcoming meeting means no fetches or scheduled checks across a day', () async {
    known.value = const CalendarMeetingSnapshot(owner: 'uid', windows: []);
    var fetches = 0;
    final gap = monitor(load: (_, __) async {
      fetches++;
      return [];
    });
    for (var second = 0; second < 86400; second += 15) {
      final at = now.add(Duration(seconds: second));
      expect(gap.nextCheckAt(at, captureOwns: false), isNull);
      await check(gap, at);
    }
    expect(fetches, 0);
  });
  test('active meeting and live capture never fetch or schedule a calendar check', () async {
    var fetches = 0;
    final gap = monitor(load: (_, __) async {
      fetches++;
      return [meeting];
    });
    for (var second = 0; second < 4200; second += 15) {
      final at = now.add(Duration(seconds: second));
      expect(gap.nextCheckAt(at, captureOwns: true), isNull);
      await check(gap, at, owns: true);
    }
    expect(fetches, 0);
  });
  test('known upcoming meeting first fetches at start, then backs off to ten minutes', () async {
    final times = <DateTime>[];
    var at = now.subtract(const Duration(minutes: 5));
    final events = <Map<String, Object?>>[];
    final gap = monitor(
        load: (start, end) async {
          expect(start, meeting.start);
          expect(end, meeting.end);
          times.add(at);
          return [meeting];
        },
        emit: events.add);
    expect(gap.nextCheckAt(at, captureOwns: false), now);
    await check(gap, at);
    expect(times, isEmpty);
    const dueSeconds = [0, 60, 180, 420, 900, 1500, 2100];
    for (final second in dueSeconds) {
      at = now.add(Duration(seconds: second));
      if (second != 0) {
        await check(gap, at.subtract(const Duration(seconds: 1)));
        expect(times.length, dueSeconds.indexOf(second));
      }
      await check(gap, at);
    }
    expect(times, dueSeconds.map((s) => now.add(Duration(seconds: s))).toList());
    expect(events, hasLength(1));
    expect(events.single.keys, isNot(contains('event_id')));
    expect(events.single.keys, isNot(contains('title')));
    expect(gap.nextCheckAt(meeting.end, captureOwns: false), isNull);
  });
  test('failed calendar reads retain exponential backoff without implying loss', () async {
    var fetches = 0;
    final events = <Map<String, Object?>>[];
    final gap = monitor(
        load: (_, __) async {
          fetches++;
          throw StateError('unavailable');
        },
        emit: events.add);
    await check(gap, now);
    await check(gap, now.add(const Duration(seconds: 59)));
    expect(fetches, 1);
    await check(gap, now.add(const Duration(seconds: 60)));
    expect(fetches, 2);
    expect(gap.nextCheckAt(now.add(const Duration(seconds: 61)), captureOwns: false),
        now.add(const Duration(seconds: 180)));
    expect(events, isEmpty);
  });
  test('owning capture after fetch and retired accounts cannot publish', () async {
    var owns = false;
    final pending = Completer<List<CalendarCaptureWindow>?>();
    final events = <Map<String, Object?>>[];
    final gap = monitor(load: (_, __) => pending.future, emit: events.add);
    final pass = gap.check(now.add(const Duration(minutes: 1)),
        captureOwns: () => owns, gapReason: () => 'not_capturing', phase: () => 'idle');
    owns = true;
    pending.complete([meeting]);
    await pass;
    expect(events, isEmpty);
    gap.dispose();
    await check(gap, now.add(const Duration(minutes: 5)));
    expect(events, isEmpty);
  });
  test('account switch during a read drops old evidence and old local windows', () async {
    var owner = 'uid';
    final pending = Completer<List<CalendarCaptureWindow>?>();
    final events = <Map<String, Object?>>[];
    final gap = monitor(load: (_, __) => pending.future, owner: () => owner, emit: events.add);
    final pass = check(gap, now.add(const Duration(minutes: 1)));
    owner = 'successor';
    pending.complete([meeting]);
    await pass;
    expect(events, isEmpty);
    expect(gap.nextCheckAt(now, captureOwns: false), isNull);
  });
  test('local meeting changes during a pending fetch cannot schedule a zero-delay retry loop', () async {
    final pending = Completer<List<CalendarCaptureWindow>?>();
    var owner = 'uid';
    final events = <Map<String, Object?>>[];
    final gap = monitor(load: (_, __) => pending.future, owner: () => owner, emit: events.add);
    final pass = check(gap, now.add(const Duration(minutes: 1)));
    owner = 'new-account';
    known.value = CalendarMeetingSnapshot(owner: owner, windows: [meeting]);
    expect(gap.nextCheckAt(now.add(const Duration(minutes: 1)), captureOwns: false), isNull);
    pending.complete([meeting]);
    await pass;
    expect(events, isEmpty);
    expect(
        gap.nextCheckAt(now.add(const Duration(minutes: 1)), captureOwns: false), now.add(const Duration(minutes: 1)));
  });

  test('local cache is bounded, title-free and account scoped', () {
    GoogleCalendarService.rememberMeetings(
        'uid', [meeting, CalendarCaptureWindow('ended', now.subtract(const Duration(hours: 2)), now)],
        now: now);
    expect(GoogleCalendarService.knownMeetings.value.windows, [meeting]);
    GoogleCalendarService.rememberMeetings('other', [], now: now);
    expect(GoogleCalendarService.knownMeetings.value.owner, 'other');
    expect(GoogleCalendarService.knownMeetings.value.windows, isEmpty);
    GoogleCalendarService.rememberMeetings(
        'other', List.generate(100, (i) => CalendarCaptureWindow('$i', now, meeting.end)),
        now: now);
    expect(GoogleCalendarService.knownMeetings.value.windows, hasLength(64));
    GoogleCalendarService.knownMeetings.value = const CalendarMeetingSnapshot(owner: '', windows: []);
  });
  test('real idle controller has no polling timer; local meeting schedules, live capture cancels it', () async {
    final dir = await Directory.systemTemp.createTemp('meeting_gap_gate_');
    addTearDown(() => dir.delete(recursive: true));
    known.value = const CalendarMeetingSnapshot(owner: 'uid', windows: []);
    var fetches = 0;
    final gap = monitor(load: (_, __) async {
      fetches++;
      return [meeting];
    });
    final world = await CaptureReplayWorld.boot(tempDir: dir, startTime: now, calendarGapMonitor: gap);
    addTearDown(world.dispose);
    expect(world.scheduler.pendingTimerLabels.where((l) => l == 'periodic(0:00:15.000000)'), isEmpty);
    await world.elapse(const Duration(minutes: 10));
    expect(fetches, 0);
    known.value = CalendarMeetingSnapshot(owner: 'uid', windows: [meeting]);
    await world.elapse(Duration.zero);
    expect(fetches, 1);
    await world.startLiveCapture();
    world.emitNativeState(PhoneMicCaptureState.running);
    for (var second = 0; second < 60; second++) {
      world.injectAudioFrames(100, sessionId: world.hostApi.lastStartSessionId!);
      await world.elapse(const Duration(seconds: 1));
    }
    expect(fetches, 1);
    await world.controller.pauseCapture();
    await world.elapse(const Duration(minutes: 2));
    expect(fetches, 1, reason: 'a deliberately paused session still owns capture');
    world.disposeController();
    await world.settle();
  });
}
