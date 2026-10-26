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
}
