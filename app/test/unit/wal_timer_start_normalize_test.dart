import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/wal.dart';

void main() {
  group('normalizeWalTimerStart (#4770)', () {
    const now = 2000000000;

    test('shifts a mildly future device window so it ends at now', () {
      const proposed = now + 180;
      final normalized = normalizeWalTimerStart(proposed, durationSeconds: 60, nowSeconds: now);

      expect(normalized, now - 60);
      expect(normalized + 60, now);
    });

    test('leaves a past capture window unchanged', () {
      const proposed = now - 600;
      expect(normalizeWalTimerStart(proposed, durationSeconds: 60, nowSeconds: now), proposed);
    });

    test('replaces far-future garbage with now minus duration', () {
      const proposed = now + 3600;
      expect(normalizeWalTimerStart(proposed, durationSeconds: 45, nowSeconds: now), now - 45);
    });

    test('zero-duration future start clamps to now', () {
      expect(normalizeWalTimerStart(now + 30, durationSeconds: 0, nowSeconds: now), now);
    });
  });

  group('batchWalClockShiftSeconds / normalizeWalTimerStartsInBatch (#4771)', () {
    const now = 2000000000;
    const skew = 180;
    const duration = 60;
    const device = 'omiabc';

    test('shared shift preserves five-minute offline shard span', () {
      final windows = [
        for (var i = 0; i < 5; i++) (start: now + skew + i * duration, durationSeconds: duration),
      ];
      final shift = batchWalClockShiftSeconds(windows, nowSeconds: now);
      expect(shift, skew + 5 * duration);

      final starts = <int>[];
      for (final window in windows) {
        final end = window.start + duration;
        starts.add(
          normalizeWalCaptureWindow(
            window.start,
            end,
            nowSeconds: now,
            clockShiftSeconds: shift,
          ).start,
        );
      }
      expect(starts, [for (var i = 0; i < 5; i++) now - 300 + i * duration]);
      expect(starts.toSet(), hasLength(5));
    });

    test('batch normalize keeps distinct Wal ids for equal-duration future shards', () {
      final wals = [
        for (var i = 0; i < 3; i++)
          Wal(
            timerStart: now + skew + i * duration,
            codec: BleAudioCodec.opus,
            seconds: duration,
            device: device,
          ),
      ];
      normalizeWalTimerStartsInBatch(wals, nowSeconds: now);

      final ids = wals.map((w) => w.id).toList();
      expect(ids.toSet(), hasLength(3));
      expect(wals.map((w) => w.getFileName()).toSet(), hasLength(3));
      expect(wals[0].timerStart, now - 3 * duration);
      expect(wals[1].timerStart, now - 2 * duration);
      expect(wals[2].timerStart, now - duration);
    });
  });
}
