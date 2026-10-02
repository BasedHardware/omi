import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/analytics/mobile_performance_telemetry.dart';

void main() {
  test('render samples are bounded, aggregated, and discarded across identities', () {
    var epoch = 0;
    final events = <Map<String, dynamic>>[];
    final observer = MobilePerformanceTelemetry(emit: (_, p) => events.add(p), identityEpoch: () => epoch);
    for (var i = 0; i < 599; i++) {
      observer.observeFrame(16000);
    }
    observer.observeFrame(45000);
    expect(events, hasLength(1));
    expect(events.single['frame_count'], 600);
    expect(events.single['frames_over_32ms'], 1);
    observer.observeFrame(15000);
    epoch++;
    observer.flush();
    expect(events, hasLength(1));
    observer.setForeground(false);
    observer.observeFrame(15000);
    observer.flush();
    expect(events, hasLength(1));
  });
  testWidgets('dynamic routes are bounded and a superseded frame does not emit', (tester) async {
    final events = <Map<String, dynamic>>[];
    final observer = MobilePerformanceTelemetry(emit: (_, props) => events.add(props), identityEpoch: () => 1);
    observer.attach();
    final privateRoute = MaterialPageRoute<void>(
        settings: const RouteSettings(name: '/conversation/private-id?text=secret'), builder: (_) => const SizedBox());
    observer.didChangeTop(privateRoute, null);
    await tester.pumpWidget(const SizedBox());
    expect(events, hasLength(1));
    expect(events.single['surface'], 'unnamed_route');
    expect(events.single['stage'], 'first_frame');
    expect(events.toString(), isNot(contains('private-id')));
    observer.dispose();
  });

  testWidgets('disposal and identity change cancel pending first-frame observations', (tester) async {
    final events = <Map<String, dynamic>>[];
    var epoch = 1;
    final first = MobilePerformanceTelemetry(emit: (_, props) => events.add(props), identityEpoch: () => epoch);
    first.attach();
    epoch++;
    await tester.pumpWidget(const SizedBox());
    expect(events, isEmpty);
    first.dispose();
    final second = MobilePerformanceTelemetry(emit: (_, props) => events.add(props), identityEpoch: () => epoch);
    second.attach();
    second.dispose();
    await tester.pump();
    expect(events, isEmpty);
  });

  testWidgets('background suppresses first frame and telemetry failures stay fail-open', (tester) async {
    final events = <Map<String, dynamic>>[];
    final observer = MobilePerformanceTelemetry(emit: (_, props) => events.add(props), identityEpoch: () => 0);
    observer.attach();
    observer.setForeground(false);
    await tester.pumpWidget(const SizedBox());
    expect(events, isEmpty);
    observer.dispose();
    final broken = MobilePerformanceTelemetry(emit: (_, __) => throw StateError('synthetic'), identityEpoch: () => 0);
    expect(() {
      broken.observeFrame(10000);
      broken.flush();
      broken.dispose();
    }, returnsNormally);
  });
}
