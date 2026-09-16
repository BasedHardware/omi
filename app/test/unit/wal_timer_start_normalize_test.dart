import 'package:flutter_test/flutter_test.dart';

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
      const proposed = now + walMaxFutureSkewSeconds + 60;
      expect(normalizeWalTimerStart(proposed, durationSeconds: 120, nowSeconds: now), now - 120);
    });

    test('treats negative duration as zero-length window', () {
      const proposed = now + 30;
      expect(normalizeWalTimerStart(proposed, durationSeconds: -5, nowSeconds: now), proposed);
    });
  });
}
