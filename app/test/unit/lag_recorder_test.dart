import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/analytics/lag_recorder.dart';
import 'package:omi/utils/analytics/mobile_performance_telemetry.dart';

void main() {
  late List<(String, Map<String, Object?>)> events;
  late int now;
  late LagRecorder lag;

  setUp(() {
    events = [];
    now = 1000000;
    lag = LagRecorder(emit: (type, fields) => events.add((type, fields)), nowUs: () => now)..active = true;
  });

  Iterable<Map<String, Object?>> of(String type) => events.where((e) => e.$1 == type).map((e) => e.$2);

  test('fast frames only count; a severe frame is logged with its bound and context', () {
    lag.setSurface('ConversationDetailPage');
    for (var i = 0; i < 100; i++) {
      lag.observeFrame(buildUs: 6000, rasterUs: 5000, totalUs: 12000);
    }
    expect(events, isEmpty);
    lag.onPointerDown(1, Offset.zero);
    lag.onPointerMove(1, const Offset(0, 40));
    lag.observeFrame(buildUs: 9000, rasterUs: 48000, totalUs: 60000);
    final frame = of('mobile_lag_frame').single;
    expect(frame['event'], 'mobile_lag_frame');
    expect(frame['surface'], 'ConversationDetailPage');
    expect(frame['bound'], 'raster');
    expect(frame['interaction'], 'scroll');
    expect(frame['raster_ms'], 48.0);
    lag.writeReport('background');
    final report = of('mobile_lag_report').single;
    final surface = (report['surfaces'] as List).single as Map;
    expect(surface['frames'], 101);
    expect(surface['slow_frames'], 1);
    expect(surface['raster_bound'], 1);
    expect(surface['slow_while_scrolling'], 1);
    expect((report['worst_frames'] as List).single, isNot(contains('_score')));
  });

  test('frames are attributed to the surface on top when they started', () {
    lag.setSurface('home_tab:conversations');
    now = 2000000;
    lag.setSurface('ChatPage');
    lag.observeFrame(buildUs: 40000, rasterUs: 1000, totalUs: 42000, vsyncStartUs: 1500000);
    lag.observeFrame(buildUs: 40000, rasterUs: 1000, totalUs: 42000, vsyncStartUs: 2100000);
    expect(of('mobile_lag_frame').map((f) => f['surface']), ['home_tab:conversations', 'ChatPage']);
  });

  test('individual frame logs are rate limited but every frame is counted', () {
    for (var i = 0; i < 30; i++) {
      lag.observeFrame(buildUs: 50000, rasterUs: 1000, totalUs: 52000);
    }
    expect(of('mobile_lag_frame'), hasLength(LagRecorder.frameLogsPerMinute));
    lag.writeReport('background');
    final report = of('mobile_lag_report').single;
    expect(((report['surfaces'] as List).single as Map)['severe_frames'], 30);
    expect((report['worst_frames'] as List).length, lessThanOrEqualTo(12));
  });

  test('stalls and taps under their thresholds stay silent', () {
    lag.recordStall(40000);
    lag.recordTap('home_tab:tasks', 30000);
    lag.recordTap('home_tab:tasks', 3000000); // waited for an unrelated frame
    expect(events, isEmpty);
    lag.recordStall(420000);
    lag.recordTap('home_tab:tasks', 180000);
    expect(of('mobile_lag_stall').single['blocked_ms'], 420.0);
    expect(of('mobile_lag_tap').single['tap_to_frame_ms'], 180.0);
  });

  test('a drag is a scroll through its fling tail, never a tap', () {
    lag.onPointerDown(1, Offset.zero);
    lag.onPointerMove(1, const Offset(0, 40));
    lag.onPointerUp(1);
    now += LagRecorder.flingTailUs - 1000;
    lag.observeFrame(buildUs: 50000, rasterUs: 0, totalUs: 50000);
    now += 2000;
    lag.observeFrame(buildUs: 50000, rasterUs: 0, totalUs: 50000);
    expect(of('mobile_lag_frame').map((f) => f['interaction']), ['scroll', 'idle']);
    expect(of('mobile_lag_tap'), isEmpty);
  });

  test('a second finger does not disturb the first pointer', () {
    lag.onPointerDown(1, Offset.zero);
    lag.onPointerDown(2, const Offset(100, 100));
    lag.onPointerMove(2, const Offset(100, 200));
    lag.onPointerUp(2);
    lag.observeFrame(buildUs: 50000, rasterUs: 0, totalUs: 50000);
    expect(of('mobile_lag_frame').single['interaction'], 'idle');
  });

  test('input is ignored while capture is off, and turning it off forgets a live scroll', () {
    lag.onPointerDown(1, Offset.zero);
    lag.onPointerMove(1, const Offset(0, 40));
    lag.active = false;
    lag.onPointerDown(2, Offset.zero);
    lag.onPointerMove(2, const Offset(0, 40));
    lag.active = true;
    lag.observeFrame(buildUs: 50000, rasterUs: 0, totalUs: 50000);
    expect(of('mobile_lag_frame').single['interaction'], 'idle');
  });

  test('page labels never include route arguments', () {
    final labelled = MaterialPageRoute<void>(builder: (_) => const SizedBox());
    lagRouteLabels[labelled] = 'ConversationDetailPage';
    expect(lagSurfaceFor(labelled, homeTab: 0), 'ConversationDetailPage');
    final dynamicName = MaterialPageRoute<void>(
        settings: const RouteSettings(name: '/conversation/abc?text=secret'), builder: (_) => const SizedBox());
    expect(lagSurfaceFor(dynamicName, homeTab: 0), 'page');
  });

  testWidgets('the recorder runs only while debug logs are on, and reports on background', (tester) async {
    var diagnostics = false;
    final observer = MobilePerformanceTelemetry(
      emit: (_, __) {},
      identityEpoch: () => 0,
      diagnosticsEnabled: () => diagnostics,
      lag: lag,
    );
    lag.active = false;
    observer.attach();
    expect(lag.watchdogRunning, isFalse);
    expect(lag.active, isFalse);
    diagnostics = true;
    observer.setForeground(true);
    expect(lag.watchdogRunning, isTrue);
    expect(lag.active, isTrue);
    lag.observeFrame(buildUs: 50000, rasterUs: 0, totalUs: 50000);
    observer.setForeground(false);
    expect(lag.watchdogRunning, isFalse);
    expect(of('mobile_lag_report'), hasLength(1));
    observer.dispose();
  });

  testWidgets('the stall watchdog stops on inactive and hidden, not only paused', (tester) async {
    final observer = MobilePerformanceTelemetry(
      emit: (_, __) {},
      identityEpoch: () => 0,
      diagnosticsEnabled: () => true,
      lag: lag,
    );
    lag.active = false;
    observer.attach();
    observer.onLifecycleState(AppLifecycleState.resumed);
    expect(lag.watchdogRunning, isTrue);
    // iOS delivers inactive → hidden → paused, and Dart timers are throttled
    // before `paused`: every non-resumed state must already stop the watchdog
    // or the throttled background gap is recorded as UI stalls.
    for (final state in [
      AppLifecycleState.inactive,
      AppLifecycleState.hidden,
      AppLifecycleState.paused,
    ]) {
      observer.onLifecycleState(state);
      expect(lag.watchdogRunning, isFalse, reason: '$state must suspend the stall watchdog');
      expect(lag.active, isFalse, reason: '$state must stop lag capture');
    }
    observer.onLifecycleState(AppLifecycleState.resumed);
    expect(lag.watchdogRunning, isTrue);
    expect(lag.active, isTrue);
    observer.dispose();
  });

  testWidgets('real drags reach the recorder through the global pointer route, with no widget mounted', (tester) async {
    final observer = MobilePerformanceTelemetry(
      emit: (_, __) {},
      identityEpoch: () => 0,
      diagnosticsEnabled: () => true,
      lag: lag,
    );
    observer.attach();
    addTearDown(observer.dispose);
    await tester.pumpWidget(MaterialApp(
      home: ListView.builder(itemCount: 100, itemBuilder: (_, i) => SizedBox(height: 60, child: Text('row $i'))),
    ));
    final gesture = await tester.startGesture(const Offset(200, 400));
    await gesture.moveBy(const Offset(0, -120));
    lag.observeFrame(buildUs: 50000, rasterUs: 0, totalUs: 50000);
    await gesture.up();
    expect(of('mobile_lag_frame').single['interaction'], 'scroll');
    expect(lagHomeTabChanged, isNotNull);
    observer.dispose();
    expect(lagHomeTabChanged, isNull);
  });
}
