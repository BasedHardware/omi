import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';

import '../../integration_test/perf/heavy_frame_collector.dart';

void main() {
  FrameTiming frame(int cost) => FrameTiming(
        vsyncStart: 0,
        buildStart: 0,
        buildFinish: cost,
        rasterStart: cost,
        rasterFinish: cost + 1,
        rasterFinishWallTime: cost + 1,
      );

  test('sparse cold p90 retains the worst frame at six and seven samples', () {
    for (final count in [6, 7]) {
      final frames = [for (var i = 0; i < count - 1; i++) frame(1000), frame(160000)];
      final result = HeavyFrameCollector.summarize('cold_start', frames, const Duration(seconds: 1));
      expect(result['build_p90_us'], 160000);
      expect(result['worst_build_us'], 160000);
      expect(result['frames_over_100ms'], 1);
      expect(result['frame_count'], count);
      expect(result['percentile_method'], 'nearest-rank/v1');
    }
  });

  test('nearest rank p90 selects rank 90 of 100 without changing jank counts', () {
    final frames = [for (var i = 1; i <= 100; i++) frame(i * 1000)];
    final result = HeavyFrameCollector.summarize('scroll', frames, const Duration(seconds: 1));
    expect(result['build_p90_us'], 90000);
    expect(result['build_p99_us'], 99000);
    expect(result['worst_build_us'], 100000);
    expect(result['frame_count'], 100);
  });

  test('total spans from the earlier of vsync and build start, never negative', () {
    // iOS 27 on device: build starts ~850 us before the recorded vsync.
    final early = FrameTiming(
      vsyncStart: 10850,
      buildStart: 10000,
      buildFinish: 10394,
      rasterStart: 10400,
      rasterFinish: 10546,
      rasterFinishWallTime: 10546,
    );
    expect(early.totalSpan.inMicroseconds, -304);
    expect(HeavyFrameCollector.frameTotalUs(early), 546);
    final result = HeavyFrameCollector.summarize('cold_start', [early, frame(1000)], const Duration(seconds: 1));
    expect(result['total_p50_us'], 546);
    expect(HeavyFrameCollector.frameTotalUs(frame(1000)), frame(1000).totalSpan.inMicroseconds);
  });

  test('stall probe counts only ticks blocked past 50 ms and sums the 100 ms ones', () {
    final probe = HeavyStallProbe();
    var now = 0;
    for (final gapMs in [20, 20, 70, 20, 160, 20, 1630]) {
      now += gapMs * 1000;
      probe.record(now);
    }
    final result = probe.stop();
    expect(result['stalls_over_50ms'], 3);
    expect(result['stalls_over_100ms'], 2);
    expect(result['stall_blocked_over_100ms_us'], 140000 + 1610000);
    expect(result['worst_stall_us'], 1610000);
  });
}
