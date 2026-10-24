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
    lag.onScrollStart();
    lag.observeFrame(buildUs: 9000, rasterUs: 48000, totalUs: 60000);
    final frame = of('mobile_lag_frame').single;
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

  test('a moved pointer is not a tap; frames within a second of a tap are tap frames', () {
    lag.onPointerDown(Offset.zero);
    lag.onPointerMove(const Offset(0, 40));
    lag.onPointerUp();
    lag.observeFrame(buildUs: 50000, rasterUs: 0, totalUs: 50000);
    expect(of('mobile_lag_frame').single['interaction'], 'idle');
  });

  test('input is ignored while capture is off, and turning it off forgets a live scroll', () {
    lag.onScrollStart();
    lag.active = false;
    lag.onScrollStart();
    lag.onPointerDown(Offset.zero);
    lag.onPointerUp();
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
}
