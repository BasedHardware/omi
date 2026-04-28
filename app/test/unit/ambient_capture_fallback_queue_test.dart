import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/ambient_capture/ambient_capture_health.dart';
import 'package:omi/services/ambient_capture/ambient_capture_models.dart';
import 'package:omi/services/ambient_capture/fallback_segment_queue.dart';

void main() {
  test('fallback segment queue persists and clears pending segments', () async {
    final dir = await Directory.systemTemp.createTemp('ambient_queue_test');
    final file = File('${dir.path}/queue.jsonl');
    final queue = FallbackSegmentQueue(file: file);
    final segment = AmbientFallbackSegment(
      text: 'Visible caption text',
      source: AmbientFallbackSource.accessibilityCaption,
      start: DateTime.utc(2026, 1, 1, 12),
      end: DateTime.utc(2026, 1, 1, 12, 0, 1),
      healthState: AmbientCaptureHealthState.textOnlyFallback,
      foregroundAppPackage: 'us.zoom.videomeetings',
      rawAudioAvailable: false,
    );

    await queue.enqueue(segment);
    await queue.enqueue(segment);
    final pending = await queue.loadPending();

    expect(pending, hasLength(1));
    expect(pending.first.text, 'Visible caption text');
    expect(pending.first.source, AmbientFallbackSource.accessibilityCaption);

    await queue.markUploaded(pending);
    expect(await queue.loadPending(), isEmpty);
    await queue.clearUploaded();
    expect(await file.readAsString(), isEmpty);

    await queue.clear();
    expect(await file.exists(), isFalse);
  });
}
