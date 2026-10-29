import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/pages/conversations/widgets/capture_continuity_dogfood_banner.dart';
import 'package:omi/services/capture/capture_continuity_monitor.dart';

void main() {
  late DateTime now;
  late List<(String, Map<String, Object>)> events;
  late bool dogfood;
  late CaptureContinuityMonitor monitor;

  CaptureContinuityProbe probe({
    String? deviceId = 'pendant',
    bool expected = true,
    bool capturing = false,
  }) =>
      CaptureContinuityProbe(
        deviceId: deviceId,
        source: 'omi',
        captureExpected: expected,
        capturing: capturing,
        phase: 'idle',
        syncFenced: false,
      );

  /// Observes [probe] every check interval for [duration].
  void observeFor(Duration duration, CaptureContinuityProbe Function() probe) {
    final end = now.add(duration);
    while (now.isBefore(end)) {
      monitor.observe(probe());
      now = now.add(CaptureContinuityMonitor.checkInterval);
    }
    monitor.observe(probe());
  }

  List<String> triggersOf(String event) =>
      events.where((e) => e.$1 == event).map((e) => e.$2['trigger'] as String).toList();

  setUp(() {
    now = DateTime.utc(2026, 10, 20, 9, 32);
    events = [];
    dogfood = true;
    monitor = CaptureContinuityMonitor(
      now: () => now,
      track: (event, properties) => events.add((event, properties)),
      dogfood: () => dogfood,
      appBuild: () => '1420',
      platform: () => 'ios',
    );
  });

  test('a connected pendant with no capture and no custody declares once after the threshold', () {
    observeFor(const Duration(seconds: 45), probe);
    expect(events, isEmpty);
    observeFor(const Duration(minutes: 10), probe);
    expect(triggersOf('Capture Wedge Detected'), [CaptureContinuityMonitor.trigger]);
    final properties = events.single.$2;
    expect(properties['seconds_without_custody'], greaterThanOrEqualTo(60));
    expect(properties['app_build'], '1420');
    expect(monitor.dogfoodAlert.value?.deviceId, 'pendant');
  });

  test('frames reaching custody (orphan audio persisted to the WAL) keep it quiet', () {
    for (var i = 0; i < 40; i++) {
      monitor.onFrameInCustody();
      monitor.observe(probe());
      now = now.add(CaptureContinuityMonitor.checkInterval);
    }
    expect(events, isEmpty);
    // Custody stops: the clock runs from the last frame.
    observeFor(const Duration(seconds: 30), probe);
    expect(events, isEmpty);
    observeFor(const Duration(seconds: 30), probe);
    expect(triggersOf('Capture Wedge Detected'), [CaptureContinuityMonitor.trigger]);
  });

  test('capture coming back resolves the episode and clears the banner', () {
    observeFor(const Duration(minutes: 2), probe);
    expect(monitor.dogfoodAlert.value, isNotNull);
    monitor.observe(probe(capturing: true));
    expect(triggersOf('Capture Recovery Resolved'), [CaptureContinuityMonitor.trigger]);
    expect(monitor.dogfoodAlert.value, isNull);
    // A new episode declares again.
    observeFor(const Duration(minutes: 2), probe);
    expect(triggersOf('Capture Wedge Detected'), hasLength(2));
  });

  test('no pendant, capture not expected (muted, Transcribe Later, a call) or capturing never declares', () {
    observeFor(const Duration(minutes: 5), () => probe(deviceId: null));
    observeFor(const Duration(minutes: 5), () => probe(expected: false));
    observeFor(const Duration(minutes: 5), () => probe(capturing: true));
    expect(events, isEmpty);
  });

  test('store builds emit the event but never raise the dogfood banner', () {
    dogfood = false;
    observeFor(const Duration(minutes: 2), probe);
    expect(triggersOf('Capture Wedge Detected'), [CaptureContinuityMonitor.trigger]);
    expect(monitor.dogfoodAlert.value, isNull);
  });

  testWidgets('the dogfood banner renders only while an alert is open', (tester) async {
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: CaptureContinuityDogfoodBanner(monitor: monitor))));
    expect(find.textContaining('Dogfood'), findsNothing);
    monitor.dogfoodAlert.value = CaptureContinuityAlert(deviceId: 'pendant', since: DateTime.now());
    await tester.pump();
    expect(find.textContaining('pendant audio is not being recorded'), findsOneWidget);
    monitor.dogfoodAlert.value = null;
    await tester.pump();
    expect(find.textContaining('Dogfood'), findsNothing);
  });
}
